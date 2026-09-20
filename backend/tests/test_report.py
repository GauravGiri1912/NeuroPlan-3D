"""
Priority 12 — Engineering analysis report.

The report's value is that it cannot quietly omit things. These tests
assert the presence of the gap-reporting, not just the happy path: an
analysis that was not run must appear as NOT_MODELED, and the limitation
list must stay honest as features are added.
"""
import pytest

from server.core.analysis.report import (
    build_report, report_to_dict, ValueClass, EngineeringReport,
)
from server.core.analysis.buckling import screen_structure as buckling_screen
from server.core.analysis.sensitivity import run_sensitivity
from server.core.codes.is800_2007 import screen_structure as code_screen
from server.core.fea.solver import solve
from server.core.fea.load_cases import DEFAULT_COMBINATION, LIVE_ONLY_COMBINATION
from server.core.generator.topology import generate_structure
from server.models.structure import EngineeringSpec

REQUIRED_SECTIONS = [
    "requirements", "geometry", "materials", "loads", "solver", "results",
    "verification", "buckling", "code", "sensitivity", "validation",
]


@pytest.fixture(scope="module")
def full_report() -> EngineeringReport:
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    results = solve(structure, spec, combination=DEFAULT_COMBINATION)
    return build_report(
        structure, spec, results,
        buckling=buckling_screen(structure, results.member_results),
        sensitivity=run_sensitivity(structure, spec),
        code_report=code_screen(structure, results.member_results),
    )


def _minimal_report() -> EngineeringReport:
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    return build_report(structure, spec, solve(structure, spec))


# ─────────────────────────────────────────────
# Structure and completeness
# ─────────────────────────────────────────────

def test_report_contains_every_required_section(full_report):
    present = [s.key for s in full_report.sections]
    for key in REQUIRED_SECTIONS:
        assert key in present, f"missing report section: {key}"


def test_every_item_carries_a_classification(full_report):
    for section in full_report.sections:
        for item in section.items:
            assert item.classification in set(ValueClass)
            assert item.label
            assert item.value != ""


def test_report_identifies_software_version_and_simulation_id(full_report):
    assert full_report.software_version
    assert full_report.simulation_id.startswith("NP3D-")
    assert full_report.generated_at
    assert full_report.python_version


def test_simulation_id_is_deterministic_for_the_same_model():
    a, b = _minimal_report(), _minimal_report()
    assert a.simulation_id == b.simulation_id


def test_simulation_id_changes_when_the_model_changes():
    spec = EngineeringSpec()
    base = build_report(generate_structure(spec), spec,
                        solve(generate_structure(spec), spec))

    other = EngineeringSpec()
    other.num_panels = 8
    changed = build_report(generate_structure(other), other,
                           solve(generate_structure(other), other))

    assert base.simulation_id != changed.simulation_id


# ─────────────────────────────────────────────
# Classification correctness
# ─────────────────────────────────────────────

def test_solver_outputs_are_classified_computed(full_report):
    results = full_report.section("results")
    stress = next(i for i in results.items if i.label == "Max stress")
    assert stress.classification is ValueClass.COMPUTED


def test_handbook_material_properties_are_classified_assumed(full_report):
    materials = full_report.section("materials")
    e_item = next(i for i in materials.items if "— E" in i.label)
    assert e_item.classification is ValueClass.ASSUMED
    assert "handbook" in e_item.source.lower()


def test_section_properties_are_classified_derived(full_report):
    materials = full_report.section("materials")
    chs = next(i for i in materials.items if i.label.startswith("CHS"))
    assert chs.classification is ValueClass.DERIVED


def test_self_weight_force_is_derived_from_computed_mass(full_report):
    loads = full_report.section("loads")
    mass = next(i for i in loads.items if i.label == "Self-weight mass")
    force = next(i for i in loads.items if i.label == "Self-weight force")
    assert mass.classification is ValueClass.COMPUTED
    assert force.classification is ValueClass.DERIVED
    assert "g" in force.source


def test_classification_counts_cover_every_item(full_report):
    counts = full_report.classification_counts()
    total = sum(counts.values())
    assert total == sum(len(s.items) for s in full_report.sections)


# ─────────────────────────────────────────────
# Gaps must be visible, not omitted
# ─────────────────────────────────────────────

def test_analyses_that_were_not_run_are_marked_not_modeled():
    report = _minimal_report()
    for key in ("buckling", "code", "sensitivity"):
        section = report.section(key)
        assert any(i.classification is ValueClass.NOT_MODELED for i in section.items), \
            f"{key} was not run and must be reported as NOT_MODELED"


def test_weightless_run_declares_self_weight_excluded():
    spec = EngineeringSpec()
    structure = generate_structure(spec)
    results = solve(structure, spec, combination=LIVE_ONLY_COMBINATION)
    report = build_report(structure, spec, results)

    loads = report.section("loads")
    item = next(i for i in loads.items if i.label == "Self-weight")
    assert item.classification is ValueClass.NOT_MODELED
    assert "weightless" in item.value.lower()
    assert any("weightless" in lim.lower() for lim in report.limitations)


def test_limitations_cover_the_major_unmodelled_physics(full_report):
    joined = " ".join(full_report.limitations).lower()
    for topic in ("material nonlinearity", "geometric nonlinearity", "bending",
                  "connections", "fatigue", "foundation", "imperfection",
                  "dynamic", "fire"):
        assert topic in joined, f"limitation list omits {topic}"


def test_limitations_are_not_empty_even_on_a_clean_run(full_report):
    assert len(full_report.limitations) >= 10


def test_buckling_section_warns_about_the_unconservative_range(full_report):
    section = full_report.section("buckling")
    item = next(i for i in section.items if "unconservative" in i.label.lower())
    assert "OVERESTIMATES" in item.note


def test_code_section_disclaims_compliance(full_report):
    notes = " ".join(full_report.section("code").notes)
    assert "not a compliance check" in notes
    assert "NOT IMPLEMENTED" in notes


def test_sensitivity_section_disclaims_statistical_meaning(full_report):
    section = full_report.section("sensitivity")
    item = next(i for i in section.items if i.label == "Statistical")
    assert item.value == "no"
    assert "NOT A CONFIDENCE INTERVAL" in item.note


def test_verification_section_states_it_checks_computation_not_safety(full_report):
    notes = " ".join(full_report.section("verification").notes)
    assert "COMPUTATION" in notes
    assert "safe" in notes


def test_validation_section_scopes_the_claim_to_the_solver(full_report):
    notes = " ".join(full_report.section("validation").notes)
    assert "says nothing about the structure analysed in this report" in notes


# ─────────────────────────────────────────────
# Positioning
# ─────────────────────────────────────────────

def test_positioning_refuses_the_certified_package_claim(full_report):
    assert "NOT a certified commercial structural-design package" in full_report.positioning
    assert "evidence-traceable" in full_report.positioning


def test_report_is_serialisable(full_report):
    data = report_to_dict(full_report)
    assert data["simulation_id"] == full_report.simulation_id
    assert len(data["sections"]) == len(full_report.sections)
    assert data["limitations"]
