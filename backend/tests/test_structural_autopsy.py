"""Structural Autopsy — evidence-only diagnosis (Task 4A).

No AI. Every assertion is checked against exact solver output, either
by re-deriving the expected value independently or by cross-checking
against the ExperimentResult the diagnosis was built from.
"""
import pytest

from server.core.experiments.autopsy import (
    diagnose, DiagnosisStepType, CAUSE_NOT_DETERMINED,
)
from server.core.experiments.engine import run_experiment
from server.core.experiments.models import Perturbation, PerturbationType
from server.core.generator.topology import generate_structure
from server.models.structure import (
    Structure, Node, Member, Support, SupportType, PointLoad, CrossSection,
    EngineeringSpec,
)

SECTION = CrossSection(0.1143, 0.0064)


def _spec():
    return EngineeringSpec()


def _structure():
    return generate_structure(_spec())


def _braced_panel(load: float = 10_000.0) -> Structure:
    """Indeterminate-by-1 panel (both diagonals present) — removing
    either diagonal leaves a determinate, stable structure with a real,
    non-trivial displacement/stress change."""
    return Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, 4, 0, 0), Node(2, 4, 3, 0), Node(3, 0, 3, 0)],
        members=[
            Member(0, 0, 1, "A36", SECTION),
            Member(1, 1, 2, "A36", SECTION),
            Member(2, 2, 3, "A36", SECTION),
            Member(3, 3, 0, "A36", SECTION),
            Member(4, 0, 2, "A36", SECTION),
            Member(5, 1, 3, "A36", SECTION),
        ],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X, dx=False, dy=True, dz=True),
            Support(node_id=2, support_type=SupportType.OUT_OF_PLANE),
            Support(node_id=3, support_type=SupportType.OUT_OF_PLANE),
        ],
        loads=[PointLoad(node_id=2, fy=-load)],
    )


def _step_types(autopsy):
    return [s.type for s in autopsy.steps]


# ─────────────────────────────────────────────
# Stable removal — displacement increase
# ─────────────────────────────────────────────

def test_stable_removal_with_displacement_increase():
    structure = _braced_panel()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    autopsy = diagnose(result)

    assert autopsy.baseline_status == "stable"
    assert autopsy.perturbed_status == "stable"
    disp_step = next(s for s in autopsy.steps if s.type is DiagnosisStepType.DISPLACEMENT_INCREASE)
    assert disp_step.evidence["baseline_max_displacement_mm"] == pytest.approx(
        result.baseline_max_displacement_mm, rel=1e-9)
    assert disp_step.evidence["perturbed_max_displacement_mm"] == pytest.approx(
        result.perturbed_max_displacement_mm, rel=1e-9)
    assert disp_step.evidence["max_displacement_mm_change"] > 0
    assert disp_step.evidence["max_displacement_mm_percent_change"] == pytest.approx(
        result.displacement_percent_change, rel=1e-9)


# ─────────────────────────────────────────────
# Stress increase
# ─────────────────────────────────────────────

def test_stress_increase_step_matches_experiment_result():
    structure = _braced_panel()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    autopsy = diagnose(result)

    stress_step = next(s for s in autopsy.steps if s.type is DiagnosisStepType.STRESS_INCREASE)
    assert stress_step.evidence["max_stress_mpa_change"] == pytest.approx(
        result.stress_change_mpa, rel=1e-9)
    assert stress_step.evidence["max_stress_mpa_percent_change"] == pytest.approx(
        result.stress_percent_change, rel=1e-9)
    assert "increased" in stress_step.summary
    assert f"{result.stress_percent_change:.2f}%" in stress_step.summary


# ─────────────────────────────────────────────
# Critical member change
# ─────────────────────────────────────────────

def test_critical_member_changed_step():
    """The determinate Pratt truss under MEMBER_AREA_SCALE keeps solving
    (unlike MEMBER_REMOVE, which makes it a mechanism), giving a clean,
    stable case to exercise a critical-member change deterministically."""
    structure = _structure()
    baseline_critical = max(
        run_experiment(structure, _spec(),
                       Perturbation(type=PerturbationType.MEMBER_AREA_SCALE,
                                   member_id=structure.members[0].id, scale_factor=1.0))
        .baseline_results.member_results,
        key=lambda m: abs(m.stress),
    ).member_id

    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_AREA_SCALE,
                                        member_id=baseline_critical, scale_factor=1.5))
    assert result.critical_member_changed, "fixture assumes enlarging the critical member shifts it"

    autopsy = diagnose(result)
    step = next(s for s in autopsy.steps if s.type is DiagnosisStepType.CRITICAL_MEMBER_CHANGED)
    assert step.evidence["previous_critical_member"] == result.critical_member_before
    assert step.evidence["new_critical_member"] == result.critical_member_after
    assert str(result.critical_member_before) in step.summary
    assert str(result.critical_member_after) in step.summary


