"""
NeuroPlan-3D — Experimental Case: Steel Truss Bridge, Undamaged Baseline
(DS "Loss of a Lower Chord" test series, UD/undamaged state, Load Setup-1)

Reconstructed from primary sources actually read for this integration:

  [G] Fig. 2 "Final design of the bridge specimen" — Supplementary
      Information PDF, p.7 (Nature paper 10.1038/s41586-025-09300-8).
      A fully dimensioned drawing: plan top/bottom views, North/South
      lateral (elevation) views, and cross-section, with member-type
      labels (C1/C2 chords, M1-M5 verticals, D1-D5 diagonals, DP/DS/VI
      bracing) placed directly on the drawing.
  [T1] Table 1 "Tensile mechanical properties of the steel of the bridge",
      Supplementary Information p.7.
  [T2] Table 2 "Areas and inertias of the original profiles...", p.8.
  [F4] Fig. 4 "Average stress-strain curve...", p.9 — the coupon
      properties explicitly captioned as "used later in the computational
      models": E = 207,639.8 MPa, F_y = 326.6 MPa.
  [F6] Fig. 6 "Load setup of the test", p.10 — Load Setup-1: four 20 kN
      point loads, symmetric about the bridge centreline.
  [S13] Section 1.3 "Monitoring", p.12 — sensor counts and general
      placement description (14 displacement transducers at lower-chord
      panel points, 7 per side).
  [FIG15] Fig. 15 "Vertical displacement results" (DS: Loss of a lower
      chord), p.17-18 — the published UD/D sensor table used to
      cross-check the raw dataset file.

WHAT IS SOURCED VS DERIVED VS ASSUMED
--------------------------------------
Every geometric, material and load parameter below is SOURCED directly
from [G]/[T1]/[T2]/[F4]/[F6] with a page/figure reference — these are not
invented. Two things are NOT independently confirmed from a dimensioned
source and are explicitly flagged:

1. The exact two top-chord nodes that receive the four 20 kN loads
   (DERIVED: read visually from Fig. 6's isometric sketch as the two
   panel points immediately flanking mid-span; Fig. 6 has no dimension
   callout for the load positions).
2. The precise sensor-ID <-> node-ID correspondence for sensors 1-7 /
   8-14 (ASSUMED — see "SENSOR MAPPING" below).

SENSOR MAPPING — HOW IT WAS CHOSEN, AND WHY THAT MATTERS
---------------------------------------------------------
[S13] narrows the sensor positions but does not fix them. It states the
7 transducers per side sit "at the lower nodes... at the point of
connection between the lower chord, the vertical and the diagonal". In
this specimen all 11 INTERIOR lower-chord panel points (nodes 1-11)
satisfy that description, so the source constrains the candidates to
symmetric 7-subsets of {1..11} containing mid-span (node 6). There are
exactly 10 such layouts. No published table selects among them.

All 10 were scored against the measured Fig. 15 / raw-dataset profile
using the real production solver (see
`test_sensor_mapping_candidates_rule_out_the_consecutive_layout`):

  nodes                  MAE      max rel err
  [1, 3, 4, 6, 8, 9, 11] 0.609 mm     23.9%
  [1, 3, 5, 6, 7, 9, 11] 0.820 mm     23.9%   <-- USED
  [2, 3, 4, 6, 8, 9, 10] 0.892 mm     71.2%
  ... (6 further layouts, 0.99-1.54 mm) ...
  [3, 4, 5, 6, 7, 8, 9]  2.177 mm    172.4%   <-- previously used, RULED OUT

Two conclusions, of different strength:

  (a) STRONG: the consecutive-node layout [3..9] used in the first
      version of this file is wrong. It is the worst of all 10
      candidates by a wide margin and predicts 6.04 mm where 2.48 mm
      was measured. This was a reconstruction error on our side, not a
      disagreement between the solver and the experiment.

  (b) WEAK: the data alone cannot uniquely select among the remaining
      9. The layout used here, [1, 3, 5, 6, 7, 9, 11], is NOT the
      lowest-MAE candidate. It was chosen because it is the only
      regular layout among the leaders — alternate panel points with
      added resolution at mid-span — which is how such a test is
      normally instrumented. Selecting [1, 3, 4, 6, 8, 9, 11] instead,
      purely because its MAE is 0.2 mm lower, would be fitting an
      irregular sensor layout to the residuals.

CONSEQUENCE FOR THE VALIDATION CLAIM: because the mapping was informed
by the measurements, the resulting agreement is NOT independent
evidence that the solver is correct. It cannot be used to claim
validation. Only conclusion (a) — that a specific candidate layout is
inconsistent with the data — is a genuine inference. For this reason,
and because the source defines no numeric acceptance criterion, this
case is reported as REFERENCE_COMPARED and never CRITERION_MET — see
`server/validation/state.py`.

The mid-span identification (sensor 4 / sensor 11 <-> node 6) is the one
high-confidence element: it is the unambiguous peak of a symmetric
curve and is the same node under all 10 candidate layouts.
"""
from __future__ import annotations

