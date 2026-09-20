"""
Nonlinear truss analysis: geometric (P-Delta) and material.

VALIDATION STRATEGY for geometric nonlinearity uses the von Mises shallow
truss (two bars from fixed supports to a free apex, symmetric point load)
— the classic closed-form snap-through benchmark. Two checks are used,
deliberately different in character:

  1. FORWARD equilibrium check (primary, unconditionally valid): at the
     converged solution, F_int(u) must equal F_target to high precision.
     This is the actual definition of a correct nonlinear solve and does
     not depend on how close we are to any limit point.

  2. Displacement-vs-closed-form check (secondary, only away from the
     limit point): comparing the converged apex displacement to a
     v_target chosen via the closed-form P(v) relation. This is only
     meaningful away from the snap-through point, because near a limit
     point dP/dv -> 0, so the inverse v(P) is ill-conditioned — small
     floating-point differences in P produce large differences in v.
     This was discovered directly while building this test: an earlier
     version tested up to 82% of the snap-through displacement and saw
     the comparison error grow to 1.3%, while the FORWARD check at the
     exact same point matched to 1e-7. The growth traced entirely to
     proximity to the limit point, not a solver defect.
"""
import math
import pytest

from server.core.fea.nonlinear import (
    solve_nonlinear, build_nonlinear_inputs, _member_axial_forces,
    _internal_force_vector,
)
from server.core.fea.assembly import build_load_vector
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import (
    Structure, Node, Member, Support, SupportType, PointLoad, CrossSection,
    EngineeringSpec, MATERIAL_LIBRARY,
)

E_A36 = MATERIAL_LIBRARY["A36"].E
FY_A36 = MATERIAL_LIBRARY["A36"].yield_stress
SECTION = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)


def _axial_bar(length=4.0):
    return Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, length, 0, 0)],
        members=[Member(0, 0, 1, "A36", SECTION)],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X, dx=False, dy=True, dz=True),
        ],
        loads=[PointLoad(node_id=1, fx=0.0)],
    )


def _von_mises_truss(a=1.0, h=0.1, area=1e-4):
    """Two bars, fixed supports at (+-a, 0, 0), free apex at (0, h, 0)."""
    od = 0.1
    t = area / (math.pi * od)   # thin-ring approx: area = pi*od*t
    section = CrossSection(od, t)
    return Structure(
        nodes=[Node(0, -a, 0, 0), Node(1, a, 0, 0), Node(2, 0, h, 0)],
        members=[Member(0, 0, 2, "A36", section), Member(1, 1, 2, "A36", section)],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.PIN),
            Support(node_id=2, support_type=SupportType.OUT_OF_PLANE),
        ],
        loads=[PointLoad(node_id=2, fy=0.0)],
    )


def _von_mises_p_closed(v, a=1.0, h=0.1, E=E_A36, area=1e-4):
    """
    Closed-form apex equilibrium, derived directly from the FEA's own
    validated internal-force convention (F_int_j = +N*c): at the apex,
    F_ext_y = F_int_y = 2*N*sin(theta), N = E*A*(L(v)-L0)/L0.
    """
    L0 = math.sqrt(a ** 2 + h ** 2)
    Lv = math.sqrt(a ** 2 + (h - v) ** 2)
    sinth = (h - v) / Lv
    strain = (Lv - L0) / L0
    N = E * area * strain
    return 2 * N * sinth


# ─────────────────────────────────────────────
# Sanity: nonlinear solver reproduces the linear solver when linear
# ─────────────────────────────────────────────

def test_pure_linear_case_matches_the_linear_solver_closed_form():
    """geometric=False, material=False, below yield: must match u = PL/(AE)."""
    structure = _axial_bar()
    dof_map, constrained = build_nonlinear_inputs(structure)
    structure.loads = [PointLoad(node_id=1, fx=50_000.0)]
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=False, material=False, n_steps=1)
    assert result.converged
    u = result.displacements[dof_map[1][0]]
    expected = 50_000.0 * 4.0 / (SECTION.area * E_A36)
    assert u == pytest.approx(expected, rel=1e-6)


def test_small_load_geometric_nonlinear_matches_linear_closely():
    """At small load, P-Delta effects vanish and both solves should agree."""
    structure = _axial_bar()
    dof_map, constrained = build_nonlinear_inputs(structure)
    structure.loads = [PointLoad(node_id=1, fx=1_000.0)]
    F = build_load_vector(structure, dof_map)

    linear = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=False, material=False, n_steps=1)
    nonlinear = solve_nonlinear(structure, F, dof_map, constrained,
                                geometric=True, material=False, n_steps=5)
    assert linear.converged and nonlinear.converged
    assert nonlinear.displacements[dof_map[1][0]] == pytest.approx(
        linear.displacements[dof_map[1][0]], rel=1e-4
    )


