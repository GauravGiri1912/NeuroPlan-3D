"""
Priority 1 — Self-weight, and Priority 2 — Load case engine.

The spec requires three specific proofs:
  1. weight = 0 reproduces the previous (weightless) result
  2. non-zero density changes reactions / stresses / displacements
  3. reported mass and applied weight agree

Plus the load-case guarantees: nothing enters the solver outside a named
case, and an unsupported case cannot contribute force.
"""
import math
import pytest

from server.core.fea.solver import solve
from server.core.fea.load_cases import (
    GRAVITY, compute_self_weight, build_load_cases, collect_factored_loads,
    LoadCombination, DEFAULT_COMBINATION, LIVE_ONLY_COMBINATION,
)
from server.core.generator.topology import generate_structure
from server.models.structure import (
    EngineeringSpec, LoadCaseType, MATERIAL_LIBRARY, Node, Member, Support,
    SupportType, PointLoad, Structure, CrossSection,
)


def _spec() -> EngineeringSpec:
    return EngineeringSpec()


def _structure() -> Structure:
    return generate_structure(_spec())


# ─────────────────────────────────────────────
# Formulation
# ─────────────────────────────────────────────

def test_single_member_self_weight_matches_hand_calculation():
    """
    One horizontal bar, 10 m long, A36 steel (rho = 7850), CHS 0.2 m OD /
    0.01 m wall.

        A = pi*(0.1^2 - 0.09^2)      = 5.96903e-3 m^2
        mass = rho*A*L               = 7850 * A * 10
        weight = mass * 9.80665
        each node gets weight/2 downward
    """
    section = CrossSection(outer_diameter=0.2, wall_thickness=0.01)
    area = math.pi * (0.1 ** 2 - 0.09 ** 2)
    assert section.area == pytest.approx(area)

    structure = Structure(
        nodes=[Node(0, 0.0, 0.0, 0.0), Node(1, 10.0, 0.0, 0.0)],
        members=[Member(0, 0, 1, "A36", section)],
        supports=[], loads=[],
    )
    sw = compute_self_weight(structure)

    expected_mass = 7850.0 * area * 10.0
    expected_weight = expected_mass * GRAVITY

    assert sw.total_mass_kg == pytest.approx(expected_mass)
    assert sw.total_weight_n == pytest.approx(expected_weight)
    assert len(sw.nodal_loads) == 2
    for load in sw.nodal_loads:
        assert load.fy == pytest.approx(-expected_weight / 2.0)
        assert load.fx == 0.0 and load.fz == 0.0
        assert load.case is LoadCaseType.DEAD


def test_reported_mass_and_applied_weight_agree():
    """Spec requirement 3: the displayed total must equal what was applied."""
    sw = compute_self_weight(_structure())
    assert sw.applied_weight_n() == pytest.approx(sw.total_weight_n, rel=1e-12)
    assert sw.total_weight_n == pytest.approx(sw.total_mass_kg * GRAVITY)


def test_self_weight_total_matches_structure_total_weight():
    """Cross-check against the independently-written Structure.total_weight()."""
    structure = _structure()
    sw = compute_self_weight(structure)
    assert sw.total_mass_kg == pytest.approx(structure.total_weight())


def test_per_member_breakdown_sums_to_the_reported_total():
    """The audit trail must actually add up to the headline number."""
    sw = compute_self_weight(_structure())
    assert sum(m.mass_kg for m in sw.member_weights) == pytest.approx(sw.total_mass_kg)
    assert sum(m.weight_n for m in sw.member_weights) == pytest.approx(sw.total_weight_n)


def test_unknown_material_contributes_zero_and_is_reported():
    """A member with no material must not silently vanish from the audit."""
    structure = _structure()
    structure.members[0].material_key = "UNOBTAINIUM"
    sw = compute_self_weight(structure)

    assert structure.members[0].id in sw.unknown_material_members
    entry = next(m for m in sw.member_weights if m.member_id == structure.members[0].id)
    assert entry.known_material is False
    assert entry.mass_kg == 0.0


