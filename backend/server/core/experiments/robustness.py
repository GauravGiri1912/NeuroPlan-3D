"""Deterministic Load Robustness Sweep.

Runs the EXISTING LOAD_SCALE perturbation (server.core.experiments.engine
.run_experiment) at a fixed set of load scale factors and records the
actual solver output at each. Not a reliability or probabilistic
assessment — see RobustnessSweepResult.terminology_note.

WHY A SCENARIO CANNOT BECOME UNSTABLE HERE: the global stiffness matrix
K depends only on geometry, supports and member properties — never on
load magnitude. Scaling a load changes F, not K, so a structure that is
stable at one scale is stable at every scale (0.80-1.20 or otherwise);
"unstable" is not a reachable per-scenario outcome for LOAD_SCALE alone.
An UNSOLVABLE BASELINE (a mechanism before any scaling) is a different,
model-level problem: run_experiment() solves the baseline unguarded (by
design — see engine.py), so a broken baseline raises FEASolverError
immediately, failing the whole sweep loudly rather than fabricating five
scenarios from a structure that was never valid to begin with.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...models.structure import Structure, EngineeringSpec
from ..fea.load_cases import LoadCombination
from .engine import run_experiment
from .models import (
    Perturbation, PerturbationType, ExperimentResult,
    STATUS_STABLE, STATUS_UNSTABLE, STATUS_FAILED_CHECKS,
)

DEFAULT_LOAD_SCALES: tuple[float, ...] = (0.80, 0.90, 1.00, 1.10, 1.20)

TERMINOLOGY_NOTE = (
    "Deterministic robustness sweep — results observed under the tested "
    "load scenarios only. This is NOT a reliability or probabilistic "
    "assessment: no probability is calculated, and no claim is made about "
    "structural safety at load scales outside those actually tested."
)


@dataclass
class LoadScaleScenario:
    load_scale: float
    structural_status: str
    max_displacement_mm: float | None
    max_stress_mpa: float | None
    critical_member: int | None
    verified: bool | None
    error: str | None


@dataclass
class RobustnessSweepSummary:
    total_scenarios: int
    stable_scenarios: int
    unstable_scenarios: int
    failed_check_scenarios: int
    max_observed_displacement_mm: float | None
    max_observed_stress_mpa: float | None


@dataclass
class RobustnessSweepResult:
    load_index: int
    scales: list[float]
    scenarios: list[LoadScaleScenario] = field(default_factory=list)
    summary: RobustnessSweepSummary | None = None
    terminology_note: str = TERMINOLOGY_NOTE


def _scenario_from(scale: float, result: ExperimentResult) -> LoadScaleScenario:
    """Reuses ExperimentResult's own null-safety: perturbed_max_*/critical_member/
    verified are already None whenever the scenario was unstable, so no
    displacement/stress is fabricated here."""
    return LoadScaleScenario(
        load_scale=scale,
        structural_status=result.structural_status,
        max_displacement_mm=result.perturbed_max_displacement_mm,
        max_stress_mpa=result.perturbed_max_stress_mpa,
        critical_member=result.critical_member_after,
        verified=result.perturbed_verified,
        error=result.perturbed_error,
    )


def _summarize(scenarios: list[LoadScaleScenario]) -> RobustnessSweepSummary:
    displacements = [s.max_displacement_mm for s in scenarios if s.max_displacement_mm is not None]
    stresses = [s.max_stress_mpa for s in scenarios if s.max_stress_mpa is not None]
    return RobustnessSweepSummary(
        total_scenarios=len(scenarios),
        stable_scenarios=sum(1 for s in scenarios if s.structural_status == STATUS_STABLE),
        unstable_scenarios=sum(1 for s in scenarios if s.structural_status == STATUS_UNSTABLE),
        failed_check_scenarios=sum(1 for s in scenarios if s.structural_status == STATUS_FAILED_CHECKS),
        max_observed_displacement_mm=max(displacements) if displacements else None,
        max_observed_stress_mpa=max(stresses) if stresses else None,
    )


def run_load_robustness_sweep(
    structure: Structure,
    spec: EngineeringSpec,
    load_index: int = 0,
    scales: list[float] | tuple[float, ...] | None = None,
    combination: LoadCombination | None = None,
) -> RobustnessSweepResult:
    """
    Evaluate `structure` at each load scale via the existing LOAD_SCALE
    perturbation. `structure` is never mutated (run_experiment already
    guarantees this); each scenario is an independent, isolated
    experiment. Raises ValueError immediately (no scenarios run) if
    load_index is invalid — the same validation run_experiment already
    performs, not duplicated here.
    """
    scale_list = list(scales) if scales is not None else list(DEFAULT_LOAD_SCALES)

    scenarios: list[LoadScaleScenario] = []
    for scale in scale_list:
        result = run_experiment(
            structure, spec,
            Perturbation(type=PerturbationType.LOAD_SCALE, load_index=load_index, scale_factor=scale),
            combination=combination,
        )
        scenarios.append(_scenario_from(scale, result))

    return RobustnessSweepResult(
        load_index=load_index,
        scales=scale_list,
        scenarios=scenarios,
        summary=_summarize(scenarios),
    )
