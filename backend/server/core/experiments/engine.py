"""Failure Experiment Engine — apply one perturbation, re-solve, compare.

Deep-copies the baseline Structure, mutates the copy only, and runs both
baseline and perturbed cases through the real solver (server.core.fea.solver.solve).
No parallel physics, no invented numbers.
"""
from __future__ import annotations

import copy

from ...models.structure import Structure, EngineeringSpec, Material, MATERIAL_LIBRARY
from ..fea.solver import solve, FEASolverError
from ..fea.load_cases import LoadCombination
from ..analysis.sensitivity import _thickness_for_area, _solve_with_materials
from .models import Perturbation, PerturbationType, ExperimentResult


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def apply_perturbation(
    structure: Structure, perturbation: Perturbation
) -> tuple[Structure, dict[str, Material] | None]:
    """Return (perturbed structure copy, material override dict or None).

    The original `structure` is never mutated. Raises ValueError for a
    malformed or unresolvable perturbation.
    """
    new_structure = copy.deepcopy(structure)
    material_override: dict[str, Material] | None = None
    p = perturbation

    if p.type is PerturbationType.LOAD_SCALE:
        _require(p.load_index is not None, "load_index is required for LOAD_SCALE")
        _require(p.scale_factor is not None, "scale_factor is required for LOAD_SCALE")
        _require(0 <= p.load_index < len(new_structure.loads),
                 f"load_index {p.load_index} out of range (0..{len(new_structure.loads) - 1})")
        load = new_structure.loads[p.load_index]
        load.fx *= p.scale_factor
        load.fy *= p.scale_factor
        load.fz *= p.scale_factor

    elif p.type is PerturbationType.LOAD_REVERSE:
        _require(p.load_index is not None, "load_index is required for LOAD_REVERSE")
        _require(0 <= p.load_index < len(new_structure.loads),
                 f"load_index {p.load_index} out of range (0..{len(new_structure.loads) - 1})")
        load = new_structure.loads[p.load_index]
        load.fx, load.fy, load.fz = -load.fx, -load.fy, -load.fz

    elif p.type is PerturbationType.MEMBER_AREA_SCALE:
        _require(p.member_id is not None, "member_id is required for MEMBER_AREA_SCALE")
        _require(p.scale_factor is not None, "scale_factor is required for MEMBER_AREA_SCALE")
        member = next((m for m in new_structure.members if m.id == p.member_id), None)
        _require(member is not None, f"member_id {p.member_id} not found")
        # Members may share one CrossSection object — copy before mutating
        # so this doesn't silently change sibling members too.
        member.section = copy.deepcopy(member.section)
        target_area = member.section.area * p.scale_factor
        member.section.wall_thickness = _thickness_for_area(member.section.outer_diameter, target_area)

    elif p.type is PerturbationType.YOUNGS_MODULUS_SCALE:
        _require(p.material_key is not None, "material_key is required for YOUNGS_MODULUS_SCALE")
        _require(p.scale_factor is not None, "scale_factor is required for YOUNGS_MODULUS_SCALE")
        _require(p.material_key in MATERIAL_LIBRARY, f"Unknown material_key '{p.material_key}'")
        original = MATERIAL_LIBRARY[p.material_key]
        material_override = {
            p.material_key: Material(
                key=original.key, name=original.name,
                E=original.E * p.scale_factor,
                yield_stress=original.yield_stress,
                density=original.density,
            )
        }

    elif p.type is PerturbationType.GEOMETRY_OFFSET:
        _require(p.node_id is not None, "node_id is required for GEOMETRY_OFFSET")
        _require(p.offset is not None, "offset is required for GEOMETRY_OFFSET")
        node = next((n for n in new_structure.nodes if n.id == p.node_id), None)
        _require(node is not None, f"node_id {p.node_id} not found")
        dx, dy, dz = p.offset
        node.x += dx
        node.y += dy
        node.z += dz

    elif p.type is PerturbationType.MEMBER_REMOVE:
        _require(p.member_id is not None, "member_id is required for MEMBER_REMOVE")
        remaining = [m for m in new_structure.members if m.id != p.member_id]
        _require(len(remaining) < len(new_structure.members), f"member_id {p.member_id} not found")
        new_structure.members = remaining

    elif p.type is PerturbationType.SUPPORT_REMOVE:
        _require(p.support_node_id is not None, "support_node_id is required for SUPPORT_REMOVE")
        remaining = [s for s in new_structure.supports if s.node_id != p.support_node_id]
        _require(len(remaining) < len(new_structure.supports),
                 f"No support found at node_id {p.support_node_id}")
        new_structure.supports = remaining

    else:
        raise ValueError(f"Unsupported perturbation type: {p.type}")

    return new_structure, material_override


def run_experiment(
    structure: Structure,
    spec: EngineeringSpec,
    perturbation: Perturbation,
    combination: LoadCombination | None = None,
) -> ExperimentResult:
    """Solve baseline, apply one perturbation to a copy, solve that, compare.

    `structure` is never mutated. A perturbed case that fails to solve
    (e.g. SUPPORT_REMOVE creating a mechanism) is captured as
    perturbed_results=None + perturbed_error, not raised.
    """
    baseline_results = solve(structure, spec, combination=combination)

    perturbed_structure, material_override = apply_perturbation(structure, perturbation)

    perturbed_results = None
    perturbed_error = None
    try:
        if material_override is not None:
            perturbed_results = _solve_with_materials(
                perturbed_structure, spec, material_override, combination
            )
        else:
            perturbed_results = solve(perturbed_structure, spec, combination=combination)
    except FEASolverError as e:
        perturbed_error = str(e)

    return ExperimentResult.build(perturbation, baseline_results, perturbed_results, perturbed_error)
