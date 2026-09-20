"""
NeuroPlan-3D — Demo Preset Regression Tests

These lock in the exact payloads the UI's demo buttons send, because a real
regression shipped here once: Demo 3 silently rendered a planar Pratt truss.
The root cause was a stale backend whose dispatcher coerced an unknown
structure_type to PRATT instead of rejecting it — so these tests assert not
just that the models are correct, but that they are *different from each
other* and that silent substitution cannot happen.

Every assertion below is on real solver/generator output.
"""
import copy
import pytest

from server.models.structure import EngineeringSpec, StructureType
from server.core.generator.topology import generate_structure
from server.core.generator.space_truss import assert_is_genuinely_spatial
from server.core.fea.solver import solve
from server.core.fea.elements import direction_cosines

EPS = 1e-9

# Mirrors of the UI demo preset payloads (SpecificationPanel.tsx).
DEMO_1 = EngineeringSpec(
    structure_type=StructureType.PRATT,
    span=20.0, height=3.3333333333333335, num_panels=8,
    primary_load=50000.0, load_description="center point load",
    material_key="A36", section_key="CHS_114x6",
)
DEMO_3 = EngineeringSpec(
    structure_type=StructureType.SPACE_TRUSS,
    span=24.0, height=2.5, width=4.0, num_panels=8,
    primary_load=80000.0, lateral_load_z=15000.0,
    load_description="distributed load",
    material_key="A36", section_key="CHS_168x6",
)


def _dz_member_count(structure) -> int:
    node_map = structure.node_dict()
    return sum(
        1 for m in structure.members
        if abs(node_map[m.node_j].z - node_map[m.node_i].z) > EPS
    )


# ── 1. Demo 1 remains planar ──────────────────────────────────────────

def test_demo1_remains_planar_pratt():
    spec = copy.deepcopy(DEMO_1)
    assert spec.structure_type is StructureType.PRATT
    assert spec.structure_type.is_spatial is False

    structure = generate_structure(spec)
    assert all(abs(n.z) < EPS for n in structure.nodes), "Demo 1 must have every node at z=0"
    assert _dz_member_count(structure) == 0, "Demo 1 must have no members spanning z"

    results = solve(structure, spec)
    assert results.is_spatial is False


# ── 2 & 3. Demo 3 is spatial with non-zero Z extent ───────────────────

def test_demo3_is_spatial_with_meaningful_z_extent():
    spec = copy.deepcopy(DEMO_3)
    assert spec.structure_type is StructureType.SPACE_TRUSS
    assert spec.structure_type.is_spatial is True

    structure = generate_structure(spec)
    zs = [n.z for n in structure.nodes]
    z_extent = max(zs) - min(zs)

    assert z_extent == pytest.approx(spec.width, rel=1e-9), "z extent must equal the specified width"
    assert z_extent > 0.1, "Demo 3 must have a meaningful z extent"
    # Symmetric about the longitudinal axis: −W/2 .. +W/2
    assert min(zs) == pytest.approx(-spec.width / 2, rel=1e-9)
    assert max(zs) == pytest.approx(+spec.width / 2, rel=1e-9)


# ── 4. Demo 3 contains members with dz != 0 ───────────────────────────

def test_demo3_has_members_spanning_z():
    structure = generate_structure(copy.deepcopy(DEMO_3))
    dz_members = _dz_member_count(structure)
    assert dz_members > 0, "no member joins the two truss planes"
    # Transverse members alone would be 2*(panels+1)=18; bracing adds more.
    assert dz_members >= 18

    # And members spanning more than one axis at once (true 3D bracing).
    node_map = structure.node_dict()
    multi_axis = 0
    for m in structure.members:
        lx, ly, lz, _ = direction_cosines(node_map[m.node_i], node_map[m.node_j])
        if sum(1 for c in (lx, ly, lz) if abs(c) > EPS) >= 2:
            multi_axis += 1
    assert multi_axis > 0


# ── 5. Demo 3 uses 3 DOF per node ─────────────────────────────────────

def test_demo3_uses_three_dof_per_node():
    spec = copy.deepcopy(DEMO_3)
    structure = generate_structure(spec)
    results = solve(structure, spec)
    assert results.dof_count == 3 * len(structure.nodes)


# ── 6. Demo 3 accepts Fz ──────────────────────────────────────────────

