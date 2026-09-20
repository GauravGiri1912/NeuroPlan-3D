"""
NeuroPlan-3D Core Data Models

Defines all engineering entities used throughout the system:
structures, materials, sections, loads, supports, and analysis results.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid
import math


# ─────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────

class StructureType(str, Enum):
    """
    Only types with an implemented generator belong here — see
    server/core/generator/topology.py's `generate_structure` dispatch table,
    which raises rather than silently substituting a different type for
    anything not listed both here and there.

    PLANAR types put every node at z=0 (a 2D structural system solved with
    the 3D formulation, requiring artificial out-of-plane bracing supports).
    SPATIAL types produce genuinely three-dimensional geometry with members
    spanning all three axes and no artificial bracing.
    """
    # --- Planar (z = 0 for every node) ---
    PRATT = "pratt"
    WARREN = "warren"
    HOWE = "howe"
    # --- Spatial (genuine x/y/z geometry) ---
    SPACE_TRUSS = "space_truss"

    @property
    def is_spatial(self) -> bool:
        return self is StructureType.SPACE_TRUSS


PLANAR_STRUCTURE_TYPES = (StructureType.PRATT, StructureType.WARREN, StructureType.HOWE)
SPATIAL_STRUCTURE_TYPES = (StructureType.SPACE_TRUSS,)


class DimensionalityIntent(str, Enum):
    """
    What the requirement actually stated about 2D vs. 3D.

    Selecting a structural system is a decision with engineering
    consequences, so the basis for that decision is carried with the spec
    rather than discarded. UNSPECIFIED and CONFLICTING both mean the
    chosen system is an interpretation, not something the user asked for,
    and must not be presented as a confident reading.
    """
    EXPLICIT_SPATIAL = "explicit_spatial"   # user asked for 3D / space truss
    EXPLICIT_PLANAR = "explicit_planar"     # user asked for 2D / named a planar type
    CONFLICTING = "conflicting"             # both stated, e.g. "3D Pratt truss"
    UNSPECIFIED = "unspecified"             # neither stated — default applied

    @property
    def is_explicit(self) -> bool:
        return self in (
            DimensionalityIntent.EXPLICIT_SPATIAL,
            DimensionalityIntent.EXPLICIT_PLANAR,
        )


class SupportType(str, Enum):
    PIN = "pin"         # Restrains dx, dy, dz
    ROLLER_X = "roller_x"  # Restrains dy, dz (free in x)
    ROLLER_Z = "roller_z"  # Restrains dx, dy (free in z)
    FIXED = "fixed"     # Restrains dx, dy, dz (same as pin for truss)
    OUT_OF_PLANE = "out_of_plane"  # Restrains dz only (lateral/sway bracing for planar trusses)
    VERTICAL_ONLY = "vertical_only"  # Restrains dy only (bearing free to slide in the x-z plane)


class MemberStatus(str, Enum):
    OK = "ok"
    OVERSTRESSED = "overstressed"
    BUCKLING_RISK = "buckling_risk"


class NodeStatus(str, Enum):
    OK = "ok"
    EXCESSIVE_DISPLACEMENT = "excessive_displacement"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"


class RepairStrategy(str, Enum):
    """Only strategies the repair engine actually implements — see
    server/core/repair/engine.py's `_select_strategy`."""
    INCREASE_SECTION = "increase_section"
    INCREASE_HEIGHT = "increase_height"


class FailureType(str, Enum):
    STRESS_EXCEEDED = "stress_exceeded"
    DISPLACEMENT_EXCEEDED = "displacement_exceeded"
    BUCKLING_RISK = "buckling_risk"
    INSTABILITY = "instability"


# ─────────────────────────────────────────────
# Materials
# ─────────────────────────────────────────────

@dataclass
class Material:
    key: str
    name: str
    E: float           # Young's modulus in Pa
    yield_stress: float # Yield stress in Pa
    density: float      # kg/m³

    @property
    def E_gpa(self) -> float:
        return self.E / 1e9

    @property
    def yield_stress_mpa(self) -> float:
        return self.yield_stress / 1e6


MATERIAL_LIBRARY: dict[str, Material] = {
    "A36": Material(
        key="A36",
        name="ASTM A36 Steel",
        E=200e9,
        yield_stress=250e6,
        density=7850.0,
    ),
    "A992": Material(
        key="A992",
        name="ASTM A992 Steel",
        E=200e9,
        yield_stress=345e6,
        density=7850.0,
    ),
    "AL6061": Material(
        key="AL6061",
        name="Aluminum 6061-T6",
        E=68.9e9,
        yield_stress=276e6,
        density=2700.0,
    ),
}


# ─────────────────────────────────────────────
# Cross-Sections
# ─────────────────────────────────────────────

