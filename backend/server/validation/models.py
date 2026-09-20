"""
NeuroPlan-3D — Experimental Validation Data Models

These types exist to make one thing structurally impossible: displaying an
experimental (measured) number without saying where it came from, or
confusing it with a NeuroPlan-computed number.

Design rule: every field that holds an external value is paired with a
`Provenance` record. A field with no defensible source is not populated —
it is represented as `None` with a `ParameterStatus.MISSING` /
`ASSUMED` / `DERIVED` tag, never silently invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ParameterStatus(str, Enum):
    """How a reconstructed model parameter relates to the source material."""
    SOURCED = "sourced"        # directly stated in the dataset/publication, with a page/figure reference
    DERIVED = "derived"        # computed or inferred from sourced values via an explicit, stated method
    ASSUMED = "assumed"        # not stated; a reasoned engineering assumption, lower confidence
    MISSING = "missing"        # required but unavailable — the field is left unpopulated


class ValidationState(str, Enum):
    """
    States for "Real-World Validation" — replaces a single N/A flag.

    NOT_AVAILABLE       — no experimental dataset is attached to this project at all.
    REFERENCE_AVAILABLE — a dataset/case exists but no comparison has been run yet.
    REFERENCE_COMPARED  — NeuroPlan results have been compared against measurements.
    CRITERION_MET       — a criterion defined BEFORE evaluation, and the comparison satisfies it.
    CRITERION_NOT_MET   — same, but the comparison fails it.
    MODEL_NOT_APPLICABLE— the experiment requires physics outside the solver's modeling
                           assumptions (e.g. post-damage bending/torsion in a pin-jointed
                           axial-truss solver); no comparison is scientifically meaningful.

    REFERENCE_COMPARED never auto-promotes to CRITERION_MET — that requires an
    explicit, pre-declared AcceptanceCriterion.
    """
    NOT_AVAILABLE = "not_available"
    REFERENCE_AVAILABLE = "reference_available"
    REFERENCE_COMPARED = "reference_compared"
    CRITERION_MET = "criterion_met"
    CRITERION_NOT_MET = "criterion_not_met"
    MODEL_NOT_APPLICABLE = "model_not_applicable"


class ParameterRole(str, Enum):
    """
    Which part of the model a parameter controls.

    The roles are exhaustive over the things that can be tuned to make a
    comparison look good. Every one of them must appear in a case's
    parameter inventory, so that "nothing was calibrated" is a checked
    statement about a complete list rather than an absence of records.
    """
    GEOMETRY = "geometry"
    MATERIAL = "material"
    CROSS_SECTION = "cross_section"
    BOUNDARY_CONDITION = "boundary_condition"
    LOAD = "load"
    SENSOR_MAPPING = "sensor_mapping"


@dataclass
class ModelParameter:
    """
    One reconstructed model input, and — the point of this record —
    whether the measured results were consulted when choosing it.

    `selected_using_measurements` is the calibration flag. It is
    independent of `status`: a parameter can be ASSUMED without being
    calibrated (a standard handbook value nobody tuned), and in principle
    DERIVED while being calibrated. Conflating the two is what lets a
    tuned model be presented as a validated one.
    """
    name: str
    role: ParameterRole
    status: ParameterStatus
    selected_using_measurements: bool
    value_summary: str = ""
    source_reference: str = ""
    note: str = ""


class EvidenceIndependence(str, Enum):
    """
    Whether a comparison is independent evidence, per the calibration /
    validation distinction in ASME V&V 10 and the NAFEMS V&V guidance.

    INDEPENDENT  — no model parameter was selected using the measured
                   results. The comparison is a genuine predictive test.
    CALIBRATED   — at least one parameter was chosen with reference to the
                   measurements. The agreement is partly circular and is
                   NOT independent validation evidence, however small the
                   error is.
    NOT_ASSESSED — no parameter inventory was supplied, so independence
                   cannot be claimed. Deliberately distinct from
                   INDEPENDENT: absence of recorded calibration is not
                   evidence that none occurred.
    """
    INDEPENDENT = "independent"
    CALIBRATED = "calibrated"
    NOT_ASSESSED = "not_assessed"


@dataclass
class IndependenceAssessment:
    """Result of scanning a case's full parameter inventory."""
    verdict: EvidenceIndependence
    headline: str
    explanation: str
    standard_reference: str
    calibrated_parameters: list[ModelParameter] = field(default_factory=list)
    independent_parameters: list[ModelParameter] = field(default_factory=list)
    missing_roles: list[ParameterRole] = field(default_factory=list)


