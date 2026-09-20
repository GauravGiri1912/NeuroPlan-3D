"""
NeuroPlan-3D — Engineering Analysis Report (Priority 12)

Compiles every part of an analysis into one inspectable document.

THE CENTRAL RULE
────────────────────────────────────────────────────────────────────────
Every value carries a classification, and the classification is part of
the value — not a footnote:

    COMPUTED     produced by the deterministic solver from the model
    MEASURED     a real experimental reading from a cited dataset
    DERIVED      calculated from COMPUTED/MEASURED values by a stated
                 formula
    ASSUMED      chosen by NeuroPlan or the user; not measured, not
                 derived from anything
    NOT_MODELED  the quantity is absent from the model entirely

NOT_MODELED entries are emitted deliberately. A report that simply omits
what it cannot do reads as complete; one that lists its own gaps lets a
reader judge whether the analysis is fit for their purpose. The
limitation list is therefore part of the report body, not an appendix.
"""
from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum

from ...models.structure import (
    Structure, EngineeringSpec, AnalysisResults, MATERIAL_LIBRARY,
)
from ..evidence import SOFTWARE_VERSION
from ..fea.load_cases import LoadCaseType
from .buckling import BucklingScreeningReport
from .sensitivity import SensitivityReport


class ValueClass(str, Enum):
    COMPUTED = "computed"
    MEASURED = "measured"
    DERIVED = "derived"
    ASSUMED = "assumed"
    NOT_MODELED = "not_modeled"


@dataclass
class ReportItem:
    label: str
    value: str
    classification: ValueClass
    unit: str = ""
    source: str = ""
    note: str = ""


@dataclass
class ReportSection:
    key: str
    title: str
    items: list[ReportItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, label: str, value, classification: ValueClass,
            unit: str = "", source: str = "", note: str = "") -> None:
        self.items.append(ReportItem(
            label=label,
            value=value if isinstance(value, str) else _format(value),
            classification=classification, unit=unit, source=source, note=note,
        ))


@dataclass
class EngineeringReport:
    simulation_id: str
    generated_at: str
    software_version: str
    python_version: str
    sections: list[ReportSection] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    positioning: str = (
        "NeuroPlan-3D is an AI-assisted, deterministic, evidence-traceable "
        "structural design and verification environment. It is NOT a "
        "certified commercial structural-design package, and no output here "
        "constitutes a design certification or a statement that a physical "
        "structure is safe to build."
    )

    def section(self, key: str) -> ReportSection | None:
        return next((s for s in self.sections if s.key == key), None)

    def classification_counts(self) -> dict[str, int]:
        counts = {c.value: 0 for c in ValueClass}
        for s in self.sections:
            for item in s.items:
                counts[item.classification.value] += 1
        return counts


