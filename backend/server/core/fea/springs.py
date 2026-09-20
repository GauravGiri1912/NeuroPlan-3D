"""
NeuroPlan-3D — Elastic Spring Supports

The honest primitive for "flexible foundation" support: a spring of
stiffness k (N/m) supplied by the caller, NOT a soil model. There is no
bearing-capacity theory, no consolidation/settlement prediction, and no
SPT-N or CPT correlation here — k must come from the user (e.g. a
geotechnical report's subgrade modulus times tributary area, or an
assumed value for sensitivity study). This module only injects that
known stiffness into the structural stiffness matrix correctly.

────────────────────────────────────────────────────────────────────────
FORMULATION
────────────────────────────────────────────────────────────────────────
A translational spring at DOF d with stiffness k contributes a diagonal
term to the global stiffness matrix:

    K[d, d] += k

and the DOF remains FREE (not eliminated as a rigid constraint) — the
spring itself provides the restoring force via K*u, exactly like any
other structural stiffness contribution. This is standard practice
(e.g. Winkler-spring / elastic foundation modelling in matrix structural
analysis) and requires no change to the solve procedure beyond adding
this term to K before the free/constrained partition: a spring on an
otherwise-free DOF naturally lands inside K_ff after partitioning; a
spring parallel to a RIGID support has no effect (the constrained DOF is
eliminated regardless of what's added to its diagonal), which is also
the physically correct outcome — a rigid restraint dominates a parallel
spring.

VALIDATION: a single bar with a rigid pin at one end and a spring
(instead of a rigid support) at the other, loaded axially, is exactly a
two-spring system in series (member axial stiffness AE/L, support
stiffness k_spring):

    u = F * (1/(AE/L) + 1/k_spring)

This is checked directly in the test suite.

────────────────────────────────────────────────────────────────────────
WHAT THIS DOES NOT DO
────────────────────────────────────────────────────────────────────────
  - No bearing capacity, no settlement prediction, no consolidation
    theory, no soil layering, no SPT-N/CPT correlation.
  - Linear (constant-k) spring only — no nonlinear soil response, no
    tension cutoff (a real soil spring cannot pull the foundation down;
    this linear spring can, and does not model separation).
  - No coupling between adjacent spring supports (each DOF's spring is
    independent — no shared soil continuum behaviour).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ElasticSupport:
    """A translational spring at one node. Stiffnesses in N/m; 0 = no spring in that direction."""
    node_id: int
    kx: float = 0.0
    ky: float = 0.0
    kz: float = 0.0

    def source_note(self) -> str:
        return (
            "Spring stiffness is a USER INPUT, not derived from soil "
            "properties. No bearing capacity, settlement prediction or "
            "consolidation theory is applied."
        )


def spring_reaction_forces(
    springs: list[ElasticSupport],
    dof_map: dict[int, tuple[int, int, int]],
    u,
) -> list:
    """
    The force EACH spring exerts on the structure: F_spring = -k*u,
    the direct definition of a linear spring's restoring force.

    This is deliberately NOT computed as K_original@u - F at the spring's
    DOF: that quantity is ~0 there, because the DOF is FREE and the
    solved system already satisfies K*u=F exactly at every free row —
    that residual mixes together the member's contribution and the
    spring's, cancelling to zero, and says nothing about how much of the
    restraint came from the spring specifically. -k*u isolates exactly
    that, and is what a global equilibrium check needs to add alongside
    ordinary support reactions: without it, an equilibrium check that
    only sums rigid-support reactions will show a spurious residual equal
    to whatever load the spring(s) are actually carrying.
    """
    from ...models.structure import Reaction
    forces = []
    for spring in springs:
        dx, dy, dz = dof_map[spring.node_id]
        forces.append(Reaction(
            node_id=spring.node_id,
            rx=-spring.kx * u[dx],
            ry=-spring.ky * u[dy],
            rz=-spring.kz * u[dz],
        ))
    return forces


def apply_spring_stiffness(
    K: np.ndarray,
    dof_map: dict[int, tuple[int, int, int]],
    springs: list[ElasticSupport],
) -> np.ndarray:
    """
    Return a COPY of K with spring stiffnesses added to the diagonal.
    K is never mutated in place, so a caller holding the original
    (unmodified) matrix elsewhere is never surprised.
    """
    K_out = K.copy()
    for spring in springs:
        if spring.node_id not in dof_map:
            raise ValueError(f"Spring support references unknown node {spring.node_id}")
        dx, dy, dz = dof_map[spring.node_id]
        K_out[dx, dx] += spring.kx
        K_out[dy, dy] += spring.ky
        K_out[dz, dz] += spring.kz
    return K_out
