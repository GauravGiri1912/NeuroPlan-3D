"""
NeuroPlan-3D — Evidence & Traceability Tests

The claim this feature makes is that no displayed number is unattributable
and none is invented. These tests hold it to that: every provenance value
and every verification figure must be traceable to the solver output it
claims to come from, and must move when the inputs move.
"""
import copy
import math
import pytest

from server.models.structure import EngineeringSpec, StructureType, MATERIAL_LIBRARY
from server.models.evidence import CheckStatus, EvidenceCategory
from server.core.generator.topology import generate_structure
from server.core.fea.solver import solve
from server.core.evidence import (
    build_provenance, build_verification_items, run_benchmarks,
    get_assumptions, build_simulation_record, build_load_paths,
    SOFTWARE_VERSION,
)

PLANAR = EngineeringSpec(
    structure_type=StructureType.PRATT, span=20.0, height=3.33, num_panels=8,
    primary_load=50000.0, material_key="A36", section_key="CHS_114x6",
)
SPATIAL = EngineeringSpec(
    structure_type=StructureType.SPACE_TRUSS, span=24.0, height=2.5, width=4.0,
    num_panels=8, primary_load=80000.0, lateral_load_z=15000.0,
    load_description="distributed load", material_key="A36", section_key="CHS_168x6",
)


def _run(spec):
    structure = generate_structure(spec)
    return structure, solve(structure, spec)


# ── Provenance values must equal solver values ────────────────────────

@pytest.mark.parametrize("spec", [PLANAR, SPATIAL], ids=["planar", "spatial"])
def test_provenance_max_stress_equals_solver_member_stress(spec):
    structure, results = _run(copy.deepcopy(spec))
    prov = {p.metric: p for p in build_provenance(structure, results, spec)}

    entry = prov["max_stress"]
    member_result = next(
        m for m in results.member_results if m.member_id == entry.source_id
    )
    # The reported value must BE the solver's value for the named member.
    assert entry.value == member_result.stress
    # And that member must genuinely be the extreme one.
    assert abs(member_result.stress) == max(abs(m.stress) for m in results.member_results)


@pytest.mark.parametrize("spec", [PLANAR, SPATIAL], ids=["planar", "spatial"])
def test_provenance_max_displacement_equals_solver_node_displacement(spec):
    structure, results = _run(copy.deepcopy(spec))
    prov = {p.metric: p for p in build_provenance(structure, results, spec)}

    entry = prov["max_displacement"]
    node_result = next(n for n in results.node_results if n.node_id == entry.source_id)
    assert entry.value == pytest.approx(node_result.total_displacement, rel=1e-12)
    assert node_result.total_displacement == max(
        n.total_displacement for n in results.node_results
    )
    # The recorded UX/UY/UZ inputs must be that node's actual components.
    values = {i.label: i.value for i in entry.inputs}
    assert values["UX"] == node_result.dx
    assert values["UY"] == node_result.dy
    assert values["UZ"] == node_result.dz


def test_provenance_stress_equation_reproduces_reported_value():
    """σ = N/A must actually reproduce the reported stress from its own inputs."""
    structure, results = _run(copy.deepcopy(SPATIAL))
    entry = next(p for p in build_provenance(structure, results, SPATIAL) if p.metric == "max_stress")
    inputs = {i.label.split(" ")[0]: i.value for i in entry.inputs}
    assert inputs["N"] / inputs["A"] == pytest.approx(entry.value, rel=1e-9)


def test_provenance_reaction_equals_solver_reaction():
    structure, results = _run(copy.deepcopy(SPATIAL))
    entry = next(p for p in build_provenance(structure, results, SPATIAL) if p.metric == "max_reaction")
    reaction = next(r for r in results.reactions if r.node_id == entry.source_id)
    expected = math.sqrt(reaction.rx**2 + reaction.ry**2 + reaction.rz**2)
    assert entry.value == pytest.approx(expected, rel=1e-12)