from ...models.structure import (
    Structure, Node, Member, Support, PointLoad, SupportType,
    CrossSection, EngineeringSpec, Material, MATERIAL_LIBRARY,
)
from ..models import (
    ExperimentalCase, Provenance, ParameterStatus, ModelMapping,
    ModelParameter, ParameterRole,
    MeasurementPoint,
)
from ..datasets.steel_truss_zenodo import STEEL_TRUSS_DATASET

CASE_ID = "steel_truss_loss_of_chord_UD"

# --- Material [T1]/[F4] -----------------------------------------------
# F4's coupon (E=207,639.8 MPa, Fy=326.6 MPa) is explicitly captioned as
# the property set "used later in the computational models" — used here
# as the primary source. Table 1's mean (Fy=278.8 MPa, 3 coupons from the
# ORIGINAL full-scale bridge steel) is a distinct, separately reported
# value kept only for reference/context, not used for the solve.
_E_PA = 207_639.8e6
_FY_PA = 326.6e6
_DENSITY = 7850.0  # kg/m^3, standard structural steel — not separately
                    # re-measured in the source; ASSUMED at the standard value.

MATERIAL_KEY = "STEEL_TRUSS_EXP_COUPON"
if MATERIAL_KEY not in MATERIAL_LIBRARY:
    MATERIAL_LIBRARY[MATERIAL_KEY] = Material(
        key=MATERIAL_KEY,
        name="Scaled specimen steel (Fig. 4 dog-bone coupon)",
        E=_E_PA,
        yield_stress=_FY_PA,
        density=_DENSITY,
    )

# --- Cross-sections [T2], "Scaled-down specimen" column, area only ----
# The solver is a pure pin-jointed axial-truss formulation (no bending),
# so only cross-sectional area A is used; Ix/Iy from Table 2 are not
# consumed by NeuroPlan's element stiffness and are not reproduced here.
_AREA_CM2 = {
    "C1": 8.4, "C2": 8.4,
    "M1": 6.9, "M2": 3.1, "M3": 1.7, "M4": 3.1, "M5": 1.7,
    "D1": 3.1, "D2": 3.1, "D3": 1.7, "D4": 3.1, "D5": 1.7,
}


class _FixedAreaSection(CrossSection):
    """A CrossSection carrying an exact area from Table 2 (angle/T sections
    whose real second moment of area is irrelevant to an axial-only solve)."""

    def __init__(self, area_m2: float):
        super().__init__(outer_diameter=0.05, wall_thickness=0.005)
        self._area = area_m2

    @property
    def area(self) -> float:
        return self._area

    @property
    def moment_of_inertia(self) -> float:
        return 1e-8  # not physically meaningful; solver does not use it for axial-only members


def _section(key: str) -> _FixedAreaSection:
    return _FixedAreaSection(_AREA_CM2[key] * 1.0e-4)


# --- Geometry [G]: 12 panels x 500 mm = 6000 mm span, 600 mm height ----
PANEL_M = 0.5
HEIGHT_M = 0.6
N_PANELS = 12
SPAN_M = PANEL_M * N_PANELS  # 6.0 m

# Per-panel-segment chord type, read directly off Fig. 2's North/South
# lateral views (left half; mirrored for the right half by the drawing's
# own symmetry, confirmed identical on both labelled halves).
_CHORD_TYPE = ["C1", "C1", "C1", "C2", "C2", "C2", "C2", "C2", "C2", "C1", "C1", "C1"]
# Per-node (0..12) vertical type.
_VERT_TYPE = ["M1", "M2", "M3", "M4", "M3", "M5", "M5", "M5", "M3", "M4", "M3", "M2", "M1"]
# Per-panel-segment diagonal type.
_DIAG_TYPE = ["D1", "D2", "D3", "D4", "D3", "D5", "D5", "D3", "D4", "D3", "D2", "D1"]

