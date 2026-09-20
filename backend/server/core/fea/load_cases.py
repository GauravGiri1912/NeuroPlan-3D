"""
NeuroPlan-3D — Load Cases and Self-Weight

Makes every force entering the solver explicit and attributable. Nothing
is applied inside the solver that is not listed in a load case here.

────────────────────────────────────────────────────────────────────────
SELF-WEIGHT: MATHEMATICAL FORMULATION
────────────────────────────────────────────────────────────────────────
For each member m with material density rho, cross-sectional area A and
length L:

    mass_m   = rho * A * L                      [kg]
    weight_m = mass_m * g,   g = 9.80665 m/s^2  [N]

The weight is a distributed load w = rho * A * g [N/m] acting along the
member. For a 2-node bar element with linear shape functions N1 = 1 - x/L
and N2 = x/L, the consistent nodal load vector for a uniform transverse
load w is

    f_i = integral_0^L w * N1 dx = w * L / 2
    f_j = integral_0^L w * N2 dx = w * L / 2

so exactly half of each member's weight goes to each end node, applied in
the -Y direction (Y is up in NeuroPlan's coordinate system):

    F_y(node) -= sum over members touching node of (rho * A * L * g) / 2

This "half to each end" result is not an approximation of the consistent
vector — for a uniform load on a linear bar it IS the consistent vector.

ASSUMPTIONS (and what they exclude):
  1. Members are pin-jointed and carry axial force only, so a member does
     not resist its own weight in bending. Local sag of a member under
     self-weight is NOT modelled. This is consistent with the rest of the
     solver, which has no rotational DOF.
  2. Gravity acts in -Y. There is no support for tilted gravity.
  3. Connection hardware, gusset plates, bolts, decking, cladding and any
     non-structural mass are NOT included. Only the prismatic volume of
     the modelled members contributes.
  4. Density comes from MATERIAL_LIBRARY; a member whose material key is
     unknown contributes zero weight and is reported as such rather than
     silently skipped.

────────────────────────────────────────────────────────────────────────
LOAD CASES
────────────────────────────────────────────────────────────────────────
A case is only marked `supported` if the physics behind it is actually
implemented. Unsupported cases are still listed — with the reason — so
the limitation is visible rather than absent.
"""
from __future__ import annotations


from dataclasses import dataclass, field
from enum import Enum

from ...models.structure import (
    Structure, PointLoad, MATERIAL_LIBRARY, LoadCaseType,
    LoadSummary, LoadCaseSummary, SelfWeightSummary,
)

# Standard gravity, CODATA / ISO 80000-3.
GRAVITY = 9.80665  # m/s^2

__all__ = [
    "GRAVITY", "LoadCaseType", "MemberWeight", "SelfWeightResult", "LoadCase",
    "LoadCombination", "compute_self_weight", "build_load_cases",
    "DEFAULT_COMBINATION", "LIVE_ONLY_COMBINATION",
]


@dataclass
class MemberWeight:
    """Per-member self-weight breakdown — the audit trail for the total."""
    member_id: int
    material_key: str
    density: float          # kg/m^3
    area_m2: float
    length_m: float
    mass_kg: float
    weight_n: float
    known_material: bool = True


@dataclass
class SelfWeightResult:
    """Everything needed to display and verify the dead load case."""
    member_weights: list[MemberWeight]
    total_mass_kg: float
    total_weight_n: float
    gravity: float
    nodal_loads: list[PointLoad]
    unknown_material_members: list[int] = field(default_factory=list)

    def applied_weight_n(self) -> float:
        """Sum of what was actually put into the load vector (must equal total_weight_n)."""
        return -sum(load.fy for load in self.nodal_loads)


