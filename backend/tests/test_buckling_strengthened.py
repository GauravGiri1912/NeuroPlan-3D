"""
Buckling SCREENING — Task 5 strengthening tests.

These cover the additive fields (area/inertia/E exposed per member,
governing_reason, the new NOT_MODELED status for a degenerate section)
and the current-model wiring for the buckling block of /analyse. All
existing behaviour and benchmark values from test_buckling_screening.py
are unchanged — see that file for the underlying Euler/slenderness
regression.
"""
import copy
import math
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.core.analysis.buckling import (
    screen_member, screen_structure, ColumnClass, ScreeningStatus, DEFAULT_K,
)
from server.core.fea.solver import solve
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec, StructureType, CrossSection

client = TestClient(app)

E_A36 = 200e9
FY_A36 = 250e6
SECTION = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)
LENGTH = 20.0 / 6.0


def _screen(axial_force, length=LENGTH, k=DEFAULT_K, section=SECTION):
    return screen_member(
        member_id=0, axial_force=axial_force, length=length,
        area=section.area, inertia=section.moment_of_inertia,
        radius_of_gyration=section.radius_of_gyration,
        E=E_A36, fy=FY_A36, k_factor=k,
    )


# ── 1 & 2. Per-member inputs are exposed, not just derived outputs ────

def test_screening_exposes_the_inputs_it_used():
    """area/inertia/E used in the calculation are stored, not discarded."""
    s = _screen(-100_000.0)
    assert s.area == pytest.approx(SECTION.area, rel=1e-9)
    assert s.inertia == pytest.approx(SECTION.moment_of_inertia, rel=1e-9)
    assert s.E == pytest.approx(E_A36, rel=1e-9)


def test_exposed_inputs_are_consistent_with_euler_load():
    """P_cr must be reconstructible from the exposed area/inertia/E/effective_length."""
    s = _screen(-100_000.0)
    recomputed = (math.pi ** 2) * s.E * s.inertia / (s.effective_length ** 2)
    assert s.euler_critical_load == pytest.approx(recomputed, rel=1e-9)


# ── 6. K assumption is disclosed per structure, still k=1.0 default ───

def test_k_factor_is_recorded_on_every_member():
    s = _screen(-100_000.0)
    assert s.k_factor == pytest.approx(DEFAULT_K)
    assert s.k_factor == pytest.approx(1.0)


# ── 9. Missing/unsupported input: degenerate section is NOT_MODELED ───

def test_zero_radius_of_gyration_is_not_modeled_not_a_fake_fail():
    """
    A degenerate section (r <= 0) must not be silently reported as FAIL
    against an infinite critical load — that would misrepresent an input
    problem as a genuine overload finding.
    """
    s = screen_member(
        member_id=7, axial_force=-50_000.0, length=3.0,
        area=SECTION.area, inertia=SECTION.moment_of_inertia,
        radius_of_gyration=0.0, E=E_A36, fy=FY_A36, k_factor=1.0,
    )
    assert s.status is ScreeningStatus.NOT_MODELED
    assert s.status is not ScreeningStatus.FAIL
    assert "cannot be screened" in s.note.lower() or "degenerate" in s.note.lower()


def test_not_modeled_member_does_not_poison_max_slenderness():
    """A NOT_MODELED member's infinite slenderness must not leak into the
    report's max_slenderness aggregate (a real pre-existing footgun this
    change fixes while it's being touched)."""
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    results = solve(structure, spec).member_results

    baseline = screen_structure(structure, results)
    compression_member_id = next(m.member_id for m in baseline.members if m.is_compression)

    # CrossSection instances are shared from a global catalog by
    # generate_structure(), so the section must be deep-copied before
    # mutating it, or the corruption leaks into every other structure
    # using that same section key for the rest of the process.
    target = next(m for m in structure.members if m.id == compression_member_id)
    target.section = copy.deepcopy(target.section)
    target.section.wall_thickness = 0.0

    report = screen_structure(structure, results)
    corrupted = next(m for m in report.members if m.member_id == compression_member_id)
    assert corrupted.status is ScreeningStatus.NOT_MODELED
    assert math.isfinite(report.max_slenderness)


