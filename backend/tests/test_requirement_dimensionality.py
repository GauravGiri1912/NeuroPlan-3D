"""
NeuroPlan-3D — Structural Dimension Interpretation Regression Tests

A real bug shipped here: "design a 20m bridge ... build a 3d one" parsed to
a PLANAR Pratt truss, because the fallback parser's keyword list contained
'3d truss' but not a bare '3d'. The user was shown "SYSTEM: PLANAR (2D)"
for an explicitly three-dimensional request.

These tests lock in:
  - explicit 3D intent selects the supported spatial system, in every
    phrasing listed in the requirement,
  - the resulting geometry is GENUINELY spatial (real non-zero z, real 3D
    solver) — not a 3D label over a planar model,
  - explicit 2D intent stays planar,
  - unstated dimensionality is reported as an assumption, never as
    certainty,
  - the AI's proposal cannot override an explicit dimensional statement,
  - the existing demo presets are unaffected.

Every assertion runs the real parser, the real generator, and the real
solver. Nothing is stubbed.
"""
import copy
import pytest

from server.core.parser.requirement_parser import (
    _build_spec_from_dict, parse_requirements_fallback,
)
from server.core.parser.dimensionality import detect_dimensionality
from server.core.generator.topology import generate_structure
from server.core.generator.space_truss import assert_is_genuinely_spatial
from server.core.fea.solver import solve
from server.models.structure import DimensionalityIntent, StructureType

EPS = 1e-9

# The phrasings the requirement names explicitly, plus the bare-"3d" case
# that actually shipped broken.
EXPLICIT_3D_INPUTS = [
    "design a 20m bridge ... build a 3d one",
    "design a 20m bridge, make it 3D",
    "design a 20m bridge, 3-D please",
    "design a 20m three dimensional bridge",
    "design a 20m three-dimensional bridge",
    "design a 20m space truss",
    "design a 20m space-truss",
    "design a 20m spatial truss",
    "design a 20m space frame",
    "design a 20m box truss",
]

EXPLICIT_2D_INPUTS = [
    "design a 2D Pratt truss, 20m span",
    "design a two-dimensional truss, 20m span",
    "design a planar warren truss, 18m span",
    "design a 20m howe truss",
]


# ── 1. Explicit 3D intent selects the spatial system ──────────────────

@pytest.mark.parametrize("raw", EXPLICIT_3D_INPUTS)
def test_explicit_3d_intent_selects_space_truss(raw):
    spec = parse_requirements_fallback(raw)
    assert spec.structure_type is StructureType.SPACE_TRUSS, (
        f"explicit 3D request parsed as {spec.structure_type.value}: {raw!r}"
    )
    assert spec.structure_type.is_spatial is True
    assert spec.dimensionality_intent is DimensionalityIntent.EXPLICIT_SPATIAL


def test_the_exact_reported_input_is_no_longer_planar():
    """The literal regression from the bug report."""
    spec = parse_requirements_fallback("design a 20m bridge ... build a 3d one")
    assert spec.structure_type is not StructureType.PRATT
    assert spec.structure_type.is_spatial is True


# ── 2 & 3. The geometry is genuinely spatial, not a 3D label ──────────

@pytest.mark.parametrize("raw", EXPLICIT_3D_INPUTS)
def test_explicit_3d_produces_genuinely_spatial_geometry(raw):
    spec = parse_requirements_fallback(raw)
    structure = generate_structure(spec)

    # The existing contract check: raises if the geometry is really planar.
    assert_is_genuinely_spatial(structure)

    zs = [n.z for n in structure.nodes]
    z_extent = max(zs) - min(zs)
    assert z_extent > 0.1, "spatial request produced a flat model"
    assert z_extent == pytest.approx(spec.width, rel=1e-9)
    assert spec.width > 0, "a space truss needs a real transverse width"

    # Members must actually join the two planes.
    node_map = structure.node_dict()
    dz_members = sum(
        1 for m in structure.members
        if abs(node_map[m.node_j].z - node_map[m.node_i].z) > EPS
    )
    assert dz_members > 0, "no member spans z — the two planes are unconnected"


def test_explicit_3d_uses_the_real_3d_solver():
    spec = parse_requirements_fallback("design a 20m bridge supporting 50 kN, build a 3d one")
    structure = generate_structure(spec)
    results = solve(structure, spec)

    assert results.is_spatial is True
    assert results.dof_count == 3 * len(structure.nodes)
    assert results.equilibrium.passed