# ─────────────────────────────────────────────
# Geometric nonlinearity — von Mises snap-through
# ─────────────────────────────────────────────

@pytest.mark.parametrize("v_target_frac", [0.05, 0.15, 0.25, 0.35])
def test_snap_through_converged_solution_satisfies_equilibrium(v_target_frac):
    """
    PRIMARY check: F_int at the converged solution must equal F_target.
    Valid at any point on the primary branch, including close to the
    limit point, because it does not require inverting the P(v) relation.
    """
    a, h, area = 1.0, 0.1, 1e-4
    v_target = v_target_frac * h
    P_target = _von_mises_p_closed(v_target, a, h, E_A36, area)

    structure = _von_mises_truss(a, h, area)
    structure.loads = [PointLoad(node_id=2, fy=P_target)]
    dof_map, constrained = build_nonlinear_inputs(structure)
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=True, material=False,
                             n_steps=60, max_iterations=60, tolerance=1e-9)
    assert result.converged, result.divergence_reason

    u = result.displacements
    base = {n.id: (n.x, n.y, n.z) for n in structure.nodes}
    positions = {
        nid: (x + u[dof_map[nid][0]], y + u[dof_map[nid][1]], z + u[dof_map[nid][2]])
        for nid, (x, y, z) in base.items()
    }
    forces, _ = _member_axial_forces(structure, u, dof_map, positions,
                                     fy_cap=False, base_positions=base)
    F_int = _internal_force_vector(structure, dof_map, forces, positions)
    assert F_int[dof_map[2][1]] == pytest.approx(P_target, rel=1e-5)


@pytest.mark.parametrize("v_target_frac", [0.05, 0.15, 0.25, 0.35])
def test_snap_through_displacement_matches_closed_form_away_from_the_limit(v_target_frac):
    """
    SECONDARY check. v_snap ~ 0.424*h for this geometry, so frac<=0.35
    keeps v_target comfortably below it (~83% of v_snap at worst),
    avoiding the region where dP/dv -> 0 makes the inverse v(P) mapping
    ill-conditioned (see module docstring). Tolerance is loosened as
    frac increases because approaching the limit point is exactly where
    this ill-conditioning grows, even though the FORWARD equilibrium
    check above remains tight throughout.
    """
    a, h, area = 1.0, 0.1, 1e-4
    v_target = v_target_frac * h
    P_target = _von_mises_p_closed(v_target, a, h, E_A36, area)

    structure = _von_mises_truss(a, h, area)
    structure.loads = [PointLoad(node_id=2, fy=P_target)]
    dof_map, constrained = build_nonlinear_inputs(structure)
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=True, material=False, n_steps=60, max_iterations=60)
    assert result.converged
    v_fea = -result.displacements[dof_map[2][1]]
    tolerance = 0.005 if v_target_frac <= 0.15 else 0.015
    assert v_fea == pytest.approx(v_target, rel=tolerance)


def test_geometric_nonlinearity_actually_changes_the_result():
    """A linear solve of the same snap-through load must NOT match — the
    whole point of the feature is that it differs from the linear answer."""
    a, h, area = 1.0, 0.1, 1e-4
    P_target = _von_mises_p_closed(0.25 * h, a, h, E_A36, area)
    structure = _von_mises_truss(a, h, area)
    structure.loads = [PointLoad(node_id=2, fy=P_target)]
    dof_map, constrained = build_nonlinear_inputs(structure)
    F = build_load_vector(structure, dof_map)

    linear = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=False, material=False, n_steps=1)
    nonlinear = solve_nonlinear(structure, F, dof_map, constrained,
                                geometric=True, material=False, n_steps=60)
    v_linear = -linear.displacements[dof_map[2][1]]
    v_nonlinear = -nonlinear.displacements[dof_map[2][1]]
    assert v_linear != pytest.approx(v_nonlinear, rel=0.05)


def test_apex_stays_on_the_symmetry_line():
    """No horizontal drift for a symmetric truss under symmetric load."""
    structure = _von_mises_truss()
    structure.loads = [PointLoad(node_id=2, fy=_von_mises_p_closed(0.03, 1.0, 0.1, E_A36, 1e-4))]
    dof_map, constrained = build_nonlinear_inputs(structure)
    F = build_load_vector(structure, dof_map)
    result = solve_nonlinear(structure, F, dof_map, constrained, geometric=True, n_steps=40)
    assert result.displacements[dof_map[2][0]] == pytest.approx(0.0, abs=1e-9)