def test_demo3_accepts_and_applies_fz():
    spec = copy.deepcopy(DEMO_3)
    structure = generate_structure(spec)
    applied_fz = sum(l.fz for l in structure.loads)
    assert applied_fz == pytest.approx(spec.lateral_load_z, rel=1e-9), "Fz was discarded"


# ── 7. Demo 3 produces a real spatial response to wind ────────────────

def test_demo3_wind_produces_spatial_response():
    """
    A/B on the identical structure: wind off vs. wind on. The Z response
    must change materially, and the Z reactions must balance the applied
    transverse load exactly.
    """
    spec_a = copy.deepcopy(DEMO_3)
    spec_a.lateral_load_z = 0.0
    spec_b = copy.deepcopy(DEMO_3)

    res_a = solve(generate_structure(spec_a), spec_a)
    res_b = solve(generate_structure(spec_b), spec_b)

    uz_a = max(abs(r.dz) for r in res_a.node_results)
    uz_b = max(abs(r.dz) for r in res_b.node_results)
    rz_a = sum(r.rz for r in res_a.reactions)
    rz_b = sum(r.rz for r in res_b.reactions)

    assert rz_a == pytest.approx(0.0, abs=1e-6), "no wind should mean no net Z reaction"
    assert rz_b == pytest.approx(-spec_b.lateral_load_z, rel=1e-6), "Z reactions must balance the wind"
    assert uz_b > uz_a * 2, "wind must materially increase the out-of-plane displacement"

    # Member forces must actually redistribute, not just displacements move.
    f_a = {m.member_id: m.axial_force for m in res_a.member_results}
    f_b = {m.member_id: m.axial_force for m in res_b.member_results}
    changed = sum(1 for mid in f_a if abs(f_a[mid] - f_b[mid]) > 1.0)
    assert changed > 0, "wind changed no member force — it is not being carried"


# ── 8. Demo 1 still solves correctly ──────────────────────────────────

def test_demo1_still_solves_correctly():
    spec = copy.deepcopy(DEMO_1)
    results = solve(generate_structure(spec), spec)
    assert results.checks.all_passed
    assert sum(r.ry for r in results.reactions) == pytest.approx(spec.primary_load, rel=1e-6)
    assert results.equilibrium.passed


# ── 9. No silent fallback to PLANAR/PRATT ─────────────────────────────

def test_spatial_request_can_never_silently_return_planar():
    """
    The exact regression that shipped: a spatial request coming back as a
    planar Pratt truss. The dispatcher must raise instead.
    """
    spec = copy.deepcopy(DEMO_3)
    structure = generate_structure(spec)
    # Flatten it, simulating a generator that ignored the spatial request.
    for node in structure.nodes:
        node.z = 0.0
    with pytest.raises(ValueError, match="PLANAR structure"):
        assert_is_genuinely_spatial(structure)


def test_two_separated_planes_with_no_connection_is_rejected():
    """Two independent planar trusses are not one spatial structure."""
    spec = copy.deepcopy(DEMO_3)
    structure = generate_structure(spec)
    node_map = structure.node_dict()
    # Remove every member that joins the two planes.
    structure.members = [
        m for m in structure.members
        if abs(node_map[m.node_j].z - node_map[m.node_i].z) <= EPS
    ]
    with pytest.raises(ValueError, match="no member connects nodes at different z"):
        assert_is_genuinely_spatial(structure)


# ── 10. The two presets are genuinely different models ────────────────

def test_demo1_and_demo3_are_genuinely_different_models():
    s1 = generate_structure(copy.deepcopy(DEMO_1))
    s3 = generate_structure(copy.deepcopy(DEMO_3))
    r1 = solve(s1, DEMO_1)
    r3 = solve(s3, DEMO_3)

    assert len(s1.nodes) != len(s3.nodes)
    assert len(s1.members) != len(s3.members)
    assert r1.dof_count != r3.dof_count
    assert r1.is_spatial is False and r3.is_spatial is True

    z1 = max(n.z for n in s1.nodes) - min(n.z for n in s1.nodes)
    z3 = max(n.z for n in s3.nodes) - min(n.z for n in s3.nodes)
    assert z1 == pytest.approx(0.0, abs=EPS)
    assert z3 > 0.1

    assert _dz_member_count(s1) == 0
    assert _dz_member_count(s3) > 0

    # Out-of-plane response exists in one and is exactly zero in the other.
    assert max(abs(r.dz) for r in r1.node_results) == pytest.approx(0.0, abs=1e-15)
    assert max(abs(r.dz) for r in r3.node_results) > 1e-9
