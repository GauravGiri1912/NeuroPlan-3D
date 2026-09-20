"""Failure Experiment Engine — domain model.

One perturbation applied to a copy of a baseline Structure, re-solved
through the real production solver. See engine.py for execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...models.structure import AnalysisResults


class PerturbationType(str, Enum):
    LOAD_SCALE = "load_scale"                  # increase/decrease a load's magnitude
    LOAD_REVERSE = "load_reverse"               # negate a load's direction
    MEMBER_AREA_SCALE = "member_area_scale"     # scale one member's cross-sectional area
    YOUNGS_MODULUS_SCALE = "youngs_modulus_scale"  # scale one material's E
    GEOMETRY_OFFSET = "geometry_offset"         # move one node by (dx, dy, dz)
    SUPPORT_REMOVE = "support_remove"           # remove all supports at a node
    MEMBER_REMOVE = "member_remove"             # remove one member


@dataclass
class Perturbation:
    """Exactly one deterministic change to apply. Only the fields the
    chosen `type` needs are used; others are ignored."""
    type: PerturbationType
    load_index: int | None = None
    member_id: int | None = None
    material_key: str | None = None
    node_id: int | None = None
    support_node_id: int | None = None
    scale_factor: float | None = None
    offset: tuple[float, float, float] | None = None
    description: str = ""


def _max_stress_mpa(results: AnalysisResults) -> float:
    return max((abs(m.stress) for m in results.member_results), default=0.0) / 1e6


def _critical_member(results: AnalysisResults) -> int | None:
    worst, worst_id = -1.0, None
    for member in results.member_results:
        if abs(member.stress) > worst:
            worst, worst_id = abs(member.stress), member.member_id
    return worst_id


def _percent_change(baseline: float, perturbed: float) -> float | None:
    """None when the baseline value is ~0 — percentage change is not
    mathematically meaningful there (division by zero)."""
    if abs(baseline) <= 1e-12:
        return None
    return (perturbed - baseline) / baseline * 100.0


# Structural status of the PERTURBED case:
#   "stable"                 — solved, and the diagnosis passed all checks
#   "solved_but_failed_checks" — solved, but overstressed / over-displaced
#   "unstable"                — solver could not produce a solution
#                               (mechanism/singular system) — see perturbed_error
#                               for the specific engineering reason.
STATUS_STABLE = "stable"
STATUS_FAILED_CHECKS = "solved_but_failed_checks"
STATUS_UNSTABLE = "unstable"


def case_structural_status(results: AnalysisResults) -> str:
    """STATUS_STABLE / STATUS_FAILED_CHECKS / STATUS_UNSTABLE for one
    solved AnalysisResults, using the same mechanism-detection rule as
    ExperimentResult.build() (stability.n_zero_modes is authoritative
    over diagnosis.passed). Shared so callers (e.g. Structural Autopsy)
    never re-derive this logic."""
    n_zero_modes = results.stability.n_zero_modes if results.stability else None
    if n_zero_modes:
        return STATUS_UNSTABLE
    return STATUS_STABLE if results.diagnosis.passed else STATUS_FAILED_CHECKS


@dataclass
class ExperimentResult:
    perturbation: Perturbation
    baseline_results: AnalysisResults
    perturbed_results: AnalysisResults | None
    perturbed_error: str | None
    displacement_change_mm: float | None
    stress_change_mpa: float | None
    displacement_percent_change: float | None
    stress_percent_change: float | None
    critical_member_before: int | None
    critical_member_after: int | None
    critical_member_changed: bool
    baseline_verified: bool
    perturbed_verified: bool | None
    verification_status_changed: bool
    structural_status: str

    @property
    def removed_member_id(self) -> int | None:
        if self.perturbation.type is PerturbationType.MEMBER_REMOVE:
            return self.perturbation.member_id
        return None

    @property
    def baseline_max_displacement_mm(self) -> float:
        return self.baseline_results.diagnosis.max_displacement_mm

    @property
    def perturbed_max_displacement_mm(self) -> float | None:
        return self.perturbed_results.diagnosis.max_displacement_mm if self.perturbed_results else None

    @property
    def baseline_max_stress_mpa(self) -> float:
        return _max_stress_mpa(self.baseline_results)

    @property
    def perturbed_max_stress_mpa(self) -> float | None:
        return _max_stress_mpa(self.perturbed_results) if self.perturbed_results else None

    @classmethod
    def build(
        cls,
        perturbation: Perturbation,
        baseline_results: AnalysisResults,
        perturbed_results: AnalysisResults | None,
        perturbed_error: str | None,
    ) -> "ExperimentResult":
        critical_before = _critical_member(baseline_results)
        baseline_verified = baseline_results.diagnosis.passed

        # The solver's linear (Cholesky) mechanism check can miss a
        # mechanism when the applied load happens not to excite the
        # singular mode (a near-zero, not exactly-zero, pivot in floating
        # point) — solve() then succeeds numerically even though the
        # structure has a genuine zero-energy mode. The independent
        # eigen-decomposition already computed on every successful solve
        # (AnalysisResults.stability.n_zero_modes) catches this and is
        # authoritative over diagnosis.passed for structural stability.
        # Such a case is treated exactly like a solver failure: no
        # fabricated displacement/stress numbers from a result that
        # happened to converge only because the load missed the mechanism.
        if perturbed_results is not None:
            n_zero_modes = perturbed_results.stability.n_zero_modes if perturbed_results.stability else None
            if n_zero_modes:
                perturbed_error = (
                    f"The structure solved numerically, but an independent stability "
                    f"check found {n_zero_modes} zero-energy mode(s) — the applied load "
                    f"did not happen to excite the mechanism, but the structure is not "
                    f"stable. Treating this as an unstable result rather than reporting "
                    f"the coincidental numeric solution."
                )
                perturbed_results = None

        if perturbed_results is None:
            return cls(
                perturbation=perturbation,
                baseline_results=baseline_results,
                perturbed_results=None,
                perturbed_error=perturbed_error,
                displacement_change_mm=None,
                stress_change_mpa=None,
                displacement_percent_change=None,
                stress_percent_change=None,
                critical_member_before=critical_before,
                critical_member_after=None,
                critical_member_changed=True,
                baseline_verified=baseline_verified,
                perturbed_verified=None,
                verification_status_changed=True,
                structural_status=STATUS_UNSTABLE,
            )

        critical_after = _critical_member(perturbed_results)
        perturbed_verified = perturbed_results.diagnosis.passed
        base_disp = baseline_results.diagnosis.max_displacement_mm
        pert_disp = perturbed_results.diagnosis.max_displacement_mm
        base_stress = _max_stress_mpa(baseline_results)
        pert_stress = _max_stress_mpa(perturbed_results)

        return cls(
            perturbation=perturbation,
            baseline_results=baseline_results,
            perturbed_results=perturbed_results,
            perturbed_error=None,
            displacement_change_mm=pert_disp - base_disp,
            stress_change_mpa=pert_stress - base_stress,
            displacement_percent_change=_percent_change(base_disp, pert_disp),
            stress_percent_change=_percent_change(base_stress, pert_stress),
            critical_member_before=critical_before,
            critical_member_after=critical_after,
            critical_member_changed=critical_before != critical_after,
            baseline_verified=baseline_verified,
            perturbed_verified=perturbed_verified,
            verification_status_changed=baseline_verified != perturbed_verified,
            structural_status=case_structural_status(perturbed_results),
        )