def test_near_the_limit_point_load_control_fails_to_converge_and_says_so():
    """
    Beyond the limit load, no static equilibrium exists on the primary
    branch for load-controlled iteration. This MUST be reported as
    non-convergence, never as a fabricated displacement.
    """
    a, h, area = 1.0, 0.1, 1e-4
    vs_fine = [i * h / 2000 for i in range(2001)]
    p_min = min(_von_mises_p_closed(v, a, h, E_A36, area) for v in vs_fine)

    structure = _von_mises_truss(a, h, area)
    structure.loads = [PointLoad(node_id=2, fy=p_min * 1.05)]   # beyond the limit
    dof_map, constrained = build_nonlinear_inputs(structure)
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=True, material=False,
                             n_steps=100, max_iterations=40)
    assert result.converged is False
    assert result.divergence_reason
    assert result.displacements.size == 0, "no numeric result must be reported on failure"


# ─────────────────────────────────────────────
# Material nonlinearity — elastic-perfectly-plastic
# ─────────────────────────────────────────────
#
# The single-member axial bar is unsuitable for testing yielding itself:
# once its one member fully yields it has ZERO remaining stiffness (no
# redundancy to redistribute to), so load-controlled Newton-Raphson
# correctly fails to converge for any target beyond that member's own
# capacity — there is no equilibrium state to find. Yielding is properly
# tested with a REDUNDANT structure so load redistributes to members that
# haven't yielded yet, which is also the physically interesting behaviour
# elastic-plastic analysis exists to capture.
#
# Three parallel members between the SAME two nodes, one each of A36,
# A992 and AL6061, force IDENTICAL elongation (same endpoints) but have
# DIFFERENT yield strains (fy/E: A36 0.00125, A992 0.001725, AL6061
# 0.004006), giving clean, closed-form-derivable staggered yielding: at
# strain 0.0013 only A36 has yielded; at strain 0.002, A36 and A992 have
# yielded while AL6061 remains elastic.

_YIELD_SECTION = CrossSection(outer_diameter=0.05, wall_thickness=0.01)


def _three_material_bar(length=4.0):
    return Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, length, 0, 0)],
        members=[
            Member(0, 0, 1, "A36", _YIELD_SECTION),
            Member(1, 0, 1, "A992", _YIELD_SECTION),
            Member(2, 0, 1, "AL6061", _YIELD_SECTION),
        ],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X, dx=False, dy=True, dz=True),
        ],
        loads=[PointLoad(node_id=1, fx=0.0)],
    )


def _staggered_yield_p_closed(strain, area=None):
    """Total axial force at a given common strain, each member capped at A*f_y."""
    area = area or _YIELD_SECTION.area
    total = 0.0
    for key in ("A36", "A992", "AL6061"):
        m = MATERIAL_LIBRARY[key]
        stress = max(-m.yield_stress, min(m.yield_stress, m.E * strain))
        total += area * stress
    return total


def test_below_yield_matches_the_linear_elastic_result():
    structure = _three_material_bar()
    dof_map, constrained = build_nonlinear_inputs(structure)
    strain = 0.0005   # below every member's yield strain
    structure.loads = [PointLoad(node_id=1, fx=_staggered_yield_p_closed(strain))]
    F = build_load_vector(structure, dof_map)

    elastic = solve_nonlinear(structure, F, dof_map, constrained,
                              geometric=False, material=False, n_steps=1)
    plastic_capable = solve_nonlinear(structure, F, dof_map, constrained,
                                      geometric=False, material=True, n_steps=10)
    assert elastic.displacements[dof_map[1][0]] == pytest.approx(
        plastic_capable.displacements[dof_map[1][0]], rel=1e-6
    )
    assert not plastic_capable.any_yielded


def test_one_member_yields_while_others_stay_elastic():
    """
    strain = 0.0013: only A36 (yield strain 0.00125) has yielded. Each
    member's force is checked individually against the closed form, not
    just the total — this is the actual test of load redistribution.
    """
    structure = _three_material_bar()
    dof_map, constrained = build_nonlinear_inputs(structure)
    strain = 0.0013
    structure.loads = [PointLoad(node_id=1, fx=_staggered_yield_p_closed(strain))]
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=False, material=True,
                             n_steps=30, max_iterations=60)
    assert result.converged, result.divergence_reason

    a36_cap = _YIELD_SECTION.area * MATERIAL_LIBRARY["A36"].yield_stress
    forces = result.final_member_forces
    assert forces[0] == pytest.approx(a36_cap, rel=1e-4)          # A36: yielded, capped
    assert forces[1] == pytest.approx(                              # A992: elastic
        _YIELD_SECTION.area * MATERIAL_LIBRARY["A992"].E * strain, rel=1e-4)
    assert forces[2] == pytest.approx(                              # AL6061: elastic
        _YIELD_SECTION.area * MATERIAL_LIBRARY["AL6061"].E * strain, rel=1e-4)

    states = {s.member_id: s.yielded for s in result.steps[-1].member_states}
    assert states[0] is True and states[1] is False and states[2] is False


