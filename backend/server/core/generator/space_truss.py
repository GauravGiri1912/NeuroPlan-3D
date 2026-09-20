"""
NeuroPlan-3D — Spatial (3D) Space-Truss Generator

This is the project's first genuinely three-dimensional structural
generator. Unlike the planar Pratt/Howe/Warren generators (which place
every node at z=0 and therefore need artificial out-of-plane bracing
supports to avoid a singular stiffness matrix), this generator produces a
structure whose members span all three axes and which is spatially stable
on its own — no `OUT_OF_PLANE` bracing supports are added anywhere.

GEOMETRY — a box/through-type space-truss pedestrian bridge
-----------------------------------------------------------
Four longitudinal chords run along x, forming a rectangular tube of
structural depth `height` (y) and width `width` (z). The two truss
planes are placed symmetrically about z = 0, so the structure is
centred on the longitudinal axis:

    top-front    (i·p, H, −W/2)    top-back    (i·p, H, +W/2)
    bottom-front (i·p, 0, −W/2)    bottom-back (i·p, 0, +W/2)

for i = 0..n_panels, where p = span / n_panels.

MEMBER GROUPS
-------------
1. Front vertical truss  (x-y plane at z=0):   chords, verticals, Pratt diagonals
2. Back vertical truss   (x-y plane at z=W):   same pattern
3. Transverse members    (pure z):             front↔back at every panel point,
                                               top and bottom
4. Bottom plan bracing   (x-z plane at y=0):   alternating diagonals — these
                                               have non-zero dx AND dz
5. Top plan bracing      (x-z plane at y=H):   alternating diagonals
6. End portal bracing    (y-z plane at each
                          end):                cross diagonals with non-zero
                                               dy AND dz

Groups 4-6 are what make this genuinely spatial: their members have two or
three non-zero direction cosines, so they contribute stiffness coupling
between axes in the global matrix. A planar truss has cz = 0 for every
member, which is exactly why it needs artificial z-restraints.

SUPPORTS — 6 restraints suppress the 6 rigid-body modes
--------------------------------------------------------
With the four bottom corner nodes A(0,0,0), B(L,0,0), C(0,0,W), D(L,0,W):

    A: UX, UY, UZ   (pin)            — kills the 3 translations
    B: UY, UZ       (roller_x)       — UZ kills rotation about Y,
                                       UY kills rotation about Z
    C: UY           (vertical only)  — kills rotation about X
    D: UY           (vertical only)  — 4th bearing (1 redundancy)

That is 7 restraints against 6 rigid-body modes: one redundancy, which the
direct stiffness method handles natively and which matches real practice
(bridges sit on four bearings). The redundancy is deliberate and documented
rather than accidental.
"""
from ...models.structure import (
    Structure, Node, Member, Support, PointLoad,
    EngineeringSpec, SupportType,
    CrossSection, SECTION_CATALOG,
)


def generate_space_truss(spec: EngineeringSpec) -> Structure:
    """
    Generate a 3D box space-truss bridge from an engineering specification.

    Requires `spec.width > 0` — a zero-width "space truss" would collapse
    onto a single plane and is rejected rather than silently degraded into
    a planar structure.
    """
    if spec.width <= 0:
        raise ValueError(
            "A space truss requires width > 0 (the z-direction separation "
            "between the two vertical trusses). Received width="
            f"{spec.width}."
        )

    n_panels = spec.num_panels
    span = spec.span
    height = spec.height
    width = spec.width
    panel_width = span / n_panels

    section = SECTION_CATALOG.get(spec.section_key, CrossSection(0.1143, 0.0064))

    nodes: list[Node] = []
    members: list[Member] = []

    def add_member(ni: int, nj: int) -> None:
        members.append(Member(
            id=len(members), node_i=ni, node_j=nj,
            material_key=spec.material_key, section=section,
        ))

    # ── Nodes: four longitudinal chords ────────────────────────────────
    bottom_front: list[int] = []
    top_front: list[int] = []
    bottom_back: list[int] = []
    top_back: list[int] = []

    # Truss planes sit symmetrically about z = 0.
    z_front = -width / 2.0
    z_back = +width / 2.0

    for i in range(n_panels + 1):
        x = i * panel_width
        for chord, y, z in (
            (bottom_front, 0.0, z_front),
            (top_front, height, z_front),
            (bottom_back, 0.0, z_back),
            (top_back, height, z_back),
        ):
            node_id = len(nodes)
            nodes.append(Node(id=node_id, x=x, y=y, z=z))
            chord.append(node_id)

    # ── 1 & 2. Front and back vertical trusses (Pratt pattern) ─────────
    mid = n_panels / 2
    for bottom, top in ((bottom_front, top_front), (bottom_back, top_back)):
        for i in range(n_panels):
            add_member(bottom[i], bottom[i + 1])   # bottom chord
            add_member(top[i], top[i + 1])         # top chord
        for i in range(n_panels + 1):
            add_member(bottom[i], top[i])          # verticals
        for i in range(n_panels):                  # Pratt diagonals
            if i < mid:
                add_member(bottom[i + 1], top[i])
            else:
                add_member(bottom[i], top[i + 1])

    # ── 3. Transverse members (pure z) at every panel point ────────────
    for i in range(n_panels + 1):
        add_member(bottom_front[i], bottom_back[i])
        add_member(top_front[i], top_back[i])

    # ── 4 & 5. Plan bracing in the bottom (y=0) and top (y=H) planes ───
    # Alternating diagonals — non-zero dx AND dz, so they resist the
    # horizontal shear (lozenging) that transverse members alone cannot.
    for front, back in ((bottom_front, bottom_back), (top_front, top_back)):
        for i in range(n_panels):
            if i % 2 == 0:
                add_member(front[i], back[i + 1])
            else:
                add_member(back[i], front[i + 1])

    # ── 6. End portal bracing (y-z plane at each end) ──────────────────
    # Cross bracing in the end frames — non-zero dy AND dz — preventing the
    # tube from racking (top plane swaying in z relative to the bottom).
    for end in (0, n_panels):
        add_member(bottom_front[end], top_back[end])
        add_member(bottom_back[end], top_front[end])

    # ── Supports: 6 rigid-body modes suppressed (see module docstring) ──
    supports = [
        Support(node_id=bottom_front[0], support_type=SupportType.PIN),
        Support(node_id=bottom_front[-1], support_type=SupportType.ROLLER_X),
        Support(node_id=bottom_back[0], support_type=SupportType.VERTICAL_ONLY),
        Support(node_id=bottom_back[-1], support_type=SupportType.VERTICAL_ONLY),
    ]
    # NOTE: deliberately NO out-of-plane bracing supports. This structure is
    # spatially stable through its own members — which is the whole point.

    loads = _apply_spatial_loads(spec, bottom_front, bottom_back, n_panels)

    structure = Structure(nodes=nodes, members=members, supports=supports, loads=loads)
    assert_is_genuinely_spatial(structure, minimum_z_extent=0.1)
    return structure


