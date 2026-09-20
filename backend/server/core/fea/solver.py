"""
NeuroPlan-3D — FEA Solver (Direct Stiffness Method)

Main solver module that orchestrates:
1. Global stiffness assembly
2. Load vector construction
3. Boundary condition application
4. Linear solve [K]{u} = {F}
5. Post-processing (forces, stresses, reactions)
6. Constraint validation

This is the DETERMINISTIC PHYSICS AUTHORITY.
No AI involvement. No approximations. No random results.
Same input → Same output. Always.
"""
import time
import numpy as np
from numpy.linalg import LinAlgError
from scipy.linalg import cho_factor, cho_solve, LinAlgError as ScipyLinAlgError

from ...models.structure import (
    Structure, EngineeringSpec, AnalysisResults,
    FailureDiagnosis, FailureInfo, FailureType, VerificationChecks,
    LoadCaseType,
)
from .assembly import assemble_global_stiffness, build_load_vector
from .load_cases import (
    LoadCombination, build_load_cases, collect_factored_loads,
    summarize_load_cases, LIVE_ONLY_COMBINATION,
)
from .diagnostics import (
    analyze_stability, check_topology, explain_solve_failure,
    format_diagnostics, Severity,
)
from .thermal import (
    ThermalLoadCase, SupportSettlement, build_thermal_load_vector,
    thermal_force_correction, build_prescribed_displacement_vector,
)
from .springs import ElasticSupport, apply_spring_stiffness, spring_reaction_forces
from .boundary import get_constrained_dofs
from .postprocess import (
    compute_member_forces,
    compute_node_displacements,
    compute_reactions,
    compute_equilibrium,
)
from .validator import validate_constraints


class FEASolverError(Exception):
    """Raised when the FEA solver encounters a fatal error."""
    pass


def check_model_validity(structure: Structure) -> list[str]:
    """
    Pre-solve validation checks.

    Returns list of error messages (empty = valid).
    """
    errors = []

    if len(structure.nodes) < 2:
        errors.append("Structure must have at least 2 nodes")

    if len(structure.members) < 1:
        errors.append("Structure must have at least 1 member")

    if len(structure.supports) < 1:
        errors.append("Structure must have at least 1 support")

    if len(structure.loads) < 1:
        errors.append("Structure must have at least 1 load")

    # Check for duplicate nodes at same location
    seen_coords = {}
    for node in structure.nodes:
        key = (round(node.x, 6), round(node.y, 6), round(node.z, 6))
        if key in seen_coords:
            errors.append(
                f"Duplicate node location: nodes {seen_coords[key]} and {node.id} "
                f"at ({node.x}, {node.y}, {node.z})"
            )
        seen_coords[key] = node.id

    # Check member connectivity
    node_ids = {n.id for n in structure.nodes}
    for member in structure.members:
        if member.node_i not in node_ids:
            errors.append(f"Member {member.id} references unknown node {member.node_i}")
        if member.node_j not in node_ids:
            errors.append(f"Member {member.id} references unknown node {member.node_j}")
        if member.node_i == member.node_j:
            errors.append(f"Member {member.id} connects node {member.node_i} to itself")

    # Check supports reference valid nodes
    for support in structure.supports:
        if support.node_id not in node_ids:
            errors.append(f"Support references unknown node {support.node_id}")

    # Check loads reference valid nodes
    for load in structure.loads:
        if load.node_id not in node_ids:
            errors.append(f"Load references unknown node {load.node_id}")

    return errors