def test_provenance_node_coordinates_match_generated_geometry():
    structure, results = _run(copy.deepcopy(SPATIAL))
    entry = next(p for p in build_provenance(structure, results, SPATIAL) if p.metric == "max_displacement")
    node = next(n for n in structure.nodes if n.id == entry.source_id)
    # The coordinates quoted in the provenance text are the generated ones.
    assert f"{node.x:.3f}" in entry.source_detail
    assert f"{node.y:.3f}" in entry.source_detail
    assert f"{node.z:.3f}" in entry.source_detail


# ── Verification evidence must come from the actual checks ────────────

@pytest.mark.parametrize("spec", [PLANAR, SPATIAL], ids=["planar", "spatial"])
def test_verification_values_match_solver_state(spec):
    structure, results = _run(copy.deepcopy(spec))
    items = {v.key: v for v in build_verification_items(structure, results, spec)}

    assert items["equilibrium_x"].actual_value == results.equilibrium.residual_fx
    assert items["equilibrium_y"].actual_value == results.equilibrium.residual_fy
    assert items["equilibrium_z"].actual_value == results.equilibrium.residual_fz
    assert items["moment_equilibrium_x"].actual_value == results.equilibrium.residual_mx
    assert items["moment_equilibrium_y"].actual_value == results.equilibrium.residual_my
    assert items["moment_equilibrium_z"].actual_value == results.equilibrium.residual_mz
    assert items["numerical_residual"].actual_value == results.equilibrium.relative_residual
    assert items["stress_limit"].actual_value == results.diagnosis.max_stress_ratio
    assert items["displacement_limit"].actual_value == results.diagnosis.max_displacement_mm
    assert items["dof_model"].actual_value == float(results.dof_count)
    assert items["geometry_nodes"].actual_value == float(len(structure.nodes))


def test_every_verification_item_carries_its_evidence():
    """No bare status: each item must state a value, a source and units."""
    structure, results = _run(copy.deepcopy(SPATIAL))
    for item in build_verification_items(structure, results, SPATIAL):
        assert item.actual_display, f"{item.key} has no actual value displayed"
        assert item.label, f"{item.key} has no label"
        if item.status in (CheckStatus.PASS, CheckStatus.FAIL):
            assert item.source and item.source != "—", f"{item.key} has no source"


def test_real_world_validation_is_reported_not_available():
    """It must never read as a pass — the capability does not exist."""
    structure, results = _run(copy.deepcopy(SPATIAL))
    item = next(
        v for v in build_verification_items(structure, results, SPATIAL)
        if v.key == "real_world_validation"
    )
    assert item.status is CheckStatus.NOT_AVAILABLE
    assert item.category is EvidenceCategory.REAL_WORLD
    assert "not performed" in item.actual_display.lower()


def test_iterative_convergence_is_info_not_a_pass():
    """A direct solver has no iteration to converge — say so, don't claim PASS."""
    structure, results = _run(copy.deepcopy(SPATIAL))
    item = next(
        v for v in build_verification_items(structure, results, SPATIAL)
        if v.key == "iterative_convergence"
    )
    assert item.status is CheckStatus.INFO


# ── Evidence must change when the model changes ───────────────────────

def test_changing_the_load_changes_the_evidence():
    """Provenance is computed per-run, not cached or hard-coded."""
    light = copy.deepcopy(SPATIAL)
    heavy = copy.deepcopy(SPATIAL)
    heavy.primary_load = SPATIAL.primary_load * 3.0

    s_light, r_light = _run(light)
    s_heavy, r_heavy = _run(heavy)

    p_light = {p.metric: p.value for p in build_provenance(s_light, r_light, light)}
    p_heavy = {p.metric: p.value for p in build_provenance(s_heavy, r_heavy, heavy)}

    assert abs(p_heavy["max_stress"]) > abs(p_light["max_stress"])
    assert p_heavy["max_displacement"] > p_light["max_displacement"]
    assert p_heavy["max_reaction"] > p_light["max_reaction"]


