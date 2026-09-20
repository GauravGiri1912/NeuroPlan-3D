"""
NeuroPlan-3D — Serialization Helpers

Convert internal dataclass models to Pydantic response models.
"""
from ..models.structure import (
    Structure, EngineeringSpec, AnalysisResults, IterationResult,
    MATERIAL_LIBRARY,
)
from .schemas import (
    NodeResponse, MemberResponse, SectionResponse,
    SupportResponse, LoadResponse, StructureResponse,
    MemberResultResponse, NodeResultResponse, ReactionResponse,
    FailureInfoResponse, DiagnosisResponse, RepairActionResponse,
    AnalysisResultsResponse, IterationResponse, SpecResponse,
    MaterialResponse, EquilibriumResponse, VerificationChecksResponse,
    EvidenceResponse, ProvenanceResponse, ProvenanceInputResponse,
    VerificationItemResponse, BenchmarkResponse, AssumptionResponse,
    SimulationRecordResponse, LoadPathResponse, LoadPathMemberResponse,
)


def serialize_structure(s: Structure) -> StructureResponse:
    return StructureResponse(
        nodes=[NodeResponse(id=n.id, x=n.x, y=n.y, z=n.z) for n in s.nodes],
        members=[
            MemberResponse(
                id=m.id,
                node_i=m.node_i,
                node_j=m.node_j,
                material_key=m.material_key,
                section=SectionResponse(
                    outer_diameter=m.section.outer_diameter,
                    wall_thickness=m.section.wall_thickness,
                    area=m.section.area,
                    moment_of_inertia=m.section.moment_of_inertia,
                ),
            )
            for m in s.members
        ],
        supports=[
            SupportResponse(
                node_id=sup.node_id,
                support_type=sup.support_type.value,
                dx=sup.dx, dy=sup.dy, dz=sup.dz,
            )
            for sup in s.supports
        ],
        loads=[
            LoadResponse(node_id=l.node_id, fx=l.fx, fy=l.fy, fz=l.fz)
            for l in s.loads
        ],
    )


def serialize_results(r: AnalysisResults) -> AnalysisResultsResponse:
    return AnalysisResultsResponse(
        member_results=[
            MemberResultResponse(
                member_id=mr.member_id,
                axial_force=round(mr.axial_force, 2),
                axial_force_kn=round(mr.axial_force_kn, 2),
                stress=round(mr.stress, 2),
                stress_mpa=round(mr.stress_mpa, 2),
                stress_ratio=round(mr.stress_ratio, 4),
                allowable_stress_mpa=round(mr.allowable_stress / 1e6, 2),
                status=mr.status.value,
                euler_buckling_load=round(mr.euler_buckling_load, 2),
            )
            for mr in r.member_results
        ],
        node_results=[
            NodeResultResponse(
                node_id=nr.node_id,
                dx=round(nr.dx, 8),
                dy=round(nr.dy, 8),
                dz=round(nr.dz, 8),
                total_displacement_mm=round(nr.total_displacement_mm, 4),
            )
            for nr in r.node_results
        ],
        reactions=[
            ReactionResponse(
                node_id=rx.node_id,
                rx=round(rx.rx, 2),
                ry=round(rx.ry, 2),
                rz=round(rx.rz, 2),
            )
            for rx in r.reactions
        ],
        diagnosis=DiagnosisResponse(
            passed=r.diagnosis.passed,
            failures=[
                FailureInfoResponse(
                    failure_type=f.failure_type.value,
                    member_id=f.member_id,
                    node_id=f.node_id,
                    actual_value=round(f.actual_value, 4),
                    limit_value=round(f.limit_value, 4),
                    ratio=round(f.ratio, 4),
                    description=f.description,
                )
                for f in r.diagnosis.failures
            ],
            max_stress_ratio=round(r.diagnosis.max_stress_ratio, 4),
            max_displacement_mm=round(r.diagnosis.max_displacement_mm, 4),
            failed_member_count=r.diagnosis.failed_member_count,
            failed_node_count=r.diagnosis.failed_node_count,
        ),
        solve_time_ms=r.solve_time_ms,
        total_weight_kg=r.total_weight_kg,
        equilibrium=EquilibriumResponse(
            residual_fx=r.equilibrium.residual_fx,
            residual_fy=r.equilibrium.residual_fy,
            residual_fz=r.equilibrium.residual_fz,
            residual_mx=r.equilibrium.residual_mx,
            residual_my=r.equilibrium.residual_my,
            residual_mz=r.equilibrium.residual_mz,
            max_residual=r.equilibrium.max_residual,
            max_moment_residual=r.equilibrium.max_moment_residual,
            load_magnitude=round(r.equilibrium.load_magnitude, 4),
            moment_magnitude=round(r.equilibrium.moment_magnitude, 4),
            relative_residual=r.equilibrium.relative_residual,
            relative_moment_residual=r.equilibrium.relative_moment_residual,
            tolerance=r.equilibrium.tolerance,
            passed=r.equilibrium.passed,
        ),
        checks=VerificationChecksResponse(
            solver=r.checks.solver,
            geometry=r.checks.geometry,
            boundary_conditions=r.checks.boundary_conditions,
            equilibrium=r.checks.equilibrium,
            stress=r.checks.stress,
            displacement=r.checks.displacement,
            all_passed=r.checks.all_passed,
        ),
        dof_count=r.dof_count,
        is_spatial=r.is_spatial,
    )