# Loaded top nodes: the two panel points flanking mid-span (node 6),
# i.e. nodes 5 and 7 at x=2.5 m and x=3.5 m. DERIVED, moderate confidence
# — see module docstring point (1).
_LOADED_TOP_NODE_INDICES = (5, 7)
_LOAD_PER_POINT_N = 20_000.0  # [F6]: 20 kN per point, four points total (80 kN)

# Sensor -> node mapping. ASSUMED — see "SENSOR MAPPING" in the module
# docstring for the full candidate ranking and why this layout was chosen
# over the marginally lower-MAE irregular one.
_SENSOR_NODE_SEQUENCE = (1, 3, 5, 6, 7, 9, 11)
SOUTH_SENSOR_NODES = {str(i + 1): n for i, n in enumerate(_SENSOR_NODE_SEQUENCE)}
NORTH_SENSOR_NODES = {str(i + 8): n for i, n in enumerate(_SENSOR_NODE_SEQUENCE)}

# The layout ruled out by the candidate scan. Kept so the regression test
# can assert it stays rejected rather than silently creeping back.
REJECTED_CONSECUTIVE_SENSOR_SEQUENCE = (3, 4, 5, 6, 7, 8, 9)
MIDSPAN_NODE = 6


def _source(page_or_figure: str, note: str = "") -> Provenance:
    return Provenance(
        source_type="publication",
        status=ParameterStatus.SOURCED,
        publication=STEEL_TRUSS_DATASET.linked_publication_title,
        doi=STEEL_TRUSS_DATASET.linked_publication_doi,
        page_or_figure=page_or_figure,
        retrieved=STEEL_TRUSS_DATASET.retrieved,
        note=note,
    )


def _derived(note: str) -> Provenance:
    return Provenance(
        source_type="derived", status=ParameterStatus.DERIVED,
        page_or_figure="Fig. 6 (Supplementary Information, p.10)", note=note,
    )


def _assumed(note: str) -> Provenance:
    return Provenance(source_type="derived", status=ParameterStatus.ASSUMED, note=note)


def build_structure() -> tuple[Structure, dict[str, int]]:
    """
    Build the real NeuroPlan Structure for one Pratt truss plane of the
    specimen (the South truss; North is geometrically identical with
    supports mirrored end-for-end, per [G] — this function models one
    plane, which is what the 7-sensor-per-side measurement set requires).

    Returns (structure, node_index) where node_index maps a readable name
    ("bottom_6", "top_5", ...) to the NeuroPlan node id, for use in the
    sensor mapping and load application.
    """
    nodes: list[Node] = []
    bottom_ids = list(range(0, N_PANELS + 1))
    top_ids = list(range(N_PANELS + 1, 2 * (N_PANELS + 1)))

    for i in range(N_PANELS + 1):
        nodes.append(Node(id=bottom_ids[i], x=i * PANEL_M, y=0.0, z=0.0))
    for i in range(N_PANELS + 1):
        nodes.append(Node(id=top_ids[i], x=i * PANEL_M, y=HEIGHT_M, z=0.0))

    members: list[Member] = []
    mid = 0
    for i in range(N_PANELS):
        members.append(Member(id=mid, node_i=bottom_ids[i], node_j=bottom_ids[i + 1],
                               material_key=MATERIAL_KEY, section=_section(_CHORD_TYPE[i])))
        mid += 1
    for i in range(N_PANELS):
        members.append(Member(id=mid, node_i=top_ids[i], node_j=top_ids[i + 1],
                               material_key=MATERIAL_KEY, section=_section(_CHORD_TYPE[i])))
        mid += 1
    for i in range(N_PANELS + 1):
        members.append(Member(id=mid, node_i=bottom_ids[i], node_j=top_ids[i],
                               material_key=MATERIAL_KEY, section=_section(_VERT_TYPE[i])))
        mid += 1
    half = N_PANELS / 2
    for i in range(N_PANELS):
        # Pratt convention: diagonals slope toward centre (tension under
        # gravity) — same convention as server/core/generator/topology.py's
        # generate_pratt_truss, confirmed matching Fig. 2's drawn diagonals.
        if i < half:
            members.append(Member(id=mid, node_i=bottom_ids[i + 1], node_j=top_ids[i],
                                   material_key=MATERIAL_KEY, section=_section(_DIAG_TYPE[i])))
        else:
            members.append(Member(id=mid, node_i=bottom_ids[i], node_j=top_ids[i + 1],
                                   material_key=MATERIAL_KEY, section=_section(_DIAG_TYPE[i])))
        mid += 1

    # Supports [G]: hinged one end, roller the other — exact type per
    # Table's own "Hinged Support" / "Rolling Support" labels.
    supports = [
        Support(node_id=bottom_ids[0], support_type=SupportType.PIN),
        Support(node_id=bottom_ids[-1], support_type=SupportType.ROLLER_X),
    ]
    # This is a single planar truss (z=0 throughout) solved with NeuroPlan's
    # 3-DOF/node formulation, so every other node needs the same
    # out-of-plane bracing the planar generators use — see
    # server/core/generator/topology.py's _add_out_of_plane_bracing.
    braced_ids = {s.node_id for s in supports}
    for n in nodes:
        if n.id not in braced_ids:
            supports.append(Support(node_id=n.id, support_type=SupportType.OUT_OF_PLANE))

    loads = [
        PointLoad(node_id=top_ids[i], fy=-_LOAD_PER_POINT_N)
        for i in _LOADED_TOP_NODE_INDICES
    ]

    structure = Structure(nodes=nodes, members=members, supports=supports, loads=loads)
    index = {f"bottom_{i}": bottom_ids[i] for i in range(N_PANELS + 1)}
    index.update({f"top_{i}": top_ids[i] for i in range(N_PANELS + 1)})
    return structure, index


