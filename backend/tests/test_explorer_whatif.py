"""
Priority 10 — Design space explorer, and Priority 11 — What-if.

The load-doubling case is the strongest available check on the whole
chain: in a linear-elastic determinate truss, doubling the applied load
must double stress, displacement, stress ratio and buckling utilisation
EXACTLY, while leaving weight and member count untouched. Any scaling
bug anywhere in generation, assembly, solve or metric extraction breaks
that identity.
"""
import pytest

from server.core.analysis.explorer import (
    explore_design_space, run_what_if, WhatIfParameter, TradeoffTable,
    PARETO_RELATIVE_TOLERANCE, _is_better, _is_not_worse,
)
from server.models.structure import EngineeringSpec, StructureType


def _spec() -> EngineeringSpec:
    return EngineeringSpec()


# ─────────────────────────────────────────────
# Design space explorer
# ─────────────────────────────────────────────

def test_explorer_analyses_the_full_cartesian_product():
    table = explore_design_space(
        _spec(),
        structure_types=[StructureType.PRATT, StructureType.WARREN],
        panel_counts=[4, 6],
        heights=[2.0, 3.0],
    )
    assert len(table.candidates) == 2 * 2 * 2
    assert table.n_analysed == 8
    assert table.n_failed == 0


def test_every_candidate_reports_the_required_metrics():
    table = explore_design_space(_spec(), panel_counts=[4, 6])
    for candidate in table.successful():
        m = candidate.metrics
        assert m.weight_kg > 0
        assert m.max_stress_mpa > 0
        assert m.max_displacement_mm > 0
        assert m.member_count > 0
        assert m.material_volume_m3 > 0
        assert m.factor_of_safety > 0


def test_deeper_truss_reduces_stress_and_displacement():
    """Physics sanity across the design space, not just at one point."""
    table = explore_design_space(
        _spec(), structure_types=[StructureType.PRATT], heights=[2.0, 4.0])
    shallow = next(c for c in table.successful() if c.parameters["height_m"] == "2")
    deep = next(c for c in table.successful() if c.parameters["height_m"] == "4")

    assert deep.metrics.max_stress_mpa < shallow.metrics.max_stress_mpa
    assert deep.metrics.max_displacement_mm < shallow.metrics.max_displacement_mm


def test_no_candidate_is_declared_best():
    """The explorer must not pick a winner for the engineer."""
    table = explore_design_space(_spec(), panel_counts=[4, 6, 8])
    assert not hasattr(table, "best")
    assert not hasattr(table, "recommended")
    assert "No design is declared 'best'" in table.selection_policy
    assert "left to you" in table.selection_policy


def test_pareto_marking_identifies_a_non_empty_non_dominated_set():
    table = explore_design_space(
        _spec(),
        structure_types=[StructureType.PRATT, StructureType.WARREN],
        panel_counts=[4, 6], heights=[2.0, 3.0],
    )
    optimal = [c for c in table.successful() if c.pareto_optimal]
    assert optimal, "at least one candidate must be non-dominated"
    assert len(optimal) <= len(table.successful())


def test_a_strictly_worse_candidate_is_marked_dominated():
    """
    Same topology and height, but a heavier section can only be heavier;
    if it is also no better on stress and deflection it must be dominated.
    """
    table = explore_design_space(
        _spec(), structure_types=[StructureType.PRATT], panel_counts=[6],
        heights=[3.0], section_keys=["CHS_114x6", "CHS_219x8"],
    )
    entries = {c.parameters["section"]: c for c in table.successful()}
    light, heavy = entries["CHS_114x6"], entries["CHS_219x8"]

    assert heavy.metrics.weight_kg > light.metrics.weight_kg
    if (heavy.metrics.max_stress_mpa >= light.metrics.max_stress_mpa
            and heavy.metrics.max_displacement_mm >= light.metrics.max_displacement_mm):
        assert heavy.pareto_optimal is False


def test_pareto_domination_ignores_floating_point_noise():
    """
    Regression. Three topologies gave mathematically identical peak
    stress differing in the 14th significant figure; the one that rounded
    down escaped domination and was presented as a real trade-off.
    """
    a, b = 38.412047973599954, 38.412047973599975
    assert not _is_better(a, b), "a 2e-14 difference is not an engineering difference"
    assert _is_not_worse(a, b) and _is_not_worse(b, a)

    assert _is_better(1.0, 2.0)
    assert not _is_better(2.0, 1.0)
    assert PARETO_RELATIVE_TOLERANCE < 1e-6


