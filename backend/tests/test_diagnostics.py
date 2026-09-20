"""
Priority 3 — Structural diagnostics.

Every defect is built deliberately and must be detected and NAMED. A test
that only asserts "an error was raised" would pass even if the message
were still 'matrix is not positive definite', which is exactly the
outcome this feature exists to remove.
"""
import numpy as np
import pytest

from server.core.fea.diagnostics import (
    DiagnosticCode, Severity, check_topology, analyze_stability,
    explain_solve_failure, format_diagnostics,
    ILL_CONDITIONED_THRESHOLD,
)
from server.core.fea.solver import solve, FEASolverError
from server.core.generator.topology import generate_structure
from server.models.structure import (
    EngineeringSpec, Structure, Node, Member, Support, SupportType,
    PointLoad, CrossSection,
)

SECTION = CrossSection(outer_diameter=0.114, wall_thickness=0.006)


def _codes(diagnostics) -> set:
    return {d.code for d in diagnostics}


def _triangle() -> Structure:
    """
    A minimal stable truss: 3 nodes, 3 members, pin + roller.

    The apex carries an OUT_OF_PLANE restraint because this is a 3-DOF
    solver: a planar triangle in 3D is free to swing out of its own plane
    unless Z is held. Maxwell then gives m + r = 3 + 6 = 9 = 3n, i.e.
    statically determinate.
    """
    return Structure(
        nodes=[Node(0, 0.0, 0.0, 0.0), Node(1, 4.0, 0.0, 0.0), Node(2, 2.0, 3.0, 0.0)],
        members=[
            Member(0, 0, 1, "A36", SECTION),
            Member(1, 1, 2, "A36", SECTION),
            Member(2, 2, 0, "A36", SECTION),
        ],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X),
            Support(node_id=2, support_type=SupportType.OUT_OF_PLANE),
        ],
        loads=[PointLoad(node_id=2, fy=-10_000.0)],
    )


# ─────────────────────────────────────────────
# Topology defects
# ─────────────────────────────────────────────

def test_zero_length_member_is_detected_and_explained():
    s = _triangle()
    s.nodes.append(Node(3, 2.0, 3.0, 0.0))       # coincident with node 2
    s.members.append(Member(3, 2, 3, "A36", SECTION))

    found = check_topology(s)
    assert DiagnosticCode.ZERO_LENGTH_MEMBER in _codes(found)

    d = next(x for x in found if x.code is DiagnosticCode.ZERO_LENGTH_MEMBER)
    assert d.severity is Severity.ERROR
    assert 3 in d.affected_members
    assert "AE/L" in d.explanation      # states the actual reason
    assert d.remedy


def test_duplicate_member_is_detected_in_either_orientation():
    s = _triangle()
    s.members.append(Member(3, 1, 0, "A36", SECTION))   # reverse of member 0

    found = check_topology(s)
    assert DiagnosticCode.DUPLICATE_MEMBER in _codes(found)
    d = next(x for x in found if x.code is DiagnosticCode.DUPLICATE_MEMBER)
    assert 3 in d.affected_members
    assert d.severity is Severity.WARNING   # solvable, but misleading


def test_disconnected_node_is_detected():
    s = _triangle()
    s.nodes.append(Node(9, 10.0, 10.0, 0.0))   # attached to nothing

    found = check_topology(s)
    assert DiagnosticCode.DISCONNECTED_NODE in _codes(found)
    d = next(x for x in found if x.code is DiagnosticCode.DISCONNECTED_NODE)
    assert 9 in d.affected_nodes


def test_split_assembly_is_detected_as_separate_pieces():
    s = _triangle()
    s.nodes += [Node(10, 20.0, 0.0, 0.0), Node(11, 24.0, 0.0, 0.0)]
    s.members.append(Member(10, 10, 11, "A36", SECTION))

    found = check_topology(s)
    codes = _codes(found)
    assert DiagnosticCode.DISCONNECTED_ASSEMBLY in codes
    assert DiagnosticCode.UNSUPPORTED_ASSEMBLY in codes

    d = next(x for x in found if x.code is DiagnosticCode.UNSUPPORTED_ASSEMBLY)
    assert set(d.affected_nodes) == {10, 11}


def test_clean_structure_produces_no_topology_diagnostics():
    assert check_topology(_triangle()) == []
    assert check_topology(generate_structure(EngineeringSpec())) == []


# ─────────────────────────────────────────────
# Maxwell counting criterion
# ─────────────────────────────────────────────

def test_maxwell_count_identifies_an_under_constrained_truss():
    """Remove a support component and the count must go deficient."""
    s = _triangle()
    s.supports = [Support(node_id=0, support_type=SupportType.PIN)]

    report = analyze_stability(s)
    assert report.counting_satisfied is False
    assert report.determinacy == "mechanism"
    assert DiagnosticCode.COUNTING_CRITERION_DEFICIENT in _codes(report.diagnostics)

    d = next(x for x in report.diagnostics
             if x.code is DiagnosticCode.COUNTING_CRITERION_DEFICIENT)
    assert "m + r >= 3n" in d.basis
    assert d.measured_value < d.threshold