def solve(
    structure: Structure,
    spec: EngineeringSpec,
    combination: LoadCombination | None = None,
    include_self_weight: bool | None = None,
    thermal: "ThermalLoadCase | None" = None,
    settlements: "list[SupportSettlement] | None" = None,
    springs: "list[ElasticSupport] | None" = None,
) -> AnalysisResults:
    """
    Run the complete FEA analysis pipeline.

    Steps:
    1. Validate model
    2. Assemble global stiffness matrix
    3. Build load vector
    4. Apply boundary conditions
    5. Solve [K]{u} = {F}
    6. Compute member forces and stresses
    7. Compute nodal displacements
    8. Compute reactions
    9. Validate constraints

    Parameters:
        structure: Complete structural model
        spec: Engineering specification with constraints

    Returns:
        AnalysisResults containing all results and diagnosis

    Raises:
        FEASolverError: If the model is invalid or the solve fails
    """
    t_start = time.perf_counter()

    # --- Step 1: Validate ---
    errors = check_model_validity(structure)
    if errors:
        raise FEASolverError("Model validation failed:\n" + "\n".join(errors))

    # Topology defects are caught before assembly so the user gets the
    # engineering cause (orphan node, split assembly, zero-length member)
    # rather than a downstream matrix error that hides it.
    topology = check_topology(structure)
    fatal = [d for d in topology if d.severity is Severity.ERROR]
    if fatal:
        raise FEASolverError(
            "The model is not a valid structure.\n\n" + format_diagnostics(fatal)
        )

    # --- Step 2: Assemble K ---
    K_global, dof_map = assemble_global_stiffness(structure)

    # --- Step 3: Resolve load cases and build F ---
    #
    # Default (combination=None) is LIVE-only: the applied loads exactly as
    # given, structure treated as weightless. That preserves the behaviour
    # every hand-calculation benchmark was written against. Callers that
    # want dead load pass DEFAULT_COMBINATION explicitly, so self-weight is
    # never switched on behind a caller's back.
    if combination is None:
        combination = LIVE_ONLY_COMBINATION
    if include_self_weight is None:
        include_self_weight = combination.factor_for(LoadCaseType.DEAD) != 0.0

    cases, self_weight = build_load_cases(
        structure, include_self_weight=include_self_weight,
        thermal=thermal, settlements=settlements,
    )
    factored = collect_factored_loads(cases, combination)
    load_summary = summarize_load_cases(cases, combination, self_weight)

    # The solver consumes the factored case loads, never structure.loads
    # directly — so a force can only reach F by being in a named case.
    F = build_load_vector(structure, dof_map, loads=factored)

    # Thermal enters as an equivalent nodal load vector alongside the
    # mechanical loads (see thermal.py for the derivation).
    if thermal is not None and thermal.delta_t != 0.0:
        F = F + build_thermal_load_vector(structure, dof_map, thermal)

    # Spring supports add stiffness at (otherwise free) DOFs — folded into
    # K_global BEFORE the free/constrained partition and BEFORE K_original
    # is fixed, so both the solve and reaction recovery (R = K·u − F) see
    # the same, spring-augmented structural stiffness. A spring parallel
    # to a rigid support has no effect, since that DOF is still eliminated
    # by the rigid constraint regardless of what's on its diagonal — the
    # rigid restraint correctly dominates.
    if springs:
        K_global = apply_spring_stiffness(K_global, dof_map, springs)

    # --- Step 4: Identify constrained DOFs ---
    # K_original is retained unmodified for reaction recovery (R = K·u − F).
    # The solve itself uses the reduced free-DOF submatrix rather than the
    # elimination method, so the full matrix is never mutated.
    K_original = K_global
    constrained_dofs = get_constrained_dofs(structure.supports, dof_map)

    # --- Step 5: Solve the reduced (free-DOF) system ---
    #
    # Mechanism detection and the solve are done together via Cholesky
    # factorization of the free-DOF submatrix K_ff.
    #
    # Why not a determinant test: stiffness terms are O(AE/L) ~ 1e9, so
    # det(K) for an n-DOF system is O(1e9^n) — it overflows float64 above
    # roughly n=35 and returns inf/nan, silently defeating the check exactly
    # when structures get large (i.e. in 3D).
    #
    # Why Cholesky: for a properly restrained truss, K_ff is symmetric
    # positive definite. A rigid-body mode or internal mechanism makes it
    # singular (positive *semi*-definite), and the factorization fails —
    # which is precisely the condition we need to detect. It is also ~5x
    # faster than an SVD and reuses the factorization to solve, rather than
    # paying for a separate factorization in np.linalg.solve.
    n_free = len(F) - len(constrained_dofs)
    if n_free <= 0:
        raise FEASolverError("All DOFs are constrained — no free DOFs to solve")

    free_dofs = np.setdiff1d(np.arange(len(F)), np.asarray(constrained_dofs, dtype=int))
    K_ff = K_original[np.ix_(free_dofs, free_dofs)]
    F_f = F[free_dofs]

    # Prescribed (non-zero) support displacements. Partitioning gives
    #     K_ff u_f = F_f - K_fc u_c
    # so a settlement acts as an equivalent load term on the free DOF.
    u_prescribed = build_prescribed_displacement_vector(
        structure, dof_map, settlements or []
    )
    has_settlement = bool(np.any(u_prescribed))
    if has_settlement:
        constrained_index = np.asarray(sorted(constrained_dofs), dtype=int)
        K_fc = K_original[np.ix_(free_dofs, constrained_index)]
        F_f = F_f - K_fc @ u_prescribed[constrained_index]

    if not np.any(K_ff):
        raise FEASolverError("Stiffness matrix is entirely zero — no structural connectivity")

    try:
        cho = cho_factor(K_ff, lower=True, check_finite=False)
        u_f = cho_solve(cho, F_f, check_finite=False)
    except (LinAlgError, ScipyLinAlgError) as e:
        # Do not hand the user "matrix is not positive definite". Run the
        # full diagnostic battery and tell them which physical defect
        # caused it and what to change.
        diagnostics = explain_solve_failure(structure, K_ff)
        raise FEASolverError(
            "The structure cannot be solved — it is not a stable structure.\n\n"
            + format_diagnostics(diagnostics)
            + f"\n\n(underlying numerical error: {e})"
        )

    if not np.all(np.isfinite(u_f)):
        raise FEASolverError("Solver produced non-finite displacements")

    # Verify the reduced system was actually satisfied. A near-singular
    # matrix can factor successfully but yield a meaningless solution, so
    # this residual check catches what the factorization alone would miss.
    reference = np.linalg.norm(F_f)
    residual = np.linalg.norm(K_ff @ u_f - F_f)
    if reference > 1e-12 and (residual / reference) > 1e-6:
        diagnostics = explain_solve_failure(structure, K_ff)
        raise FEASolverError(
            f"The solve did not converge (relative residual "
            f"{residual / reference:.3e} exceeds 1e-6). The factorisation "
            f"succeeded but the solution does not satisfy the equations, "
            f"which means the system is numerically degenerate.\n\n"
            + format_diagnostics(diagnostics)
        )

    # Scatter the free-DOF solution back into the full displacement vector.
    # Constrained DOFs remain exactly zero (prescribed displacement = 0).
    # Constrained DOF take their prescribed value (zero unless a
    # settlement was imposed there).
    u = u_prescribed.copy()
    u[free_dofs] = u_f

    # --- Step 6: Member forces & stresses ---
    member_results = compute_member_forces(
        structure, u, dof_map,
        thermal_correction=thermal_force_correction(structure, thermal),
    )

    # --- Step 7: Nodal displacements ---
    node_results = compute_node_displacements(structure, u, dof_map)

    # --- Step 8: Reactions ---
    reactions = compute_reactions(K_original, u, F, structure, dof_map)

    # --- Step 9: Global force equilibrium (independent check on the solve) ---
    # Spring forces must be included alongside support reactions in the
    # equilibrium check — see springs.spring_reaction_forces for why a
    # naive K*u-F residual at the spring's own (free) DOF cannot be used
    # for this instead (it is identically ~0 there).
    equilibrium_reactions = reactions
    if springs:
        equilibrium_reactions = reactions + spring_reaction_forces(springs, dof_map, u)
    equilibrium = compute_equilibrium(structure, equilibrium_reactions, loads=factored)

    # --- Step 9b: Conditioning report on the SUCCESS path ---
    # A near-singular system can factor without error and return numbers
    # dominated by round-off. That is more dangerous than a hard failure,
    # so conditioning is measured even when the solve appeared to work.
    stability = analyze_stability(structure, K_ff=K_ff, n_free_dof=n_free)
    stability.diagnostics = topology + stability.diagnostics

    # --- Step 10: Validate constraints ---
    diagnosis = validate_constraints(structure, member_results, node_results, spec)

    # --- Step 11: Explicit verification breakdown ---
    # Reaching this point means the solve itself succeeded, the geometry
    # passed check_model_validity, and K was non-singular after BCs.
    max_allowable_disp = spec.span / spec.max_displacement_ratio
    checks = VerificationChecks(
        solver=True,
        geometry=True,
        boundary_conditions=True,
        equilibrium=equilibrium.passed,
        stress=diagnosis.max_stress_ratio <= 1.0,
        displacement=(diagnosis.max_displacement_mm / 1000.0) <= max_allowable_disp,
    )

    t_end = time.perf_counter()
    solve_time_ms = (t_end - t_start) * 1000

    return AnalysisResults(
        member_results=member_results,
        node_results=node_results,
        reactions=reactions,
        diagnosis=diagnosis,
        solve_time_ms=round(solve_time_ms, 2),
        total_weight_kg=round(structure.total_weight(), 2),
        equilibrium=equilibrium,
        checks=checks,
        dof_count=3 * len(structure.nodes),
        is_spatial=any(abs(n.z) > 1e-9 for n in structure.nodes),
        load_summary=load_summary,
        stability=stability,
    )
