"""
NeuroPlan-3D — Design Space Explorer (Priority 10) and What-If (Priority 11)

Both features rest on the same rule: EVERY number comes from an actual
run of the production solver on an actually-generated structure. Nothing
is interpolated, scaled from a baseline, or estimated from a formula.

────────────────────────────────────────────────────────────────────────
DESIGN SPACE EXPLORER
────────────────────────────────────────────────────────────────────────
Generates candidate structures across a user-chosen parameter grid,
analyses each, and returns a trade-off table.

It deliberately does NOT declare a winner. "Best" depends on what the
engineer is optimising for and on constraints the tool does not know
about — fabrication cost, available sections, transport, erection
sequence, architectural intent. Instead it reports:

  * the full table, so the trade-off is visible;
  * the PARETO-OPTIMAL (non-dominated) subset.

A candidate is dominated when another candidate is at least as good on
EVERY objective and strictly better on at least one. Dominated designs
can be discarded without knowing the engineer's weighting — that is a
mathematical fact, not a preference. Choosing among the non-dominated
set requires a preference, so the tool stops there and leaves it to the
user.

────────────────────────────────────────────────────────────────────────
WHAT-IF
────────────────────────────────────────────────────────────────────────
Runs a baseline and a modified case through the same solver and reports
the deltas, including which member governs and whether the verification
verdict changed. A changed critical member is often more important than
a changed peak number, because it means the load path moved.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from itertools import product

from ...models.structure import (
    Structure, EngineeringSpec, AnalysisResults, StructureType,
    SECTION_CATALOG, MATERIAL_LIBRARY,
)
from ..fea.solver import solve, FEASolverError
from ..fea.load_cases import LoadCombination
from ..generator.topology import generate_structure
from .buckling import screen_structure as buckling_screen, ScreeningStatus


@dataclass
class CandidateMetrics:
    """The comparable outcome of one analysed design."""
    weight_kg: float
    max_stress_mpa: float
    max_displacement_mm: float
    max_stress_ratio: float
    factor_of_safety: float          # fy / max stress; inf when unstressed
    max_buckling_utilisation: float  # from the Euler screening
    member_count: int
    node_count: int
    material_volume_m3: float
    verified: bool


@dataclass
class DesignCandidate:
    candidate_id: str
    structure_type: str
    parameters: dict[str, str]
    metrics: CandidateMetrics | None = None
    failed: bool = False
    failure_reason: str = ""
    pareto_optimal: bool = False


@dataclass
class TradeoffTable:
    candidates: list[DesignCandidate] = field(default_factory=list)
    objectives: list[str] = field(default_factory=lambda: [
        "weight_kg", "max_stress_mpa", "max_displacement_mm",
    ])
    selection_policy: str = (
        "No design is declared 'best'. Dominated candidates are marked "
        "because they can be discarded without knowing your priorities. "
        "Choosing among the non-dominated (Pareto-optimal) set requires a "
        "preference between competing objectives — that is an engineering "
        "judgement, not a computation, and it is left to you."
    )
    n_analysed: int = 0
    n_failed: int = 0

    def successful(self) -> list[DesignCandidate]:
        return [c for c in self.candidates if not c.failed and c.metrics]


def _metrics(structure: Structure, results: AnalysisResults,
             material_key: str) -> CandidateMetrics:
    nodes = structure.node_dict()
    max_stress = max((abs(m.stress) for m in results.member_results), default=0.0)

    material = MATERIAL_LIBRARY.get(material_key)
    fy = material.yield_stress if material else 0.0
    fos = (fy / max_stress) if max_stress > 1e-9 and fy > 0 else float("inf")

    screening = buckling_screen(structure, results.member_results)
    max_buckling = max(
        (m.utilisation for m in screening.members if m.is_compression),
        default=0.0,
    )

    volume = sum(m.section.area * m.length(nodes) for m in structure.members)

    return CandidateMetrics(
        weight_kg=results.total_weight_kg,
        max_stress_mpa=max_stress / 1e6,
        max_displacement_mm=results.diagnosis.max_displacement_mm,
        max_stress_ratio=results.diagnosis.max_stress_ratio,
        factor_of_safety=fos,
        max_buckling_utilisation=max_buckling,
        member_count=len(structure.members),
        node_count=len(structure.nodes),
        material_volume_m3=volume,
        verified=results.diagnosis.passed,
    )


def explore_design_space(
    base_spec: EngineeringSpec,
    structure_types: list[StructureType] | None = None,
    panel_counts: list[int] | None = None,
    heights: list[float] | None = None,
    section_keys: list[str] | None = None,
    combination: LoadCombination | None = None,
) -> TradeoffTable:
    """
    Build and analyse the cartesian product of the supplied variations.

    A candidate that cannot be generated or solved is recorded as FAILED
    with its reason — never dropped silently, since a failing region of
    the design space is itself information.
    """
    structure_types = structure_types or [base_spec.structure_type]
    panel_counts = panel_counts or [base_spec.num_panels]
    heights = heights or [base_spec.height]
    section_keys = section_keys or [base_spec.section_key]

    table = TradeoffTable()

    for stype, panels, height, section_key in product(
        structure_types, panel_counts, heights, section_keys
    ):
        spec = copy.deepcopy(base_spec)
        spec.structure_type = stype
        spec.num_panels = panels
        spec.height = height
        spec.section_key = section_key
        # Spatial types need a non-zero width; carry the base value or
        # derive a sensible one rather than generating an invalid model.
        if stype is StructureType.SPACE_TRUSS and spec.width <= 0:
            spec.width = max(base_spec.width, height)

        candidate = DesignCandidate(
            candidate_id=f"{stype.value}-p{panels}-h{height:g}-{section_key}",
            structure_type=stype.value,
            parameters={
                "panels": str(panels),
                "height_m": f"{height:g}",
                "section": section_key,
                "span_m": f"{spec.span:g}",
            },
        )

        try:
            structure = generate_structure(spec)
            if section_key in SECTION_CATALOG:
                section = SECTION_CATALOG[section_key]
                for member in structure.members:
                    member.section = copy.deepcopy(section)
            results = solve(structure, spec, combination=combination)
            candidate.metrics = _metrics(structure, results, spec.material_key)
            table.n_analysed += 1
        except (FEASolverError, ValueError, KeyError, ArithmeticError,
                IndexError) as e:
            candidate.failed = True
            candidate.failure_reason = str(e).split("\n")[0][:300]
            table.n_failed += 1

        table.candidates.append(candidate)

    _mark_pareto_optimal(table)
    return table


# Two objective values closer than this (relatively) are treated as
# equal. Without it, Pareto status gets decided by floating-point noise:
# three topologies that are mathematically identical in peak stress
# differed in the 14th significant figure, and the one that happened to
# round down escaped domination — presenting a meaningless design to the
# user as a genuine trade-off. 1e-9 sits far above float64 round-off
# (~1e-16) and far below any difference an engineer would act on.
PARETO_RELATIVE_TOLERANCE = 1e-9


def _is_better(b: float, a: float) -> bool:
    """b is meaningfully lower than a (objectives are minimised)."""
    return b < a - PARETO_RELATIVE_TOLERANCE * max(abs(a), abs(b), 1.0)


def _is_not_worse(b: float, a: float) -> bool:
    return b <= a + PARETO_RELATIVE_TOLERANCE * max(abs(a), abs(b), 1.0)


def _mark_pareto_optimal(table: TradeoffTable) -> None:
    """
    Mark non-dominated candidates.

    Candidate B dominates A when B is no worse than A on every objective
    (all are minimised) and meaningfully better on at least one, both
    judged within PARETO_RELATIVE_TOLERANCE.
    """
    entries = table.successful()
    for candidate in entries:
        dominated = False
        for other in entries:
            if other is candidate:
                continue
            a = [getattr(candidate.metrics, o) for o in table.objectives]
            b = [getattr(other.metrics, o) for o in table.objectives]
            if (all(_is_not_worse(x, y) for x, y in zip(b, a))
                    and any(_is_better(x, y) for x, y in zip(b, a))):
                dominated = True
                break
        candidate.pareto_optimal = not dominated


# ─────────────────────────────────────────────
# Priority 11 — What-If
# ─────────────────────────────────────────────

class WhatIfParameter(str, Enum):
    PRIMARY_LOAD = "primary_load"
    LATERAL_LOAD_X = "lateral_load_x"
    LATERAL_LOAD_Z = "lateral_load_z"
    MATERIAL = "material"
    SECTION = "section"
    SPAN = "span"
    HEIGHT = "height"
    WIDTH = "width"
    STRUCTURE_TYPE = "structure_type"
    NUM_PANELS = "num_panels"


@dataclass
class MetricDelta:
    name: str
    baseline: float
    modified: float
    absolute_change: float
    percent_change: float | None
    unit: str = ""


@dataclass
class WhatIfResult:
    changes: dict[str, str]
    deltas: list[MetricDelta] = field(default_factory=list)
    baseline_critical_member: int | None = None
    modified_critical_member: int | None = None
    critical_member_changed: bool = False
    baseline_verified: bool = False
    modified_verified: bool = False
    verification_changed: bool = False
    baseline_reaction_total_n: float = 0.0
    modified_reaction_total_n: float = 0.0
    failed: bool = False
    failure_reason: str = ""
    provenance: str = (
        "Both the baseline and the modified case were produced by a full "
        "run of the production solver. No value is scaled or extrapolated."
    )


def _critical_member(results: AnalysisResults) -> int | None:
    worst, worst_id = -1.0, None
    for member in results.member_results:
        if abs(member.stress) > worst:
            worst, worst_id = abs(member.stress), member.member_id
    return worst_id


def _apply_change(spec: EngineeringSpec, parameter: WhatIfParameter, value) -> None:
    if parameter is WhatIfParameter.PRIMARY_LOAD:
        spec.primary_load = float(value)
    elif parameter is WhatIfParameter.LATERAL_LOAD_X:
        spec.lateral_load_x = float(value)
    elif parameter is WhatIfParameter.LATERAL_LOAD_Z:
        spec.lateral_load_z = float(value)
    elif parameter is WhatIfParameter.MATERIAL:
        if value not in MATERIAL_LIBRARY:
            raise ValueError(f"Unknown material '{value}'")
        spec.material_key = str(value)
    elif parameter is WhatIfParameter.SECTION:
        if value not in SECTION_CATALOG:
            raise ValueError(f"Unknown section '{value}'")
        spec.section_key = str(value)
    elif parameter is WhatIfParameter.SPAN:
        spec.span = float(value)
    elif parameter is WhatIfParameter.HEIGHT:
        spec.height = float(value)
    elif parameter is WhatIfParameter.WIDTH:
        spec.width = float(value)
    elif parameter is WhatIfParameter.NUM_PANELS:
        spec.num_panels = int(value)
    elif parameter is WhatIfParameter.STRUCTURE_TYPE:
        spec.structure_type = StructureType(value)


def _build_and_solve(spec: EngineeringSpec, combination: LoadCombination | None):
    structure = generate_structure(spec)
    if spec.section_key in SECTION_CATALOG:
        section = SECTION_CATALOG[spec.section_key]
        for member in structure.members:
            member.section = copy.deepcopy(section)
    for member in structure.members:
        member.material_key = spec.material_key
    return structure, solve(structure, spec, combination=combination)


def run_what_if(
    base_spec: EngineeringSpec,
    changes: dict[WhatIfParameter, object],
    combination: LoadCombination | None = None,
) -> WhatIfResult:
    """Run baseline vs modified and report every delta from real solves."""
    if not changes:
        raise ValueError("what-if requires at least one parameter change")

    modified_spec = copy.deepcopy(base_spec)
    for parameter, value in changes.items():
        _apply_change(modified_spec, parameter, value)

    result = WhatIfResult(
        changes={p.value: str(v) for p, v in changes.items()},
    )

    try:
        base_structure, base_results = _build_and_solve(
            copy.deepcopy(base_spec), combination)
        mod_structure, mod_results = _build_and_solve(modified_spec, combination)
    except (FEASolverError, KeyError, ArithmeticError, IndexError) as e:
        result.failed = True
        result.failure_reason = str(e).split("\n")[0][:300]
        return result

    base_metrics = _metrics(base_structure, base_results, base_spec.material_key)
    mod_metrics = _metrics(mod_structure, mod_results, modified_spec.material_key)

    for name, unit in (
        ("max_stress_mpa", "MPa"),
        ("max_displacement_mm", "mm"),
        ("max_stress_ratio", "-"),
        ("weight_kg", "kg"),
        ("max_buckling_utilisation", "-"),
        ("member_count", "-"),
    ):
        before = float(getattr(base_metrics, name))
        after = float(getattr(mod_metrics, name))
        percent = ((after - before) / abs(before) * 100.0) if abs(before) > 1e-12 else None
        result.deltas.append(MetricDelta(
            name=name, baseline=before, modified=after,
            absolute_change=after - before, percent_change=percent, unit=unit,
        ))

    result.baseline_critical_member = _critical_member(base_results)
    result.modified_critical_member = _critical_member(mod_results)
    result.critical_member_changed = (
        result.baseline_critical_member != result.modified_critical_member
    )

    result.baseline_verified = base_results.diagnosis.passed
    result.modified_verified = mod_results.diagnosis.passed
    result.verification_changed = result.baseline_verified != result.modified_verified

    result.baseline_reaction_total_n = sum(
        (r.rx ** 2 + r.ry ** 2 + r.rz ** 2) ** 0.5 for r in base_results.reactions
    )
    result.modified_reaction_total_n = sum(
        (r.rx ** 2 + r.ry ** 2 + r.rz ** 2) ** 0.5 for r in mod_results.reactions
    )

    return result
