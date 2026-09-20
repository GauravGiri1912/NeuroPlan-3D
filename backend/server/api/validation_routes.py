"""
NeuroPlan-3D — Experimental Validation API

Separate from the main structural pipeline: this exposes the fixed
steel-truss experimental validation case (Engineering Credibility ->
Real-World Validation), not anything derived from the user's own input.
"""
from fastapi import APIRouter

from ..validation.state import run_validation, run_independent_validation, DAMAGE_STATE_INAPPLICABILITY_REASON
from ..validation.datasets.steel_truss_zenodo import STEEL_TRUSS_DATASET
from .validation_schemas import (
    ValidationResultResponse, DatasetMetadataResponse, ExperimentalCaseResponse,
    SensorMappingResponse, ComparisonResultResponse, ComparisonSummaryResponse,
    ModelParameterResponse, IndependenceResponse,
    IndependentValidationResponse, DataLeakageCheckResponse,
)


def _serialize_parameter(p) -> ModelParameterResponse:
    return ModelParameterResponse(
        name=p.name, role=p.role.value, status=p.status.value,
        selected_using_measurements=p.selected_using_measurements,
        value_summary=p.value_summary, source_reference=p.source_reference,
        note=p.note,
    )

router = APIRouter(prefix="/api/validation", tags=["validation"])


def _serialize_dataset() -> DatasetMetadataResponse:
    d = STEEL_TRUSS_DATASET
    return DatasetMetadataResponse(
        title=d.title, authors=d.authors, institution=d.institution,
        doi=d.doi, license=d.license, publication_date=d.publication_date,
        version=d.version, repository=d.repository, files=d.files,
        description=d.description,
        linked_publication_title=d.linked_publication_title,
        linked_publication_doi=d.linked_publication_doi,
        linked_publication_url=d.linked_publication_url,
        retrieved=d.retrieved,
    )


@router.get("/steel-truss", response_model=ValidationResultResponse)
async def get_steel_truss_validation():
    """
    Run (or report the status of) the steel-truss experimental validation
    case. Always attempts a live run against the real solver and the real
    dataset file if present; falls back to REFERENCE_AVAILABLE (not an
    error, not a fabricated comparison) if the data file isn't present in
    this environment.
    """
    result = run_validation()

    case_resp = None
    if result.case:
        case_resp = ExperimentalCaseResponse(
            case_id=result.case.case_id,
            title=result.case.title,
            description=result.case.description,
            load_setup_description=result.case.load_setup_description,
            applicable=result.case.applicable,
            inapplicability_reason=result.case.inapplicability_reason,
            parameter_notes=result.case.parameter_notes,
        )

    summary_resp = None
    if result.summary:
        s = result.summary
        summary_resp = ComparisonSummaryResponse(
            n_points=s.n_points, mae=s.mae, rmse=s.rmse,
            max_absolute_error=s.max_absolute_error,
            max_relative_error=s.max_relative_error,
            r_squared=s.r_squared, r_squared_note=s.r_squared_note,
            uncertainty_note=s.uncertainty_note,
        )

    ind = result.independence
    return ValidationResultResponse(
        state=result.state.value,
        independence=IndependenceResponse(
            verdict=ind.verdict.value,
            headline=ind.headline,
            explanation=ind.explanation,
            standard_reference=ind.standard_reference,
            calibrated_parameters=[_serialize_parameter(p) for p in ind.calibrated_parameters],
            independent_parameters=[_serialize_parameter(p) for p in ind.independent_parameters],
            missing_roles=[r.value for r in ind.missing_roles],
        ),
        parameters=[_serialize_parameter(p) for p in result.parameters],
        error=result.error,
        dataset=_serialize_dataset(),
        case=case_resp,
        mappings=[
            SensorMappingResponse(
                sensor_id=m.sensor_id, node_id=m.node_id, member_id=m.member_id,
                dof=m.dof, status=m.status.value, reasoning=m.reasoning,
                comparable=m.comparable, incomparable_reason=m.incomparable_reason,
            )
            for m in result.mappings
        ],
        comparisons=[
            ComparisonResultResponse(
                sensor_id=c.sensor_id, node_id=c.node_id, quantity=c.quantity,
                experimental_value=c.experimental_value, neuroplan_value=c.neuroplan_value,
                units=c.units, absolute_error=c.absolute_error,
                relative_error=c.relative_error, mapping_status=c.mapping_status.value,
                mapping_note=c.mapping_note,
            )
            for c in result.comparisons
        ],
        summary=summary_resp,
        criterion_note=result.criterion_note,
        damage_scenarios_note=DAMAGE_STATE_INAPPLICABILITY_REASON,
    )


