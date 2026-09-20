"""
NeuroPlan-3D — Structural Diagnostics (Priority 3)

Turns solver failures into engineering explanations.

"Matrix is singular" tells a user nothing actionable. The same condition,
diagnosed properly, is one of: too few supports, a support pattern that
leaves a rigid-body mode, a node nothing connects to, a sub-assembly
floating free of the supported part, or a genuine internal mechanism.
Each has a different fix. This module distinguishes them.

────────────────────────────────────────────────────────────────────────
MATHEMATICAL BASIS
────────────────────────────────────────────────────────────────────────
1. MAXWELL'S COUNTING CRITERION (necessary, not sufficient)

   For a pin-jointed truss in d dimensions with n nodes, m members and r
   independent reaction components:

       m + r  <  d*n   -> mechanism (statically/kinematically deficient)
       m + r == d*n    -> statically determinate, if arrangement is proper
       m + r  >  d*n   -> statically indeterminate (redundant)

   NeuroPlan uses d = 3 (three translational DOF per node).

   This is a COUNT. It cannot see a bad arrangement: a structure can
   satisfy m + r >= 3n and still be a mechanism if members are collinear
   or a sub-assembly is unbraced. So a passing count is reported as
   "necessary condition met", never as "stable".

2. RANK / NULL-SPACE TEST (sufficient, and what actually decides)

   The free-DOF stiffness submatrix K_ff is symmetric positive definite
   for a properly restrained truss. Its eigenvalues are all > 0. Each
   zero eigenvalue is one independent mechanism or rigid-body mode, and
   the corresponding eigenvector IS the mode shape — which tells us which
   nodes move. We report the count and the participating nodes.

3. CONDITION NUMBER

       kappa(K_ff) = lambda_max / lambda_min   (symmetric, so = sigma ratio)

   Roughly log10(kappa) digits of precision are lost in the solve. With
   float64 carrying ~16 digits:

       kappa > 1e12  -> ill-conditioned; results are numerically suspect
       kappa > 1e15  -> effectively singular; results are meaningless

   A near-singular system often factors "successfully" and returns
   plausible-looking numbers, which is more dangerous than an outright
   failure. This is why conditioning is checked even on the success path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ...models.structure import Structure, SupportType

# Condition-number thresholds. Justified in the module docstring by
# float64 precision, not chosen for convenience.
ILL_CONDITIONED_THRESHOLD = 1e12
EFFECTIVELY_SINGULAR_THRESHOLD = 1e15

# An eigenvalue below this fraction of the largest is treated as zero,
# i.e. a mechanism. Scaled relatively so it is independent of the units
# and stiffness magnitude of the model.
ZERO_EIGENVALUE_RATIO = 1e-12

# Full eigen-decomposition is O(n^3); above this many free DOF we report
# the cheaper reciprocal-condition estimate instead of mode shapes.
MAX_DOF_FOR_EIGEN_ANALYSIS = 1500


class DiagnosticCode(str, Enum):
    ZERO_LENGTH_MEMBER = "zero_length_member"
    DUPLICATE_MEMBER = "duplicate_member"
    DISCONNECTED_NODE = "disconnected_node"
    DISCONNECTED_ASSEMBLY = "disconnected_assembly"
    UNSUPPORTED_ASSEMBLY = "unsupported_assembly"
    INSUFFICIENT_CONSTRAINTS = "insufficient_constraints"
    COUNTING_CRITERION_DEFICIENT = "counting_criterion_deficient"
    RIGID_BODY_MODE = "rigid_body_mode"
    UNSTABLE_MECHANISM = "unstable_mechanism"
    SINGULAR_MATRIX = "singular_matrix"
    NEAR_SINGULAR_MATRIX = "near_singular_matrix"
    ILL_CONDITIONED = "ill_conditioned"


class Severity(str, Enum):
    ERROR = "error"      # the model cannot be solved meaningfully
    WARNING = "warning"  # solvable, but the result is suspect
    INFO = "info"        # worth knowing; not a defect


@dataclass
class Diagnostic:
    code: DiagnosticCode
    severity: Severity
    title: str
    explanation: str          # what is wrong, in engineering terms
    remedy: str = ""          # what the user can actually do about it
    affected_nodes: list[int] = field(default_factory=list)
    affected_members: list[int] = field(default_factory=list)
    measured_value: float | None = None
    threshold: float | None = None
    basis: str = ""           # which test produced this


@dataclass
class StabilityReport:
    """Result of the counting + rank analysis."""
    n_nodes: int
    n_members: int
    n_reaction_components: int
    n_free_dof: int
    required_dof: int                  # 3 * n_nodes
    counting_margin: int               # (m + r) - 3n
    counting_satisfied: bool
    determinacy: str                   # "mechanism" | "determinate" | "indeterminate"
    n_zero_modes: int | None = None
    condition_number: float | None = None
    eigen_analysis_performed: bool = False
    diagnostics: list[Diagnostic] = field(default_factory=list)


# ─────────────────────────────────────────────
# Topology checks (pre-solve, no matrix needed)
# ─────────────────────────────────────────────

def _reaction_component_count(structure: Structure) -> int:
    """Count independent restrained translational DOF across all supports."""
    total = 0
    for support in structure.supports:
        total += int(support.dx) + int(support.dy) + int(support.dz)
    return total


def check_topology(structure: Structure, tolerance: float = 1e-9) -> list[Diagnostic]:
    """
    Geometry and connectivity defects that make a model ill-posed before
    any matrix is assembled.
    """
    found: list[Diagnostic] = []
    nodes = structure.node_dict()

    # --- Zero-length members ---
    zero_length = []
    for member in structure.members:
        if member.node_i not in nodes or member.node_j not in nodes:
            continue
        if member.length(nodes) <= tolerance:
            zero_length.append(member.id)
    if zero_length:
        found.append(Diagnostic(
            code=DiagnosticCode.ZERO_LENGTH_MEMBER,
            severity=Severity.ERROR,
            title="Zero-length member",
            explanation=(
                f"{len(zero_length)} member(s) connect two coincident points. "
                f"Element stiffness is AE/L, so L = 0 makes the stiffness "
                f"infinite and the global matrix unusable. This usually means "
                f"two nodes were generated at the same coordinates."
            ),
            remedy="Remove the member, or move one of its end nodes apart.",
            affected_members=zero_length,
            basis="Element length check, L <= 1e-9 m",
        ))

    # --- Duplicate members (same node pair, either orientation) ---
    seen: dict[tuple[int, int], int] = {}
    duplicates: list[int] = []
    for member in structure.members:
        key = (min(member.node_i, member.node_j), max(member.node_i, member.node_j))
        if key in seen:
            duplicates.append(member.id)
        else:
            seen[key] = member.id
    if duplicates:
        found.append(Diagnostic(
            code=DiagnosticCode.DUPLICATE_MEMBER,
            severity=Severity.WARNING,
            title="Duplicate member",
            explanation=(
                f"{len(duplicates)} member(s) connect a node pair that is "
                f"already connected. The duplicate adds its stiffness in "
                f"parallel, so the structure is stiffer than the drawing "
                f"suggests and each member carries only part of the force "
                f"an engineer reading the model would expect."
            ),
            remedy="Delete the duplicate, or merge the two into one member with the combined area.",
            affected_members=duplicates,
            basis="Node-pair uniqueness check",
        ))

    # --- Nodes no member touches ---
    connected_nodes = set()
    for member in structure.members:
        connected_nodes.add(member.node_i)
        connected_nodes.add(member.node_j)
    orphans = sorted(n.id for n in structure.nodes if n.id not in connected_nodes)
    if orphans:
        found.append(Diagnostic(
            code=DiagnosticCode.DISCONNECTED_NODE,
            severity=Severity.ERROR,
            title="Disconnected node",
            explanation=(
                f"Node(s) {orphans} are not attached to any member. Their "
                f"three DOF have zero stiffness, so the global matrix has "
                f"zero rows and columns and cannot be factorised. If such a "
                f"node also carries load, that load has no path to a support."
            ),
            remedy="Connect the node with at least one member, or delete it.",
            affected_nodes=orphans,
            basis="Node-to-member incidence check",
        ))

    # --- Separate assemblies, and whether each is supported ---
    components = _connected_components(structure)
    if len(components) > 1:
        sizes = sorted((len(c) for c in components), reverse=True)
        found.append(Diagnostic(
            code=DiagnosticCode.DISCONNECTED_ASSEMBLY,
            severity=Severity.ERROR,
            title="Structure is in separate pieces",
            explanation=(
                f"The model splits into {len(components)} assemblies that "
                f"share no member (sizes: {sizes}). They cannot transfer "
                f"force to each other, so each must be independently "
                f"supported — otherwise the unsupported one floats free."
            ),
            remedy="Connect the assemblies with members, or support each one independently.",
            basis="Connected-component analysis of the member graph",
        ))

    supported_nodes = {s.node_id for s in structure.supports
                       if s.dx or s.dy or s.dz}
    for component in components:
        if not (component & supported_nodes):
            found.append(Diagnostic(
                code=DiagnosticCode.UNSUPPORTED_ASSEMBLY,
                severity=Severity.ERROR,
                title="Unsupported assembly",
                explanation=(
                    f"An assembly of {len(component)} node(s) has no support "
                    f"anywhere on it. Nothing resists its rigid-body motion, "
                    f"so it has at least three free translation modes and the "
                    f"stiffness matrix is singular."
                ),
                remedy="Add a support to this assembly, or connect it to a supported part.",
                affected_nodes=sorted(component),
                basis="Support reachability per connected component",
            ))

    return found


def _connected_components(structure: Structure) -> list[set[int]]:
    """Connected components of the node-member graph (union-find)."""
    parent: dict[int, int] = {n.id: n.id for n in structure.nodes}

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for member in structure.members:
        if member.node_i in parent and member.node_j in parent:
            union(member.node_i, member.node_j)

    groups: dict[int, set[int]] = {}
    for node_id in parent:
        groups.setdefault(find(node_id), set()).add(node_id)
    return list(groups.values())


# ─────────────────────────────────────────────
# Counting + rank analysis
# ─────────────────────────────────────────────

def analyze_stability(
    structure: Structure,
    K_ff: np.ndarray | None = None,
    n_free_dof: int | None = None,
) -> StabilityReport:
    """
    Maxwell count plus, when K_ff is supplied, the eigenvalue test that
    actually decides stability.
    """
    n = len(structure.nodes)
    m = len(structure.members)
    r = _reaction_component_count(structure)
    required = 3 * n
    margin = (m + r) - required

    if margin < 0:
        determinacy = "mechanism"
    elif margin == 0:
        determinacy = "determinate"
    else:
        determinacy = "indeterminate"

    report = StabilityReport(
        n_nodes=n, n_members=m, n_reaction_components=r,
        n_free_dof=n_free_dof if n_free_dof is not None else required - r,
        required_dof=required,
        counting_margin=margin,
        counting_satisfied=margin >= 0,
        determinacy=determinacy,
    )

    if margin < 0:
        report.diagnostics.append(Diagnostic(
            code=DiagnosticCode.COUNTING_CRITERION_DEFICIENT,
            severity=Severity.ERROR,
            title="Too few members or supports (Maxwell count)",
            explanation=(
                f"Maxwell's criterion for a 3D pin-jointed truss requires "
                f"m + r >= 3n. Here m = {m} members, r = {r} restrained "
                f"reaction components and n = {n} nodes, giving "
                f"{m} + {r} = {m + r} against a required {required}. "
                f"The structure is short by {-margin} constraint(s) and is "
                f"a mechanism: it can move without straining any member."
            ),
            remedy=(
                f"Add {-margin} more member(s) or restrained support "
                f"component(s). Bracing a panel or fixing a roller in an "
                f"additional direction both count."
            ),
            measured_value=float(m + r),
            threshold=float(required),
            basis="Maxwell counting criterion, m + r >= 3n",
        ))

    if K_ff is not None and K_ff.size:
        _add_matrix_diagnostics(K_ff, report)

    return report


def _add_matrix_diagnostics(K_ff: np.ndarray, report: StabilityReport) -> None:
    """Eigenvalue and conditioning analysis of the free-DOF submatrix."""
    n = K_ff.shape[0]

    if n > MAX_DOF_FOR_EIGEN_ANALYSIS:
        # Too large for a full decomposition; use a cheap 1-norm estimate.
        try:
            cond = float(np.linalg.cond(K_ff, p=1))
        except (np.linalg.LinAlgError, ValueError):
            cond = float("inf")
        report.condition_number = cond
        _add_conditioning_diagnostic(cond, report)
        return

    try:
        eigenvalues = np.linalg.eigvalsh(K_ff)
    except np.linalg.LinAlgError:
        report.diagnostics.append(Diagnostic(
            code=DiagnosticCode.SINGULAR_MATRIX,
            severity=Severity.ERROR,
            title="Stiffness matrix could not be decomposed",
            explanation=(
                "The eigenvalue decomposition of the free-DOF stiffness "
                "matrix failed, which indicates a degenerate or non-finite "
                "matrix rather than a merely ill-conditioned one."
            ),
            remedy="Check for zero-length members, zero areas or non-finite coordinates.",
            basis="numpy.linalg.eigvalsh failure",
        ))
        return

    report.eigen_analysis_performed = True
    lambda_max = float(np.max(np.abs(eigenvalues)))
    lambda_min = float(np.min(eigenvalues))

    if lambda_max <= 0.0:
        report.condition_number = float("inf")
        return

    zero_tol = ZERO_EIGENVALUE_RATIO * lambda_max
    zero_modes = int(np.sum(eigenvalues < zero_tol))
    report.n_zero_modes = zero_modes
    report.condition_number = (
        float(lambda_max / lambda_min) if lambda_min > 0 else float("inf")
    )

    if zero_modes > 0:
        report.diagnostics.append(Diagnostic(
            code=DiagnosticCode.UNSTABLE_MECHANISM,
            severity=Severity.ERROR,
            title=f"{zero_modes} rigid-body / mechanism mode(s) detected",
            explanation=(
                f"The free-DOF stiffness matrix has {zero_modes} eigenvalue(s) "
                f"at or below {zero_tol:.3e} (largest eigenvalue "
                f"{lambda_max:.3e}). Each zero eigenvalue is one independent "
                f"way the structure can displace without storing any strain "
                f"energy — a rigid-body motion or an internal mechanism. "
                f"Such a structure has no unique equilibrium solution: any "
                f"multiple of that mode can be added to a solution and it "
                f"remains a solution."
            ),
            remedy=(
                "Add restraint or bracing in the direction the structure is "
                "free to move. If the Maxwell count is already satisfied, the "
                "problem is arrangement, not quantity — look for collinear "
                "members or an unbraced sub-assembly."
            ),
            measured_value=float(zero_modes),
            threshold=0.0,
            basis="Eigenvalue null-space count of K_ff",
        ))

    _add_conditioning_diagnostic(report.condition_number, report)


def _add_conditioning_diagnostic(cond: float | None, report: StabilityReport) -> None:
    if cond is None or not np.isfinite(cond):
        report.diagnostics.append(Diagnostic(
            code=DiagnosticCode.SINGULAR_MATRIX,
            severity=Severity.ERROR,
            title="Singular stiffness matrix",
            explanation=(
                "The condition number is infinite: the stiffness matrix has "
                "no inverse. The structure is a mechanism, or a DOF has zero "
                "stiffness because nothing connects to it."
            ),
            remedy="Add supports or members to remove the free motion.",
            basis="Condition number of K_ff",
        ))
        return

    if cond > EFFECTIVELY_SINGULAR_THRESHOLD:
        report.diagnostics.append(Diagnostic(
            code=DiagnosticCode.NEAR_SINGULAR_MATRIX,
            severity=Severity.ERROR,
            title="Near-singular stiffness matrix",
            explanation=(
                f"Condition number {cond:.3e} exceeds {EFFECTIVELY_SINGULAR_THRESHOLD:.0e}. "
                f"float64 carries about 16 significant digits, so a solve "
                f"here loses essentially all of them. The matrix may still "
                f"factor and return numbers, but those numbers are dominated "
                f"by round-off and must not be trusted. This is more "
                f"dangerous than an outright failure, because the output "
                f"looks like a result."
            ),
            remedy=(
                "The structure is almost a mechanism — commonly a very "
                "slender bracing member, near-collinear members, or extreme "
                "stiffness ratios between adjacent elements."
            ),
            measured_value=cond,
            threshold=EFFECTIVELY_SINGULAR_THRESHOLD,
            basis="kappa(K_ff) vs float64 precision limit",
        ))
    elif cond > ILL_CONDITIONED_THRESHOLD:
        report.diagnostics.append(Diagnostic(
            code=DiagnosticCode.ILL_CONDITIONED,
            severity=Severity.WARNING,
            title="Ill-conditioned stiffness matrix",
            explanation=(
                f"Condition number {cond:.3e} exceeds {ILL_CONDITIONED_THRESHOLD:.0e}. "
                f"Roughly log10(kappa) = {np.log10(cond):.1f} of the ~16 "
                f"available significant digits are lost in the solve. The "
                f"results are probably usable but their precision is reduced, "
                f"and small changes in input may produce disproportionate "
                f"changes in output."
            ),
            remedy=(
                "Check for extreme stiffness ratios — e.g. a very stiff chord "
                "next to a very flexible tie — or near-collinear geometry."
            ),
            measured_value=cond,
            threshold=ILL_CONDITIONED_THRESHOLD,
            basis="kappa(K_ff) vs float64 precision limit",
        ))


def explain_solve_failure(structure: Structure, K_ff: np.ndarray | None) -> list[Diagnostic]:
    """
    Called when the factorisation fails. Runs every check and returns the
    engineering explanations, so the user is told WHY rather than being
    handed 'matrix is not positive definite'.
    """
    found = check_topology(structure)
    report = analyze_stability(structure, K_ff=K_ff)
    found.extend(report.diagnostics)

    if not found:
        found.append(Diagnostic(
            code=DiagnosticCode.SINGULAR_MATRIX,
            severity=Severity.ERROR,
            title="Stiffness matrix is singular for an undetermined reason",
            explanation=(
                "The factorisation failed, but the topology checks, the "
                "Maxwell count and the eigenvalue test did not identify a "
                "specific cause. This is reported honestly rather than "
                "guessing: the model is unsolvable, but NeuroPlan cannot "
                "currently name the defect."
            ),
            remedy="Inspect support conditions and member connectivity manually.",
            basis="No diagnostic matched",
        ))
    return found


def format_diagnostics(diagnostics: list[Diagnostic]) -> str:
    """Human-readable block for an exception message."""
    lines = []
    for d in diagnostics:
        lines.append(f"[{d.severity.value.upper()}] {d.title}")
        lines.append(f"  {d.explanation}")
        if d.remedy:
            lines.append(f"  Fix: {d.remedy}")
        if d.basis:
            lines.append(f"  Basis: {d.basis}")
    return "\n".join(lines)