# ── 4. Unstated dimensionality is disclosed, never claimed ────────────

def test_unspecified_dimensionality_is_reported_as_unspecified():
    spec = parse_requirements_fallback(
        "design a 20-meter pedestrian bridge truss supporting a 50 kN center load"
    )
    assert spec.dimensionality_intent is DimensionalityIntent.UNSPECIFIED
    # Existing behaviour preserved: planar remains the default choice...
    assert spec.structure_type is StructureType.PRATT
    # ...but it is disclosed as an assumption rather than asserted.
    assert any(
        "assumed, not requested" in note for note in spec.defaults_applied
    ), f"dimensionality assumption was not disclosed: {spec.defaults_applied}"


def test_unspecified_dimensionality_does_not_mark_structure_type_as_specified():
    """The user did not choose this system, so it must not look like they did."""
    spec = parse_requirements_fallback("build me a 20m truss for a 50 kN load")
    assert spec.dimensionality_intent is DimensionalityIntent.UNSPECIFIED
    assert any("structure type" in note for note in spec.defaults_applied)


def test_conflicting_dimensionality_is_flagged_and_not_silently_resolved():
    """'3D Pratt truss' names a planar type and a 3D system at once."""
    spec = parse_requirements_fallback("design a 3D pratt truss, 20m span")

    assert spec.dimensionality_intent is DimensionalityIntent.CONFLICTING
    # The explicit 3D term is honoured (requirement: 3D intent selects 3D)...
    assert spec.structure_type is StructureType.SPACE_TRUSS
    # ...and the conflict is stated, including that it is not certain.
    conflict_notes = [n for n in spec.defaults_applied if "states both" in n]
    assert conflict_notes, f"conflict not disclosed: {spec.defaults_applied}"
    assert "not certain" in conflict_notes[0]


def test_conflicting_spatial_type_with_2d_word_still_builds_real_3d_geometry():
    """A flagged conflict must still never produce a faked 3D model."""
    spec = parse_requirements_fallback("design a 2D space truss, 20m span")
    assert spec.dimensionality_intent is DimensionalityIntent.CONFLICTING
    assert_is_genuinely_spatial(generate_structure(spec))


# ── 5. Explicit 2D requests stay planar ───────────────────────────────

@pytest.mark.parametrize("raw", EXPLICIT_2D_INPUTS)
def test_explicit_2d_intent_stays_planar(raw):
    spec = parse_requirements_fallback(raw)
    assert spec.structure_type.is_spatial is False, (
        f"planar request parsed as spatial: {raw!r}"
    )
    assert spec.dimensionality_intent is DimensionalityIntent.EXPLICIT_PLANAR

    structure = generate_structure(spec)
    assert all(abs(n.z) < EPS for n in structure.nodes), "planar model has non-zero z"


def test_2d_pratt_truss_remains_pratt():
    spec = parse_requirements_fallback("design a 2D Pratt truss, 20m span")
    assert spec.structure_type is StructureType.PRATT


def test_named_planar_types_are_preserved():
    assert parse_requirements_fallback("a 20m warren truss").structure_type is StructureType.WARREN
    assert parse_requirements_fallback("a 20m howe truss").structure_type is StructureType.HOWE


# ── 6. Explicit 3D requests keep working end-to-end ───────────────────

def test_3d_space_truss_request_remains_genuinely_3d():
    spec = parse_requirements_fallback("3D space truss, 24m span, 4m wide, 80 kN distributed")
    assert spec.structure_type is StructureType.SPACE_TRUSS
    assert spec.width == pytest.approx(4.0)

    structure = generate_structure(spec)
    assert_is_genuinely_spatial(structure)
    results = solve(structure, spec)
    assert results.is_spatial is True


# ── 7. The AI's proposal cannot override an explicit statement ────────

def test_ai_planar_proposal_is_overridden_by_explicit_3d_text():
    """
    The second failure surface: the AI parser returning 'pratt' for a
    requirement that plainly says 3D. The text is authoritative.
    """
    ai_output = {
        "structure_type": "pratt", "span": 20, "height": 3.3, "num_panels": 8,
        "primary_load": 50000, "specified_fields": ["span", "primary_load"],
    }
    spec = _build_spec_from_dict(ai_output, "design a 20m bridge, build a 3d one, 50 kN")

    assert spec.structure_type is StructureType.SPACE_TRUSS
    assert spec.width > 0
    assert any("overridden" in note for note in spec.defaults_applied)
    assert_is_genuinely_spatial(generate_structure(spec))