def _serialize_independence(ind) -> IndependenceResponse:
    return IndependenceResponse(
        verdict=ind.verdict.value,
        headline=ind.headline,
        explanation=ind.explanation,
        standard_reference=ind.standard_reference,
        calibrated_parameters=[_serialize_parameter(p) for p in ind.calibrated_parameters],
        independent_parameters=[_serialize_parameter(p) for p in ind.independent_parameters],
        missing_roles=[r.value for r in ind.missing_roles],
    )


def _serialize_comparison(c) -> ComparisonResultResponse:
    return ComparisonResultResponse(
        sensor_id=c.sensor_id, node_id=c.node_id, quantity=c.quantity,
        experimental_value=c.experimental_value, neuroplan_value=c.neuroplan_value,
        units=c.units, absolute_error=c.absolute_error,
        relative_error=c.relative_error, mapping_status=c.mapping_status.value,
        mapping_note=c.mapping_note,
    )


def _serialize_summary(s) -> ComparisonSummaryResponse | None:
    if s is None:
        return None
    return ComparisonSummaryResponse(
        n_points=s.n_points, mae=s.mae, rmse=s.rmse,
        max_absolute_error=s.max_absolute_error,
        max_relative_error=s.max_relative_error,
        r_squared=s.r_squared, r_squared_note=s.r_squared_note,
        uncertainty_note=s.uncertainty_note,
    )


@router.get("/independent", response_model=IndependentValidationResponse)
async def get_independent_validation():
    """
    Run the independent validation workflow — calibration/validation split,
    leakage detection, and honest status reporting.
    """
    result = run_independent_validation()

    return IndependentValidationResponse(
        status=result.status.value,
        status_label=result.status_label,
        calibration_case_id=result.calibration_case_id,
        calibration_description=result.calibration_description,
        calibration_sensor_ids=result.calibration_sensor_ids,
        calibration_comparisons=[_serialize_comparison(c) for c in result.calibration_comparisons],
        calibration_summary=_serialize_summary(result.calibration_summary),
        calibration_independence=_serialize_independence(result.calibration_independence),
        validation_case_id=result.validation_case_id,
        validation_description=result.validation_description,
        validation_sensor_ids=result.validation_sensor_ids,
        validation_comparisons=[_serialize_comparison(c) for c in result.validation_comparisons],
        validation_summary=_serialize_summary(result.validation_summary),
        validation_independence=_serialize_independence(result.validation_independence),
        midspan_comparison=_serialize_comparison(result.midspan_comparison) if result.midspan_comparison else None,
        midspan_is_independent=result.midspan_is_independent,
        midspan_note=result.midspan_note,
        leakage_check=DataLeakageCheckResponse(
            passed=result.leakage_check.passed,
            calibration_sensor_ids=result.leakage_check.calibration_sensor_ids,
            validation_sensor_ids=result.leakage_check.validation_sensor_ids,
            overlapping_sensor_ids=result.leakage_check.overlapping_sensor_ids,
            explanation=result.leakage_check.explanation,
        ),
        solver_method=result.solver_method,
        model_parameters=[_serialize_parameter(p) for p in result.model_parameters],
        calibration_parameters_used=result.calibration_parameters_used,
        validation_data_used_during_calibration=result.validation_data_used_during_calibration,
        limitations=result.limitations,
        scientific_explanation=result.scientific_explanation,
        error=result.error,
    )
