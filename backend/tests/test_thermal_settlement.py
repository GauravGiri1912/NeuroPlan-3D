"""
Priority 8 — Thermal loading and support settlement.

Both are pinned to the analytically-known limiting cases, which are the
ones a wrong sign or a missing correction term would break:

  THERMAL
    free bar, dT > 0            ->  N = 0          (expands, no stress)
    fully restrained, dT > 0    ->  N = -E*A*alpha*dT   (COMPRESSION)
    thermal loads               ->  globally self-equilibrating

  SETTLEMENT
    determinate structure       ->  displacement, but NO member force
    indeterminate structure     ->  member forces DO develop
"""
import math
import pytest

from server.core.fea.solver import solve, FEASolverError
from server.core.fea.thermal import (
    ThermalLoadCase, SupportSettlement, thermal_axial_force,
    build_thermal_load_vector, build_prescribed_displacement_vector,
    THERMAL_EXPANSION, MAX_VALID_TEMPERATURE_CHANGE_K,
)
from server.core.fea.assembly import assemble_global_stiffness
from server.core.generator.topology import generate_structure
from server.models.structure import (
    EngineeringSpec, Structure, Node, Member, Support, SupportType,
    PointLoad, CrossSection, MATERIAL_LIBRARY,
)

SECTION = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)
ALPHA = 1.2e-5
E_A36 = 200e9


def _free_bar() -> Structure:
    """
    One bar along X, 4 m, pinned at the left and on an X-roller at the
    right: axially FREE, so it expands without stress.

    ROLLER_X restrains dy and dz but leaves dx free, giving exactly one
    free DOF — enough for the solver, and the expansion is unresisted.
    """
    return Structure(
        nodes=[Node(0, 0.0, 0.0, 0.0), Node(1, 4.0, 0.0, 0.0)],
        members=[Member(0, 0, 1, "A36", SECTION)],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X),
        ],
        loads=[PointLoad(node_id=1, fy=0.0)],
    )


def _restrained_bar() -> Structure:
    """
    Two collinear 2 m bars pinned at BOTH outer ends, 4 m overall.

    A single bar pinned at both ends has zero free DOF and the solver
    (correctly) refuses to run. Splitting it gives one free DOF — the
    middle node's X — which by symmetry does not move under uniform
    heating, so each half is still fully axially restrained and must
    develop exactly N = -E*A*alpha*dT.

    The middle node uses ROLLER_X (dy, dz held; dx free) because a
    collinear chain has no transverse stiffness to hold it otherwise.
    """
    return Structure(
        nodes=[Node(0, 0.0, 0.0, 0.0), Node(1, 2.0, 0.0, 0.0), Node(2, 4.0, 0.0, 0.0)],
        members=[
            Member(0, 0, 1, "A36", SECTION),
            Member(1, 1, 2, "A36", SECTION),
        ],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X),
            Support(node_id=2, support_type=SupportType.PIN),
        ],
        loads=[PointLoad(node_id=1, fy=0.0)],
    )


def _indeterminate_truss() -> Structure:
    """
    The generated Pratt truss is statically DETERMINATE (m + r = 3n
    exactly), so support settlement moves it without straining it. Adding
    one redundant vertical support makes it indeterminate, which is the
    condition under which settlement induces member forces.
    """
    structure = generate_structure(EngineeringSpec())
    bottom_mid = structure.nodes[3].id
    structure.supports.append(
        Support(node_id=bottom_mid, support_type=SupportType.VERTICAL_ONLY)
    )
    return structure


# ─────────────────────────────────────────────
# Thermal — closed-form limiting cases
# ─────────────────────────────────────────────

def test_thermal_axial_force_matches_closed_form():
    n_t = thermal_axial_force(E_A36, SECTION.area, ALPHA, 50.0)
    assert n_t == pytest.approx(E_A36 * SECTION.area * ALPHA * 50.0)
    # 200e9 * 2.16946e-3 * 1.2e-5 * 50 = 260.3 kN
    assert n_t == pytest.approx(260_335.0, rel=1e-3)


