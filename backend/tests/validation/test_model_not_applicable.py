"""
Damage-scenario (post component-removal) applicability determination.

The dataset's "D" sheets (and all component-removal scenarios) require
bending/torsional physics the current pin-jointed axial-truss solver does
not model. This must produce MODEL_NOT_APPLICABLE, backed by the specific
evidence from the source publication — never a forced numeric comparison.
"""
from server.validation.state import DAMAGE_STATE_INAPPLICABILITY_REASON
from server.validation.models import ValidationState


def test_inapplicability_reason_cites_specific_evidence():
    reason = DAMAGE_STATE_INAPPLICABILITY_REASON.lower()
    assert "vierendeel" in reason
    assert "bending" in reason
    assert "torsional" in reason
    assert "axial" in reason


def test_model_not_applicable_is_a_real_state():
    assert ValidationState.MODEL_NOT_APPLICABLE.value == "model_not_applicable"


def test_inapplicability_reason_is_not_empty_and_not_generic():
    """A placeholder like 'not supported' would fail this — the reason
    must be specific enough to be checked against the source."""
    assert len(DAMAGE_STATE_INAPPLICABILITY_REASON) > 200
    assert "supplementary information" in DAMAGE_STATE_INAPPLICABILITY_REASON.lower()