@dataclass
class CrossSection:
    """Circular Hollow Section (CHS) — MVP default."""
    outer_diameter: float  # meters
    wall_thickness: float  # meters

    @property
    def area(self) -> float:
        """Cross-sectional area in m²."""
        r_out = self.outer_diameter / 2
        r_in = r_out - self.wall_thickness
        return math.pi * (r_out**2 - r_in**2)

    @property
    def moment_of_inertia(self) -> float:
        """Second moment of area in m⁴ (for buckling check)."""
        r_out = self.outer_diameter / 2
        r_in = r_out - self.wall_thickness
        return (math.pi / 4) * (r_out**4 - r_in**4)

    @property
    def radius_of_gyration(self) -> float:
        """Radius of gyration in m."""
        if self.area == 0:
            return 0.0
        return math.sqrt(self.moment_of_inertia / self.area)

    def scaled(self, factor: float) -> CrossSection:
        """Return a new section with outer diameter scaled by factor,
        keeping wall thickness proportional."""
        return CrossSection(
            outer_diameter=self.outer_diameter * factor,
            wall_thickness=self.wall_thickness * factor,
        )


# Default section catalog
SECTION_CATALOG: dict[str, CrossSection] = {
    "CHS_76x3.2":  CrossSection(0.0762, 0.0032),   # 76.2mm OD, 3.2mm wall
    "CHS_89x4":    CrossSection(0.0889, 0.0040),
    "CHS_114x4":   CrossSection(0.1143, 0.0040),
    "CHS_114x6":   CrossSection(0.1143, 0.0064),
    "CHS_141x6":   CrossSection(0.1413, 0.0064),
    "CHS_168x6":   CrossSection(0.1683, 0.0064),
    "CHS_219x8":   CrossSection(0.2191, 0.0080),
}


# ─────────────────────────────────────────────
# Structural Geometry
# ─────────────────────────────────────────────

@dataclass
class Node:
    id: int
    x: float  # meters
    y: float  # meters
    z: float  # meters (0.0 for planar trusses)


@dataclass
class Member:
    id: int
    node_i: int  # start node ID
    node_j: int  # end node ID
    material_key: str
    section: CrossSection

    def length(self, nodes: dict[int, Node]) -> float:
        ni = nodes[self.node_i]
        nj = nodes[self.node_j]
        return math.sqrt(
            (nj.x - ni.x)**2 +
            (nj.y - ni.y)**2 +
            (nj.z - ni.z)**2
        )


@dataclass
class Support:
    node_id: int
    support_type: SupportType
    dx: bool = True   # restrain x displacement
    dy: bool = True   # restrain y displacement
    dz: bool = True   # restrain z displacement

    def __post_init__(self):
        if self.support_type == SupportType.PIN:
            self.dx, self.dy, self.dz = True, True, True
        elif self.support_type == SupportType.ROLLER_X:
            self.dx, self.dy, self.dz = False, True, True
        elif self.support_type == SupportType.ROLLER_Z:
            self.dx, self.dy, self.dz = True, True, False
        elif self.support_type == SupportType.FIXED:
            self.dx, self.dy, self.dz = True, True, True
        elif self.support_type == SupportType.OUT_OF_PLANE:
            self.dx, self.dy, self.dz = False, False, True
        elif self.support_type == SupportType.VERTICAL_ONLY:
            self.dx, self.dy, self.dz = False, True, False


class LoadCaseType(str, Enum):
    """
    Named load cases. Defined here (rather than in the FEA package) so a
    PointLoad can carry its own case tag without a circular import.

    Which of these are actually SUPPORTED by the solver is decided in
    `core/fea/load_cases.py`, not here — this enum only names them.
    """
    DEAD = "dead"
    LIVE = "live"
    WIND_PLUS_X = "wind_plus_x"
    WIND_MINUS_X = "wind_minus_x"
    WIND_PLUS_Z = "wind_plus_z"
    WIND_MINUS_Z = "wind_minus_z"
    THERMAL = "thermal"
    SETTLEMENT = "settlement"


@dataclass
class PointLoad:
    node_id: int
    fx: float = 0.0  # Newtons
    fy: float = 0.0  # Newtons
    fz: float = 0.0  # Newtons
    # Which load case this force belongs to. Defaults to LIVE so that any
    # existing caller that builds loads without a case keeps working and
    # is grouped as an applied service load, never silently as dead load.
    case: LoadCaseType = LoadCaseType.LIVE


@dataclass
class Structure:
    nodes: list[Node]
    members: list[Member]
    supports: list[Support]
    loads: list[PointLoad]

    def node_dict(self) -> dict[int, Node]:
        return {n.id: n for n in self.nodes}

    def member_dict(self) -> dict[int, Member]:
        return {m.id: m for m in self.members}

    def total_weight(self) -> float:
        """Estimate total structural weight in kg."""
        nd = self.node_dict()
        weight = 0.0
        for m in self.members:
            mat = MATERIAL_LIBRARY.get(m.material_key)
            if mat:
                length = m.length(nd)
                weight += mat.density * m.section.area * length
        return weight


