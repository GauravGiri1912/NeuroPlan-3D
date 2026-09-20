"""
NeuroPlan-3D — Pipeline API Route

The main endpoint that runs the full analysis pipeline:
Parse → Generate → Analyze → Repair → Verify

Uses Server-Sent Events (SSE) for real-time progress streaming.
"""
import json
import asyncio
import copy
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..api.schemas import (
    PipelineRequest, SpecRequest, ParseRequest,
    PipelineResultResponse, SpecResponse, AIOpinionResponse,
)
from ..api.serializers import (
    serialize_structure, serialize_results,
    serialize_iteration, serialize_spec, serialize_materials,
    serialize_evidence,
)
from ..models.structure import (
    EngineeringSpec, StructureType, MATERIAL_LIBRARY, SECTION_CATALOG,
)
from ..core.parser.requirement_parser import parse_requirements_ai, parse_requirements_fallback
from ..core.parser.ai_opinion import get_ai_naive_opinion
from ..core.generator.topology import generate_structure
from ..core.fea.solver import solve, FEASolverError
from ..core.repair.engine import run_repair_loop


router = APIRouter(prefix="/api", tags=["pipeline"])


def _spec_from_request(req: SpecRequest) -> EngineeringSpec:
    """Convert a SpecRequest to an EngineeringSpec."""
    type_map = {
        "pratt": StructureType.PRATT,
        "warren": StructureType.WARREN,
        "howe": StructureType.HOWE,
        "space_truss": StructureType.SPACE_TRUSS,
    }
    if req.structure_type not in type_map:
        # No silent substitution — tell the caller exactly what is supported.
        raise HTTPException(
            400,
            f"Unsupported structure_type '{req.structure_type}'. "
            f"Supported: {', '.join(sorted(type_map))}.",
        )

    spec = EngineeringSpec(
        structure_type=type_map[req.structure_type],
        span=req.span,
        height=req.height,
        width=req.width,
        num_panels=req.num_panels,
        primary_load=req.primary_load,
        lateral_load_x=req.lateral_load_x,
        lateral_load_z=req.lateral_load_z,
        load_description=req.load_description,
        material_key=req.material_key,
        section_key=req.section_key,
        safety_factor=req.safety_factor,
        max_displacement_ratio=req.max_displacement_ratio,
        description=req.description,
    )

    if spec.structure_type.is_spatial and spec.width <= 0:
        spec.width = round(spec.span / 5, 3)
        spec.note_default(
            f"transverse width: {spec.width:g} m (not specified — default span/5 applied)"
        )

    return spec


@router.post("/parse")
async def parse_requirements(req: ParseRequest):
    """Parse natural language into an engineering specification."""
    spec = await parse_requirements_ai(req.raw_input)
    return serialize_spec(spec)


