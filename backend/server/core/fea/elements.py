"""
NeuroPlan-3D — Truss Element Stiffness Matrix

Computes the local and global stiffness matrices for 3D truss elements.
Each truss element has 2 nodes, 3 DOF per node (dx, dy, dz) = 6 DOF total.

The local stiffness for an axial element is:
    k_local = (AE/L) * [[ 1, -1],
                         [-1,  1]]

Expanded to 6×6 and transformed to global coordinates via direction cosines.
"""
import numpy as np
from ...models.structure import Node, Member, MATERIAL_LIBRARY


def direction_cosines(node_i: Node, node_j: Node) -> tuple[float, float, float, float]:
    """
    Compute direction cosines and length for a member.

    Returns:
        (cx, cy, cz, L) — direction cosines and member length
    """
    dx = node_j.x - node_i.x
    dy = node_j.y - node_i.y
    dz = node_j.z - node_i.z
    L = np.sqrt(dx**2 + dy**2 + dz**2)
    if L < 1e-12:
        raise ValueError(
            f"Zero-length member between nodes ({node_i.x},{node_i.y},{node_i.z}) "
            f"and ({node_j.x},{node_j.y},{node_j.z})"
        )
    return dx / L, dy / L, dz / L, L


def truss_element_stiffness(
    node_i: Node,
    node_j: Node,
    A: float,
    E: float,
) -> np.ndarray:
    """
    Compute the 6×6 global stiffness matrix for a 3D truss element.

    Parameters:
        node_i: Start node
        node_j: End node
        A: Cross-sectional area (m²)
        E: Young's modulus (Pa)

    Returns:
        6×6 numpy array — global element stiffness matrix
        DOF order: [u_i, v_i, w_i, u_j, v_j, w_j]
    """
    cx, cy, cz, L = direction_cosines(node_i, node_j)

    # Build the transformation vector
    # For a truss element, the stiffness in global coordinates is:
    # K_e = (AE/L) * [[ C,  -C],
    #                  [-C,  C]]
    # where C = [cx, cy, cz]^T * [cx, cy, cz] (3×3 outer product)

    c = np.array([cx, cy, cz])
    C = np.outer(c, c)  # 3×3

    k = (A * E / L)

    # Assemble 6×6 matrix
    K_e = np.zeros((6, 6))
    K_e[0:3, 0:3] = k * C       # top-left
    K_e[0:3, 3:6] = -k * C      # top-right
    K_e[3:6, 0:3] = -k * C      # bottom-left
    K_e[3:6, 3:6] = k * C       # bottom-right

    return K_e


def element_stiffness_for_member(
    member: Member,
    nodes: dict[int, Node],
) -> np.ndarray:
    """
    Convenience function: compute stiffness matrix for a Member object.
    """
    node_i = nodes[member.node_i]
    node_j = nodes[member.node_j]
    A = member.section.area
    mat = MATERIAL_LIBRARY[member.material_key]
    E = mat.E
    return truss_element_stiffness(node_i, node_j, A, E)
