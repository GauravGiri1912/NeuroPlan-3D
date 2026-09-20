"""
NeuroPlan-3D — CPU Solver Benchmark

Measures real solve times across structure sizes so the GPU-acceleration
question (NVIDIA Warp) can be answered with data instead of vibes.

Run:  python tools/benchmark_solver.py
"""
import sys
import pathlib
import time
import statistics

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from server.models.structure import EngineeringSpec, StructureType
from server.core.generator.topology import generate_structure
from server.core.fea.solver import solve
from server.core.fea.assembly import assemble_global_stiffness, build_load_vector
from server.core.fea.boundary import get_constrained_dofs


def bench_case(label: str, spec: EngineeringSpec, repeats: int = 5) -> dict:
    structure = generate_structure(spec)
    n_nodes = len(structure.nodes)
    n_members = len(structure.members)
    n_dof = 3 * n_nodes

    # Full pipeline (assembly + BC + solve + postprocess + checks)
    full_times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        results = solve(structure, spec)
        full_times.append((time.perf_counter() - t0) * 1000)

    # Stage breakdown, using the same code path the solver actually takes.
    assembly_times, factor_solve_times = [], []
    for _ in range(repeats):
        t0 = time.perf_counter()
        K, dof_map = assemble_global_stiffness(structure)
        F = build_load_vector(structure, dof_map)
        assembly_times.append((time.perf_counter() - t0) * 1000)

        constrained = get_constrained_dofs(structure.supports, dof_map)
        free = np.setdiff1d(np.arange(len(F)), np.asarray(constrained, dtype=int))
        K_ff = K[np.ix_(free, free)]
        F_f = F[free]

        t0 = time.perf_counter()
        cho = cho_factor(K_ff, lower=True, check_finite=False)
        cho_solve(cho, F_f, check_finite=False)
        factor_solve_times.append((time.perf_counter() - t0) * 1000)

    return {
        "label": label,
        "nodes": n_nodes,
        "members": n_members,
        "dof": n_dof,
        "full_ms": statistics.median(full_times),
        "assembly_ms": statistics.median(assembly_times),
        "solve_ms": statistics.median(factor_solve_times),
        "matrix_mb": (n_dof * n_dof * 8) / (1024 ** 2),
        "equilibrium_ok": results.equilibrium.passed,
    }


def main() -> None:
    cases = [
        ("Planar Pratt (small)", EngineeringSpec(
            structure_type=StructureType.PRATT, span=20.0, height=3.33, num_panels=6)),
        ("Space truss (MVP)", EngineeringSpec(
            structure_type=StructureType.SPACE_TRUSS, span=20.0, height=2.5,
            width=4.0, num_panels=6, section_key="CHS_168x6")),
        ("Space truss (medium)", EngineeringSpec(
            structure_type=StructureType.SPACE_TRUSS, span=60.0, height=5.0,
            width=6.0, num_panels=30, section_key="CHS_219x8")),
        ("Space truss (large)", EngineeringSpec(
            structure_type=StructureType.SPACE_TRUSS, span=200.0, height=8.0,
            width=8.0, num_panels=120, section_key="CHS_219x8")),
        ("Space truss (very large)", EngineeringSpec(
            structure_type=StructureType.SPACE_TRUSS, span=400.0, height=10.0,
            width=10.0, num_panels=300, section_key="CHS_219x8")),
    ]

    print(f"{'Case':<26}{'Nodes':>7}{'Members':>9}{'DOF':>7}"
          f"{'Total(ms)':>11}{'Assembly':>10}{'Factor+Solve':>14}{'K(MB)':>8}{'Equil':>7}")
    print("-" * 97)
    for label, spec in cases:
        try:
            r = bench_case(label, spec)
            print(f"{r['label']:<26}{r['nodes']:>7}{r['members']:>9}{r['dof']:>7}"
                  f"{r['full_ms']:>11.2f}{r['assembly_ms']:>10.2f}{r['solve_ms']:>14.2f}"
                  f"{r['matrix_mb']:>8.2f}{'OK' if r['equilibrium_ok'] else 'FAIL':>7}")
        except Exception as e:  # noqa: BLE001 - benchmark should report, not crash
            print(f"{label:<26}  FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
