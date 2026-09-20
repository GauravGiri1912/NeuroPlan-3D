"""
Priority 7 — Connection screening.

Hand-verified worked examples (IS 800:2007 Section 10):

  M20 grade 8.8, 1 bolt, single shear through threads:
      V_dsb = (800/sqrt(3)) * 245 / 1.25  = 90.53 kN

  Same bolt bearing on an 8 mm Fe 410 ply, e = 35, p = 50, d_0 = 22:
      k_b = min(35/66, 50/66-0.25, 800/410, 1.0) = 0.5076
      V_dpb = 2.5 * 0.5076 * 20 * 8 * 410 / 1.25 = 66.59 kN

  6 mm fillet weld, 200 mm long, shop, Fe 410:
      a = 0.7*6 = 4.2 mm
      capacity = 4.2 * 200 * (410/sqrt(3))/1.25 = 159.07 kN

The most important behaviour under test is NOT a number: a member with
no declared connection must report NOT MODELED, never an assumed pass.
"""
import math
import pytest

from server.core.codes.connections import (
    bolt_shear_capacity, bolt_bearing_capacity, fillet_weld_capacity,
    screen_connections, BoltedConnection, WeldedConnection,
    ConnectionStatus, ConnectionType, GAMMA_MB, GAMMA_MW_SHOP, GAMMA_MW_SITE,
    BOLT_GRADE_FUB, UNSUPPORTED_CONNECTION_CHECKS,
)
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec


@pytest.fixture(scope="module")
def member_results():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    return solve(structure, spec).member_results


# ─────────────────────────────────────────────
# Capacity equations vs hand calculation
# ─────────────────────────────────────────────

def test_bolt_shear_matches_hand_calculation():
    capacity, _ = bolt_shear_capacity(20, "8.8", 1, 1, 0)
    expected = (800e6 / math.sqrt(3)) * 245e-6 / GAMMA_MB
    assert capacity == pytest.approx(expected, rel=1e-9)
    assert capacity / 1000 == pytest.approx(90.53, rel=1e-3)


def test_bolt_shear_scales_with_bolt_count():
    one, _ = bolt_shear_capacity(20, "8.8", 1)
    four, _ = bolt_shear_capacity(20, "8.8", 4)
    assert four == pytest.approx(4.0 * one, rel=1e-12)


def test_double_shear_through_threads_doubles_capacity():
    single, _ = bolt_shear_capacity(20, "8.8", 1, planes_threaded=1)
    double, _ = bolt_shear_capacity(20, "8.8", 1, planes_threaded=2)
    assert double == pytest.approx(2.0 * single, rel=1e-12)


def test_shank_plane_gives_more_capacity_than_threaded_plane():
    """A_sb (314 mm^2) exceeds A_nb (245 mm^2) for M20."""
    threaded, _ = bolt_shear_capacity(20, "8.8", 1, planes_threaded=1, planes_shank=0)
    shank, _ = bolt_shear_capacity(20, "8.8", 1, planes_threaded=0, planes_shank=1)
    assert shank > threaded


def test_higher_bolt_grade_gives_more_capacity():
    low, _ = bolt_shear_capacity(20, "4.6", 1)
    high, _ = bolt_shear_capacity(20, "8.8", 1)
    assert high == pytest.approx(low * 800.0 / 400.0, rel=1e-12)


def test_bolt_bearing_matches_hand_calculation():
    capacity, inputs = bolt_bearing_capacity(20, "8.8", 1, 8.0, 35.0, 50.0, 410e6)
    kb = min(35 / 66, 50 / 66 - 0.25, 800 / 410, 1.0)
    expected = 2.5 * kb * 0.020 * 0.008 * 410e6 / GAMMA_MB

    assert capacity == pytest.approx(expected, rel=1e-9)
    assert float(inputs["k_b"]) == pytest.approx(kb, abs=1e-3)


def test_bearing_reports_which_term_governed_kb():
    _, inputs = bolt_bearing_capacity(20, "8.8", 1, 8.0, 35.0, 50.0, 410e6)
    assert inputs["k_b governed by"] == "p/(3 d0) - 0.25"


def test_small_end_distance_governs_kb_and_reduces_capacity():
    generous, _ = bolt_bearing_capacity(20, "8.8", 1, 8.0, 60.0, 80.0, 410e6)
    tight, inputs = bolt_bearing_capacity(20, "8.8", 1, 8.0, 25.0, 80.0, 410e6)
    assert tight < generous
    assert inputs["k_b governed by"] == "e/(3 d0)"


def test_fillet_weld_matches_hand_calculation():
    capacity, inputs = fillet_weld_capacity(6.0, 200.0, 410e6, shop=True)
    expected = 0.7 * 0.006 * 0.200 * (410e6 / math.sqrt(3)) / GAMMA_MW_SHOP
    assert capacity == pytest.approx(expected, rel=1e-9)
    assert capacity / 1000 == pytest.approx(159.07, rel=1e-3)
    assert inputs["throat a = 0.7s"].startswith("4.20")


