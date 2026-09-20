"""
NeuroPlan-3D — Independent 3D Space-Truss Solver Tests

These validate the 3D formulation against closed-form results derived by
hand, independent of any code in this repo. They exist to answer one
question precisely: is this genuinely solving 3D structural mechanics, or
merely drawing 3D pictures of 2D results?

3D TRUSS ELEMENT FORMULATION UNDER TEST
---------------------------------------
For a member from node i=(xi,yi,zi) to node j=(xj,yj,zj):

    dx = xj-xi,  dy = yj-yi,  dz = zj-zi
    L  = sqrt(dx² + dy² + dz²)
    lx = dx/L,   ly = dy/L,   lz = dz/L        (direction cosines)

    c  = [lx, ly, lz]ᵀ
    C  = c·cᵀ                                   (3×3, rank 1)

    K_e = (AE/L) · [[ C, -C],
                    [-C,  C]]                   (6×6, global coords)

Each node contributes 3 translational DOF (UX, UY, UZ), so an N-node
structure yields a 3N × 3N global system [K]{u} = {F}.

For a single axial bar carrying force F along its own axis:
    elongation δ = F·L / (A·E)
    stress     σ = F / A
and these must hold regardless of how the bar is oriented in space —
which is precisely what Tests 1-4 check.
"""
import math
import pytest

from server.models.structure import (
    Structure, Node, Member, Support, PointLoad,
    SupportType, CrossSection, EngineeringSpec, StructureType,
)
from server.core.fea.solver import solve, FEASolverError
from server.core.fea.elements import direction_cosines, truss_element_stiffness
from server.core.generator.space_truss import generate_space_truss


E_A36 = 200e9  # Pa — must match MATERIAL_LIBRARY["A36"].E
AREA = 0.002   # m²


class _FixedAreaSection(CrossSection):
    """CrossSection with an exact known area, for closed-form comparisons."""

    def __init__(self, area: float = AREA):
        super().__init__(outer_diameter=0.1, wall_thickness=0.01)
        self._area = area

    @property
    def area(self):
        return self._area

    @property
    def moment_of_inertia(self):
        return 1e-6


def _axial_bar_along(axis: str, L: float, F: float) -> Structure:
    """
    One bar of length L from the origin along the given axis, fully fixed at
    the origin end, restrained perpendicular to its axis at the free end,
    and loaded with force F along its own axis at the free end.

    Closed form: elongation = F·L/(A·E) along that axis, stress = F/A.
    """
    end = {"x": (L, 0.0, 0.0), "y": (0.0, L, 0.0), "z": (0.0, 0.0, L)}[axis]
    nodes = [Node(id=0, x=0.0, y=0.0, z=0.0), Node(id=1, x=end[0], y=end[1], z=end[2])]
    members = [Member(id=0, node_i=0, node_j=1, material_key="A36", section=_FixedAreaSection())]

    # Free end: release only the axis of action, restrain the other two.
    free_end = Support(node_id=1, support_type=SupportType.PIN)
    free_end.dx = axis != "x"
    free_end.dy = axis != "y"
    free_end.dz = axis != "z"

    loads = [PointLoad(
        node_id=1,
        fx=F if axis == "x" else 0.0,
        fy=F if axis == "y" else 0.0,
        fz=F if axis == "z" else 0.0,
    )]
    return Structure(
        nodes=nodes, members=members,
        supports=[Support(node_id=0, support_type=SupportType.PIN), free_end],
        loads=loads,
    )


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_axial_bar_matches_closed_form_on_every_axis(axis):
    """
    TESTS 1, 2, 3 — axial member aligned with X, Y, and Z.

    The Z case is the one a 2D solver fundamentally cannot pass: it has no
    UZ degree of freedom, so a Z-aligned bar would have no stiffness at all.
    """
    L, F = 2.0, 10000.0
    structure = _axial_bar_along(axis, L, F)
    spec = EngineeringSpec(material_key="A36")
    results = solve(structure, spec)

    expected_elongation = F * L / (AREA * E_A36)
    expected_stress = F / AREA

    node1 = next(r for r in results.node_results if r.node_id == 1)
    actual_elongation = {"x": node1.dx, "y": node1.dy, "z": node1.dz}[axis]

    assert actual_elongation == pytest.approx(expected_elongation, rel=1e-9)
    assert results.member_results[0].axial_force == pytest.approx(F, rel=1e-9)
    assert results.member_results[0].stress == pytest.approx(expected_stress, rel=1e-9)
    assert results.equilibrium.passed
    assert results.equilibrium.relative_residual < 1e-9


