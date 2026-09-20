"""
NeuroPlan-3D — Independent Validation Workflow

Implements the clean separation between:

  CALIBRATED / REFERENCE COMPARISON
and
  INDEPENDENT VALIDATION

The key scientific rule: a comparison whose model parameters (including
sensor mapping) were selected using the measured results is CALIBRATION,
not validation. Independent validation requires that the validation
measurements were NOT consulted during any parameter-selection step.

For the steel-truss dataset:
- South-side sensors (1-7) were used in the mapping calibration scan
- North-side sensors (8-14) use the SAME mapping derived from that scan
- Only mid-span (node 6, sensor 4/11) is genuinely layout-invariant

The honest result: INDEPENDENT VALIDATION NOT ESTABLISHED, with the
mid-span point flagged as the one genuinely independent comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import (
    ComparisonResult, ComparisonSummary, ExperimentalCase,
    ModelMapping, ModelParameter, IndependenceAssessment,
)


class IndependentValidationStatus(str, Enum):
    """
    Status of the independent validation workflow.

    These are deliberately distinct from ValidationState — they describe
    the WORKFLOW state, not a single comparison's state.
    """
    INDEPENDENT_PASSED = "independent_passed"
    COMPLETED_REVIEW_REQUIRED = "completed_review_required"
    CALIBRATED_REFERENCE = "calibrated_reference"
    INSUFFICIENT_DATA = "insufficient_data"
    BLOCKED_DATA_LEAKAGE = "blocked_data_leakage"
    NOT_RUN = "not_run"


STATUS_LABELS = {
    IndependentValidationStatus.INDEPENDENT_PASSED: "INDEPENDENT VALIDATION PASSED",
    IndependentValidationStatus.COMPLETED_REVIEW_REQUIRED: "INDEPENDENT VALIDATION COMPLETED — REVIEW REQUIRED",
    IndependentValidationStatus.CALIBRATED_REFERENCE: "CALIBRATED / REFERENCE COMPARED",
    IndependentValidationStatus.INSUFFICIENT_DATA: "INSUFFICIENT DATA FOR INDEPENDENT VALIDATION",
    IndependentValidationStatus.BLOCKED_DATA_LEAKAGE: "VALIDATION BLOCKED — DATA LEAKAGE",
    IndependentValidationStatus.NOT_RUN: "VALIDATION NOT RUN",
}


@dataclass
class DataLeakageCheck:
    """Explicit record of whether validation data influenced calibration."""
    passed: bool
    calibration_sensor_ids: list[str]
    validation_sensor_ids: list[str]
    overlapping_sensor_ids: list[str]
    explanation: str


@dataclass
class IndependentValidationResult:
    """
    The complete result of an independent validation attempt.

    Every field is explicit — there is no way to display a result without
    showing which data was used for calibration vs validation.
    """
    status: IndependentValidationStatus
    status_label: str
    # Calibration side
    calibration_case_id: str
    calibration_description: str
    calibration_sensor_ids: list[str]
    calibration_comparisons: list[ComparisonResult]
    calibration_summary: ComparisonSummary | None
    calibration_independence: IndependenceAssessment
    # Validation side
    validation_case_id: str
    validation_description: str
    validation_sensor_ids: list[str]
    validation_comparisons: list[ComparisonResult]
    validation_summary: ComparisonSummary | None
    validation_independence: IndependenceAssessment
    # Mid-span (the one genuinely independent point)
    midspan_comparison: ComparisonResult | None
    midspan_is_independent: bool
    midspan_note: str
    # Leakage
    leakage_check: DataLeakageCheck
    # Model configuration
    solver_method: str
    model_parameters: list[ModelParameter]
    calibration_parameters_used: list[str]
    validation_data_used_during_calibration: bool
    # Limitations
    limitations: list[str]
    scientific_explanation: str
    error: str | None = None


def detect_data_leakage(
    calibration_sensor_ids: list[str],
    validation_sensor_ids: list[str],
) -> DataLeakageCheck:
    """
    Check whether any validation sensor was used during calibration.

    Any overlap means the validation data influenced calibration — the
    validation result is blocked.
    """
    cal_set = set(calibration_sensor_ids)
    val_set = set(validation_sensor_ids)
    overlap = sorted(cal_set & val_set)

    if overlap:
        return DataLeakageCheck(
            passed=False,
            calibration_sensor_ids=calibration_sensor_ids,
            validation_sensor_ids=validation_sensor_ids,
            overlapping_sensor_ids=overlap,
            explanation=(
                f"VALIDATION DATA USED FOR CALIBRATION. "
                f"Sensors {overlap} appear in both the calibration and "
                f"validation sets. The validation result is invalid."
            ),
        )

    return DataLeakageCheck(
        passed=True,
        calibration_sensor_ids=calibration_sensor_ids,
        validation_sensor_ids=validation_sensor_ids,
        overlapping_sensor_ids=[],
        explanation=(
            f"No overlap: {len(calibration_sensor_ids)} calibration sensors "
            f"and {len(validation_sensor_ids)} validation sensors are "
            f"disjoint. No validation data was used during calibration."
        ),
    )


MIDSPAN_INDEPENDENT_NOTE = (
    "Mid-span (node 6) is the same node under all 10 candidate sensor "
    "layouts. The sensor-4 (South) / sensor-11 (North) mapping to this "
    "node is therefore genuinely independent of the mapping selection "
    "performed using the South-side deflection profile. However, n=1 is "
    "insufficient for statistical validation — this is a single-point "
    "reference comparison, not a validated model."
)

INSUFFICIENT_DATA_EXPLANATION = (
    "Available experimental data is currently used for calibrated/reference "
    "comparison. The sensor-to-node mapping was selected by scoring 10 "
    "candidate layouts against the South-side (sensors 1-7) measured "
    "deflection profile. The same mapping is applied to the North-side "
    "(sensors 8-14), so the North-side agreement is also influenced by "
    "the calibration — it is NOT an unseen, independently-mapped test.\n\n"
    "Only the mid-span sensor (sensor 4/11 → node 6) is genuinely "
    "independent of the mapping choice, because node 6 is the peak of "
    "the symmetric deflection curve and maps to the same node under all "
    "10 candidate layouts. However, a single comparison point does not "
    "constitute statistical validation.\n\n"
    "An unseen experimental case — with its own independently-documented "
    "sensor positions, or a different test specimen entirely — is required "
    "for independent validation. This is scientifically stronger than "
    "manufacturing a positive result from the same calibration data."
)

LIMITATIONS = [
    "The sensor-to-node mapping for both South and North sides was derived "
    "from the same calibration scan against South-side measurements.",
    "Only mid-span (node 6) is layout-invariant and genuinely independent.",
    "n=1 (mid-span only) is insufficient for statistical validation metrics "
    "(R², MAE over a population, etc.).",
    "The North-side comparison uses the same model as the South-side — "
    "same geometry, same material, same loads, same solver. No independent "
    "model was built.",
    "No acceptance criterion is defined by the source publication.",
    "Experimental uncertainty is not provided in the dataset.",
]
""", "Description": "Core independent validation module with status enum, leakage detection, and data structures", "Overwrite": false, "TargetFile": "c:\\Users\\Gaurav Giri\\OneDrive\\Desktop\\W\\backend\\server\\validation\\independent.py"""