def test_ai_spatial_proposal_is_overridden_by_explicit_2d_text():
    ai_output = {
        "structure_type": "space_truss", "span": 20, "height": 3.3,
        "num_panels": 8, "primary_load": 50000, "specified_fields": ["span"],
    }
    spec = _build_spec_from_dict(ai_output, "design a 2D warren truss, 20m")

    assert spec.structure_type is StructureType.WARREN
    assert spec.structure_type.is_spatial is False
    assert any("overridden" in note for note in spec.defaults_applied)


def test_ai_agreement_produces_no_override_note():
    ai_output = {
        "structure_type": "space_truss", "span": 24, "height": 2.5, "width": 4.0,
        "num_panels": 8, "primary_load": 80000,
        "specified_fields": ["span", "width", "primary_load"],
    }
    spec = _build_spec_from_dict(ai_output, "3D space truss, 24m span, 4m wide")

    assert spec.structure_type is StructureType.SPACE_TRUSS
    assert not [n for n in spec.defaults_applied if "overridden" in n]


def test_ai_proposal_is_kept_when_text_states_no_dimensionality():
    """With nothing explicit to contradict, the AI's reading survives."""
    ai_output = {
        "structure_type": "warren", "span": 20, "height": 3.3, "num_panels": 8,
        "primary_load": 50000, "specified_fields": ["span"],
    }
    spec = _build_spec_from_dict(ai_output, "a 20m bridge carrying 50 kN")

    assert spec.structure_type is StructureType.WARREN
    assert spec.dimensionality_intent is DimensionalityIntent.UNSPECIFIED


# ── 8. Detector unit behaviour ────────────────────────────────────────

def test_detector_reports_the_terms_it_matched_as_evidence():
    evidence = detect_dimensionality("design a 3D pratt truss")
    assert evidence.intent is DimensionalityIntent.CONFLICTING
    assert "3d" in evidence.spatial_terms
    assert "pratt" in evidence.planar_terms
    assert "'3d'" in evidence.describe()


def test_detector_does_not_fire_on_unrelated_words():
    """'3d'/'2d' must match as words, not as fragments of other tokens."""
    for text in ("a 3dimensional-ish name", "model3d_v2", "a 20m bridge"):
        assert detect_dimensionality(text).intent is DimensionalityIntent.UNSPECIFIED, text


def test_detector_handles_empty_input():
    assert detect_dimensionality("").intent is DimensionalityIntent.UNSPECIFIED


# ── 9. Existing demo presets are unaffected ───────────────────────────

def test_demo_preset_natural_language_still_parses_planar():
    """Demo 1 sends this exact string through the parser."""
    spec = parse_requirements_fallback(
        "Design a 20-meter pedestrian bridge truss supporting a 50 kN "
        "center load with A36 steel"
    )
    assert spec.structure_type is StructureType.PRATT
    assert spec.structure_type.is_spatial is False
    assert spec.span == pytest.approx(20.0)
    assert spec.primary_load == pytest.approx(50000.0)
    assert spec.material_key == "A36"

    structure = generate_structure(spec)
    assert all(abs(n.z) < EPS for n in structure.nodes)
    assert solve(structure, spec).is_spatial is False


def test_demo_presets_bypass_the_parser_entirely_and_are_unchanged():
    """
    Demos 2 and 3 post a pre-built spec, so the parser must not be able to
    affect them. Their dimensionality is whatever the spec says.
    """
    # Imported from the existing preset regression module rather than
    # re-declared, so the two test files cannot drift apart.
    from test_demo_presets import DEMO_1, DEMO_3

    d1 = copy.deepcopy(DEMO_1)
    d3 = copy.deepcopy(DEMO_3)

    assert d1.structure_type is StructureType.PRATT
    assert d3.structure_type is StructureType.SPACE_TRUSS
    # Pre-built specs are never parsed, so intent stays at its default.
    assert d1.dimensionality_intent is DimensionalityIntent.UNSPECIFIED

    assert solve(generate_structure(d1), d1).is_spatial is False
    assert solve(generate_structure(d3), d3).is_spatial is True