def test_fully_restrained_bar_develops_compression_on_heating():
    """The classic case. A sign error here flips compression to tension."""
    structure = _restrained_bar()
    results = solve(structure, EngineeringSpec(),
                    thermal=ThermalLoadCase(delta_t=+50.0))

    force = results.member_results[0].axial_force
    expected = -thermal_axial_force(E_A36, SECTION.area, ALPHA, 50.0)

    assert force == pytest.approx(expected, rel=1e-9)
    assert force < 0, "heating a restrained bar must produce COMPRESSION"


def test_fully_restrained_bar_develops_tension_on_cooling():
    structure = _restrained_bar()
    results = solve(structure, EngineeringSpec(),
                    thermal=ThermalLoadCase(delta_t=-50.0))
    assert results.member_results[0].axial_force > 0, \
        "cooling a restrained bar must produce TENSION"


def test_axially_free_bar_develops_no_thermal_force():
    """
    An unrestrained bar expands freely and carries NO stress. This is the
    test that fails if the thermal correction term is omitted from force
    recovery — it would report a spurious E*A*alpha*dT tension.
    """
    structure = _free_bar()
    results = solve(structure, EngineeringSpec(),
                    thermal=ThermalLoadCase(delta_t=+50.0))

    assert results.member_results[0].axial_force == pytest.approx(0.0, abs=1e-6)


def test_free_bar_actually_elongates_by_alpha_dt_L():
    """The displacement must still show the free thermal expansion."""
    structure = _free_bar()
    results = solve(structure, EngineeringSpec(),
                    thermal=ThermalLoadCase(delta_t=+50.0))

    node1 = next(n for n in results.node_results if n.node_id == 1)
    assert node1.dx == pytest.approx(ALPHA * 50.0 * 4.0, rel=1e-9)


def test_zero_temperature_change_reproduces_the_untouched_result():
    structure = generate_structure(EngineeringSpec())
    spec = EngineeringSpec()

    base = solve(structure, spec)
    zero = solve(structure, spec, thermal=ThermalLoadCase(delta_t=0.0))

    for a, b in zip(base.member_results, zero.member_results):
        assert a.axial_force == pytest.approx(b.axial_force, rel=1e-12, abs=1e-9)


def test_thermal_force_scales_linearly_with_temperature():
    structure = _restrained_bar()
    spec = EngineeringSpec()

    f25 = solve(structure, spec, thermal=ThermalLoadCase(delta_t=25.0)).member_results[0]
    f50 = solve(structure, spec, thermal=ThermalLoadCase(delta_t=50.0)).member_results[0]

    assert f50.axial_force == pytest.approx(2.0 * f25.axial_force, rel=1e-9)


def test_thermal_load_vector_is_globally_self_equilibrating():
    """
    Thermal equivalent loads are internal: they must sum to zero force
    AND zero moment, otherwise they would fabricate external load.
    """
    structure = generate_structure(EngineeringSpec())
    _, dof_map = assemble_global_stiffness(structure)
    F = build_thermal_load_vector(structure, dof_map, ThermalLoadCase(delta_t=40.0))

    nodes = structure.node_dict()
    fx = fy = fz = 0.0
    mx = my = mz = 0.0
    for node in structure.nodes:
        dx, dy, dz = dof_map[node.id]
        px, py, pz = F[dx], F[dy], F[dz]
        fx += px; fy += py; fz += pz
        n = nodes[node.id]
        mx += n.y * pz - n.z * py
        my += n.z * px - n.x * pz
        mz += n.x * py - n.y * px

    scale = max(abs(F).max(), 1.0)
    for component in (fx, fy, fz, mx, my, mz):
        assert abs(component) < 1e-6 * scale