def test_no_critical_member_step_when_unchanged():
    structure = _braced_panel()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.LOAD_SCALE, load_index=0, scale_factor=1.0000001))
    assert not result.critical_member_changed
    autopsy = diagnose(result)
    assert DiagnosisStepType.CRITICAL_MEMBER_CHANGED not in _step_types(autopsy)


# ─────────────────────────────────────────────
# Unstable removal
# ─────────────────────────────────────────────

def test_unstable_removal_reports_instability_only():
    """On the determinate Pratt truss every member is non-redundant —
    removing any one is a mechanism, deterministically."""
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=9))
    assert result.perturbed_results is None

    autopsy = diagnose(result)
    assert autopsy.perturbed_status == "unstable"
    assert autopsy.baseline_status == "stable"
    assert len(autopsy.steps) == 1
    assert autopsy.steps[0].type is DiagnosisStepType.STRUCTURAL_INSTABILITY
    assert autopsy.steps[0].evidence["solver_error"] == result.perturbed_error
    assert autopsy.steps[0].evidence["solver_error"] is not None


def test_unstable_removal_has_no_displacement_or_stress_steps():
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=9))
    autopsy = diagnose(result)
    types = _step_types(autopsy)
    assert DiagnosisStepType.DISPLACEMENT_INCREASE not in types
    assert DiagnosisStepType.DISPLACEMENT_DECREASE not in types
    assert DiagnosisStepType.STRESS_INCREASE not in types
    assert DiagnosisStepType.STRESS_DECREASE not in types
    assert DiagnosisStepType.FORCE_REDISTRIBUTION not in types
    assert DiagnosisStepType.CRITICAL_MEMBER_CHANGED not in types


# ─────────────────────────────────────────────
# Missing comparison data / zero-baseline percentage
# ─────────────────────────────────────────────

def test_missing_comparison_data_produces_no_magnitude_steps():
    """When perturbed_results is None there is nothing to compare —
    the autopsy must not invent a comparison."""
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.SUPPORT_REMOVE,
                                        support_node_id=structure.supports[0].node_id))
    assert result.perturbed_results is None
    autopsy = diagnose(result)
    assert len(autopsy.steps) == 1
    assert autopsy.steps[0].type is DiagnosisStepType.STRUCTURAL_INSTABILITY


def test_zero_baseline_percentage_is_none_not_fabricated():
    structure = _braced_panel()
    # LOAD_SCALE by 0 zeroes the load entirely -> baseline stress/displacement
    # for THIS perturbation's own baseline is unaffected (baseline is always
    # the untouched structure), so instead exercise the zero-denominator via
    # the model-level helper directly to prove the autopsy never divides by
    # a ~0 baseline while still asserting it end-to-end from a real result.
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert result.baseline_max_displacement_mm > 0   # sanity: real fixture, not the zero case
    from server.core.experiments.models import _percent_change
    assert _percent_change(0.0, 5.0) is None
    assert _percent_change(1e-15, 5.0) is None

    # ExperimentResult is a plain (non-frozen) dataclass — shallow-copy it
    # and force stress_percent_change to None, exactly the state a
    # zero-baseline case produces, to prove the autopsy surfaces None
    # rather than fabricating 0% or inf%.
    import copy
    zero_baseline_result = copy.copy(result)
    zero_baseline_result.stress_percent_change = None
    autopsy = diagnose(zero_baseline_result)
    stress_step = next(s for s in autopsy.steps if s.type in (
        DiagnosisStepType.STRESS_INCREASE, DiagnosisStepType.STRESS_DECREASE,
        DiagnosisStepType.STRESS_UNCHANGED))
    assert stress_step.evidence["max_stress_mpa_percent_change"] is None
    assert "%" not in stress_step.summary


# ─────────────────────────────────────────────
# No fabricated metrics
# ─────────────────────────────────────────────

def test_no_fabricated_metrics_on_unstable_case():
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=9))
    autopsy = diagnose(result)
    for step in autopsy.steps:
        for key, value in step.evidence.items():
            if key != "solver_error":
                pytest.fail(f"unexpected evidence key on an unstable diagnosis: {key}")
    assert autopsy.steps[0].evidence["solver_error"] == result.perturbed_error


