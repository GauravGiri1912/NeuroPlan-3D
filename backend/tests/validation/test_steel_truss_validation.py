"""
Full validation pipeline tests — dataset parsing, solver usage, comparison
correctness, and the honest disagreement this case actually produces.

Tests that need the real 81.5MB dataset file are skipped (not faked) when
it is not present in this environment.
"""
import os
import pytest

from server.validation.parsers.xlsx_parser import dataset_path, DatasetFileNotFoundError
from server.validation.state import run_validation, ValidationState
from server.validation.cases.steel_truss_measurements import (
    load_measurements, PUBLISHED_SOUTH_UD_MM, SHEET_NAME,
)

try:
    dataset_path()
    _HAS_DATASET = True
except DatasetFileNotFoundError:
    _HAS_DATASET = False

requires_dataset = pytest.mark.skipif(
    not _HAS_DATASET,
    reason="Steel truss dataset xlsx not present in this environment",
)


def test_missing_dataset_produces_reference_available_not_a_fabricated_result(monkeypatch, tmp_path):
    """
    With no dataset file reachable, the state must be REFERENCE_AVAILABLE
    (the case is documented) — never REFERENCE_COMPARED, and never a
    silently-invented comparison.
    """
    fake_path = str(tmp_path / "does_not_exist.xlsx")
    result = run_validation(dataset_path=fake_path)
    assert result.state == ValidationState.REFERENCE_AVAILABLE
    assert result.comparisons == []
    assert result.error is not None


@requires_dataset
def test_raw_dataset_values_match_published_figure_within_rounding():
    """
    Cross-check: the raw xlsx sensor readings at peak load must match the
    peer-reviewed publication's own reported table (Fig. 15) — this
    verifies we are reading the correct sheet/columns, independent of our
    own solver.
    """
    # Tolerance: the raw file's peak recorded Jack_Load is 79.87 kN, not
    # exactly the paper's reported 80 kN reference point, so a small,
    # consistently-signed gap (published values all slightly higher, i.e.
    # the higher load) is expected — not a data error. Max observed gap
    # across all 7 sensors is ~0.051 mm; 0.06 mm leaves headroom without
    # masking an actual mismatch (e.g. reading the wrong column entirely).
    measurements = load_measurements()
    by_sensor = {m.sensor_id: m for m in measurements}
    for sensor_id, published_mm in PUBLISHED_SOUTH_UD_MM.items():
        raw_mm = by_sensor[sensor_id].value
        assert raw_mm == pytest.approx(published_mm, abs=0.06), (
            f"sensor {sensor_id}: raw xlsx={raw_mm} vs published Fig.15={published_mm}"
        )


@requires_dataset
def test_measurements_carry_full_provenance():
    measurements = load_measurements()
    for m in measurements:
        assert m.provenance.source_type == "experimental"
        assert m.provenance.dataset
        assert m.provenance.file
        assert m.provenance.sheet == SHEET_NAME
        assert m.provenance.doi == "10.5281/zenodo.15658671"


@requires_dataset
def test_experimental_values_are_never_modified_by_the_pipeline():
    """The comparison must use the raw sensor value verbatim as
    experimental_value — not a recomputed or rounded substitute."""
    measurements = {m.sensor_id: m.value for m in load_measurements()}
    result = run_validation()
    for c in result.comparisons:
        assert c.experimental_value == measurements[c.sensor_id]


@requires_dataset
def test_validation_uses_the_actual_production_solver():
    """
    Proof this isn't a parallel solver: monkeypatch the real production
    solve() and confirm run_validation's result changes accordingly.
    """
    import server.validation.state as state_module

    original_solve = state_module.solve
    calls = {"count": 0}

    def spy_solve(structure, spec):
        calls["count"] += 1
        return original_solve(structure, spec)

    state_module.solve = spy_solve
    try:
        run_validation()
    finally:
        state_module.solve = original_solve

    assert calls["count"] == 1, "run_validation must call the production solve() exactly once"


@requires_dataset
def test_state_is_reference_compared_not_criterion_met():
    """
    No defensible acceptance criterion exists for this case — the result
    must never auto-promote to CRITERION_MET.
    """
    result = run_validation()
    assert result.state == ValidationState.REFERENCE_COMPARED
    assert result.criterion is None
    assert "criterion" in result.criterion_note.lower()