def test_planar_and_spatial_produce_different_evidence():
    s_p, r_p = _run(copy.deepcopy(PLANAR))
    s_s, r_s = _run(copy.deepcopy(SPATIAL))

    items_p = {v.key: v for v in build_verification_items(s_p, r_p, PLANAR)}
    items_s = {v.key: v for v in build_verification_items(s_s, r_s, SPATIAL)}

    assert items_p["dof_model"].actual_value != items_s["dof_model"].actual_value
    assert items_p["geometry_nodes"].actual_value != items_s["geometry_nodes"].actual_value


# ── Benchmarks must be genuinely independent ──────────────────────────

def test_benchmarks_match_hand_derived_reference_values():
    """
    These references are derived by hand in the benchmark's own docstring.
    They must not be this solver's recorded output.
    """
    comparisons = run_benchmarks()
    assert len(comparisons) >= 5
    for b in comparisons:
        assert b.status is CheckStatus.PASS, (
            f"{b.quantity}: NeuroPlan={b.neuroplan_value} vs reference={b.reference_value} "
            f"(rel diff {b.relative_difference:.2e})"
        )
        assert b.reference_source, "a benchmark must name where its reference comes from"
        assert b.relative_difference <= b.tolerance_relative


def test_benchmark_reference_values_are_independent_constants():
    """
    Spot-check that the reference numbers are the hand-derived closed forms,
    not whatever the solver happened to produce.
    """
    by_quantity = {b.quantity: b for b in run_benchmarks()}
    P = 10000.0
    assert by_quantity["Bottom chord AB axial force"].reference_value == pytest.approx(3 * P / 8)
    assert by_quantity["Inclined member AC axial force"].reference_value == pytest.approx(-5 * P / 8)
    assert by_quantity["Vertical reaction at A"].reference_value == pytest.approx(P / 2)
    # δ = FL/AE with F=10kN, L=2m, A=0.002, E=200GPa → 5e-5 m
    assert by_quantity["Tip elongation"].reference_value == pytest.approx(5e-5)
    assert by_quantity["Axial stress"].reference_value == pytest.approx(5e6)


def test_benchmarks_run_live_against_the_solver():
    """Running twice must give identical results — deterministic, not recorded."""
    first = {b.quantity: b.neuroplan_value for b in run_benchmarks()}
    second = {b.quantity: b.neuroplan_value for b in run_benchmarks()}
    assert first == second


# ── Assumptions must reflect the real implementation ──────────────────

def test_assumptions_disclose_that_self_weight_is_not_applied():
    """
    total_weight() is reported but never added to the load vector — a
    reader could easily assume otherwise, so it must be disclosed.
    """
    assumptions = {a.topic: a for a in get_assumptions()}
    self_weight = assumptions["Self-weight / dead load"]
    assert self_weight.modeled is False
    assert "not applied" in self_weight.description.lower()


def test_assumptions_describe_buckling_as_partial():
    assumptions = {a.topic: a for a in get_assumptions()}
    buckling = assumptions["Buckling (full treatment)"]
    assert buckling.modeled is False
    assert "euler" in buckling.description.lower()


def test_assumptions_list_both_modeled_and_unmodeled():
    assumptions = get_assumptions()
    assert any(a.modeled for a in assumptions)
    assert any(not a.modeled for a in assumptions)
    for a in assumptions:
        assert a.description, f"{a.topic} has no description"


# ── Load paths must be real and verifiable ────────────────────────────

@pytest.mark.parametrize("spec", [PLANAR, SPATIAL], ids=["planar", "spatial"])
def test_load_path_exists_for_every_applied_load(spec):
    structure, results = _run(copy.deepcopy(spec))
    paths = build_load_paths(structure, results)
    assert len(paths) == len(structure.loads)
    assert {p.node_id for p in paths} == {l.node_id for l in structure.loads}


@pytest.mark.parametrize("spec", [PLANAR, SPATIAL], ids=["planar", "spatial"])
def test_load_path_joint_equilibrium_holds(spec):
    """
    The check that makes a load path meaningful: at the loaded joint, the
    applied force plus every connected member's contribution must cancel.
    """
    structure, results = _run(copy.deepcopy(spec))
    for path in build_load_paths(structure, results):
        assert path.joint_equilibrium_passed, (
            f"node {path.node_id}: relative residual {path.joint_relative_residual:.3e}"
        )
        assert path.joint_relative_residual < 1e-9


