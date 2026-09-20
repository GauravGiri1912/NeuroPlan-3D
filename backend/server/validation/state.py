"""
NeuroPlan-3D — Validation Orchestration & State Machine

`run_validation()` is the single entry point: it runs the ACTUAL
production solver (server.core.fea.solver.solve — the same function the
main pipeline uses) against the reconstructed experimental case, compares
against real measurements loaded from the actual dataset file, and
returns a state per the state machine documented in `models.ValidationState`.

No acceptance criterion currently qualifies as defensible for this case
(see `ACCEPTANCE_CRITERION_NOTE`) — so a successful comparison lands on
REFERENCE_COMPARED, never CRITERION_MET. This is a deliberate scientific
choice, not an oversight.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.fea.solver import solve
from ..models.structure import AnalysisResults
from .models import (
    ValidationState, ComparisonResult, ComparisonSummary, ExperimentalCase,
    ModelMapping, AcceptanceCriterion, IndependenceAssessment, ModelParameter,
    ParameterStatus,
)
from .independence import assess_independence, blocks_criterion_promotion
from .comparison.engine import compare_point, summarize
from .cases import steel_truss_loss_of_chord as case_module
from .cases.steel_truss_measurements import load_measurements, DatasetFileNotFoundError

ACCEPTANCE_CRITERION_NOTE = (
    "No acceptance criterion is defined by the source publication (its own "
    "validation, Section 2.4.1.5, is qualitative — 'confirms the results', "
    "not a numeric threshold). A generic threshold such as 'error < 10%' "
    "would be arbitrary and is not applied. Additionally, the sensor-to-node "
    "mapping used for the outer sensors is ASSUMED, not SOURCED: the source "
    "places the transducers at interior lower-chord panel points without "
    "saying which, leaving 10 possible symmetric layouts, and the one used "
    "here was selected with reference to the measured data (see "
    "steel_truss_loss_of_chord.py). That makes the agreement at those "
    "sensors partly circular — it is NOT independent evidence that the "
    "solver is correct. Only mid-span, which is the same node under every "
    "candidate layout, is free of this caveat. For all of these reasons "
    "this comparison is reported as REFERENCE_COMPARED, never CRITERION_MET."
)

# Damage-scenario (post component-removal) applicability — see Phase 15.
# The source publication explicitly and repeatedly describes bending
# moments, torsional deformation and "Vierendeel-type mechanisms" as the
# dominant response after member removal (Supplementary Information
# Sections 2.2-2.4, e.g. p.59-77: "A Vierendeel-type mechanism is
# activated, causing a substantial increase in bending..."). NeuroPlan's
# solver is a pin-jointed, axial-force-only Direct Stiffness formulation
# with no bending or torsional DOF. Comparing damaged-state predictions
# against measurements would therefore not be scientifically meaningful.
DAMAGE_STATE_INAPPLICABILITY_REASON = (
    "The source publication documents that component removal activates "
    "Vierendeel-type bending mechanisms and global torsional deformation "
    "in the damaged structure (Supplementary Information Sections 2.2-2.4). "
    "NeuroPlan's solver is a pin-jointed, axial-force-only Direct Stiffness "
    "formulation with no bending or torsional degrees of freedom. A "
    "comparison against post-damage measurements would not be scientifically "
    "meaningful and is not attempted. This applies to all 'D' (damaged) "
    "sheets and all component-removal scenarios in this dataset."
)


@dataclass
class ValidationRunResult:
    state: ValidationState
    case: ExperimentalCase | None
    comparisons: list[ComparisonResult]
    summary: ComparisonSummary | None
    mappings: list[ModelMapping]
    criterion: AcceptanceCriterion | None
    criterion_note: str
    independence: IndependenceAssessment
    parameters: list[ModelParameter] = field(default_factory=list)
    error: str | None = None


def _resolve_state(
    proposed: ValidationState,
    criterion: AcceptanceCriterion | None,
    assessment: IndependenceAssessment,
) -> ValidationState:
    """
    Gate the final state on the independence verdict.

    A comparison whose parameters were fitted to the data cannot be
    promoted to CRITERION_MET, regardless of how well it scores. Passing
    a threshold you tuned toward is not a pass — it is the fit reporting
    on itself. This is enforced here, structurally, so that adding an
    AcceptanceCriterion later cannot quietly upgrade a calibrated case.
    """
    if proposed is ValidationState.CRITERION_MET and blocks_criterion_promotion(assessment):
        return ValidationState.REFERENCE_COMPARED
    return proposed


def run_validation(dataset_path: str | None = None) -> ValidationRunResult:
    """
    Run the full validation pipeline for the one applicable case
    (steel truss, undamaged baseline, lower-chord test series).
    """
    case = case_module.build_case()
    parameters = case_module.build_parameter_inventory()
    assessment = assess_independence(parameters)

    try:
        measurements = load_measurements(dataset_path)
    except DatasetFileNotFoundError as e:
        return ValidationRunResult(
            state=ValidationState.REFERENCE_AVAILABLE,
            case=case,
            comparisons=[],
            summary=None,
            mappings=case_module.build_sensor_mappings(),
            criterion=None,
            criterion_note=ACCEPTANCE_CRITERION_NOTE,
            independence=assessment,
            parameters=parameters,
            error=(
                f"Reference dataset is documented and its case is reconstructed, "
                f"but the underlying data file is not available in this environment "
                f"to run the comparison ({e})."
            ),
        )

    structure, node_index = case_module.build_structure()
    spec = case_module.build_spec()

    # THE ACTUAL PRODUCTION SOLVER — identical call the main pipeline uses.
    results: AnalysisResults = solve(structure, spec)

    node_results = {r.node_id: r for r in results.node_results}
    mappings = case_module.build_sensor_mappings()

    comparisons: list[ComparisonResult] = []
    measurement_by_sensor = {m.sensor_id: m for m in measurements}
    for mapping in mappings:
        meas = measurement_by_sensor.get(mapping.sensor_id)
        if meas is None or mapping.node_id is None:
            continue
        # Sign convention: the publication defines vertical displacement as
        # positive DOWNWARD (Section 1.4.1.1). NeuroPlan's Y-axis is
        # positive UP, so a downward deflection is a negative UY. This is
        # a coordinate-convention conversion, not a modification of either
        # value — the raw experimental reading and the raw solver UY are
        # both used unchanged; only the sign alignment is applied here, and
        # it is applied identically to every point.
        neuroplan_downward_mm = -node_results[mapping.node_id].dy * 1000.0
        comparisons.append(compare_point(
            sensor_id=mapping.sensor_id,
            node_id=mapping.node_id,
            quantity="vertical_displacement",
            experimental_value=meas.value,
            neuroplan_value=neuroplan_downward_mm,
            units="mm",
            mapping_status=mapping.status,
            mapping_note=mapping.reasoning,
        ))

    summary = summarize(comparisons)

    criterion = None
    return ValidationRunResult(
        state=_resolve_state(ValidationState.REFERENCE_COMPARED, criterion, assessment),
        case=case,
        comparisons=comparisons,
        summary=summary,
        mappings=mappings,
        criterion=criterion,
        criterion_note=ACCEPTANCE_CRITERION_NOTE,
        independence=assessment,
        parameters=parameters,
        error=None,
    )


def run_independent_validation(dataset_path: str | None = None) -> "IndependentValidationResult":
    """
    Run the independent validation workflow.

    Uses the SAME solver, SAME model, but evaluates against BOTH South
    (calibration) and North (validation) sensors, with explicit leakage
    detection and honest status reporting.
    """
    from .independent import (
        IndependentValidationResult, IndependentValidationStatus, STATUS_LABELS,
        detect_data_leakage, MIDSPAN_INDEPENDENT_NOTE,
        INSUFFICIENT_DATA_EXPLANATION, LIMITATIONS,
    )
    from .cases.steel_truss_measurements import load_north_measurements

    SOLVER_METHOD = "3D Direct Stiffness Method (pin-jointed truss, 3 translational DOF/node)"

    case = case_module.build_case()
    parameters = case_module.build_parameter_inventory()
    calibration_assessment = assess_independence(parameters)

    # Calibration sensor IDs (South, 1-7)
    cal_sensor_ids = list(case_module.SOUTH_SENSOR_NODES.keys())
    # Validation sensor IDs (North, 8-14)
    val_sensor_ids = list(case_module.NORTH_SENSOR_NODES.keys())

    # Leakage detection
    leakage = detect_data_leakage(cal_sensor_ids, val_sensor_ids)
    if not leakage.passed:
        return IndependentValidationResult(
            status=IndependentValidationStatus.BLOCKED_DATA_LEAKAGE,
            status_label=STATUS_LABELS[IndependentValidationStatus.BLOCKED_DATA_LEAKAGE],
            calibration_case_id=case_module.CASE_ID,
            calibration_description="South-side sensors 1-7 (mapping calibrated)",
            calibration_sensor_ids=cal_sensor_ids,
            calibration_comparisons=[], calibration_summary=None,
            calibration_independence=calibration_assessment,
            validation_case_id=f"{case_module.CASE_ID}_north",
            validation_description="North-side sensors 8-14",
            validation_sensor_ids=val_sensor_ids,
            validation_comparisons=[], validation_summary=None,
            validation_independence=calibration_assessment,
            midspan_comparison=None, midspan_is_independent=False,
            midspan_note="Blocked by data leakage.",
            leakage_check=leakage,
            solver_method=SOLVER_METHOD,
            model_parameters=parameters,
            calibration_parameters_used=[p.name for p in parameters if p.selected_using_measurements],
            validation_data_used_during_calibration=True,
            limitations=LIMITATIONS,
            scientific_explanation=leakage.explanation,
        )

    # Load measurements
    try:
        south_measurements = load_measurements(dataset_path)
        north_measurements = load_north_measurements(dataset_path)
    except DatasetFileNotFoundError as e:
        return IndependentValidationResult(
            status=IndependentValidationStatus.NOT_RUN,
            status_label=STATUS_LABELS[IndependentValidationStatus.NOT_RUN],
            calibration_case_id=case_module.CASE_ID,
            calibration_description="South-side sensors 1-7 (mapping calibrated)",
            calibration_sensor_ids=cal_sensor_ids,
            calibration_comparisons=[], calibration_summary=None,
            calibration_independence=calibration_assessment,
            validation_case_id=f"{case_module.CASE_ID}_north",
            validation_description="North-side sensors 8-14",
            validation_sensor_ids=val_sensor_ids,
            validation_comparisons=[], validation_summary=None,
            validation_independence=calibration_assessment,
            midspan_comparison=None, midspan_is_independent=False,
            midspan_note="Dataset not available.",
            leakage_check=leakage,
            solver_method=SOLVER_METHOD,
            model_parameters=parameters,
            calibration_parameters_used=[p.name for p in parameters if p.selected_using_measurements],
            validation_data_used_during_calibration=False,
            limitations=LIMITATIONS,
            scientific_explanation=f"Dataset not available: {e}",
            error=str(e),
        )

    # Run solver ONCE — same model for both sides
    structure, node_index = case_module.build_structure()
    spec = case_module.build_spec()
    results: AnalysisResults = solve(structure, spec)
    node_results = {r.node_id: r for r in results.node_results}

    def _build_comparisons(sensor_nodes, measurements):
        comps = []
        mappings = []
        measurement_by_sensor = {m.sensor_id: m for m in measurements}
        for sensor_id, node_id in sensor_nodes.items():
            high_conf = node_id == case_module.MIDSPAN_NODE
            mappings.append(ModelMapping(
                sensor_id=sensor_id, node_id=node_id, dof="UY",
                status=ParameterStatus.SOURCED if high_conf else ParameterStatus.ASSUMED,
                reasoning="Mid-span (layout-invariant)" if high_conf else "Calibration-derived mapping",
            ))
            meas = measurement_by_sensor.get(sensor_id)
            if meas is None:
                continue
            neuroplan_downward_mm = -node_results[node_id].dy * 1000.0
            comps.append(compare_point(
                sensor_id=sensor_id, node_id=node_id,
                quantity="vertical_displacement",
                experimental_value=meas.value,
                neuroplan_value=neuroplan_downward_mm,
                units="mm",
                mapping_status=ParameterStatus.SOURCED if high_conf else ParameterStatus.ASSUMED,
                mapping_note="Layout-invariant mid-span" if high_conf else "Calibration-derived",
            ))
        return comps

    cal_comparisons = _build_comparisons(case_module.SOUTH_SENSOR_NODES, south_measurements)
    val_comparisons = _build_comparisons(case_module.NORTH_SENSOR_NODES, north_measurements)

    cal_summary = summarize(cal_comparisons)
    val_summary = summarize(val_comparisons)

    # Validation independence: same inventory, mapping still calibrated
    val_assessment = assess_independence(parameters)

    # Mid-span: the one genuinely independent point
    # North mid-span is sensor "11" → node 6
    midspan_comp = next((c for c in val_comparisons if c.sensor_id == "11"), None)

    # The honest status: INSUFFICIENT_DATA because the mapping is calibration-derived
    # and the one independent point (mid-span) is n=1
    status = IndependentValidationStatus.INSUFFICIENT_DATA

    return IndependentValidationResult(
        status=status,
        status_label=STATUS_LABELS[status],
        calibration_case_id=case_module.CASE_ID,
        calibration_description="South-side sensors 1-7 (mapping calibrated against measured deflection profile)",
        calibration_sensor_ids=cal_sensor_ids,
        calibration_comparisons=cal_comparisons,
        calibration_summary=cal_summary,
        calibration_independence=calibration_assessment,
        validation_case_id=f"{case_module.CASE_ID}_north",
        validation_description="North-side sensors 8-14 (same mapping, not independently documented)",
        validation_sensor_ids=val_sensor_ids,
        validation_comparisons=val_comparisons,
        validation_summary=val_summary,
        validation_independence=val_assessment,
        midspan_comparison=midspan_comp,
        midspan_is_independent=True,
        midspan_note=MIDSPAN_INDEPENDENT_NOTE,
        leakage_check=leakage,
        solver_method=SOLVER_METHOD,
        model_parameters=parameters,
        calibration_parameters_used=[p.name for p in parameters if p.selected_using_measurements],
        validation_data_used_during_calibration=False,
        limitations=LIMITATIONS,
        scientific_explanation=INSUFFICIENT_DATA_EXPLANATION,
    )
