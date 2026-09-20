"""
Hand-calculable correctness tests for the Direct Stiffness Method solver.

These exist because the solver had zero test coverage despite being the one
component whose correctness matters most (the "deterministic physics
authority" of the whole pipeline).
"""
import math
import pytest

from server.models.structure import (
    Structure, Node, Member, Support, PointLoad,
    SupportType, CrossSection, EngineeringSpec, StructureType,
)
from server.core.fea.solver import solve, FEASolverError
from server.core.generator.topology import generate_structure
from server.core.repair.engine import run_repair_loop


class _FixedAreaSection(CrossSection):
    """CrossSection override with a known, exact area for hand-calculation tests."""

    def __init__(self, area: float):
        super().__init__(outer_diameter=0.1, wall_thickness=0.01)
        self._area = area

    @property
    def area(self):
        return self._area

    @property
    def moment_of_inertia(self):
        return 1e-6  # irrelevant to this test, must be > 0


def _single_bar_structure(F: float, A: float, E: float, L: float) -> Structure:
    """
    A single axial bar along X: node 0 fully fixed, node 1 free in X only,
    loaded with force F at node 1. Analytically:
        elongation = F * L / (A * E)
        stress     = F / A
    """
    nodes = [Node(id=0, x=0.0, y=0.0, z=0.0), Node(id=1, x=L, y=0.0, z=0.0)]
    member = Member(id=0, node_i=0, node_j=1, material_key="A36", section=_FixedAreaSection(A))
    supports = [
        Support(node_id=0, support_type=SupportType.PIN),
        Support(node_id=1, support_type=SupportType.ROLLER_X),  # free in x, restrained in y,z
    ]
    loads = [PointLoad(node_id=1, fx=F)]
    return Structure(nodes=nodes, members=[member], supports=supports, loads=loads)


def test_single_bar_axial_tension_matches_hand_calculation():
    A = 0.002  # m^2
    E = 200e9  # Pa (A36 steel — must match MATERIAL_LIBRARY["A36"].E)
    L = 2.0    # m
    F = 10000.0  # N (tension)

    structure = _single_bar_structure(F, A, E, L)
    spec = EngineeringSpec(material_key="A36", safety_factor=1.67, max_displacement_ratio=300.0)
    results = solve(structure, spec)

    expected_elongation = F * L / (A * E)
    expected_stress = F / A

    node1 = next(r for r in results.node_results if r.node_id == 1)
    member0 = results.member_results[0]

    assert node1.dx == pytest.approx(expected_elongation, rel=1e-9)
    assert member0.axial_force == pytest.approx(F, rel=1e-9)
    assert member0.stress == pytest.approx(expected_stress, rel=1e-9)


def test_reactions_balance_applied_load():
    spec = EngineeringSpec(
        structure_type=StructureType.PRATT,
        span=20.0, height=3.33, num_panels=6,
        primary_load=50000.0, material_key="A36", section_key="CHS_219x8",
    )
    structure = generate_structure(spec)
    results = solve(structure, spec)

    total_ry = sum(r.ry for r in results.reactions)
    assert total_ry == pytest.approx(spec.primary_load, rel=1e-6)
    assert results.diagnosis.passed is True


def test_generated_pratt_truss_is_not_a_mechanism():
    """Regression test: generator must brace every node out-of-plane."""
    spec = EngineeringSpec(structure_type=StructureType.PRATT, span=20.0, height=3.33, num_panels=6)
    structure = generate_structure(spec)
    # Should not raise FEASolverError("... mechanism ...")
    results = solve(structure, spec)
    assert results is not None


def test_generated_warren_truss_is_not_a_mechanism():
    spec = EngineeringSpec(structure_type=StructureType.WARREN, span=20.0, height=3.33, num_panels=6)
    structure = generate_structure(spec)
    results = solve(structure, spec)
    assert results is not None


def test_mechanism_is_detected_and_raises():
    nodes = [Node(id=0, x=0, y=0, z=0), Node(id=1, x=5, y=0, z=0)]
    section = CrossSection(0.1143, 0.0064)
    members = [Member(id=0, node_i=0, node_j=1, material_key="A36", section=section)]
    supports = [Support(node_id=0, support_type=SupportType.PIN)]  # only 1 support => mechanism
    loads = [PointLoad(node_id=1, fy=-1000)]
    structure = Structure(nodes=nodes, members=members, supports=supports, loads=loads)
    spec = EngineeringSpec()

    with pytest.raises(FEASolverError):
        solve(structure, spec)


def test_repair_loop_converges_on_undersized_structure():
    spec = EngineeringSpec(
        structure_type=StructureType.PRATT,
        span=30.0, height=2.0, num_panels=6,
        primary_load=200000.0, material_key="A36", section_key="CHS_76x3.2",
    )
    structure = generate_structure(spec)
    initial_results = solve(structure, spec)
    assert initial_results.diagnosis.passed is False

    iterations = run_repair_loop(structure, spec, initial_results)
    assert len(iterations) > 1
    assert iterations[-1].results.diagnosis.max_stress_ratio < initial_results.diagnosis.max_stress_ratio