def assert_is_genuinely_spatial(
    structure: Structure,
    minimum_z_extent: float = 0.1,
    epsilon: float = 1e-9,
) -> None:
    """
    Fail loudly if a structure claiming to be spatial is not.

    This exists because the failure mode it guards against is silent and
    convincing: a structure that carries z-coordinates but is geometrically
    flat still renders plausibly in a 3D viewport and still solves, while
    being a planar model wearing a 3D label. These are the structural facts
    that distinguish the two, so they are asserted rather than assumed.

    Checks:
      1. The nodes span a meaningful z extent (not all in one plane).
      2. At least one MEMBER connects nodes at different z — a structure can
         have two separated planes and still be two independent planar
         trusses if nothing joins them.

    Raises:
        ValueError: if either condition fails.
    """
    if not structure.nodes:
        raise ValueError("Spatial validation failed: structure has no nodes.")

    z_values = [n.z for n in structure.nodes]
    z_extent = max(z_values) - min(z_values)
    if z_extent < minimum_z_extent:
        raise ValueError(
            f"Spatial validation failed: z extent is {z_extent:.6g} m "
            f"(minimum {minimum_z_extent} m). Every node lies in one plane, so "
            "this is a PLANAR structure — it must not be presented as a space truss."
        )

    node_map = structure.node_dict()
    spanning_members = sum(
        1 for m in structure.members
        if abs(node_map[m.node_j].z - node_map[m.node_i].z) > epsilon
    )
    if spanning_members == 0:
        raise ValueError(
            "Spatial validation failed: no member connects nodes at different z. "
            "The truss planes are not structurally joined, so this is not a "
            "single spatial structure."
        )


def _apply_spatial_loads(
    spec: EngineeringSpec,
    bottom_front: list[int],
    bottom_back: list[int],
    n_panels: int,
) -> list[PointLoad]:
    """
    Apply loads to the bottom deck chords.

    The vertical load (`primary_load`) is shared equally between the front
    and back bottom chords — a deck spanning transversely between the two
    trusses delivers half its reaction to each.

    Lateral components (`lateral_load_x`, `lateral_load_z`) are applied to
    the same nodes, so a transverse wind load or a longitudinal braking
    load produces genuinely three-dimensional member forces rather than
    being silently discarded.
    """
    desc = spec.load_description.lower()
    loads: list[PointLoad] = []

    if "distributed" in desc or "uniform" in desc:
        interior_front = bottom_front[1:-1]
        interior_back = bottom_back[1:-1]
        target_nodes = interior_front + interior_back
    else:
        mid_idx = n_panels // 2
        target_nodes = [bottom_front[mid_idx], bottom_back[mid_idx]]

    if not target_nodes:
        # Degenerate panel count — fall back to the two mid-span chord nodes.
        mid_idx = n_panels // 2
        target_nodes = [bottom_front[mid_idx], bottom_back[mid_idx]]

    n_targets = len(target_nodes)
    fy_each = -spec.primary_load / n_targets
    fx_each = spec.lateral_load_x / n_targets
    fz_each = spec.lateral_load_z / n_targets

    for node_id in target_nodes:
        loads.append(PointLoad(node_id=node_id, fx=fx_each, fy=fy_each, fz=fz_each))

    return loads
