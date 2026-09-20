"""
Priority 5 — Buckling screening.

Pinned against hand calculations, not against current output.

Reference member (CHS 114.3 x 6.4, A36 steel, L = 3.3333 m, K = 1.0):

    r_out = 0.05715 m,  r_in = 0.05075 m
    A     = pi*(r_out^2 - r_in^2)          = 2.1694582e-3 m^2
    I     = pi/4*(r_out^4 - r_in^4)        = 3.1683229e-6 m^4
    r     = sqrt(I/A)                      = 0.038215458 m
    lambda= K*L/r = 3.333333/0.038215458   = 87.2247
    P_cr  = pi^2*E*I/(K*L)^2               = 562.862 kN

Transition slenderness for A36 (E = 200 GPa, fy = 250 MPa):

    lambda_c = pi*sqrt(2E/fy) = pi*sqrt(1600) = pi*40 = 125.66
"""
import math
import pytest

from server.core.analysis.buckling import (
    screen_member, screen_structure, transition_slenderness,
    ColumnClass, ScreeningStatus, DEFAULT_K,
    K_PINNED_PINNED, K_FIXED_FIXED, SHORT_COLUMN_SLENDERNESS,
)
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, CrossSection, MATERIAL_LIBRARY

E_A36 = 200e9
FY_A36 = 250e6
SECTION = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)
LENGTH = 20.0 / 6.0     # 6 panels over a 20 m span


def _screen(axial_force, length=LENGTH, k=DEFAULT_K, E=E_A36, fy=FY_A36,
            section=SECTION):
    return screen_member(
        member_id=0, axial_force=axial_force, length=length,
        area=section.area, inertia=section.moment_of_inertia,
        radius_of_gyration=section.radius_of_gyration,
        E=E, fy=fy, k_factor=k,
    )


# ─────────────────────────────────────────────
# Formulation against hand calculation
# ─────────────────────────────────────────────

def test_section_properties_match_hand_calculation():
    assert SECTION.area == pytest.approx(2.1694582e-3, rel=1e-6)
    assert SECTION.moment_of_inertia == pytest.approx(3.1683229e-6, rel=1e-6)
    assert SECTION.radius_of_gyration == pytest.approx(0.038215458, rel=1e-6)


def test_slenderness_matches_hand_calculation():
    s = _screen(-100_000.0)
    assert s.slenderness == pytest.approx(87.2247, rel=1e-5)


def test_euler_critical_load_matches_hand_calculation():
    s = _screen(-100_000.0)
    assert s.euler_critical_load == pytest.approx(562_862.0, rel=1e-5)


def test_euler_critical_stress_is_consistent_with_critical_load():
    """sigma_cr = pi^2 E / lambda^2 must equal P_cr / A."""
    s = _screen(-100_000.0)
    assert s.euler_critical_stress == pytest.approx(
        s.euler_critical_load / SECTION.area, rel=1e-9
    )


def test_transition_slenderness_matches_closed_form():
    assert transition_slenderness(E_A36, FY_A36) == pytest.approx(math.pi * 40.0, rel=1e-9)
    assert transition_slenderness(E_A36, FY_A36) == pytest.approx(125.66, rel=1e-3)


# ─────────────────────────────────────────────
# Effective length factor
# ─────────────────────────────────────────────

def test_effective_length_uses_k_factor():
    s = _screen(-100_000.0, k=K_FIXED_FIXED)
    assert s.effective_length == pytest.approx(K_FIXED_FIXED * LENGTH)
    assert s.slenderness == pytest.approx(K_FIXED_FIXED * LENGTH / SECTION.radius_of_gyration)


def test_fixed_ends_quadruple_the_euler_load_relative_to_pinned():
    """P_cr ∝ 1/K^2, so K = 0.5 gives 4x the pinned capacity."""
    pinned = _screen(-100_000.0, k=K_PINNED_PINNED)
    fixed = _screen(-100_000.0, k=K_FIXED_FIXED)
    assert fixed.euler_critical_load == pytest.approx(4.0 * pinned.euler_critical_load, rel=1e-9)


def test_default_k_is_pinned_because_the_solver_is_pin_jointed():
    assert DEFAULT_K == K_PINNED_PINNED == 1.0


# ─────────────────────────────────────────────
# Classification and the unconservative range
# ─────────────────────────────────────────────

def test_tension_member_is_not_applicable():
    s = _screen(+100_000.0)
    assert s.is_compression is False
    assert s.column_class is ColumnClass.NOT_COMPRESSION
    assert s.status is ScreeningStatus.NOT_APPLICABLE


def test_slender_member_is_classified_elastic_and_euler_applies():
    """Long member: lambda > lambda_c, so Euler is legitimate."""
    s = _screen(-10_000.0, length=8.0)
    assert s.slenderness > s.transition_slenderness
    assert s.column_class is ColumnClass.SLENDER
    assert s.euler_applicable is True
    assert s.status is ScreeningStatus.PASS


def test_intermediate_member_is_flagged_as_unconservative():
    """
    The key honesty requirement: below lambda_c, Euler OVERESTIMATES
    capacity. A low utilisation must NOT be reported as a pass.
    """
    s = _screen(-10_000.0, length=LENGTH)     # lambda = 87 < 125.7
    assert s.column_class is ColumnClass.INTERMEDIATE
    assert s.euler_applicable is False
    assert s.utilisation < 1.0
    assert s.status is ScreeningStatus.UNCONSERVATIVE
    assert "OVERESTIMATES" in s.note


def test_short_member_is_identified_as_squashing():
    s = _screen(-10_000.0, length=0.5)
    assert s.slenderness < SHORT_COLUMN_SLENDERNESS
    assert s.column_class is ColumnClass.SHORT
    assert s.euler_applicable is False
    assert "squash" in s.note.lower()


def test_overloaded_member_fails_regardless_of_classification():
    """An exceeded Euler load is a FAIL even in the inelastic range."""
    s = _screen(-2_000_000.0, length=LENGTH)
    assert s.utilisation > 1.0
    assert s.status is ScreeningStatus.FAIL


def test_utilisation_is_demand_over_capacity():
    s = _screen(-281_431.0, length=LENGTH)    # exactly half of P_cr
    assert s.utilisation == pytest.approx(0.5, rel=1e-4)


# ─────────────────────────────────────────────
# Whole-structure screening
# ─────────────────────────────────────────────

def test_screening_covers_every_member_of_a_solved_structure():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    results = solve(structure, spec)

    report = screen_structure(structure, results.member_results)
    assert len(report.members) == len(structure.members)
    assert report.n_compression > 0


def test_report_is_labelled_screening_not_analysis():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    report = screen_structure(structure, solve(structure, spec).member_results)

    assert report.title == "BUCKLING SCREENING"
    assert "not a buckling analysis" in report.disclaimer
    assert any("column curves" in lim for lim in report.method_limitations)
    assert any("lateral-torsional" in lim for lim in report.method_limitations)


def test_default_truss_is_reported_as_inelastic_and_therefore_unconservative():
    """
    A real, honest finding for this model: every compression member sits
    below lambda_c, so the Euler screen is unconservative throughout and
    says so rather than reporting a clean pass.
    """
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    report = screen_structure(structure, solve(structure, spec).member_results)

    assert report.n_unconservative == report.n_compression
    assert report.n_compression > 0
    assert report.max_slenderness < transition_slenderness(E_A36, FY_A36)


def test_k_basis_states_why_pinned_is_correct_here():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    report = screen_structure(structure, solve(structure, spec).member_results)
    assert "pin-jointed" in report.k_basis
    assert "no rotational DOF" in report.k_basis
