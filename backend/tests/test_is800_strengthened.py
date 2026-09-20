"""
IS 800:2007 — Strengthened screening tests.

Tests for the new section-classification check, effective-length
assumption disclosure, per-member detail, and regression against
the existing Perry-Robertson benchmark.
"""
import math
import pytest

from server.core.codes.is800_2007 import (
    screen_structure, design_compressive_stress, classify_chs, epsilon,
    check_tension_yielding, check_compression, check_slenderness_limit,
    check_section_classification, check_effective_length_assumption,
    SectionClass, CheckStatus, GAMMA_M0, GAMMA_M1, IMPERFECTION_FACTOR,
    SLENDERNESS_LIMIT_COMPRESSION, SLENDERNESS_LIMIT_TENSION,
    CHS_PLASTIC_LIMIT, CHS_COMPACT_LIMIT, CHS_SEMI_COMPACT_LIMIT,
    IMPLEMENTED_CLAUSES, UNSUPPORTED_CLAUSES,
)
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, CrossSection

FY = 250e6
E = 200e9
SECTION = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)
LAMBDA_EFF = 87.2247


# ─────────────────────────────────────────────
# Regression: existing benchmark values MUST be preserved
# ─────────────────────────────────────────────

def test_perry_robertson_benchmark_values_unchanged():
    """The hand-calculated reference values from the docstring must not drift."""
    f_cd, parts = design_compressive_stress(FY, E, LAMBDA_EFF, "a")

    assert parts["f_cc"] == pytest.approx(259.45e6, rel=1e-4)
    assert parts["lambda"] == pytest.approx(0.98162, rel=1e-4)
    assert parts["phi"] == pytest.approx(1.063859, rel=1e-5)
    assert parts["chi"] == pytest.approx(0.678424, rel=1e-5)
    assert f_cd == pytest.approx(154.19e6, rel=1e-4)


# ─────────────────────────────────────────────
# Section classification check (cl. 3.7.2)
# ─────────────────────────────────────────────

def test_section_classification_plastic_passes():
    """CHS 114.3x6.4, Fe250 — d/t=17.86, should be PLASTIC, PASS."""
    check = check_section_classification(0, 0.1143, 0.0064, FY)
    assert check.status is CheckStatus.PASS
    assert "PLASTIC" in check.note
    assert check.clause == "cl. 3.7.2 / Table 2"
    assert check.inputs  # full evidence set


def test_section_classification_slender_fails():
    """d/t=300 — should be SLENDER, FAIL."""
    check = check_section_classification(0, 0.300, 0.001, FY)
    assert check.status is CheckStatus.FAIL
    assert "SLENDER" not in check.note or "exceeds" in check.note
    assert "local buckling" in check.note.lower() or "unconservative" in check.note.lower()


def test_section_classification_has_all_limits_in_inputs():
    check = check_section_classification(0, 0.1143, 0.0064, FY)
    assert "d/t" in check.inputs
    assert "epsilon" in check.inputs
    # All three limits must be shown
    assert any("42" in k for k in check.inputs)
    assert any("52" in k for k in check.inputs)
    assert any("146" in k for k in check.inputs)


def test_section_classification_dc_ratio_is_d_over_t_vs_semi_compact():
    """D/C ratio = (d/t) / (146*eps^2)."""
    d, t = 0.1143, 0.0064
    check = check_section_classification(0, d, t, FY)
    d_over_t = d / t
    limit = CHS_SEMI_COMPACT_LIMIT * epsilon(FY) ** 2
    assert check.dc_ratio == pytest.approx(d_over_t / limit, rel=1e-9)


# ─────────────────────────────────────────────
# Effective length assumption (cl. 7.2.2)
# ─────────────────────────────────────────────

def test_effective_length_is_not_supported_status():
    check = check_effective_length_assumption(0, 1.0, 3.0)
    assert check.status is CheckStatus.NOT_SUPPORTED
    assert "ASSUMED" in check.note


def test_effective_length_shows_k_and_length():
    check = check_effective_length_assumption(5, 0.85, 2.5)
    assert check.inputs["k (assumed)"] == "0.85"
    assert "2500.0" in check.inputs["L"]
    assert "2125.0" in check.inputs["KL"]


def test_effective_length_dc_ratio_is_zero():
    """NOT_SUPPORTED checks have no demand/capacity comparison."""
    check = check_effective_length_assumption(0, 1.0, 3.0)
    assert check.dc_ratio == 0.0
    assert check.demand == 0.0


# ─────────────────────────────────────────────
# Per-member detail in full report
# ─────────────────────────────────────────────

def _report():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    return screen_structure(structure, solve(structure, spec).member_results)


def test_every_member_now_has_four_checks():
    """Strength + slenderness + section classification + effective length."""
    report = _report()
    for member in report.members:
        # At least 4 checks (compression/tension + slenderness + classification + k-factor)
        assert len(member.checks) >= 4, (
            f"Member {member.member_id} has {len(member.checks)} checks, expected >= 4"
        )


def test_section_classification_check_present_for_every_member():
    report = _report()
    for member in report.members:
        classification_checks = [c for c in member.checks if "classification" in c.check_name.lower()]
        assert len(classification_checks) == 1, (
            f"Member {member.member_id}: expected 1 classification check"
        )


def test_effective_length_disclosure_present_for_every_member():
    report = _report()
    for member in report.members:
        k_checks = [c for c in member.checks if "effective length" in c.check_name.lower()]
        assert len(k_checks) == 1, (
            f"Member {member.member_id}: expected 1 effective-length disclosure"
        )


def test_not_supported_checks_are_not_counted_as_failures():
    """NOT_SUPPORTED (k-factor) must not inflate n_failed."""
    report = _report()
    all_ns = sum(
        1 for m in report.members
        for c in m.checks if c.status is CheckStatus.NOT_SUPPORTED
    )
    assert all_ns > 0, "Expected at least one NOT_SUPPORTED check"
    # n_failed should only count FAIL, not NOT_SUPPORTED
    all_fail = sum(
        1 for m in report.members
        for c in m.checks if c.status is CheckStatus.FAIL
    )
    assert report.n_failed == all_fail


def test_governing_member_dc_ratio_unchanged_from_existing_checks():
    """The governing D/C should come from compression/tension/slenderness,
    NOT from the new section-classification D/C (which uses d/t ratio)."""
    report = _report()
    # The governing check should still be one of the original checks
    governing_member = next(
        m for m in report.members if m.member_id == report.governing_member_id
    )
    gov_check = governing_member.governing
    assert gov_check is not None
    # Governing must be from strength or slenderness, not classification
    assert "classification" not in gov_check.check_name.lower()


def test_implemented_clauses_now_includes_section_classification_check():
    report = _report()
    assert any("section classification check" in c.lower() for c in report.implemented_clauses)


def test_full_evidence_still_present_on_all_pass_fail_checks():
    """Every PASS/FAIL check must have code, edition, clause, inputs, equation."""
    for member in _report().members:
        for check in member.checks:
            if check.status in (CheckStatus.PASS, CheckStatus.FAIL):
                assert check.code == "IS 800"
                assert check.edition == "2007"
                assert check.clause.startswith("cl.")
                assert check.equation
                assert check.inputs
