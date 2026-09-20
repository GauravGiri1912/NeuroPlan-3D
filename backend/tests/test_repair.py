"""
NeuroPlan-3D — Repair Engine Tests

test_solver.py already covers one end-to-end repair-loop convergence case.
This file covers the strategy-selection logic directly and the iteration
budget, which had zero coverage before.
"""
import pytest

from server.models.structure import (
    EngineeringSpec, StructureType, FailureDiagnosis, FailureInfo, FailureType,
    RepairStrategy,
)
from server.core.generator.topology import generate_structure
from server.core.fea.solver import solve
from server.core.repair.engine import _select_strategy, RepairBudget, run_repair_loop
from server.config import MAX_REPAIR_ITERATIONS


def _budget(structure) -> RepairBudget:
    max_area = max(m.section.area for m in structure.members)
    ys = [n.y for n in structure.nodes]
    return RepairBudget(initial_max_area=max_area, initial_height=max(ys) - min(ys))


def test_select_strategy_for_stress_exceeded_increases_section():
    spec = EngineeringSpec(structure_type=StructureType.PRATT, span=20.0, height=3.33, num_panels=6)
    structure = generate_structure(spec)
    budget = _budget(structure)

    failure = FailureInfo(failure_type=FailureType.STRESS_EXCEEDED, member_id=structure.members[0].id, ratio=1.5)
    diagnosis = FailureDiagnosis(passed=False, failures=[failure])

    result = _select_strategy(diagnosis, structure, budget, spec)
    assert result is not None
    strategy, target = result
    assert strategy == RepairStrategy.INCREASE_SECTION
    assert target is failure


def test_select_strategy_for_displacement_exceeded_increases_height():
    spec = EngineeringSpec(structure_type=StructureType.PRATT, span=20.0, height=3.33, num_panels=6)
    structure = generate_structure(spec)
    budget = _budget(structure)

    failure = FailureInfo(failure_type=FailureType.DISPLACEMENT_EXCEEDED, node_id=structure.nodes[0].id, ratio=1.2)
    diagnosis = FailureDiagnosis(passed=False, failures=[failure])

    result = _select_strategy(diagnosis, structure, budget, spec)
    assert result is not None
    strategy, _ = result
    assert strategy == RepairStrategy.INCREASE_HEIGHT


def test_select_strategy_returns_none_when_no_failures():
    spec = EngineeringSpec(structure_type=StructureType.PRATT, span=20.0, height=3.33, num_panels=6)
    structure = generate_structure(spec)
    budget = _budget(structure)

    diagnosis = FailureDiagnosis(passed=True, failures=[])
    assert _select_strategy(diagnosis, structure, budget, spec) is None


def test_repair_loop_works_on_spatial_structures_without_corrupting_geometry():
    """
    Phase 13: the existing repair strategies are dimension-agnostic —
    `increase_section` scales member areas, and `increase_height` scales only
    the top-chord y coordinates. Both are mathematically valid for a space
    truss, so no spatial-specific strategy is needed. What must NOT happen is
    the repair flattening or distorting the z geometry.
    """
    spec = EngineeringSpec(
        structure_type=StructureType.SPACE_TRUSS,
        span=36.0, height=1.8, width=3.5, num_panels=6,
        primary_load=400_000.0, section_key="CHS_76x3.2",
    )
    structure = generate_structure(spec)
    initial = solve(structure, spec)
    assert initial.diagnosis.passed is False

    iterations = run_repair_loop(structure, spec, initial)
    assert len(iterations) > 1

    final = iterations[-1]
    # Still genuinely spatial, with the original width preserved exactly.
    assert final.results.is_spatial is True
    z_values = {round(n.z, 6) for n in final.structure.nodes}
    assert z_values == {-1.75, 1.75}  # ±width/2, preserved exactly through repair
    # Equilibrium must hold at every single iteration, not just the last.
    for it in iterations:
        assert it.results.equilibrium.passed, f"equilibrium lost at iteration {it.iteration_number}"
    # And the repair actually improved the structure.
    assert final.results.diagnosis.max_stress_ratio < initial.diagnosis.max_stress_ratio


def test_repair_loop_respects_max_iteration_budget():
    """
    A structure with an extremely tiny section and a huge load should never
    converge within the iteration cap — the loop must stop at
    MAX_REPAIR_ITERATIONS rather than looping forever.
    """
    spec = EngineeringSpec(
        structure_type=StructureType.PRATT,
        span=40.0, height=1.0, num_panels=6,
        primary_load=5_000_000.0, material_key="A36", section_key="CHS_76x3.2",
    )
    structure = generate_structure(spec)
    initial_results = solve(structure, spec)
    assert initial_results.diagnosis.passed is False

    iterations = run_repair_loop(structure, spec, initial_results)
    # iteration 0 is the initial (unrepaired) result, so at most
    # MAX_REPAIR_ITERATIONS repair attempts follow it.
    assert len(iterations) <= MAX_REPAIR_ITERATIONS + 1