def serialize_iteration(it: IterationResult) -> IterationResponse:
    repair = None
    if it.repair_action:
        ra = it.repair_action
        repair = RepairActionResponse(
            iteration=ra.iteration,
            strategy=ra.strategy.value,
            target_description=ra.target_description,
            parameter_changed=ra.parameter_changed,
            old_value=round(ra.old_value, 6),
            new_value=round(ra.new_value, 6),
            rationale=ra.rationale,
        )
    return IterationResponse(
        iteration_number=it.iteration_number,
        structure=serialize_structure(it.structure),
        results=serialize_results(it.results),
        repair_action=repair,
    )


def serialize_spec(spec: EngineeringSpec) -> SpecResponse:
    return SpecResponse(
        structure_type=spec.structure_type.value,
        is_spatial=spec.structure_type.is_spatial,
        span=spec.span,
        height=spec.height,
        width=spec.width,
        num_panels=spec.num_panels,
        primary_load=spec.primary_load,
        lateral_load_x=spec.lateral_load_x,
        lateral_load_z=spec.lateral_load_z,
        load_description=spec.load_description,
        material_key=spec.material_key,
        section_key=spec.section_key,
        safety_factor=spec.safety_factor,
        max_displacement_ratio=spec.max_displacement_ratio,
        description=spec.description,
        raw_input=spec.raw_input,
        defaults_applied=list(spec.defaults_applied),
        dimensionality_intent=spec.dimensionality_intent.value,
    )


