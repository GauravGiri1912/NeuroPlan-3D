"""
NeuroPlan-3D — Constraint Validator

Checks analysis results against engineering constraints:
- Stress limits (yield stress / safety factor)
- Displacement limits (span / ratio)
- Simplified Euler buckling for compression members

Returns a ranked FailureDiagnosis used by the repair engine.
"""
import math
from ...models.structure import (
    Structure, MemberResult, NodeResult,
    FailureDiagnosis, FailureInfo, FailureType,
    MemberStatus, NodeStatus,
    MATERIAL_LIBRARY, EngineeringSpec,
)


def validate_constraints(
    structure: Structure,
    member_results: list[MemberResult],
    node_results: list[NodeResult],
    spec: EngineeringSpec,
) -> FailureDiagnosis:
    """
    Check all structural constraints and produce a failure diagnosis.

    Constraints checked:
    1. Member stress ≤ yield_stress / safety_factor
    2. Nodal displacement ≤ span / max_displacement_ratio
    3. Compression member force < Euler buckling load (simplified)

    Parameters:
        structure: The structural model
        member_results: FEA member force/stress results
        node_results: FEA nodal displacement results
        spec: Engineering specification with constraint values

    Returns:
        FailureDiagnosis with ranked failures
    """
    failures: list[FailureInfo] = []
    max_stress_ratio = 0.0
    max_displacement = 0.0
    failed_members = 0
    failed_nodes = 0

    # --- Stress check ---
    for mr in member_results:
        mat = MATERIAL_LIBRARY.get(spec.material_key)
        if not mat:
            continue

        allowable_stress = mat.yield_stress / spec.safety_factor
        stress_ratio = abs(mr.stress) / allowable_stress if allowable_stress > 0 else 0.0

        # Update the result object
        mr.stress_ratio = stress_ratio
        mr.allowable_stress = allowable_stress
        max_stress_ratio = max(max_stress_ratio, stress_ratio)

        if stress_ratio > 1.0:
            mr.status = MemberStatus.OVERSTRESSED
            failed_members += 1
            failures.append(FailureInfo(
                failure_type=FailureType.STRESS_EXCEEDED,
                member_id=mr.member_id,
                actual_value=abs(mr.stress),
                limit_value=allowable_stress,
                ratio=stress_ratio,
                description=(
                    f"Member {mr.member_id}: |σ| = {abs(mr.stress)/1e6:.1f} MPa "
                    f"> {allowable_stress/1e6:.1f} MPa (ratio: {stress_ratio:.2f})"
                ),
            ))
        else:
            mr.status = MemberStatus.OK

        # --- Buckling check (compression members only) ---
        if mr.axial_force < 0:  # compression
            if abs(mr.axial_force) > mr.euler_buckling_load and mr.euler_buckling_load > 0:
                mr.status = MemberStatus.BUCKLING_RISK
                failures.append(FailureInfo(
                    failure_type=FailureType.BUCKLING_RISK,
                    member_id=mr.member_id,
                    actual_value=abs(mr.axial_force),
                    limit_value=mr.euler_buckling_load,
                    ratio=abs(mr.axial_force) / mr.euler_buckling_load,
                    description=(
                        f"Member {mr.member_id}: Buckling risk — "
                        f"|P| = {abs(mr.axial_force)/1e3:.1f} kN "
                        f"> P_cr = {mr.euler_buckling_load/1e3:.1f} kN"
                    ),
                ))

    # --- Displacement check ---
    max_allowable_disp = spec.span / spec.max_displacement_ratio

    for nr in node_results:
        disp = nr.total_displacement
        max_displacement = max(max_displacement, disp)

        if disp > max_allowable_disp:
            failed_nodes += 1
            failures.append(FailureInfo(
                failure_type=FailureType.DISPLACEMENT_EXCEEDED,
                node_id=nr.node_id,
                actual_value=disp,
                limit_value=max_allowable_disp,
                ratio=disp / max_allowable_disp if max_allowable_disp > 0 else 0,
                description=(
                    f"Node {nr.node_id}: δ = {disp*1000:.2f} mm "
                    f"> {max_allowable_disp*1000:.2f} mm (L/{spec.max_displacement_ratio:.0f})"
                ),
            ))

    # Sort failures by ratio (severity) descending
    failures.sort(key=lambda f: f.ratio, reverse=True)

    passed = len(failures) == 0

    return FailureDiagnosis(
        passed=passed,
        failures=failures,
        max_stress_ratio=max_stress_ratio,
        max_displacement_mm=max_displacement * 1000,
        failed_member_count=failed_members,
        failed_node_count=failed_nodes,
    )