def test_unsolvable_candidate_is_recorded_not_dropped():
    """A failing region of the design space is information, not noise."""
    table = explore_design_space(
        _spec(), structure_types=[StructureType.PRATT], panel_counts=[6, 0])
    assert len(table.candidates) == 2
    failed = [c for c in table.candidates if c.failed]
    if failed:
        assert failed[0].failure_reason
        assert failed[0] in table.candidates


# ─────────────────────────────────────────────
# What-if
# ─────────────────────────────────────────────

def _delta(result, name):
    return next(d for d in result.deltas if d.name == name)


def test_doubling_the_load_exactly_doubles_every_force_driven_metric():
    spec = _spec()
    result = run_what_if(spec, {WhatIfParameter.PRIMARY_LOAD: spec.primary_load * 2})

    assert not result.failed
    for name in ("max_stress_mpa", "max_displacement_mm",
                 "max_stress_ratio", "max_buckling_utilisation"):
        d = _delta(result, name)
        assert d.modified == pytest.approx(2.0 * d.baseline, rel=1e-9), name
        assert d.percent_change == pytest.approx(100.0, rel=1e-6)


def test_doubling_the_load_leaves_weight_and_member_count_unchanged():
    spec = _spec()
    result = run_what_if(spec, {WhatIfParameter.PRIMARY_LOAD: spec.primary_load * 2})

    assert _delta(result, "weight_kg").absolute_change == pytest.approx(0.0)
    assert _delta(result, "member_count").absolute_change == pytest.approx(0.0)


def test_what_if_reports_the_critical_member_before_and_after():
    spec = _spec()
    result = run_what_if(spec, {WhatIfParameter.PRIMARY_LOAD: spec.primary_load * 2})

    assert result.baseline_critical_member is not None
    assert result.modified_critical_member is not None
    # Pure load scaling cannot move the critical member in a linear model.
    assert result.critical_member_changed is False


def test_changing_geometry_can_move_the_critical_member():
    """A changed load path is the finding, not just a changed number."""
    spec = _spec()
    result = run_what_if(spec, {
        WhatIfParameter.HEIGHT: 1.2,
        WhatIfParameter.NUM_PANELS: 10,
    })
    assert not result.failed
    assert result.modified_critical_member is not None


def test_what_if_detects_a_verification_flip():
    """A load large enough to overstress the truss must flip the verdict."""
    spec = _spec()
    result = run_what_if(spec, {WhatIfParameter.PRIMARY_LOAD: 5_000_000.0})

    assert result.baseline_verified is True
    assert result.modified_verified is False
    assert result.verification_changed is True


def test_heavier_section_reduces_stress_and_increases_weight():
    result = run_what_if(_spec(), {WhatIfParameter.SECTION: "CHS_219x8"})

    assert _delta(result, "weight_kg").absolute_change > 0
    assert _delta(result, "max_stress_mpa").absolute_change < 0


def test_changing_material_changes_the_result():
    result = run_what_if(_spec(), {WhatIfParameter.MATERIAL: "AL6061"})
    assert not result.failed
    # Aluminium is lighter and less stiff than steel.
    assert _delta(result, "weight_kg").absolute_change < 0
    assert _delta(result, "max_displacement_mm").absolute_change > 0


def test_reactions_are_reported_and_scale_with_load():
    spec = _spec()
    result = run_what_if(spec, {WhatIfParameter.PRIMARY_LOAD: spec.primary_load * 2})
    assert result.modified_reaction_total_n == pytest.approx(
        2.0 * result.baseline_reaction_total_n, rel=1e-6
    )


def test_unknown_material_is_rejected():
    with pytest.raises(ValueError, match="Unknown material"):
        run_what_if(_spec(), {WhatIfParameter.MATERIAL: "MITHRIL"})


def test_unknown_section_is_rejected():
    with pytest.raises(ValueError, match="Unknown section"):
        run_what_if(_spec(), {WhatIfParameter.SECTION: "CHS_9999"})


def test_empty_change_set_is_rejected():
    with pytest.raises(ValueError, match="at least one parameter"):
        run_what_if(_spec(), {})


def test_what_if_states_that_both_cases_were_actually_solved():
    result = run_what_if(_spec(), {WhatIfParameter.PRIMARY_LOAD: 60_000.0})
    assert "production solver" in result.provenance
    assert "No value is scaled or extrapolated" in result.provenance
