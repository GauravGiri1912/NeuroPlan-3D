"""
Connection SCREENING — Task 6 strengthening tests.

Covers the additive per-member GOVERNING check rollup
(ConnectionSummary/report.summaries/report.governing_member_id) and the
API-level wiring that lets a caller actually DECLARE a bolted/welded
connection through /analyse (previously screen_connections() was always
called with no declarations, so every member showed NOT MODELED no
matter what). All existing capacity-equation benchmarks are unchanged —
see test_connections.py for those.
"""
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.core.codes.connections import (
    screen_connections, BoltedConnection, WeldedConnection,
    ConnectionStatus, ConnectionType,
)
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, StructureType

client = TestClient(app)


@pytest.fixture(scope="module")
def member_results():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    return solve(structure, spec).member_results


# ── 1. Benchmark regression (also re-asserted at this layer) ──────────

def test_m20_grade_8_8_bolt_shear_benchmark_via_summary(member_results):
    target = max(member_results, key=lambda m: abs(m.axial_force))
    report = screen_connections(
        member_results,
        bolted=[BoltedConnection(member_id=target.member_id, bolt_diameter_mm=20,
                                  bolt_grade="8.8", bolt_count=1)],
    )
    shear_check = next(c for c in report.checks
                        if c.member_id == target.member_id and "shear" in c.check_name.lower())
    assert shear_check.capacity / 1000 == pytest.approx(90.53, rel=1e-3)


# ── 4. Governing-check selection is computed, not hardcoded ───────────

def test_governing_check_is_the_lower_capacity_not_always_shear(member_results):
    """
    Bearing capacity for this worked example (66.59 kN) is lower than
    shear (90.53 kN), so bearing must govern — proving the selection
    isn't a fixed "shear always governs" assumption.
    """
    target = max(member_results, key=lambda m: abs(m.axial_force))
    report = screen_connections(
        member_results,
        bolted=[BoltedConnection(member_id=target.member_id, bolt_diameter_mm=20,
                                  bolt_grade="8.8", bolt_count=1)],
    )
    summary = next(s for s in report.summaries if s.member_id == target.member_id)
    assert "bearing" in summary.governing_check_name.lower()
    assert summary.capacity == pytest.approx(66_590, rel=1e-2)


def test_governing_member_id_reflects_the_worst_declared_connection(member_results):
    """Two declared connections, different margins — the tighter one governs overall."""
    members = sorted(member_results, key=lambda m: abs(m.axial_force), reverse=True)[:2]
    report = screen_connections(
        member_results,
        bolted=[
            BoltedConnection(member_id=members[0].member_id, bolt_diameter_mm=12,
                              bolt_grade="4.6", bolt_count=1),   # weak — likely governs
            BoltedConnection(member_id=members[1].member_id, bolt_diameter_mm=30,
                              bolt_grade="10.9", bolt_count=8),  # strong
        ],
    )
    assert report.governing_member_id is not None
    governing_summary = next(s for s in report.summaries if s.member_id == report.governing_member_id)
    weak_summary = next(s for s in report.summaries if s.member_id == members[0].member_id)
    assert governing_summary.dc_ratio == max(s.dc_ratio for s in report.summaries)
    assert governing_summary.dc_ratio >= weak_summary.dc_ratio


def test_governing_member_id_is_none_when_nothing_is_declared(member_results):
    """No arbitrary NOT_MODELED member should be reported as 'governing'."""
    report = screen_connections(member_results)
    assert report.governing_member_id is None


# ── 5 & 6. PASS / FAIL cases at the summary level ──────────────────────

def test_pass_case_at_summary_level(member_results):
    target = min(member_results, key=lambda m: abs(m.axial_force))
    report = screen_connections(
        member_results,
        bolted=[BoltedConnection(member_id=target.member_id, bolt_diameter_mm=30,
                                  bolt_grade="10.9", bolt_count=8)],
    )
    summary = next(s for s in report.summaries if s.member_id == target.member_id)
    assert summary.status is ConnectionStatus.PASS


