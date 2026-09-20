"""
NeuroPlan-3D — Engineering Evidence & Traceability

Builds the evidence package that backs every displayed number:

  * provenance  — which element produced a headline metric, and the
                  equation and inputs that produced it
  * verification — every check with its actual value, limit, units and source
  * assumptions  — what the solver does and does not model
  * benchmarks   — comparisons against values derived by hand, outside this code
  * record       — a traceable summary of the run

Everything here READS solver state. Nothing recomputes a physical result
for display: if a number appears in the UI it was produced by the solver,
and this module's job is to say where from. A capability that does not
exist reports NOT_AVAILABLE — never a silent pass.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from ..models.structure import (
    Structure, EngineeringSpec, AnalysisResults,
    ResultProvenance, ProvenanceInput,
    MATERIAL_LIBRARY,
)
from ..models.evidence import (
    CheckStatus, EvidenceCategory, VerificationItem,
    BenchmarkComparison, ModelingAssumption, SimulationRecord,
    LoadPath, LoadPathMember,
)
from .fea.elements import direction_cosines

SOFTWARE_VERSION = "0.2.0"
SOLVER_METHOD = "3D Direct Stiffness Method (pin-jointed truss, 3 translational DOF/node)"
SOLVER_BACKEND = "CPU — NumPy dense assembly, SciPy Cholesky (cho_factor/cho_solve)"


# ─────────────────────────────────────────────
# Provenance — where each headline number came from
# ─────────────────────────────────────────────

def build_provenance(
    structure: Structure,
    results: AnalysisResults,
    spec: EngineeringSpec,
) -> list[ResultProvenance]:
    """
    Attribute each headline metric to the specific element that produced it,
    with the equation and the actual input values used.

    The values are read back from solver output — `max_stress` is found by
    locating the member whose recorded stress is largest, not by recomputing
    a stress for display.
    """
    provenance: list[ResultProvenance] = []
    node_map = structure.node_dict()
    member_map = structure.member_dict()

    # --- Maximum stress → the specific member ---
    if results.member_results:
        peak = max(results.member_results, key=lambda m: abs(m.stress))
        member = member_map.get(peak.member_id)
        area = member.section.area if member else float("nan")
        provenance.append(ResultProvenance(
            metric="max_stress",
            label="Maximum Stress",
            value=peak.stress,
            units="Pa",
            source_type="member",
            source_id=peak.member_id,
            source_detail=f"Member {peak.member_id} → axial force ÷ cross-sectional area",
            equation="σ = N / A",
            inputs=[
                ProvenanceInput("N (axial force)", peak.axial_force, "N"),
                ProvenanceInput("A (cross-sectional area)", area, "m²"),
            ],
            note="Sign convention: positive = tension, negative = compression.",
        ))

        # --- Maximum stress ratio (utilisation) ---
        peak_ratio = max(results.member_results, key=lambda m: m.stress_ratio)
        provenance.append(ResultProvenance(
            metric="max_stress_ratio",
            label="Maximum Stress Ratio (utilisation)",
            value=peak_ratio.stress_ratio,
            units="–",
            source_type="member",
            source_id=peak_ratio.member_id,
            source_detail=f"Member {peak_ratio.member_id} → |σ| ÷ allowable stress",
            equation="ratio = |σ| / (σ_yield / FOS)",
            inputs=[
                ProvenanceInput("|σ| (stress magnitude)", abs(peak_ratio.stress), "Pa"),
                ProvenanceInput("σ_yield", MATERIAL_LIBRARY[spec.material_key].yield_stress, "Pa"),
                ProvenanceInput("FOS (safety factor)", spec.safety_factor, "–"),
                ProvenanceInput("allowable stress", peak_ratio.allowable_stress, "Pa"),
            ],
            note="Ratio > 1.0 means the member exceeds its allowable stress.",
        ))

    # --- Maximum displacement → the specific node and DOF ---
    if results.node_results:
        peak_node = max(results.node_results, key=lambda n: n.total_displacement)
        components = {"UX": peak_node.dx, "UY": peak_node.dy, "UZ": peak_node.dz}
        dominant = max(components, key=lambda k: abs(components[k]))
        node = node_map.get(peak_node.node_id)
        provenance.append(ResultProvenance(
            metric="max_displacement",
            label="Maximum Nodal Displacement",
            value=peak_node.total_displacement,
            units="m",
            source_type="node",
            source_id=peak_node.node_id,
            source_detail=(
                f"Node {peak_node.node_id} "
                f"({node.x:.3f}, {node.y:.3f}, {node.z:.3f}) → dominant component {dominant}"
            ),
            equation="|u| = √(UX² + UY² + UZ²)",
            inputs=[
                ProvenanceInput("UX", peak_node.dx, "m"),
                ProvenanceInput("UY", peak_node.dy, "m"),
                ProvenanceInput("UZ", peak_node.dz, "m"),
            ],
            note="Taken from the solved displacement vector u at this node's three DOF.",
        ))

    # --- Largest support reaction ---
    if results.reactions:
        peak_reaction = max(
            results.reactions,
            key=lambda r: math.sqrt(r.rx**2 + r.ry**2 + r.rz**2),
        )
        magnitude = math.sqrt(peak_reaction.rx**2 + peak_reaction.ry**2 + peak_reaction.rz**2)
        provenance.append(ResultProvenance(
            metric="max_reaction",
            label="Largest Support Reaction",
            value=magnitude,
            units="N",
            source_type="reaction",
            source_id=peak_reaction.node_id,
            source_detail=f"Support at node {peak_reaction.node_id}",
            equation="R = K·u − F  (evaluated at restrained DOF)",
            inputs=[
                ProvenanceInput("Rx", peak_reaction.rx, "N"),
                ProvenanceInput("Ry", peak_reaction.ry, "N"),
                ProvenanceInput("Rz", peak_reaction.rz, "N"),
            ],
            note="Recovered from the assembled stiffness matrix, not assumed.",
        ))

    # --- Structural mass (reporting only — see assumptions) ---
    provenance.append(ResultProvenance(
        metric="total_weight",
        label="Total Structural Mass",
        value=results.total_weight_kg,
        units="kg",
        source_type="system",
        source_detail="Σ over members of (density × area × length)",
        equation="m = Σ ρ·A·L",
        inputs=[
            ProvenanceInput("member count", float(len(structure.members)), "–"),
            ProvenanceInput("density", MATERIAL_LIBRARY[spec.material_key].density, "kg/m³"),
        ],
        note="REPORTING ONLY — self-weight is not applied as a load in this analysis.",
    ))

    return provenance


# ─────────────────────────────────────────────
# Load path tracing
# ─────────────────────────────────────────────

def build_load_paths(
    structure: Structure,
    results: AnalysisResults,
    tolerance: float = 1e-6,
) -> list[LoadPath]:
    """
    Trace each applied load into the members that carry it.

    A truss load does not follow one unique route — it distributes through
    every connected member. So rather than inventing a single "path", this
    reports the actual transfer at the loaded joint and verifies it:

        applied force + Σ(member force on the joint) = 0

    For a member in tension (N > 0) the member pulls the joint toward its
    far end, so the force it applies to the joint is N·c, where c is the
    unit vector from the joint toward the other node. That residual is the
    checkable link in the chain from load to reaction: if it is zero, those
    members genuinely carry that load.
    """
    node_map = structure.node_dict()
    force_by_member = {m.member_id: m for m in results.member_results}
    paths: list[LoadPath] = []

    for load in structure.loads:
        joint = node_map[load.node_id]
        path = LoadPath(
            node_id=load.node_id,
            node_x=joint.x, node_y=joint.y, node_z=joint.z,
            applied_fx=load.fx, applied_fy=load.fy, applied_fz=load.fz,
        )

        sum_fx = sum_fy = sum_fz = 0.0
        for member in structure.members:
            if load.node_id not in (member.node_i, member.node_j):
                continue
            other_id = member.node_j if member.node_i == load.node_id else member.node_i
            other = node_map[other_id]

            # Unit vector pointing from the joint toward the other end.
            lx, ly, lz, _ = direction_cosines(joint, other)

            mr = force_by_member.get(member.id)
            if mr is None:
                continue
            n = mr.axial_force

            fx, fy, fz = n * lx, n * ly, n * lz
            sum_fx += fx
            sum_fy += fy
            sum_fz += fz

            path.members.append(LoadPathMember(
                member_id=member.id,
                other_node_id=other_id,
                axial_force=n,
                stress=mr.stress,
                direction_cosines=(lx, ly, lz),
                fx_on_joint=fx, fy_on_joint=fy, fz_on_joint=fz,
            ))

        path.joint_residual_fx = load.fx + sum_fx
        path.joint_residual_fy = load.fy + sum_fy
        path.joint_residual_fz = load.fz + sum_fz

        applied_magnitude = math.sqrt(load.fx**2 + load.fy**2 + load.fz**2)
        max_residual = max(
            abs(path.joint_residual_fx),
            abs(path.joint_residual_fy),
            abs(path.joint_residual_fz),
        )
        path.joint_relative_residual = (
            max_residual / applied_magnitude if applied_magnitude > 1e-12 else max_residual
        )
        path.joint_equilibrium_passed = path.joint_relative_residual <= tolerance
        paths.append(path)

    return paths


# ─────────────────────────────────────────────
# Verification evidence
# ─────────────────────────────────────────────

def build_verification_items(
    structure: Structure,
    results: AnalysisResults,
    spec: EngineeringSpec,
) -> list[VerificationItem]:
    """Every check, with the actual numbers behind its status."""
    items: list[VerificationItem] = []
    eq = results.equilibrium
    checks = results.checks
    node_map = structure.node_dict()

    def ok(flag: bool) -> CheckStatus:
        return CheckStatus.PASS if flag else CheckStatus.FAIL

    # ── MODEL DEFINITION ──
    items.append(VerificationItem(
        key="geometry_nodes",
        category=EvidenceCategory.MODEL_DEFINITION,
        label="Geometry — node definition",
        status=ok(checks.geometry),
        actual_display=f"{len(structure.nodes)} nodes",
        limit_display="≥ 2 required",
        units="nodes",
        source="generator → Structure.nodes",
        detail="Every node carries explicit x, y, z coordinates.",
        actual_value=float(len(structure.nodes)),
        limit_value=2.0,
    ))

    zero_length = 0
    for m in structure.members:
        try:
            direction_cosines(node_map[m.node_i], node_map[m.node_j])
        except ValueError:
            zero_length += 1
    items.append(VerificationItem(
        key="zero_length_members",
        category=EvidenceCategory.MODEL_DEFINITION,
        label="Zero-length member check",
        status=ok(zero_length == 0),
        actual_display=f"{zero_length} zero-length members",
        limit_display="0 allowed",
        units="members",
        source="elements.direction_cosines → length test (L < 1e-12)",
        detail="A zero-length member would make AE/L singular.",
        actual_value=float(zero_length),
        limit_value=0.0,
    ))

    unknown_refs = sum(
        1 for m in structure.members
        if m.node_i not in node_map or m.node_j not in node_map
    )
    items.append(VerificationItem(
        key="member_connectivity",
        category=EvidenceCategory.MODEL_DEFINITION,
        label="Member connectivity",
        status=ok(unknown_refs == 0),
        actual_display=f"{len(structure.members)} members, {unknown_refs} dangling references",
        limit_display="0 dangling",
        units="members",
        source="solver.check_model_validity → node id resolution",
        detail="Every member must reference nodes that exist.",
        actual_value=float(unknown_refs),
        limit_value=0.0,
    ))

    restraint_count = sum(s.dx + s.dy + s.dz for s in structure.supports)
    items.append(VerificationItem(
        key="boundary_conditions",
        category=EvidenceCategory.MODEL_DEFINITION,
        label="Boundary conditions — restraint sufficiency",
        status=ok(checks.boundary_conditions),
        actual_display=f"{restraint_count} restrained DOF across {len(structure.supports)} supports",
        limit_display="≥ 6 required to suppress rigid-body modes",
        units="DOF",
        source="boundary.get_constrained_dofs → solver Cholesky factorization",
        detail=(
            "Sufficiency is proven by the Cholesky factorization succeeding: an "
            "under-restrained structure yields a singular matrix and fails to factor."
        ),
        actual_value=float(restraint_count),
        limit_value=6.0,
    ))

    # ── SOLVER ──
    items.append(VerificationItem(
        key="dof_model",
        category=EvidenceCategory.SOLVER,
        label="Degrees of freedom (3 translational per node)",
        status=ok(results.dof_count == 3 * len(structure.nodes)),
        actual_display=f"{results.dof_count} DOF = 3 × {len(structure.nodes)} nodes",
        limit_display=f"exactly {3 * len(structure.nodes)}",
        units="DOF",
        source="assembly.build_dof_map → base = 3 × node index",
        detail="UX, UY and UZ are solved at every node.",
        actual_value=float(results.dof_count),
        limit_value=float(3 * len(structure.nodes)),
    ))

    items.append(VerificationItem(
        key="matrix_solvable",
        category=EvidenceCategory.SOLVER,
        label="Global stiffness assembly & solvability",
        status=ok(checks.solver),
        actual_display="K_ff factorized successfully (Cholesky)",
        limit_display="symmetric positive definite required",
        units="–",
        source="solver → scipy.linalg.cho_factor on the free-DOF submatrix",
        detail=(
            "K_ff is symmetric positive definite for a properly restrained truss. "
            "Factorization failure is the mechanism check."
        ),
    ))

    # ── EQUILIBRIUM (force) ──
    for axis, residual in (("ΣFx", eq.residual_fx), ("ΣFy", eq.residual_fy), ("ΣFz", eq.residual_fz)):
        items.append(VerificationItem(
            key=f"equilibrium_{axis[-1].lower()}",
            category=EvidenceCategory.EQUILIBRIUM,
            label=f"Force equilibrium — {axis}",
            status=ok(eq.relative_residual <= eq.tolerance),
            actual_display=f"{residual:+.6e} N",
            limit_display=f"|relative residual| ≤ {eq.tolerance:.0e}",
            units="N",
            source="Σ(applied loads) + Σ(reactions), reactions from R = K·u − F",
            detail="Independent check that the assembled system was actually satisfied.",
            actual_value=residual,
            limit_value=eq.tolerance,
        ))

    # ── EQUILIBRIUM (moment) ──
    for axis, residual in (("ΣMx", eq.residual_mx), ("ΣMy", eq.residual_my), ("ΣMz", eq.residual_mz)):
        items.append(VerificationItem(
            key=f"moment_equilibrium_{axis[-1].lower()}",
            category=EvidenceCategory.EQUILIBRIUM,
            label=f"Moment equilibrium — {axis} (about origin)",
            status=ok(eq.relative_moment_residual <= eq.tolerance),
            actual_display=f"{residual:+.6e} N·m",
            limit_display=f"|relative residual| ≤ {eq.tolerance:.0e}",
            units="N·m",
            source="Σ(r × applied) + Σ(r × reactions) about the global origin",
            detail=(
                "Catches errors force balance alone cannot: reactions that sum correctly "
                "but are distributed to the wrong supports."
            ),
            actual_value=residual,
            limit_value=eq.tolerance,
        ))

    # ── NUMERICAL ──
    items.append(VerificationItem(
        key="numerical_residual",
        category=EvidenceCategory.NUMERICAL,
        label="Relative force-equilibrium residual",
        status=ok(eq.relative_residual <= eq.tolerance),
        actual_display=f"{eq.relative_residual:.3e}",
        limit_display=f"≤ {eq.tolerance:.0e}",
        units="–",
        source=f"max|force residual| ÷ applied load magnitude ({eq.load_magnitude:.1f} N)",
        detail="Normalized so the tolerance is scale-independent.",
        actual_value=eq.relative_residual,
        limit_value=eq.tolerance,
    ))
    items.append(VerificationItem(
        key="numerical_moment_residual",
        category=EvidenceCategory.NUMERICAL,
        label="Relative moment-equilibrium residual",
        status=ok(eq.relative_moment_residual <= eq.tolerance),
        actual_display=f"{eq.relative_moment_residual:.3e}",
        limit_display=f"≤ {eq.tolerance:.0e}",
        units="–",
        source=f"max|moment residual| ÷ applied moment magnitude ({eq.moment_magnitude:.1f} N·m)",
        detail="Normalized separately from forces — different units, different scale.",
        actual_value=eq.relative_moment_residual,
        limit_value=eq.tolerance,
    ))
    items.append(VerificationItem(
        key="iterative_convergence",
        category=EvidenceCategory.NUMERICAL,
        label="Iterative convergence",
        status=CheckStatus.INFO,
        actual_display="Not applicable — direct solver",
        limit_display="–",
        units="–",
        source="solver → direct Cholesky factorization",
        detail=(
            "This is a direct (non-iterative) linear solve, so there is no iteration "
            "tolerance to converge. Accuracy is confirmed by the residual checks above."
        ),
    ))

    # ── STRUCTURAL LIMITS ──
    diag = results.diagnosis
    allowable = MATERIAL_LIBRARY[spec.material_key].yield_stress / spec.safety_factor
    items.append(VerificationItem(
        key="stress_limit",
        category=EvidenceCategory.LIMITS,
        label="Stress limit",
        status=ok(checks.stress),
        actual_display=f"max ratio {diag.max_stress_ratio:.4f}",
        limit_display="≤ 1.0000",
        units="–",
        source=f"validator → |σ| ÷ (σ_yield/FOS); allowable = {allowable/1e6:.1f} MPa",
        detail=f"{diag.failed_member_count} member(s) exceed the allowable stress.",
        actual_value=diag.max_stress_ratio,
        limit_value=1.0,
    ))
    max_allowable_disp_mm = (spec.span / spec.max_displacement_ratio) * 1000
    items.append(VerificationItem(
        key="displacement_limit",
        category=EvidenceCategory.LIMITS,
        label="Displacement limit",
        status=ok(checks.displacement),
        actual_display=f"{diag.max_displacement_mm:.3f} mm",
        limit_display=f"≤ {max_allowable_disp_mm:.3f} mm (L/{spec.max_displacement_ratio:.0f})",
        units="mm",
        source="validator → max nodal |u| vs span/ratio",
        detail=f"{diag.failed_node_count} node(s) exceed the displacement limit.",
        actual_value=diag.max_displacement_mm,
        limit_value=max_allowable_disp_mm,
    ))

    buckling_risk = sum(
        1 for m in results.member_results
        if m.axial_force < 0 and m.euler_buckling_load > 0
        and abs(m.axial_force) > m.euler_buckling_load
    )
    items.append(VerificationItem(
        key="buckling_check",
        category=EvidenceCategory.LIMITS,
        label="Buckling — simplified Euler only",
        status=ok(buckling_risk == 0),
        actual_display=f"{buckling_risk} member(s) over simplified Euler load",
        limit_display="0 members",
        units="members",
        source="postprocess → P_cr = π²EI/L² per compression member",
        detail=(
            "PARTIAL CHECK. Effective-length factor K=1 assumed; no lateral-torsional "
            "buckling, no combined axial+bending interaction, no code column curves."
        ),
        actual_value=float(buckling_risk),
        limit_value=0.0,
    ))

    # ── REAL-WORLD VALIDATION ──
    items.append(VerificationItem(
        key="real_world_validation",
        category=EvidenceCategory.REAL_WORLD,
        label="Real-world / experimental validation",
        status=CheckStatus.NOT_AVAILABLE,
        actual_display="Not performed",
        limit_display="–",
        units="–",
        source="—",
        detail=(
            "No physical testing, no comparison against commercial FEA, and no "
            "licensed-engineer review has been performed for THIS model. The checks "
            "above verify the COMPUTATION, not real-world structural safety. "
            "Separately, this solver's underlying formulation has been compared "
            "against a real laboratory experiment (a published steel truss bridge "
            "test) — see 'Validation Library' for that comparison, its result, and "
            "its documented limitations. That comparison validates the solver in "
            "general, not this specific structure."
        ),
    ))

    return items


# ─────────────────────────────────────────────
# Independent benchmarks
# ─────────────────────────────────────────────

def run_benchmarks() -> list[BenchmarkComparison]:
    """
    Solve reference structures whose answers are derived by hand, and
    compare. These run live against the real solver on every request — they
    are not recorded results.

    The derivations are reproduced in the `derivation` field so a reader can
    check the reference value themselves rather than trusting it.
    """
    from ..models.structure import (
        Node, Member, Support, PointLoad, SupportType, CrossSection,
    )
    from .fea.solver import solve

    comparisons: list[BenchmarkComparison] = []
    section = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)

    # ── Case 1: symmetric triangular truss, Method of Joints ──
    # A(0,0) pin, B(6,0) roller, C(3,4) apex, P = 10 kN downward at C.
    # By symmetry Ay = By = P/2 = 5000 N.
    # Joint C: −4/5·F_CA − 4/5·F_CB − P = 0 and F_CA = F_CB
    #   → F_CA = F_CB = −5P/8 = −6250 N (compression)
    # Joint A: F_AB + 3/5·F_AC = 0 → F_AB = +3P/8 = +3750 N (tension)
    P = 10000.0
    structure = Structure(
        nodes=[
            Node(id=0, x=0.0, y=0.0, z=0.0),
            Node(id=1, x=6.0, y=0.0, z=0.0),
            Node(id=2, x=3.0, y=4.0, z=0.0),
        ],
        members=[
            Member(id=0, node_i=0, node_j=1, material_key="A36", section=section),
            Member(id=1, node_i=0, node_j=2, material_key="A36", section=section),
            Member(id=2, node_i=1, node_j=2, material_key="A36", section=section),
        ],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X),
            Support(node_id=2, support_type=SupportType.OUT_OF_PLANE),
        ],
        loads=[PointLoad(node_id=2, fy=-P)],
    )
    res = solve(structure, EngineeringSpec(material_key="A36"))
    forces = {m.member_id: m.axial_force for m in res.member_results}
    reactions = {r.node_id: r for r in res.reactions}

    ref_src = "Hand derivation via the Method of Joints (see derivation)"
    comparisons.append(BenchmarkComparison(
        case="Symmetric triangular truss (6 m span, 4 m rise, 10 kN apex load)",
        quantity="Bottom chord AB axial force",
        neuroplan_value=forces[0], reference_value=3 * P / 8,
        units="N", tolerance_relative=1e-6, reference_source=ref_src,
        derivation="Joint A: F_AB + (3/5)·F_AC = 0, with F_AC = −5P/8 → F_AB = +3P/8 = +3750 N (tension)",
    ))
    comparisons.append(BenchmarkComparison(
        case="Symmetric triangular truss (6 m span, 4 m rise, 10 kN apex load)",
        quantity="Inclined member AC axial force",
        neuroplan_value=forces[1], reference_value=-5 * P / 8,
        units="N", tolerance_relative=1e-6, reference_source=ref_src,
        derivation="Joint C: −(4/5)(F_CA + F_CB) = P with F_CA = F_CB → F_CA = −5P/8 = −6250 N (compression)",
    ))
    comparisons.append(BenchmarkComparison(
        case="Symmetric triangular truss (6 m span, 4 m rise, 10 kN apex load)",
        quantity="Vertical reaction at A",
        neuroplan_value=reactions[0].ry, reference_value=P / 2,
        units="N", tolerance_relative=1e-6, reference_source=ref_src,
        derivation="Symmetric structure, centred load → Ay = By = P/2 = 5000 N",
    ))

    # ── Case 2: single axial bar, closed form ──
    # δ = F·L/(A·E), σ = F/A — independent of the stiffness method used.
    class _FixedArea(CrossSection):
        def __init__(self, area: float):
            super().__init__(outer_diameter=0.1, wall_thickness=0.01)
            self._area = area

        @property
        def area(self):
            return self._area

        @property
        def moment_of_inertia(self):
            return 1e-6

    A, E, L, F = 0.002, 200e9, 2.0, 10000.0
    free_end = Support(node_id=1, support_type=SupportType.PIN)
    free_end.dx, free_end.dy, free_end.dz = False, True, True
    bar = Structure(
        nodes=[Node(id=0, x=0.0, y=0.0, z=0.0), Node(id=1, x=L, y=0.0, z=0.0)],
        members=[Member(id=0, node_i=0, node_j=1, material_key="A36", section=_FixedArea(A))],
        supports=[Support(node_id=0, support_type=SupportType.PIN), free_end],
        loads=[PointLoad(node_id=1, fx=F)],
    )
    bar_res = solve(bar, EngineeringSpec(material_key="A36"))
    tip = next(r for r in bar_res.node_results if r.node_id == 1)
    comparisons.append(BenchmarkComparison(
        case="Axial bar (L = 2 m, A = 0.002 m², E = 200 GPa, F = 10 kN)",
        quantity="Tip elongation",
        neuroplan_value=tip.dx, reference_value=F * L / (A * E),
        units="m", tolerance_relative=1e-9,
        reference_source="Closed-form elasticity: δ = F·L/(A·E)",
        derivation="δ = (10000 × 2) / (0.002 × 200e9) = 5.0e-5 m",
    ))
    comparisons.append(BenchmarkComparison(
        case="Axial bar (L = 2 m, A = 0.002 m², E = 200 GPa, F = 10 kN)",
        quantity="Axial stress",
        neuroplan_value=bar_res.member_results[0].stress, reference_value=F / A,
        units="Pa", tolerance_relative=1e-9,
        reference_source="Closed-form elasticity: σ = F/A",
        derivation="σ = 10000 / 0.002 = 5.0e6 Pa = 5 MPa",
    ))

    return comparisons


# ─────────────────────────────────────────────
# Assumptions & limitations
# ─────────────────────────────────────────────

def get_assumptions() -> list[ModelingAssumption]:
    """
    What this solver does and does not model.

    Each entry reflects the actual implementation. `modeled=False` entries
    are things a reader might reasonably assume are included and which are
    not — they matter more than the ones that are.
    """
    return [
        # --- Modeled ---
        ModelingAssumption(
            "Linear elastic material", True,
            "Members follow σ = E·ε with a constant Young's modulus.",
            "Valid only below yield; post-yield behaviour is not represented.",
        ),
        ModelingAssumption(
            "Small-displacement (linear geometry)", True,
            "Equilibrium is formed on the undeformed geometry.",
            "P-delta and large-deflection effects are not captured.",
        ),
        ModelingAssumption(
            "Pin-jointed truss idealization", True,
            "All joints are frictionless pins; members carry axial force only.",
            "No bending moment or shear is computed in any member.",
        ),
        ModelingAssumption(
            "Static loading", True,
            "Loads are applied statically with no time dependence.",
            "No dynamic amplification, resonance or time-history response.",
        ),
        ModelingAssumption(
            "Three translational DOF per node", True,
            "UX, UY and UZ are solved at every node (3N total DOF).",
            "Rotational DOF are absent by design — consistent with a pin-jointed truss.",
        ),
        # --- NOT modeled ---
        ModelingAssumption(
            "Self-weight / dead load", False,
            "Structural mass is reported but is NOT applied as a load in the analysis.",
            "Reported stresses and displacements exclude the structure's own weight.",
        ),
        ModelingAssumption(
            "Buckling (full treatment)", False,
            "Only a simplified Euler check (P_cr = π²EI/L², K=1) per compression member.",
            "No effective-length factors, lateral-torsional buckling or code column curves.",
        ),
        ModelingAssumption(
            "Material nonlinearity", False,
            "No plasticity, yielding redistribution, creep or strain hardening.", "",
        ),
        ModelingAssumption(
            "Geometric nonlinearity", False,
            "No large-displacement or stress-stiffening formulation.", "",
        ),
        ModelingAssumption(
            "Dynamic, modal and seismic response", False,
            "No mass matrix is assembled; no eigenvalue or time-history analysis.", "",
        ),
        ModelingAssumption(
            "Fatigue", False, "No cyclic loading or endurance assessment.", "",
        ),
        ModelingAssumption(
            "Connections, welds and bolts", False,
            "Joints are idealized pins; no connection capacity is checked.",
            "In real trusses connections frequently govern before members do.",
        ),
        ModelingAssumption(
            "Foundation and soil interaction", False,
            "Supports are idealized rigid restraints.", "",
        ),
        ModelingAssumption(
            "Thermal and settlement effects", False,
            "No temperature loads or imposed support displacements.", "",
        ),
        ModelingAssumption(
            "Construction tolerances and imperfections", False,
            "Geometry is treated as exact and members as perfectly straight.", "",
        ),
        ModelingAssumption(
            "Design-code compliance", False,
            "No AISC, Eurocode or IS code clause checks are performed.",
            "The safety factor is a simple user-set divisor, not a code procedure.",
        ),
    ]


# ─────────────────────────────────────────────
# Simulation record
# ─────────────────────────────────────────────

def build_simulation_record(
    structure: Structure,
    results: AnalysisResults,
    spec: EngineeringSpec,
    iteration_count: int,
) -> SimulationRecord:
    """A traceable summary of one run."""
    warnings: list[str] = []
    if not results.checks.all_passed:
        failed = [
            name for name, flag in (
                ("solver", results.checks.solver),
                ("geometry", results.checks.geometry),
                ("boundary_conditions", results.checks.boundary_conditions),
                ("equilibrium", results.checks.equilibrium),
                ("stress", results.checks.stress),
                ("displacement", results.checks.displacement),
            ) if not flag
        ]
        warnings.append("Failed computational checks: " + ", ".join(failed))
    warnings.append("Self-weight is not applied as a load in this analysis.")
    warnings.append("No real-world or experimental validation has been performed.")

    return SimulationRecord(
        simulation_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        software_version=SOFTWARE_VERSION,
        solver_method=SOLVER_METHOD,
        solver_backend=SOLVER_BACKEND,
        node_count=len(structure.nodes),
        member_count=len(structure.members),
        dof_per_node=3,
        total_dof=results.dof_count,
        support_count=len(structure.supports),
        load_count=len(structure.loads),
        material_keys=sorted({m.material_key for m in structure.members}),
        section_keys=[spec.section_key],
        iteration_count=iteration_count,
        warnings=warnings,
    )
