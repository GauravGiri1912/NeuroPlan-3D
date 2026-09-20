"""
NeuroPlan-3D — Engineering analysis API (Priorities 1-12).

Exposes the hardening-pass capabilities: load cases and self-weight,
diagnostics, buckling screening, sensitivity, IS 800 screening,
connection screening, design-space exploration, what-if, and the
compiled engineering report.

Every endpoint runs the real production solver. None returns a cached,
scaled or estimated number.
"""
from __future__ import annotations

from dataclasses import asdict

import numpy as np
from enum import Enum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.analysis.buckling import screen_structure as buckling_screen
from ..core.analysis.explorer import (
    explore_design_space, run_what_if, WhatIfParameter,
)
from ..core.analysis.report import build_report, report_to_dict
from ..core.analysis.sensitivity import run_sensitivity, SensitivityParameter
from ..core.codes.connections import (
    screen_connections, BoltedConnection, WeldedConnection,
)
from ..core.codes.is800_2007 import screen_structure as is800_screen
from ..core.fea.load_cases import DEFAULT_COMBINATION, LIVE_ONLY_COMBINATION
from ..core.fea.solver import solve, FEASolverError
from ..core.fea.thermal import ThermalLoadCase, SupportSettlement
from ..core.fea.nonlinear import solve_nonlinear, build_nonlinear_inputs
from ..core.fea.assembly import build_load_vector
from ..core.fea.dynamics import (
    solve_modal, response_spectrum_analysis, SeismicZone, SoilType,
)
from ..core.fea.springs import ElasticSupport
from ..core.codes.fatigue import (
    FatigueDetailCategory, screen_fatigue, stress_range_from_results,
)
from ..core.codes.fire import screen_fire
from ..core.experiments.engine import run_experiment
from ..core.experiments.models import Perturbation, PerturbationType, case_structural_status
from ..core.experiments.autopsy import diagnose
from ..core.experiments.robustness import run_load_robustness_sweep, DEFAULT_LOAD_SCALES
from ..core.generator.topology import generate_structure
from ..models.structure import EngineeringSpec, StructureType, MATERIAL_LIBRARY
from .schemas import SpecRequest as SpecSchema

router = APIRouter(prefix="/api/engineering", tags=["engineering"])


def _to_jsonable(value):
    """Dataclasses, enums and nested containers -> JSON-safe structures."""
    if isinstance(value, Enum):
        return value.value
    # NumPy scalars (np.bool_, np.int64, np.float64) reach here from the
    # solver and are not JSON-serialisable. .item() converts to the
    # equivalent Python scalar without changing the value.
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, np.ndarray):
        return [_to_jsonable(v) for v in value.tolist()]
    if hasattr(value, "__dataclass_fields__"):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, float):
        # JSON has no inf/nan; report them as strings rather than crashing
        # or silently substituting a number that isn't the result.
        if value != value:
            return "NaN"
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
    return value


def _spec_from(payload: SpecSchema | None) -> EngineeringSpec:
    if payload is None:
        return EngineeringSpec()
    spec = EngineeringSpec()
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field_name == "structure_type":
            spec.structure_type = StructureType(value)
        elif hasattr(spec, field_name):
            setattr(spec, field_name, value)
    return spec


def _model_meta(spec: EngineeringSpec, structure, spec_provided: bool) -> dict:
    """
    Identifies which structure an analysis actually ran on. Every engineering
    endpoint below attaches this to its response so the caller can verify
    (rather than assume) that the analysis used the model it intended to.

    `spec_provided` is False exactly when the request omitted `spec`, in
    which case `_spec_from(None)` silently substituted the backend's
    bare-default EngineeringSpec() — the caller must be able to tell this
    apart from a genuine current-model request, so it is reported rather
    than hidden.
    """
    return {
        "structure_type": spec.structure_type.value,
        "is_spatial": spec.structure_type.is_spatial,
        "node_count": len(structure.nodes),
        "member_count": len(structure.members),
        "spec_provided": spec_provided,
    }


class BoltedConnectionRequest(BaseModel):
    """Mirrors server.core.codes.connections.BoltedConnection — the user
    declaring a real connection at one member end, never inferred."""
    member_id: int
    bolt_diameter_mm: int
    bolt_grade: str
    bolt_count: int = Field(gt=0)
    shear_planes_threaded: int = 1
    shear_planes_shank: int = 0
    ply_thickness_mm: float = 8.0
    end_distance_mm: float = 35.0
    pitch_mm: float = 50.0
    plate_fu_pa: float = 410e6


