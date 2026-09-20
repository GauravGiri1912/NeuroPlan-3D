"""
NeuroPlan-3D — Solver Validation Against a Classical Statics Benchmark

This is the credibility test: it proves the Direct Stiffness Method
implementation reproduces member forces derivable entirely by hand via the
classical Method of Joints, independent of the solver's own code.

Benchmark structure: a symmetric isosceles triangular truss — a standard
statically-determinate "Method of Joints" problem shape used throughout
introductory structural analysis.

    C (3, 4)
    /\\
   /  \\
  A----B
(0,0) (6,0)

- A: pin support (both reactions)
- B: roller support (vertical reaction only)
- C: apex, single downward point load P

Members: AB (bottom chord, length 6), AC and BC (both length 5, since
each rises 4 and runs 3 horizontally — a 3-4-5 right triangle mirrored
about the centerline).

Hand derivation (method of joints, independent of any code in this repo):

Reactions (by symmetry, since the load is at the apex, centered over AB):
    Ay = By = P / 2
    Ax = 0

Joint C: two members, CA (unit vector (-3,-4)/5) and CB (unit vector (3,-4)/5).
    sum Fx: -3/5 F_CA + 3/5 F_CB = 0        => F_CA = F_CB  (symmetry)
    sum Fy: -4/5 F_CA - 4/5 F_CB - P = 0    => F_CA = F_CB = -5P/8  (compression)

Joint A: members AB (unit vector (1,0)) and AC (unit vector (3,4)/5), plus Ay = P/2.
    sum Fx: F_AB + 3/5 F_AC = 0             => F_AB = -3/5 * (-5P/8) = 3P/8  (tension)
    sum Fy check: 4/5 F_AC + Ay = 4/5*(-5P/8) + P/2 = -P/2 + P/2 = 0  ✓

So for P = 10,000 N:
    F_AB = +3750 N (tension)
    F_AC = F_BC = -6250 N (compression)
    Ay = By = 5000 N, Ax = 0

Crucially, for a statically determinate truss these member forces are
independent of material (E) and cross-section (A) entirely — they come
from equilibrium alone. This test therefore validates the solver's
assembly + boundary-condition + solve + force-recovery pipeline against
pure statics, decoupled from any assumption about stiffness.
"""
import pytest

from server.models.structure import (
    Structure, Node, Member, Support, PointLoad,
    SupportType, CrossSection, EngineeringSpec,
)
from server.core.fea.solver import solve


def _triangular_benchmark_truss(P: float) -> Structure:
    nodes = [
        Node(id=0, x=0.0, y=0.0, z=0.0),  # A
        Node(id=1, x=6.0, y=0.0, z=0.0),  # B
        Node(id=2, x=3.0, y=4.0, z=0.0),  # C (apex)
    ]
    section = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)  # arbitrary — forces are area-independent
    members = [
        Member(id=0, node_i=0, node_j=1, material_key="A36", section=section),  # AB
        Member(id=1, node_i=0, node_j=2, material_key="A36", section=section),  # AC
        Member(id=2, node_i=1, node_j=2, material_key="A36", section=section),  # BC
    ]
    supports = [
        Support(node_id=0, support_type=SupportType.PIN),        # A: both reactions
        Support(node_id=1, support_type=SupportType.ROLLER_X),   # B: vertical reaction only
        # C has no in-plane support, but every node needs its out-of-plane
        # (z) DOF braced since this is a planar truss with no z-stiffness —
        # see the same fix applied in the real topology generators.
        Support(node_id=2, support_type=SupportType.OUT_OF_PLANE),
    ]
    loads = [PointLoad(node_id=2, fy=-P)]
    return Structure(nodes=nodes, members=members, supports=supports, loads=loads)


def test_solver_matches_hand_calculated_triangular_truss():
    P = 10000.0  # N
    structure = _triangular_benchmark_truss(P)
    spec = EngineeringSpec(material_key="A36", safety_factor=1.67, max_displacement_ratio=300.0)

    results = solve(structure, spec)
    forces = {m.member_id: m.axial_force for m in results.member_results}
    reactions = {r.node_id: r for r in results.reactions}

    # Member forces (member ids: 0=AB, 1=AC, 2=BC)
    assert forces[0] == pytest.approx(3750.0, rel=1e-6)    # AB — tension
    assert forces[1] == pytest.approx(-6250.0, rel=1e-6)   # AC — compression
    assert forces[2] == pytest.approx(-6250.0, rel=1e-6)   # BC — compression

    # Reactions
    assert reactions[0].rx == pytest.approx(0.0, abs=1e-6)
    assert reactions[0].ry == pytest.approx(5000.0, rel=1e-6)
    assert reactions[1].ry == pytest.approx(5000.0, rel=1e-6)

    # Global equilibrium: total vertical reaction must equal the applied load
    total_ry = sum(r.ry for r in results.reactions)
    assert total_ry == pytest.approx(P, rel=1e-9)
