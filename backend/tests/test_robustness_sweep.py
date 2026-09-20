"""Deterministic Load Robustness Sweep (Task 5A).

Reuses the existing LOAD_SCALE perturbation and run_experiment — no
physics duplicated here. Every assertion is checked against real,
independently-derivable solver behaviour (exact linear scaling for a
determinate truss) or cross-checked against the underlying
ExperimentResult objects.
"""
import pytest

from server.core.experiments.robustness import (
    run_load_robustness_sweep, DEFAULT_LOAD_SCALES, TERMINOLOGY_NOTE,
)
from server.core.experiments.engine import run_experiment
from server.core.experiments.models import Perturbation, PerturbationType
from server.core.fea.solver import FEASolverError
from server.core.generator.topology import generate_structure
from server.models.structure import (
    EngineeringSpec, Structure, Node, Member, Support, SupportType,
    PointLoad, CrossSection,
)


def _spec(**overrides):
    return EngineeringSpec(**overrides)


def _structure(spec=None):
    return generate_structure(spec or _spec())


# ─────────────────────────────────────────────
# Default scales and structure
# ─────────────────────────────────────────────

def test_default_five_load_scales():
    assert DEFAULT_LOAD_SCALES == (0.80, 0.90, 1.00, 1.10, 1.20)
    structure = _structure()
    sweep = run_load_robustness_sweep(structure, _spec())
    assert sweep.scales == [0.80, 0.90, 1.00, 1.10, 1.20]
    assert len(sweep.scenarios) == 5
    assert [s.load_scale for s in sweep.scenarios] == [0.80, 0.90, 1.00, 1.10, 1.20]


def test_custom_scales_are_honoured():
    structure = _structure()
    sweep = run_load_robustness_sweep(structure, _spec(), scales=[0.5, 1.5])
    assert sweep.scales == [0.5, 1.5]
    assert len(sweep.scenarios) == 2


# ─────────────────────────────────────────────
# Deterministic ordering
# ─────────────────────────────────────────────

def test_scenario_order_matches_input_scale_order():
    structure = _structure()
    sweep = run_load_robustness_sweep(structure, _spec(), scales=[1.20, 0.80, 1.00])
    assert [s.load_scale for s in sweep.scenarios] == [1.20, 0.80, 1.00]


def test_repeated_sweep_produces_equivalent_results():
    structure = _structure()
    spec = _spec()
    sweep_a = run_load_robustness_sweep(structure, spec)
    sweep_b = run_load_robustness_sweep(structure, spec)

    assert [s.load_scale for s in sweep_a.scenarios] == [s.load_scale for s in sweep_b.scenarios]
    assert [s.structural_status for s in sweep_a.scenarios] == [s.structural_status for s in sweep_b.scenarios]
    for a, b in zip(sweep_a.scenarios, sweep_b.scenarios):
        assert a.max_displacement_mm == pytest.approx(b.max_displacement_mm, rel=1e-12)
        assert a.max_stress_mpa == pytest.approx(b.max_stress_mpa, rel=1e-12)


# ─────────────────────────────────────────────
# Baseline / isolation
# ─────────────────────────────────────────────

def test_baseline_structure_is_not_mutated_by_the_sweep():
    structure = _structure()
    snapshot_loads = [(l.fx, l.fy, l.fz) for l in structure.loads]
    snapshot_members = len(structure.members)

    run_load_robustness_sweep(structure, _spec())

    assert [(l.fx, l.fy, l.fz) for l in structure.loads] == snapshot_loads
    assert len(structure.members) == snapshot_members


def test_scenarios_are_isolated_from_each_other():
    """One scale's perturbation must not leak into another's result —
    checked by confirming each scenario matches an INDEPENDENT single
    run_experiment call at that exact scale."""
    structure = _structure()
    spec = _spec()
    sweep = run_load_robustness_sweep(structure, spec, scales=[0.8, 1.2])

    for scenario in sweep.scenarios:
        independent = run_experiment(
            structure, spec,
            Perturbation(type=PerturbationType.LOAD_SCALE, load_index=0, scale_factor=scenario.load_scale),
        )
        assert scenario.max_displacement_mm == pytest.approx(
            independent.perturbed_max_displacement_mm, rel=1e-12)
        assert scenario.max_stress_mpa == pytest.approx(
            independent.perturbed_max_stress_mpa, rel=1e-12)


# ─────────────────────────────────────────────
# Real load scaling (linear system, exact checks)
# ─────────────────────────────────────────────

def test_load_scaling_is_exactly_linear():
    structure = _structure()
    sweep = run_load_robustness_sweep(structure, _spec())
    baseline = next(s for s in sweep.scenarios if s.load_scale == 1.00)

    for scenario in sweep.scenarios:
        assert scenario.max_displacement_mm == pytest.approx(
            scenario.load_scale * baseline.max_displacement_mm, rel=1e-9)
        assert scenario.max_stress_mpa == pytest.approx(
            scenario.load_scale * baseline.max_stress_mpa, rel=1e-9)


def test_default_structure_is_stable_across_all_default_scales():
    structure = _structure()
    sweep = run_load_robustness_sweep(structure, _spec())
    assert all(s.structural_status == "stable" for s in sweep.scenarios)
    assert all(s.verified is True for s in sweep.scenarios)


# ─────────────────────────────────────────────
# Failed-check scenarios
# ─────────────────────────────────────────────

