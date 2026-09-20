"""
NeuroPlan-3D — Demo Preset Audit

Proves, from the solver's own output, that Demo 1 (planar Pratt) and Demo 3
(3D space truss) are genuinely different structural models — not the same
model drawn from a different camera angle.

Also runs the wind A/B case: the identical space truss solved with and
without a transverse load, so the Z-direction response can be compared
directly.

Run:  python tools/audit_demos.py
"""
import sys
import pathlib
import copy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from server.models.structure import EngineeringSpec, StructureType
from server.core.generator.topology import generate_structure
from server.core.fea.solver import solve
from server.core.fea.elements import direction_cosines

EPS = 1e-9

# The exact payloads the UI's Demo 1 and Demo 3 buttons send.
DEMO_1 = EngineeringSpec(
    structure_type=StructureType.PRATT,
    span=20.0, height=3.3333333333333335, num_panels=8,
    primary_load=50000.0, load_description="center point load",
    material_key="A36", section_key="CHS_114x6",
)
DEMO_3 = EngineeringSpec(
    structure_type=StructureType.SPACE_TRUSS,
    span=24.0, height=2.5, width=4.0, num_panels=8,
    primary_load=80000.0, lateral_load_z=15000.0,
    load_description="distributed load",
    material_key="A36", section_key="CHS_168x6",
)


def describe(label: str, spec: EngineeringSpec) -> dict:
    structure = generate_structure(spec)
    results = solve(structure, spec)
    node_map = structure.node_dict()

    zs = [n.z for n in structure.nodes]
    dz_members = [
        m for m in structure.members
        if abs(node_map[m.node_j].z - node_map[m.node_i].z) > EPS
    ]
    multi_axis = 0
    for m in structure.members:
        lx, ly, lz, _ = direction_cosines(node_map[m.node_i], node_map[m.node_j])
        if sum(1 for c in (lx, ly, lz) if abs(c) > EPS) >= 2:
            multi_axis += 1

    max_uz = max(abs(r.dz) for r in results.node_results)
    sum_rz = sum(r.rz for r in results.reactions)

    print(f"{label}")
    print(f"  system            = {'SPACE_TRUSS (3D)' if spec.structure_type.is_spatial else 'PLANAR (2D)'}")
    print(f"  structure_type    = {spec.structure_type.value}")
    print(f"  nodes             = {len(structure.nodes)}")
    print(f"  members           = {len(structure.members)}")
    print(f"  DOF (3 per node)  = {results.dof_count}  (3 x {len(structure.nodes)} = {3*len(structure.nodes)})")
    print(f"  z_range           = [{min(zs):+.3f}, {max(zs):+.3f}]   extent = {max(zs)-min(zs):.3f} m")
    print(f"  members dz != 0   = {len(dz_members)}")
    print(f"  members >=2 axes  = {multi_axis}")
    print(f"  applied Fz        = {sum(l.fz for l in structure.loads):+.1f} N")
    print(f"  max |UZ|          = {max_uz:.6e} m")
    print(f"  sum Rz            = {sum_rz:+.1f} N")
    print(f"  solver is_spatial = {results.is_spatial}")
    print(f"  equilibrium       = {'PASS' if results.equilibrium.passed else 'FAIL'} "
          f"(rel residual {results.equilibrium.relative_residual:.2e})")
    print()
    return {
        "nodes": len(structure.nodes), "members": len(structure.members),
        "dof": results.dof_count, "z_extent": max(zs) - min(zs),
        "dz_members": len(dz_members), "max_uz": max_uz, "sum_rz": sum_rz,
        "is_spatial": results.is_spatial,
    }


def wind_ab_test() -> None:
    print("=" * 72)
    print("PHYSICS A/B — identical space truss, wind on vs. wind off")
    print("=" * 72)

    spec_a = copy.deepcopy(DEMO_3)
    spec_a.lateral_load_z = 0.0
    spec_b = copy.deepcopy(DEMO_3)  # wind = 15 kN

    rows = []
    for label, spec in (("CASE A (vertical only) ", spec_a), ("CASE B (vertical + wind)", spec_b)):
        structure = generate_structure(spec)
        results = solve(structure, spec)
        max_uz = max(abs(r.dz) for r in results.node_results)
        sum_rz = sum(r.rz for r in results.reactions)
        forces = {m.member_id: m.axial_force for m in results.member_results}
        rows.append((label, spec.lateral_load_z, max_uz, sum_rz, forces,
                     results.diagnosis.max_stress_ratio))
        print(f"{label}  Fz_applied={spec.lateral_load_z:>8.0f} N   "
              f"max|UZ|={max_uz:.6e} m   sumRz={sum_rz:+9.1f} N   "
              f"max_sigma_ratio={results.diagnosis.max_stress_ratio:.4f}")

    (_, _, uz_a, rz_a, f_a, sr_a) = rows[0]
    (_, _, uz_b, rz_b, f_b, sr_b) = rows[1]

    changed = sum(1 for mid in f_a if abs(f_a[mid] - f_b[mid]) > 1.0)
    biggest = max(((mid, abs(f_a[mid] - f_b[mid])) for mid in f_a), key=lambda t: t[1])

    print()
    print(f"  UZ response ratio B/A        : {(uz_b / uz_a) if uz_a > 0 else float('inf'):.1f}x")
    print(f"  Z reaction   A -> B          : {rz_a:+.1f} N -> {rz_b:+.1f} N")
    print(f"  members with force change    : {changed} / {len(f_a)}")
    print(f"  largest member force change  : member {biggest[0]}, {biggest[1]:.1f} N")
    print(f"  max stress ratio A -> B      : {sr_a:.4f} -> {sr_b:.4f}")
    print()


def main() -> None:
    print("=" * 72)
    print("DEMO PRESET COMPARISON")
    print("=" * 72)
    d1 = describe("Demo 1 — Clean Pass (20m bridge)", DEMO_1)
    d3 = describe("Demo 3 — 3D Space Truss (+ wind)", DEMO_3)

    print("=" * 72)
    print("VERDICT")
    print("=" * 72)
    checks = [
        ("Demo 1 is planar (z extent = 0)", d1["z_extent"] < 1e-9),
        ("Demo 1 has no dz members", d1["dz_members"] == 0),
        ("Demo 3 has meaningful z extent", d3["z_extent"] > 0.1),
        ("Demo 3 has members with dz != 0", d3["dz_members"] > 0),
        ("Demo 3 flagged spatial by solver", d3["is_spatial"] is True),
        ("Demo 3 responds in Z", d3["max_uz"] > 1e-9),
        ("Models differ in node count", d1["nodes"] != d3["nodes"]),
        ("Models differ in member count", d1["members"] != d3["members"]),
        ("Both use 3 DOF per node", d1["dof"] == 3 * d1["nodes"] and d3["dof"] == 3 * d3["nodes"]),
    ]
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print()
    if not all(ok for _, ok in checks):
        print("!! DEMO PRESETS ARE NOT GENUINELY DIFFERENT — implementation is wrong.")
        sys.exit(1)
    print("All structural-difference checks passed.\n")

    wind_ab_test()


if __name__ == "__main__":
    main()