def serialize_evidence(
    structure, results, spec, iteration_count: int
) -> "EvidenceResponse":
    """
    Build the full traceability package. Every field here is read from
    solver state via server.core.evidence — nothing is recomputed for
    display, and nothing is hard-coded.
    """
    from ..core.evidence import (
        build_provenance, build_verification_items, run_benchmarks,
        get_assumptions, build_simulation_record, build_load_paths,
    )
    from ..models.evidence import CheckStatus

    provenance = build_provenance(structure, results, spec)
    verification = build_verification_items(structure, results, spec)
    benchmarks = run_benchmarks()
    assumptions = get_assumptions()
    load_paths = build_load_paths(structure, results)
    record = build_simulation_record(structure, results, spec, iteration_count)

    # "Computation verified" means every gating check passed. INFO and
    # NOT_AVAILABLE items are explicitly not treated as passes.
    gating = [v for v in verification if v.status in (CheckStatus.PASS, CheckStatus.FAIL)]
    computation_verified = all(v.status is CheckStatus.PASS for v in gating)

    return EvidenceResponse(
        provenance=[
            ProvenanceResponse(
                metric=p.metric, label=p.label, value=p.value, units=p.units,
                source_type=p.source_type, source_id=p.source_id,
                source_detail=p.source_detail, equation=p.equation,
                inputs=[
                    ProvenanceInputResponse(label=i.label, value=i.value, units=i.units)
                    for i in p.inputs
                ],
                note=p.note,
            )
            for p in provenance
        ],
        verification=[
            VerificationItemResponse(
                key=v.key, category=v.category.value, label=v.label,
                status=v.status.value, actual_display=v.actual_display,
                limit_display=v.limit_display, units=v.units,
                source=v.source, detail=v.detail,
                actual_value=v.actual_value, limit_value=v.limit_value,
            )
            for v in verification
        ],
        benchmarks=[
            BenchmarkResponse(
                case=b.case, quantity=b.quantity,
                neuroplan_value=b.neuroplan_value, reference_value=b.reference_value,
                units=b.units, absolute_difference=b.absolute_difference,
                relative_difference=b.relative_difference,
                tolerance_relative=b.tolerance_relative,
                reference_source=b.reference_source, derivation=b.derivation,
                status=b.status.value,
            )
            for b in benchmarks
        ],
        assumptions=[
            AssumptionResponse(
                topic=a.topic, modeled=a.modeled,
                description=a.description, implication=a.implication,
            )
            for a in assumptions
        ],
        load_paths=[
            LoadPathResponse(
                node_id=lp.node_id,
                node_x=lp.node_x, node_y=lp.node_y, node_z=lp.node_z,
                applied_fx=lp.applied_fx, applied_fy=lp.applied_fy, applied_fz=lp.applied_fz,
                members=[
                    LoadPathMemberResponse(
                        member_id=m.member_id, other_node_id=m.other_node_id,
                        axial_force=m.axial_force, stress=m.stress,
                        lx=m.direction_cosines[0], ly=m.direction_cosines[1],
                        lz=m.direction_cosines[2],
                        fx_on_joint=m.fx_on_joint, fy_on_joint=m.fy_on_joint,
                        fz_on_joint=m.fz_on_joint,
                    )
                    for m in lp.members
                ],
                joint_residual_fx=lp.joint_residual_fx,
                joint_residual_fy=lp.joint_residual_fy,
                joint_residual_fz=lp.joint_residual_fz,
                joint_relative_residual=lp.joint_relative_residual,
                joint_equilibrium_passed=lp.joint_equilibrium_passed,
            )
            for lp in load_paths
        ],
        record=SimulationRecordResponse(
            simulation_id=record.simulation_id,
            timestamp_utc=record.timestamp_utc,
            software_version=record.software_version,
            solver_method=record.solver_method,
            solver_backend=record.solver_backend,
            node_count=record.node_count,
            member_count=record.member_count,
            dof_per_node=record.dof_per_node,
            total_dof=record.total_dof,
            support_count=record.support_count,
            load_count=record.load_count,
            material_keys=record.material_keys,
            section_keys=record.section_keys,
            iteration_count=record.iteration_count,
            warnings=record.warnings,
        ),
        computation_verified=computation_verified,
        # Honest by construction: no experimental validation exists, so this
        # is False until real reference/experimental data is actually added.
        real_world_validated=False,
    )


def serialize_materials() -> list[MaterialResponse]:
    return [
        MaterialResponse(
            key=m.key,
            name=m.name,
            E_gpa=m.E_gpa,
            yield_stress_mpa=m.yield_stress_mpa,
            density=m.density,
        )
        for m in MATERIAL_LIBRARY.values()
    ]
