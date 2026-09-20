"""
NeuroPlan-3D — Repair Engine

Implements bounded, rule-based structural repair.
NOT an optimizer — applies engineering-motivated corrections.

Repair loop:
1. Diagnose failures from FEA results
2. Select appropriate repair strategy based on failure type
3. Apply repair (modify structure parameters)
4. Re-run FEA
5. Repeat until pass OR budget exhausted OR no improvement

Termination conditions:
- All constraints satisfied → PASS
- Max iterations reached → best-effort result
- No improvement in 2 consecutive iterations → early stop
- Structure becomes infeasible → report infeasibility
"""
import copy
import math
from dataclasses import dataclass

from ...models.structure import (
    Structure, EngineeringSpec, AnalysisResults,
    FailureDiagnosis, FailureInfo, FailureType,
    RepairAction, RepairStrategy, IterationResult,
    CrossSection, MATERIAL_LIBRARY,
)
from ..fea.solver import solve, FEASolverError
from ...config import (
    MAX_REPAIR_ITERATIONS,
    MAX_AREA_INCREASE_FACTOR,
    MAX_HEIGHT_INCREASE_FACTOR,
)


@dataclass
class RepairBudget:
    max_iterations: int = MAX_REPAIR_ITERATIONS
    max_area_increase_factor: float = MAX_AREA_INCREASE_FACTOR
    max_height_increase_factor: float = MAX_HEIGHT_INCREASE_FACTOR
    current_iteration: int = 0
    initial_max_area: float = 0.0
    initial_height: float = 0.0

    def is_exhausted(self) -> bool:
        return self.current_iteration >= self.max_iterations


def _select_strategy(
    diagnosis: FailureDiagnosis,
    structure: Structure,
    budget: RepairBudget,
    spec: EngineeringSpec,
) -> tuple[RepairStrategy, FailureInfo] | None:
    """
    Select the most appropriate repair strategy for the worst failure.

    Strategy selection matrix:
    - Stress exceeded → increase section area of that member
    - Displacement exceeded → increase truss height
    - Buckling risk → increase section area (increases I)

    Returns:
        (strategy, target_failure) or None if no repair applicable
    """
    if not diagnosis.failures:
        return None

    worst = diagnosis.failures[0]  # Already sorted by severity

    if worst.failure_type == FailureType.STRESS_EXCEEDED:
        # Check if we can still increase area
        if worst.member_id is not None:
            member = None
            for m in structure.members:
                if m.id == worst.member_id:
                    member = m
                    break
            if member and member.section.area < budget.initial_max_area * budget.max_area_increase_factor:
                return (RepairStrategy.INCREASE_SECTION, worst)

        # Fallback: increase height if area budget is exhausted
        current_height = _get_truss_height(structure)
        if current_height < budget.initial_height * budget.max_height_increase_factor:
            return (RepairStrategy.INCREASE_HEIGHT, worst)

    elif worst.failure_type == FailureType.DISPLACEMENT_EXCEEDED:
        # Primary: increase height (stiffens truss)
        current_height = _get_truss_height(structure)
        if current_height < budget.initial_height * budget.max_height_increase_factor:
            return (RepairStrategy.INCREASE_HEIGHT, worst)

        # Fallback: increase all member sections
        return (RepairStrategy.INCREASE_SECTION, worst)

    elif worst.failure_type == FailureType.BUCKLING_RISK:
        # Increase section to raise moment of inertia
        if worst.member_id is not None:
            return (RepairStrategy.INCREASE_SECTION, worst)

    return None


def _apply_section_increase(
    structure: Structure,
    failure: FailureInfo,
    diagnosis: FailureDiagnosis,
) -> RepairAction | None:
    """
    Increase the cross-section of overstressed members.

    Scale factor = sqrt(stress_ratio) * 1.1 to overshoot slightly
    and converge faster.
    """
    if failure.member_id is None:
        return None

    # Find all overstressed members and increase them
    repaired_ids = []
    for f in diagnosis.failures:
        if f.failure_type in (FailureType.STRESS_EXCEEDED, FailureType.BUCKLING_RISK):
            if f.member_id is not None:
                for member in structure.members:
                    if member.id == f.member_id:
                        old_od = member.section.outer_diameter
                        # Scale factor based on stress ratio
                        scale = math.sqrt(f.ratio) * 1.1
                        scale = min(scale, 1.5)  # cap single-step increase
                        scale = max(scale, 1.05)  # minimum meaningful increase
                        member.section = member.section.scaled(scale)
                        repaired_ids.append(member.id)
                        break

    if not repaired_ids:
        return None

    target_member = None
    for m in structure.members:
        if m.id == failure.member_id:
            target_member = m
            break

    old_area = failure.actual_value  # stress as proxy
    new_area = target_member.section.area if target_member else 0

    return RepairAction(
        iteration=0,  # set by caller
        strategy=RepairStrategy.INCREASE_SECTION,
        target_description=f"Members {repaired_ids}",
        parameter_changed="section_outer_diameter",
        old_value=round(old_area, 6),
        new_value=round(new_area, 6),
        rationale=f"Stress ratio {failure.ratio:.2f} > 1.0 on member {failure.member_id}",
    )