def test_load_path_member_forces_equal_solver_forces():
    structure, results = _run(copy.deepcopy(SPATIAL))
    by_member = {m.member_id: m for m in results.member_results}
    for path in build_load_paths(structure, results):
        for m in path.members:
            assert m.axial_force == by_member[m.member_id].axial_force
            assert m.stress == by_member[m.member_id].stress


def test_load_path_members_are_actually_connected_to_the_joint():
    structure, results = _run(copy.deepcopy(SPATIAL))
    for path in build_load_paths(structure, results):
        for lpm in path.members:
            member = next(m for m in structure.members if m.id == lpm.member_id)
            assert path.node_id in (member.node_i, member.node_j)
            # The "other" node must be the far end.
            expected_other = member.node_j if member.node_i == path.node_id else member.node_i
            assert lpm.other_node_id == expected_other


def test_load_path_force_contribution_equals_force_times_direction_cosine():
    """F_on_joint = N · c must hold exactly for every listed member."""
    structure, results = _run(copy.deepcopy(SPATIAL))
    for path in build_load_paths(structure, results):
        for m in path.members:
            lx, ly, lz = m.direction_cosines
            assert m.fx_on_joint == pytest.approx(m.axial_force * lx, rel=1e-12, abs=1e-9)
            assert m.fy_on_joint == pytest.approx(m.axial_force * ly, rel=1e-12, abs=1e-9)
            assert m.fz_on_joint == pytest.approx(m.axial_force * lz, rel=1e-12, abs=1e-9)
            # Direction cosines must be a unit vector.
            assert lx * lx + ly * ly + lz * lz == pytest.approx(1.0, rel=1e-12)


def test_load_path_applied_force_equals_the_actual_load():
    structure, results = _run(copy.deepcopy(SPATIAL))
    loads = {l.node_id: l for l in structure.loads}
    for path in build_load_paths(structure, results):
        load = loads[path.node_id]
        assert path.applied_fx == load.fx
        assert path.applied_fy == load.fy
        assert path.applied_fz == load.fz


def test_load_path_carries_the_transverse_wind_component():
    """
    With a Z load applied, at least one member at the joint must carry a
    Z contribution — otherwise the wind is not actually being transferred.
    """
    structure, results = _run(copy.deepcopy(SPATIAL))
    paths = build_load_paths(structure, results)
    windy = [p for p in paths if abs(p.applied_fz) > 1e-9]
    assert windy, "expected loads with a Z component"
    for path in windy:
        assert any(abs(m.fz_on_joint) > 1e-6 for m in path.members)


# ── Simulation record must match the actual run ───────────────────────

@pytest.mark.parametrize("spec", [PLANAR, SPATIAL], ids=["planar", "spatial"])
def test_simulation_record_matches_the_actual_run(spec):
    structure, results = _run(copy.deepcopy(spec))
    record = build_simulation_record(structure, results, spec, iteration_count=1)

    assert record.node_count == len(structure.nodes)
    assert record.member_count == len(structure.members)
    assert record.total_dof == results.dof_count
    assert record.dof_per_node == 3
    assert record.support_count == len(structure.supports)
    assert record.load_count == len(structure.loads)
    assert record.software_version == SOFTWARE_VERSION
    assert record.material_keys == sorted({m.material_key for m in structure.members})
    assert record.simulation_id
    assert record.timestamp_utc


def test_simulation_record_ids_are_unique_per_run():
    structure, results = _run(copy.deepcopy(SPATIAL))
    a = build_simulation_record(structure, results, SPATIAL, 1)
    b = build_simulation_record(structure, results, SPATIAL, 1)
    assert a.simulation_id != b.simulation_id


def test_simulation_record_always_warns_about_scope():
    structure, results = _run(copy.deepcopy(SPATIAL))
    record = build_simulation_record(structure, results, SPATIAL, 1)
    joined = " ".join(record.warnings).lower()
    assert "self-weight" in joined
    assert "validation" in joined
