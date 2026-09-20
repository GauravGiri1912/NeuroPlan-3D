"""
Fire screening: elevated-temperature strength/stiffness reduction.

Table values pinned to the exact EN 1993-1-2 Table 3.1 points, plus
interpolation between them (using the midpoint of 500C/600C as a case
where hand-computed linear interpolation is trivial to verify).
"""
import copy
import pytest

from server.core.codes.fire import (
    yield_reduction_factor, modulus_reduction_factor, reduced_properties,
    screen_fire, SOURCE_CITATION,
)
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, MATERIAL_LIBRARY


def test_reduction_factors_at_table_points_match_exactly():
    assert yield_reduction_factor(20) == pytest.approx(1.00)
    assert yield_reduction_factor(500) == pytest.approx(0.78)
    assert yield_reduction_factor(600) == pytest.approx(0.47)
    assert yield_reduction_factor(1200) == pytest.approx(0.00)
    assert modulus_reduction_factor(20) == pytest.approx(1.00)
    assert modulus_reduction_factor(600) == pytest.approx(0.31)


def test_interpolation_at_midpoint_is_the_linear_average():
    assert modulus_reduction_factor(550) == pytest.approx((0.60 + 0.31) / 2, rel=1e-9)
    assert yield_reduction_factor(550) == pytest.approx((0.78 + 0.47) / 2, rel=1e-9)


def test_below_20c_clamps_to_full_strength():
    assert yield_reduction_factor(-40) == pytest.approx(1.00)
    assert modulus_reduction_factor(0) == pytest.approx(1.00)


def test_above_1200c_clamps_to_zero():
    assert yield_reduction_factor(1500) == pytest.approx(0.0)
    assert modulus_reduction_factor(3000) == pytest.approx(0.0)


def test_reduction_factors_are_monotonically_non_increasing_with_temperature():
    temps = [20, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200]
    ky = [yield_reduction_factor(t) for t in temps]
    ke = [modulus_reduction_factor(t) for t in temps]
    assert ky == sorted(ky, reverse=True)
    assert ke == sorted(ke, reverse=True)


def test_reduced_properties_scale_correctly():
    props = reduced_properties("A36", fy_pa=250e6, e_pa=200e9, temperature_c=600)
    assert props.reduced_fy_pa == pytest.approx(250e6 * 0.47, rel=1e-9)
    assert props.reduced_e_pa == pytest.approx(200e9 * 0.31, rel=1e-9)


def test_500_degrees_leaves_yield_strength_untouched():
    """k_y,theta = 1.00 up to 400C exactly, per the table."""
    props = reduced_properties("A36", fy_pa=250e6, e_pa=200e9, temperature_c=400)
    assert props.reduced_fy_pa == pytest.approx(250e6, rel=1e-9)
    assert props.reduced_e_pa == pytest.approx(200e9 * 0.70, rel=1e-9)


# ─────────────────────────────────────────────
# Re-solve at elevated temperature (real solver, reduced material)
# ─────────────────────────────────────────────

def test_elevated_temperature_resolve_increases_deflection():
    """Reduced E must produce MORE deflection under the same load."""
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    cold = solve(structure, spec)

    hot_materials = {
        key: type(m)(key=m.key, name=m.name, E=m.E * modulus_reduction_factor(600),
                     yield_stress=m.yield_stress, density=m.density)
        for key, m in MATERIAL_LIBRARY.items()
    }
    original = dict(MATERIAL_LIBRARY)
    try:
        MATERIAL_LIBRARY.update(hot_materials)
        hot = solve(structure, spec)
    finally:
        MATERIAL_LIBRARY.clear()
        MATERIAL_LIBRARY.update(original)

    assert hot.diagnosis.max_displacement_mm > cold.diagnosis.max_displacement_mm
    # E reduced to 31% -> displacement should scale ~ 1/0.31
    ratio = hot.diagnosis.max_displacement_mm / cold.diagnosis.max_displacement_mm
    assert ratio == pytest.approx(1.0 / modulus_reduction_factor(600), rel=1e-6)


def test_fire_screening_report_flags_overstressed_members_at_high_temperature():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    results = solve(structure, spec)

    material_key_by_member = {m.id: m.material_key for m in structure.members}
    fy_by_material = {k: m.yield_stress for k, m in MATERIAL_LIBRARY.items()}
    e_by_material = {k: m.E for k, m in MATERIAL_LIBRARY.items()}

    cool_report = screen_fire(results.member_results, temperature_c=20.0,
                              fy_by_member={}, material_key_by_member=material_key_by_member,
                              original_e_by_material=e_by_material,
                              original_fy_by_material=fy_by_material)
    hot_report = screen_fire(results.member_results, temperature_c=700.0,
                             fy_by_member={}, material_key_by_member=material_key_by_member,
                             original_e_by_material=e_by_material,
                             original_fy_by_material=fy_by_material)

    assert hot_report.max_utilisation > cool_report.max_utilisation
    assert hot_report.n_failed >= cool_report.n_failed


def test_report_cites_eurocode_not_a_fabricated_is800_table():
    from server.core.codes.fire import FireScreeningReport
    report = FireScreeningReport()
    assert "EN 1993-1-2" in report.source_citation
    assert "does not publish its own" in report.source_citation
    assert "Cross-check" in report.source_citation


def test_report_states_it_excludes_heating_rate_and_insulation():
    from server.core.codes.fire import FireScreeningReport
    report = FireScreeningReport()
    joined = report.disclaimer.lower()
    assert "heating-rate" in joined or "insulation" in joined
    assert "uniform temperature" in joined
