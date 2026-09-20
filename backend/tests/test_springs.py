"""
Elastic spring supports.

Closed form: a single bar (axial stiffness k_member = AE/L), pinned at
one end (node0, fixed to ground), spring-supported (k_spring) at the
free end (node1). Both the member (node0->node1, with node0 = ground)
and the spring (node1->ground) connect node1 to the SAME fixed
reference — two independent load paths to ground from the same point
are springs in PARALLEL, not in series (series would require the spring
to sit between node1 and some THIRD, separately-fixed point, which this
single-node spring model does not represent):

    K[1,1] = k_member + k_spring
    u = F / (k_member + k_spring)

This was confirmed directly against the assembled stiffness matrix
(K[dof,dof] before/after adding the spring) before writing the test,
rather than assumed from an initial (incorrect, series-based) intuition.
"""
import pytest

from server.core.fea.solver import solve
from server.core.fea.springs import ElasticSupport
from server.core.generator.topology import generate_structure
from server.models.structure import (
    Structure, Node, Member, Support, SupportType, PointLoad, CrossSection,
    EngineeringSpec, MATERIAL_LIBRARY,
)

SECTION = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)
E_A36 = MATERIAL_LIBRARY["A36"].E


def _spring_bar(k_spring: float, length: float = 4.0, force: float = 20_000.0) -> Structure:
    """Pin at node0; node1 free-in-X (spring-restrained), rigid in Y/Z."""
    return Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, length, 0, 0)],
        members=[Member(0, 0, 1, "A36", SECTION)],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X, dx=False, dy=True, dz=True),
        ],
        loads=[PointLoad(node_id=1, fx=force)],
    )


def test_parallel_spring_matches_closed_form():
    length, force, k_spring = 4.0, 20_000.0, 5.0e6
    structure = _spring_bar(k_spring, length, force)
    k_member = SECTION.area * E_A36 / length

    results = solve(structure, EngineeringSpec(),
                    springs=[ElasticSupport(node_id=1, kx=k_spring)])
    u = next(n for n in results.node_results if n.node_id == 1).dx
    expected = force / (k_member + k_spring)
    assert u == pytest.approx(expected, rel=1e-9)


def test_stiffer_spring_gives_smaller_displacement():
    structure_soft = _spring_bar(1.0e6)
    structure_stiff = _spring_bar(1.0e8)
    soft = solve(structure_soft, EngineeringSpec(), springs=[ElasticSupport(node_id=1, kx=1.0e6)])
    stiff = solve(structure_stiff, EngineeringSpec(), springs=[ElasticSupport(node_id=1, kx=1.0e8)])
    u_soft = next(n for n in soft.node_results if n.node_id == 1).dx
    u_stiff = next(n for n in stiff.node_results if n.node_id == 1).dx
    assert u_stiff < u_soft


def test_infinitely_stiff_spring_drives_displacement_to_zero():
    """
    Parallel configuration (see module docstring): as k_spring -> infinity,
    u = F/(k_member + k_spring) -> 0 — an infinitely stiff spring in
    parallel with the member fully dominates and pins node1 in place,
    unlike a series spring which would instead approach F/k_member.
    """
    length, force = 4.0, 20_000.0
    k_huge = 1e16
    structure = _spring_bar(k_huge, length, force)
    results = solve(structure, EngineeringSpec(), springs=[ElasticSupport(node_id=1, kx=k_huge)])
    u = next(n for n in results.node_results if n.node_id == 1).dx
    assert u == pytest.approx(0.0, abs=1e-9)


def test_zero_spring_stiffness_is_a_no_op():
    structure = _spring_bar(0.0)
    with_zero_spring = solve(structure, EngineeringSpec(), springs=[ElasticSupport(node_id=1, kx=0.0)])
    without_springs = solve(structure, EngineeringSpec())
    u1 = next(n for n in with_zero_spring.node_results if n.node_id == 1).dx
    u2 = next(n for n in without_springs.node_results if n.node_id == 1).dx
    assert u1 == pytest.approx(u2, rel=1e-12)


def test_spring_parallel_to_a_rigid_support_has_no_effect():
    """
    A rigid restraint must dominate a parallel spring, not combine with
    it. node1 is fully PIN-fixed (zero free DOF there); node0 carries the
    load through the member. Adding a spring at the already-fully-rigid
    node1 must change nothing, since every one of its DOFs is eliminated
    regardless of what is added to their diagonal.
    """
    structure = Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, 4.0, 0, 0)],
        members=[Member(0, 0, 1, "A36", SECTION)],
        supports=[
            Support(node_id=0, support_type=SupportType.ROLLER_X, dx=False, dy=True, dz=True),
            Support(node_id=1, support_type=SupportType.PIN),   # fully rigid
        ],
        loads=[PointLoad(node_id=0, fx=15_000.0)],
    )
    with_spring = solve(structure, EngineeringSpec(),
                        springs=[ElasticSupport(node_id=1, kx=1e9, ky=1e9, kz=1e9)])
    without_spring = solve(structure, EngineeringSpec())
    for a, b in zip(with_spring.node_results, without_spring.node_results):
        assert a.dx == pytest.approx(b.dx, abs=1e-15)
        assert a.dy == pytest.approx(b.dy, abs=1e-15)


def test_spring_at_unknown_node_is_rejected():
    from server.core.fea.springs import apply_spring_stiffness
    from server.core.fea.assembly import assemble_global_stiffness
    structure = _spring_bar(1e6)
    K, dof_map = assemble_global_stiffness(structure)
    with pytest.raises(ValueError, match="unknown node"):
        apply_spring_stiffness(K, dof_map, [ElasticSupport(node_id=999, kx=1e6)])


def test_reactions_remain_consistent_with_springs_present():
    """The equilibrium check must still pass — reactions were computed
    from the SAME spring-augmented K used for the solve."""
    structure = _spring_bar(2.0e6)
    results = solve(structure, EngineeringSpec(),
                    springs=[ElasticSupport(node_id=1, kx=2.0e6)])
    assert results.equilibrium.passed


def test_spring_works_on_the_real_generated_truss():
    """
    Add a Y-spring at a node with NO existing vertical restraint (a
    support node's own Y is already rigidly fixed, so a spring parallel
    to it would be a no-op per the test above — this uses an ordinary
    unsupported bottom-chord node instead, where the spring is the ONLY
    Y-stiffness present and must genuinely reduce displacement there).
    """
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    # Every node in the generated truss carries at least an OUT_OF_PLANE
    # brace (dz only); pick a node whose Y is not among the RESTRAINED
    # components of its own support, so the spring is the only Y-stiffness
    # acting there.
    restrained_y = {s.node_id for s in structure.supports if s.dy}
    free_node = next(n.id for n in structure.nodes if n.id not in restrained_y)

    baseline = solve(structure, spec)
    with_spring = solve(structure, spec,
                        springs=[ElasticSupport(node_id=free_node, ky=1.0e8)])
    assert with_spring.equilibrium.passed

    base_disp = baseline.diagnosis.max_displacement_mm
    spring_disp = with_spring.diagnosis.max_displacement_mm
    assert spring_disp <= base_disp


def test_source_note_states_stiffness_is_a_user_input():
    note = ElasticSupport(node_id=0, ky=1e6).source_note()
    assert "USER INPUT" in note
    assert "bearing capacity" in note