def test_mixed_stable_and_failed_check_scenarios():
    spec = _spec(primary_load=180_000.0)
    structure = _structure(spec)
    sweep = run_load_robustness_sweep(structure, spec)

    statuses = [s.structural_status for s in sweep.scenarios]
    assert statuses == ["stable", "stable", "stable", "solved_but_failed_checks", "solved_but_failed_checks"]
    failed = [s for s in sweep.scenarios if s.structural_status == "solved_but_failed_checks"]
    for s in failed:
        assert s.verified is False
        assert s.max_displacement_mm is not None    # solved -> real numbers, not withheld
        assert s.max_stress_mpa is not None


def test_summary_counts_match_scenario_statuses():
    spec = _spec(primary_load=180_000.0)
    structure = _structure(spec)
    sweep = run_load_robustness_sweep(structure, spec)

    assert sweep.summary.total_scenarios == 5
    assert sweep.summary.stable_scenarios == 3
    assert sweep.summary.failed_check_scenarios == 2
    assert sweep.summary.unstable_scenarios == 0
    assert sweep.summary.stable_scenarios + sweep.summary.failed_check_scenarios \
        + sweep.summary.unstable_scenarios == sweep.summary.total_scenarios


def test_summary_max_observed_values_match_the_worst_scenario():
    spec = _spec(primary_load=180_000.0)
    structure = _structure(spec)
    sweep = run_load_robustness_sweep(structure, spec)

    expected_max_disp = max(s.max_displacement_mm for s in sweep.scenarios)
    expected_max_stress = max(s.max_stress_mpa for s in sweep.scenarios)
    assert sweep.summary.max_observed_displacement_mm == pytest.approx(expected_max_disp, rel=1e-12)
    assert sweep.summary.max_observed_stress_mpa == pytest.approx(expected_max_stress, rel=1e-12)
    # highest load scale must be the worst case for a monotonic linear system
    assert sweep.scenarios[-1].max_displacement_mm == pytest.approx(expected_max_disp, rel=1e-12)


# ─────────────────────────────────────────────
# Unstable scenario handling
# ─────────────────────────────────────────────
#
# K (global stiffness) depends only on geometry/supports/members, never
# on load magnitude — so LOAD_SCALE cannot itself turn a stable baseline
# into a mechanism at some scales but not others. Verified directly: a
# structure stable at 1.0x is stable at every one of the default scales.
# The only way instability enters this sweep is an ALREADY-BROKEN
# baseline, which the (unguarded, by existing design) baseline solve in
# run_experiment() raises on immediately — the sweep must fail loudly
# rather than report five fabricated "unstable" scenarios.

def _insufficiently_supported_structure() -> Structure:
    section = CrossSection(0.1143, 0.0064)
    return Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, 4, 0, 0)],
        members=[Member(0, 0, 1, "A36", section)],
        # Only node 0 restrained; node 1 fully free -> mechanism, independent of load.
        supports=[Support(node_id=0, support_type=SupportType.PIN)],
        loads=[PointLoad(node_id=1, fx=10_000.0)],
    )


def test_load_scale_cannot_produce_an_unstable_scenario():
    """
    Direct evidence for the physical claim: across a wide range of scales
    (including a very small and a very large one), none becomes UNSTABLE
    — K never changes. An extreme scale (100x) still fails its stress/
    displacement CHECKS, which is a different, load-dependent outcome
    from becoming a mechanism.
    """
    structure = _structure()
    sweep = run_load_robustness_sweep(structure, _spec(), scales=[0.01, 0.8, 1.0, 1.2, 100.0])
    assert all(s.structural_status != "unstable" for s in sweep.scenarios)
    assert [s.structural_status for s in sweep.scenarios] == [
        "stable", "stable", "stable", "stable", "solved_but_failed_checks",
    ]


def test_unsolvable_baseline_raises_instead_of_fabricating_scenarios():
    structure = _insufficiently_supported_structure()
    with pytest.raises(FEASolverError):
        run_load_robustness_sweep(structure, _spec())


# ─────────────────────────────────────────────
# No fabricated values
# ─────────────────────────────────────────────

def test_no_fabricated_values_on_an_unsolvable_baseline():
    """The sweep must not return a partially-fabricated result — it
    either returns real scenarios or raises, never both."""
    structure = _insufficiently_supported_structure()
    try:
        sweep = run_load_robustness_sweep(structure, _spec())
        pytest.fail(f"expected FEASolverError, got a result: {sweep}")
    except FEASolverError:
        pass


def test_terminology_avoids_reliability_and_probability_language():
    structure = _structure()
    sweep = run_load_robustness_sweep(structure, _spec())
    note = sweep.terminology_note.lower()
    assert "reliability" not in note or "not" in note
    assert "probability" in note
    assert "no probability is calculated" in note
    assert sweep.terminology_note == TERMINOLOGY_NOTE


def test_summary_never_claims_safety_outside_tested_scenarios():
    structure = _structure()
    sweep = run_load_robustness_sweep(structure, _spec())
    assert "safe" not in sweep.terminology_note.lower() or "safety" in sweep.terminology_note.lower()
    assert "outside" in sweep.terminology_note.lower()


# ─────────────────────────────────────────────
# Invalid model / error handling
# ─────────────────────────────────────────────

def test_invalid_load_index_raises_cleanly():
    structure = _structure()
    with pytest.raises(ValueError, match="out of range"):
        run_load_robustness_sweep(structure, _spec(), load_index=999)


def test_invalid_load_index_runs_no_scenarios():
    """A fail-fast sweep must not report partial/fabricated results."""
    structure = _structure()
    try:
        run_load_robustness_sweep(structure, _spec(), load_index=999)
        assert False, "expected ValueError"
    except ValueError:
        pass
    # structure itself must remain untouched even on failure
    assert len(structure.loads) >= 1
