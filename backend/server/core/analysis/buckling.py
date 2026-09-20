"""
NeuroPlan-3D — Buckling SCREENING (Priority 5)

This is a SCREENING check, not a buckling analysis. The distinction is
kept in the name everywhere it is surfaced.

────────────────────────────────────────────────────────────────────────
FORMULATION
────────────────────────────────────────────────────────────────────────
Effective length:               Le = K * L
Radius of gyration:             r  = sqrt(I / A)
Slenderness ratio:              lambda = Le / r = K*L / r
Euler critical load:            P_cr = pi^2 * E * I / (K*L)^2
Euler critical stress:          sigma_cr = pi^2 * E / lambda^2
Utilisation:                    |P_compression| / P_cr

EFFECTIVE LENGTH FACTOR K
    Theoretical values for ideal end conditions:
        pinned-pinned   K = 1.0
        fixed-fixed     K = 0.5
        fixed-pinned    K = 0.7
        fixed-free      K = 2.0
    NeuroPlan's solver is pin-jointed: it has no rotational DOF, so the
    member ends genuinely cannot transmit moment. K = 1.0 is therefore
    not a conservative guess here — it is the correct value for the model
    as formulated. Real bolted/welded gussets provide partial rotational
    restraint, so a real member is usually somewhat stronger than this
    screening suggests. K is exposed as an input so a user can override.

THE INELASTIC RANGE — WHERE EULER IS UNCONSERVATIVE
    Euler's formula assumes the material is still elastic at buckling.
    It ceases to be valid once sigma_cr exceeds the proportional limit.
    The transition slenderness is

        lambda_c = pi * sqrt(2E / fy)

    (the slenderness at which sigma_cr = fy/2, the classical Euler–
    Engesser transition point).

        lambda >= lambda_c : elastic buckling; Euler is applicable.
        lambda <  lambda_c : INELASTIC buckling. Euler OVERESTIMATES the
                             capacity, sometimes greatly. A member can
                             pass this screening and still fail.

    This is reported explicitly per member rather than silently ignored,
    because an unconservative check that looks like a pass is worse than
    no check at all.

WHAT THIS DOES NOT DO
    - No column curves / imperfection factors (that is design-code work;
      see the IS 800 module).
    - No lateral-torsional buckling.
    - No local/plate buckling of the tube wall.
    - No combined axial + bending interaction.
    - No geometric nonlinearity or P-delta.
    - No initial imperfection, residual stress or out-of-straightness.
    - Buckling about the weak axis only in the sense that a CHS is
      axisymmetric, so I is the same about every axis. For a non-
      axisymmetric section this screening would need the minimum I.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from ...models.structure import (
    Structure, MATERIAL_LIBRARY, MemberResult,
)

# Theoretical effective-length factors for ideal end conditions.
K_PINNED_PINNED = 1.0
K_FIXED_FIXED = 0.5
K_FIXED_PINNED = 0.7
K_FIXED_FREE = 2.0

# Default for this solver: pin-jointed formulation, no rotational DOF.
DEFAULT_K = K_PINNED_PINNED

# Below this slenderness the member squashes rather than buckles; Euler
# predicts an absurdly high load and the check is meaningless.
SHORT_COLUMN_SLENDERNESS = 30.0


class ColumnClass(str, Enum):
    NOT_COMPRESSION = "not_compression"   # tension or zero — buckling N/A
    SHORT = "short"                       # squashing governs
    INTERMEDIATE = "intermediate"         # inelastic buckling — Euler unconservative
    SLENDER = "slender"                   # elastic buckling — Euler applicable


class ScreeningStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    PASS = "pass"
    FAIL = "fail"
    UNCONSERVATIVE = "unconservative"     # passes Euler but Euler does not apply
    NOT_MODELED = "not_modeled"           # r/effective length degenerate — cannot screen


@dataclass
class MemberBucklingScreening:
    member_id: int
    axial_force: float               # N, negative = compression
    is_compression: bool
    length: float                    # m
    area: float                      # m^2 — as used in this screening's inputs
    inertia: float                   # m^4 — I, as used in this screening's inputs
    E: float                         # Pa — material modulus, as used
    k_factor: float
    effective_length: float          # m
    radius_of_gyration: float        # m
    slenderness: float               # KL/r
    transition_slenderness: float    # lambda_c
    column_class: ColumnClass
    euler_critical_load: float       # N
    euler_critical_stress: float     # Pa
    utilisation: float               # |P| / P_cr
    status: ScreeningStatus
    euler_applicable: bool
    note: str = ""


@dataclass
class BucklingScreeningReport:
    title: str = "BUCKLING SCREENING"
    members: list[MemberBucklingScreening] = field(default_factory=list)
    n_compression: int = 0
    n_failed: int = 0
    n_unconservative: int = 0
    max_slenderness: float = 0.0
    governing_member_id: int | None = None
    governing_reason: str = ""
    k_basis: str = (
        "K = 1.0 (pinned-pinned). NeuroPlan's solver is pin-jointed with no "
        "rotational DOF, so member ends transmit no moment — this is the "
        "correct K for the model as formulated, not a conservative default."
    )
    method_limitations: list[str] = field(default_factory=lambda: [
        "Elastic Euler screening only — no column curves or imperfection factors.",
        "No lateral-torsional buckling.",
        "No local (plate/shell) buckling of the tube wall.",
        "No combined axial + bending interaction.",
        "No geometric nonlinearity, P-delta, residual stress or out-of-straightness.",
    ])
    disclaimer: str = (
        "This is a SCREENING check, not a buckling analysis. It identifies "
        "members that clearly warrant attention; it does not establish that "
        "any member is adequate."
    )


def transition_slenderness(E: float, fy: float) -> float:
    """
    lambda_c = pi * sqrt(2E / fy)

    The classical Euler–Engesser transition: below this slenderness the
    critical stress would exceed fy/2 and inelastic effects dominate.
    """
    if fy <= 0:
        return float("inf")
    return math.pi * math.sqrt(2.0 * E / fy)


def screen_member(
    member_id: int,
    axial_force: float,
    length: float,
    area: float,
    inertia: float,
    radius_of_gyration: float,
    E: float,
    fy: float,
    k_factor: float = DEFAULT_K,
) -> MemberBucklingScreening:
    """Screen one member. Pure function — no structure access, easy to test."""
    is_compression = axial_force < 0.0
    effective_length = k_factor * length
    lambda_c = transition_slenderness(E, fy)

    if radius_of_gyration > 0.0:
        slenderness = effective_length / radius_of_gyration
    else:
        slenderness = float("inf")

    if effective_length > 0.0 and math.isfinite(slenderness):
        p_cr = (math.pi ** 2) * E * inertia / (effective_length ** 2)
        sigma_cr = (math.pi ** 2) * E / (slenderness ** 2)
    else:
        p_cr = float("inf")
        sigma_cr = float("inf")

    if not is_compression:
        return MemberBucklingScreening(
            member_id=member_id, axial_force=axial_force, is_compression=False,
            length=length, area=area, inertia=inertia, E=E,
            k_factor=k_factor, effective_length=effective_length,
            radius_of_gyration=radius_of_gyration, slenderness=slenderness,
            transition_slenderness=lambda_c, column_class=ColumnClass.NOT_COMPRESSION,
            euler_critical_load=p_cr, euler_critical_stress=sigma_cr,
            utilisation=0.0, status=ScreeningStatus.NOT_APPLICABLE,
            euler_applicable=False,
            note="Member is in tension (or unloaded); buckling does not apply.",
        )

    # A degenerate section (radius of gyration <= 0, e.g. zero wall
    # thickness) or non-finite effective length cannot be screened — this
    # is reported explicitly rather than silently producing a FAIL against
    # an infinite "critical load", which would misrepresent an input
    # problem as an overload finding.
    if radius_of_gyration <= 0.0 or not math.isfinite(slenderness):
        return MemberBucklingScreening(
            member_id=member_id, axial_force=axial_force, is_compression=True,
            length=length, area=area, inertia=inertia, E=E,
            k_factor=k_factor, effective_length=effective_length,
            radius_of_gyration=radius_of_gyration, slenderness=slenderness,
            transition_slenderness=lambda_c, column_class=ColumnClass.NOT_COMPRESSION,
            euler_critical_load=p_cr, euler_critical_stress=sigma_cr,
            utilisation=0.0, status=ScreeningStatus.NOT_MODELED,
            euler_applicable=False,
            note=(
                "Radius of gyration is not positive (degenerate section "
                "geometry) — this member cannot be screened for buckling. "
                "Not reported as PASS or FAIL."
            ),
        )

    demand = abs(axial_force)
    utilisation = demand / p_cr if p_cr > 0 and math.isfinite(p_cr) else float("inf")

    if slenderness < SHORT_COLUMN_SLENDERNESS:
        column_class = ColumnClass.SHORT
        euler_applicable = False
    elif slenderness < lambda_c:
        column_class = ColumnClass.INTERMEDIATE
        euler_applicable = False
    else:
        column_class = ColumnClass.SLENDER
        euler_applicable = True

    if utilisation > 1.0:
        status = ScreeningStatus.FAIL
        note = (
            f"Compression demand {demand/1000:.1f} kN exceeds the Euler "
            f"critical load {p_cr/1000:.1f} kN."
        )
    elif not euler_applicable:
        status = ScreeningStatus.UNCONSERVATIVE
        if column_class is ColumnClass.SHORT:
            note = (
                f"Slenderness {slenderness:.0f} is below {SHORT_COLUMN_SLENDERNESS:.0f}: "
                f"this is a short column that will squash rather than buckle. "
                f"The Euler load is not a meaningful capacity here — check "
                f"the yield/squash capacity instead."
            )
        else:
            note = (
                f"Slenderness {slenderness:.0f} is below the transition "
                f"lambda_c = {lambda_c:.0f}, so buckling would be INELASTIC. "
                f"Euler OVERESTIMATES capacity in this range — passing this "
                f"screening does not mean the member is adequate. A code "
                f"column curve is required."
            )
    else:
        status = ScreeningStatus.PASS
        note = (
            f"Elastic range (lambda {slenderness:.0f} >= lambda_c {lambda_c:.0f}); "
            f"Euler is applicable. Utilisation {utilisation:.2f}."
        )

    return MemberBucklingScreening(
        member_id=member_id, axial_force=axial_force, is_compression=True,
        length=length, area=area, inertia=inertia, E=E,
        k_factor=k_factor, effective_length=effective_length,
        radius_of_gyration=radius_of_gyration, slenderness=slenderness,
        transition_slenderness=lambda_c, column_class=column_class,
        euler_critical_load=p_cr, euler_critical_stress=sigma_cr,
        utilisation=utilisation, status=status,
        euler_applicable=euler_applicable, note=note,
    )


def screen_structure(
    structure: Structure,
    member_results: list[MemberResult],
    k_factor: float = DEFAULT_K,
) -> BucklingScreeningReport:
    """Run the screening across every member of a solved structure."""
    nodes = structure.node_dict()
    by_id = {m.id: m for m in structure.members}
    report = BucklingScreeningReport()

    worst_utilisation = -1.0
    governing: MemberBucklingScreening | None = None
    for result in member_results:
        member = by_id.get(result.member_id)
        if member is None:
            continue
        material = MATERIAL_LIBRARY.get(member.material_key)
        if material is None:
            continue

        screening = screen_member(
            member_id=member.id,
            axial_force=result.axial_force,
            length=member.length(nodes),
            area=member.section.area,
            inertia=member.section.moment_of_inertia,
            radius_of_gyration=member.section.radius_of_gyration,
            E=material.E,
            fy=material.yield_stress,
            k_factor=k_factor,
        )
        report.members.append(screening)

        if screening.is_compression:
            report.n_compression += 1
            if math.isfinite(screening.slenderness):
                report.max_slenderness = max(report.max_slenderness, screening.slenderness)
            if screening.status is ScreeningStatus.FAIL:
                report.n_failed += 1
            elif screening.status is ScreeningStatus.UNCONSERVATIVE:
                report.n_unconservative += 1
            if screening.utilisation > worst_utilisation:
                worst_utilisation = screening.utilisation
                report.governing_member_id = member.id
                governing = screening

    if governing is not None:
        report.governing_reason = (
            f"M{governing.member_id} has the highest demand/capacity ratio "
            f"({governing.utilisation:.3f}) among the {report.n_compression} "
            f"compression member(s) screened — slenderness KL/r = "
            f"{governing.slenderness:.1f}, column class "
            f"{governing.column_class.value}."
        )

    return report
