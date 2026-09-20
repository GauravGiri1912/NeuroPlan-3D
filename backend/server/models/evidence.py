"""
NeuroPlan-3D — Engineering Evidence Models

Data structures for the traceability layer: verification evidence,
assumptions, benchmark comparisons and the simulation record.

Design rule for everything in this module: a status is never carried
without the evidence that produced it. `VerificationItem` therefore has no
bare boolean — it holds the actual value, the limit it was compared
against, the units, and where the number came from. A check that cannot be
performed reports NOT_AVAILABLE rather than silently passing.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_AVAILABLE = "not_available"   # capability does not exist — never a silent pass
    INFO = "info"                      # reported for transparency, not a pass/fail gate


class EvidenceCategory(str, Enum):
    MODEL_DEFINITION = "model_definition"
    SOLVER = "solver"
    EQUILIBRIUM = "equilibrium"
    NUMERICAL = "numerical"
    LIMITS = "limits"
    BENCHMARK = "benchmark"
    REAL_WORLD = "real_world"


@dataclass
class VerificationItem:
    """
    One check, with the evidence that produced its status.

    `actual_display` / `limit_display` are preformatted with units so the UI
    never has to guess at formatting or, worse, recompute a value for
    display and risk showing something the solver never produced.
    """
    key: str
    category: EvidenceCategory
    label: str
    status: CheckStatus
    actual_display: str = ""
    limit_display: str = ""
    units: str = ""
    source: str = ""          # e.g. "solver → equilibrium → ΣFy"
    detail: str = ""          # human explanation of what this check means
    actual_value: Optional[float] = None
    limit_value: Optional[float] = None


@dataclass
class BenchmarkComparison:
    """
    One independent reference case: NeuroPlan's result against a value
    derived by hand, outside this codebase.

    `reference_source` must name where the reference number comes from. A
    benchmark whose "reference" is just this solver's own earlier output is
    not a benchmark, and must not be listed here.
    """
    case: str
    quantity: str
    neuroplan_value: float
    reference_value: float
    units: str
    tolerance_relative: float
    reference_source: str
    derivation: str = ""

    @property
    def absolute_difference(self) -> float:
        return abs(self.neuroplan_value - self.reference_value)

    @property
    def relative_difference(self) -> float:
        denom = abs(self.reference_value)
        if denom < 1e-12:
            return self.absolute_difference
        return self.absolute_difference / denom

    @property
    def status(self) -> CheckStatus:
        return CheckStatus.PASS if self.relative_difference <= self.tolerance_relative else CheckStatus.FAIL


@dataclass
class ModelingAssumption:
    """Something the solver does (modeled=True) or does not do (modeled=False)."""
    topic: str
    modeled: bool
    description: str
    implication: str = ""      # what this means for interpreting results


@dataclass
class LoadPathMember:
    """One member carrying load away from a joint, with its contribution."""
    member_id: int
    other_node_id: int
    axial_force: float          # N, + tension / − compression
    stress: float               # Pa
    direction_cosines: tuple[float, float, float]  # pointing AWAY from the joint
    # Force this member applies TO the joint (tension pulls the joint toward
    # the far end): F_on_joint = N · c
    fx_on_joint: float
    fy_on_joint: float
    fz_on_joint: float


@dataclass
class LoadPath:
    """
    The traceable path of one applied load: what was applied, which members
    carry it away from the joint, and where it ends up as reactions.

    The joint-equilibrium residual is the verifiable link in that chain —
    at the loaded node, the applied force plus every connected member's
    force contribution must sum to zero. If that holds, the load really is
    being carried by those members and not by an accounting error.
    """
    node_id: int
    node_x: float
    node_y: float
    node_z: float
    applied_fx: float
    applied_fy: float
    applied_fz: float
    members: list[LoadPathMember] = field(default_factory=list)
    # Joint equilibrium: applied + Σ(member force on joint) ≈ 0
    joint_residual_fx: float = 0.0
    joint_residual_fy: float = 0.0
    joint_residual_fz: float = 0.0
    joint_relative_residual: float = 0.0
    joint_equilibrium_passed: bool = True


@dataclass
class SimulationRecord:
    """
    A traceable record of one pipeline run — enough to audit and reproduce it.
    """
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
    material_keys: list[str] = field(default_factory=list)
    section_keys: list[str] = field(default_factory=list)
    iteration_count: int = 1
    warnings: list[str] = field(default_factory=list)
