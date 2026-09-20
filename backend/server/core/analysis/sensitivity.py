"""
NeuroPlan-3D — Deterministic Sensitivity Analysis (Priority 4)

WHAT THIS IS
────────────────────────────────────────────────────────────────────────
A one-at-a-time (OAT) perturbation study. Each input parameter is moved
by a stated amount, the FULL production solver is re-run, and the change
in each output is recorded. It answers:

    "If this input were wrong by +/-10%, how wrong would the answer be?"

WHAT THIS IS NOT
────────────────────────────────────────────────────────────────────────
This is NOT a statistical uncertainty analysis and must never be
presented as one. The distinction is not pedantic:

  SENSITIVITY (what we do)
      Deterministic. Perturbs inputs by chosen amounts. Requires no
      knowledge of how the inputs are actually distributed. Produces a
      RANGE and a ranking of influence.

  STATISTICAL UNCERTAINTY (what we do NOT do)
      Requires a probability distribution for every input — mean,
      variance, and correlations — obtained from measurement or a
      published characterisation. Produces a confidence interval with a
      stated coverage probability (e.g. "95% CI").

Because no input here has a characterised distribution, the output has
NO confidence level. The range below is "what happens across the
perturbations I chose", not "where the true value lies with 95%
probability". Reporting the former as the latter would be fabricating a
statistical claim from non-statistical evidence.

A further limitation of OAT: it varies one parameter at a time, so it
cannot see interaction effects. If two parameters only matter jointly,
OAT will under-report both. This is stated in the result rather than
hidden.

METHOD
────────────────────────────────────────────────────────────────────────
For parameter p with baseline value p0 and relative perturbation delta:

    p_minus = p0 * (1 - delta)
    p_plus  = p0 * (1 + delta)

Each is applied to a deep copy of the model, solved, and the outputs
recorded. The reported sensitivity of output y to parameter p is the
normalised local slope

    S = (dy / y0) / (dp / p0)

evaluated by central difference:

    S ~ ((y_plus - y_minus) / y0) / (2 * delta)

S = 1 means "a 1% change in this input produces a 1% change in this
output". S is dimensionless, so parameters in different units can be
ranked against each other, which is what makes the dominant-parameter
ranking meaningful.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from enum import Enum

from ...models.structure import (
    Structure, EngineeringSpec, AnalysisResults, MATERIAL_LIBRARY, Material,
)
from ..fea.solver import solve, FEASolverError
from ..fea.load_cases import LoadCombination

DEFAULT_PERTURBATION = 0.10  # +/-10%


class SensitivityParameter(str, Enum):
    LOAD = "load"
    YOUNGS_MODULUS = "youngs_modulus"
    CROSS_SECTION_AREA = "cross_section_area"
    GEOMETRY_HEIGHT = "geometry_height"
    MATERIAL_DENSITY = "material_density"


PARAMETER_LABELS: dict[SensitivityParameter, str] = {
    SensitivityParameter.LOAD: "Applied load magnitude",
    SensitivityParameter.YOUNGS_MODULUS: "Young's modulus E",
    SensitivityParameter.CROSS_SECTION_AREA: "Cross-sectional area",
    SensitivityParameter.GEOMETRY_HEIGHT: "Truss height (structural depth)",
    SensitivityParameter.MATERIAL_DENSITY: "Material density",
}


@dataclass
class OutputMetrics:
    """The scalar outputs tracked across perturbations."""
    max_stress_mpa: float
    max_displacement_mm: float
    max_stress_ratio: float
    total_weight_kg: float
    max_reaction_n: float

    @staticmethod
    def names() -> list[str]:
        return ["max_stress_mpa", "max_displacement_mm", "max_stress_ratio",
                "total_weight_kg", "max_reaction_n"]

    def get(self, name: str) -> float:
        return getattr(self, name)


@dataclass
class ParameterSensitivity:
    parameter: SensitivityParameter
    label: str
    baseline_value: float
    perturbation: float
    low_value: float
    high_value: float
    # output name -> (low, baseline, high, change_pct, normalised_slope)
    outputs: dict[str, "OutputSensitivity"] = field(default_factory=dict)
    failed: bool = False
    failure_reason: str = ""


@dataclass
class OutputSensitivity:
    output_name: str
    baseline: float
    minimum: float
    maximum: float
    change_percent: float        # (max - min) / |baseline| * 100
    normalised_slope: float      # dimensionless S


@dataclass
class SensitivityReport:
    baseline: OutputMetrics
    perturbation: float
    parameters: list[ParameterSensitivity] = field(default_factory=list)
    dominant: dict[str, str] = field(default_factory=dict)   # output -> parameter label
    method: str = (
        "One-at-a-time (OAT) deterministic perturbation. Each parameter is "
        "scaled by +/-{pct:.0f}% and the full production solver is re-run."
    )
    is_statistical: bool = False
    statistical_disclaimer: str = (
        "THIS IS A SENSITIVITY RANGE, NOT A CONFIDENCE INTERVAL. No input "
        "has a characterised probability distribution, so no coverage "
        "probability can be attached to this range. It shows what happens "
        "across the perturbations actually applied — nothing more."
    )
    interaction_limitation: str = (
        "One-at-a-time perturbation cannot detect interaction effects. "
        "Parameters that matter only in combination will be under-reported."
    )


def _extract(results: AnalysisResults) -> OutputMetrics:
    max_reaction = 0.0
    for r in results.reactions:
        magnitude = (r.rx ** 2 + r.ry ** 2 + r.rz ** 2) ** 0.5
        max_reaction = max(max_reaction, magnitude)
    max_stress_mpa = max(
        (abs(m.stress) for m in results.member_results), default=0.0
    ) / 1e6
    return OutputMetrics(
        max_stress_mpa=max_stress_mpa,
        max_displacement_mm=results.diagnosis.max_displacement_mm,
        max_stress_ratio=results.diagnosis.max_stress_ratio,
        total_weight_kg=results.total_weight_kg,
        max_reaction_n=max_reaction,
    )


def _scaled_material_library(scale_e: float = 1.0, scale_density: float = 1.0):
    """A copy of the material library with E and/or density scaled."""
    return {
        key: Material(
            key=m.key, name=m.name,
            E=m.E * scale_e,
            yield_stress=m.yield_stress,
            density=m.density * scale_density,
        )
        for key, m in MATERIAL_LIBRARY.items()
    }


def _thickness_for_area(outer_diameter: float, target_area: float) -> float:
    """
    Wall thickness of a CHS giving exactly `target_area`.

        A = pi * (r^2 - (r - t)^2) = pi * (2rt - t^2)

    Solving the quadratic t^2 - 2rt + A/pi = 0 for the physical root
    (t < r):

        t = r - sqrt(r^2 - A/pi)

    Scaling thickness directly would NOT scale area proportionally (area
    is quadratic in t), so the reported "10% area change" would be a lie.
    """
    r = outer_diameter / 2.0
    discriminant = r * r - target_area / math.pi
    if discriminant < 0:
        raise ValueError("target area exceeds that of a solid section")
    return r - math.sqrt(discriminant)


def _apply_perturbation(
    structure: Structure,
    spec: EngineeringSpec,
    parameter: SensitivityParameter,
    scale: float,
) -> tuple[Structure, EngineeringSpec, dict | None]:
    """
    Return a perturbed (structure, spec, material_override).

    Geometry perturbation regenerates the structure from the modified
    spec — scaling node coordinates directly would produce a model the
    generator would never have produced.
    """
    s = copy.deepcopy(structure)
    sp = copy.deepcopy(spec)
    materials = None

    if parameter is SensitivityParameter.LOAD:
        for load in s.loads:
            load.fx *= scale
            load.fy *= scale
            load.fz *= scale
        sp.primary_load *= scale

    elif parameter is SensitivityParameter.YOUNGS_MODULUS:
        materials = _scaled_material_library(scale_e=scale)

    elif parameter is SensitivityParameter.CROSS_SECTION_AREA:
        # Members commonly SHARE one CrossSection object, so each unique
        # section must be adjusted exactly once. Scaling per-member would
        # compound the change once per member (scale^n).
        for section in {id(m.section): m.section for m in s.members}.values():
            target = section.area * scale
            section.wall_thickness = _thickness_for_area(section.outer_diameter, target)

    elif parameter is SensitivityParameter.GEOMETRY_HEIGHT:
        from ..generator.topology import generate_structure
        sp.height = spec.height * scale
        s = generate_structure(sp)

    elif parameter is SensitivityParameter.MATERIAL_DENSITY:
        materials = _scaled_material_library(scale_density=scale)

    return s, sp, materials


def _solve_with_materials(
    structure: Structure,
    spec: EngineeringSpec,
    materials: dict | None,
    combination: LoadCombination | None,
) -> AnalysisResults:
    """
    Run the real solver, temporarily swapping the material library when a
    material property is being perturbed.

    The swap is done around the call and always restored, so a perturbed
    run cannot leak into subsequent analyses.
    """
    if materials is None:
        return solve(structure, spec, combination=combination)

    # Mutate the shared dict IN PLACE rather than rebinding module-level
    # names. Every module that did `from ... import MATERIAL_LIBRARY` holds
    # a reference to this same dict object, so an in-place change reaches
    # all of them — including elements.py, which computes the stiffness E
    # and would be missed by any hand-maintained list of modules to patch.
    original = dict(MATERIAL_LIBRARY)
    try:
        MATERIAL_LIBRARY.update(materials)
        return solve(structure, spec, combination=combination)
    finally:
        MATERIAL_LIBRARY.clear()
        MATERIAL_LIBRARY.update(original)


def run_sensitivity(
    structure: Structure,
    spec: EngineeringSpec,
    perturbation: float = DEFAULT_PERTURBATION,
    parameters: list[SensitivityParameter] | None = None,
    combination: LoadCombination | None = None,
) -> SensitivityReport:
    """
    Perturb each parameter by +/-`perturbation` and re-solve.

    Every number reported comes from an actual solver run — nothing is
    extrapolated from the baseline.
    """
    if not 0.0 < perturbation < 1.0:
        raise ValueError("perturbation must be a fraction strictly between 0 and 1")

    if parameters is None:
        parameters = list(SensitivityParameter)

    baseline_results = solve(structure, spec, combination=combination)
    baseline = _extract(baseline_results)

    report = SensitivityReport(
        baseline=baseline,
        perturbation=perturbation,
        method=SensitivityReport.method.format(pct=perturbation * 100),
    )

    for parameter in parameters:
        entry = ParameterSensitivity(
            parameter=parameter,
            label=PARAMETER_LABELS[parameter],
            baseline_value=_baseline_value(structure, spec, parameter),
            perturbation=perturbation,
            low_value=_baseline_value(structure, spec, parameter) * (1 - perturbation),
            high_value=_baseline_value(structure, spec, parameter) * (1 + perturbation),
        )

        try:
            low_s, low_sp, low_mat = _apply_perturbation(
                structure, spec, parameter, 1.0 - perturbation)
            high_s, high_sp, high_mat = _apply_perturbation(
                structure, spec, parameter, 1.0 + perturbation)
            low = _extract(_solve_with_materials(low_s, low_sp, low_mat, combination))
            high = _extract(_solve_with_materials(high_s, high_sp, high_mat, combination))
        except (FEASolverError, ValueError, KeyError) as e:
            entry.failed = True
            entry.failure_reason = (
                f"The perturbed model could not be solved: {e}. This "
                f"parameter's sensitivity is reported as UNAVAILABLE rather "
                f"than estimated."
            )
            report.parameters.append(entry)
            continue

        for name in OutputMetrics.names():
            b = baseline.get(name)
            lo, hi = low.get(name), high.get(name)
            minimum, maximum = min(lo, hi), max(lo, hi)
            denominator = abs(b) if abs(b) > 1e-12 else 1.0
            change_pct = (maximum - minimum) / denominator * 100.0
            slope = ((hi - lo) / denominator) / (2.0 * perturbation)
            entry.outputs[name] = OutputSensitivity(
                output_name=name,
                baseline=b,
                minimum=minimum,
                maximum=maximum,
                change_percent=change_pct,
                normalised_slope=slope,
            )

        report.parameters.append(entry)

    _rank_dominant(report)
    return report


def _baseline_value(
    structure: Structure, spec: EngineeringSpec, parameter: SensitivityParameter
) -> float:
    if parameter is SensitivityParameter.LOAD:
        return spec.primary_load
    if parameter is SensitivityParameter.YOUNGS_MODULUS:
        return MATERIAL_LIBRARY[spec.material_key].E
    if parameter is SensitivityParameter.CROSS_SECTION_AREA:
        return structure.members[0].section.area if structure.members else 0.0
    if parameter is SensitivityParameter.GEOMETRY_HEIGHT:
        return spec.height
    if parameter is SensitivityParameter.MATERIAL_DENSITY:
        return MATERIAL_LIBRARY[spec.material_key].density
    return 0.0


def _rank_dominant(report: SensitivityReport) -> None:
    """
    For each output, name the parameter with the largest |normalised slope|.

    Ranking uses the dimensionless slope rather than the raw change, so
    parameters measured in newtons, pascals and metres are comparable.
    """
    for name in OutputMetrics.names():
        best_label, best_slope = None, 0.0
        for entry in report.parameters:
            if entry.failed or name not in entry.outputs:
                continue
            slope = abs(entry.outputs[name].normalised_slope)
            if slope > best_slope:
                best_label, best_slope = entry.label, slope
        if best_label is not None and best_slope > 1e-9:
            report.dominant[name] = best_label
