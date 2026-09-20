"""
Fatigue screening — IS 800:2007 Section 13 S-N methodology.

Hand-verified: category sigma_c=100 MPa, m=3, N_ref=2e6.
  N(range=50) = 2e6*(100/50)^3 = 2e6*8 = 16,000,000 cycles
  N(range=80) = 2e6*(100/80)^3 = 2e6*1.953125 = 3,906,250 cycles
"""
import pytest

from server.core.codes.fatigue import (
    FatigueDetailCategory, check_fatigue, permissible_cycles,
    miners_cumulative_damage, stress_range_from_results, screen_fatigue,
)
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec

CATEGORY = FatigueDetailCategory(name="Test Class", sigma_c_mpa=100.0, m=3.0, n_ref=2_000_000)


def test_permissible_cycles_matches_hand_calculation():
    assert permissible_cycles(50.0, CATEGORY) == pytest.approx(16_000_000.0, rel=1e-9)
    assert permissible_cycles(80.0, CATEGORY) == pytest.approx(3_906_250.0, rel=1e-6)


def test_halving_stress_range_multiplies_permissible_cycles_by_eight():
    """N ~ 1/range^3, so halving the range gives 2^3 = 8x the life."""
    full = permissible_cycles(100.0, CATEGORY)
    half = permissible_cycles(50.0, CATEGORY)
    assert half == pytest.approx(8.0 * full, rel=1e-9)


def test_at_reference_strength_permissible_cycles_equals_n_ref():
    assert permissible_cycles(CATEGORY.sigma_c_mpa, CATEGORY) == pytest.approx(
        CATEGORY.n_ref, rel=1e-9
    )


def test_usage_ratio_matches_hand_calculation():
    check = check_fatigue(0, 50.0, design_cycles=1_000_000, category=CATEGORY)
    assert check.usage_ratio == pytest.approx(1_000_000 / 16_000_000, rel=1e-9)
    assert check.status == "pass"


def test_usage_ratio_above_one_fails():
    check = check_fatigue(0, 50.0, design_cycles=20_000_000, category=CATEGORY)
    assert check.usage_ratio > 1.0
    assert check.status == "fail"


def test_zero_stress_range_is_not_applicable():
    check = check_fatigue(0, 0.0, design_cycles=1_000_000, category=CATEGORY)
    assert check.status == "not_applicable"
    assert check.usage_ratio == 0.0


def test_miners_rule_matches_hand_calculation():
    D, per_range = miners_cumulative_damage(
        [(50.0, 8_000_000), (80.0, 500_000)], CATEGORY
    )
    expected = 8_000_000 / 16_000_000 + 500_000 / 3_906_250
    assert D == pytest.approx(expected, rel=1e-9)
    assert per_range[0] == pytest.approx(0.5, rel=1e-9)


def test_miners_rule_at_exactly_one_is_the_failure_boundary():
    D, _ = miners_cumulative_damage([(50.0, 16_000_000)], CATEGORY)
    assert D == pytest.approx(1.0, rel=1e-9)


def test_stress_range_computed_from_two_real_solver_runs():
    """
    The stress range must come from two ACTUAL solves, not a formula.

    generate_structure() bakes the load into structure.loads at
    generation time — solve() does not re-read spec.primary_load, so the
    "unloaded" case needs its OWN structure generated from a zero-load
    spec, not just a different spec passed to solve() on the same
    already-loaded structure.
    """
    spec = EngineeringSpec()
    structure = generate_structure(spec)

    unloaded_spec = EngineeringSpec(primary_load=0.0)
    unloaded_structure = generate_structure(unloaded_spec)

    loaded_results = solve(structure, spec)
    unloaded_results = solve(unloaded_structure, unloaded_spec)

    ranges = stress_range_from_results(
        loaded_results.member_results, unloaded_results.member_results
    )
    assert len(ranges) == len(structure.members)
    # The loaded case's own stress equals the range here since unloaded=0.
    loaded_stress = {m.member_id: abs(m.stress) / 1e6 for m in loaded_results.member_results}
    for member_id, rng in ranges.items():
        assert rng == pytest.approx(loaded_stress[member_id], rel=1e-9)


def test_screening_report_identifies_the_governing_member():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    unloaded_spec = EngineeringSpec(primary_load=0.0)
    ranges = stress_range_from_results(
        solve(structure, spec).member_results,
        solve(structure, unloaded_spec).member_results,
    )
    report = screen_fatigue(ranges, design_cycles=2_000_000, category=CATEGORY)

    assert report.title == "FATIGUE SCREENING"
    assert report.governing_member_id is not None
    governing_check = next(c for c in report.checks if c.member_id == report.governing_member_id)
    assert governing_check.usage_ratio == pytest.approx(report.max_usage_ratio)


def test_report_discloses_that_the_table_is_not_embedded():
    report = screen_fatigue({0: 10.0}, 1000, CATEGORY)
    assert "not looked up from an embedded code table" in report.disclaimer
    assert "Table 26" in report.disclaimer


def test_category_default_slope_is_three():
    cat = FatigueDetailCategory(name="X", sigma_c_mpa=71.0)
    assert cat.m == 3.0
    assert cat.n_ref == 2_000_000
