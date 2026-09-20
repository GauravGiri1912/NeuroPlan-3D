"""
NeuroPlan-3D — Nonlinear Truss Analysis: Geometric (P-Delta) and Material

Extends the linear Direct Stiffness solver with an incremental-iterative
Newton-Raphson solution for pin-jointed 3D trusses. Two independent
nonlinearities are supported and can be toggled separately:

  GEOMETRIC  — equilibrium is enforced on the DEFORMED geometry (P-Delta /
               large-displacement effects), via a geometric stiffness
               matrix built from the current member axial force.
  MATERIAL   — each member follows an elastic-perfectly-plastic axial
               law: stress is capped at +/- f_y once the member yields.

────────────────────────────────────────────────────────────────────────
FORMULATION — GEOMETRIC (P-DELTA)
────────────────────────────────────────────────────────────────────────
For a 2-node pin-jointed bar with unit direction c = (cx,cy,cz), length L
and CURRENT axial force N (tension +), the truss geometric stiffness
matrix (McGuire, Gallagher & Ziemian, "Matrix Structural Analysis", the
standard reference for this exact element) is

    K_g = (N/L) * [ (I - c c^T)   -(I - c c^T) ]
                  [ -(I - c c^T)   (I - c c^T) ]

where I is the 3x3 identity and (I - c c^T) projects onto the plane
TRANSVERSE to the member axis. This is the correct and complete
geometric stiffness for a truss bar: N > 0 (tension) stiffens the
transverse directions (a taut string resists lateral perturbation);
N < 0 (compression) softens them (this is precisely what drives global
sway/snap-through instability).

IMPORTANT SCOPE LIMIT, stated because it is easy to get wrong: since a
truss element has NO bending stiffness (EI never appears in this
formulation), this captures P-DELTA at the level of the ASSEMBLED
STRUCTURE — joints translating relative to each other, global sway,
snap-through — but it structurally CANNOT capture individual-member
flexural (Euler) buckling. That remains the separate per-member check
in analysis/buckling.py and codes/is800_2007.py.

The nonlinear equilibrium equation solved at each load step is

    K_T(u) * du = F - F_int(u)

with tangent stiffness K_T = K_elastic + K_g(N(u)) reassembled every
iteration from the current member forces, and internal force F_int
computed from the current axial forces projected onto global DOF. The
load is applied in increments (`n_steps`) and each increment is solved
to convergence (Newton-Raphson) before the next is applied, so equilibrium
is enforced on the deformed shape at every stage — this is what makes it
P-Delta rather than a linear correction.

────────────────────────────────────────────────────────────────────────
FORMULATION — MATERIAL (ELASTIC-PERFECTLY-PLASTIC)
────────────────────────────────────────────────────────────────────────
Each member's axial stress-strain law:

    stress = E * strain,             |stress| <  f_y   (elastic)
    stress = sign(strain) * f_y,     |stress| >= f_y   (yielded)

At each Newton-Raphson iteration, a member's TANGENT axial stiffness is

    (AE/L)   if the member is elastic at the current trial state
    ~0       if the member has yielded (perfectly plastic: no further
             stress increase for further strain, so no further
             stiffness contribution beyond the member's residual force)

A yielded member still carries its capacity force (A*f_y, signed) in the
internal-force vector — it just stops contributing tangent stiffness.
This is the standard elastic-perfectly-plastic truss algorithm (see e.g.
Crisfield, "Non-linear Finite Element Analysis of Solids and Structures",
Vol 1, Ch. 5, or any FEA textbook's worked truss-yielding example).

Reduced/zero tangent stiffness for a fully-yielded, fully-disconnected
sub-structure can make K_T singular; this is DETECTED (via the existing
Cholesky-based mechanism check) and reported as a genuine failure — the
structure has become a mechanism, which is the physically correct outcome
of losing too many members to yielding.

────────────────────────────────────────────────────────────────────────
WHAT THIS DOES NOT DO
────────────────────────────────────────────────────────────────────────
  - No strain hardening (perfectly plastic only) and no cyclic/hysteretic
    behaviour — loading history beyond monotonic is not tracked.
  - No buckling-induced post-peak softening of individual members (a
    yielded/buckled compression member here simply plateaus at its
    capacity, it does not lose capacity).
  - No arc-length / snap-through tracing past a limit point: if the
    tangent stiffness loses positive-definiteness (e.g. exactly at a
    global buckling load), Newton-Raphson at fixed load will fail to
    converge and this is reported honestly as NON-CONVERGENCE, not as a
    number.
  - Convergence is on force residual, in the units of the applied load
    (Newtons) — not a normalized dimensionless energy check.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.linalg import LinAlgError
from scipy.linalg import cho_factor, cho_solve, LinAlgError as ScipyLinAlgError

from ...models.structure import Structure, MATERIAL_LIBRARY
from .assembly import assemble_global_stiffness
from .boundary import get_constrained_dofs
from .elements import direction_cosines

DEFAULT_LOAD_STEPS = 10
DEFAULT_MAX_ITERATIONS = 30
DEFAULT_FORCE_TOLERANCE = 1e-6   # relative to the step's applied load norm


@dataclass
class MemberState:
    member_id: int
    axial_force: float
    yielded: bool = False


@dataclass
class NonlinearStepResult:
    step: int
    load_factor: float
    converged: bool
    iterations: int
    residual_norm: float
    member_states: list[MemberState] = field(default_factory=list)


@dataclass
class NonlinearAnalysisResult:
    geometric: bool
    material: bool
    steps: list[NonlinearStepResult] = field(default_factory=list)
    displacements: np.ndarray = field(default_factory=lambda: np.zeros(0))
    converged: bool = True
    divergence_step: int | None = None
    divergence_reason: str = ""
    scope_note: str = (
        "Geometric nonlinearity captures ASSEMBLY-LEVEL P-Delta/sway effects "
        "only; it cannot represent individual-member flexural buckling "
        "(no bending DOF exists in this element). Material nonlinearity is "
        "elastic-perfectly-plastic with no hardening and no cyclic history."
    )

    @property
    def final_member_forces(self) -> dict[int, float]:
        if not self.steps:
            return {}
        return {m.member_id: m.axial_force for m in self.steps[-1].member_states}

    @property
    def any_yielded(self) -> bool:
        return bool(self.steps) and any(m.yielded for m in self.steps[-1].member_states)


def _geometric_stiffness_element(cx: float, cy: float, cz: float, L: float,
                                  N: float) -> np.ndarray:
    """K_g for one 3D truss bar — see module docstring for the derivation."""
    c = np.array([cx, cy, cz])
    proj = np.eye(3) - np.outer(c, c)
    k = N / L
    K = np.zeros((6, 6))
    K[0:3, 0:3] = k * proj
    K[0:3, 3:6] = -k * proj
    K[3:6, 0:3] = -k * proj
    K[3:6, 3:6] = k * proj
    return K


def _internal_force_vector(structure: Structure, dof_map, member_forces: dict[int, float],
                           node_positions: dict[int, tuple[float, float, float]]) -> np.ndarray:
    """Assemble F_int from current member axial forces, on the DEFORMED geometry."""
    n_dof = 3 * len(structure.nodes)
    F_int = np.zeros(n_dof)
    for member in structure.members:
        xi, yi, zi = node_positions[member.node_i]
        xj, yj, zj = node_positions[member.node_j]
        dx, dy, dz = xj - xi, yj - yi, zj - zi
        L = float(np.sqrt(dx * dx + dy * dy + dz * dz))
        if L < 1e-12:
            continue
        c = np.array([dx / L, dy / L, dz / L])
        N = member_forces[member.id]
        dofs_i = dof_map[member.node_i]
        dofs_j = dof_map[member.node_j]
        # Sign convention derived directly from the linear element
        # stiffness matrix K_e = k*[[C,-C],[-C,C]] (elements.py), so that
        # K_e @ u reproduces this exactly in the small-strain limit:
        # F_int_i = k*C*(u_i - u_j) = -N*c ; F_int_j = k*C*(u_j - u_i) = +N*c.
        # (N > 0 tension pulls the two ends TOWARD each other: node i is
        # pulled toward j, i.e. in +c; node j is pulled toward i, i.e. -c
        # — so as internal RESISTING force appearing on the F_int side of
        # F_ext - F_int = 0, node i carries -N*c and node j carries +N*c.)
        F_int[dofs_i[0]] -= N * c[0]
        F_int[dofs_i[1]] -= N * c[1]
        F_int[dofs_i[2]] -= N * c[2]
        F_int[dofs_j[0]] += N * c[0]
        F_int[dofs_j[1]] += N * c[1]
        F_int[dofs_j[2]] += N * c[2]
    return F_int


def _tangent_stiffness(structure: Structure, dof_map, node_positions,
                       member_forces: dict[int, float], yielded: dict[int, bool],
                       geometric: bool, material: bool) -> np.ndarray:
    n_dof = 3 * len(structure.nodes)
    K = np.zeros((n_dof, n_dof))
    for member in structure.members:
        material_props = MATERIAL_LIBRARY.get(member.material_key)
        if material_props is None:
            continue
        xi, yi, zi = node_positions[member.node_i]
        xj, yj, zj = node_positions[member.node_j]
        dx, dy, dz = xj - xi, yj - yi, zj - zi
        L = float(np.sqrt(dx * dx + dy * dy + dz * dz))
        if L < 1e-12:
            continue
        cx, cy, cz = dx / L, dy / L, dz / L
        A = member.section.area

        has_yielded = material and yielded.get(member.id, False)
        # Elastic (axial) tangent stiffness — zero once the member has
        # yielded under the perfectly-plastic law (no further stress rise).
        k_axial = 0.0 if has_yielded else (A * material_props.E / L)

        c = np.array([cx, cy, cz])
        C = np.outer(c, c)
        k_elem = np.zeros((6, 6))
        k_elem[0:3, 0:3] = k_axial * C
        k_elem[0:3, 3:6] = -k_axial * C
        k_elem[3:6, 0:3] = -k_axial * C
        k_elem[3:6, 3:6] = k_axial * C

        if geometric:
            N = member_forces.get(member.id, 0.0)
            k_elem = k_elem + _geometric_stiffness_element(cx, cy, cz, L, N)

        dofs_i = dof_map[member.node_i]
        dofs_j = dof_map[member.node_j]
        idx = list(dofs_i) + list(dofs_j)
        for a in range(6):
            for b in range(6):
                K[idx[a], idx[b]] += k_elem[a, b]
    return K


def _member_axial_forces(structure: Structure, u: np.ndarray, dof_map,
                         node_positions, fy_cap: bool,
                         base_positions: dict[int, tuple[float, float, float]] | None = None,
                         geometric: bool = True,
                         ) -> tuple[dict[int, float], dict[int, bool]]:
    """
    Recover axial force per member.

    Two distinct elongation measures are used depending on `geometric`,
    and this distinction is the whole point of the geometric/material
    toggle being independent:

    geometric=True  — exact large-displacement elongation,
        delta = L_current - L_original, using the CURRENT (deformed)
        direction cosine. Projecting total displacement onto the current
        axis instead (c_current . (u_j - u_i)) is only first-order
        accurate in the rotation and was caught failing a regression test
        here: relative error against a closed-form snap-through benchmark
        grew from 3% to 35% across the load range before this fix, because
        under finite rotation c_current . d0 != L_original.

    geometric=False — the standard SMALL-DISPLACEMENT formula,
        delta = c_original . (u_j - u_i), using the ORIGINAL (undeformed)
        direction cosine — identical to postprocess.py's linear solver.
        This is essential, not cosmetic: an earlier version of this
        module used the large-displacement kinematics unconditionally and
        only toggled the geometric-STIFFNESS (tangent) term off, which
        left the EQUILIBRIUM EQUATION itself always nonlinear — Newton-
        Raphson converged to the same nonlinear root regardless of the
        flag, silently making "geometric=False" not actually linear. A
        regression test (test_geometric_nonlinearity_actually_changes_
        the_result) catches this: it asserts the linear and P-Delta
        solutions for the same load DIFFER for a case with real rotation.
    """
    if base_positions is None:
        base_positions = {n.id: (n.x, n.y, n.z) for n in structure.nodes}

    forces: dict[int, float] = {}
    yielded: dict[int, bool] = {}
    for member in structure.members:
        material_props = MATERIAL_LIBRARY.get(member.material_key)
        if material_props is None:
            forces[member.id] = 0.0
            yielded[member.id] = False
            continue

        x0i, y0i, z0i = base_positions[member.node_i]
        x0j, y0j, z0j = base_positions[member.node_j]
        dx0, dy0, dz0 = x0j - x0i, y0j - y0i, z0j - z0i
        L0 = float(np.sqrt(dx0 * dx0 + dy0 * dy0 + dz0 * dz0))

        if geometric:
            xi, yi, zi = node_positions[member.node_i]
            xj, yj, zj = node_positions[member.node_j]
            dx, dy, dz = xj - xi, yj - yi, zj - zi
            L = float(np.sqrt(dx * dx + dy * dy + dz * dz))
            delta = L - L0
        else:
            c0 = (np.array([dx0, dy0, dz0]) / L0) if L0 > 1e-12 else np.zeros(3)
            dofs_i = dof_map[member.node_i]
            dofs_j = dof_map[member.node_j]
            u_i = u[list(dofs_i)]
            u_j = u[list(dofs_j)]
            delta = float(c0 @ (u_j - u_i))

        A = member.section.area
        E = material_props.E
        elastic_force = (A * E / L0) * delta if L0 > 1e-12 else 0.0

        if fy_cap:
            cap = A * material_props.yield_stress
            if elastic_force > cap:
                forces[member.id] = cap
                yielded[member.id] = True
            elif elastic_force < -cap:
                forces[member.id] = -cap
                yielded[member.id] = True
            else:
                forces[member.id] = elastic_force
                yielded[member.id] = False
        else:
            forces[member.id] = elastic_force
            yielded[member.id] = False
    return forces, yielded


def solve_nonlinear(
    structure: Structure,
    target_load: np.ndarray,
    dof_map,
    constrained_dofs,
    geometric: bool = True,
    material: bool = False,
    n_steps: int = DEFAULT_LOAD_STEPS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    tolerance: float = DEFAULT_FORCE_TOLERANCE,
) -> NonlinearAnalysisResult:
    """
    Incremental-iterative Newton-Raphson solve.

    `target_load` is the FULL load vector (as the linear solver would
    build it); it is applied over `n_steps` equal increments, each solved
    to convergence before the next increment is applied — updating the
    displacement (and, for geometric nonlinearity, the member direction
    cosines) at every step, which is what makes this P-Delta rather than
    a single linear correction.
    """
    n_dof = len(target_load)
    free_dofs = np.setdiff1d(np.arange(n_dof), np.asarray(sorted(constrained_dofs), dtype=int))
    if len(free_dofs) == 0:
        raise ValueError("All DOFs are constrained — no free DOFs to solve")

    base_positions = {n.id: (n.x, n.y, n.z) for n in structure.nodes}
    u = np.zeros(n_dof)
    result = NonlinearAnalysisResult(geometric=geometric, material=material)

    for step in range(1, n_steps + 1):
        load_factor = step / n_steps
        F_target = target_load * load_factor

        converged = False
        residual_norm = float("inf")
        iterations = 0

        for iteration in range(1, max_iterations + 1):
            iterations = iteration
            positions = {
                nid: (x + u[dof_map[nid][0]], y + u[dof_map[nid][1]], z + u[dof_map[nid][2]])
                for nid, (x, y, z) in base_positions.items()
            }
            # Kinematic positions: DEFORMED when geometric nonlinearity is
            # on (equilibrium enforced on the current shape), ORIGINAL
            # when off (small-displacement theory — see _member_axial_
            # forces docstring for why this distinction is load-bearing,
            # not cosmetic).
            kinematic_positions = positions if geometric else base_positions

            member_forces, yielded = _member_axial_forces(
                structure, u, dof_map, kinematic_positions, fy_cap=material,
                base_positions=base_positions, geometric=geometric,
            )
            F_int = _internal_force_vector(structure, dof_map, member_forces, kinematic_positions)
            residual = F_target - F_int

            reference = np.linalg.norm(F_target[free_dofs])
            residual_norm = float(np.linalg.norm(residual[free_dofs]))
            rel_residual = residual_norm / reference if reference > 1e-9 else residual_norm
            if rel_residual < tolerance:
                converged = True
                break

            K_T = _tangent_stiffness(
                structure, dof_map, kinematic_positions, member_forces, yielded, geometric, material
            )
            K_ff = K_T[np.ix_(free_dofs, free_dofs)]
            r_f = residual[free_dofs]

            try:
                cho = cho_factor(K_ff, lower=True, check_finite=False)
                du_f = cho_solve(cho, r_f, check_finite=False)
            except (LinAlgError, ScipyLinAlgError):
                result.converged = False
                result.divergence_step = step
                result.divergence_reason = (
                    f"Tangent stiffness became singular at step {step}, iteration "
                    f"{iteration} — the structure has lost stability (a mechanism "
                    f"formed, e.g. from geometric softening near a critical load "
                    f"or from enough members yielding to remove a load path). "
                    f"This is reported as non-convergence, not extrapolated as a "
                    f"numeric result."
                )
                return result

            if not np.all(np.isfinite(du_f)):
                result.converged = False
                result.divergence_step = step
                result.divergence_reason = f"Non-finite displacement increment at step {step}."
                return result

            u = u.copy()
            u[free_dofs] += du_f

        positions = {
            nid: (x + u[dof_map[nid][0]], y + u[dof_map[nid][1]], z + u[dof_map[nid][2]])
            for nid, (x, y, z) in base_positions.items()
        }
        kinematic_positions = positions if geometric else base_positions
        final_forces, final_yielded = _member_axial_forces(
            structure, u, dof_map, kinematic_positions, fy_cap=material,
            base_positions=base_positions, geometric=geometric,
        )
        result.steps.append(NonlinearStepResult(
            step=step, load_factor=load_factor, converged=converged,
            iterations=iterations, residual_norm=residual_norm,
            member_states=[
                MemberState(member_id=mid, axial_force=f, yielded=final_yielded.get(mid, False))
                for mid, f in final_forces.items()
            ],
        ))

        if not converged:
            result.converged = False
            result.divergence_step = step
            result.divergence_reason = (
                f"Did not converge within {max_iterations} iterations at load "
                f"factor {load_factor:.3f} (relative residual "
                f"{residual_norm:.3e}). The structure may be approaching a "
                f"critical (buckling) load or losing too many members to "
                f"yielding."
            )
            return result

    result.displacements = u
    return result


def build_nonlinear_inputs(structure: Structure):
    """Convenience: assemble dof_map and constrained_dofs the way solve_nonlinear expects."""
    _, dof_map = assemble_global_stiffness(structure)
    constrained = get_constrained_dofs(structure.supports, dof_map)
    return dof_map, constrained