class WeldedConnectionRequest(BaseModel):
    """Mirrors server.core.codes.connections.WeldedConnection."""
    member_id: int
    weld_size_mm: float = Field(gt=0.0)
    weld_length_mm: float = Field(gt=0.0)
    shop_weld: bool = True
    parent_fu_pa: float = 410e6


class AnalysisRequest(BaseModel):
    spec: SpecSchema | None = None
    include_self_weight: bool = True
    temperature_change_k: float = 0.0
    run_sensitivity: bool = False
    sensitivity_perturbation: float = Field(default=0.10, gt=0.0, lt=1.0)
    bolted_connections: list[BoltedConnectionRequest] = []
    welded_connections: list[WeldedConnectionRequest] = []


def _run(request: AnalysisRequest):
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)
    combination = DEFAULT_COMBINATION if request.include_self_weight else LIVE_ONLY_COMBINATION
    thermal = (ThermalLoadCase(delta_t=request.temperature_change_k)
               if request.temperature_change_k else None)
    results = solve(structure, spec, combination=combination, thermal=thermal)
    return spec, structure, results


@router.post("/analyse")
async def analyse(request: AnalysisRequest):
    """Full analysis with load cases, diagnostics, buckling and code checks."""
    try:
        spec, structure, results = _run(request)
    except (FEASolverError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    buckling = buckling_screen(structure, results.member_results)
    code = is800_screen(structure, results.member_results)
    try:
        connections = screen_connections(
            results.member_results,
            bolted=[BoltedConnection(**c.model_dump()) for c in request.bolted_connections],
            welded=[WeldedConnection(**c.model_dump()) for c in request.welded_connections],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "model": _model_meta(spec, structure, request.spec is not None),
        "load_summary": _to_jsonable(results.load_summary),
        "stability": _to_jsonable(results.stability),
        "buckling": _to_jsonable(buckling),
        "code_checks": _to_jsonable(code),
        "connections": _to_jsonable(connections),
        "max_stress_mpa": _to_jsonable(
            max((abs(m.stress) for m in results.member_results), default=0.0) / 1e6),
        "max_displacement_mm": _to_jsonable(results.diagnosis.max_displacement_mm),
        "total_weight_kg": _to_jsonable(results.total_weight_kg),
        "equilibrium_passed": _to_jsonable(results.equilibrium.passed),
    }


@router.post("/sensitivity")
async def sensitivity(request: AnalysisRequest):
    try:
        spec = _spec_from(request.spec)
        structure = generate_structure(spec)
        report = run_sensitivity(
            structure, spec,
            perturbation=request.sensitivity_perturbation,
            combination=DEFAULT_COMBINATION if request.include_self_weight
            else LIVE_ONLY_COMBINATION,
        )
    except (FEASolverError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    payload = _to_jsonable(report)
    payload["model"] = _model_meta(spec, structure, request.spec is not None)
    return payload


class ExploreRequest(BaseModel):
    spec: SpecSchema | None = None
    structure_types: list[str] | None = None
    panel_counts: list[int] | None = None
    heights: list[float] | None = None
    section_keys: list[str] | None = None


@router.post("/explore")
async def explore(request: ExploreRequest):
    spec = _spec_from(request.spec)
    try:
        types = ([StructureType(t) for t in request.structure_types]
                 if request.structure_types else None)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    table = explore_design_space(
        spec, structure_types=types, panel_counts=request.panel_counts,
        heights=request.heights, section_keys=request.section_keys,
    )
    return _to_jsonable(table)


class WhatIfRequest(BaseModel):
    spec: SpecSchema | None = None
    changes: dict[str, str]


@router.post("/what-if")
async def what_if(request: WhatIfRequest):
    spec = _spec_from(request.spec)
    try:
        changes = {WhatIfParameter(k): v for k, v in request.changes.items()}
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"{e}. Valid parameters: {[p.value for p in WhatIfParameter]}",
        )
    try:
        result = run_what_if(spec, changes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _to_jsonable(result)


@router.post("/report")
async def engineering_report(request: AnalysisRequest):
    """The compiled engineering analysis report (Priority 12)."""
    try:
        spec, structure, results = _run(request)
    except (FEASolverError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    sensitivity_report = None
    if request.run_sensitivity:
        sensitivity_report = run_sensitivity(
            structure, spec, perturbation=request.sensitivity_perturbation)

    report = build_report(
        structure, spec, results,
        buckling=buckling_screen(structure, results.member_results),
        sensitivity=sensitivity_report,
        code_report=is800_screen(structure, results.member_results),
    )
    payload = _to_jsonable(report_to_dict(report))
    payload["classification_counts"] = report.classification_counts()
    return payload


@router.get("/capabilities")
async def capabilities():
    """
    What this solver can and cannot do — served from the same constants
    the analyses use, so it cannot drift out of date relative to them.
    """
    from ..core.codes.is800_2007 import IMPLEMENTED_CLAUSES, UNSUPPORTED_CLAUSES
    from ..core.codes.connections import UNSUPPORTED_CONNECTION_CHECKS
    from ..core.fea.load_cases import build_load_cases

    spec = EngineeringSpec()
    cases, _ = build_load_cases(generate_structure(spec))

    return {
        "solver": {
            "method": "Direct Stiffness Method, linear elastic",
            "element": "3D pin-jointed bar, 3 translational DOF per node",
            "dof_per_node": 3,
            "supports_bending": False,
            "supports_geometric_nonlinearity": False,
            "supports_material_nonlinearity": False,
            "supports_dynamics": False,
        },
        "load_cases": [
            {
                "case": c.case_type.value,
                "supported": c.supported,
                "formulation": c.formulation,
                "limitations": c.limitations,
            }
            for c in cases
        ],
        "design_code": {
            "code": "IS 800:2007",
            "scope": "SCREENING SUBSET — not a compliance check",
            "implemented": IMPLEMENTED_CLAUSES,
            "not_implemented": UNSUPPORTED_CLAUSES,
        },
        "connections": {
            "scope": "SCREENING — closed-form capacity only",
            "not_implemented": UNSUPPORTED_CONNECTION_CHECKS,
        },
        "sensitivity_parameters": [p.value for p in SensitivityParameter],
        "what_if_parameters": [p.value for p in WhatIfParameter],
    }


class NonlinearRequest(BaseModel):
    spec: SpecSchema | None = None
    geometric: bool = True
    material: bool = False
    n_steps: int = Field(default=10, ge=1, le=500)
    max_iterations: int = Field(default=30, ge=1, le=200)


@router.post("/nonlinear")
async def nonlinear_analysis(request: NonlinearRequest):
    """Geometric (P-Delta) and/or material (elastic-perfectly-plastic) nonlinear analysis."""
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)
    dof_map, constrained = build_nonlinear_inputs(structure)
    target_load = build_load_vector(structure, dof_map)

    try:
        result = solve_nonlinear(
            structure, target_load, dof_map, constrained,
            geometric=request.geometric, material=request.material,
            n_steps=request.n_steps, max_iterations=request.max_iterations,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    payload = _to_jsonable(result)
    payload["model"] = _model_meta(spec, structure, request.spec is not None)
    return payload


class ModalRequest(BaseModel):
    spec: SpecSchema | None = None
    n_modes: int = Field(default=6, ge=1, le=30)
    live_load_mass_fraction: float = Field(default=0.0, ge=0.0, le=1.0)


@router.post("/modal")
async def modal_analysis(request: ModalRequest):
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)
    try:
        result = solve_modal(structure, n_modes=request.n_modes,
                             live_load_mass_fraction=request.live_load_mass_fraction)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    payload = _to_jsonable(result)
    payload["model"] = _model_meta(spec, structure, request.spec is not None)
    return payload


class SeismicRequest(BaseModel):
    spec: SpecSchema | None = None
    zone: str
    soil: str
    importance_factor: float = Field(default=1.0, gt=0.0)
    response_reduction_factor: float = Field(default=3.0, gt=0.0)
    direction: str = "x"
    n_modes: int = Field(default=6, ge=1, le=30)


@router.post("/seismic")
async def seismic_response_spectrum(request: SeismicRequest):
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)
    try:
        zone = SeismicZone(request.zone)
        soil = SoilType(request.soil)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"{e}. Valid zones: {[z.value for z in SeismicZone]}, "
                   f"valid soils: {[s.value for s in SoilType]}",
        )
    try:
        result = response_spectrum_analysis(
            structure, zone, soil, request.importance_factor,
            request.response_reduction_factor, request.direction, request.n_modes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    payload = _to_jsonable(result)
    payload["model"] = _model_meta(spec, structure, request.spec is not None)
    return payload


class FatigueRequest(BaseModel):
    spec: SpecSchema | None = None
    detail_category_name: str = "User-supplied"
    sigma_c_mpa: float = Field(gt=0.0)
    m: float = Field(default=3.0, gt=0.0)
    n_ref: int = Field(default=2_000_000, gt=0)
    design_cycles: float = Field(gt=0.0)


@router.post("/fatigue")
async def fatigue_screening(request: FatigueRequest):
    """
    Stress range is taken between the FULLY LOADED case and an unloaded
    case of the same structure — both real solver runs.
    """
    spec = _spec_from(request.spec)
    loaded_structure = generate_structure(spec)
    unloaded_spec = _spec_from(request.spec)
    unloaded_spec.primary_load = 0.0
    unloaded_structure = generate_structure(unloaded_spec)

    try:
        loaded_results = solve(loaded_structure, spec)
        unloaded_results = solve(unloaded_structure, unloaded_spec)
    except FEASolverError as e:
        raise HTTPException(status_code=422, detail=str(e))

    ranges = stress_range_from_results(loaded_results.member_results, unloaded_results.member_results)
    category = FatigueDetailCategory(
        name=request.detail_category_name, sigma_c_mpa=request.sigma_c_mpa,
        m=request.m, n_ref=request.n_ref,
    )
    report = screen_fatigue(ranges, request.design_cycles, category)
    payload = _to_jsonable(report)
    payload["model"] = _model_meta(spec, loaded_structure, request.spec is not None)
    return payload


class FireRequest(BaseModel):
    spec: SpecSchema | None = None
    temperature_c: float = Field(ge=20.0, le=1200.0)


@router.post("/fire")
async def fire_screening(request: FireRequest):
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)
    try:
        results = solve(structure, spec)
    except FEASolverError as e:
        raise HTTPException(status_code=422, detail=str(e))

    material_key_by_member = {m.id: m.material_key for m in structure.members}
    fy_by_material = {k: m.yield_stress for k, m in MATERIAL_LIBRARY.items()}
    e_by_material = {k: m.E for k, m in MATERIAL_LIBRARY.items()}

    report = screen_fire(
        results.member_results, temperature_c=request.temperature_c,
        fy_by_member={}, material_key_by_member=material_key_by_member,
        original_e_by_material=e_by_material, original_fy_by_material=fy_by_material,
    )
    payload = _to_jsonable(report)
    payload["model"] = _model_meta(spec, structure, request.spec is not None)
    return payload