def test_equilibrium_still_holds_under_thermal_load():
    structure = generate_structure(EngineeringSpec())
    results = solve(structure, EngineeringSpec(),
                    thermal=ThermalLoadCase(delta_t=40.0))
    assert results.equilibrium.passed


def test_aluminium_expands_more_than_steel():
    assert THERMAL_EXPANSION["AL6061"] > THERMAL_EXPANSION["A36"]

    steel = _restrained_bar()
    alu = _restrained_bar()
    # BOTH members, otherwise the bar is a steel/aluminium composite: the
    # midpoint shifts and the fully-restrained formula no longer applies.
    for member in alu.members:
        member.material_key = "AL6061"

    spec = EngineeringSpec()
    fs = abs(solve(steel, spec, thermal=ThermalLoadCase(delta_t=50.0)).member_results[0].axial_force)
    fa = abs(solve(alu, spec, thermal=ThermalLoadCase(delta_t=50.0)).member_results[0].axial_force)

    # E*alpha for aluminium (68.9e9*2.32e-5) vs steel (200e9*1.2e-5)
    assert fa == pytest.approx(
        fs * (68.9e9 * 2.32e-5) / (200e9 * 1.2e-5), rel=1e-6
    )


def test_high_temperature_change_is_flagged_as_outside_validity():
    """E is held constant with temperature, so fire is out of scope."""
    warning = ThermalLoadCase(delta_t=600.0).validity_warning()
    assert warning
    assert "fire" in warning.lower()
    assert ThermalLoadCase(delta_t=30.0).validity_warning() == ""


# ─────────────────────────────────────────────
# Settlement
# ─────────────────────────────────────────────

def test_settlement_moves_the_support_by_the_prescribed_amount():
    structure = generate_structure(EngineeringSpec())
    support_node = structure.supports[0].node_id

    results = solve(structure, EngineeringSpec(),
                    settlements=[SupportSettlement(node_id=support_node, dy=-0.01)])

    moved = next(n for n in results.node_results if n.node_id == support_node)
    assert moved.dy == pytest.approx(-0.01, rel=1e-9)


def test_settlement_of_a_determinate_truss_produces_no_member_force():
    """
    A statically determinate structure follows a support movement without
    straining. Member forces developing here would indicate the
    partitioned K_fc term is wrong.
    """
    structure = _free_bar()   # determinate
    results = solve(structure, EngineeringSpec(),
                    settlements=[SupportSettlement(node_id=0, dy=-0.005)])

    assert results.member_results[0].axial_force == pytest.approx(0.0, abs=1e-6)


def test_settlement_of_the_determinate_generated_truss_produces_no_member_force():
    """
    The generated Pratt truss has m + r = 3n exactly, i.e. it is
    statically determinate. Classical theory: a determinate structure
    accommodates support movement by rigid-body motion and develops NO
    internal force. Forces appearing here would mean the K_fc term is
    wrong.
    """
    structure = generate_structure(EngineeringSpec())
    spec = EngineeringSpec()

    base = solve(structure, spec)
    settled = solve(structure, spec,
                    settlements=[SupportSettlement(node_id=structure.supports[0].node_id,
                                                   dy=-0.02)])

    for a, b in zip(base.member_results, settled.member_results):
        assert a.axial_force == pytest.approx(b.axial_force, abs=1e-3)


def test_settlement_of_an_indeterminate_truss_does_produce_member_force():
    """The converse — otherwise the feature would be doing nothing."""
    structure = _indeterminate_truss()
    spec = EngineeringSpec()

    base = solve(structure, spec)
    settled = solve(structure, spec,
                    settlements=[SupportSettlement(node_id=structure.supports[0].node_id,
                                                   dy=-0.02)])

    changed = any(
        abs(a.axial_force - b.axial_force) > 1.0
        for a, b in zip(base.member_results, settled.member_results)
    )
    assert changed, "settlement must redistribute force in an indeterminate truss"