def build_spec() -> EngineeringSpec:
    return EngineeringSpec(
        material_key=MATERIAL_KEY,
        span=SPAN_M,
        height=HEIGHT_M,
        safety_factor=1.67,
        max_displacement_ratio=300.0,
        description="Steel truss bridge experimental validation case (South truss, UD, DS-Loss-of-Chord, Load Setup-1)",
    )


def build_case() -> ExperimentalCase:
    notes = [
        "Geometry (12 panels x 500mm, 600mm height): SOURCED, Fig. 2, Supplementary Information p.7.",
        "Material (E=207,639.8 MPa, Fy=326.6 MPa): SOURCED, Fig. 4 caption ('used later in the computational models'), p.9.",
        "Cross-section areas (C1/C2/M1-M5/D1-D5): SOURCED, Table 2 'Scaled-down specimen' column, p.8.",
        "Supports (hinged + roller): SOURCED, Fig. 2, p.7.",
        "Load magnitude (4 x 20kN = 80kN total, Load Setup-1): SOURCED, Section 1.2 text p.9-10 and Fig. 6, p.10; "
        "cross-checked against the raw dataset's Jack_Load column (peak ~79.87 kN).",
        "Load application nodes (top nodes flanking mid-span): DERIVED from Fig. 6's isometric sketch — "
        "not independently dimensioned in the source. Moderate confidence.",
        "Density (7850 kg/m^3): ASSUMED at the standard structural-steel value — not separately measured in the source.",
        "Sensor-to-node mapping for the 14 displacement transducers: ASSUMED. Section 1.3 places them at "
        "interior lower-chord panel points but gives no table of which point holds which sensor, leaving 10 "
        "possible symmetric layouts. All 10 were scored against the measurements; the consecutive-node layout "
        "is ruled out (it predicts 6.04mm where 2.48mm was measured). The regular alternate-panel layout "
        "(nodes 1,3,5,6,7,9,11) is used — not the marginally better-fitting irregular one, which would be "
        "overfitting. IMPORTANT: because this layout was chosen with reference to the measured data, the "
        "resulting agreement is NOT independent evidence that the solver is correct. Mid-span (sensor 4 / "
        "sensor 11) is the one high-confidence mapping — it is the same node under all 10 layouts.",
        "Bending/frame behaviour, connection stiffness, self-weight and rig dead load (4.2kN + 5.4kN) are NOT "
        "included in this model — see assumptions in server/validation/state.py.",
    ]
    return ExperimentalCase(
        case_id=CASE_ID,
        title="Steel Truss Bridge — Undamaged Baseline (Loss-of-Chord DS, UD state)",
        dataset=STEEL_TRUSS_DATASET,
        description=(
            "Intact (undamaged) South Pratt truss of the scaled steel bridge specimen, "
            "under the four-point 80kN symmetric Load Setup-1, compared against the 7 "
            "South-side vertical displacement transducers recorded in the 'Loss_Chord_UD' "
            "sheet (the pre-damage baseline of the lower-chord removal test series)."
        ),
        load_setup_description=(
            "Load Setup-1: four 20kN point loads applied at upper-chord panel points "
            "symmetric about the bridge centreline (two per truss plane), quasi-static, "
            "displacement-controlled hydraulic jack (0.05 mm/s)."
        ),
        applicable=True,
        parameter_notes=notes,
    )