def _apply_height_increase(
    structure: Structure,
    failure: FailureInfo,
) -> RepairAction | None:
    """
    Increase the height of the truss by raising top chord nodes.

    Scale factor = 1.15 per iteration (15% height increase).
    """
    old_height = _get_truss_height(structure)
    scale = 1.15

    # Find top chord nodes (highest y-coordinate nodes)
    max_y = max(n.y for n in structure.nodes)
    if max_y < 1e-6:
        return None

    for node in structure.nodes:
        if abs(node.y - max_y) < 1e-6:
            node.y *= scale

    new_height = _get_truss_height(structure)

    return RepairAction(
        iteration=0,
        strategy=RepairStrategy.INCREASE_HEIGHT,
        target_description="Top chord nodes",
        parameter_changed="truss_height",
        old_value=round(old_height, 4),
        new_value=round(new_height, 4),
        rationale=f"{'Displacement' if failure.failure_type == FailureType.DISPLACEMENT_EXCEEDED else 'Stress'} "
                  f"ratio {failure.ratio:.2f} — increasing height to stiffen truss",
    )


def _get_truss_height(structure: Structure) -> float:
    """Get the current height of the truss (max_y - min_y)."""
    if not structure.nodes:
        return 0.0
    ys = [n.y for n in structure.nodes]
    return max(ys) - min(ys)


def run_repair_loop(
    structure: Structure,
    spec: EngineeringSpec,
    initial_results: AnalysisResults,
) -> list[IterationResult]:
    """
    Run the bounded repair loop.

    Parameters:
        structure: Initial structure (will be modified in place via deep copies)
        spec: Engineering specification
        initial_results: Results from the initial FEA run

    Returns:
        List of all iteration results (including initial)
    """
    iterations: list[IterationResult] = []

    # Record initial iteration
    iterations.append(IterationResult(
        iteration_number=0,
        structure=copy.deepcopy(structure),
        results=initial_results,
        repair_action=None,
    ))

    if initial_results.diagnosis.passed:
        return iterations

    # Initialize budget
    max_area = max(m.section.area for m in structure.members) if structure.members else 0
    budget = RepairBudget(
        initial_max_area=max_area,
        initial_height=_get_truss_height(structure),
    )

    # Track improvement for early stopping
    prev_max_ratio = initial_results.diagnosis.max_stress_ratio
    no_improvement_count = 0

    current_structure = copy.deepcopy(structure)

    while not budget.is_exhausted():
        budget.current_iteration += 1
        iteration_num = budget.current_iteration

        # Get latest diagnosis
        latest = iterations[-1].results.diagnosis

        # Select strategy
        strategy_result = _select_strategy(latest, current_structure, budget, spec)
        if strategy_result is None:
            break  # No applicable strategy

        strategy, target_failure = strategy_result

        # Apply repair
        if strategy == RepairStrategy.INCREASE_SECTION:
            action = _apply_section_increase(current_structure, target_failure, latest)
        elif strategy == RepairStrategy.INCREASE_HEIGHT:
            action = _apply_height_increase(current_structure, target_failure)
        else:
            break

        if action is None:
            break

        action.iteration = iteration_num

        # Re-run FEA
        try:
            new_results = solve(current_structure, spec)
        except FEASolverError:
            break  # Structure became infeasible

        iterations.append(IterationResult(
            iteration_number=iteration_num,
            structure=copy.deepcopy(current_structure),
            results=new_results,
            repair_action=action,
        ))

        # Check if passed
        if new_results.diagnosis.passed:
            break

        # Check for improvement
        current_ratio = new_results.diagnosis.max_stress_ratio
        if current_ratio >= prev_max_ratio - 0.01:
            no_improvement_count += 1
        else:
            no_improvement_count = 0

        if no_improvement_count >= 2:
            break  # No improvement in 2 consecutive iterations

        prev_max_ratio = current_ratio

    return iterations