# ─────────────────────────────────────────────
# Engineering Specification (parsed from NL)
# ─────────────────────────────────────────────

@dataclass
class EngineeringSpec:
    structure_type: StructureType = StructureType.PRATT
    span: float = 20.0              # meters (x direction)
    height: float = 3.0             # meters (y direction — structural depth)
    width: float = 0.0              # meters (z direction). 0 = planar; >0 required for spatial types
    num_panels: int = 6             # number of panels
    primary_load: float = 50000.0   # Newtons — VERTICAL (−y) magnitude
    lateral_load_x: float = 0.0     # Newtons — longitudinal (+x), e.g. braking/traction
    lateral_load_z: float = 0.0     # Newtons — transverse (+z), e.g. wind
    load_description: str = "center point load"
    material_key: str = "A36"
    section_key: str = "CHS_114x6"
    safety_factor: float = 1.67
    max_displacement_ratio: float = 300.0  # L/300
    description: str = ""
    raw_input: str = ""
    # Phase 14 honesty: every value the user did NOT specify, which the system
    # filled in on their behalf. Surfaced in the API/UI — never silently hidden.
    defaults_applied: list[str] = field(default_factory=list)
    # How structure_type's dimensionality was arrived at. UNSPECIFIED and
    # CONFLICTING mean the planar/spatial choice is an interpretation, so the
    # UI must not render it as a stated requirement.
    dimensionality_intent: DimensionalityIntent = DimensionalityIntent.UNSPECIFIED

    def note_default(self, message: str) -> None:
        if message not in self.defaults_applied:
            self.defaults_applied.append(message)


# ─────────────────────────────────────────────
# Analysis Results
# ─────────────────────────────────────────────

@dataclass
class MemberResult:
    member_id: int
    axial_force: float     # Newtons (+ tension, - compression)
    stress: float          # Pa
    stress_ratio: float    # |stress| / allowable_stress
    status: MemberStatus = MemberStatus.OK
    allowable_stress: float = 0.0  # Pa
    euler_buckling_load: float = 0.0  # N (for compression members)

    @property
    def stress_mpa(self) -> float:
        return self.stress / 1e6

    @property
    def axial_force_kn(self) -> float:
        return self.axial_force / 1e3


@dataclass
class NodeResult:
    node_id: int
    dx: float = 0.0  # meters
    dy: float = 0.0  # meters
    dz: float = 0.0  # meters

    @property
    def total_displacement(self) -> float:
        return math.sqrt(self.dx**2 + self.dy**2 + self.dz**2)

    @property
    def total_displacement_mm(self) -> float:
        return self.total_displacement * 1000


@dataclass
class Reaction:
    node_id: int
    rx: float = 0.0  # Newtons
    ry: float = 0.0  # Newtons
    rz: float = 0.0  # Newtons


@dataclass
class FailureInfo:
    failure_type: FailureType
    member_id: Optional[int] = None
    node_id: Optional[int] = None
    actual_value: float = 0.0
    limit_value: float = 0.0
    ratio: float = 0.0
    description: str = ""


@dataclass
class FailureDiagnosis:
    passed: bool
    failures: list[FailureInfo] = field(default_factory=list)
    max_stress_ratio: float = 0.0
    max_displacement_mm: float = 0.0
    failed_member_count: int = 0
    failed_node_count: int = 0


@dataclass
class EquilibriumCheck:
    """
    Global equilibrium residuals: for a correctly solved system both

        Σ(applied forces)  + Σ(reactions)         = 0   (3 force equations)
        Σ(applied moments) + Σ(reaction moments)  = 0   (3 moment equations)

    must hold on every axis. Moments are taken about the global origin;
    since every force is a point load at a node, each contributes r × F.

    This is an independent check on the solve — the reactions come from
    R = K·u − F, so a non-zero residual means the linear system was not
    actually satisfied (bad conditioning, wrong BCs, an assembly bug), not
    merely that the structure is overstressed.

    Force and moment residuals are normalized separately because they have
    different units (N vs N·m) and therefore different natural scales.
    """
    residual_fx: float = 0.0
    residual_fy: float = 0.0
    residual_fz: float = 0.0
    residual_mx: float = 0.0
    residual_my: float = 0.0
    residual_mz: float = 0.0
    load_magnitude: float = 0.0        # reference force magnitude (N)
    moment_magnitude: float = 0.0      # reference moment magnitude (N·m)
    relative_residual: float = 0.0     # max|force residual| / load_magnitude
    relative_moment_residual: float = 0.0
    tolerance: float = 1e-6
    passed: bool = True                # True only if BOTH force and moment pass

    @property
    def max_residual(self) -> float:
        return max(abs(self.residual_fx), abs(self.residual_fy), abs(self.residual_fz))

    @property
    def max_moment_residual(self) -> float:
        return max(abs(self.residual_mx), abs(self.residual_my), abs(self.residual_mz))


