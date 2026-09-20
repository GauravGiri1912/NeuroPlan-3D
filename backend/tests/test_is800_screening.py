"""
Priority 6 — IS 800:2007 screening checks.

Hand-verified worked example (CHS 114.3 x 6.4, Fe 250, KL/r = 87.2247,
buckling class a, alpha = 0.21):

    f_cc   = pi^2 * 200e9 / 87.2247^2        = 259.45 MPa
    lambda = sqrt(250 / 259.45)              = 0.98162
    phi    = 0.5[1 + 0.21(0.98162-0.2) + 0.98162^2]
           = 0.5[1 + 0.164140 + 0.963578]    = 1.063859
    chi    = 1/(1.063859 + sqrt(1.131796 - 0.963578))
           = 1/1.474003                       = 0.678424
    f_cd   = 0.678424 * 250/1.10              = 154.19 MPa

Section classification:
    epsilon = sqrt(250/250) = 1.0
    d/t     = 114.3/6.4     = 17.86  <= 42  -> PLASTIC
"""
import math
import pytest

from server.core.codes.is800_2007 import (
    screen_structure, design_compressive_stress, classify_chs, epsilon,
    check_tension_yielding, check_compression, check_slenderness_limit,
    SectionClass, CheckStatus, GAMMA_M0, GAMMA_M1, IMPERFECTION_FACTOR,
    SLENDERNESS_LIMIT_COMPRESSION, SLENDERNESS_LIMIT_TENSION,
    IMPLEMENTED_CLAUSES, UNSUPPORTED_CLAUSES, CODE_NAME, CODE_EDITION,
)
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, CrossSection

FY = 250e6
E = 200e9
SECTION = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)
LAMBDA_EFF = 87.2247


# ─────────────────────────────────────────────
# Partial safety factors (cl. 5.4.1, Table 5)
# ─────────────────────────────────────────────

def test_partial_safety_factors_match_the_code():
    assert GAMMA_M0 == 1.10
    assert GAMMA_M1 == 1.25


def test_imperfection_factors_match_table_7():
    assert IMPERFECTION_FACTOR == {"a": 0.21, "b": 0.34, "c": 0.49, "d": 0.76}


# ─────────────────────────────────────────────
# Section classification (cl. 3.7.2, Table 2)
# ─────────────────────────────────────────────

def test_epsilon_is_one_for_fe250():
    assert epsilon(250e6) == pytest.approx(1.0)


def test_epsilon_reduces_for_higher_grade_steel():
    assert epsilon(345e6) == pytest.approx(math.sqrt(250.0 / 345.0))
    assert epsilon(345e6) < epsilon(250e6)


def test_reference_chs_is_classified_plastic():
    assert classify_chs(0.1143, 0.0064, FY) is SectionClass.PLASTIC


def test_thin_walled_tube_is_classified_slender():
    """d/t = 300 exceeds the 146*epsilon^2 semi-compact limit."""
    assert classify_chs(0.300, 0.001, FY) is SectionClass.SLENDER


def test_classification_boundaries_follow_table_2():
    """d/t just inside vs just outside the 42*eps^2 plastic limit."""
    d = 0.42
    assert classify_chs(d, d / 41.9, FY) is SectionClass.PLASTIC
    assert classify_chs(d, d / 42.1, FY) is not SectionClass.PLASTIC


# ─────────────────────────────────────────────
# Compression (cl. 7.1.2.1) vs hand calculation
# ─────────────────────────────────────────────

def test_design_compressive_stress_matches_hand_calculation():
    f_cd, parts = design_compressive_stress(FY, E, LAMBDA_EFF, "a")

    assert parts["f_cc"] == pytest.approx(259.45e6, rel=1e-4)
    assert parts["lambda"] == pytest.approx(0.98162, rel=1e-4)
    assert parts["phi"] == pytest.approx(1.063859, rel=1e-5)
    assert parts["chi"] == pytest.approx(0.678424, rel=1e-5)
    assert f_cd == pytest.approx(154.19e6, rel=1e-4)


def test_design_compressive_stress_never_exceeds_the_yield_limit():
    """chi <= 1, so f_cd <= f_y/gamma_m0 at every slenderness."""
    cap = FY / GAMMA_M0
    for slenderness in (0.0, 1.0, 10.0, 50.0, 87.2, 150.0, 300.0):
        f_cd, _ = design_compressive_stress(FY, E, slenderness, "a")
        assert f_cd <= cap * (1.0 + 1e-12)


def test_stocky_column_reaches_the_squash_capacity():
    f_cd, _ = design_compressive_stress(FY, E, 0.0, "a")
    assert f_cd == pytest.approx(FY / GAMMA_M0)


def test_design_stress_decreases_monotonically_with_slenderness():
    values = [design_compressive_stress(FY, E, s, "a")[0]
              for s in (20.0, 60.0, 100.0, 140.0, 200.0)]
    assert values == sorted(values, reverse=True)


