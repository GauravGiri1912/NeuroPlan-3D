"""
NeuroPlan-3D — Post-Processing

Computes member forces, stresses, and reactions from the
global displacement vector.
"""
import math
import numpy as np
from ...models.structure import (
    Structure, Node, Member, MemberResult, NodeResult, Reaction,
    MemberStatus, MATERIAL_LIBRARY, EquilibriumCheck,
)
from .elements import direction_cosines


def compute_member_forces(
    structure: Structure,
    u: np.ndarray,
    dof_map: dict[int, tuple[int, int, int]],
    thermal_correction: dict[int, float] | None = None,
) -> list[MemberResult]:
    """
    Compute axial forces and stresses for all members.

    For each member:
    1. Extract nodal displacements in global coordinates
    2. Project onto member axis using direction cosines
    3. Compute elongation and axial force
    4. Compute stress = force / area

    Parameters:
        structure: The structural model
        u: Global displacement vector
        dof_map: Node ID → DOF indices

    Returns:
        List of MemberResult with forces and stresses
    """
    if thermal_correction is None:
        thermal_correction = {}

    node_dict = structure.node_dict()
    results = []

    for member in structure.members:
        ni = node_dict[member.node_i]
        nj = node_dict[member.node_j]

        cx, cy, cz, L = direction_cosines(ni, nj)

        # Extract nodal displacements
        dofs_i = dof_map[member.node_i]
        dofs_j = dof_map[member.node_j]

        u_i = np.array([u[dofs_i[0]], u[dofs_i[1]], u[dofs_i[2]]])
        u_j = np.array([u[dofs_j[0]], u[dofs_j[1]], u[dofs_j[2]]])

        # Direction vector
        c = np.array([cx, cy, cz])

        # Elongation = projection of relative displacement onto member axis
        delta = np.dot(c, u_j - u_i)

        # Axial force: F = (AE/L) * delta
        A = member.section.area
        mat = MATERIAL_LIBRARY[member.material_key]
        E = mat.E
        # Total axial force = elastic force implied by the nodal
        # displacements MINUS the thermal contribution. Without the
        # subtraction a freely-expanding bar would report a spurious
        # tension equal to E*A*alpha*dT; with it, a free bar correctly
        # reports zero and a fully restrained bar reports -E*A*alpha*dT.
        axial_force = (A * E / L) * delta - thermal_correction.get(member.id, 0.0)

        # Stress
        stress = axial_force / A if A > 0 else 0.0

        # Allowable stress
        allowable = mat.yield_stress  # will be divided by FOS later in validator

        # Euler buckling load (for compression members)
        I = member.section.moment_of_inertia
        if L > 0:
            euler_load = (math.pi**2 * E * I) / (L**2)
        else:
            euler_load = float('inf')

        results.append(MemberResult(
            member_id=member.id,
            axial_force=axial_force,
            stress=stress,
            stress_ratio=0.0,  # computed in validator with FOS
            allowable_stress=allowable,
            euler_buckling_load=euler_load,
        ))

    return results


def compute_node_displacements(
    structure: Structure,
    u: np.ndarray,
    dof_map: dict[int, tuple[int, int, int]],
) -> list[NodeResult]:
    """
    Extract per-node displacement results from the global vector.
    """
    results = []
    for node in structure.nodes:
        dofs = dof_map[node.id]
        results.append(NodeResult(
            node_id=node.id,
            dx=u[dofs[0]],
            dy=u[dofs[1]],
            dz=u[dofs[2]],
        ))
    return results


def compute_reactions(
    K_original: np.ndarray,
    u: np.ndarray,
    F: np.ndarray,
    structure: Structure,
    dof_map: dict[int, tuple[int, int, int]],
) -> list[Reaction]:
    """
    Compute support reactions: R = K_original * u - F at constrained DOFs.
    """
    R_full = K_original @ u - F
    reactions = []

    for support in structure.supports:
        dofs = dof_map[support.node_id]
        reactions.append(Reaction(
            node_id=support.node_id,
            rx=R_full[dofs[0]] if support.dx else 0.0,
            ry=R_full[dofs[1]] if support.dy else 0.0,
            rz=R_full[dofs[2]] if support.dz else 0.0,
        ))

    return reactions


