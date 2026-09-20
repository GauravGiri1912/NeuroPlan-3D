"""
NeuroPlan-3D — Boundary Condition Application

Applies displacement boundary conditions to the global stiffness matrix
and load vector using the elimination (row/column zeroing) method.

This method:
1. Zeros out the row and column of each constrained DOF
2. Sets the diagonal to 1.0
3. Sets the corresponding load to 0.0

This produces exact boundary enforcement (no penalty parameter to tune).
"""
import numpy as np
from ...models.structure import Structure, Support


def get_constrained_dofs(
    supports: list[Support],
    dof_map: dict[int, tuple[int, int, int]],
) -> list[int]:
    """
    Get list of all constrained DOF indices from support definitions.

    Returns:
        Sorted list of constrained global DOF indices
    """
    constrained = []
    for support in supports:
        if support.node_id not in dof_map:
            raise ValueError(f"Support references unknown node {support.node_id}")
        dofs = dof_map[support.node_id]
        if support.dx:
            constrained.append(dofs[0])
        if support.dy:
            constrained.append(dofs[1])
        if support.dz:
            constrained.append(dofs[2])
    return sorted(set(constrained))


def apply_boundary_conditions(
    K: np.ndarray,
    F: np.ndarray,
    supports: list[Support],
    dof_map: dict[int, tuple[int, int, int]],
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """
    Apply boundary conditions via the elimination method.

    Parameters:
        K: Global stiffness matrix (modified in place on copy)
        F: Global load vector (modified in place on copy)
        supports: List of support conditions
        dof_map: node_id → DOF indices

    Returns:
        (K_mod, F_mod, constrained_dofs)
    """
    K_mod = K.copy()
    F_mod = F.copy()

    constrained = get_constrained_dofs(supports, dof_map)

    for dof in constrained:
        # Zero the entire row and column
        K_mod[dof, :] = 0.0
        K_mod[:, dof] = 0.0
        # Set diagonal to 1
        K_mod[dof, dof] = 1.0
        # Set load to 0 (prescribed displacement = 0)
        F_mod[dof] = 0.0

    return K_mod, F_mod, constrained