@dataclass
class LoadCase:
    """One named load case and the nodal forces it contributes."""
    case_type: LoadCaseType
    name: str
    supported: bool
    loads: list[PointLoad] = field(default_factory=list)
    formulation: str = ""
    assumptions: list[str] = field(default_factory=list)
    limitations: str = ""
    unsupported_reason: str = ""

    # True for cases that act through a mechanism other than nodal point
    # loads (thermal equivalent forces, prescribed support displacement),
    # so `active` cannot be inferred from `loads` alone.
    applied_non_nodally: bool = False

    @property
    def active(self) -> bool:
        """A case is active only if it is supported AND actually applied."""
        return self.supported and (bool(self.loads) or self.applied_non_nodally)

    def resultant(self) -> tuple[float, float, float]:
        return (
            sum(l.fx for l in self.loads),
            sum(l.fy for l in self.loads),
            sum(l.fz for l in self.loads),
        )


@dataclass
class LoadCombination:
    """
    A factored sum of load cases.

    Factors are explicit and displayed. NeuroPlan does not apply hidden
    code factors — a combination is only labelled with a code reference
    if that code's clause was actually implemented.
    """
    name: str
    factors: dict[LoadCaseType, float]
    description: str = ""
    source: str = "User / NeuroPlan default — not a code-mandated combination"

    def factor_for(self, case_type: LoadCaseType) -> float:
        return self.factors.get(case_type, 0.0)


def compute_self_weight(structure: Structure, gravity: float = GRAVITY) -> SelfWeightResult:
    """
    Compute member self-weight and lump it to end nodes.

    See the module docstring for the derivation. Returns the full
    per-member breakdown so the displayed total can be audited rather
    than trusted.
    """
    nodes = structure.node_dict()
    member_weights: list[MemberWeight] = []
    unknown: list[int] = []
    nodal_fy: dict[int, float] = {}

    for member in structure.members:
        material = MATERIAL_LIBRARY.get(member.material_key)
        length = member.length(nodes)
        area = member.section.area

        if material is None:
            unknown.append(member.id)
            member_weights.append(MemberWeight(
                member_id=member.id, material_key=member.material_key,
                density=0.0, area_m2=area, length_m=length,
                mass_kg=0.0, weight_n=0.0, known_material=False,
            ))
            continue

        mass = material.density * area * length
        weight = mass * gravity
        member_weights.append(MemberWeight(
            member_id=member.id, material_key=member.material_key,
            density=material.density, area_m2=area, length_m=length,
            mass_kg=mass, weight_n=weight,
        ))

        # Consistent nodal load for a uniform load on a linear bar: wL/2 each end.
        half = weight / 2.0
        nodal_fy[member.node_i] = nodal_fy.get(member.node_i, 0.0) - half
        nodal_fy[member.node_j] = nodal_fy.get(member.node_j, 0.0) - half

    nodal_loads = [
        PointLoad(node_id=nid, fx=0.0, fy=fy, fz=0.0, case=LoadCaseType.DEAD)
        for nid, fy in sorted(nodal_fy.items())
        if fy != 0.0
    ]

    total_mass = sum(mw.mass_kg for mw in member_weights)
    return SelfWeightResult(
        member_weights=member_weights,
        total_mass_kg=total_mass,
        total_weight_n=total_mass * gravity,
        gravity=gravity,
        nodal_loads=nodal_loads,
        unknown_material_members=unknown,
    )


_WIND_CASE_AXIS = {
    LoadCaseType.WIND_PLUS_X: ("fx", 1.0),
    LoadCaseType.WIND_MINUS_X: ("fx", -1.0),
    LoadCaseType.WIND_PLUS_Z: ("fz", 1.0),
    LoadCaseType.WIND_MINUS_Z: ("fz", -1.0),
}

_WIND_LIMITATION = (
    "Applied as nodal lateral forces of a user-specified magnitude. This "
    "is NOT a code-derived wind load: there is no velocity pressure, "
    "terrain/exposure category, gust factor, shape or drag coefficient, "
    "or projected-area calculation. The magnitude is an input, not a "
    "derived demand."
)

_THERMAL_LIMITATION = (
    "Uniform temperature change only. No through-depth gradient (which "
    "would cause bending, and this solver has no rotational DOF), no "
    "temperature-dependent E or yield strength, and therefore NOT valid "
    "for fire conditions."
)

