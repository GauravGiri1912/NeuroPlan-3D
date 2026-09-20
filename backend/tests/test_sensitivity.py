"""
Priority 4 — Deterministic sensitivity.

These tests pin the sensitivity engine against CLOSED-FORM expectations
for a linear-elastic determinate truss, not against whatever the code
happens to produce:

    displacement  delta ∝ P·L/(A·E)   ->  S(P) = +1, S(A) = S(E) = -1
    stress        sigma = F/A          ->  S(P) = +1, S(A) = -1, S(E) = 0
    weight        W = rho·A·L          ->  S(rho) = S(A) = +1, S(P) = 0

For an inverse relationship y = C/x the CENTRAL-DIFFERENCE estimate of
the normalised slope is not exactly -1; it is

    S = -1 / (1 - delta^2)

which is -1.0101... at delta = 0.1. The tests assert that exact value,
so a change in the differencing scheme cannot pass unnoticed.
"""
import math
import pytest

from server.core.analysis.sensitivity import (
    run_sensitivity, SensitivityParameter, DEFAULT_PERTURBATION,
    _thickness_for_area,
)
from server.core.fea.load_cases import DEFAULT_COMBINATION, LIVE_ONLY_COMBINATION
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, MATERIAL_LIBRARY


DELTA = DEFAULT_PERTURBATION
INVERSE_SLOPE = -1.0 / (1.0 - DELTA ** 2)     # -1.010101...


@pytest.fixture(scope="module")
def report():
    spec = EngineeringSpec()
    return run_sensitivity(generate_structure(spec), spec)


def _slope(report, parameter, output):
    entry = next(p for p in report.parameters if p.parameter is parameter)
    assert not entry.failed, entry.failure_reason
    return entry.outputs[output].normalised_slope


# ─────────────────────────────────────────────
# Closed-form physics
# ─────────────────────────────────────────────

def test_displacement_is_proportional_to_load(report):
    assert _slope(report, SensitivityParameter.LOAD, "max_displacement_mm") == \
        pytest.approx(1.0, abs=1e-6)


def test_stress_is_proportional_to_load(report):
    assert _slope(report, SensitivityParameter.LOAD, "max_stress_mpa") == \
        pytest.approx(1.0, abs=1e-6)


def test_displacement_is_inversely_proportional_to_youngs_modulus(report):
    assert _slope(report, SensitivityParameter.YOUNGS_MODULUS, "max_displacement_mm") == \
        pytest.approx(INVERSE_SLOPE, rel=1e-3)


def test_stress_does_not_depend_on_youngs_modulus(report):
    """
    In a statically determinate truss member forces come from statics
    alone, so sigma = F/A is independent of E. A non-zero slope here
    would indicate the stiffness and the stress recovery disagree about
    the material.
    """
    assert _slope(report, SensitivityParameter.YOUNGS_MODULUS, "max_stress_mpa") == \
        pytest.approx(0.0, abs=1e-6)


def test_stress_and_displacement_are_inversely_proportional_to_area(report):
    assert _slope(report, SensitivityParameter.CROSS_SECTION_AREA, "max_stress_mpa") == \
        pytest.approx(INVERSE_SLOPE, rel=1e-3)
    assert _slope(report, SensitivityParameter.CROSS_SECTION_AREA, "max_displacement_mm") == \
        pytest.approx(INVERSE_SLOPE, rel=1e-3)


def test_weight_is_proportional_to_area_and_density(report):
    """
    Tolerance note: AnalysisResults.total_weight_kg is rounded to 2 dp by
    the solver for display. On a ~1500 kg model that 0.01 kg quantum is
    amplified by the central difference (divide by 2*delta = 0.2) to

        0.01 / (1497 * 0.2) = 3.34e-5

    so 5e-5 is the derived quantization bound, not a loosened tolerance.
    Computed on unrounded weights the slope is 1.000000000000008.
    """
    quantization_bound = 5e-5
    assert _slope(report, SensitivityParameter.CROSS_SECTION_AREA, "total_weight_kg") == \
        pytest.approx(1.0, abs=quantization_bound)
    assert _slope(report, SensitivityParameter.MATERIAL_DENSITY, "total_weight_kg") == \
        pytest.approx(1.0, abs=quantization_bound)


def test_weight_does_not_depend_on_load(report):
    assert _slope(report, SensitivityParameter.LOAD, "total_weight_kg") == \
        pytest.approx(0.0, abs=1e-9)


def test_density_does_not_affect_stress_when_self_weight_is_excluded(report):
    """Baseline runs LIVE-only, so density is inert in the structural result."""
    assert _slope(report, SensitivityParameter.MATERIAL_DENSITY, "max_stress_mpa") == \
        pytest.approx(0.0, abs=1e-9)