def build_parameter_inventory() -> list[ModelParameter]:
    """
    The complete list of model inputs, each flagged with whether the
    measured results were consulted when choosing it.

    This inventory is what `independence.assess_independence` scans to
    decide whether this comparison counts as independent validation
    evidence. It must stay exhaustive over ParameterRole — a role with no
    entry forces a NOT_ASSESSED verdict rather than a clean one.

    Exactly one entry here is calibrated: the sensor-to-node mapping,
    which was chosen by scoring candidate layouts against the measured
    deflection profile (see SENSOR MAPPING above). That single flag is
    what correctly prevents this case from being presented as validation.
    """
    return [
        ModelParameter(
            name="Span, height and panel layout",
            role=ParameterRole.GEOMETRY,
            status=ParameterStatus.SOURCED,
            selected_using_measurements=False,
            value_summary=f"{N_PANELS} panels x {PANEL_M*1000:.0f} mm = {SPAN_M:.1f} m span, {HEIGHT_M*1000:.0f} mm deep",
            source_reference="[G] Fig. 2, Supplementary Information p.7",
        ),
        ModelParameter(
            name="Steel elastic modulus and yield stress",
            role=ParameterRole.MATERIAL,
            status=ParameterStatus.SOURCED,
            selected_using_measurements=False,
            value_summary=f"E = {_E_PA/1e6:,.1f} MPa, Fy = {_FY_PA/1e6:.1f} MPa",
            source_reference="[F4] Fig. 4 coupon test, p.9",
            note="Density 7850 kg/m^3 is ASSUMED at the standard value but was "
                 "likewise not chosen with reference to the measurements.",
        ),
        ModelParameter(
            name="Member cross-sectional areas",
            role=ParameterRole.CROSS_SECTION,
            status=ParameterStatus.SOURCED,
            selected_using_measurements=False,
            value_summary=f"{len(_AREA_CM2)} member types, C1/C2/M1-M5/D1-D5",
            source_reference="[T2] Table 2, 'Scaled-down specimen' column, p.8",
        ),
        ModelParameter(
            name="Support conditions",
            role=ParameterRole.BOUNDARY_CONDITION,
            status=ParameterStatus.SOURCED,
            selected_using_measurements=False,
            value_summary="Hinged one end, roller the other; out-of-plane restraint at panel points",
            source_reference="[G] Fig. 2, p.7",
        ),
        ModelParameter(
            name="Applied load magnitude and position",
            role=ParameterRole.LOAD,
            status=ParameterStatus.DERIVED,
            selected_using_measurements=False,
            value_summary=f"{_LOAD_PER_POINT_N/1000:.0f} kN at top nodes {_LOADED_TOP_NODE_INDICES}",
            source_reference="[F6] Fig. 6 and Section 1.2, p.9-10",
            note="Magnitude SOURCED and cross-checked against the dataset's "
                 "Jack_Load column. Positions DERIVED by reading Fig. 6's "
                 "sketch — read from the figure, not fitted to the deflections.",
        ),
        ModelParameter(
            name="Sensor-to-node mapping",
            role=ParameterRole.SENSOR_MAPPING,
            status=ParameterStatus.ASSUMED,
            selected_using_measurements=True,
            value_summary=f"lower-chord panel points {_SENSOR_NODE_SEQUENCE}",
            source_reference="[S13] Section 1.3, p.12 (constrains but does not fix the positions)",
            note="CALIBRATED. The source leaves 10 possible symmetric layouts; "
                 "the choice among them was made by scoring candidates against "
                 "the measured deflection profile. This is why the comparison "
                 "is reported as calibration, not validation.",
        ),
    ]


def build_sensor_mappings() -> list[ModelMapping]:
    mappings = []
    for sensor_id, node_id in SOUTH_SENSOR_NODES.items():
        high_conf = node_id == MIDSPAN_NODE
        mappings.append(ModelMapping(
            sensor_id=sensor_id,
            node_id=node_id,
            dof="UY",
            status=ParameterStatus.SOURCED if high_conf else ParameterStatus.ASSUMED,
            reasoning=(
                "Mid-span node — unambiguous as the peak of the symmetric measured "
                "curve, and identical under all 10 candidate sensor layouts."
                if high_conf else
                "Assumed. [S13] places the transducers at interior lower-chord panel "
                "points but does not say which; this node comes from the regular "
                "alternate-panel layout selected in the module docstring. Because "
                "that layout was chosen with reference to the measurements, the "
                "agreement at this node is not independent validation evidence."
            ),
            comparable=True,
        ))
    return mappings
