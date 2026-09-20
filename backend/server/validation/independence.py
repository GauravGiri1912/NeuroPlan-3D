"""
NeuroPlan-3D — Calibration vs. Validation

Implements the single question that decides whether a reference comparison
counts as validation evidence at all:

    Was ANY model parameter — sensor mapping, material property, cross
    section, boundary condition, load, or geometry — selected using the
    measured results?

        YES -> REFERENCE COMPARED / NOT INDEPENDENT VALIDATION
        NO  -> INDEPENDENT REFERENCE COMPARISON

Why this is a computed verdict and not a sentence somebody wrote:

Without it, a future change can tune E, a cross-sectional area, a support
condition, a load magnitude, or a sensor mapping until the error is tiny,
and the result still renders as "validated". Error magnitude is not
evidence of correctness when the parameters were fitted to that error.
Tuning parameters to match data is CALIBRATION; comparing a model whose
parameters were fixed beforehand is VALIDATION. This distinction is the
substance of ASME V&V 10 (Guide for Verification and Validation in
Computational Solid Mechanics) and of the NAFEMS V&V guidance, both of
which treat calibrated agreement as a fit, not as predictive evidence.

The verdict is therefore derived by scanning the case's declared
parameter inventory on every run. Two deliberate rules:

  1. Any single calibrated parameter is enough to downgrade the whole
     comparison. Independence is not a majority vote — one fitted input
     makes the residual error partly circular.

  2. An empty or incomplete inventory yields NOT_ASSESSED, never
     INDEPENDENT. `any([])` is False, so a naive check would report an
     unexamined model as independent — the exact failure this module
     exists to prevent. Absence of recorded calibration is not evidence
     that no calibration happened.
"""
from __future__ import annotations

from .models import (
    EvidenceIndependence, IndependenceAssessment, ModelParameter, ParameterRole,
)

STANDARD_REFERENCE = (
    "ASME V&V 10, Guide for Verification and Validation in Computational "
    "Solid Mechanics, and NAFEMS V&V guidance: parameters fitted to "
    "measured data constitute model CALIBRATION, which does not by itself "
    "establish predictive capability. Validation requires comparison "
    "against data not used to set the model's parameters."
)

HEADLINE_INDEPENDENT = "INDEPENDENT REFERENCE COMPARISON"
HEADLINE_CALIBRATED = "REFERENCE COMPARED — NOT INDEPENDENT VALIDATION"
HEADLINE_NOT_ASSESSED = "INDEPENDENCE NOT ASSESSED"


def assess_independence(parameters: list[ModelParameter]) -> IndependenceAssessment:
    """
    Derive the independence verdict from a case's parameter inventory.

    The inventory must cover every ParameterRole. A role with no declared
    parameter means that part of the model was never examined for
    calibration, which is reported as NOT_ASSESSED rather than assumed
    clean.
    """
    calibrated = [p for p in parameters if p.selected_using_measurements]
    independent = [p for p in parameters if not p.selected_using_measurements]

    covered = {p.role for p in parameters}
    missing = [role for role in ParameterRole if role not in covered]

    if calibrated:
        names = ", ".join(f"{p.name} ({p.role.value})" for p in calibrated)
        return IndependenceAssessment(
            verdict=EvidenceIndependence.CALIBRATED,
            headline=HEADLINE_CALIBRATED,
            explanation=(
                f"{len(calibrated)} of {len(parameters)} model parameters were "
                f"selected with reference to the measured results: {names}. "
                f"The agreement at the affected points is therefore partly "
                f"circular and is NOT independent evidence that the solver is "
                f"correct — a small error here reflects the fit, not "
                f"demonstrated predictive capability. This comparison cannot "
                f"be promoted past REFERENCE_COMPARED."
            ),
            standard_reference=STANDARD_REFERENCE,
            calibrated_parameters=calibrated,
            independent_parameters=independent,
            missing_roles=missing,
        )

    if not parameters or missing:
        missing_names = ", ".join(role.value for role in missing) or "all roles"
        return IndependenceAssessment(
            verdict=EvidenceIndependence.NOT_ASSESSED,
            headline=HEADLINE_NOT_ASSESSED,
            explanation=(
                f"No parameter inventory is declared for: {missing_names}. "
                f"Independence cannot be claimed for a model whose inputs have "
                f"not been enumerated — an unexamined parameter is not a "
                f"verified-clean one. Declare every role in the case's "
                f"parameter inventory to obtain a verdict."
            ),
            standard_reference=STANDARD_REFERENCE,
            calibrated_parameters=[],
            independent_parameters=independent,
            missing_roles=missing,
        )

    return IndependenceAssessment(
        verdict=EvidenceIndependence.INDEPENDENT,
        headline=HEADLINE_INDEPENDENT,
        explanation=(
            f"All {len(parameters)} declared model parameters — covering "
            f"geometry, material, cross sections, boundary conditions, loads "
            f"and sensor mapping — were fixed from the source documentation "
            f"before the comparison was run. None was selected using the "
            f"measured results, so this comparison is a genuine predictive "
            f"test of the solver."
        ),
        standard_reference=STANDARD_REFERENCE,
        calibrated_parameters=[],
        independent_parameters=independent,
        missing_roles=[],
    )


def blocks_criterion_promotion(assessment: IndependenceAssessment) -> bool:
    """
    A comparison that is not INDEPENDENT must never be promoted to
    CRITERION_MET, even if an acceptance criterion is later defined and
    the numbers satisfy it. Passing a threshold you tuned toward is not
    a pass.
    """
    return assessment.verdict is not EvidenceIndependence.INDEPENDENT
