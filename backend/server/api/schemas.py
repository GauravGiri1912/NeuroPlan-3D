"""
NeuroPlan-3D — Pydantic API Schemas

Request/response models for the REST API.
Serializable versions of the internal dataclass models.
"""
from pydantic import BaseModel, Field
from typing import Optional


# ─────────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────────

class ParseRequest(BaseModel):
    raw_input: str = Field(..., description="Natural language engineering requirement")


class SpecRequest(BaseModel):
    structure_type: str = "pratt"
    span: float = 20.0
    height: float = 3.33
    width: float = 0.0            # z-direction; required (> 0) for spatial types
    num_panels: int = 6
    primary_load: float = 50000.0  # vertical (−y) magnitude
    lateral_load_x: float = 0.0    # longitudinal (+x)
    lateral_load_z: float = 0.0    # transverse (+z), e.g. wind
    load_description: str = "center point load"
    material_key: str = "A36"
    section_key: str = "CHS_114x6"
    safety_factor: float = 1.67
    max_displacement_ratio: float = 300.0
    description: str = ""


class PipelineRequest(BaseModel):
    raw_input: str = Field("", description="Natural language input (optional if spec provided)")
    spec: Optional[SpecRequest] = Field(None, description="Pre-built spec (skips parsing)")


# ─────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────

class NodeResponse(BaseModel):
    id: int
    x: float
    y: float
    z: float


class SectionResponse(BaseModel):
    outer_diameter: float
    wall_thickness: float
    area: float
    moment_of_inertia: float


class MemberResponse(BaseModel):
    id: int
    node_i: int
    node_j: int
    material_key: str
    section: SectionResponse


class SupportResponse(BaseModel):
    node_id: int
    support_type: str
    dx: bool
    dy: bool
    dz: bool


class LoadResponse(BaseModel):
    node_id: int
    fx: float
    fy: float
    fz: float


class StructureResponse(BaseModel):
    nodes: list[NodeResponse]
    members: list[MemberResponse]
    supports: list[SupportResponse]
    loads: list[LoadResponse]


class MemberResultResponse(BaseModel):
    member_id: int
    axial_force: float
    axial_force_kn: float
    stress: float
    stress_mpa: float
    stress_ratio: float
    allowable_stress_mpa: float
    status: str
    euler_buckling_load: float


class NodeResultResponse(BaseModel):
    node_id: int
    dx: float
    dy: float
    dz: float
    total_displacement_mm: float


class ReactionResponse(BaseModel):
    node_id: int
    rx: float
    ry: float
    rz: float


class FailureInfoResponse(BaseModel):
    failure_type: str
    member_id: Optional[int] = None
    node_id: Optional[int] = None
    actual_value: float
    limit_value: float
    ratio: float
    description: str


class DiagnosisResponse(BaseModel):
    passed: bool
    failures: list[FailureInfoResponse]
    max_stress_ratio: float
    max_displacement_mm: float
    failed_member_count: int
    failed_node_count: int


class RepairActionResponse(BaseModel):
    iteration: int
    strategy: str
    target_description: str
    parameter_changed: str
    old_value: float
    new_value: float
    rationale: str


class EquilibriumResponse(BaseModel):
    residual_fx: float
    residual_fy: float
    residual_fz: float
    residual_mx: float
    residual_my: float
    residual_mz: float
    max_residual: float
    max_moment_residual: float
    load_magnitude: float
    moment_magnitude: float
    relative_residual: float
    relative_moment_residual: float
    tolerance: float
    passed: bool


class ProvenanceInputResponse(BaseModel):
    label: str
    value: float
    units: str


class ProvenanceResponse(BaseModel):
    metric: str
    label: str
    value: float
    units: str
    source_type: str
    source_id: Optional[int] = None
    source_detail: str
    equation: str
    inputs: list[ProvenanceInputResponse]
    note: str