@requires_dataset
def test_midspan_comparison_is_the_correct_order_of_magnitude():
    """
    The high-confidence (SOURCED) mapping — sensor 4 at mid-span — should
    show a real, non-trivial but bounded disagreement: same sign, same
    order of magnitude. This is the specific, defensible claim this
    integration can make.
    """
    result = run_validation()
    midspan = next(c for c in result.comparisons if c.sensor_id == "4")
    assert midspan.neuroplan_value > 0  # downward, same sign as experiment
    assert midspan.experimental_value > 0
    assert midspan.relative_error < 0.5, (
        f"expected order-of-magnitude agreement at mid-span, got "
        f"{midspan.relative_error*100:.1f}% relative error"
    )


@requires_dataset
def test_worst_sensor_disagreement_is_reported_not_averaged_away():
    """
    The summary must surface the WORST point, not just a flattering mean.
    Whatever the residual disagreement is, max_relative_error has to equal
    the largest per-sensor error actually present — no smoothing, no
    dropping of outliers.
    """
    result = run_validation()
    per_sensor = [c.relative_error for c in result.comparisons if c.relative_error is not None]
    assert result.summary.max_relative_error == pytest.approx(max(per_sensor))
    assert result.summary.mae <= result.summary.rmse  # RMSE penalises the outlier


@requires_dataset
def test_sensor_mapping_candidates_rule_out_the_consecutive_layout():
    """
    Locks in the reconstruction fix.

    The source constrains the 7 transducers to interior lower-chord panel
    points but does not say which, leaving 10 symmetric candidate layouts.
    The consecutive layout [3..9] used originally is the WORST of the 10 —
    that is a genuine inference from the data and must stay rejected.

    The layout actually used is deliberately NOT the lowest-MAE one (see
    the module docstring): picking that would be fitting an irregular
    sensor arrangement to the residuals. This test therefore asserts the
    ranking, not that we chose the winner.
    """
    from itertools import combinations
    from server.core.fea.solver import solve
    from server.validation.cases import steel_truss_loss_of_chord as case_module
    from server.validation.cases.steel_truss_measurements import load_measurements

    structure, node_index = case_module.build_structure()
    results = solve(structure, case_module.build_spec())
    node_results = {r.node_id: r for r in results.node_results}

    def downward_mm(panel_point: int) -> float:
        return -node_results[node_index[f"bottom_{panel_point}"]].dy * 1000.0

    by_sensor = {m.sensor_id: m.value for m in load_measurements()}
    measured = [by_sensor[sid] for sid in ("1", "2", "3", "4", "5", "6", "7")]

    def mae_for(sequence) -> float:
        predicted = [downward_mm(n) for n in sequence]
        return sum(abs(p - m) for p, m in zip(predicted, measured)) / len(measured)

    pairs = [(1, 11), (2, 10), (3, 9), (4, 8), (5, 7)]
    scored = {}
    for chosen in combinations(pairs, 3):
        left = sorted(p[0] for p in chosen)
        sequence = tuple(left + [case_module.MIDSPAN_NODE] + sorted(12 - k for k in left))
        scored[sequence] = mae_for(sequence)

    assert len(scored) == 10, "candidate enumeration changed"

    rejected = case_module.REJECTED_CONSECUTIVE_SENSOR_SEQUENCE
    assert scored[rejected] == max(scored.values()), (
        "the consecutive-node layout must remain the worst-fitting candidate; "
        "if it no longer is, the reconstruction changed and the mapping "
        "rationale in the module docstring needs revisiting"
    )

    in_use = case_module._SENSOR_NODE_SEQUENCE
    assert in_use in scored, "the mapping in use is not a valid candidate layout"
    assert scored[in_use] < scored[rejected] / 2, (
        "the layout in use should fit far better than the rejected one"
    )


@requires_dataset
def test_changing_load_magnitude_changes_neuroplan_prediction_but_not_measurements():
    """Inputs changing must change the PREDICTION; the stored
    EXPERIMENTAL values must never move."""
    from server.validation.cases import steel_truss_loss_of_chord as case_module

    original = case_module._LOAD_PER_POINT_N
    try:
        baseline = run_validation()
        baseline_pred = {c.sensor_id: c.neuroplan_value for c in baseline.comparisons}
        baseline_exp = {c.sensor_id: c.experimental_value for c in baseline.comparisons}

        case_module._LOAD_PER_POINT_N = original * 2
        doubled = run_validation()
        doubled_pred = {c.sensor_id: c.neuroplan_value for c in doubled.comparisons}
        doubled_exp = {c.sensor_id: c.experimental_value for c in doubled.comparisons}

        for sid in baseline_pred:
            assert doubled_pred[sid] == pytest.approx(baseline_pred[sid] * 2, rel=1e-6)
            assert doubled_exp[sid] == baseline_exp[sid]
    finally:
        case_module._LOAD_PER_POINT_N = original
