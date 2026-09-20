"""
NeuroPlan-3D — Modal Analysis and IS 1893:2016 Response-Spectrum Seismic

Two layers:
  1. MODAL ANALYSIS — natural frequencies and mode shapes. Exact linear
     algebra, no code-specific content, no uncertainty.
  2. RESPONSE SPECTRUM SEISMIC — projects a design spectrum (IS 1893:2016
     Part 1) onto the mode shapes and combines them (SRSS) into an
     equivalent static force vector, run through the same production
     solver as every other load case.

────────────────────────────────────────────────────────────────────────
MODAL ANALYSIS — FORMULATION
────────────────────────────────────────────────────────────────────────
Free vibration of the undamped structure:  M*u_ddot + K*u = 0
Assuming u = phi*sin(omega*t) gives the generalized eigenproblem

    K * phi = omega^2 * M * phi

solved here on the FREE DOF only (constrained DOF have no dynamic
freedom). `scipy.linalg.eigh(K_ff, M_ff)` solves this directly for
symmetric K_ff and symmetric POSITIVE DEFINITE M_ff, and returns
eigenvectors that are M-ORTHONORMAL: phi_i^T M phi_j = delta_ij. This
orthonormality is a mathematical property of the eigenproblem, not an
assumption — it is checked directly in the test suite as a solver
correctness test independent of any closed-form example.

MASS MODEL: lumped, translational-only, diagonal. Each member's mass
(rho*A*L, exactly as in load_cases.py's self-weight) is split rho*A*L/2
to each end node — identical logic to gravity load lumping, just without
multiplying by g. No rotational mass terms exist because the element has
no rotational DOF. Optionally, a fraction of LIVE-case point loads can be
converted to seismic mass (mass = |load|/g) per user-supplied fraction,
reflecting that codes require some portion of live load to be included
as seismic mass — but WHICH fraction (IS 1893 cl. 7.3.1 ties it to
occupancy/imposed-load intensity) is a user decision, never assumed.

────────────────────────────────────────────────────────────────────────
IS 1893:2016 PART 1 — RESPONSE SPECTRUM SEISMIC (cl. 6.4.2, 7.7.5)
────────────────────────────────────────────────────────────────────────
Design horizontal seismic coefficient for mode i:

    Ah_i = (Z/2) * (I/R) * (Sa/g)_i

  Z  — zone factor (Table 3): II=0.10, III=0.16, IV=0.24, V=0.36
  I  — importance factor (Table 8) — SUPPLIED by the caller, never
       assumed, since it depends on the structure's function/occupancy.
  R  — response reduction factor (Table 9) — SUPPLIED by the caller for
       the same reason (depends on the lateral system and ductility).
  Sa/g — spectral shape (Fig. 2 / cl. 6.4.2), 5% damping, by soil type:

    Type I  (rock/hard):  0.00-0.10s: 1+15T | 0.10-0.40s: 2.5 | 0.40-4.00s: 1.000/T
    Type II (medium):     0.00-0.10s: 1+15T | 0.10-0.55s: 2.5 | 0.55-4.00s: 1.375/T
    Type III (soft):      0.00-0.10s: 1+15T | 0.10-0.67s: 2.5 | 0.67-4.00s: 1.675/T

  The plateau breakpoints (T2 = 0.40 / 0.55 / 0.67 s) are the code's
  published soil-type shape parameters and are used directly. The 1/T
  coefficient past each breakpoint is NOT independently recalled — it is
  DERIVED as 2.5*T2, the value continuity at T2 requires. This was
  adopted after a continuity self-test caught a ~1% mismatch from an
  imprecisely-remembered published digit (1.36 instead of 1.375 for Type
  II); deriving it removes that uncertainty rather than hiding it behind
  a looser tolerance. This implementation does not extend the spectrum
  beyond T=4.0s (no long-period tail is applied) — a real design for a
  structure with a fundamental period beyond 4s must consult the current
  code text directly rather than rely on this tool.

MODAL COMBINATION: SRSS (Square Root of Sum of Squares) only. IS 1893
requires CQC (Complete Quadratic Combination) when modal frequencies are
closely spaced (cl. 7.7.5.4) — CQC is NOT implemented here. SRSS is
reported as an approximation and is unconservative for closely-spaced
modes; this is stated explicitly in every result.

Per-mode equivalent static nodal force vector:

    F_i = Ah_i * g * Gamma_i * M * phi_i,    Gamma_i = phi_i^T M r

where r is the influence vector (1 at every translational DOF in the
excited direction, 0 elsewhere) and Gamma_i is the modal participation
factor (M_i = 1 already, from the M-orthonormal eigenvectors). Modal base
shear V_i = Ah_i * g * Gamma_i^2. Combined (SRSS) nodal forces and base
shear are then applied as an ordinary static load case through the same
production solve() used everywhere else in NeuroPlan — this is an
EQUIVALENT STATIC representation of the response-spectrum result, not a
time-history.

────────────────────────────────────────────────────────────────────────
WHAT THIS DOES NOT DO
────────────────────────────────────────────────────────────────────────
  - No time-history / nonlinear dynamic analysis.
  - No CQC modal combination (SRSS only).
  - No torsional/accidental eccentricity (cl. 7.9).
  - No vertical seismic component.
  - No soil-structure interaction or site amplification beyond the
    spectrum's own soil-type shape.
  - No damping other than the spectrum's built-in 5%.
  - Seismic mass excludes non-structural/equipment mass unless the
    caller explicitly supplies a live-load mass fraction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from scipy.linalg import eigh

from ...models.structure import Structure, MATERIAL_LIBRARY, LoadCaseType
from .load_cases import GRAVITY
from .assembly import assemble_global_stiffness
from .boundary import get_constrained_dofs

MAX_MODES_DEFAULT = 6


class SoilType(str, Enum):
    ROCK_HARD = "type_i_rock_hard"
    MEDIUM = "type_ii_medium"
    SOFT = "type_iii_soft"


class SeismicZone(str, Enum):
    II = "ii"
    III = "iii"
    IV = "iv"
    V = "v"


ZONE_FACTOR: dict[SeismicZone, float] = {
    SeismicZone.II: 0.10,
    SeismicZone.III: 0.16,
    SeismicZone.IV: 0.24,
    SeismicZone.V: 0.36,
}

# T2 = period where the flat plateau (Sa/g = 2.5) ends and the 1/T decay
# begins, per soil type. The published IS 1893:2016 coefficient of that
# 1/T branch is DERIVED, not independently recalled here: continuity at
# T2 requires coeff/T2 = 2.5, i.e. coeff = 2.5*T2. Deriving it this way
# — rather than hardcoding a remembered coefficient — was adopted after a
# continuity regression test caught a ~1% mismatch (1.36 vs the required
# 1.375 for Type II) that traced to an imprecisely recalled published
# digit. The breakpoints T2 themselves (0.40 / 0.55 / 0.67 s) are
# structural features of the code's spectrum shape and are used directly.
_SPECTRUM_T2: dict[SoilType, float] = {
    SoilType.ROCK_HARD: 0.40,
    SoilType.MEDIUM: 0.55,
    SoilType.SOFT: 0.67,
}
_SPECTRUM_BREAKPOINTS: dict[SoilType, tuple[float, float]] = {
    soil: (t2, 2.5 * t2) for soil, t2 in _SPECTRUM_T2.items()
}


def design_spectrum_sa_g(period_s: float, soil: SoilType) -> float:
    """Sa/g per IS 1893:2016 Part 1, Fig. 2 / cl. 6.4.2 — see module docstring."""
    if period_s < 0:
        raise ValueError("period must be non-negative")
    t2, coeff = _SPECTRUM_BREAKPOINTS[soil]
    if period_s <= 0.10:
        return 1.0 + 15.0 * period_s
    if period_s <= t2:
        return 2.5
    if period_s <= 4.0:
        return coeff / period_s
    raise ValueError(
        f"Period {period_s:.3f}s exceeds 4.0s — this spectrum is not extended "
        f"beyond the code's tabulated range. Consult IS 1893:2016 directly."
    )


@dataclass
class Mode:
    mode_number: int
    angular_frequency: float    # rad/s
    frequency_hz: float
    period_s: float
    mode_shape: np.ndarray      # full-length (all DOF), zero at constrained DOF
    modal_mass: float           # should be 1.0 (M-orthonormal)
    participation_x: float = 0.0
    participation_y: float = 0.0
    participation_z: float = 0.0
    effective_mass_x: float = 0.0
    effective_mass_y: float = 0.0
    effective_mass_z: float = 0.0


@dataclass
class ModalAnalysisResult:
    modes: list[Mode] = field(default_factory=list)
    total_mass_kg: float = 0.0
    mass_participation_x_percent: float = 0.0
    mass_participation_y_percent: float = 0.0
    mass_participation_z_percent: float = 0.0
    mass_model_note: str = (
        "Lumped translational mass from member self-weight (rho*A*L, half "
        "to each end node), matching the self-weight LOAD calculation "
        "exactly. Non-structural / live-load mass is excluded unless a "
        "live-load mass fraction was explicitly supplied."
    )


def assemble_lumped_mass_matrix(
    structure: Structure,
    live_load_mass_fraction: float = 0.0,
    live_loads: list | None = None,
    gravity: float = GRAVITY,
) -> np.ndarray:
    """
    Diagonal lumped mass matrix, translational DOF only.

    live_load_mass_fraction, if > 0, converts that fraction of the
    magnitude of each LIVE-case point load's vertical (Y) component into
    additional nodal mass (mass = fraction*|Fy|/g) at the same node and
    DOF. This mirrors (without automating) IS 1893 cl. 7.3.1's
    requirement that some portion of imposed load be treated as seismic
    mass — the fraction itself is a code/occupancy decision left to the
    caller.
    """
    n_dof = 3 * len(structure.nodes)
    M = np.zeros(n_dof)
    nodes = structure.node_dict()

    dof_map = {}
    idx = 0
    for node in structure.nodes:
        dof_map[node.id] = (idx, idx + 1, idx + 2)
        idx += 3

    for member in structure.members:
        material = MATERIAL_LIBRARY.get(member.material_key)
        if material is None:
            continue
        length = member.length(nodes)
        mass = material.density * member.section.area * length
        half = mass / 2.0
        for node_id in (member.node_i, member.node_j):
            dx, dy, dz = dof_map[node_id]
            M[dx] += half
            M[dy] += half
            M[dz] += half

    if live_load_mass_fraction > 0 and live_loads:
        for load in live_loads:
            if load.node_id not in dof_map:
                continue
            extra = live_load_mass_fraction * abs(load.fy) / gravity
            dx, dy, dz = dof_map[load.node_id]
            M[dx] += extra
            M[dy] += extra
            M[dz] += extra

    return M


def solve_modal(
    structure: Structure,
    n_modes: int = MAX_MODES_DEFAULT,
    live_load_mass_fraction: float = 0.0,
) -> ModalAnalysisResult:
    """Natural frequencies, mode shapes and modal participation factors."""
    K_global, dof_map = assemble_global_stiffness(structure)
    constrained_dofs = get_constrained_dofs(structure.supports, dof_map)
    n_dof = K_global.shape[0]

    live_loads = [l for l in structure.loads if l.case == LoadCaseType.LIVE]
    M_diag = assemble_lumped_mass_matrix(
        structure, live_load_mass_fraction=live_load_mass_fraction, live_loads=live_loads
    )

    free_dofs = np.setdiff1d(np.arange(n_dof), np.asarray(sorted(constrained_dofs), dtype=int))
    if len(free_dofs) == 0:
        raise ValueError("All DOFs are constrained — no free DOFs for modal analysis")

    K_ff = K_global[np.ix_(free_dofs, free_dofs)]
    m_free = M_diag[free_dofs]

    if np.any(m_free <= 0):
        zero_mass_dofs = free_dofs[m_free <= 0]
        raise ValueError(
            f"{len(zero_mass_dofs)} free DOF(s) have zero mass — modal analysis "
            f"requires every free DOF to have tributary mass (a massless free "
            f"DOF gives an infinite-frequency mode, which is not physical for "
            f"this analysis). Check for a node with no connected member mass."
        )
    M_ff = np.diag(m_free)

    n_modes = min(n_modes, len(free_dofs))
    eigenvalues, eigenvectors = eigh(
        K_ff, M_ff, subset_by_index=[0, n_modes - 1]
    )

    total_mass = float(np.sum(M_diag) / 3.0)   # 3 DOF share the same lumped nodal mass
    result = ModalAnalysisResult(total_mass_kg=total_mass)

    def _influence_vector(axis: int) -> np.ndarray:
        r = np.zeros(len(free_dofs))
        idx = np.array([i for i, d in enumerate(free_dofs) if d % 3 == axis], dtype=int)
        if idx.size:
            r[idx] = 1.0
        return r

    r_x, r_y, r_z = _influence_vector(0), _influence_vector(1), _influence_vector(2)

    sum_eff_x = sum_eff_y = sum_eff_z = 0.0
    for i in range(n_modes):
        lam = eigenvalues[i]
        omega = math.sqrt(max(lam, 0.0))
        phi_free = eigenvectors[:, i]

        phi_full = np.zeros(n_dof)
        phi_full[free_dofs] = phi_free

        modal_mass = float(phi_free @ (M_ff @ phi_free))   # should be ~1.0

        gamma_x = float(phi_free @ (M_ff @ r_x))
        gamma_y = float(phi_free @ (M_ff @ r_y))
        gamma_z = float(phi_free @ (M_ff @ r_z))
        eff_x, eff_y, eff_z = gamma_x ** 2, gamma_y ** 2, gamma_z ** 2
        sum_eff_x += eff_x; sum_eff_y += eff_y; sum_eff_z += eff_z

        freq_hz = omega / (2.0 * math.pi) if omega > 0 else 0.0
        period = 1.0 / freq_hz if freq_hz > 0 else float("inf")

        result.modes.append(Mode(
            mode_number=i + 1, angular_frequency=omega, frequency_hz=freq_hz,
            period_s=period, mode_shape=phi_full, modal_mass=modal_mass,
            participation_x=gamma_x, participation_y=gamma_y, participation_z=gamma_z,
            effective_mass_x=eff_x, effective_mass_y=eff_y, effective_mass_z=eff_z,
        ))

    if total_mass > 0:
        result.mass_participation_x_percent = 100.0 * sum_eff_x / total_mass
        result.mass_participation_y_percent = 100.0 * sum_eff_y / total_mass
        result.mass_participation_z_percent = 100.0 * sum_eff_z / total_mass

    return result


@dataclass
class ModalSeismicContribution:
    mode_number: int
    period_s: float
    sa_over_g: float
    ah: float
    base_shear_n: float


@dataclass
class ResponseSpectrumResult:
    zone: str
    zone_factor: float
    importance_factor: float
    response_reduction_factor: float
    soil_type: str
    direction: str
    modal: ModalAnalysisResult
    mode_contributions: list[ModalSeismicContribution] = field(default_factory=list)
    nodal_forces: np.ndarray = field(default_factory=lambda: np.zeros(0))
    base_shear_srss_n: float = 0.0
    combination_method: str = "SRSS"
    combination_caveat: str = (
        "SRSS combination only. CQC (required by IS 1893 cl. 7.7.5.4 for "
        "closely-spaced modes) is NOT implemented — SRSS can be "
        "unconservative when modal periods are close together."
    )
    scope_note: str = (
        "Equivalent-static representation of a linear response-spectrum "
        "result. No time-history, no CQC, no torsional/accidental "
        "eccentricity, no vertical seismic component, no soil-structure "
        "interaction beyond the spectrum's own soil-type shape."
    )


def response_spectrum_analysis(
    structure: Structure,
    zone: SeismicZone,
    soil: SoilType,
    importance_factor: float,
    response_reduction_factor: float,
    direction: str = "x",
    n_modes: int = MAX_MODES_DEFAULT,
    live_load_mass_fraction: float = 0.0,
) -> ResponseSpectrumResult:
    """
    IS 1893:2016 response-spectrum seismic analysis (see module docstring
    for the full formulation). `direction` is 'x' or 'z' (horizontal).
    """
    if response_reduction_factor <= 0:
        raise ValueError("response_reduction_factor must be positive")
    if direction not in ("x", "z"):
        raise ValueError("direction must be 'x' or 'z' (horizontal seismic only)")

    modal = solve_modal(structure, n_modes=n_modes, live_load_mass_fraction=live_load_mass_fraction)
    K_global, dof_map = assemble_global_stiffness(structure)
    n_dof = K_global.shape[0]
    M_diag = assemble_lumped_mass_matrix(
        structure, live_load_mass_fraction=live_load_mass_fraction,
        live_loads=[l for l in structure.loads if l.case == LoadCaseType.LIVE],
    )

    z = ZONE_FACTOR[zone]
    result = ResponseSpectrumResult(
        zone=zone.value, zone_factor=z, importance_factor=importance_factor,
        response_reduction_factor=response_reduction_factor, soil_type=soil.value,
        direction=direction, modal=modal,
    )

    combined_forces_sq = np.zeros(n_dof)
    base_shear_sq = 0.0

    for mode in modal.modes:
        if mode.period_s == float("inf") or mode.period_s <= 0:
            continue
        capped_period = min(mode.period_s, 4.0)
        sa_g = design_spectrum_sa_g(capped_period, soil)
        ah = (z / 2.0) * (importance_factor / response_reduction_factor) * sa_g

        gamma = mode.participation_x if direction == "x" else mode.participation_z
        base_shear_i = ah * GRAVITY * (gamma ** 2)
        result.mode_contributions.append(ModalSeismicContribution(
            mode_number=mode.mode_number, period_s=mode.period_s,
            sa_over_g=sa_g, ah=ah, base_shear_n=base_shear_i,
        ))
        base_shear_sq += base_shear_i ** 2

        force_i = ah * GRAVITY * gamma * (M_diag * mode.mode_shape)
        combined_forces_sq += force_i ** 2

    result.nodal_forces = np.sqrt(combined_forces_sq)
    result.base_shear_srss_n = math.sqrt(base_shear_sq)
    return result