def test_fail_case_at_summary_level(member_results):
    target = max(member_results, key=lambda m: abs(m.axial_force))
    report = screen_connections(
        member_results,
        bolted=[BoltedConnection(member_id=target.member_id, bolt_diameter_mm=12,
                                  bolt_grade="4.6", bolt_count=1)],
    )
    summary = next(s for s in report.summaries if s.member_id == target.member_id)
    assert summary.status is ConnectionStatus.FAIL
    assert summary.dc_ratio > 1.0


# ── 7 & 8. Missing input / unsupported configuration ───────────────────

def test_summary_for_undeclared_member_is_not_modeled(member_results):
    report = screen_connections(member_results)
    assert report.summaries
    assert all(s.status is ConnectionStatus.NOT_MODELED for s in report.summaries)
    assert all(s.connection_type is ConnectionType.NOT_DEFINED for s in report.summaries)


def test_every_member_gets_exactly_one_summary(member_results):
    """No member is double-counted or dropped by the rollup."""
    report = screen_connections(member_results)
    member_ids = {r.member_id for r in member_results}
    assert {s.member_id for s in report.summaries} == member_ids
    assert len(report.summaries) == len(member_ids)


def test_unsupported_bolt_grade_via_api_is_a_422_not_a_fabricated_result():
    response = client.post("/api/engineering/analyse", json={
        "bolted_connections": [{
            "member_id": 0, "bolt_diameter_mm": 20,
            "bolt_grade": "99.9", "bolt_count": 1,
        }],
    })
    assert response.status_code == 422


# ── 9. Current-model identity ──────────────────────────────────────────

def test_connections_api_reflects_the_current_spec_not_a_default():
    small = {"structure_type": "pratt", "span": 12.0, "height": 2.0, "num_panels": 4}
    large = {
        "structure_type": "space_truss", "span": 24.0, "height": 2.5,
        "width": 4.0, "num_panels": 8,
    }
    r_small = client.post("/api/engineering/analyse", json={"spec": small}).json()
    r_large = client.post("/api/engineering/analyse", json={"spec": large}).json()

    assert r_small["model"]["structure_type"] == "pratt"
    assert r_large["model"]["structure_type"] == "space_truss"
    assert (len(r_small["connections"]["summaries"])
            != len(r_large["connections"]["summaries"]))


def test_declared_connection_via_api_is_checked_against_the_current_model():
    """
    The core wiring fix: previously /analyse never passed bolted_connections
    through, so every member was NOT MODELED regardless of what a caller
    sent. This proves a declared connection is now actually screened.
    """
    response = client.post("/api/engineering/analyse", json={
        "spec": {"structure_type": "pratt", "span": 12.0, "height": 2.0, "num_panels": 4},
        "bolted_connections": [{
            "member_id": 0, "bolt_diameter_mm": 20,
            "bolt_grade": "8.8", "bolt_count": 1,
        }],
    })
    assert response.status_code == 200
    data = response.json()["connections"]
    summary0 = next(s for s in data["summaries"] if s["member_id"] == 0)
    assert summary0["status"] != "not_modeled"
    assert summary0["connection_type"] == "bolted_shear"


def test_declared_welded_connection_via_api():
    response = client.post("/api/engineering/analyse", json={
        "welded_connections": [{
            "member_id": 0, "weld_size_mm": 6.0, "weld_length_mm": 200.0, "shop_weld": True,
        }],
    })
    assert response.status_code == 200
    data = response.json()["connections"]
    summary0 = next(s for s in data["summaries"] if s["member_id"] == 0)
    assert summary0["connection_type"] == "fillet_weld"
    check0 = next(c for c in data["checks"] if c["member_id"] == 0 and "weld" in c["check_name"].lower())
    assert check0["capacity"] / 1000 == pytest.approx(159.07, rel=1e-3)


# ── 10. Regression: existing values still exact ────────────────────────

def test_bearing_and_weld_benchmarks_unchanged():
    from server.core.codes.connections import bolt_bearing_capacity, fillet_weld_capacity
    bearing, _ = bolt_bearing_capacity(20, "8.8", 1, 8.0, 35.0, 50.0, 410e6)
    assert bearing / 1000 == pytest.approx(66.59, rel=1e-3)
    weld, _ = fillet_weld_capacity(6.0, 200.0, 410e6, shop=True)
    assert weld / 1000 == pytest.approx(159.07, rel=1e-3)
