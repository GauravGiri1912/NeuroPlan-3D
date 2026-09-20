"""
Calibration vs. validation (ASME V&V 10 / NAFEMS).

The point of these tests is not that the current case reports the right
label today — it is that the label RESPONDS. If a future change tunes a
material property, a section, a support, a load, the geometry or the
sensor mapping against the measured results, the verdict must degrade on
its own. A hardcoded string would pass a "looks right" review and then
silently mislabel a fitted model as validated.
"""
import pytest

from server.validation.models import (
    EvidenceIndependence, ModelParameter, ParameterRole, ParameterStatus,
    ValidationState, AcceptanceCriterion, IndependenceAssessment,
)
from server.validation.independence import (
    assess_independence, blocks_criterion_promotion,
)
from server.validation.cases import steel_truss_loss_of_chord as case_module


def _param(role: ParameterRole, calibrated: bool = False) -> ModelParameter:
    return ModelParameter(
        name=f"{role.value} parameter",
        role=role,
        status=ParameterStatus.SOURCED,
        selected_using_measurements=calibrated,
    )


def _full_clean_inventory() -> list[ModelParameter]:
    return [_param(role) for role in ParameterRole]


def test_fully_sourced_inventory_is_independent():
    assessment = assess_independence(_full_clean_inventory())
    assert assessment.verdict is EvidenceIndependence.INDEPENDENT
    assert assessment.headline == "INDEPENDENT REFERENCE COMPARISON"
    assert not assessment.calibrated_parameters


@pytest.mark.parametrize("role", list(ParameterRole))
def test_calibrating_any_single_role_downgrades_the_verdict(role):
    """
    The user-facing guarantee: tuning ANY one of sensor mapping, material
    E, cross-section, support stiffness, load or geometry against the
    measurements flips the verdict. One fitted input is enough.
    """
    inventory = [_param(r, calibrated=(r is role)) for r in ParameterRole]
    assessment = assess_independence(inventory)

    assert assessment.verdict is EvidenceIndependence.CALIBRATED
    assert "NOT INDEPENDENT VALIDATION" in assessment.headline
    assert [p.role for p in assessment.calibrated_parameters] == [role]
    assert role.value in assessment.explanation


def test_empty_inventory_is_not_assessed_rather_than_independent():
    """
    `any([])` is False, so a naive implementation would report an
    unexamined model as independent. That is the single most dangerous
    failure mode of this whole feature.
    """
    assessment = assess_independence([])
    assert assessment.verdict is EvidenceIndependence.NOT_ASSESSED
    assert assessment.verdict is not EvidenceIndependence.INDEPENDENT


@pytest.mark.parametrize("omitted", list(ParameterRole))
def test_an_undeclared_role_prevents_an_independence_claim(omitted):
    """A model may only be called independent if every role was examined."""
    inventory = [_param(r) for r in ParameterRole if r is not omitted]
    assessment = assess_independence(inventory)

    assert assessment.verdict is EvidenceIndependence.NOT_ASSESSED
    assert omitted in assessment.missing_roles


def test_calibrated_verdict_wins_over_incomplete_inventory():
    """A known calibration is reported as such, not masked as unassessed."""
    inventory = [_param(ParameterRole.MATERIAL, calibrated=True)]
    assessment = assess_independence(inventory)
    assert assessment.verdict is EvidenceIndependence.CALIBRATED


def test_only_independent_evidence_may_be_promoted_to_criterion_met():
    for verdict, blocked in (
        (EvidenceIndependence.INDEPENDENT, False),
        (EvidenceIndependence.CALIBRATED, True),
        (EvidenceIndependence.NOT_ASSESSED, True),
    ):
        assessment = IndependenceAssessment(
            verdict=verdict, headline="", explanation="", standard_reference="",
        )
        assert blocks_criterion_promotion(assessment) is blocked


def test_criterion_met_is_refused_for_the_calibrated_steel_truss_case():
    """
    Even handed a satisfied acceptance criterion, a calibrated case must
    fall back to REFERENCE_COMPARED. Passing a threshold you tuned toward
    is not a pass.
    """
    from server.validation.state import _resolve_state

    assessment = assess_independence(case_module.build_parameter_inventory())
    criterion = AcceptanceCriterion(
        description="hypothetical", metric="relative_error",
        threshold=0.25, source="test", defensible=True,
    )
    resolved = _resolve_state(ValidationState.CRITERION_MET, criterion, assessment)
    assert resolved is ValidationState.REFERENCE_COMPARED


def test_steel_truss_inventory_covers_every_role_and_flags_the_sensor_mapping():
    """
    The real case: the inventory must be exhaustive, and the one thing
    that WAS chosen using the data — the sensor mapping — must be the
    thing flagged. Everything else came from the publication.
    """
    inventory = case_module.build_parameter_inventory()
    assert {p.role for p in inventory} == set(ParameterRole)

    calibrated = [p for p in inventory if p.selected_using_measurements]
    assert [p.role for p in calibrated] == [ParameterRole.SENSOR_MAPPING]

    assessment = assess_independence(inventory)
    assert assessment.verdict is EvidenceIndependence.CALIBRATED


def test_published_values_have_not_drifted_from_their_sources():
    """
    Guards the other half of the risk: a parameter could be silently
    tuned WITHOUT its calibration flag being set. These constants are
    transcribed from the publication, so any edit to fit the data fails
    here and forces the change to be justified.
    """
    assert case_module._E_PA == pytest.approx(207_639.8e6)   # [F4] Fig. 4
    assert case_module._FY_PA == pytest.approx(326.6e6)      # [F4] Fig. 4
    assert case_module.PANEL_M == pytest.approx(0.5)         # [G] Fig. 2
    assert case_module.HEIGHT_M == pytest.approx(0.6)        # [G] Fig. 2
    assert case_module.N_PANELS == 12                        # [G] Fig. 2
    assert case_module._LOAD_PER_POINT_N == pytest.approx(20_000.0)  # [F6]
    assert case_module._AREA_CM2["C1"] == pytest.approx(8.4)  # [T2] Table 2
    assert case_module._AREA_CM2["D5"] == pytest.approx(1.7)  # [T2] Table 2