# ── 5. Critical/governing member selection is computed, not hardcoded ─

def test_governing_member_has_the_worst_utilisation_not_the_largest_id():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    results = solve(structure, spec).member_results
    report = screen_structure(structure, results)

    assert report.governing_member_id is not None
    compression_members = [m for m in report.members if m.is_compression]
    worst = max(compression_members, key=lambda m: m.utilisation)
    assert report.governing_member_id == worst.member_id
    # And it is not simply the highest member id among compression members.
    assert report.governing_member_id != max(m.member_id for m in compression_members) or (
        worst.member_id == max(m.member_id for m in compression_members)
    )


def test_governing_reason_cites_the_actual_governing_members_numbers():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    report = screen_structure(structure, solve(structure, spec).member_results)

    governing = next(m for m in report.members if m.member_id == report.governing_member_id)
    assert report.governing_reason
    assert f"M{governing.member_id}" in report.governing_reason
    assert f"{governing.utilisation:.3f}" in report.governing_reason


def test_two_different_structures_have_different_governing_members_or_reasons():
    """Proves the governing selection reacts to the actual model, not a fixed pick."""
    spec_a = EngineeringSpec(structure_type=StructureType.PRATT, span=12.0, height=2.0, num_panels=4)
    spec_b = EngineeringSpec(
        structure_type=StructureType.SPACE_TRUSS, span=24.0, height=2.5,
        width=4.0, num_panels=8,
    )
    structure_a = generate_structure(spec_a)
    structure_b = generate_structure(spec_b)
    report_a = screen_structure(structure_a, solve(structure_a, spec_a).member_results)
    report_b = screen_structure(structure_b, solve(structure_b, spec_b).member_results)

    assert report_a.governing_reason != report_b.governing_reason


# ── 7 & 8. PASS / REVIEW (unconservative) statuses unchanged ──────────

def test_pass_status_still_reachable():
    s = _screen(-10_000.0, length=8.0)
    assert s.status is ScreeningStatus.PASS


def test_unconservative_status_still_reachable_and_flagged():
    s = _screen(-10_000.0, length=LENGTH)
    assert s.status is ScreeningStatus.UNCONSERVATIVE
    assert s.column_class is ColumnClass.INTERMEDIATE


# ── 10. Current-model identity: buckling reflects the CURRENT spec ────

def test_buckling_block_reflects_the_spec_actually_sent():
    small = {"structure_type": "pratt", "span": 12.0, "height": 2.0, "num_panels": 4}
    large = {
        "structure_type": "space_truss", "span": 24.0, "height": 2.5,
        "width": 4.0, "num_panels": 8,
    }
    r_small = client.post("/api/engineering/analyse", json={"spec": small}).json()
    r_large = client.post("/api/engineering/analyse", json={"spec": large}).json()

    assert r_small["model"]["structure_type"] == "pratt"
    assert r_large["model"]["structure_type"] == "space_truss"
    assert r_small["model"]["node_count"] != r_large["model"]["node_count"]
    # The buckling report's own member count must track the model actually solved.
    assert len(r_small["buckling"]["members"]) == len(
        generate_structure(EngineeringSpec(
            structure_type=StructureType.PRATT, span=12.0, height=2.0, num_panels=4,
        )).members
    )
    assert r_small["buckling"]["members"] != r_large["buckling"]["members"]


def test_buckling_block_has_per_member_detail_in_the_api_response():
    response = client.post("/api/engineering/analyse", json={}).json()
    members = response["buckling"]["members"]
    assert len(members) > 0
    m = members[0]
    for key in ("member_id", "area", "inertia", "E", "k_factor",
                "slenderness", "euler_critical_load", "status"):
        assert key in m, f"missing {key} in per-member buckling response"


def test_governing_reason_is_present_in_the_api_response():
    response = client.post("/api/engineering/analyse", json={}).json()
    assert response["buckling"]["governing_reason"]