def _format(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return str(value)
        return f"{value:,.4g}"
    return str(value)


def _simulation_id(structure: Structure, spec: EngineeringSpec) -> str:
    """
    Deterministic content hash: the same model always yields the same ID,
    so two reports claiming the same ID describe the same analysis.
    """
    payload = {
        "type": getattr(spec.structure_type, "value", str(spec.structure_type)),
        "span": spec.span, "height": spec.height, "width": spec.width,
        "panels": spec.num_panels, "load": spec.primary_load,
        "lat_x": spec.lateral_load_x, "lat_z": spec.lateral_load_z,
        "material": spec.material_key, "section": spec.section_key,
        "nodes": [(n.id, n.x, n.y, n.z) for n in structure.nodes],
        "members": [(m.id, m.node_i, m.node_j) for m in structure.members],
    }
    blob = json.dumps(payload, sort_keys=True).encode()
    return "NP3D-" + hashlib.sha256(blob).hexdigest()[:16].upper()


def build_report(
    structure: Structure,
    spec: EngineeringSpec,
    results: AnalysisResults,
    buckling: BucklingScreeningReport | None = None,
    sensitivity: SensitivityReport | None = None,
    code_report=None,
    validation=None,
) -> EngineeringReport:
    """
    Assemble the full report. Optional analyses that were not run are
    reported as NOT AVAILABLE sections rather than omitted.
    """
    report = EngineeringReport(
        simulation_id=_simulation_id(structure, spec),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        software_version=SOFTWARE_VERSION,
        python_version=platform.python_version(),
    )

    # ---- Requirements ----
    s = ReportSection("requirements", "1. Requirements")
    s.add("Raw requirement", spec.raw_input or "(not supplied)",
          ValueClass.ASSUMED if not spec.raw_input else ValueClass.MEASURED,
          source="User input")
    s.add("Structure type", getattr(spec.structure_type, "value", spec.structure_type),
          ValueClass.ASSUMED, source="Parsed/selected from the requirement")
    s.add("Span", spec.span, ValueClass.ASSUMED, "m")
    s.add("Height", spec.height, ValueClass.ASSUMED, "m")
    s.add("Width", spec.width, ValueClass.ASSUMED, "m")
    s.add("Panels", spec.num_panels, ValueClass.ASSUMED)
    s.add("Safety factor", spec.safety_factor, ValueClass.ASSUMED)
    s.add("Displacement limit", f"L/{spec.max_displacement_ratio:g}", ValueClass.ASSUMED)
    for default in spec.defaults_applied:
        s.notes.append(f"DEFAULT APPLIED: {default}")
    report.sections.append(s)

    # ---- Geometry ----
    s = ReportSection("geometry", "2. Geometry")
    s.add("Nodes", len(structure.nodes), ValueClass.COMPUTED)
    s.add("Members", len(structure.members), ValueClass.COMPUTED)
    s.add("Supports", len(structure.supports), ValueClass.COMPUTED)
    s.add("Degrees of freedom", results.dof_count, ValueClass.COMPUTED,
          note="3 translational DOF per node")
    s.add("Genuinely spatial", results.is_spatial, ValueClass.COMPUTED,
          note="True when any node has z != 0")
    xs = [n.x for n in structure.nodes] or [0.0]
    ys = [n.y for n in structure.nodes] or [0.0]
    zs = [n.z for n in structure.nodes] or [0.0]
    s.add("Bounding box", f"{max(xs)-min(xs):.3f} x {max(ys)-min(ys):.3f} x {max(zs)-min(zs):.3f}",
          ValueClass.COMPUTED, "m")
    report.sections.append(s)

    # ---- Materials & sections ----
    s = ReportSection("materials", "3. Materials and Sections")
    for key in sorted({m.material_key for m in structure.members}):
        material = MATERIAL_LIBRARY.get(key)
        if material is None:
            s.add(f"Material {key}", "UNKNOWN", ValueClass.NOT_MODELED,
                  note="Not in the material library; contributes no weight or stiffness.")
            continue
        s.add(f"{material.name} — E", material.E / 1e9, ValueClass.ASSUMED, "GPa",
              source="MATERIAL_LIBRARY (handbook value)")
        s.add(f"{material.name} — yield", material.yield_stress / 1e6,
              ValueClass.ASSUMED, "MPa", source="MATERIAL_LIBRARY (handbook value)")
        s.add(f"{material.name} — density", material.density, ValueClass.ASSUMED,
              "kg/m^3", source="MATERIAL_LIBRARY (handbook value)")
    sections = {(m.section.outer_diameter, m.section.wall_thickness)
                for m in structure.members}
    for od, t in sorted(sections):
        from ...models.structure import CrossSection
        cs = CrossSection(od, t)
        s.add(f"CHS {od*1000:.1f} x {t*1000:.1f}",
              f"A = {cs.area*1e4:.2f} cm^2, I = {cs.moment_of_inertia*1e8:.2f} cm^4, "
              f"r = {cs.radius_of_gyration*1000:.1f} mm",
              ValueClass.DERIVED, source="Computed from OD and wall thickness")
    report.sections.append(s)

    # ---- Loads and load cases ----
    s = ReportSection("loads", "4. Loads and Load Cases")
    summary = results.load_summary
    if summary is not None:
        s.add("Combination", summary.combination_name, ValueClass.ASSUMED,
              source=summary.combination_source)
        s.add("Total applied Fx", summary.total_applied_fx, ValueClass.COMPUTED, "N")
        s.add("Total applied Fy", summary.total_applied_fy, ValueClass.COMPUTED, "N")
        s.add("Total applied Fz", summary.total_applied_fz, ValueClass.COMPUTED, "N")
        for case in summary.cases:
            if case.supported:
                state = "ACTIVE" if case.active else "supported, not applied"
                klass = ValueClass.COMPUTED if case.active else ValueClass.ASSUMED
            else:
                state = "NOT SUPPORTED"
                klass = ValueClass.NOT_MODELED
            s.add(f"Case {case.case_type}", f"{state} (factor {case.factor:g}, "
                  f"R = {case.resultant_fx:,.0f}/{case.resultant_fy:,.0f}/"
                  f"{case.resultant_fz:,.0f} N)",
                  klass, source=case.formulation, note=case.limitations)
        sw = summary.self_weight
        if sw is not None and sw.included:
            s.add("Self-weight mass", sw.total_mass_kg, ValueClass.COMPUTED, "kg",
                  source="sum(rho*A*L) over all members")
            s.add("Self-weight force", sw.total_weight_n, ValueClass.DERIVED, "N",
                  source=f"mass * g, g = {sw.gravity} m/s^2")
            s.add("Applied as nodal load", sw.applied_weight_n, ValueClass.COMPUTED, "N",
                  note="Must equal the self-weight force; half of each member to each end node.")
            s.add("Mass/applied consistency", sw.consistent, ValueClass.COMPUTED)
        else:
            s.add("Self-weight", "EXCLUDED — structure analysed as weightless",
                  ValueClass.NOT_MODELED)
    report.sections.append(s)

    # ---- Solver ----
    s = ReportSection("solver", "5. Solver")
    s.add("Method", "Direct Stiffness Method, linear elastic", ValueClass.ASSUMED)
    s.add("Element", "3D pin-jointed bar, 3 translational DOF per node", ValueClass.ASSUMED)
    s.add("Factorisation", "Cholesky (scipy cho_factor/cho_solve)", ValueClass.ASSUMED)
    s.add("Solve time", results.solve_time_ms, ValueClass.COMPUTED, "ms")
    stability = results.stability
    if stability is not None:
        s.add("Maxwell count m+r vs 3n",
              f"{stability.n_members}+{stability.n_reaction_components} vs {stability.required_dof}",
              ValueClass.COMPUTED, source="m + r >= 3n")
        s.add("Determinacy", stability.determinacy, ValueClass.DERIVED)
        s.add("Rigid-body / mechanism modes",
              stability.n_zero_modes if stability.n_zero_modes is not None else "not assessed",
              ValueClass.COMPUTED, source="Eigenvalue null-space count of K_ff")
        s.add("Condition number", stability.condition_number, ValueClass.COMPUTED,
              note="log10(kappa) digits of precision lost in the solve")
        for diagnostic in stability.diagnostics:
            s.notes.append(f"[{diagnostic.severity.value.upper()}] {diagnostic.title}: "
                           f"{diagnostic.explanation}")
    report.sections.append(s)

    # ---- Results ----
    s = ReportSection("results", "6. Results")
    max_stress = max((abs(m.stress) for m in results.member_results), default=0.0)
    s.add("Max stress", max_stress / 1e6, ValueClass.COMPUTED, "MPa")
    s.add("Max stress ratio", results.diagnosis.max_stress_ratio, ValueClass.DERIVED,
          source="|stress| / (yield / safety factor)")
    s.add("Max displacement", results.diagnosis.max_displacement_mm,
          ValueClass.COMPUTED, "mm")
    s.add("Total weight", results.total_weight_kg, ValueClass.COMPUTED, "kg")
    s.add("Failed members", results.diagnosis.failed_member_count, ValueClass.COMPUTED)
    s.add("Failed nodes", results.diagnosis.failed_node_count, ValueClass.COMPUTED)

    tension = [m for m in results.member_results if m.axial_force > 0]
    compression = [m for m in results.member_results if m.axial_force < 0]
    s.add("Members in tension", len(tension), ValueClass.COMPUTED)
    s.add("Members in compression", len(compression), ValueClass.COMPUTED)

    total_r = [sum(r.rx for r in results.reactions),
               sum(r.ry for r in results.reactions),
               sum(r.rz for r in results.reactions)]
    s.add("Sum of reactions", f"{total_r[0]:,.1f} / {total_r[1]:,.1f} / {total_r[2]:,.1f}",
          ValueClass.COMPUTED, "N", source="R = K.u - F")
    report.sections.append(s)

    # ---- Verification ----
    s = ReportSection("verification", "7. Verification")
    checks = results.checks
    for label, value in (
        ("Solver completed", checks.solver),
        ("Geometry valid", checks.geometry),
        ("Boundary conditions", checks.boundary_conditions),
        ("Global equilibrium", checks.equilibrium),
        ("Stress within allowable", checks.stress),
        ("Displacement within limit", checks.displacement),
    ):
        s.add(label, value, ValueClass.COMPUTED)
    equilibrium = results.equilibrium
    s.add("Force residual", getattr(equilibrium, "max_force_residual", "n/a"),
          ValueClass.COMPUTED, "N", source="sum(applied) + sum(reactions)")
    s.notes.append(
        "These checks verify the COMPUTATION — that the arithmetic is "
        "self-consistent. They do not establish that a physical structure "
        "built to this model would be safe."
    )
    report.sections.append(s)

    # ---- Buckling ----
    s = ReportSection("buckling", "8. Buckling Screening")
    if buckling is None:
        s.add("Buckling screening", "NOT RUN", ValueClass.NOT_MODELED)
    else:
        s.add("Compression members", buckling.n_compression, ValueClass.COMPUTED)
        s.add("Exceeding Euler load", buckling.n_failed, ValueClass.COMPUTED)
        s.add("In the unconservative range", buckling.n_unconservative,
              ValueClass.COMPUTED,
              note="Below lambda_c Euler OVERESTIMATES capacity; a pass here is not adequacy.")
        s.add("Max slenderness KL/r", buckling.max_slenderness, ValueClass.DERIVED)
        s.add("Effective length factor", "K = 1.0", ValueClass.ASSUMED,
              source=buckling.k_basis)
        for limitation in buckling.method_limitations:
            s.notes.append(f"NOT MODELLED: {limitation}")
    report.sections.append(s)

    # ---- Code checks ----
    s = ReportSection("code", "9. Design Code Checks")
    if code_report is None:
        s.add("Design code check", "NOT RUN", ValueClass.NOT_MODELED)
    else:
        s.add("Code", f"{code_report.code}:{code_report.edition}", ValueClass.ASSUMED,
              source=code_report.code_title)
        s.add("Scope", code_report.title, ValueClass.ASSUMED)
        s.add("Failed checks", code_report.n_failed, ValueClass.COMPUTED)
        s.add("Max D/C ratio", code_report.max_dc_ratio, ValueClass.DERIVED)
        s.add("Governing member", code_report.governing_member_id, ValueClass.COMPUTED)
        s.notes.append(code_report.compliance_disclaimer)
        for clause in code_report.unsupported_clauses:
            s.notes.append(f"NOT IMPLEMENTED: {clause}")
    report.sections.append(s)

    # ---- Sensitivity ----
    s = ReportSection("sensitivity", "10. Sensitivity")
    if sensitivity is None:
        s.add("Sensitivity study", "NOT RUN", ValueClass.NOT_MODELED)
    else:
        s.add("Method", sensitivity.method, ValueClass.ASSUMED)
        s.add("Perturbation", sensitivity.perturbation * 100, ValueClass.ASSUMED, "%")
        s.add("Statistical", sensitivity.is_statistical, ValueClass.COMPUTED,
              note=sensitivity.statistical_disclaimer)
        for parameter in sensitivity.parameters:
            if parameter.failed:
                s.add(parameter.label, "UNAVAILABLE", ValueClass.NOT_MODELED,
                      note=parameter.failure_reason)
                continue
            disp = parameter.outputs.get("max_displacement_mm")
            if disp:
                s.add(f"{parameter.label} -> displacement",
                      f"{disp.minimum:.4g} .. {disp.maximum:.4g} mm "
                      f"({disp.change_percent:.1f}% span, S = {disp.normalised_slope:+.3f})",
                      ValueClass.COMPUTED)
        for output, dominant in sensitivity.dominant.items():
            s.notes.append(f"Dominant parameter for {output}: {dominant}")
        s.notes.append(sensitivity.statistical_disclaimer)
        s.notes.append(sensitivity.interaction_limitation)
    report.sections.append(s)

    # ---- Experimental validation ----
    s = ReportSection("validation", "11. Experimental Reference Comparison")
    if validation is None:
        s.add("Experimental comparison", "NOT INCLUDED IN THIS RUN",
              ValueClass.NOT_MODELED,
              note="See the Validation Library for the standalone steel-truss comparison.")
    else:
        s.add("State", getattr(validation.state, "value", validation.state),
              ValueClass.MEASURED)
        independence = getattr(validation, "independence", None)
        if independence is not None:
            s.add("Evidence independence", independence.headline, ValueClass.DERIVED,
                  source=independence.standard_reference, note=independence.explanation)
        if validation.summary:
            s.add("MAE", validation.summary.mae, ValueClass.DERIVED, "mm")
            s.add("Max relative error",
                  (validation.summary.max_relative_error or 0) * 100,
                  ValueClass.DERIVED, "%")
        s.notes.append(validation.criterion_note)
    s.notes.append(
        "The experimental comparison validates the SOLVER against one "
        "laboratory specimen. It says nothing about the structure analysed "
        "in this report."
    )
    report.sections.append(s)

    # ---- Limitations ----
    report.limitations = _limitations(results, buckling, code_report, sensitivity)
    return report


def _limitations(results, buckling, code_report, sensitivity) -> list[str]:
    """
    The honest gap list. Items are removed only when the corresponding
    physics is genuinely implemented, never to make the list shorter.
    """
    limitations = [
        "Linear elastic analysis only — no material nonlinearity (no yielding, "
        "plastic redistribution or strain hardening is modelled).",
        "Small-displacement (first-order) theory — no geometric nonlinearity, "
        "no P-delta, no large-deflection effects.",
        "Pin-jointed truss formulation — members carry AXIAL FORCE ONLY. No "
        "bending moments, no shear, no torsion, no rotational DOF.",
        "Connections are not modelled: joints are idealised frictionless pins "
        "with no gusset plates, bolts, welds, slip or eccentricity.",
        "No dynamic, modal, seismic or time-dependent analysis. All loads are "
        "static.",
        "No fatigue assessment — no stress-cycle spectrum or detail category.",
        "No foundation or soil-structure interaction; supports are ideal.",
        "No member imperfections: no initial out-of-straightness, residual "
        "stress or fabrication tolerance.",
        "No fire, corrosion, creep or durability assessment.",
    ]

    summary = results.load_summary
    if summary is None or summary.self_weight is None or not summary.self_weight.included:
        limitations.append(
            "Self-weight is NOT included in this run — the structure was "
            "analysed as weightless."
        )
    else:
        limitations.append(
            "Self-weight covers the modelled members only: no decking, "
            "cladding, services, connection hardware or other non-structural mass."
        )

    if summary is not None:
        for case in summary.cases:
            if not case.supported:
                limitations.append(f"Load case {case.case_type}: {case.unsupported_reason}")

    if buckling is None:
        limitations.append("Buckling was not screened in this run.")
    else:
        limitations.append(
            "Buckling is SCREENED, not analysed: elastic Euler only, no "
            "lateral-torsional buckling, no local/plate buckling, no "
            "combined axial+bending interaction."
        )
        if buckling.n_unconservative:
            limitations.append(
                f"{buckling.n_unconservative} compression member(s) fall below "
                f"the elastic transition slenderness, where the Euler screen "
                f"is UNCONSERVATIVE. A code column curve governs there."
            )

    if code_report is None:
        limitations.append("No design-code check was run.")
    else:
        limitations.append(code_report.compliance_disclaimer)

    if sensitivity is None:
        limitations.append("No sensitivity study was run for this analysis.")
    else:
        limitations.append(sensitivity.statistical_disclaimer)

    return limitations


def report_to_dict(report: EngineeringReport) -> dict:
    """Serialisable form for the API and for export."""
    return asdict(report)