def test_zero_settlement_reproduces_the_untouched_result():
    structure = generate_structure(EngineeringSpec())
    spec = EngineeringSpec()

    base = solve(structure, spec)
    zero = solve(structure, spec,
                 settlements=[SupportSettlement(node_id=structure.supports[0].node_id)])

    for a, b in zip(base.member_results, zero.member_results):
        assert a.axial_force == pytest.approx(b.axial_force, rel=1e-12, abs=1e-9)


def test_settlement_on_an_unrestrained_direction_is_rejected():
    """
    Prescribing a displacement where the support is already free is
    meaningless and must be refused, not silently ignored.
    """
    structure = _free_bar()
    _, dof_map = assemble_global_stiffness(structure)

    with pytest.raises(ValueError, match="already free"):
        build_prescribed_displacement_vector(
            structure, dof_map, [SupportSettlement(node_id=1, dx=0.01)]
        )


def test_settlement_at_a_node_with_no_support_is_rejected():
    """
    Built explicitly: the generator braces every node out-of-plane, so a
    generated truss has no support-free node to use here.
    """
    structure = Structure(
        nodes=[Node(0, 0.0, 0.0, 0.0), Node(1, 4.0, 0.0, 0.0)],
        members=[Member(0, 0, 1, "A36", SECTION)],
        supports=[Support(node_id=0, support_type=SupportType.PIN)],
        loads=[PointLoad(node_id=1, fy=-1000.0)],
    )
    _, dof_map = assemble_global_stiffness(structure)

    with pytest.raises(ValueError, match="no support"):
        build_prescribed_displacement_vector(
            structure, dof_map, [SupportSettlement(node_id=1, dy=-0.01)]
        )


def test_equilibrium_still_holds_under_settlement():
    structure = generate_structure(EngineeringSpec())
    results = solve(structure, EngineeringSpec(),
                    settlements=[SupportSettlement(node_id=structure.supports[0].node_id,
                                                   dy=-0.01)])
    assert results.equilibrium.passed


def test_thermal_and_settlement_can_be_applied_together():
    structure = generate_structure(EngineeringSpec())
    results = solve(
        structure, EngineeringSpec(),
        thermal=ThermalLoadCase(delta_t=30.0),
        settlements=[SupportSettlement(node_id=structure.supports[0].node_id, dy=-0.01)],
    )
    assert results.equilibrium.passed
    assert all(math.isfinite(m.axial_force) for m in results.member_results)


def test_thermal_stress_develops_only_where_the_span_is_restrained():
    """
    The determinate/indeterminate distinction, stated as a pair.

    The generated truss has a roller, so the span expands freely: uniform
    heating gives displacement but no stress. Adding one restraint in the
    direction of expansion makes it indeterminate, and large thermal
    stress appears. Testing only one half of this would let a broken
    thermal implementation pass.
    """
    from server.models.structure import Support, SupportType

    spec = EngineeringSpec()
    free = generate_structure(spec)
    base = solve(free, spec)
    hot = solve(free, spec, thermal=ThermalLoadCase(delta_t=40.0))

    base_stress = max(abs(m.stress) for m in base.member_results)
    hot_stress = max(abs(m.stress) for m in hot.member_results)
    assert hot_stress == pytest.approx(base_stress, rel=1e-9)
    assert hot.diagnosis.max_displacement_mm > base.diagnosis.max_displacement_mm

    restrained = generate_structure(spec)
    restrained.supports.append(
        Support(node_id=restrained.nodes[3].id, support_type=SupportType.ROLLER_Z)
    )
    cold = solve(restrained, spec)
    warm = solve(restrained, spec, thermal=ThermalLoadCase(delta_t=40.0))

    cold_stress = max(abs(m.stress) for m in cold.member_results)
    warm_stress = max(abs(m.stress) for m in warm.member_results)
    assert warm_stress > 10.0 * cold_stress