def test_worse_buckling_class_gives_lower_capacity():
    """Larger imperfection factor alpha must reduce f_cd."""
    stresses = [design_compressive_stress(FY, E, LAMBDA_EFF, c)[0]
                for c in ("a", "b", "c", "d")]
    assert stresses == sorted(stresses, reverse=True)


def test_is800_is_more_conservative_than_raw_euler_in_the_inelastic_range():
    """
    The reason this module exists alongside the Euler screening: at
    lambda = 87 the Euler stress is unconservative. The code curve must
    come out materially below it.
    """
    from server.core.analysis.buckling import screen_member

    euler = screen_member(
        member_id=0, axial_force=-1.0, length=20.0 / 6.0,
        area=SECTION.area, inertia=SECTION.moment_of_inertia,
        radius_of_gyration=SECTION.radius_of_gyration, E=E, fy=FY,
    )
    f_cd, _ = design_compressive_stress(FY, E, LAMBDA_EFF, "a")

    assert f_cd < euler.euler_critical_stress
    assert f_cd / euler.euler_critical_stress < 0.7


# ─────────────────────────────────────────────
# Tension (cl. 6.2)
# ─────────────────────────────────────────────

def test_tension_yield_capacity_matches_the_clause():
    check = check_tension_yielding(0, 100_000.0, SECTION.area, FY)
    assert check.capacity == pytest.approx(SECTION.area * FY / GAMMA_M0)
    assert check.clause == "cl. 6.2"
    assert check.status is CheckStatus.PASS


def test_overloaded_tension_member_fails():
    capacity = SECTION.area * FY / GAMMA_M0
    check = check_tension_yielding(0, capacity * 1.5, SECTION.area, FY)
    assert check.dc_ratio == pytest.approx(1.5, rel=1e-9)
    assert check.status is CheckStatus.FAIL


def test_tension_check_declares_that_rupture_and_block_shear_are_not_done():
    check = check_tension_yielding(0, 100_000.0, SECTION.area, FY)
    assert "6.3" in check.note and "6.4" in check.note
    assert "govern" in check.note


# ─────────────────────────────────────────────
# Slenderness limits (cl. 3.8, Table 3)
# ─────────────────────────────────────────────

def test_compression_slenderness_limit_is_180():
    assert check_slenderness_limit(0, 179.0, True).status is CheckStatus.PASS
    assert check_slenderness_limit(0, 181.0, True).status is CheckStatus.FAIL
    assert SLENDERNESS_LIMIT_COMPRESSION == 180.0


def test_tension_slenderness_limit_is_400():
    assert check_slenderness_limit(0, 399.0, False).status is CheckStatus.PASS
    assert check_slenderness_limit(0, 401.0, False).status is CheckStatus.FAIL
    assert SLENDERNESS_LIMIT_TENSION == 400.0


# ─────────────────────────────────────────────
# Reporting and honesty
# ─────────────────────────────────────────────

def _report():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    return screen_structure(structure, solve(structure, spec).member_results)


def test_every_check_carries_the_full_evidence_set():
    """Code, edition, clause, inputs, equation, demand, capacity, D/C, status."""
    for member in _report().members:
        for check in member.checks:
            assert check.code == CODE_NAME
            assert check.edition == CODE_EDITION
            assert check.clause.startswith("cl.")
            assert check.equation
            assert check.inputs
            assert check.status in set(CheckStatus)


def test_report_is_titled_screening_not_compliance():
    report = _report()
    assert report.title == "IS 800:2007 SCREENING CHECKS"
    assert "not a compliance check" in report.compliance_disclaimer
    assert "does NOT establish" in report.compliance_disclaimer


def test_unsupported_clauses_are_declared_explicitly():
    report = _report()
    joined = " ".join(report.unsupported_clauses).lower()
    for topic in ("block shear", "fatigue", "fire", "connection", "rupture"):
        assert topic in joined


def test_implemented_clause_list_is_published():
    report = _report()
    assert report.implemented_clauses == IMPLEMENTED_CLAUSES
    assert any("7.1.2" in c for c in report.implemented_clauses)
    assert any("6.2" in c for c in report.implemented_clauses)


def test_load_factor_omission_is_declared():
    """
    Analysis runs unfactored by default; pretending otherwise would be
    the most dangerous silent gap in a code check.
    """
    joined = " ".join(UNSUPPORTED_CLAUSES)
    assert "partial safety factors for LOADS are NOT applied" in joined


def test_every_member_gets_a_check_and_a_section_class():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    report = screen_structure(structure, solve(structure, spec).member_results)

    assert len(report.members) == len(structure.members)
    for member in report.members:
        assert member.checks
        assert member.section_class in set(SectionClass)


def test_governing_member_has_the_highest_demand_capacity_ratio():
    report = _report()
    governing = next(m for m in report.members
                     if m.member_id == report.governing_member_id)
    assert governing.governing.dc_ratio == pytest.approx(report.max_dc_ratio)
