"""
NeuroPlan-3D — Pydantic schemas for the Experimental Validation API.
"""
from pydantic import BaseModel
from typing import Optional


class DatasetMetadataResponse(BaseModel):
    title: str
    authors: list[str]
    institution: str
    doi: str
    license: str
    publication_date: str
    version: str
    repository: str
    files: list[str]
    description: str
    linked_publication_title: str
    linked_publication_doi: str
    linked_publication_url: str
    retrieved: str


class ParameterNoteResponse(BaseModel):
    text: str


class ExperimentalCaseResponse(BaseModel):
    case_id: str
    title: str
    description: str
    load_setup_description: str
    applicable: bool
    inapplicability_reason: str
    parameter_notes: list[str]


class SensorMappingResponse(BaseModel):
    sensor_id: str
    node_id: Optional[int]
    member_id: Optional[int]
    dof: str
    status: str
    reasoning: str
    comparable: bool
    incomparable_reason: str


class ComparisonResultResponse(BaseModel):
    sensor_id: str
    node_id: Optional[int]
    quantity: str
    experimental_value: float
    neuroplan_value: float
    units: str
    absolute_error: float
    relative_error: Optional[float]
    mapping_status: str
    mapping_note: str


class ComparisonSummaryResponse(BaseModel):
    n_points: int
    mae: Optional[float]
    rmse: Optional[float]
    max_absolute_error: Optional[float]
    max_relative_error: Optional[float]
    r_squared: Optional[float]
    r_squared_note: str
    uncertainty_note: str


class ModelParameterResponse(BaseModel):
    name: str
    role: str
    status: str
    selected_using_measurements: bool
    value_summary: str
    source_reference: str
    note: str


class IndependenceResponse(BaseModel):
    """The calibration-vs-validation verdict (ASME V&V 10 / NAFEMS)."""
    verdict: str
    headline: str
    explanation: str
    standard_reference: str
    calibrated_parameters: list[ModelParameterResponse]
    independent_parameters: list[ModelParameterResponse]
    missing_roles: list[str]


class ValidationResultResponse(BaseModel):
    state: str
    independence: IndependenceResponse
    parameters: list[ModelParameterResponse]
    error: Optional[str]
    dataset: DatasetMetadataResponse
    case: Optional[ExperimentalCaseResponse]
    mappings: list[SensorMappingResponse]
    comparisons: list[ComparisonResultResponse]
    summary: Optional[ComparisonSummaryResponse]
    criterion_note: str
    damage_scenarios_note: str


class DataLeakageCheckResponse(BaseModel):
    passed: bool
    calibration_sensor_ids: list[str]
    validation_sensor_ids: list[str]
    overlapping_sensor_ids: list[str]
    explanation: str


class IndependentValidationResponse(BaseModel):
    """Full independent validation result with explicit calibration/validation split."""
    model_config = {"protected_namespaces": ()}
    status: str
    status_label: str
    # Calibration side
    calibration_case_id: str
    calibration_description: str
    calibration_sensor_ids: list[str]
    calibration_comparisons: list[ComparisonResultResponse]
    calibration_summary: Optional[ComparisonSummaryResponse]
    calibration_independence: IndependenceResponse
    # Validation side
    validation_case_id: str
    validation_description: str
    validation_sensor_ids: list[str]
    validation_comparisons: list[ComparisonResultResponse]
    validation_summary: Optional[ComparisonSummaryResponse]
    validation_independence: IndependenceResponse
    # Mid-span
    midspan_comparison: Optional[ComparisonResultResponse]
    midspan_is_independent: bool
    midspan_note: str
    # Leakage
    leakage_check: DataLeakageCheckResponse
    # Model
    solver_method: str
    model_parameters: list[ModelParameterResponse]
    calibration_parameters_used: list[str]
    validation_data_used_during_calibration: bool
    # Limitations
    limitations: list[str]
    scientific_explanation: str
    error: Optional[str]
