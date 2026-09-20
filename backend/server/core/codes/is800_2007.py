"""
NeuroPlan-3D — IS 800:2007 SCREENING CHECKS

IS 800:2007 is the Indian standard "General Construction in Steel — Code
of Practice" (limit state method).

THIS IS A SCREENING SUBSET, NOT A COMPLIANCE CHECK.
────────────────────────────────────────────────────────────────────────
Only the clauses listed in IMPLEMENTED_CLAUSES below are evaluated. A
structure passing every check here is NOT "IS 800 compliant" — most of
the code is not implemented, and several of the unimplemented parts
(connections, block shear, fatigue, fire) routinely govern real designs.
The coverage list is published alongside the results so the gap is
visible rather than implied away.

────────────────────────────────────────────────────────────────────────
IMPLEMENTED CLAUSES
────────────────────────────────────────────────────────────────────────
cl. 5.4.1 / Table 5 — Partial safety factors for material
    gamma_m0 = 1.10  (resistance governed by yielding or buckling)
    gamma_m1 = 1.25  (resistance governed by ultimate stress)

cl. 3.8 / Table 3 — Maximum effective slenderness ratio (KL/r)
    180  compression member carrying dead + imposed load
    250  compression member resisting wind/earthquake forces only
    400  tension member (no stress reversal)

cl. 3.7.2 / Table 2 — Section classification, CHS under axial compression
    with epsilon = sqrt(250/fy), fy in MPa:
        plastic       d/t <=  42 * epsilon^2
        compact       d/t <=  52 * epsilon^2
        semi-compact  d/t <= 146 * epsilon^2
        beyond that the section is SLENDER and local buckling governs.

cl. 6.2 — Design strength of a tension member, yielding of gross section
        T_dg = A_g * f_y / gamma_m0

cl. 7.1.2 — Design compressive strength
        P_d = A_e * f_cd
cl. 7.1.2.1 — Design compressive stress (Perry-Robertson column curve)
        f_cc   = pi^2 * E / lambda_eff^2          (Euler stress)
        lambda = sqrt(f_y / f_cc)                 (non-dimensional slenderness)
        phi    = 0.5 * [1 + alpha*(lambda - 0.2) + lambda^2]
        chi    = 1 / (phi + sqrt(phi^2 - lambda^2))      <= 1.0
        f_cd   = chi * f_y / gamma_m0
cl. 7.1.2.2 / Table 7 — Imperfection factor alpha by buckling class
        a: 0.21   b: 0.34   c: 0.49   d: 0.76
cl. 7.1.2.2 / Table 10 — Buckling class for a hollow section
        hot-finished  -> class a
        cold-formed   -> class b

Unlike the code-neutral Euler screening in analysis/buckling.py, the
column curve above IS valid in the inelastic range: that is precisely
what the imperfection factor and the chi reduction exist to capture.

────────────────────────────────────────────────────────────────────────
NOT IMPLEMENTED — these are declared, never silently skipped
────────────────────────────────────────────────────────────────────────
See UNSUPPORTED_CLAUSES.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from ...models.structure import Structure, MATERIAL_LIBRARY, MemberResult

CODE_NAME = "IS 800"
CODE_EDITION = "2007"
CODE_TITLE = "General Construction in Steel — Code of Practice (Limit State Method)"

# cl. 5.4.1, Table 5
GAMMA_M0 = 1.10
GAMMA_M1 = 1.25

# cl. 7.1.2.2, Table 7 — imperfection factors
IMPERFECTION_FACTOR = {"a": 0.21, "b": 0.34, "c": 0.49, "d": 0.76}

# cl. 3.8, Table 3 — maximum effective slenderness ratio
SLENDERNESS_LIMIT_COMPRESSION = 180.0
SLENDERNESS_LIMIT_WIND_ONLY = 250.0
SLENDERNESS_LIMIT_TENSION = 400.0

# cl. 3.7.2, Table 2 — CHS in axial compression, as multiples of epsilon^2
CHS_PLASTIC_LIMIT = 42.0
CHS_COMPACT_LIMIT = 52.0
CHS_SEMI_COMPACT_LIMIT = 146.0


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    NOT_SUPPORTED = "not_supported"


class SectionClass(str, Enum):
    PLASTIC = "plastic"
    COMPACT = "compact"
    SEMI_COMPACT = "semi_compact"
    SLENDER = "slender"


@dataclass
class CodeCheck:
    """
    One clause evaluated for one member.

    Every field the spec asks for is present: code, edition, clause,
    inputs, equation, demand, capacity, D/C ratio and status. A result
    that cannot show its inputs and equation is not reportable.
    """
    member_id: int
    clause: str
    check_name: str
    equation: str
    inputs: dict[str, str] = field(default_factory=dict)
    demand: float = 0.0            # N (or dimensionless for slenderness)
    capacity: float = 0.0
    unit: str = "N"
    dc_ratio: float = 0.0
    status: CheckStatus = CheckStatus.NOT_APPLICABLE
    note: str = ""
    code: str = CODE_NAME
    edition: str = CODE_EDITION


@dataclass
class MemberCodeReport:
    member_id: int
    axial_force: float
    is_compression: bool
    section_class: SectionClass
    checks: list[CodeCheck] = field(default_factory=list)

    @property
    def governing(self) -> CodeCheck | None:
        real = [c for c in self.checks
                if c.status in (CheckStatus.PASS, CheckStatus.FAIL)]
        return max(real, key=lambda c: c.dc_ratio) if real else None


@dataclass
class CodeScreeningReport:
    title: str = f"{CODE_NAME}:{CODE_EDITION} SCREENING CHECKS"
    code: str = CODE_NAME
    edition: str = CODE_EDITION
    code_title: str = CODE_TITLE
    members: list[MemberCodeReport] = field(default_factory=list)
    n_failed: int = 0
    max_dc_ratio: float = 0.0
    governing_member_id: int | None = None
    implemented_clauses: list[str] = field(default_factory=list)
    unsupported_clauses: list[str] = field(default_factory=list)
    compliance_disclaimer: str = (
        f"This is a SCREENING SUBSET of {CODE_NAME}:{CODE_EDITION}, not a "
        f"compliance check. Passing every check here does NOT establish "
        f"code compliance: the unimplemented clauses listed alongside "
        f"include connection design, block shear, fatigue and fire, any of "
        f"which can govern a real design."
    )


IMPLEMENTED_CLAUSES = [
    "cl. 5.4.1 / Table 5 — partial safety factors (gamma_m0 = 1.10, gamma_m1 = 1.25)",
    "cl. 3.7.2 / Table 2 — section classification, CHS in axial compression",
    "cl. 3.8 / Table 3 — maximum effective slenderness ratio",
    "cl. 6.2 — tension member, yielding of gross section",
    "cl. 7.1.2 / 7.1.2.1 — design compressive strength, Perry-Robertson curve",
    "cl. 7.1.2.2 / Table 7, Table 10 — imperfection factor and buckling class",
    "cl. 3.7.2 / Table 2 — section classification check (slender sections flagged)",
]

UNSUPPORTED_CLAUSES = [
    "cl. 6.3 — rupture of critical section: implemented SEPARATELY in "
    "is800_tension_extended.py, only when a bolted connection is "
    "explicitly declared (bolt hole sizes/layout are not otherwise known). "
    "Not part of this module's per-member screen.",
    "cl. 6.4 — block shear: implemented SEPARATELY (simplified, single "
    "bolt line only) in is800_tension_extended.py under the same condition.",
    "Design of members subjected to bending (the code's flexural-member "
    "provisions): this solver is pin-jointed and carries no bending moment.",
    "Combined axial force and bending provisions: no bending to combine.",
    "cl. 8.2.2 — lateral-torsional buckling: requires flexural members.",
    "Connections (bolts, welds) beyond what is covered in "
    "codes/connections.py and codes/is800_tension_extended.py.",
    "Fatigue: implemented separately in codes/fatigue.py using the S-N "
    "methodology, with the detail-category strength supplied by the "
    "caller rather than looked up from an embedded table — see that "
    "module for the exact clause citation and why the table itself is "
    "not embedded.",
    "Fire / elevated-temperature design: implemented separately in "
    "codes/fire.py using EN 1993-1-2 reduction factors, since IS "
    "800:2007 does not publish its own numeric reduction table for this.",
    "Durability / corrosion allowance provisions.",
    "cl. 5.5 — deflection limits are checked against the user's own "
    "serviceability ratio, not against Table 6.",
    "Load combinations from IS 875 / partial safety factors for LOADS "
    "are NOT applied — analysis is run at the combination the user "
    "selected, which is unfactored by default.",
    "This module cites clause numbers with high confidence where they are "
    "commonly and consistently referenced in practice (cl. 5.4.1, 6.2, "
    "6.3, 6.4, 7.1.2, Tables 2/3/5/7/10). Section-LEVEL numbers for "
    "topics outside the scope of this screening (fatigue, seismic "
    "detailing, working-stress design, durability) are deliberately not "
    "asserted here, since NeuroPlan cannot verify the current edition's "
    "exact section numbering — verify against the code text directly.",
]


def epsilon(fy_pa: float) -> float:
    """cl. 3.7.2: epsilon = sqrt(250 / fy), with fy in MPa."""
    fy_mpa = fy_pa / 1e6
    if fy_mpa <= 0:
        return 0.0
    return math.sqrt(250.0 / fy_mpa)


def classify_chs(outer_diameter: float, thickness: float, fy_pa: float) -> SectionClass:
    """cl. 3.7.2 / Table 2 — CHS under axial compression."""
    if thickness <= 0:
        return SectionClass.SLENDER
    d_over_t = outer_diameter / thickness
    e2 = epsilon(fy_pa) ** 2

    if d_over_t <= CHS_PLASTIC_LIMIT * e2:
        return SectionClass.PLASTIC
    if d_over_t <= CHS_COMPACT_LIMIT * e2:
        return SectionClass.COMPACT
    if d_over_t <= CHS_SEMI_COMPACT_LIMIT * e2:
        return SectionClass.SEMI_COMPACT
    return SectionClass.SLENDER


def design_compressive_stress(
    fy_pa: float, E_pa: float, slenderness: float, buckling_class: str = "a"
) -> tuple[float, dict[str, float]]:
    """
    cl. 7.1.2.1 — Perry-Robertson design compressive stress f_cd.

    Returns (f_cd in Pa, intermediate values for display).
    """
    alpha = IMPERFECTION_FACTOR[buckling_class]
    fy_over_gamma = fy_pa / GAMMA_M0

    if slenderness <= 0:
        return fy_over_gamma, {"f_cc": float("inf"), "lambda": 0.0, "phi": 0.5, "chi": 1.0}

    f_cc = (math.pi ** 2) * E_pa / (slenderness ** 2)
    lam = math.sqrt(fy_pa / f_cc)
    phi = 0.5 * (1.0 + alpha * (lam - 0.2) + lam ** 2)

    radicand = phi ** 2 - lam ** 2
    chi = 1.0 / (phi + math.sqrt(radicand)) if radicand > 0 else 1.0
    chi = min(chi, 1.0)

    return chi * fy_over_gamma, {
        "f_cc": f_cc, "lambda": lam, "phi": phi, "chi": chi, "alpha": alpha,
    }


def check_tension_yielding(member_id: int, axial_force: float,
                           area: float, fy_pa: float) -> CodeCheck:
    """cl. 6.2 — T_dg = A_g * f_y / gamma_m0."""
    capacity = area * fy_pa / GAMMA_M0
    demand = max(axial_force, 0.0)
    ratio = demand / capacity if capacity > 0 else float("inf")
    return CodeCheck(
        member_id=member_id,
        clause="cl. 6.2",
        check_name="Tension — yielding of gross section",
        equation="T_dg = A_g * f_y / gamma_m0",
        inputs={
            "A_g": f"{area*1e4:.2f} cm^2",
            "f_y": f"{fy_pa/1e6:.0f} MPa",
            "gamma_m0": f"{GAMMA_M0:.2f}",
        },
        demand=demand, capacity=capacity, unit="N", dc_ratio=ratio,
        status=CheckStatus.PASS if ratio <= 1.0 else CheckStatus.FAIL,
        note=(
            "Gross-section yielding only. Rupture of the net section "
            "(cl. 6.3) and block shear (cl. 6.4) are NOT checked — both "
            "need connection detail this model does not carry, and either "
            "can govern."
        ),
    )


def check_compression(member_id: int, axial_force: float, area: float,
                      fy_pa: float, E_pa: float, slenderness: float,
                      buckling_class: str = "a") -> CodeCheck:
    """cl. 7.1.2 — P_d = A_e * f_cd."""
    f_cd, parts = design_compressive_stress(fy_pa, E_pa, slenderness, buckling_class)
    capacity = area * f_cd
    demand = abs(min(axial_force, 0.0))
    ratio = demand / capacity if capacity > 0 else float("inf")

    return CodeCheck(
        member_id=member_id,
        clause="cl. 7.1.2 / 7.1.2.1",
        check_name="Compression — design compressive strength",
        equation=(
            "f_cc = pi^2 E/lambda_eff^2; lambda = sqrt(f_y/f_cc); "
            "phi = 0.5[1+alpha(lambda-0.2)+lambda^2]; "
            "chi = 1/(phi+sqrt(phi^2-lambda^2)); P_d = A_e * chi * f_y/gamma_m0"
        ),
        inputs={
            "A_e": f"{area*1e4:.2f} cm^2",
            "f_y": f"{fy_pa/1e6:.0f} MPa",
            "KL/r": f"{slenderness:.1f}",
            "buckling class": buckling_class,
            "alpha": f"{parts.get('alpha', 0):.2f}",
            "f_cc": f"{parts['f_cc']/1e6:.1f} MPa",
            "lambda": f"{parts['lambda']:.3f}",
            "phi": f"{parts['phi']:.3f}",
            "chi": f"{parts['chi']:.3f}",
            "f_cd": f"{f_cd/1e6:.1f} MPa",
        },
        demand=demand, capacity=capacity, unit="N", dc_ratio=ratio,
        status=CheckStatus.PASS if ratio <= 1.0 else CheckStatus.FAIL,
        note=(
            "Perry-Robertson column curve — valid in the inelastic range, "
            "unlike the code-neutral Euler screening."
        ),
    )


def check_slenderness_limit(member_id: int, slenderness: float,
                            is_compression: bool) -> CodeCheck:
    """cl. 3.8 / Table 3 — maximum effective slenderness ratio."""
    limit = (SLENDERNESS_LIMIT_COMPRESSION if is_compression
             else SLENDERNESS_LIMIT_TENSION)
    ratio = slenderness / limit if limit > 0 else float("inf")
    kind = "compression (dead + imposed)" if is_compression else "tension, no reversal"

    return CodeCheck(
        member_id=member_id,
        clause="cl. 3.8 / Table 3",
        check_name=f"Slenderness limit — {kind}",
        equation="KL/r <= limit",
        inputs={
            "KL/r": f"{slenderness:.1f}",
            "limit": f"{limit:.0f}",
        },
        demand=slenderness, capacity=limit, unit="-", dc_ratio=ratio,
        status=CheckStatus.PASS if ratio <= 1.0 else CheckStatus.FAIL,
        note=(
            f"Table 3 gives {SLENDERNESS_LIMIT_WIND_ONLY:.0f} where the "
            f"compression arises from wind or earthquake only; NeuroPlan "
            f"applies the stricter {SLENDERNESS_LIMIT_COMPRESSION:.0f} "
            f"because it does not track which case produced the force."
            if is_compression else
            "Applies where no stress reversal occurs."
        ),
    )


def check_section_classification(
    member_id: int, outer_diameter: float, wall_thickness: float,
    fy_pa: float,
) -> CodeCheck:
    """
    cl. 3.7.2 / Table 2 — section classification check for CHS.

    Makes the existing `classify_chs()` visible as a traceable CodeCheck.
    Slender sections FAIL because local buckling governs but the IS 800
    reduction for slender CHS is not implemented in this screening.
    """
    sec_class = classify_chs(outer_diameter, wall_thickness, fy_pa)
    eps = epsilon(fy_pa)
    d_over_t = outer_diameter / wall_thickness if wall_thickness > 0 else float("inf")
    semi_compact_limit = CHS_SEMI_COMPACT_LIMIT * eps ** 2

    if sec_class is SectionClass.SLENDER:
        status = CheckStatus.FAIL
        note = (
            f"d/t = {d_over_t:.1f} exceeds the semi-compact limit "
            f"({semi_compact_limit:.1f}). Local buckling governs but the "
            f"IS 800 effective-area reduction for slender CHS is NOT "
            f"implemented — this member's compression capacity may be "
            f"unconservative."
        )
    else:
        status = CheckStatus.PASS
        note = (
            f"Section classified as {sec_class.value.upper()}. "
            f"No local-buckling reduction required."
        )

    return CodeCheck(
        member_id=member_id,
        clause="cl. 3.7.2 / Table 2",
        check_name="Section classification — CHS",
        equation="d/t vs limits × epsilon^2, epsilon = sqrt(250/f_y)",
        inputs={
            "d": f"{outer_diameter*1000:.1f} mm",
            "t": f"{wall_thickness*1000:.1f} mm",
            "d/t": f"{d_over_t:.1f}",
            "f_y": f"{fy_pa/1e6:.0f} MPa",
            "epsilon": f"{eps:.4f}",
            "plastic limit (42ε²)": f"{CHS_PLASTIC_LIMIT * eps**2:.1f}",
            "compact limit (52ε²)": f"{CHS_COMPACT_LIMIT * eps**2:.1f}",
            "semi-compact limit (146ε²)": f"{semi_compact_limit:.1f}",
        },
        demand=d_over_t,
        capacity=semi_compact_limit,
        unit="-",
        dc_ratio=d_over_t / semi_compact_limit if semi_compact_limit > 0 else float("inf"),
        status=status,
        note=note,
    )


def check_effective_length_assumption(
    member_id: int, k_factor: float, length: float,
) -> CodeCheck:
    """
    Document the effective length factor assumption.

    This is NOT a pass/fail check — it is a NOT_SUPPORTED disclosure.
    The k-factor cannot be determined without connection rigidity data,
    which this model does not carry.
    """
    return CodeCheck(
        member_id=member_id,
        clause="cl. 7.2.2",
        check_name="Effective length factor",
        equation="KL = k × L",
        inputs={
            "k (assumed)": f"{k_factor:.2f}",
            "L": f"{length*1000:.1f} mm",
            "KL": f"{k_factor * length * 1000:.1f} mm",
        },
        demand=0.0, capacity=0.0, unit="-", dc_ratio=0.0,
        status=CheckStatus.NOT_SUPPORTED,
        note=(
            f"Effective length factor k = {k_factor:.2f} is ASSUMED, not "
            f"determined from connection rigidity. Real k depends on end "
            f"conditions (pinned/fixed/partial fixity) that this model does "
            f"not carry. For pinned truss joints, k ≈ 1.0 is standard "
            f"practice but must be verified by the engineer."
        ),
    )


def screen_structure(
    structure: Structure,
    member_results: list[MemberResult],
    k_factor: float = 1.0,
    buckling_class: str = "a",
) -> CodeScreeningReport:
    """Run the implemented IS 800:2007 clauses across every member."""
    nodes = structure.node_dict()
    by_id = {m.id: m for m in structure.members}
    report = CodeScreeningReport(
        implemented_clauses=list(IMPLEMENTED_CLAUSES),
        unsupported_clauses=list(UNSUPPORTED_CLAUSES),
    )

    for result in member_results:
        member = by_id.get(result.member_id)
        if member is None:
            continue
        material = MATERIAL_LIBRARY.get(member.material_key)
        if material is None:
            continue

        section = member.section
        length = member.length(nodes)
        r_gyration = section.radius_of_gyration
        slenderness = (k_factor * length / r_gyration) if r_gyration > 0 else float("inf")
        is_compression = result.axial_force < 0

        member_report = MemberCodeReport(
            member_id=member.id,
            axial_force=result.axial_force,
            is_compression=is_compression,
            section_class=classify_chs(
                section.outer_diameter, section.wall_thickness, material.yield_stress
            ),
        )

        # Strength check — compression or tension
        if is_compression:
            member_report.checks.append(check_compression(
                member.id, result.axial_force, section.area,
                material.yield_stress, material.E, slenderness, buckling_class,
            ))
        else:
            member_report.checks.append(check_tension_yielding(
                member.id, result.axial_force, section.area, material.yield_stress,
            ))

        # Slenderness limit
        member_report.checks.append(
            check_slenderness_limit(member.id, slenderness, is_compression)
        )

        # Section classification (makes classify_chs visible as a CodeCheck)
        member_report.checks.append(
            check_section_classification(
                member.id, section.outer_diameter,
                section.wall_thickness, material.yield_stress,
            )
        )

        # Effective length assumption disclosure
        member_report.checks.append(
            check_effective_length_assumption(member.id, k_factor, length)
        )

        report.members.append(member_report)

        for check in member_report.checks:
            if check.status is CheckStatus.FAIL:
                report.n_failed += 1
            if check.status in (CheckStatus.PASS, CheckStatus.FAIL):
                if check.dc_ratio > report.max_dc_ratio:
                    report.max_dc_ratio = check.dc_ratio
                    report.governing_member_id = member.id

    return report