_SETTLEMENT_LIMITATION = (
    "The settlement magnitude is an INPUT, not a prediction. There is no "
    "soil model: no bearing capacity, consolidation theory or "
    "time-dependent settlement. Note that in a statically determinate "
    "structure a support movement produces displacement but no member "
    "force — forces develop only where the structure is indeterminate."
)


def build_load_cases(
    structure: Structure,
    include_self_weight: bool = True,
    gravity: float = GRAVITY,
    thermal=None,
    settlements=None,
) -> tuple[list[LoadCase], SelfWeightResult | None]:
    """
    Group every force acting on the structure into explicit, named cases.

    Applied loads are partitioned by their own `case` tag — nothing is
    guessed. The DEAD case is computed here from member geometry and
    density rather than being supplied by the caller.
    """
    cases: list[LoadCase] = []

    self_weight = compute_self_weight(structure, gravity) if include_self_weight else None
    cases.append(LoadCase(
        case_type=LoadCaseType.DEAD,
        name="Dead — structural self-weight",
        supported=True,
        loads=list(self_weight.nodal_loads) if self_weight else [],
        formulation="w_m = rho*A*L*g; lumped as w_m/2 at each end node in -Y",
        assumptions=[
            "Members carry axial force only; member sag under self-weight is not modelled.",
            "Gravity acts in -Y at 9.80665 m/s^2.",
            "Only modelled member volume contributes — no connections, gussets, decking or cladding.",
        ],
        limitations=(
            "Non-structural mass (deck, services, finishes) is NOT included. "
            "This is the self-weight of the modelled members only."
            if include_self_weight else
            "Self-weight is DISABLED for this run — the structure is analysed as weightless."
        ),
    ))

    by_case: dict[LoadCaseType, list[PointLoad]] = {}
    for load in structure.loads:
        by_case.setdefault(load.case, []).append(load)

    cases.append(LoadCase(
        case_type=LoadCaseType.LIVE,
        name="Live — applied service load",
        supported=True,
        loads=by_case.get(LoadCaseType.LIVE, []),
        formulation="User-specified nodal forces applied directly to the load vector",
        assumptions=[
            "Loads are static and applied at nodes.",
            "No dynamic amplification, impact or load-duration factor is applied.",
        ],
        limitations=(
            "Magnitude and position come from the requirement specification; "
            "they are not derived from an occupancy or traffic loading code."
        ),
    ))

    for case_type, (component, _sign) in _WIND_CASE_AXIS.items():
        loads = by_case.get(case_type, [])
        cases.append(LoadCase(
            case_type=case_type,
            name=f"Wind — {case_type.value.replace('wind_', '').replace('_', ' ')}",
            supported=True,
            loads=loads,
            formulation=f"User-specified lateral nodal forces along {component[-1].upper()}",
            assumptions=["Static equivalent lateral force applied at nodes."],
            limitations=_WIND_LIMITATION,
        ))

    cases.append(LoadCase(
        case_type=LoadCaseType.THERMAL,
        name="Thermal — uniform temperature change",
        supported=True,
        applied_non_nodally=bool(thermal is not None and thermal.delta_t != 0.0),
        formulation="N_T = E*A*alpha*dT; equivalent nodal vector N_T*[-c, +c] per member",
        assumptions=[
            "Uniform temperature change over every member.",
            "alpha and E constant with temperature.",
            f"dT = {thermal.delta_t:+.1f} K" if thermal else "No temperature change applied.",
        ],
        limitations=_THERMAL_LIMITATION,
    ))

    cases.append(LoadCase(
        case_type=LoadCaseType.SETTLEMENT,
        name="Settlement — imposed support displacement",
        supported=True,
        applied_non_nodally=bool(settlements and any(
            s.dx or s.dy or s.dz for s in settlements
        )),
        formulation="Prescribed u_c; K_ff u_f = F_f - K_fc u_c (partitioned solve)",
        assumptions=[
            "Settlement magnitude is a user input, not a soil-mechanics prediction.",
            "Instantaneous and final — no time-dependent consolidation.",
        ],
        limitations=_SETTLEMENT_LIMITATION,
    ))

    return cases, self_weight


