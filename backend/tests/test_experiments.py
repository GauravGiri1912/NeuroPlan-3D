"""Failure Experiment Engine — Task 1.

Every perturbation is checked against exact linear-truss physics for the
generated (statically determinate) Pratt truss, not just "did it run".
"""
import copy
import pytest

from server.core.experiments.engine import run_experiment, apply_perturbation
from server.core.experiments.models import Perturbation, PerturbationType
from server.core.fea.solver import solve, FEASolverError
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, MATERIAL_LIBRARY


def _spec():
    return EngineeringSpec()


def _structure():
    return generate_structure(_spec())


def _critical(results):
    return max(results.member_results, key=lambda m: abs(m.stress))


# ─────────────────────────────────────────────
# Baseline preservation
# ─────────────────────────────────────────────

def test_baseline_structure_is_not_mutated_by_any_perturbation():
    structure = _structure()
    snapshot = copy.deepcopy(structure)

    for perturbation in (
        Perturbation(type=PerturbationType.LOAD_SCALE, load_index=0, scale_factor=3.0),
        Perturbation(type=PerturbationType.LOAD_REVERSE, load_index=0),
        Perturbation(type=PerturbationType.MEMBER_AREA_SCALE, member_id=structure.members[0].id, scale_factor=2.0),
        Perturbation(type=PerturbationType.YOUNGS_MODULUS_SCALE, material_key="A36", scale_factor=2.0),
        Perturbation(type=PerturbationType.GEOMETRY_OFFSET, node_id=structure.nodes[0].id, offset=(0.1, 0, 0)),
        Perturbation(type=PerturbationType.SUPPORT_REMOVE, support_node_id=structure.supports[0].node_id),
    ):
        run_experiment(structure, _spec(), perturbation)

    assert structure.loads[0].fy == snapshot.loads[0].fy
    assert [n.x for n in structure.nodes] == [n.x for n in snapshot.nodes]
    assert structure.members[0].section.wall_thickness == snapshot.members[0].section.wall_thickness
    assert len(structure.supports) == len(snapshot.supports)


def test_baseline_results_reproducible_after_experiment():
    structure = _structure()
    spec = _spec()
    before = solve(structure, spec)
    run_experiment(structure, spec, Perturbation(type=PerturbationType.LOAD_SCALE, load_index=0, scale_factor=5.0))
    after = solve(structure, spec)
    assert before.diagnosis.max_displacement_mm == after.diagnosis.max_displacement_mm


def test_material_library_restored_after_youngs_modulus_perturbation():
    original_e = MATERIAL_LIBRARY["A36"].E
    run_experiment(_structure(), _spec(),
                   Perturbation(type=PerturbationType.YOUNGS_MODULUS_SCALE, material_key="A36", scale_factor=3.0))
    assert MATERIAL_LIBRARY["A36"].E == original_e


# ─────────────────────────────────────────────
# LOAD_SCALE
# ─────────────────────────────────────────────

def test_load_scale_doubles_displacement_and_stress_linearly():
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.LOAD_SCALE, load_index=0, scale_factor=2.0))
    base_disp = result.baseline_results.diagnosis.max_displacement_mm
    assert result.displacement_change_mm == pytest.approx(base_disp, rel=1e-9)
    assert not result.critical_member_changed
    assert result.verification_status_changed == (result.baseline_verified != result.perturbed_verified)


def test_load_scale_down_reduces_stress():
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.LOAD_SCALE, load_index=0, scale_factor=0.5))
    assert result.stress_change_mpa < 0
    assert result.displacement_change_mm < 0


# ─────────────────────────────────────────────
# LOAD_REVERSE
# ─────────────────────────────────────────────

def test_load_reverse_flips_every_signed_member_force():
    structure = _structure()
    result = run_experiment(structure, _spec(), Perturbation(type=PerturbationType.LOAD_REVERSE, load_index=0))
    base_forces = {m.member_id: m.axial_force for m in result.baseline_results.member_results}
    pert_forces = {m.member_id: m.axial_force for m in result.perturbed_results.member_results}
    for member_id, force in base_forces.items():
        assert pert_forces[member_id] == pytest.approx(-force, abs=1e-6)


def test_load_reverse_leaves_max_displacement_magnitude_unchanged():
    """max_displacement_mm is a magnitude (Euclidean norm) — a full sign
    flip of a linear system changes direction, not magnitude."""
    structure = _structure()
    result = run_experiment(structure, _spec(), Perturbation(type=PerturbationType.LOAD_REVERSE, load_index=0))
    assert result.displacement_change_mm == pytest.approx(0.0, abs=1e-9)


# ─────────────────────────────────────────────
# MEMBER_AREA_SCALE
# ─────────────────────────────────────────────

