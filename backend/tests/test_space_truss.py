"""
NeuroPlan-3D — Spatial Generator Tests

Checks that the space truss is genuinely three-dimensional rather than a
planar truss with decorative z-coordinates, and that it is spatially stable
through its own members.
"""
import pytest

from server.models.structure import EngineeringSpec, StructureType, SupportType
from server.core.generator.space_truss import generate_space_truss
from server.core.generator.topology import generate_structure
from server.core.fea.solver import solve
from server.core.fea.elements import direction_cosines


def _spec(**overrides) -> EngineeringSpec:
    base = dict(
        structure_type=StructureType.SPACE_TRUSS,
        span=20.0, height=2.5, width=4.0, num_panels=6,
        primary_load=50000.0, section_key="CHS_168x6",
    )
    base.update(overrides)
    return EngineeringSpec(**base)


def test_space_truss_occupies_two_distinct_z_planes():
    """Truss planes sit symmetrically about z=0 at ±width/2."""
    structure = generate_space_truss(_spec())
    z_values = {round(n.z, 6) for n in structure.nodes}
    assert z_values == {-2.0, 2.0}
    assert len(structure.nodes) == 4 * (6 + 1)  # four chords × (panels+1)


def test_space_truss_has_genuinely_three_dimensional_members():
    """
    The decisive check: members whose direction cosines have TWO OR MORE
    non-zero components. A planar truss can never produce these — every one
    of its members has lz = 0 exactly.
    """
    structure = generate_space_truss(_spec())
    node_map = structure.node_dict()

    multi_axis = 0
    has_z_component = 0
    for member in structure.members:
        lx, ly, lz, _ = direction_cosines(node_map[member.node_i], node_map[member.node_j])
        non_zero = sum(1 for c in (lx, ly, lz) if abs(c) > 1e-9)
        if non_zero >= 2:
            multi_axis += 1
        if abs(lz) > 1e-9:
            has_z_component += 1

    assert has_z_component > 0, "no member has any z component — this is not a 3D structure"
    assert multi_axis > 0, "no member spans multiple axes"
    # Plan bracing (dx+dz) and portal bracing (dy+dz) must both be present.
    assert multi_axis >= 12


def test_space_truss_needs_no_artificial_out_of_plane_bracing():
    """
    The planar generators must add OUT_OF_PLANE bracing supports at nearly
    every node to avoid a singular matrix. A genuine space truss is stable
    through its own members and needs none — this is the structural proof
    that the geometry is really spatial.
    """
    structure = generate_space_truss(_spec())
    bracing = [s for s in structure.supports if s.support_type == SupportType.OUT_OF_PLANE]
    assert bracing == []
    assert len(structure.supports) == 4  # four bearings only

    # And it still solves.
    results = solve(structure, _spec())
    assert results.is_spatial is True
    assert results.equilibrium.passed


def test_space_truss_restraints_suppress_all_rigid_body_modes():
    """7 restraints against 6 rigid-body modes: stable, 1 redundancy."""
    structure = generate_space_truss(_spec())
    restraint_count = sum(s.dx + s.dy + s.dz for s in structure.supports)
    assert restraint_count == 7
    # Stability is what actually matters — the solver's mechanism check
    # passes only if all six rigid-body modes are genuinely suppressed.
    assert solve(structure, _spec()) is not None


def test_space_truss_rejects_zero_width():
    """A zero-width space truss would collapse to a plane — reject it."""
    with pytest.raises(ValueError, match="width > 0"):
        generate_space_truss(_spec(width=0.0))


def test_vertical_load_is_shared_between_both_trusses():
    structure = generate_space_truss(_spec(load_description="center point load"))
    total_fy = sum(l.fy for l in structure.loads)
    assert total_fy == pytest.approx(-50000.0, rel=1e-9)
    # Applied to both the front (z=0) and back (z=width) chords.
    node_map = structure.node_dict()
    loaded_z = {round(node_map[l.node_id].z, 6) for l in structure.loads}
    assert loaded_z == {-2.0, 2.0}


def test_lateral_loads_are_not_discarded():
    structure = generate_space_truss(_spec(lateral_load_x=8000.0, lateral_load_z=12000.0))
    assert sum(l.fx for l in structure.loads) == pytest.approx(8000.0, rel=1e-9)
    assert sum(l.fz for l in structure.loads) == pytest.approx(12000.0, rel=1e-9)


def test_transverse_load_produces_out_of_plane_response():
    """
    A pure z (wind) load must produce real z displacements. In a planar
    system this load would either be discarded or trigger a mechanism.
    """
    spec = _spec(primary_load=1.0, lateral_load_z=40000.0)
    structure = generate_space_truss(spec)
    results = solve(structure, spec)

    max_dz = max(abs(r.dz) for r in results.node_results)
    assert max_dz > 1e-6, "transverse load produced no out-of-plane displacement"
    assert results.equilibrium.passed


def test_generate_structure_dispatches_space_truss():
    """The public dispatch entry point must route SPACE_TRUSS correctly."""
    structure = generate_structure(_spec())
    assert any(abs(n.z) > 1e-9 for n in structure.nodes)


def test_space_truss_scales_with_panel_count():
    for panels in (4, 6, 8, 10):
        spec = _spec(num_panels=panels)
        structure = generate_space_truss(spec)
        assert len(structure.nodes) == 4 * (panels + 1)
        results = solve(structure, spec)
        assert results.equilibrium.passed, f"equilibrium failed at {panels} panels"