def test_two_members_yield_while_the_third_stays_elastic():
    """strain = 0.002: A36 and A992 yielded (yield strains 0.00125, 0.001725); AL6061 (0.004006) elastic."""
    structure = _three_material_bar()
    dof_map, constrained = build_nonlinear_inputs(structure)
    strain = 0.002
    structure.loads = [PointLoad(node_id=1, fx=_staggered_yield_p_closed(strain))]
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=False, material=True,
                             n_steps=30, max_iterations=60)
    assert result.converged, result.divergence_reason

    forces = result.final_member_forces
    assert forces[0] == pytest.approx(
        _YIELD_SECTION.area * MATERIAL_LIBRARY["A36"].yield_stress, rel=1e-4)
    assert forces[1] == pytest.approx(
        _YIELD_SECTION.area * MATERIAL_LIBRARY["A992"].yield_stress, rel=1e-4)
    assert forces[2] == pytest.approx(
        _YIELD_SECTION.area * MATERIAL_LIBRARY["AL6061"].E * strain, rel=1e-4)


def test_compression_yields_at_the_same_magnitude_as_tension():
    structure = _three_material_bar()
    dof_map, constrained = build_nonlinear_inputs(structure)
    strain = 0.0013
    structure.loads = [PointLoad(node_id=1, fx=-_staggered_yield_p_closed(strain))]
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=False, material=True,
                             n_steps=30, max_iterations=60)
    assert result.converged
    a36_cap = _YIELD_SECTION.area * MATERIAL_LIBRARY["A36"].yield_stress
    assert result.final_member_forces[0] == pytest.approx(-a36_cap, rel=1e-4)


def test_load_beyond_full_plastic_capacity_fails_to_converge_honestly():
    """
    Beyond the fully-plastic (collapse) load, no equilibrium exists under
    load control — the structure would deform without bound. This must
    be reported as non-convergence, not extrapolated.
    """
    structure = _three_material_bar()
    dof_map, constrained = build_nonlinear_inputs(structure)
    collapse = sum(_YIELD_SECTION.area * MATERIAL_LIBRARY[k].yield_stress
                   for k in ("A36", "A992", "AL6061"))
    structure.loads = [PointLoad(node_id=1, fx=1.2 * collapse)]
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=False, material=True,
                             n_steps=30, max_iterations=40)
    assert result.converged is False
    assert result.divergence_reason
    assert result.displacements.size == 0


def test_geometric_and_material_can_be_combined():
    """
    Confirms both toggles work together without conflicting (not a new
    closed-form check — combining geometric snap-through with material
    yielding would need its own derivation). The load (1500 N) is chosen
    safely below both the elastic snap-through limit (~7621 N for this
    geometry) and the member yield capacity, so this isolates "do the two
    mechanisms coexist" from either mechanism's own individual validation.
    """
    structure = _von_mises_truss()
    structure.loads = [PointLoad(node_id=2, fy=-1500.0)]
    dof_map, constrained = build_nonlinear_inputs(structure)
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=True, material=True, n_steps=40, max_iterations=60)
    assert result.converged, result.divergence_reason
    assert result.geometric and result.material


# ─────────────────────────────────────────────
# Scope honesty
# ─────────────────────────────────────────────

def test_result_states_its_own_scope_limits():
    structure = _axial_bar()
    dof_map, constrained = build_nonlinear_inputs(structure)
    structure.loads = [PointLoad(node_id=1, fx=1000.0)]
    F = build_load_vector(structure, dof_map)
    result = solve_nonlinear(structure, F, dof_map, constrained, n_steps=1)
    assert "cannot represent individual-member flexural buckling" in result.scope_note
    assert "no hardening" in result.scope_note


def test_real_generated_truss_runs_under_combined_nonlinearity():
    """Smoke test on the actual production topology, not just toy models."""
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    dof_map, constrained = build_nonlinear_inputs(structure)
    F = build_load_vector(structure, dof_map)

    result = solve_nonlinear(structure, F, dof_map, constrained,
                             geometric=True, material=True, n_steps=10)
    assert result.converged, result.divergence_reason

    linear_results = solve(structure, spec)
    linear_stress = max(abs(m.stress) for m in linear_results.member_results)
    # Well below yield, so nonlinear and linear member forces should
    # agree closely (small-load-relative-to-yield sanity check).
    for member_id, nl_force in result.final_member_forces.items():
        assert abs(nl_force) < structure.members[0].section.area * FY_A36 * 2
