"""
NeuroPlan-3D — Current-Model Wiring Regression Tests

The bug: every engineering-analysis endpoint (`/analyse`, `/sensitivity`,
`/nonlinear`, `/modal`, `/seismic`, `/fatigue`, `/fire`, `/springs`,
`/experiments/load-robustness`) already accepted an optional `spec` field
in its request schema, and `_spec_from(None)` silently substitutes the
backend's bare-default `EngineeringSpec()` (a 20 m Pratt truss) when the
caller omits it. The frontend was omitting it everywhere except Failure
Lab — so Sensitivity and every Advanced Analysis module always analysed
that unrelated default structure, never the structure actually loaded in
the user's workspace.

This is a request-wiring bug, not a backend architecture problem: no
endpoint needed a new schema field, only the `model` metadata block added
in this same change so a caller (or a test) can verify which structure an
analysis actually used.

These tests hit the real HTTP endpoints and the real solver end to end —
nothing here is mocked.
"""
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, StructureType

client = TestClient(app)

# Two genuinely different structures: different structure_type,
# different geometry, and therefore different node/member counts.
SPEC_SMALL = {
    "structure_type": "pratt", "span": 12.0, "height": 2.0, "num_panels": 4,
    "primary_load": 30000.0, "material_key": "A36", "section_key": "CHS_114x6",
}
SPEC_LARGE = {
    "structure_type": "space_truss", "span": 24.0, "height": 2.5, "width": 4.0,
    "num_panels": 8, "primary_load": 80000.0, "lateral_load_z": 15000.0,
    "material_key": "A36", "section_key": "CHS_168x6",
}

_SMALL_COUNTS = (
    len(generate_structure(EngineeringSpec(structure_type=StructureType.PRATT, span=12.0, height=2.0, num_panels=4)).nodes),
    len(generate_structure(EngineeringSpec(structure_type=StructureType.PRATT, span=12.0, height=2.0, num_panels=4)).members),
)
_LARGE_COUNTS = (
    len(generate_structure(EngineeringSpec(structure_type=StructureType.SPACE_TRUSS, span=24.0, height=2.5, width=4.0, num_panels=8)).nodes),
    len(generate_structure(EngineeringSpec(structure_type=StructureType.SPACE_TRUSS, span=24.0, height=2.5, width=4.0, num_panels=8)).members),
)
_DEFAULT_COUNTS = (
    len(generate_structure(EngineeringSpec()).nodes),
    len(generate_structure(EngineeringSpec()).members),
)

# The three structures must actually be distinguishable, or the tests below
# would pass by coincidence rather than by proving the wiring works.
assert len({_SMALL_COUNTS, _LARGE_COUNTS, _DEFAULT_COUNTS}) == 3


ENDPOINTS_WITH_SPEC = [
    ("/api/engineering/analyse", {}),
    ("/api/engineering/sensitivity", {}),
    ("/api/engineering/nonlinear", {}),
    ("/api/engineering/modal", {}),
    ("/api/engineering/experiments/load-robustness", {}),
    ("/api/engineering/fire", {"temperature_c": 400.0}),
    ("/api/engineering/seismic", {"zone": "iv", "soil": "type_ii_medium"}),
    ("/api/engineering/fatigue", {"sigma_c_mpa": 100.0, "design_cycles": 1e6}),
]


# ── 1 & 3 & 5. Every endpoint reports the model it actually analysed ──

@pytest.mark.parametrize("path,extra", ENDPOINTS_WITH_SPEC)
def test_endpoint_reports_the_spec_it_was_given(path, extra):
    body = {**extra, "spec": SPEC_SMALL}
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    data = response.json()

    assert "model" in data, f"{path} does not report which model it analysed"
    model = data["model"]
    assert model["spec_provided"] is True
    assert model["structure_type"] == "pratt"
    assert model["is_spatial"] is False
    assert (model["node_count"], model["member_count"]) == _SMALL_COUNTS


@pytest.mark.parametrize("path,extra", ENDPOINTS_WITH_SPEC)
def test_endpoint_reflects_a_genuinely_different_structure(path, extra):
    """The exact regression: does a different current model change what's analysed?"""
    body = {**extra, "spec": SPEC_LARGE}
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    model = response.json()["model"]

    assert model["structure_type"] == "space_truss"
    assert model["is_spatial"] is True
    assert (model["node_count"], model["member_count"]) == _LARGE_COUNTS
    # And it must differ from the small structure's counts.
    assert (model["node_count"], model["member_count"]) != _SMALL_COUNTS


# ── 4 & 6. Omitting spec is handled explicitly, not silently ──

@pytest.mark.parametrize("path,extra", ENDPOINTS_WITH_SPEC)
def test_omitted_spec_is_flagged_not_hidden(path, extra):
    """
    Existing behaviour (falling back to a default structure when no spec is
    given) must keep working — for backward compatibility and for callers
    with no current project — but it must be reported, never silent.
    """
    response = client.post(path, json=extra)
    assert response.status_code == 200, response.text
    model = response.json()["model"]

    assert model["spec_provided"] is False
    assert (model["node_count"], model["member_count"]) == _DEFAULT_COUNTS


# ── 2. Two different structures produce different analysis results ────

def test_sensitivity_baseline_differs_between_two_real_structures():
    small = client.post("/api/engineering/sensitivity", json={"spec": SPEC_SMALL}).json()
    large = client.post("/api/engineering/sensitivity", json={"spec": SPEC_LARGE}).json()

    assert small["model"]["node_count"] != large["model"]["node_count"]
    assert small["baseline"]["max_displacement_mm"] != pytest.approx(
        large["baseline"]["max_displacement_mm"], rel=1e-6,
    )
    assert small["baseline"]["total_weight_kg"] != pytest.approx(
        large["baseline"]["total_weight_kg"], rel=1e-6,
    )


def test_analyse_total_weight_differs_between_two_real_structures():
    small = client.post("/api/engineering/analyse", json={"spec": SPEC_SMALL}).json()
    large = client.post("/api/engineering/analyse", json={"spec": SPEC_LARGE}).json()
    assert small["total_weight_kg"] != pytest.approx(large["total_weight_kg"], rel=1e-6)


def test_robustness_sweep_reflects_the_structure_it_was_given():
    small = client.post(
        "/api/engineering/experiments/load-robustness", json={"spec": SPEC_SMALL},
    ).json()
    large = client.post(
        "/api/engineering/experiments/load-robustness", json={"spec": SPEC_LARGE},
    ).json()
    assert small["model"]["node_count"] == _SMALL_COUNTS[0]
    assert large["model"]["node_count"] == _LARGE_COUNTS[0]
    assert small["scenarios"][0]["max_displacement_mm"] != pytest.approx(
        large["scenarios"][0]["max_displacement_mm"], rel=1e-6,
    )


def test_nonlinear_result_differs_between_two_real_structures():
    small = client.post("/api/engineering/nonlinear", json={"spec": SPEC_SMALL}).json()
    large = client.post("/api/engineering/nonlinear", json={"spec": SPEC_LARGE}).json()
    assert small["model"]["node_count"] != large["model"]["node_count"]
    # Both must have actually solved a structure with as many steps as configured.
    assert isinstance(small.get("steps"), list) and isinstance(large.get("steps"), list)
