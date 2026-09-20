"""
Steel truss experimental case — geometry reconstruction correctness.

These tests do not require the dataset xlsx file (they test the
reconstructed model itself, not the comparison against measurements).
"""
import pytest

from server.validation.cases import steel_truss_loss_of_chord as case
from server.core.fea.solver import solve, FEASolverError


def test_geometry_has_correct_span_and_height():
    structure, idx = case.build_structure()
    xs = [n.x for n in structure.nodes]
    ys = [n.y for n in structure.nodes]
    assert max(xs) - min(xs) == pytest.approx(case.SPAN_M)
    assert max(ys) - min(ys) == pytest.approx(case.HEIGHT_M)


def test_geometry_is_planar():
    """This case models a single truss plane — every node must have z=0."""
    structure, _ = case.build_structure()
    assert all(n.z == 0.0 for n in structure.nodes)


def test_node_count_matches_thirteen_panel_points_per_chord():
    structure, idx = case.build_structure()
    assert len(structure.nodes) == 2 * (case.N_PANELS + 1)


def test_supports_are_hinged_and_roller_as_documented():
    structure, idx = case.build_structure()
    supports = {s.node_id: s for s in structure.supports}
    hinge = supports[idx["bottom_0"]]
    roller = supports[idx["bottom_12"]]
    assert (hinge.dx, hinge.dy, hinge.dz) == (True, True, True)
    assert (roller.dx, roller.dy, roller.dz) == (False, True, True)


def test_applied_load_totals_eighty_kilonewtons_on_this_truss_plane():
    """Load Setup-1: 4 x 20kN total across both trusses = 40kN on one plane."""
    structure, idx = case.build_structure()
    total = sum(-l.fy for l in structure.loads)
    assert total == pytest.approx(2 * 20_000.0)


def test_cross_section_areas_match_table_2_exactly():
    structure, idx = case.build_structure()
    member_map = structure.member_dict()
    # First bottom-chord segment is C1 (area 8.4 cm^2 = 8.4e-4 m^2)
    assert member_map[0].section.area == pytest.approx(8.4e-4)
    # Mid-span vertical (node 6) is M5 (area 1.7 cm^2)
    vertical_at_midspan = next(
        m for m in structure.members
        if idx["bottom_6"] in (m.node_i, m.node_j) and idx["top_6"] in (m.node_i, m.node_j)
    )
    assert vertical_at_midspan.section.area == pytest.approx(1.7e-4)


def test_material_matches_figure_4_coupon():
    from server.models.structure import MATERIAL_LIBRARY
    mat = MATERIAL_LIBRARY[case.MATERIAL_KEY]
    assert mat.E == pytest.approx(207_639.8e6)
    assert mat.yield_stress == pytest.approx(326.6e6)


def test_reconstructed_structure_solves_without_mechanism():
    """A faithful reconstruction of a real, built, tested bridge must not
    be an unstable mechanism in NeuroPlan's solver."""
    structure, idx = case.build_structure()
    spec = case.build_spec()
    results = solve(structure, spec)
    assert results.equilibrium.passed
    assert results.equilibrium.relative_residual < 1e-9


def test_solver_reactions_balance_the_applied_load():
    structure, idx = case.build_structure()
    spec = case.build_spec()
    results = solve(structure, spec)
    total_ry = sum(r.ry for r in results.reactions)
    applied = sum(-l.fy for l in structure.loads)
    assert total_ry == pytest.approx(applied, rel=1e-6)


def test_case_metadata_is_populated_with_real_dataset_citation():
    built = case.build_case()
    assert built.dataset.doi == "10.5281/zenodo.15658671"
    assert "CC-BY" in built.dataset.license
    assert built.applicable is True


def test_case_declares_every_derived_or_assumed_parameter():
    """Every non-SOURCED input must be visibly logged, not silently used."""
    built = case.build_case()
    joined = " ".join(built.parameter_notes).lower()
    assert "derived" in joined
    assert "assumed" in joined
    assert "load application nodes" in joined  # the load-position uncertainty
    assert "sensor-to-node mapping" in joined  # the mapping uncertainty


def test_sensor_mappings_flag_midspan_as_high_confidence():
    from server.validation.models import ParameterStatus
    mappings = case.build_sensor_mappings()
    midspan = next(m for m in mappings if m.sensor_id == "4")
    assert midspan.status is ParameterStatus.SOURCED
    assert midspan.node_id == 6

    outer = next(m for m in mappings if m.sensor_id == "1")
    assert outer.status is ParameterStatus.ASSUMED