class SpringInput(BaseModel):
    node_id: int
    kx: float = 0.0
    ky: float = 0.0
    kz: float = 0.0


class SpringRequest(BaseModel):
    spec: SpecSchema | None = None
    springs: list[SpringInput] = Field(min_length=1)
    include_self_weight: bool = True


@router.post("/springs")
async def spring_support_analysis(request: SpringRequest):
    """
    Elastic spring supports (Priority: foundation flexibility, NOT soil
    mechanics — see fea/springs.py). Runs baseline (rigid supports only)
    and with-springs cases through the real solver and reports both, so
    the effect of the supplied stiffness is visible rather than assumed.
    """
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)
    combination = DEFAULT_COMBINATION if request.include_self_weight else LIVE_ONLY_COMBINATION
    springs = [ElasticSupport(node_id=s.node_id, kx=s.kx, ky=s.ky, kz=s.kz)
              for s in request.springs]

    try:
        baseline = solve(structure, spec, combination=combination)
        with_springs = solve(structure, spec, combination=combination, springs=springs)
    except (FEASolverError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "model": _model_meta(spec, structure, request.spec is not None),
        "baseline": {
            "max_displacement_mm": _to_jsonable(baseline.diagnosis.max_displacement_mm),
            "max_stress_mpa": _to_jsonable(
                max((abs(m.stress) for m in baseline.member_results), default=0.0) / 1e6),
            "equilibrium_passed": _to_jsonable(baseline.equilibrium.passed),
        },
        "with_springs": {
            "max_displacement_mm": _to_jsonable(with_springs.diagnosis.max_displacement_mm),
            "max_stress_mpa": _to_jsonable(
                max((abs(m.stress) for m in with_springs.member_results), default=0.0) / 1e6),
            "equilibrium_passed": _to_jsonable(with_springs.equilibrium.passed),
        },
        "springs_applied": [s.model_dump() for s in request.springs],
        "source_note": ElasticSupport(node_id=0).source_note(),
    }