# ─────────────────────────────────────────────
# Spec requirement 1 & 2: effect on the solve
# ─────────────────────────────────────────────

def test_zero_gravity_reproduces_the_weightless_result():
    """Spec requirement 1: weight = 0 gives back the previous result."""
    structure, spec = _structure(), _spec()

    weightless = solve(structure, spec, combination=LIVE_ONLY_COMBINATION)
    zero_g = solve(
        structure, spec,
        combination=LoadCombination(name="zero-g", factors={
            LoadCaseType.DEAD: 0.0, LoadCaseType.LIVE: 1.0,
        }),
        include_self_weight=True,
    )

    assert zero_g.diagnosis.max_displacement_mm == pytest.approx(
        weightless.diagnosis.max_displacement_mm, rel=1e-12
    )
    for a, b in zip(zero_g.member_results, weightless.member_results):
        assert a.axial_force == pytest.approx(b.axial_force, rel=1e-12, abs=1e-9)


def test_nonzero_density_changes_reactions_stresses_and_displacements():
    """Spec requirement 2. Self-weight must actually reach the solution."""
    structure, spec = _structure(), _spec()

    without = solve(structure, spec, combination=LIVE_ONLY_COMBINATION)
    with_sw = solve(structure, spec, combination=DEFAULT_COMBINATION)

    total_r_without = sum(r.ry for r in without.reactions)
    total_r_with = sum(r.ry for r in with_sw.reactions)
    assert total_r_with > total_r_without, "self-weight must increase vertical reaction"

    sw = compute_self_weight(structure)
    assert total_r_with - total_r_without == pytest.approx(sw.total_weight_n, rel=1e-9)

    assert with_sw.diagnosis.max_displacement_mm != pytest.approx(
        without.diagnosis.max_displacement_mm
    )
    assert with_sw.diagnosis.max_stress_ratio != pytest.approx(
        without.diagnosis.max_stress_ratio
    )


def test_self_weight_preserves_global_equilibrium():
    """
    The independent equilibrium check must still pass with dead load on —
    i.e. the same force vector was used for both the solve and the check.
    """
    results = solve(_structure(), _spec(), combination=DEFAULT_COMBINATION)
    assert results.equilibrium.passed
    assert results.checks.equilibrium


def test_denser_material_produces_more_self_weight():
    """Monotonicity: steel must weigh more than aluminium, same geometry."""
    steel = _structure()
    alu = _structure()
    for m in alu.members:
        m.material_key = "AL6061"

    assert MATERIAL_LIBRARY["AL6061"].density < MATERIAL_LIBRARY["A36"].density
    assert compute_self_weight(alu).total_weight_n < compute_self_weight(steel).total_weight_n


# ─────────────────────────────────────────────
# Priority 2 — load cases
# ─────────────────────────────────────────────

def test_every_case_is_listed_even_when_unsupported():
    cases, _ = build_load_cases(_structure())
    listed = {c.case_type for c in cases}
    assert listed == set(LoadCaseType), "a case must never be omitted from the summary"


def test_thermal_and_settlement_are_supported_but_inactive_when_not_applied():
    """
    Both were implemented in Priority 8, so they are now SUPPORTED. They
    must still report `active = False` when no temperature change or
    settlement is supplied — supported is not the same as applied.
    """
    cases, _ = build_load_cases(_structure())
    for case_type in (LoadCaseType.THERMAL, LoadCaseType.SETTLEMENT):
        case = next(c for c in cases if c.case_type is case_type)
        assert case.supported is True
        assert case.active is False
        assert len(case.limitations) > 40, "must still state what is NOT modelled"


def test_thermal_case_becomes_active_when_a_temperature_change_is_applied():
    from server.core.fea.thermal import ThermalLoadCase

    cases, _ = build_load_cases(_structure(), thermal=ThermalLoadCase(delta_t=35.0))
    thermal_case = next(c for c in cases if c.case_type is LoadCaseType.THERMAL)
    assert thermal_case.active is True
    assert any("35" in a for a in thermal_case.assumptions)