def _moment_about_origin(x: float, y: float, z: float,
                          fx: float, fy: float, fz: float) -> tuple[float, float, float]:
    """Cross product r × F for a point force at (x, y, z)."""
    return (
        y * fz - z * fy,   # Mx
        z * fx - x * fz,   # My
        x * fy - y * fx,   # Mz
    )


def compute_equilibrium(
    structure: Structure,
    reactions: list[Reaction],
    tolerance: float = 1e-6,
    loads=None,
) -> EquilibriumCheck:
    """
    Verify global equilibrium — three force equations and three moment
    equations:

        Σ(applied) + Σ(reactions) = 0          (Fx, Fy, Fz)
        Σ(r × applied) + Σ(r × reactions) = 0  (Mx, My, Mz about the origin)

    The reactions come from R = K·u − F, so this is an independent check
    that the assembled system was actually satisfied by the solve — an
    assembly bug, a bad boundary condition, or an ill-conditioned matrix
    shows up here even when individual stresses look plausible.

    Moment equilibrium catches a class of error that force equilibrium
    alone cannot: reactions that sum correctly but are distributed to the
    wrong supports still balance in force while violating moment balance.

    Residuals are normalized separately (forces by total load magnitude,
    moments by total applied-moment magnitude) since the two have different
    units and scales.
    """
    node_map = structure.node_dict()

    # `loads` must be the SAME forces that were assembled into F — including
    # self-weight and any load factors. Checking reactions against
    # structure.loads while the solve used a different vector would turn
    # this independent check into a guaranteed false failure.
    if loads is None:
        loads = structure.loads

    applied_fx = sum(l.fx for l in loads)
    applied_fy = sum(l.fy for l in loads)
    applied_fz = sum(l.fz for l in loads)

    reaction_fx = sum(r.rx for r in reactions)
    reaction_fy = sum(r.ry for r in reactions)
    reaction_fz = sum(r.rz for r in reactions)

    residual_fx = applied_fx + reaction_fx
    residual_fy = applied_fy + reaction_fy
    residual_fz = applied_fz + reaction_fz

    # --- Moments about the global origin ---
    applied_mx = applied_my = applied_mz = 0.0
    applied_moment_scale = 0.0
    for load in loads:
        n = node_map[load.node_id]
        mx, my, mz = _moment_about_origin(n.x, n.y, n.z, load.fx, load.fy, load.fz)
        applied_mx += mx
        applied_my += my
        applied_mz += mz
        applied_moment_scale += math.sqrt(mx * mx + my * my + mz * mz)

    reaction_mx = reaction_my = reaction_mz = 0.0
    for r in reactions:
        n = node_map[r.node_id]
        mx, my, mz = _moment_about_origin(n.x, n.y, n.z, r.rx, r.ry, r.rz)
        reaction_mx += mx
        reaction_my += my
        reaction_mz += mz

    residual_mx = applied_mx + reaction_mx
    residual_my = applied_my + reaction_my
    residual_mz = applied_mz + reaction_mz

    load_magnitude = math.sqrt(applied_fx**2 + applied_fy**2 + applied_fz**2)
    max_force_residual = max(abs(residual_fx), abs(residual_fy), abs(residual_fz))
    max_moment_residual = max(abs(residual_mx), abs(residual_my), abs(residual_mz))

    # Guard against a zero-load model (no meaningful normalization available).
    relative_residual = (
        max_force_residual / load_magnitude if load_magnitude > 1e-12 else max_force_residual
    )
    relative_moment_residual = (
        max_moment_residual / applied_moment_scale
        if applied_moment_scale > 1e-12 else max_moment_residual
    )

    return EquilibriumCheck(
        residual_fx=residual_fx,
        residual_fy=residual_fy,
        residual_fz=residual_fz,
        residual_mx=residual_mx,
        residual_my=residual_my,
        residual_mz=residual_mz,
        load_magnitude=load_magnitude,
        moment_magnitude=applied_moment_scale,
        relative_residual=relative_residual,
        relative_moment_residual=relative_moment_residual,
        tolerance=tolerance,
        passed=(relative_residual <= tolerance and relative_moment_residual <= tolerance),
    )
