"""Structural Autopsy — evidence-only diagnosis of an ExperimentResult.

NOT an AI/LLM explanation system. Every step cites only values already
computed by the real solver (via ExperimentResult); nothing is invented,
estimated, or claimed causal beyond what the numbers directly show.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import ExperimentResult, case_structural_status, _percent_change
from ...models.structure import AnalysisResults

CAUSE_NOT_DETERMINED = "CAUSE_NOT_DETERMINED"

_ZERO_THRESHOLD = 1e-9


class DiagnosisStepType(str, Enum):
    STRUCTURAL_INSTABILITY = "structural_instability"
    FORCE_REDISTRIBUTION = "force_redistribution"
    CRITICAL_MEMBER_CHANGED = "critical_member_changed"
    STRESS_INCREASE = "stress_increase"
    STRESS_DECREASE = "stress_decrease"
    STRESS_UNCHANGED = "stress_unchanged"
    DISPLACEMENT_INCREASE = "displacement_increase"
    DISPLACEMENT_DECREASE = "displacement_decrease"
    DISPLACEMENT_UNCHANGED = "displacement_unchanged"
    FAILED_CHECK = "failed_check"


@dataclass
class DiagnosisStep:
    type: DiagnosisStepType
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuralAutopsy:
    removed_member_id: int | None
    baseline_status: str
    perturbed_status: str
    steps: list[DiagnosisStep] = field(default_factory=list)
    cause_attribution: str = CAUSE_NOT_DETERMINED
    limitation_note: str = (
        "This diagnosis is an ordered list of computed facts, not a causal "
        "explanation. It does not claim that any one fact caused another — "
        "only the deterministic solver's own numbers are reported."
    )


def _force_redistribution_step(
    baseline: AnalysisResults, perturbed: AnalysisResults
) -> DiagnosisStep | None:
    """Largest per-member axial-force change among members present in
    BOTH cases (the removed member has no perturbed value to compare)."""
    base_forces = {m.member_id: m.axial_force for m in baseline.member_results}
    pert_forces = {m.member_id: m.axial_force for m in perturbed.member_results}
    common = set(base_forces) & set(pert_forces)
    if not common:
        return None

    worst_id, worst_delta = None, 0.0
    for member_id in common:
        delta = pert_forces[member_id] - base_forces[member_id]
        if abs(delta) > abs(worst_delta):
            worst_id, worst_delta = member_id, delta

    if worst_id is None or abs(worst_delta) <= _ZERO_THRESHOLD:
        return None

    return DiagnosisStep(
        type=DiagnosisStepType.FORCE_REDISTRIBUTION,
        summary=f"Member force redistribution detected (largest change: member {worst_id})",
        evidence={
            "member_id": worst_id,
            "baseline_force_n": base_forces[worst_id],
            "perturbed_force_n": pert_forces[worst_id],
            "force_change_n": worst_delta,
            "force_percent_change": _percent_change(base_forces[worst_id], pert_forces[worst_id]),
        },
    )


def _magnitude_step(
    increase_type: DiagnosisStepType, decrease_type: DiagnosisStepType, unchanged_type: DiagnosisStepType,
    label: str, baseline_value: float, perturbed_value: float, delta: float, percent: float | None,
    evidence_key_prefix: str,
) -> DiagnosisStep:
    if delta > _ZERO_THRESHOLD:
        step_type, verb = increase_type, "increased"
    elif delta < -_ZERO_THRESHOLD:
        step_type, verb = decrease_type, "decreased"
    else:
        step_type, verb = unchanged_type, "did not change"

    summary = f"{label} {verb}"
    if percent is not None and step_type is not unchanged_type:
        summary += f" by {abs(percent):.2f}%"

    return DiagnosisStep(
        type=step_type,
        summary=summary,
        evidence={
            f"baseline_{evidence_key_prefix}": baseline_value,
            f"perturbed_{evidence_key_prefix}": perturbed_value,
            f"{evidence_key_prefix}_change": delta,
            f"{evidence_key_prefix}_percent_change": percent,
        },
    )


def diagnose(result: ExperimentResult) -> StructuralAutopsy:
    """Derive a Structural Autopsy from an already-computed ExperimentResult.

    Works for any perturbation type that produces an ExperimentResult;
    `removed_member_id` is populated only for MEMBER_REMOVE (see
    ExperimentResult.removed_member_id).
    """
    baseline_status = case_structural_status(result.baseline_results)

    if result.perturbed_results is None:
        return StructuralAutopsy(
            removed_member_id=result.removed_member_id,
            baseline_status=baseline_status,
            perturbed_status=result.structural_status,
            steps=[DiagnosisStep(
                type=DiagnosisStepType.STRUCTURAL_INSTABILITY,
                summary="Structure became unstable (mechanism) after the perturbation",
                evidence={"solver_error": result.perturbed_error},
            )],
            cause_attribution=CAUSE_NOT_DETERMINED,
        )

    steps: list[DiagnosisStep] = []

    force_step = _force_redistribution_step(result.baseline_results, result.perturbed_results)
    if force_step is not None:
        steps.append(force_step)

    if (result.critical_member_changed
            and result.critical_member_before is not None
            and result.critical_member_after is not None):
        steps.append(DiagnosisStep(
            type=DiagnosisStepType.CRITICAL_MEMBER_CHANGED,
            summary=f"Critical member changed from {result.critical_member_before} "
                    f"to {result.critical_member_after}",
            evidence={
                "previous_critical_member": result.critical_member_before,
                "new_critical_member": result.critical_member_after,
            },
        ))

    if result.stress_change_mpa is not None:
        steps.append(_magnitude_step(
            DiagnosisStepType.STRESS_INCREASE, DiagnosisStepType.STRESS_DECREASE,
            DiagnosisStepType.STRESS_UNCHANGED, "Maximum stress",
            result.baseline_max_stress_mpa, result.perturbed_max_stress_mpa,
            result.stress_change_mpa, result.stress_percent_change, "max_stress_mpa",
        ))

    if result.displacement_change_mm is not None:
        steps.append(_magnitude_step(
            DiagnosisStepType.DISPLACEMENT_INCREASE, DiagnosisStepType.DISPLACEMENT_DECREASE,
            DiagnosisStepType.DISPLACEMENT_UNCHANGED, "Maximum displacement",
            result.baseline_max_displacement_mm, result.perturbed_max_displacement_mm,
            result.displacement_change_mm, result.displacement_percent_change, "max_displacement_mm",
        ))

    if result.structural_status == "solved_but_failed_checks":
        failures = result.perturbed_results.diagnosis.failures
        if failures:
            worst = failures[0]   # validator.py sorts by ratio (severity) descending
            steps.append(DiagnosisStep(
                type=DiagnosisStepType.FAILED_CHECK,
                summary=f"Failure criterion triggered: {worst.failure_type.value}",
                evidence={
                    "failure_type": worst.failure_type.value,
                    "member_id": worst.member_id,
                    "node_id": worst.node_id,
                    "actual_value": worst.actual_value,
                    "limit_value": worst.limit_value,
                    "ratio": worst.ratio,
                    "description": worst.description,
                    "total_failed_checks": len(failures),
                },
            ))

    return StructuralAutopsy(
        removed_member_id=result.removed_member_id,
        baseline_status=baseline_status,
        perturbed_status=result.structural_status,
        steps=steps,
        cause_attribution=CAUSE_NOT_DETERMINED,
    )
