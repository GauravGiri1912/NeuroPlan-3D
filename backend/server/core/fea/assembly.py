"""
NeuroPlan-3D — Global Stiffness Matrix Assembly

Assembles individual element stiffness matrices into the global
system stiffness matrix using DOF mapping.

Uses scipy.sparse for efficiency (though for MVP truss sizes,
dense matrices would also be fine).
"""
import numpy as np
from scipy import sparse
from ...models.structure import Structure, Node, Member
from .elements import element_stiffness_for_member


def build_dof_map(nodes: list[Node]) -> dict[int, tuple[int, int, int]]:
    """
    Build mapping from node ID to global DOF indices.

    Each node has 3 DOFs: (dx, dy, dz)
    Node with index i in the sorted list maps to DOFs (3i, 3i+1, 3i+2)

    Returns:
        dict mapping node_id → (dof_x, dof_y, dof_z)
    """
    # Sort nodes by ID for deterministic ordering
    sorted_nodes = sorted(nodes, key=lambda n: n.id)
    dof_map = {}
    for idx, node in enumerate(sorted_nodes):
        base = 3 * idx
        dof_map[node.id] = (base, base + 1, base + 2)
    return dof_map


def assemble_global_stiffness(
    structure: Structure,
) -> tuple[np.ndarray, dict[int, tuple[int, int, int]]]:
    """
    Assemble the global stiffness matrix from all element contributions.

    Parameters:
        structure: Structure containing nodes and members

    Returns:
        (K_global, dof_map)
        K_global: (3N × 3N) numpy array — global stiffness matrix
        dof_map: node_id → (dof_x, dof_y, dof_z)
    """
    nodes = structure.nodes
    members = structure.members
    node_dict = structure.node_dict()
    dof_map = build_dof_map(nodes)

    n_dof = 3 * len(nodes)
    K = np.zeros((n_dof, n_dof))

    for member in members:
        # Get element stiffness (6×6)
        K_e = element_stiffness_for_member(member, node_dict)

        # Get global DOF indices for this element
        dofs_i = dof_map[member.node_i]
        dofs_j = dof_map[member.node_j]
        element_dofs = list(dofs_i) + list(dofs_j)  # [6 DOF indices]

        # Scatter element stiffness into global matrix
        for a in range(6):
            for b in range(6):
                K[element_dofs[a], element_dofs[b]] += K_e[a, b]

    return K, dof_map


def build_load_vector(
    structure: Structure,
    dof_map: dict[int, tuple[int, int, int]],
    loads=None,
) -> np.ndarray:
    """
    Assemble the global load vector from point loads.

    Parameters:
        structure: Structure containing loads
        dof_map: node_id → (dof_x, dof_y, dof_z)
        loads: explicit list of PointLoad to apply. When None, the
            structure's own loads are used. The solver passes the
            factored load-case loads here so that self-weight and load
            factors are visible in the case summary rather than being
            applied implicitly inside this function.

    Returns:
        F: (3N,) numpy array — global load vector
    """
    n_dof = 3 * len(structure.nodes)
    F = np.zeros(n_dof)

    if loads is None:
        loads = structure.loads

    for load in loads:
        if load.node_id not in dof_map:
            raise ValueError(f"Load references unknown node {load.node_id}")
        dofs = dof_map[load.node_id]
        F[dofs[0]] += load.fx
        F[dofs[1]] += load.fy
        F[dofs[2]] += load.fz

    return F