@dataclass
class ProvenanceInput:
    """One named input to a derived value, with its unit."""
    label: str
    value: float
    units: str


@dataclass
class ResultProvenance:
    """
    Where a headline number came from, and how it was computed.

    Exists so no displayed figure is unattributable: every metric carries
    the element it came from, the equation that produced it, and the actual
    input values used — all read back from solver state, never re-derived
    for display.
    """
    metric: str            # e.g. "max_stress"
    label: str             # human-readable, e.g. "Maximum Stress"
    value: float
    units: str
    source_type: str       # "member" | "node" | "reaction" | "system"
    source_id: Optional[int] = None
    source_detail: str = ""    # e.g. "Member 27" or "Node 18 → UY"
    equation: str = ""         # e.g. "sigma = N / A"
    inputs: list[ProvenanceInput] = field(default_factory=list)
    note: str = ""


@dataclass
class VerificationChecks:
    """
    Phase 19: an explicit breakdown of every computational check, so
    "verified" is never a single opaque badge.

    These are COMPUTATIONAL checks only — they do not constitute
    professional engineering certification.
    """
    solver: bool = False           # linear system solved, finite results
    geometry: bool = False         # valid nodes/members, no zero-length members
    boundary_conditions: bool = False  # sufficient restraint, non-singular K
    equilibrium: bool = False      # global force balance within tolerance
    stress: bool = False           # all members within allowable stress
    displacement: bool = False     # all nodes within displacement limit

    @property
    def all_passed(self) -> bool:
        return all([
            self.solver, self.geometry, self.boundary_conditions,
            self.equilibrium, self.stress, self.displacement,
        ])


@dataclass
class AnalysisResults:
    member_results: list[MemberResult]
    node_results: list[NodeResult]
    reactions: list[Reaction]
    diagnosis: FailureDiagnosis
    solve_time_ms: float = 0.0
    total_weight_kg: float = 0.0
    equilibrium: EquilibriumCheck = field(default_factory=EquilibriumCheck)
    checks: VerificationChecks = field(default_factory=VerificationChecks)
    dof_count: int = 0             # 3 × number of nodes
    is_spatial: bool = False       # True when the geometry is genuinely 3D (any z ≠ 0)
    # Load accounting. `load_summary` names every case considered, whether
    # it was supported, and the resultant it contributed — so no force can
    # enter the solve without appearing here.
    load_summary: "LoadSummary | None" = None
    # Numerical health of the solve: Maxwell count, rigid-body mode count
    # and condition number. Typed loosely to avoid a models -> core import.
    stability: object = None


@dataclass
class LoadCaseSummary:
    """One load case as it was actually treated in this analysis."""
    case_type: str
    name: str
    supported: bool
    active: bool
    factor: float
    resultant_fx: float
    resultant_fy: float
    resultant_fz: float
    n_loads: int
    formulation: str = ""
    assumptions: list[str] = field(default_factory=list)
    limitations: str = ""
    unsupported_reason: str = ""


@dataclass
class SelfWeightSummary:
    """Displayable self-weight breakdown (Priority 1)."""
    included: bool
    gravity: float
    total_mass_kg: float
    total_weight_n: float
    applied_weight_n: float
    n_loaded_nodes: int
    unknown_material_members: list[int] = field(default_factory=list)

    @property
    def consistent(self) -> bool:
        """Reported mass*g must equal what was actually applied."""
        return abs(self.total_weight_n - self.applied_weight_n) <= 1e-6 * max(
            1.0, abs(self.total_weight_n)
        )


@dataclass
class LoadSummary:
    combination_name: str
    combination_description: str
    combination_source: str
    cases: list[LoadCaseSummary] = field(default_factory=list)
    self_weight: Optional[SelfWeightSummary] = None
    total_applied_fx: float = 0.0
    total_applied_fy: float = 0.0
    total_applied_fz: float = 0.0


@dataclass
class RepairAction:
    iteration: int
    strategy: RepairStrategy
    target_description: str
    parameter_changed: str
    old_value: float
    new_value: float
    rationale: str


@dataclass
class IterationResult:
    iteration_number: int
    structure: Structure
    results: AnalysisResults
    repair_action: Optional[RepairAction] = None


# ─────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────

@dataclass
class Project:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Untitled"
    description: str = ""
    spec: Optional[EngineeringSpec] = None
    iterations: list[IterationResult] = field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    created_at: str = ""