def test_diagonal_member_direction_cosines_and_stiffness():
    """
    TEST 4 — a genuinely diagonal member with all three direction cosines
    non-zero. Uses a 3-4-12 / 13 Pythagorean quadruple: 3²+4²+12² = 169 = 13².
    """
    ni = Node(id=0, x=0.0, y=0.0, z=0.0)
    nj = Node(id=1, x=3.0, y=4.0, z=12.0)

    lx, ly, lz, L = direction_cosines(ni, nj)
    assert L == pytest.approx(13.0, rel=1e-12)
    assert lx == pytest.approx(3.0 / 13.0, rel=1e-12)
    assert ly == pytest.approx(4.0 / 13.0, rel=1e-12)
    assert lz == pytest.approx(12.0 / 13.0, rel=1e-12)
    # Direction cosines must be a unit vector.
    assert lx**2 + ly**2 + lz**2 == pytest.approx(1.0, rel=1e-12)

    K_e = truss_element_stiffness(ni, nj, AREA, E_A36)
    k = AREA * E_A36 / L

    # Diagonal terms are k·l², and every axis must be represented.
    assert K_e[0, 0] == pytest.approx(k * lx**2, rel=1e-12)
    assert K_e[1, 1] == pytest.approx(k * ly**2, rel=1e-12)
    assert K_e[2, 2] == pytest.approx(k * lz**2, rel=1e-12)
    # Cross-coupling between axes — the hallmark of a true 3D element.
    assert K_e[0, 2] == pytest.approx(k * lx * lz, rel=1e-12)
    assert K_e[1, 2] == pytest.approx(k * ly * lz, rel=1e-12)
    # Symmetry and equilibrium of the element matrix.
    assert K_e == pytest.approx(K_e.T, rel=1e-12)
    assert K_e.sum(axis=0) == pytest.approx([0, 0, 0, 0, 0, 0], abs=1e-6)


def test_diagonal_bar_elongates_along_its_own_axis():
    """
    TEST 4b — load a fully 3D diagonal bar along its own axis and confirm
    the displacement magnitude matches F·L/(A·E) and points along the bar.
    """
    L_target = 13.0
    F = 26000.0
    nodes = [Node(id=0, x=0.0, y=0.0, z=0.0), Node(id=1, x=3.0, y=4.0, z=12.0)]
    members = [Member(id=0, node_i=0, node_j=1, material_key="A36", section=_FixedAreaSection())]

    # Free node released in all directions; the bar alone provides stiffness
    # along its axis, so load it exactly along that axis.
    lx, ly, lz = 3.0 / 13.0, 4.0 / 13.0, 12.0 / 13.0
    loads = [PointLoad(node_id=1, fx=F * lx, fy=F * ly, fz=F * lz)]

    # Restrain the free node perpendicular to the bar using two dummy
    # members to a pair of anchors, so only the axial mode is free.
    nodes.append(Node(id=2, x=3.0 + ly, y=4.0 - lx, z=12.0))          # perp anchor 1
    nodes.append(Node(id=3, x=3.0 - lz * ly, y=4.0, z=12.0 + lx * ly))  # perp anchor 2
    members.append(Member(id=1, node_i=1, node_j=2, material_key="A36", section=_FixedAreaSection()))
    members.append(Member(id=2, node_i=1, node_j=3, material_key="A36", section=_FixedAreaSection()))

    structure = Structure(
        nodes=nodes, members=members,
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=2, support_type=SupportType.PIN),
            Support(node_id=3, support_type=SupportType.PIN),
        ],
        loads=loads,
    )
    results = solve(structure, EngineeringSpec(material_key="A36"))

    # The bar carries essentially all of the axial force.
    bar = next(m for m in results.member_results if m.member_id == 0)
    assert bar.axial_force == pytest.approx(F, rel=1e-3)
    assert results.equilibrium.passed

    node1 = next(r for r in results.node_results if r.node_id == 1)
    magnitude = math.sqrt(node1.dx**2 + node1.dy**2 + node1.dz**2)
    assert magnitude == pytest.approx(F * L_target / (AREA * E_A36), rel=1e-2)
    # Displacement must have a real Z component — impossible in a 2D solver.
    assert abs(node1.dz) > 0.1 * magnitude


def test_known_space_truss_tripod_reactions():
    """
    TEST 5 + 6 — a symmetric three-legged tripod carrying a vertical load at
    its apex. By symmetry each leg carries an equal share, and the three
    vertical reactions must each equal P/3.
    """
    P = 30000.0
    H = 4.0
    R = 3.0  # base radius
    apex = Node(id=0, x=0.0, y=H, z=0.0)
    nodes = [apex]
    members = []
    supports = []
    for k in range(3):
        theta = 2 * math.pi * k / 3
        nodes.append(Node(id=k + 1, x=R * math.cos(theta), y=0.0, z=R * math.sin(theta)))
        members.append(Member(id=k, node_i=0, node_j=k + 1,
                              material_key="A36", section=_FixedAreaSection()))
        supports.append(Support(node_id=k + 1, support_type=SupportType.PIN))

    structure = Structure(nodes=nodes, members=members, supports=supports,
                          loads=[PointLoad(node_id=0, fy=-P)])
    results = solve(structure, EngineeringSpec(material_key="A36"))

    for reaction in results.reactions:
        assert reaction.ry == pytest.approx(P / 3.0, rel=1e-9)

    # All three legs equally loaded, and in compression.
    forces = [m.axial_force for m in results.member_results]
    assert all(f < 0 for f in forces)
    assert forces[0] == pytest.approx(forces[1], rel=1e-9)
    assert forces[1] == pytest.approx(forces[2], rel=1e-9)

    # Closed form: each leg's axial force = -(P/3) · (leg length / H)
    leg_length = math.sqrt(R**2 + H**2)
    assert forces[0] == pytest.approx(-(P / 3.0) * leg_length / H, rel=1e-9)