@router.post("/pipeline/run")
async def run_pipeline(req: PipelineRequest):
    """
    Run the complete analysis pipeline and return all results.

    Stages:
    1. Parse (if raw_input provided, else use spec)
    2. Generate structure
    3. Run FEA
    4. Repair loop (if failures detected)
    5. Return all iterations

    Returns a complete PipelineResultResponse.
    """
    # --- Stage 1: Parse or use provided spec ---
    if req.spec:
        spec = _spec_from_request(req.spec)
    elif req.raw_input:
        spec = await parse_requirements_ai(req.raw_input)
    else:
        raise HTTPException(400, "Either raw_input or spec must be provided")

    # Validate spec
    if spec.span <= 0:
        raise HTTPException(400, f"Invalid span: {spec.span}")
    if spec.primary_load <= 0:
        raise HTTPException(400, f"Invalid load: {spec.primary_load}")

    # --- Stage 2: Generate ---
    try:
        structure = generate_structure(spec)
    except ValueError as e:
        # Geometry the generator cannot legally build (e.g. a zero-width
        # space truss) is a client error, not a 500.
        raise HTTPException(400, f"Geometry generation failed: {e}")

    # --- AI "gut check" opinion (no calculation, for comparison only) ---
    # This never influences the structure, the solve, or the verdict below —
    # it exists purely to make "AI proposes, physics decides" checkable.
    ai_opinion_raw = get_ai_naive_opinion(spec)

    # --- Stage 3: Initial FEA ---
    try:
        initial_results = solve(structure, spec)
    except FEASolverError as e:
        raise HTTPException(422, f"FEA solver error: {str(e)}")

    physics_says_safe = initial_results.diagnosis.passed
    ai_says_safe = ai_opinion_raw["verdict"] == "likely_safe"
    ai_opinion = AIOpinionResponse(
        verdict=ai_opinion_raw["verdict"],
        confidence=ai_opinion_raw["confidence"],
        reasoning=ai_opinion_raw["reasoning"],
        source=ai_opinion_raw["source"],
        agrees_with_physics=(ai_says_safe == physics_says_safe),
    )

    # --- Stage 4: Repair loop ---
    iterations = run_repair_loop(structure, spec, initial_results)

    # --- Stage 5: Determine final status ---
    # Phase 19: "verified" requires EVERY computational check to pass —
    # solver, geometry, boundary conditions, equilibrium, stress and
    # displacement — not merely the stress/displacement diagnosis.
    final_iteration = iterations[-1]
    passed = final_iteration.results.checks.all_passed
    verification_status = "pass" if passed else "fail"

    # Build summary
    initial_iter = iterations[0]
    summary = {
        "total_iterations": len(iterations),
        "initial_failures": initial_iter.results.diagnosis.failed_member_count + initial_iter.results.diagnosis.failed_node_count,
        "final_failures": final_iteration.results.diagnosis.failed_member_count + final_iteration.results.diagnosis.failed_node_count,
        "initial_max_stress_ratio": round(initial_iter.results.diagnosis.max_stress_ratio, 4),
        "final_max_stress_ratio": round(final_iteration.results.diagnosis.max_stress_ratio, 4),
        "initial_weight_kg": initial_iter.results.total_weight_kg,
        "final_weight_kg": final_iteration.results.total_weight_kg,
        "initial_max_displacement_mm": round(initial_iter.results.diagnosis.max_displacement_mm, 4),
        "final_max_displacement_mm": round(final_iteration.results.diagnosis.max_displacement_mm, 4),
        "solve_time_ms": final_iteration.results.solve_time_ms,
        "dof_count": final_iteration.results.dof_count,
        "node_count": len(final_iteration.structure.nodes),
        "member_count": len(final_iteration.structure.members),
        "is_spatial": 1 if final_iteration.results.is_spatial else 0,
        "equilibrium_relative_residual": final_iteration.results.equilibrium.relative_residual,
    }

    # Evidence is built from the FINAL iteration's structure and results, so
    # provenance points at the elements actually being displayed.
    evidence = serialize_evidence(
        final_iteration.structure,
        final_iteration.results,
        spec,
        iteration_count=len(iterations),
    )

    return PipelineResultResponse(
        spec=serialize_spec(spec),
        iterations=[serialize_iteration(it) for it in iterations],
        verification_status=verification_status,
        summary=summary,
        ai_opinion=ai_opinion,
        evidence=evidence,
    )