def test_site_weld_is_weaker_than_shop_weld():
    """gamma_mw is 1.50 on site against 1.25 in the shop."""
    shop, _ = fillet_weld_capacity(6.0, 200.0, 410e6, shop=True)
    site, _ = fillet_weld_capacity(6.0, 200.0, 410e6, shop=False)
    assert site == pytest.approx(shop * GAMMA_MW_SHOP / GAMMA_MW_SITE, rel=1e-12)


def test_unknown_bolt_grade_is_rejected():
    with pytest.raises(ValueError, match="Unknown bolt grade"):
        bolt_shear_capacity(20, "99.9", 1)


def test_unknown_bolt_diameter_is_rejected():
    with pytest.raises(ValueError, match="No stress area"):
        bolt_shear_capacity(17, "8.8", 1)


def test_partial_safety_factors_match_the_code():
    assert GAMMA_MB == 1.25
    assert GAMMA_MW_SHOP == 1.25
    assert GAMMA_MW_SITE == 1.50
    assert BOLT_GRADE_FUB["8.8"] == 800e6


# ─────────────────────────────────────────────
# The central honesty requirement
# ─────────────────────────────────────────────

def test_member_without_a_declared_connection_is_not_modeled(member_results):
    """
    The point of the whole module: no connection declared means NOT
    MODELED, never an assumed pass.
    """
    report = screen_connections(member_results)

    assert report.members_without_connection
    assert all(c.status is ConnectionStatus.NOT_MODELED for c in report.checks)
    assert all(c.capacity == 0.0 for c in report.checks)
    assert report.n_failed == 0

    note = report.checks[0].note
    assert "NOT MODELED" in note
    assert "cannot be inferred" in note


def test_declared_connection_is_checked_against_the_real_member_force(member_results):
    target = max(member_results, key=lambda m: abs(m.axial_force))
    report = screen_connections(
        member_results,
        bolted=[BoltedConnection(
            member_id=target.member_id, bolt_diameter_mm=20,
            bolt_grade="8.8", bolt_count=4,
        )],
    )
    checks = [c for c in report.checks if c.member_id == target.member_id
              and c.status is not ConnectionStatus.NOT_MODELED]

    assert len(checks) == 2          # shear and bearing
    for check in checks:
        assert check.demand == pytest.approx(abs(target.axial_force))
        assert check.capacity > 0
        assert check.status in (ConnectionStatus.PASS, ConnectionStatus.FAIL)


def test_undersized_connection_fails(member_results):
    target = max(member_results, key=lambda m: abs(m.axial_force))
    report = screen_connections(
        member_results,
        bolted=[BoltedConnection(
            member_id=target.member_id, bolt_diameter_mm=12,
            bolt_grade="4.6", bolt_count=1, ply_thickness_mm=4.0,
        )],
    )
    assert report.n_failed >= 1
    assert report.max_dc_ratio > 1.0


def test_welded_connection_is_screened(member_results):
    target = member_results[0]
    report = screen_connections(
        member_results,
        welded=[WeldedConnection(member_id=target.member_id,
                                 weld_size_mm=6.0, weld_length_mm=200.0)],
    )
    weld = next(c for c in report.checks
                if c.connection_type is ConnectionType.FILLET_WELD)
    assert weld.clause == "cl. 10.5.7.1"
    assert weld.capacity == pytest.approx(159_072.0, rel=1e-3)


def test_every_check_carries_full_evidence(member_results):
    target = member_results[0]
    report = screen_connections(
        member_results,
        bolted=[BoltedConnection(member_id=target.member_id,
                                 bolt_diameter_mm=20, bolt_grade="8.8",
                                 bolt_count=2)],
    )
    for check in report.checks:
        if check.status is ConnectionStatus.NOT_MODELED:
            continue
        assert check.code == "IS 800" and check.edition == "2007"
        assert check.clause.startswith("cl.")
        assert check.equation and check.inputs


def test_report_is_labelled_screening_not_analysis(member_results):
    report = screen_connections(member_results)
    assert report.title == "CONNECTION SCREENING"
    assert "not connection analysis" in report.disclaimer
    assert "NOT MODELED, never assumed adequate" in report.disclaimer


def test_unsupported_checks_are_declared(member_results):
    joined = " ".join(screen_connections(member_results).unsupported_checks).lower()
    for topic in ("gusset", "block shear", "prying", "rotational stiffness",
                  "eccentricity", "fatigue"):
        assert topic in joined


def test_rotational_stiffness_limitation_notes_it_would_change_the_analysis():
    """
    The subtlest gap: a semi-rigid joint invalidates the pin-jointed
    solve itself, not merely this check.
    """
    joined = " ".join(UNSUPPORTED_CONNECTION_CHECKS)
    assert "change the analysis itself" in joined


def test_bearing_check_warns_that_block_shear_can_govern(member_results):
    target = member_results[0]
    report = screen_connections(
        member_results,
        bolted=[BoltedConnection(member_id=target.member_id,
                                 bolt_diameter_mm=20, bolt_grade="8.8",
                                 bolt_count=2)],
    )
    bearing = next(c for c in report.checks if c.clause == "cl. 10.3.4")
    assert "Block shear" in bearing.note and "govern" in bearing.note
