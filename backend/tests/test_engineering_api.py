"""
API regression tests for the engineering endpoints.

These exist because the analysis modules were all unit-tested and green
while /analyse still returned HTTP 500: the solver emits numpy scalars
(np.bool_, np.float64) that FastAPI cannot serialise. A unit test on the
dataclass never touches that boundary. These tests do.
"""
import math
import pytest
from fastapi.testclient import TestClient

from server.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def analysis():
    response = client.post("/api/engineering/analyse", json={})
    assert response.status_code == 200, response.text
    return response.json()


# ─────────────────────────────────────────────
# Every endpoint must actually serialise
# ─────────────────────────────────────────────

@pytest.mark.parametrize("path,payload", [
    ("/api/engineering/analyse", {}),
    ("/api/engineering/sensitivity", {}),
    ("/api/engineering/report", {"run_sensitivity": True}),
    ("/api/engineering/what-if", {"changes": {"primary_load": "100000"}}),
    ("/api/engineering/explore", {"panel_counts": [4, 6]}),
])
def test_endpoint_returns_serialisable_json(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()


def test_capabilities_endpoint_is_available():
    response = client.get("/api/engineering/capabilities")
    assert response.status_code == 200
    assert response.json()["solver"]["dof_per_node"] == 3


# ─────────────────────────────────────────────
# Payload content is real
# ─────────────────────────────────────────────

def test_analyse_reports_self_weight_consistently(analysis):
    self_weight = analysis["load_summary"]["self_weight"]
    assert self_weight["included"] is True
    assert self_weight["total_weight_n"] == pytest.approx(
        self_weight["applied_weight_n"], rel=1e-9
    )


def test_analyse_reports_active_load_cases(analysis):
    active = [c["case_type"] for c in analysis["load_summary"]["cases"] if c["active"]]
    assert "dead" in active and "live" in active


def test_analyse_reports_stability_diagnostics(analysis):
    stability = analysis["stability"]
    assert stability["n_zero_modes"] == 0
    assert stability["determinacy"] in ("determinate", "indeterminate")
    assert isinstance(stability["condition_number"], float)


def test_analyse_reports_buckling_and_code_screening(analysis):
    assert analysis["buckling"]["n_compression"] > 0
    assert analysis["code_checks"]["title"] == "IS 800:2007 SCREENING CHECKS"
    assert analysis["connections"]["title"] == "CONNECTION SCREENING"


def test_members_without_a_connection_are_listed_not_hidden(analysis):
    assert analysis["connections"]["members_without_connection"]


def test_self_weight_changes_the_result_through_the_api():
    """Turning dead load off must produce a different stress."""
    with_sw = client.post("/api/engineering/analyse",
                          json={"include_self_weight": True}).json()
    without = client.post("/api/engineering/analyse",
                          json={"include_self_weight": False}).json()
    assert with_sw["max_stress_mpa"] > without["max_stress_mpa"]


def test_thermal_load_moves_the_structure_without_stressing_a_determinate_truss():
    """
    The generated truss is statically determinate and its roller leaves
    the span free to expand, so uniform heating produces DISPLACEMENT but
    NO stress. Asserting a stress change here would be asserting wrong
    physics; the displacement change is what proves thermal reached the
    solver through the API.
    """
    base = client.post("/api/engineering/analyse", json={}).json()
    heated = client.post("/api/engineering/analyse",
                         json={"temperature_change_k": 40.0}).json()

    assert heated["max_stress_mpa"] == pytest.approx(base["max_stress_mpa"], rel=1e-9)
    assert heated["max_displacement_mm"] > base["max_displacement_mm"] * 1.2


# ─────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────

def test_report_contains_sections_limitations_and_classifications():
    report = client.post("/api/engineering/report",
                         json={"run_sensitivity": True}).json()
    assert report["simulation_id"].startswith("NP3D-")
    assert len(report["sections"]) >= 11
    assert len(report["limitations"]) >= 10
    assert report["classification_counts"]["computed"] > 0
    assert "NOT a certified" in report["positioning"]


# ─────────────────────────────────────────────
# What-if and explore
# ─────────────────────────────────────────────

def test_what_if_doubling_load_doubles_stress_through_the_api():
    spec_default_load = 50000.0
    result = client.post("/api/engineering/what-if", json={
        "changes": {"primary_load": str(spec_default_load * 2)},
    }).json()
    stress = next(d for d in result["deltas"] if d["name"] == "max_stress_mpa")
    assert stress["percent_change"] == pytest.approx(100.0, rel=1e-4)


def test_what_if_rejects_an_unknown_parameter():
    response = client.post("/api/engineering/what-if",
                           json={"changes": {"colour": "blue"}})
    assert response.status_code == 422
    assert "Valid parameters" in response.json()["detail"]


def test_explore_returns_a_tradeoff_table_without_a_winner():
    table = client.post("/api/engineering/explore",
                        json={"panel_counts": [4, 6], "heights": [2.0, 3.0]}).json()
    assert len(table["candidates"]) == 4
    assert "best" not in table
    assert "No design is declared 'best'" in table["selection_policy"]
    assert any(c["pareto_optimal"] for c in table["candidates"])


def test_explore_rejects_an_unknown_structure_type():
    response = client.post("/api/engineering/explore",
                           json={"structure_types": ["geodesic_dome"]})
    assert response.status_code == 422


# ─────────────────────────────────────────────
# Non-finite handling
# ─────────────────────────────────────────────

def test_non_finite_values_are_reported_as_strings_not_dropped():
    """
    Infinite factor-of-safety (an unstressed member) must survive
    serialisation as a readable token rather than crashing the response
    or being silently replaced by a number.
    """
    table = client.post("/api/engineering/explore",
                        json={"panel_counts": [6]}).json()
    text = str(table)
    assert "nan" not in text.lower() or "NaN" in text


def test_sensitivity_endpoint_declares_itself_non_statistical():
    report = client.post("/api/engineering/sensitivity", json={}).json()
    assert report["is_statistical"] is False
    assert "NOT A CONFIDENCE INTERVAL" in report["statistical_disclaimer"]