@dataclass
class Provenance:
    """Where one value came from, precisely enough to re-find it."""
    source_type: str               # "experimental" | "publication" | "derived" | "neuroplan"
    status: ParameterStatus
    description: str = ""
    dataset: str = ""              # dataset title
    file: str = ""                 # exact file name within the dataset
    sheet: str = ""                # sheet/tab name, if applicable
    field: str = ""                # column/field name, if applicable
    publication: str = ""          # citation (journal/report), if from a paper
    page_or_figure: str = ""       # e.g. "Fig. 2, p.7" — where a human can verify this
    doi: str = ""
    license: str = ""
    retrieved: str = ""            # ISO date this was pulled from the source
    note: str = ""                 # free-text caveat, especially for DERIVED/ASSUMED


@dataclass
class DatasetMetadata:
    """Top-level citation/provenance for an entire experimental dataset."""
    title: str
    authors: list[str]
    institution: str
    doi: str
    license: str
    publication_date: str
    version: str
    repository: str
    files: list[str]
    description: str
    linked_publication_title: str = ""
    linked_publication_doi: str = ""
    linked_publication_url: str = ""
    retrieved: str = ""


@dataclass
class SensorDefinition:
    """One physical sensor, as documented in the source."""
    sensor_id: str
    sensor_type: str                # "displacement_transducer" | "strain_gauge"
    units: str
    physical_location: str          # human-readable, from the publication
    measures: str                   # "axial" | "axial_and_bending" | "unknown"
    provenance: Provenance


@dataclass
class ModelMapping:
    """
    Sensor → NeuroPlan model element, with an explicit confidence tag.

    This is the single most safety-critical mapping in the whole feature:
    a wrong sensor→node mapping silently produces a wrong "validation".
    Every mapping therefore carries its own status and a note explaining
    the reasoning, not just a bare node id.
    """
    sensor_id: str
    node_id: Optional[int] = None
    member_id: Optional[int] = None
    dof: str = ""                   # "UX" | "UY" | "UZ" | "axial_stress"
    status: ParameterStatus = ParameterStatus.ASSUMED
    reasoning: str = ""
    comparable: bool = True         # False => NOT COMPARABLE WITH CURRENT MODEL
    incomparable_reason: str = ""


@dataclass
class MeasurementPoint:
    """One experimental measurement, exactly as recorded — never modified."""
    sensor_id: str
    value: float
    units: str
    load_level_kn: Optional[float] = None
    condition: str = ""             # "UD" | "D" | scenario label
    provenance: Provenance = None   # type: ignore[assignment]


@dataclass
class AcceptanceCriterion:
    """
    A validation acceptance criterion, defined BEFORE the comparison is
    evaluated. If none is defensible, leave this unset — REFERENCE_COMPARED
    is reported instead of a fabricated PASS/FAIL threshold.
    """
    description: str
    metric: str                     # e.g. "relative_error"
    threshold: float
    source: str                     # where this threshold comes from
    defensible: bool = True


@dataclass
class ComparisonResult:
    """One experimental-vs-NeuroPlan comparison point."""
    sensor_id: str
    node_id: Optional[int]
    quantity: str                   # "vertical_displacement" | "axial_strain"
    experimental_value: float
    neuroplan_value: float
    units: str
    absolute_error: float
    relative_error: Optional[float]  # None if experimental_value == 0
    mapping_status: ParameterStatus
    mapping_note: str = ""


@dataclass
class ComparisonSummary:
    """Aggregate statistics over a set of ComparisonResults."""
    n_points: int
    mae: Optional[float] = None
    rmse: Optional[float] = None
    max_absolute_error: Optional[float] = None
    max_relative_error: Optional[float] = None
    r_squared: Optional[float] = None
    r_squared_note: str = ""
    uncertainty_note: str = (
        "Experimental uncertainty not provided / not incorporated."
    )


@dataclass
class ExperimentalCase:
    """
    One reconstructed, reproducible experimental case: geometry, materials,
    loads, supports and sensor mapping needed to run it through the actual
    NeuroPlan solver and compare against real measurements.
    """
    case_id: str
    title: str
    dataset: DatasetMetadata
    description: str
    load_setup_description: str
    applicable: bool                 # False => MODEL_NOT_APPLICABLE, with reason below
    inapplicability_reason: str = ""
    parameter_notes: list[str] = field(default_factory=list)  # human-readable MISSING/ASSUMED/DERIVED log