def test_density_does_affect_stress_once_self_weight_is_included():
    """The converse: with dead load on, density must matter."""
    spec = EngineeringSpec()
    rep = run_sensitivity(
        generate_structure(spec), spec,
        parameters=[SensitivityParameter.MATERIAL_DENSITY],
        combination=DEFAULT_COMBINATION,
    )
    slope = rep.parameters[0].outputs["max_stress_mpa"].normalised_slope
    assert abs(slope) > 1e-4, "self-weight is on, so density must influence stress"


def test_deeper_truss_reduces_stress_and_displacement(report):
    """Increasing structural depth must stiffen the truss, not weaken it."""
    assert _slope(report, SensitivityParameter.GEOMETRY_HEIGHT, "max_stress_mpa") < 0
    assert _slope(report, SensitivityParameter.GEOMETRY_HEIGHT, "max_displacement_mm") < 0


# ─────────────────────────────────────────────
# The area perturbation must actually change area
# ─────────────────────────────────────────────

def test_thickness_solver_produces_the_requested_area_exactly():
    from server.models.structure import CrossSection
    section = CrossSection(outer_diameter=0.114, wall_thickness=0.006)
    target = section.area * 1.10

    t = _thickness_for_area(section.outer_diameter, target)
    assert CrossSection(0.114, t).area == pytest.approx(target, rel=1e-12)


def test_scaling_thickness_naively_would_not_have_scaled_area():
    """
    Documents why the quadratic solve is needed: scaling t by 1.1 does
    NOT give 1.1x the area, so the naive approach would mislabel the
    perturbation size.
    """
    from server.models.structure import CrossSection
    base = CrossSection(outer_diameter=0.114, wall_thickness=0.006)
    naive = CrossSection(outer_diameter=0.114, wall_thickness=0.006 * 1.1)
    assert naive.area / base.area != pytest.approx(1.10, rel=1e-3)


def test_shared_cross_sections_are_perturbed_once_not_once_per_member():
    """
    Regression: the generator gives every member the SAME CrossSection
    object. Scaling per member compounded the change to scale^n and
    produced a normalised slope near -65 instead of -1.
    """
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    assert len({id(m.section) for m in structure.members}) == 1, \
        "fixture assumes shared sections; if this changes, so must the guard"

    slope = _slope(
        run_sensitivity(structure, spec,
                        parameters=[SensitivityParameter.CROSS_SECTION_AREA]),
        SensitivityParameter.CROSS_SECTION_AREA, "max_displacement_mm",
    )
    assert slope == pytest.approx(INVERSE_SLOPE, rel=1e-3)


# ─────────────────────────────────────────────
# Isolation and honesty
# ─────────────────────────────────────────────

def test_material_library_is_restored_after_perturbation():
    """A perturbed run must not leak into later analyses."""
    spec = EngineeringSpec()
    before_e = MATERIAL_LIBRARY["A36"].E
    before_rho = MATERIAL_LIBRARY["A36"].density

    run_sensitivity(generate_structure(spec), spec)

    assert MATERIAL_LIBRARY["A36"].E == before_e
    assert MATERIAL_LIBRARY["A36"].density == before_rho


def test_report_declares_itself_non_statistical(report):
    assert report.is_statistical is False
    assert "NOT A CONFIDENCE INTERVAL" in report.statistical_disclaimer
    assert "coverage probability" in report.statistical_disclaimer


def test_report_states_the_oat_interaction_limitation(report):
    assert "interaction" in report.interaction_limitation.lower()


def test_dominant_parameter_is_identified_per_output(report):
    assert report.dominant["max_reaction_n"] == "Applied load magnitude"
    assert report.dominant["total_weight_kg"] in (
        "Cross-sectional area", "Material density",
    )


def test_min_max_bracket_the_baseline_for_a_monotonic_parameter(report):
    entry = next(p for p in report.parameters
                 if p.parameter is SensitivityParameter.LOAD)
    out = entry.outputs["max_displacement_mm"]
    assert out.minimum < out.baseline < out.maximum
    assert out.change_percent > 0


def test_invalid_perturbation_is_rejected():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    for bad in (0.0, 1.0, -0.1, 2.0):
        with pytest.raises(ValueError):
            run_sensitivity(structure, spec, perturbation=bad)


def test_unsolvable_perturbation_is_reported_not_estimated():
    """
    If a perturbed model cannot be solved, the engine must say so rather
    than extrapolating a number from the baseline.
    """
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    # A 99% area reduction drives the section to near-zero stiffness.
    rep = run_sensitivity(
        structure, spec, perturbation=0.999,
        parameters=[SensitivityParameter.CROSS_SECTION_AREA],
    )
    entry = rep.parameters[0]
    if entry.failed:
        assert "UNAVAILABLE" in entry.failure_reason
    else:
        # It solved; then every reported number must still be real.
        assert all(math.isfinite(o.normalised_slope) for o in entry.outputs.values())