def summarize_load_cases(
    cases: list[LoadCase],
    combination: LoadCombination,
    self_weight: SelfWeightResult | None,
) -> LoadSummary:
    """
    Build the displayable record of what was applied.

    Totals here are the FACTORED resultants — i.e. exactly what enters the
    global load vector — so the summary can be checked against the
    solver's reactions rather than merely described.
    """
    case_summaries: list[LoadCaseSummary] = []
    tx = ty = tz = 0.0

    for case in cases:
        factor = combination.factor_for(case.case_type) if case.active else 0.0
        rx, ry, rz = case.resultant()
        tx += factor * rx
        ty += factor * ry
        tz += factor * rz
        case_summaries.append(LoadCaseSummary(
            case_type=case.case_type.value,
            name=case.name,
            supported=case.supported,
            active=case.active,
            factor=factor,
            resultant_fx=rx, resultant_fy=ry, resultant_fz=rz,
            n_loads=len(case.loads),
            formulation=case.formulation,
            assumptions=list(case.assumptions),
            limitations=case.limitations,
            unsupported_reason=case.unsupported_reason,
        ))

    sw_summary = None
    if self_weight is not None:
        sw_summary = SelfWeightSummary(
            included=True,
            gravity=self_weight.gravity,
            total_mass_kg=self_weight.total_mass_kg,
            total_weight_n=self_weight.total_weight_n,
            applied_weight_n=self_weight.applied_weight_n(),
            n_loaded_nodes=len(self_weight.nodal_loads),
            unknown_material_members=list(self_weight.unknown_material_members),
        )
    else:
        sw_summary = SelfWeightSummary(
            included=False, gravity=GRAVITY, total_mass_kg=0.0,
            total_weight_n=0.0, applied_weight_n=0.0, n_loaded_nodes=0,
        )

    return LoadSummary(
        combination_name=combination.name,
        combination_description=combination.description,
        combination_source=combination.source,
        cases=case_summaries,
        self_weight=sw_summary,
        total_applied_fx=tx,
        total_applied_fy=ty,
        total_applied_fz=tz,
    )


def collect_factored_loads(
    cases: list[LoadCase],
    combination: LoadCombination,
) -> list[PointLoad]:
    """
    Flatten active cases into the factored nodal loads the solver applies.

    An unsupported case contributes nothing regardless of its factor — a
    combination cannot conjure physics the solver does not implement.
    """
    out: list[PointLoad] = []
    for case in cases:
        if not case.active:
            continue
        factor = combination.factor_for(case.case_type)
        if factor == 0.0:
            continue
        for load in case.loads:
            out.append(PointLoad(
                node_id=load.node_id,
                fx=load.fx * factor,
                fy=load.fy * factor,
                fz=load.fz * factor,
                case=case.case_type,
            ))
    return out


DEFAULT_COMBINATION = LoadCombination(
    name="D + L (unfactored service)",
    factors={LoadCaseType.DEAD: 1.0, LoadCaseType.LIVE: 1.0,
             LoadCaseType.WIND_PLUS_X: 1.0, LoadCaseType.WIND_MINUS_X: 1.0,
             LoadCaseType.WIND_PLUS_Z: 1.0, LoadCaseType.WIND_MINUS_Z: 1.0},
    description=(
        "Unfactored service-level combination: self-weight plus the applied "
        "loads exactly as specified, each at factor 1.0."
    ),
    source=(
        "NeuroPlan default. This is NOT a code load combination — no "
        "partial safety factors from IS 875 / IS 800 / ASCE 7 are applied."
    ),
)

LIVE_ONLY_COMBINATION = LoadCombination(
    name="L only (self-weight excluded)",
    factors={LoadCaseType.LIVE: 1.0,
             LoadCaseType.WIND_PLUS_X: 1.0, LoadCaseType.WIND_MINUS_X: 1.0,
             LoadCaseType.WIND_PLUS_Z: 1.0, LoadCaseType.WIND_MINUS_Z: 1.0},
    description="Applied loads only; the structure is treated as weightless.",
    source="NeuroPlan default for comparison against hand calculations.",
)