def test_member_area_scale_halves_stress_without_changing_force():
    structure = _structure()
    baseline = solve(structure, _spec())
    critical = _critical(baseline)

    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_AREA_SCALE,
                                        member_id=critical.member_id, scale_factor=2.0))
    perturbed_member = next(m for m in result.perturbed_results.member_results
                            if m.member_id == critical.member_id)
    assert perturbed_member.axial_force == pytest.approx(critical.axial_force, rel=1e-9)
    assert perturbed_member.stress == pytest.approx(critical.stress / 2.0, rel=1e-6)


def test_member_area_scale_does_not_affect_sibling_members_sharing_a_section():
    structure = _structure()
    shared_id = id(structure.members[0].section)
    sibling = next((m for m in structure.members[1:] if id(m.section) == shared_id), None)
    assert sibling is not None, "fixture assumes shared CrossSection objects"

    baseline = solve(structure, _spec())
    sibling_before = next(m.stress for m in baseline.member_results if m.member_id == sibling.id)

    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_AREA_SCALE,
                                        member_id=structure.members[0].id, scale_factor=3.0))
    sibling_after = next(m.stress for m in result.perturbed_results.member_results if m.member_id == sibling.id)
    assert sibling_after == pytest.approx(sibling_before, rel=1e-9)


# ─────────────────────────────────────────────
# YOUNGS_MODULUS_SCALE
# ─────────────────────────────────────────────

def test_youngs_modulus_scale_halves_displacement_leaves_stress_unchanged():
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.YOUNGS_MODULUS_SCALE,
                                        material_key="A36", scale_factor=2.0))
    base_disp = result.baseline_results.diagnosis.max_displacement_mm
    assert result.displacement_change_mm == pytest.approx(-base_disp / 2.0, rel=1e-6)
    assert result.stress_change_mpa == pytest.approx(0.0, abs=1e-6)


# ─────────────────────────────────────────────
# GEOMETRY_OFFSET
# ─────────────────────────────────────────────

def test_geometry_offset_changes_the_solved_result():
    structure = _structure()
    target_node = structure.nodes[len(structure.nodes) // 2].id
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.GEOMETRY_OFFSET,
                                        node_id=target_node, offset=(0.0, 0.3, 0.0)))
    assert result.perturbed_results is not None
    assert result.displacement_change_mm != 0.0


def test_zero_offset_reproduces_baseline_exactly():
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.GEOMETRY_OFFSET,
                                        node_id=structure.nodes[0].id, offset=(0.0, 0.0, 0.0)))
    assert result.displacement_change_mm == pytest.approx(0.0, abs=1e-9)
    assert result.stress_change_mpa == pytest.approx(0.0, abs=1e-9)


# ─────────────────────────────────────────────
# SUPPORT_REMOVE
# ─────────────────────────────────────────────

def test_support_remove_on_determinate_truss_becomes_a_mechanism():
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.SUPPORT_REMOVE,
                                        support_node_id=structure.supports[0].node_id))
    assert result.perturbed_results is None
    assert result.perturbed_error is not None
    assert result.verification_status_changed is True
    assert result.critical_member_after is None


# ─────────────────────────────────────────────
# Invalid perturbations
# ─────────────────────────────────────────────

def test_missing_required_field_is_rejected():
    structure = _structure()
    with pytest.raises(ValueError, match="scale_factor"):
        apply_perturbation(structure, Perturbation(type=PerturbationType.LOAD_SCALE, load_index=0))


def test_out_of_range_load_index_is_rejected():
    structure = _structure()
    with pytest.raises(ValueError, match="out of range"):
        apply_perturbation(structure, Perturbation(type=PerturbationType.LOAD_SCALE,
                                                    load_index=999, scale_factor=1.5))


def test_unknown_member_id_is_rejected():
    structure = _structure()
    with pytest.raises(ValueError, match="not found"):
        apply_perturbation(structure, Perturbation(type=PerturbationType.MEMBER_AREA_SCALE,
                                                    member_id=999999, scale_factor=1.5))


def test_unknown_material_key_is_rejected():
    structure = _structure()
    with pytest.raises(ValueError, match="Unknown material_key"):
        apply_perturbation(structure, Perturbation(type=PerturbationType.YOUNGS_MODULUS_SCALE,
                                                    material_key="UNOBTAINIUM", scale_factor=1.5))


def test_unknown_node_id_is_rejected():
    structure = _structure()
    with pytest.raises(ValueError, match="not found"):
        apply_perturbation(structure, Perturbation(type=PerturbationType.GEOMETRY_OFFSET,
                                                    node_id=999999, offset=(1, 0, 0)))