def test_settlement_case_becomes_active_when_a_settlement_is_applied():
    from server.core.fea.thermal import SupportSettlement

    structure = _structure()
    cases, _ = build_load_cases(
        structure,
        settlements=[SupportSettlement(node_id=structure.supports[0].node_id, dy=-0.01)],
    )
    case = next(c for c in cases if c.case_type is LoadCaseType.SETTLEMENT)
    assert case.active is True


def test_thermal_limitation_states_it_is_invalid_for_fire():
    cases, _ = build_load_cases(_structure())
    case = next(c for c in cases if c.case_type is LoadCaseType.THERMAL)
    assert "fire" in case.limitations.lower()


def test_settlement_limitation_states_there_is_no_soil_model():
    cases, _ = build_load_cases(_structure())
    case = next(c for c in cases if c.case_type is LoadCaseType.SETTLEMENT)
    assert "soil model" in case.limitations.lower()


def test_an_unsupported_case_contributes_no_force_even_with_a_factor():
    """A combination cannot conjure physics the solver does not implement."""
    structure = _structure()
    cases, _ = build_load_cases(structure)

    greedy = LoadCombination(
        name="tries to use thermal",
        factors={LoadCaseType.THERMAL: 1.5, LoadCaseType.SETTLEMENT: 1.5},
    )
    assert collect_factored_loads(cases, greedy) == []


def test_load_factors_scale_the_applied_force_exactly():
    structure = _structure()
    cases, _ = build_load_cases(structure, include_self_weight=False)

    single = collect_factored_loads(cases, LoadCombination("1.0", {LoadCaseType.LIVE: 1.0}))
    double = collect_factored_loads(cases, LoadCombination("2.0", {LoadCaseType.LIVE: 2.0}))

    assert sum(l.fy for l in double) == pytest.approx(2.0 * sum(l.fy for l in single))


def test_summary_total_matches_the_force_actually_assembled():
    """
    The displayed combination total must equal the sum of the factored
    loads — so the UI number is the solver's number, not a parallel one.
    """
    structure = _structure()
    cases, sw = build_load_cases(structure)
    factored = collect_factored_loads(cases, DEFAULT_COMBINATION)

    from server.core.fea.load_cases import summarize_load_cases
    summary = summarize_load_cases(cases, DEFAULT_COMBINATION, sw)

    assert summary.total_applied_fy == pytest.approx(sum(l.fy for l in factored))
    assert summary.total_applied_fx == pytest.approx(sum(l.fx for l in factored))
    assert summary.total_applied_fz == pytest.approx(sum(l.fz for l in factored))


def test_solver_reports_the_load_summary_it_used():
    results = solve(_structure(), _spec(), combination=DEFAULT_COMBINATION)
    summary = results.load_summary

    assert summary is not None
    assert summary.combination_name == DEFAULT_COMBINATION.name
    assert summary.self_weight.included is True
    assert summary.self_weight.consistent, "reported mass*g must equal applied weight"

    dead = next(c for c in summary.cases if c.case_type == "dead")
    assert dead.active and dead.factor == 1.0
    assert dead.resultant_fy < 0, "dead load must act downward"


def test_live_only_run_reports_self_weight_as_excluded():
    """The weightless case must SAY it is weightless, not omit the topic."""
    results = solve(_structure(), _spec(), combination=LIVE_ONLY_COMBINATION)
    assert results.load_summary.self_weight.included is False
    dead = next(c for c in results.load_summary.cases if c.case_type == "dead")
    assert dead.factor == 0.0


def test_default_solve_is_weightless_for_benchmark_compatibility():
    """
    Calling solve() without a combination must stay LIVE-only, so the
    hand-calculation benchmarks keep comparing like with like.
    """
    results = solve(_structure(), _spec())
    assert results.load_summary.self_weight.included is False