def test_maxwell_count_reports_determinacy_for_a_normal_truss():
    report = analyze_stability(generate_structure(EngineeringSpec()))
    assert report.counting_satisfied
    assert report.determinacy in ("determinate", "indeterminate")
    assert report.counting_margin >= 0


def test_counting_criterion_is_not_claimed_to_prove_stability():
    """
    A satisfied count is necessary, not sufficient. The report must not
    assert stability from the count alone — that requires the eigen test.
    """
    report = analyze_stability(_triangle())          # no matrix supplied
    assert report.counting_satisfied
    assert report.eigen_analysis_performed is False
    assert report.n_zero_modes is None


# ─────────────────────────────────────────────
# Matrix-level diagnostics
# ─────────────────────────────────────────────

def test_zero_eigenvalue_is_reported_as_a_mechanism():
    """A matrix with a deliberate null space must be named a mechanism."""
    K = np.diag([1.0e9, 1.0e9, 0.0])
    report = analyze_stability(_triangle(), K_ff=K)

    assert report.n_zero_modes == 1
    assert DiagnosticCode.UNSTABLE_MECHANISM in _codes(report.diagnostics)
    d = next(x for x in report.diagnostics if x.code is DiagnosticCode.UNSTABLE_MECHANISM)
    assert "strain energy" in d.explanation


def test_ill_conditioned_matrix_is_flagged_as_a_warning_not_an_error():
    """Solvable but imprecise: the user should be warned, not blocked."""
    K = np.diag([1.0e9, 1.0e9 / (ILL_CONDITIONED_THRESHOLD * 10)])
    report = analyze_stability(_triangle(), K_ff=K)

    assert report.condition_number > ILL_CONDITIONED_THRESHOLD
    codes = _codes(report.diagnostics)
    assert DiagnosticCode.ILL_CONDITIONED in codes or \
           DiagnosticCode.NEAR_SINGULAR_MATRIX in codes


def test_well_conditioned_matrix_raises_no_conditioning_diagnostic():
    K = np.diag([1.0e9, 2.0e9, 3.0e9])
    report = analyze_stability(_triangle(), K_ff=K)

    assert report.n_zero_modes == 0
    assert report.condition_number == pytest.approx(3.0)
    codes = _codes(report.diagnostics)
    assert DiagnosticCode.ILL_CONDITIONED not in codes
    assert DiagnosticCode.NEAR_SINGULAR_MATRIX not in codes
    assert DiagnosticCode.UNSTABLE_MECHANISM not in codes


# ─────────────────────────────────────────────
# End-to-end: the solver must explain, not just fail
# ─────────────────────────────────────────────

def test_solver_error_names_the_defect_instead_of_a_matrix_message():
    """The whole point of Priority 3."""
    s = _triangle()
    s.nodes.append(Node(9, 10.0, 10.0, 0.0))     # orphan node

    with pytest.raises(FEASolverError) as exc:
        solve(s, EngineeringSpec())

    message = str(exc.value)
    assert "Disconnected node" in message
    assert "Fix:" in message
    assert "not positive definite" not in message


def test_under_constrained_structure_gets_an_engineering_explanation():
    s = _triangle()
    s.supports = [Support(node_id=0, support_type=SupportType.ROLLER_X)]

    with pytest.raises(FEASolverError) as exc:
        solve(s, EngineeringSpec())

    message = str(exc.value)
    assert "Maxwell" in message or "mechanism" in message.lower()
    assert "Fix:" in message


def test_explain_solve_failure_never_returns_an_empty_list():
    """
    Even when no specific check matches, the user must get a statement —
    and it must admit the cause is unidentified rather than inventing one.
    """
    found = explain_solve_failure(_triangle(), K_ff=np.eye(3))
    assert found
    text = format_diagnostics(found)
    assert "undetermined" in text.lower() or "singular" in text.lower()


def test_successful_solve_reports_conditioning():
    """Conditioning is measured on the success path, not only on failure."""
    results = solve(generate_structure(EngineeringSpec()), EngineeringSpec())
    stability = results.stability

    assert stability is not None
    assert stability.eigen_analysis_performed
    assert stability.n_zero_modes == 0
    assert np.isfinite(stability.condition_number)
    assert stability.condition_number < ILL_CONDITIONED_THRESHOLD


def test_duplicate_member_warning_does_not_block_a_solve():
    """A WARNING must not be escalated into a refusal to compute."""
    s = _triangle()
    s.members.append(Member(3, 1, 0, "A36", SECTION))

    results = solve(s, EngineeringSpec())
    codes = {d.code for d in results.stability.diagnostics}
    assert DiagnosticCode.DUPLICATE_MEMBER in codes
    assert results.diagnosis is not None