def test_evidence_values_trace_exactly_to_experiment_result():
    """Every numeric value in every step must equal a value already on
    the ExperimentResult — never independently recomputed."""
    structure = _braced_panel()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    autopsy = diagnose(result)

    disp_step = next(s for s in autopsy.steps if s.type is DiagnosisStepType.DISPLACEMENT_INCREASE)
    assert disp_step.evidence["baseline_max_displacement_mm"] == result.baseline_max_displacement_mm
    assert disp_step.evidence["perturbed_max_displacement_mm"] == result.perturbed_max_displacement_mm
    assert disp_step.evidence["max_displacement_mm_change"] == result.displacement_change_mm


# ─────────────────────────────────────────────
# Deterministic ordering
# ─────────────────────────────────────────────

def test_diagnosis_step_ordering_is_deterministic():
    structure = _braced_panel()
    perturbation = Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5)
    result_a = run_experiment(structure, _spec(), perturbation)
    result_b = run_experiment(structure, _spec(), perturbation)

    order_a = _step_types(diagnose(result_a))
    order_b = _step_types(diagnose(result_b))
    assert order_a == order_b
    # force redistribution -> stress -> displacement, matching the task's
    # example flow (no critical-member change in this fixture)
    assert order_a == [
        DiagnosisStepType.FORCE_REDISTRIBUTION,
        DiagnosisStepType.STRESS_INCREASE,
        DiagnosisStepType.DISPLACEMENT_INCREASE,
    ]


def test_failed_check_step_appears_last_when_present():
    section = SECTION
    panel = Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, 4, 0, 0), Node(2, 4, 3, 0), Node(3, 0, 3, 0)],
        members=[
            Member(0, 0, 1, "A36", section), Member(1, 1, 2, "A36", section),
            Member(2, 2, 3, "A36", section), Member(3, 3, 0, "A36", section),
            Member(4, 0, 2, "A36", section), Member(5, 1, 3, "A36", section),
        ],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X, dx=False, dy=True, dz=True),
            Support(node_id=2, support_type=SupportType.OUT_OF_PLANE),
            Support(node_id=3, support_type=SupportType.OUT_OF_PLANE),
        ],
        loads=[PointLoad(node_id=2, fy=-330_000.0)],   # baseline passes, perturbed fails
    )
    spec = EngineeringSpec()
    result = run_experiment(panel, spec, Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert result.baseline_verified is True
    assert result.perturbed_verified is False
    assert result.structural_status == "solved_but_failed_checks"

    autopsy = diagnose(result)
    assert autopsy.steps[-1].type is DiagnosisStepType.FAILED_CHECK
    evidence = autopsy.steps[-1].evidence
    worst = result.perturbed_results.diagnosis.failures[0]
    assert evidence["failure_type"] == worst.failure_type.value
    assert evidence["actual_value"] == worst.actual_value
    assert evidence["limit_value"] == worst.limit_value
    assert evidence["total_failed_checks"] == len(result.perturbed_results.diagnosis.failures)


# ─────────────────────────────────────────────
# Causality rule
# ─────────────────────────────────────────────

def test_cause_attribution_is_always_not_determined():
    structure = _braced_panel()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert diagnose(result).cause_attribution == CAUSE_NOT_DETERMINED

    unstable_result = run_experiment(_structure(), _spec(),
                                     Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=9))
    assert diagnose(unstable_result).cause_attribution == CAUSE_NOT_DETERMINED


def test_no_step_asserts_causation_in_its_summary_text():
    structure = _braced_panel()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    autopsy = diagnose(result)
    for step in autopsy.steps:
        assert "caused" not in step.summary.lower()
        assert "because" not in step.summary.lower()


# ─────────────────────────────────────────────
# Baseline immutability
# ─────────────────────────────────────────────

def test_diagnose_does_not_mutate_the_experiment_result_or_baseline_structure():
    import copy
    structure = _braced_panel()
    snapshot_member_count = len(structure.members)
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    baseline_snapshot = copy.deepcopy(result.baseline_results)

    diagnose(result)
    diagnose(result)  # run twice to catch any accumulating side effect

    assert len(structure.members) == snapshot_member_count
    assert result.baseline_results.diagnosis.max_displacement_mm == \
        baseline_snapshot.diagnosis.max_displacement_mm
    assert len(result.baseline_results.member_results) == len(baseline_snapshot.member_results)


def test_removed_member_id_is_reported():
    structure = _braced_panel()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    autopsy = diagnose(result)
    assert autopsy.removed_member_id == 5


def test_removed_member_id_is_none_for_non_removal_perturbation():
    structure = _braced_panel()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.LOAD_SCALE, load_index=0, scale_factor=1.5))
    autopsy = diagnose(result)
    assert autopsy.removed_member_id is None