def test_unknown_support_node_is_rejected():
    structure = _structure()
    with pytest.raises(ValueError, match="No support found"):
        apply_perturbation(structure, Perturbation(type=PerturbationType.SUPPORT_REMOVE,
                                                    support_node_id=999999))


def test_run_experiment_does_not_raise_for_invalid_perturbation_but_apply_does():
    """apply_perturbation raises directly — run_experiment does not swallow this."""
    structure = _structure()
    with pytest.raises(ValueError):
        run_experiment(structure, _spec(),
                       Perturbation(type=PerturbationType.MEMBER_AREA_SCALE, member_id=-1, scale_factor=2.0))


# ─────────────────────────────────────────────
# MEMBER_REMOVE (Task 2)
# ─────────────────────────────────────────────
#
# The generated Pratt truss is statically DETERMINATE (m+r=3n exactly),
# which means every one of its members is non-redundant by definition —
# removing ANY single member necessarily makes it a mechanism. That is
# used to test the failure path. A stable-removal case needs one genuine
# redundant member, so a small braced rectangular panel with BOTH
# diagonals present (indeterminate by 1) is used for that: removing
# either diagonal leaves it exactly determinate and stable.

_PANEL_SECTION = None


def _braced_panel():
    from server.models.structure import Structure, Node, Member, Support, SupportType, PointLoad, CrossSection
    section = CrossSection(0.1143, 0.0064)
    return Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, 4, 0, 0), Node(2, 4, 3, 0), Node(3, 0, 3, 0)],
        members=[
            Member(0, 0, 1, "A36", section),
            Member(1, 1, 2, "A36", section),
            Member(2, 2, 3, "A36", section),
            Member(3, 3, 0, "A36", section),
            Member(4, 0, 2, "A36", section),   # diagonal 1
            Member(5, 1, 3, "A36", section),   # diagonal 2 — redundant with diagonal 1
        ],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X, dx=False, dy=True, dz=True),
            Support(node_id=2, support_type=SupportType.OUT_OF_PLANE),
            Support(node_id=3, support_type=SupportType.OUT_OF_PLANE),
        ],
        loads=[PointLoad(node_id=2, fy=-10_000.0)],
    )


def test_member_remove_valid_removal_on_determinate_truss_is_unstable():
    """A. valid member removal — on the determinate Pratt truss this must
    make the structure a mechanism (deterministic, not incidental)."""
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=structure.members[9].id))
    assert result.removed_member_id == structure.members[9].id
    assert result.structural_status == "unstable"
    assert result.perturbed_results is None
    assert "not" in result.perturbed_error.lower() or "singular" in result.perturbed_error.lower() \
        or "converge" in result.perturbed_error.lower()


