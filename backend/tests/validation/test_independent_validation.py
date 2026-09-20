"""
Independent Validation Workflow — Tests

10 focused tests verifying the clean separation between CALIBRATED
(reference) and INDEPENDENT (validation) evidence, and that the system
honestly reports INSUFFICIENT DATA when independent validation is not
established.
"""
import pytest

from server.validation.independent import (
    IndependentValidationStatus, detect_data_leakage,
    INSUFFICIENT_DATA_EXPLANATION, LIMITATIONS,
)
from server.validation.state import run_independent_validation
from server.validation.cases import steel_truss_loss_of_chord as case_module
from server.validation.independence import assess_independence
from server.validation.models import EvidenceIndependence
from server.validation.parsers.xlsx_parser import dataset_path, DatasetFileNotFoundError

try:
    dataset_path()
    _HAS_DATASET = True
except DatasetFileNotFoundError:
    _HAS_DATASET = False

requires_dataset = pytest.mark.skipif(
    not _HAS_DATASET,
    reason="Steel truss dataset xlsx not present in this environment",
)


# ──────────────────────────────────────────────────────────────────────
# 1. Calibration data can be used for calibration (existing path)
# ──────────────────────────────────────────────────────────────────────

def test_calibration_path_still_produces_calibrated_verdict():
    """The existing calibrated comparison must still work and report CALIBRATED."""
    from server.validation.state import run_validation

    result = run_validation(dataset_path=str("__nonexistent__"))
    # Without dataset it's REFERENCE_AVAILABLE, not an error
    assert result.state.value == "reference_available"

    # The independence machinery correctly flags the sensor mapping
    assessment = assess_independence(case_module.build_parameter_inventory())
    assert assessment.verdict is EvidenceIndependence.CALIBRATED


# ──────────────────────────────────────────────────────────────────────
# 2. Validation data cannot influence calibration (North sensors not in scan)
# ──────────────────────────────────────────────────────────────────────

def test_validation_sensors_not_in_calibration_set():
    """North-side sensor IDs (8-14) must not overlap with South-side (1-7)."""
    cal_ids = set(case_module.SOUTH_SENSOR_NODES.keys())
    val_ids = set(case_module.NORTH_SENSOR_NODES.keys())
    assert cal_ids & val_ids == set(), \
        f"Overlap detected: {cal_ids & val_ids}"


# ──────────────────────────────────────────────────────────────────────
# 3. Calibration and validation cases have different IDs
# ──────────────────────────────────────────────────────────────────────

@requires_dataset
def test_calibration_and_validation_cases_are_separate():
    result = run_independent_validation()
    assert result.calibration_case_id != result.validation_case_id
    assert result.calibration_case_id == case_module.CASE_ID
    assert "north" in result.validation_case_id.lower()


# ──────────────────────────────────────────────────────────────────────
# 4. Validation metrics from untouched (North-side) measurements
# ──────────────────────────────────────────────────────────────────────

@requires_dataset
def test_validation_uses_north_side_measurements():
    """Validation comparisons must use sensors 8-14, not 1-7."""
    result = run_independent_validation()
    cal_sensor_ids = {c.sensor_id for c in result.calibration_comparisons}
    val_sensor_ids = {c.sensor_id for c in result.validation_comparisons}

    assert cal_sensor_ids == set(case_module.SOUTH_SENSOR_NODES.keys())
    assert val_sensor_ids == set(case_module.NORTH_SENSOR_NODES.keys())
    assert cal_sensor_ids & val_sensor_ids == set()


# ──────────────────────────────────────────────────────────────────────
# 5. Data leakage is detected and rejected
# ──────────────────────────────────────────────────────────────────────

def test_data_leakage_detected_for_overlapping_sensor_ids():
    leakage = detect_data_leakage(["1", "2", "3"], ["3", "4", "5"])
    assert not leakage.passed
    assert leakage.overlapping_sensor_ids == ["3"]
    assert "VALIDATION DATA USED FOR CALIBRATION" in leakage.explanation


def test_data_leakage_passes_for_disjoint_sensor_ids():
    leakage = detect_data_leakage(["1", "2", "3"], ["4", "5", "6"])
    assert leakage.passed
    assert leakage.overlapping_sensor_ids == []


# ──────────────────────────────────────────────────────────────────────
# 6. Missing validation data produces explicit NOT_RUN status
# ──────────────────────────────────────────────────────────────────────

def test_missing_dataset_produces_not_run_status(tmp_path):
    fake_path = str(tmp_path / "nonexistent.xlsx")
    result = run_independent_validation(dataset_path=fake_path)
    assert result.status == IndependentValidationStatus.NOT_RUN
    assert result.error is not None
    assert result.calibration_comparisons == []
    assert result.validation_comparisons == []


# ──────────────────────────────────────────────────────────────────────
# 7. Existing calibrated/reference comparison still works
# ──────────────────────────────────────────────────────────────────────

@requires_dataset
def test_existing_calibrated_comparison_unchanged():
    """run_validation() must still work exactly as before."""
    from server.validation.state import run_validation
    result = run_validation()
    assert result.state.value in ("reference_compared", "reference_available")
    assert result.independence.verdict is EvidenceIndependence.CALIBRATED


# ──────────────────────────────────────────────────────────────────────
# 8. Solver is called exactly once per independent validation run
# ──────────────────────────────────────────────────────────────────────

@requires_dataset
def test_solver_called_once_for_independent_validation():
    import server.validation.state as state_module

    original_solve = state_module.solve
    calls = {"count": 0}

    def spy_solve(structure, spec):
        calls["count"] += 1
        return original_solve(structure, spec)

    state_module.solve = spy_solve
    try:
        run_independent_validation()
    finally:
        state_module.solve = original_solve

    assert calls["count"] == 1, \
        "run_independent_validation must call the production solve() exactly once"


# ──────────────────────────────────────────────────────────────────────
# 9. Two runs produce consistent results
# ──────────────────────────────────────────────────────────────────────

@requires_dataset
def test_two_runs_produce_consistent_results():
    r1 = run_independent_validation()
    r2 = run_independent_validation()
    assert r1.status == r2.status
    assert r1.calibration_case_id == r2.calibration_case_id
    assert r1.validation_case_id == r2.validation_case_id
    assert len(r1.calibration_comparisons) == len(r2.calibration_comparisons)
    assert len(r1.validation_comparisons) == len(r2.validation_comparisons)


# ──────────────────────────────────────────────────────────────────────
# 10. No fake validation status — never auto-promotes to INDEPENDENT_PASSED
#     when calibration-derived mapping is used
# ──────────────────────────────────────────────────────────────────────

@requires_dataset
def test_status_never_claims_independent_validation_passed():
    """
    The single most important test: this dataset does NOT support
    independent validation, so the status must NEVER be INDEPENDENT_PASSED.
    """
    result = run_independent_validation()
    assert result.status != IndependentValidationStatus.INDEPENDENT_PASSED, \
        "INDEPENDENT_PASSED must never be reported for a dataset whose " \
        "sensor mapping was calibrated using the measured deflection profile"
    assert result.status == IndependentValidationStatus.INSUFFICIENT_DATA
    assert result.midspan_is_independent is True
    assert len(result.limitations) > 0
    assert "INDEPENDENT VALIDATION NOT ESTABLISHED" not in result.status_label or \
        result.status == IndependentValidationStatus.INSUFFICIENT_DATA