@router.post("/pipeline/stream")
async def run_pipeline_stream(req: PipelineRequest):
    """
    Run the pipeline with SSE streaming for real-time progress.
    """
    async def event_generator():
        try:
            # --- Stage 1: Parse ---
            yield _sse_event("parsing", {"message": "Extracting engineering parameters..."})

            if req.spec:
                spec = _spec_from_request(req.spec)
            elif req.raw_input:
                spec = await parse_requirements_ai(req.raw_input)
            else:
                yield _sse_event("error", {"message": "No input provided"})
                return

            yield _sse_event("parsed", {
                "spec": serialize_spec(spec).model_dump(),
                "message": f"Specification extracted: {spec.span}m {spec.structure_type.value} truss, {spec.primary_load/1000:.0f} kN load"
            })

            await asyncio.sleep(0.1)  # Small delay for UI update

            # --- Stage 2: Generate ---
            yield _sse_event("generating", {"message": "Generating structural topology..."})
            structure = generate_structure(spec)
            yield _sse_event("generated", {
                "structure": serialize_structure(structure).model_dump(),
                "message": f"Generated {len(structure.nodes)} nodes, {len(structure.members)} members"
            })

            await asyncio.sleep(0.1)

            # --- AI "gut check" opinion (no calculation) — for comparison only ---
            ai_opinion_raw = get_ai_naive_opinion(spec)
            yield _sse_event("ai_opinion", {
                **ai_opinion_raw,
                "message": f"AI's unverified first impression: {ai_opinion_raw['verdict']} ({ai_opinion_raw['confidence']} confidence)",
            })

            # --- Stage 3: Analyze ---
            yield _sse_event("analyzing", {"message": "Running FEA solver..."})
            try:
                initial_results = solve(structure, spec)
            except FEASolverError as e:
                yield _sse_event("error", {"message": f"FEA solver error: {str(e)}"})
                return

            diag = initial_results.diagnosis
            yield _sse_event("analyzed", {
                "results": serialize_results(initial_results).model_dump(),
                "message": f"Analysis complete — {'PASS' if diag.passed else f'{diag.failed_member_count} failures detected'}"
            })

            await asyncio.sleep(0.1)

            # --- Stage 4: Repair loop ---
            if not diag.passed:
                yield _sse_event("repairing", {"message": "Starting repair iterations..."})
                iterations = run_repair_loop(structure, spec, initial_results)

                for it in iterations[1:]:  # Skip initial (already sent)
                    action_msg = ""
                    if it.repair_action:
                        action_msg = f" — {it.repair_action.strategy.value}: {it.repair_action.rationale}"
                    yield _sse_event("repair_iteration", {
                        "iteration": serialize_iteration(it).model_dump(),
                        "message": f"Iteration {it.iteration_number}{action_msg}"
                    })
                    await asyncio.sleep(0.05)
            else:
                iterations = [
                    __import__('server.models.structure', fromlist=['IterationResult']).IterationResult(
                        iteration_number=0,
                        structure=copy.deepcopy(structure),
                        results=initial_results,
                    )
                ]

            # --- Stage 5: Complete ---
            final = iterations[-1]
            passed = final.results.diagnosis.passed

            # Build full result
            initial_iter = iterations[0]
            summary = {
                "total_iterations": len(iterations),
                "initial_failures": initial_iter.results.diagnosis.failed_member_count,
                "final_failures": final.results.diagnosis.failed_member_count,
                "initial_max_stress_ratio": round(initial_iter.results.diagnosis.max_stress_ratio, 4),
                "final_max_stress_ratio": round(final.results.diagnosis.max_stress_ratio, 4),
                "initial_weight_kg": initial_iter.results.total_weight_kg,
                "final_weight_kg": final.results.total_weight_kg,
            }

            yield _sse_event("complete", {
                "verification_status": "pass" if passed else "fail",
                "summary": summary,
                "spec": serialize_spec(spec).model_dump(),
                "iterations": [serialize_iteration(it).model_dump() for it in iterations],
                "message": f"Pipeline complete — {'✓ STRUCTURE VERIFIED' if passed else '✗ BEST-EFFORT RESULT'}"
            })

        except Exception as e:
            yield _sse_event("error", {"message": f"Pipeline error: {str(e)}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/materials")
async def get_materials():
    """Return the material library."""
    return serialize_materials()


@router.get("/sections")
async def get_sections():
    """Return the section catalog."""
    return {
        key: {
            "outer_diameter": s.outer_diameter,
            "wall_thickness": s.wall_thickness,
            "area": round(s.area, 8),
            "moment_of_inertia": round(s.moment_of_inertia, 12),
        }
        for key, s in SECTION_CATALOG.items()
    }


def _sse_event(event_type: str, data: dict) -> str:
    """Format a server-sent event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