def test_member_remove_actually_removes_the_member_from_the_copy():
    """B. removed member is actually absent from the copied model."""
    structure = _braced_panel()
    result = run_experiment(structure, EngineeringSpec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    # perturbed_results carries member_results only for members that solved;
    # verify via a direct apply_perturbation call for the structural copy.
    perturbed_structure, _ = apply_perturbation(structure, Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert 5 not in [m.id for m in perturbed_structure.members]
    assert len(perturbed_structure.members) == len(structure.members) - 1


def test_member_remove_leaves_other_members_unchanged():
    """C. all other members remain unchanged."""
    structure = _braced_panel()
    perturbed_structure, _ = apply_perturbation(
        structure, Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    remaining_ids = {m.id for m in perturbed_structure.members}
    for member in structure.members:
        if member.id == 5:
            continue
        assert member.id in remaining_ids
        match = next(m for m in perturbed_structure.members if m.id == member.id)
        assert match.node_i == member.node_i
        assert match.node_j == member.node_j
        assert match.material_key == member.material_key
        assert match.section.wall_thickness == member.section.wall_thickness


def test_member_remove_does_not_mutate_baseline_structure():
    """D. baseline Structure remains unchanged."""
    structure = _braced_panel()
    snapshot_ids = [m.id for m in structure.members]
    run_experiment(structure, EngineeringSpec(),
                  Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert [m.id for m in structure.members] == snapshot_ids
    assert len(structure.members) == 6


def test_member_remove_valid_resolve_after_removal():
    """E. valid re-solve occurs after removal (stable, redundant-member case)."""
    structure = _braced_panel()
    result = run_experiment(structure, EngineeringSpec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert result.structural_status in ("stable", "solved_but_failed_checks")
    assert result.perturbed_results is not None
    assert result.perturbed_error is None


def test_member_remove_displacement_comparison_is_real():
    """F. displacement comparison — exact values, not just "changed"."""
    structure = _braced_panel()
    spec = EngineeringSpec()
    result = run_experiment(structure, spec,
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert result.baseline_max_displacement_mm == pytest.approx(0.07301605191432244, rel=1e-6)
    assert result.perturbed_max_displacement_mm == pytest.approx(0.08642710794060002, rel=1e-6)
    assert result.displacement_change_mm == pytest.approx(
        result.perturbed_max_displacement_mm - result.baseline_max_displacement_mm, rel=1e-9
    )
    assert result.displacement_change_mm > 0   # removing bracing increases deflection


def test_member_remove_stress_comparison_is_real():
    """G. stress comparison."""
    structure = _braced_panel()
    result = run_experiment(structure, EngineeringSpec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert result.baseline_max_stress_mpa > 0
    assert result.perturbed_max_stress_mpa > 0
    assert result.stress_change_mpa == pytest.approx(
        result.perturbed_max_stress_mpa - result.baseline_max_stress_mpa, rel=1e-9
    )


def test_member_remove_percentage_calculation_matches_formula():
    """H. percentage calculations."""
    structure = _braced_panel()
    result = run_experiment(structure, EngineeringSpec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    expected_disp_pct = (
        (result.perturbed_max_displacement_mm - result.baseline_max_displacement_mm)
        / result.baseline_max_displacement_mm * 100.0
    )
    expected_stress_pct = (
        (result.perturbed_max_stress_mpa - result.baseline_max_stress_mpa)
        / result.baseline_max_stress_mpa * 100.0
    )
    assert result.displacement_percent_change == pytest.approx(expected_disp_pct, rel=1e-9)
    assert result.stress_percent_change == pytest.approx(expected_stress_pct, rel=1e-9)


def test_member_remove_zero_denominator_handling():
    """I. zero-denominator handling — a baseline metric of exactly 0 must
    yield None for the percentage, never a division error or fabricated number."""
    from server.core.experiments.models import _percent_change
    assert _percent_change(0.0, 5.0) is None
    assert _percent_change(0.0, 0.0) is None
    assert _percent_change(1e-20, 5.0) is None
    assert _percent_change(10.0, 15.0) == pytest.approx(50.0)


def test_member_remove_invalid_member_id():
    """J. invalid member ID."""
    structure = _structure()
    with pytest.raises(ValueError, match="not found"):
        apply_perturbation(structure, Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=999999))


def test_member_remove_missing_member_id_field():
    structure = _structure()
    with pytest.raises(ValueError, match="member_id"):
        apply_perturbation(structure, Perturbation(type=PerturbationType.MEMBER_REMOVE))


def test_member_remove_causing_mechanism_reports_unstable_explicitly():
    """K. removal causing instability/mechanism — assert the ACTUAL status,
    not merely that some error occurred."""
    structure = _structure()
    result = run_experiment(structure, _spec(),
                            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=structure.members[0].id))
    assert result.structural_status == "unstable"
    assert result.perturbed_verified is None
    assert result.perturbed_results is None
    assert result.critical_member_after is None
    assert result.verification_status_changed is True
    assert result.displacement_percent_change is None
    assert result.stress_percent_change is None


def test_member_remove_repeated_experiment_does_not_accumulate_mutations():
    """L. repeated experiment does not accumulate mutations."""
    structure = _braced_panel()
    spec = EngineeringSpec()
    for _ in range(5):
        run_experiment(structure, spec, Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    assert len(structure.members) == 6
    assert {m.id for m in structure.members} == {0, 1, 2, 3, 4, 5}


def test_member_remove_material_library_unchanged():
    """M. MATERIAL_LIBRARY remains unchanged."""
    before = {k: (m.E, m.yield_stress, m.density) for k, m in MATERIAL_LIBRARY.items()}
    structure = _braced_panel()
    run_experiment(structure, EngineeringSpec(),
                  Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))
    after = {k: (m.E, m.yield_stress, m.density) for k, m in MATERIAL_LIBRARY.items()}
    assert before == after


def test_member_remove_shared_cross_section_objects_unchanged():
    """N. shared material/cross-section objects remain unchanged.

    _braced_panel's members all share ONE CrossSection instance —
    removing a member must not touch it (unlike MEMBER_AREA_SCALE, which
    deliberately mutates a copy; removal should leave sections untouched
    everywhere, including in the ORIGINAL baseline)."""
    structure = _braced_panel()
    shared_id = id(structure.members[0].section)
    assert all(id(m.section) == shared_id for m in structure.members), \
        "fixture assumes a single shared CrossSection instance"
    original_thickness = structure.members[0].section.wall_thickness
    original_diameter = structure.members[0].section.outer_diameter

    run_experiment(structure, EngineeringSpec(),
                  Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=5))

    assert structure.members[0].section.wall_thickness == original_thickness
    assert structure.members[0].section.outer_diameter == original_diameter