def test_global_equilibrium_holds_for_three_dimensional_loading():
    """
    TEST 7 — global force equilibrium with simultaneous Fx, Fy and Fz.
    Every axis must balance independently.
    """
    spec = EngineeringSpec(
        structure_type=StructureType.SPACE_TRUSS,
        span=20.0, height=2.5, width=4.0, num_panels=6,
        primary_load=50000.0, lateral_load_x=8000.0, lateral_load_z=12000.0,
        section_key="CHS_168x6",
    )
    structure = generate_space_truss(spec)
    results = solve(structure, spec)

    eq = results.equilibrium
    assert eq.passed, f"equilibrium residual too large: {eq.relative_residual:.3e}"
    assert eq.relative_residual < 1e-9

    applied_fx = sum(l.fx for l in structure.loads)
    applied_fz = sum(l.fz for l in structure.loads)
    # Lateral load actually reached the model (not silently discarded).
    assert applied_fx == pytest.approx(spec.lateral_load_x, rel=1e-9)
    assert applied_fz == pytest.approx(spec.lateral_load_z, rel=1e-9)
    # And it produced real reactions opposing it.
    assert sum(r.rx for r in results.reactions) == pytest.approx(-applied_fx, rel=1e-6)
    assert sum(r.rz for r in results.reactions) == pytest.approx(-applied_fz, rel=1e-6)


def test_boundary_conditions_are_enforced_exactly():
    """TEST 8 — every restrained DOF must have exactly zero displacement."""
    spec = EngineeringSpec(
        structure_type=StructureType.SPACE_TRUSS,
        span=20.0, height=2.5, width=4.0, num_panels=6, section_key="CHS_168x6",
    )
    structure = generate_space_truss(spec)
    results = solve(structure, spec)

    node_results = {r.node_id: r for r in results.node_results}
    for support in structure.supports:
        nr = node_results[support.node_id]
        if support.dx:
            assert nr.dx == pytest.approx(0.0, abs=1e-15)
        if support.dy:
            assert nr.dy == pytest.approx(0.0, abs=1e-15)
        if support.dz:
            assert nr.dz == pytest.approx(0.0, abs=1e-15)


def test_unstable_3d_structure_is_detected():
    """
    TEST 9 — a spatial structure with insufficient restraint must be
    rejected, not silently solved into meaningless numbers. Here a tripod
    apex is left free in Z with no member resisting that direction.
    """
    nodes = [
        Node(id=0, x=0.0, y=0.0, z=0.0),
        Node(id=1, x=4.0, y=0.0, z=0.0),
        Node(id=2, x=2.0, y=3.0, z=0.0),
    ]
    section = _FixedAreaSection()
    members = [
        Member(id=0, node_i=0, node_j=2, material_key="A36", section=section),
        Member(id=1, node_i=1, node_j=2, material_key="A36", section=section),
    ]
    # Node 2 has no Z restraint and no member with a Z component → free to
    # drift out of plane: a genuine 3D mechanism.
    supports = [
        Support(node_id=0, support_type=SupportType.PIN),
        Support(node_id=1, support_type=SupportType.PIN),
    ]
    structure = Structure(nodes=nodes, members=members, supports=supports,
                          loads=[PointLoad(node_id=2, fy=-1000.0)])

    with pytest.raises(FEASolverError, match="mechanism"):
        solve(structure, EngineeringSpec(material_key="A36"))


def test_zero_length_member_is_rejected():
    """TEST 10 — coincident nodes must raise, not divide by zero."""
    ni = Node(id=0, x=1.0, y=2.0, z=3.0)
    nj = Node(id=1, x=1.0, y=2.0, z=3.0)
    with pytest.raises(ValueError, match="Zero-length"):
        direction_cosines(ni, nj)


def test_planar_structures_still_solve_after_3d_upgrade():
    """
    TEST 11 — planar regression. The existing planar generators must be
    completely unaffected by the spatial work.
    """
    for structure_type in (StructureType.PRATT, StructureType.HOWE, StructureType.WARREN):
        spec = EngineeringSpec(structure_type=structure_type, span=20.0, height=3.33, num_panels=6)
        from server.core.generator.topology import generate_structure
        structure = generate_structure(spec)
        results = solve(structure, spec)

        assert results.is_spatial is False, f"{structure_type} should be planar"
        assert all(abs(n.z) < 1e-12 for n in structure.nodes)
        assert results.equilibrium.passed
        assert results.dof_count == 3 * len(structure.nodes)