class MemberRemovalRequest(BaseModel):
    spec: SpecSchema | None = None
    member_id: int


@router.post("/experiments/member-removal")
async def member_removal_experiment(request: MemberRemovalRequest):
    """
    Remove one member from a copy of the structure and re-solve via the
    real production solver (server.core.experiments.engine.run_experiment).
    Curated summary response — see ExperimentResult for the full object.
    """
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)

    try:
        result = run_experiment(
            structure, spec,
            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=request.member_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    perturbed = None
    if result.perturbed_results is not None:
        perturbed = {
            "max_displacement_mm": result.perturbed_max_displacement_mm,
            "max_stress_mpa": result.perturbed_max_stress_mpa,
            "critical_member": result.critical_member_after,
            "verified": result.perturbed_verified,
        }

    return _to_jsonable({
        "removed_member_id": result.removed_member_id,
        "baseline_status": case_structural_status(result.baseline_results),
        "structural_status": result.structural_status,
        "baseline": {
            "max_displacement_mm": result.baseline_max_displacement_mm,
            "max_stress_mpa": result.baseline_max_stress_mpa,
            "critical_member": result.critical_member_before,
            "verified": result.baseline_verified,
        },
        "perturbed": perturbed,
        "displacement_change_mm": result.displacement_change_mm,
        "displacement_percent_change": result.displacement_percent_change,
        "stress_change_mpa": result.stress_change_mpa,
        "stress_percent_change": result.stress_percent_change,
        "critical_member_changed": result.critical_member_changed,
        "error": result.perturbed_error,
    })


@router.post("/experiments/member-removal/autopsy")
async def member_removal_autopsy(request: MemberRemovalRequest):
    """
    Structural Autopsy for a member-removal experiment. Re-runs the same
    deterministic experiment (server.core.experiments.engine.run_experiment)
    and serializes diagnose()'s own result — no diagnosis logic here.
    """
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)

    try:
        result = run_experiment(
            structure, spec,
            Perturbation(type=PerturbationType.MEMBER_REMOVE, member_id=request.member_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    autopsy = diagnose(result)
    return _to_jsonable(autopsy)


class RobustnessSweepRequest(BaseModel):
    spec: SpecSchema | None = None
    load_index: int = 0
    scales: list[float] | None = None


@router.post("/experiments/load-robustness")
async def load_robustness_sweep(request: RobustnessSweepRequest):
    """
    Deterministic load robustness sweep — calls the existing
    server.core.experiments.robustness.run_load_robustness_sweep()
    directly and serializes its result. No sweep logic here.
    """
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)

    try:
        sweep = run_load_robustness_sweep(
            structure, spec, load_index=request.load_index,
            scales=request.scales or list(DEFAULT_LOAD_SCALES),
        )
    except (FEASolverError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    payload = _to_jsonable(sweep)
    payload["model"] = _model_meta(spec, structure, request.spec is not None)
    return payload


class MemberAreaScaleRequest(BaseModel):
    spec: SpecSchema | None = None
    member_id: int
    scale_factor: float = Field(gt=0.0)


@router.post("/experiments/member-area-scale")
async def member_area_scale_experiment(request: MemberAreaScaleRequest):
    """
    Manual, controlled re-analysis: scale ONE member's cross-sectional
    area and re-solve. Reuses the existing MEMBER_AREA_SCALE perturbation
    and run_experiment() directly — no new repair logic, no automatic
    selection. Response shape mirrors /experiments/member-removal.
    """
    spec = _spec_from(request.spec)
    structure = generate_structure(spec)

    try:
        result = run_experiment(
            structure, spec,
            Perturbation(type=PerturbationType.MEMBER_AREA_SCALE,
                        member_id=request.member_id, scale_factor=request.scale_factor),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    perturbed = None
    if result.perturbed_results is not None:
        perturbed = {
            "max_displacement_mm": result.perturbed_max_displacement_mm,
            "max_stress_mpa": result.perturbed_max_stress_mpa,
            "critical_member": result.critical_member_after,
            "verified": result.perturbed_verified,
        }

    return _to_jsonable({
        "member_id": request.member_id,
        "scale_factor": request.scale_factor,
        "baseline_status": case_structural_status(result.baseline_results),
        "structural_status": result.structural_status,
        "baseline": {
            "max_displacement_mm": result.baseline_max_displacement_mm,
            "max_stress_mpa": result.baseline_max_stress_mpa,
            "critical_member": result.critical_member_before,
            "verified": result.baseline_verified,
        },
        "perturbed": perturbed,
        "displacement_change_mm": result.displacement_change_mm,
        "displacement_percent_change": result.displacement_percent_change,
        "stress_change_mpa": result.stress_change_mpa,
        "stress_percent_change": result.stress_percent_change,
        "critical_member_changed": result.critical_member_changed,
        "error": result.perturbed_error,
    })