class VerificationItemResponse(BaseModel):
    key: str
    category: str
    label: str
    status: str                 # pass | fail | not_available | info
    actual_display: str
    limit_display: str
    units: str
    source: str
    detail: str
    actual_value: Optional[float] = None
    limit_value: Optional[float] = None


class BenchmarkResponse(BaseModel):
    case: str
    quantity: str
    neuroplan_value: float
    reference_value: float
    units: str
    absolute_difference: float
    relative_difference: float
    tolerance_relative: float
    reference_source: str
    derivation: str
    status: str


class AssumptionResponse(BaseModel):
    topic: str
    modeled: bool
    description: str
    implication: str


class SimulationRecordResponse(BaseModel):
    simulation_id: str
    timestamp_utc: str
    software_version: str
    solver_method: str
    solver_backend: str
    node_count: int
    member_count: int
    dof_per_node: int
    total_dof: int
    support_count: int
    load_count: int
    material_keys: list[str]
    section_keys: list[str]
    iteration_count: int
    warnings: list[str]


class LoadPathMemberResponse(BaseModel):
    member_id: int
    other_node_id: int
    axial_force: float
    stress: float
    lx: float
    ly: float
    lz: float
    fx_on_joint: float
    fy_on_joint: float
    fz_on_joint: float


class LoadPathResponse(BaseModel):
    node_id: int
    node_x: float
    node_y: float
    node_z: float
    applied_fx: float
    applied_fy: float
    applied_fz: float
    members: list[LoadPathMemberResponse]
    joint_residual_fx: float
    joint_residual_fy: float
    joint_residual_fz: float
    joint_relative_residual: float
    joint_equilibrium_passed: bool


class EvidenceResponse(BaseModel):
    """The complete traceability package for one pipeline run."""
    provenance: list[ProvenanceResponse]
    verification: list[VerificationItemResponse]
    benchmarks: list[BenchmarkResponse]
    assumptions: list[AssumptionResponse]
    load_paths: list[LoadPathResponse]
    record: SimulationRecordResponse
    computation_verified: bool
    real_world_validated: bool


class VerificationChecksResponse(BaseModel):
    solver: bool
    geometry: bool
    boundary_conditions: bool
    equilibrium: bool
    stress: bool
    displacement: bool
    all_passed: bool


class AnalysisResultsResponse(BaseModel):
    member_results: list[MemberResultResponse]
    node_results: list[NodeResultResponse]
    reactions: list[ReactionResponse]
    diagnosis: DiagnosisResponse
    solve_time_ms: float
    total_weight_kg: float
    equilibrium: EquilibriumResponse
    checks: VerificationChecksResponse
    dof_count: int
    is_spatial: bool


class IterationResponse(BaseModel):
    iteration_number: int
    structure: StructureResponse
    results: AnalysisResultsResponse
    repair_action: Optional[RepairActionResponse] = None


class SpecResponse(BaseModel):
    structure_type: str
    is_spatial: bool
    span: float
    height: float
    width: float
    num_panels: int
    primary_load: float
    lateral_load_x: float
    lateral_load_z: float
    load_description: str
    material_key: str
    section_key: str
    safety_factor: float
    max_displacement_ratio: float
    description: str
    raw_input: str
    defaults_applied: list[str] = []
    # How the planar/spatial choice was reached. "unspecified"/"conflicting"
    # mean it is an interpretation, not a stated requirement.
    dimensionality_intent: str = "unspecified"


class MaterialResponse(BaseModel):
    key: str
    name: str
    E_gpa: float
    yield_stress_mpa: float
    density: float


class AIOpinionResponse(BaseModel):
    verdict: str          # "likely_safe" | "likely_unsafe" | "uncertain"
    confidence: str        # "low" | "medium" | "high"
    reasoning: str
    source: str             # "gemini" | "heuristic_fallback"
    agrees_with_physics: bool


class PipelineResultResponse(BaseModel):
    spec: SpecResponse
    iterations: list[IterationResponse]
    verification_status: str
    summary: dict
    ai_opinion: Optional[AIOpinionResponse] = None
    evidence: Optional[EvidenceResponse] = None
