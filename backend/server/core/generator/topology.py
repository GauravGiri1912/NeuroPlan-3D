"""
NeuroPlan-3D — Parametric Truss Topology Generators

Generates nodes and members for standard truss configurations
from engineering specifications.

Supported types:
- Pratt truss (diagonals slope toward center)
- Howe truss (diagonals slope away from center — mirror of Pratt)
- Warren truss (alternating diagonals, no verticals)

All generators produce PLANAR trusses (every node at z=0) — this is a 2D
structural system embedded in a 3D coordinate space for visualization, not
a true 3D space truss/frame. Out-of-plane (z) motion is prevented by
bracing supports (`_add_out_of_plane_bracing`), not by structural members,
since no generated member has any out-of-plane stiffness component.
"""
from ...models.structure import (
    Structure, Node, Member, Support, PointLoad,
    EngineeringSpec, StructureType, SupportType,
    CrossSection, SECTION_CATALOG,
)
from .space_truss import generate_space_truss, assert_is_genuinely_spatial


def generate_pratt_truss(spec: EngineeringSpec) -> Structure:
    """
    Generate a Pratt truss topology.

    Pratt truss characteristics:
    - Vertical web members at each panel point
    - Diagonal members slope TOWARD the center (tension diagonals)
    - Top and bottom chords
    - Efficient for gravity loads (diagonals in tension, verticals in compression)

    Layout (6-panel example):
        6───7───8───9───10──11
        |╲  |  ╱|╲  |  ╱|╲  |
        |  ╲| ╱  |  ╲| ╱  |  ╲|
        0───1───2───3───4───5

    Parameters:
        spec: Engineering specification

    Returns:
        Complete Structure with nodes, members, supports, loads
    """
    n_panels = spec.num_panels
    span = spec.span
    height = spec.height
    panel_width = span / n_panels

    # Get section from catalog or use default
    section = SECTION_CATALOG.get(spec.section_key, CrossSection(0.1143, 0.0064))

    nodes: list[Node] = []
    members: list[Member] = []
    member_id = 0

    # --- Bottom chord nodes (y=0) ---
    bottom_nodes = []
    for i in range(n_panels + 1):
        node_id = i
        nodes.append(Node(id=node_id, x=i * panel_width, y=0.0, z=0.0))
        bottom_nodes.append(node_id)

    # --- Top chord nodes (y=height) ---
    top_nodes = []
    for i in range(n_panels + 1):
        node_id = (n_panels + 1) + i
        nodes.append(Node(id=node_id, x=i * panel_width, y=height, z=0.0))
        top_nodes.append(node_id)

    # --- Bottom chord members ---
    for i in range(n_panels):
        members.append(Member(
            id=member_id,
            node_i=bottom_nodes[i],
            node_j=bottom_nodes[i + 1],
            material_key=spec.material_key,
            section=section,
        ))
        member_id += 1

    # --- Top chord members ---
    for i in range(n_panels):
        members.append(Member(
            id=member_id,
            node_i=top_nodes[i],
            node_j=top_nodes[i + 1],
            material_key=spec.material_key,
            section=section,
        ))
        member_id += 1

    # --- Vertical members ---
    for i in range(n_panels + 1):
        members.append(Member(
            id=member_id,
            node_i=bottom_nodes[i],
            node_j=top_nodes[i],
            material_key=spec.material_key,
            section=section,
        ))
        member_id += 1

    # --- Diagonal members (Pratt pattern: slope toward center) ---
    mid = n_panels / 2
    for i in range(n_panels):
        if i < mid:
            # Left half: diagonal from bottom-right to top-left (/)
            members.append(Member(
                id=member_id,
                node_i=bottom_nodes[i + 1],
                node_j=top_nodes[i],
                material_key=spec.material_key,
                section=section,
            ))
        else:
            # Right half: diagonal from bottom-left to top-right (\)
            members.append(Member(
                id=member_id,
                node_i=bottom_nodes[i],
                node_j=top_nodes[i + 1],
                material_key=spec.material_key,
                section=section,
            ))
        member_id += 1

    # --- Supports ---
    supports = [
        Support(node_id=bottom_nodes[0], support_type=SupportType.PIN),
        Support(node_id=bottom_nodes[-1], support_type=SupportType.ROLLER_X),
    ]
    _add_out_of_plane_bracing(supports, nodes)

    # --- Loads ---
    loads = _apply_loads(spec, bottom_nodes, n_panels)

    return Structure(
        nodes=nodes,
        members=members,
        supports=supports,
        loads=loads,
    )


def generate_howe_truss(spec: EngineeringSpec) -> Structure:
    """
    Generate a Howe truss topology.

    Howe truss characteristics:
    - Vertical web members at each panel point (same as Pratt)
    - Diagonal members slope AWAY from the center (mirror image of Pratt) —
      diagonals in compression, verticals in tension under gravity load
    - Top and bottom chords

    Layout (6-panel example) — note the diagonals run the opposite way to Pratt:
        6───7───8───9───10──11
        |  ╱|╲  |  ╱|╲  |  ╱|
        |╱  |  ╲|╱  |  ╲|╱  |
        0───1───2───3───4───5

    Geometrically identical to the Pratt generator except for the diagonal
    direction, so it shares the same chord/vertical/support/load logic.
    """
    n_panels = spec.num_panels
    span = spec.span
    height = spec.height
    panel_width = span / n_panels

    section = SECTION_CATALOG.get(spec.section_key, CrossSection(0.1143, 0.0064))

    nodes: list[Node] = []
    members: list[Member] = []
    member_id = 0

    bottom_nodes = []
    for i in range(n_panels + 1):
        node_id = i
        nodes.append(Node(id=node_id, x=i * panel_width, y=0.0, z=0.0))
        bottom_nodes.append(node_id)

    top_nodes = []
    for i in range(n_panels + 1):
        node_id = (n_panels + 1) + i
        nodes.append(Node(id=node_id, x=i * panel_width, y=height, z=0.0))
        top_nodes.append(node_id)

    for i in range(n_panels):
        members.append(Member(
            id=member_id, node_i=bottom_nodes[i], node_j=bottom_nodes[i + 1],
            material_key=spec.material_key, section=section,
        ))
        member_id += 1

    for i in range(n_panels):
        members.append(Member(
            id=member_id, node_i=top_nodes[i], node_j=top_nodes[i + 1],
            material_key=spec.material_key, section=section,
        ))
        member_id += 1

    for i in range(n_panels + 1):
        members.append(Member(
            id=member_id, node_i=bottom_nodes[i], node_j=top_nodes[i],
            material_key=spec.material_key, section=section,
        ))
        member_id += 1

    # --- Diagonal members (Howe pattern: mirror of Pratt — slope away from center) ---
    mid = n_panels / 2
    for i in range(n_panels):
        if i < mid:
            # Left half: opposite of Pratt's left-half diagonal
            members.append(Member(
                id=member_id, node_i=bottom_nodes[i], node_j=top_nodes[i + 1],
                material_key=spec.material_key, section=section,
            ))
        else:
            # Right half: opposite of Pratt's right-half diagonal
            members.append(Member(
                id=member_id, node_i=bottom_nodes[i + 1], node_j=top_nodes[i],
                material_key=spec.material_key, section=section,
            ))
        member_id += 1

    supports = [
        Support(node_id=bottom_nodes[0], support_type=SupportType.PIN),
        Support(node_id=bottom_nodes[-1], support_type=SupportType.ROLLER_X),
    ]
    _add_out_of_plane_bracing(supports, nodes)

    loads = _apply_loads(spec, bottom_nodes, n_panels)

    return Structure(nodes=nodes, members=members, supports=supports, loads=loads)


def generate_warren_truss(spec: EngineeringSpec) -> Structure:
    """
    Generate a Warren truss topology.

    Warren truss characteristics:
    - No vertical web members
    - Alternating diagonal members form a zigzag pattern
    - All diagonals at approximately equal angles
    - Economical for uniform loading

    Layout (6-panel example):
        6───7───8───9───10──11
        |╲ ╱|╲ ╱|╲ ╱|╲ ╱|╲ ╱|
        | X  | X  | X  | X  | X |
        |╱ ╲|╱ ╲|╱ ╲|╱ ╲|╱ ╲|
        0───1───2───3───4───5

    Actually Warren has alternating diagonals:
        6───7───8───9──10──11
         ╲ ╱ ╲ ╱ ╲ ╱ ╲ ╱ ╲ ╱
          X   X   X   X   X
         ╱ ╲ ╱ ╲ ╱ ╲ ╱ ╲ ╱ ╲
        0───1───2───3───4───5
    """
    n_panels = spec.num_panels
    # Warren needs even number of panels for symmetry
    if n_panels % 2 != 0:
        n_panels += 1

    span = spec.span
    height = spec.height
    panel_width = span / n_panels

    section = SECTION_CATALOG.get(spec.section_key, CrossSection(0.1143, 0.0064))

    nodes: list[Node] = []
    members: list[Member] = []
    member_id = 0

    # --- Bottom chord nodes ---
    bottom_nodes = []
    for i in range(n_panels + 1):
        node_id = i
        nodes.append(Node(id=node_id, x=i * panel_width, y=0.0, z=0.0))
        bottom_nodes.append(node_id)

    # --- Top chord nodes ---
    top_nodes = []
    for i in range(n_panels + 1):
        node_id = (n_panels + 1) + i
        nodes.append(Node(id=node_id, x=i * panel_width, y=height, z=0.0))
        top_nodes.append(node_id)

    # --- Bottom chord members ---
    for i in range(n_panels):
        members.append(Member(
            id=member_id,
            node_i=bottom_nodes[i],
            node_j=bottom_nodes[i + 1],
            material_key=spec.material_key,
            section=section,
        ))
        member_id += 1

    # --- Top chord members ---
    for i in range(n_panels):
        members.append(Member(
            id=member_id,
            node_i=top_nodes[i],
            node_j=top_nodes[i + 1],
            material_key=spec.material_key,
            section=section,
        ))
        member_id += 1

    # --- Diagonal members (Warren: alternating V and Λ) ---
    for i in range(n_panels):
        if i % 2 == 0:
            # Upward diagonal: bottom-left to top-right
            members.append(Member(
                id=member_id,
                node_i=bottom_nodes[i],
                node_j=top_nodes[i + 1],
                material_key=spec.material_key,
                section=section,
            ))
        else:
            # Downward diagonal: top-left to bottom-right
            members.append(Member(
                id=member_id,
                node_i=top_nodes[i],
                node_j=bottom_nodes[i + 1],
                material_key=spec.material_key,
                section=section,
            ))
        member_id += 1

    # Vertical members at every panel point.
    #
    # A pure pin-jointed Warren truss with only alternating diagonals is a
    # mechanism: the zigzag pattern above only touches every OTHER joint on
    # each chord (degree-of-freedom count: m+r=3n+3 < 2j=4n+4 for n panels).
    # Verticals at every point ("Warren truss with verticals") make it fully
    # triangulated and statically determinate (m+r=4n+1+3=2j), matching the
    # Pratt generator's stability.
    for i in range(n_panels + 1):
        members.append(Member(
            id=member_id,
            node_i=bottom_nodes[i],
            node_j=top_nodes[i],
            material_key=spec.material_key,
            section=section,
        ))
        member_id += 1

    # --- Supports ---
    supports = [
        Support(node_id=bottom_nodes[0], support_type=SupportType.PIN),
        Support(node_id=bottom_nodes[-1], support_type=SupportType.ROLLER_X),
    ]
    _add_out_of_plane_bracing(supports, nodes)

    # --- Loads ---
    loads = _apply_loads(spec, bottom_nodes, n_panels)

    return Structure(
        nodes=nodes,
        members=members,
        supports=supports,
        loads=loads,
    )


def _add_out_of_plane_bracing(supports: list[Support], nodes: list[Node]) -> None:
    """
    Restrain the z-DOF at every node that doesn't already have a support.

    All generated trusses are planar (z=0 for every node), so no member has any
    stiffness component in the z direction (direction cosine cz=0 everywhere).
    Without this, every joint not already pinned/rollered is an independent
    out-of-plane mechanism and the global stiffness matrix is singular.
    This models the lateral/sway bracing present in any real planar truss and,
    because it only touches the z-DOF, it cannot affect in-plane (x/y) results.
    """
    braced_node_ids = {s.node_id for s in supports}
    for node in nodes:
        if node.id not in braced_node_ids:
            supports.append(Support(node_id=node.id, support_type=SupportType.OUT_OF_PLANE))


def _apply_loads(
    spec: EngineeringSpec,
    bottom_nodes: list[int],
    n_panels: int,
) -> list[PointLoad]:
    """
    Apply loads based on the spec description.

    Supports:
    - "center" → single point load at midspan
    - "distributed" → equal loads at all interior bottom nodes
    - default → center point load
    """
    loads: list[PointLoad] = []
    desc = spec.load_description.lower()

    if "distributed" in desc or "uniform" in desc:
        # Distribute load equally among interior bottom nodes
        interior_nodes = bottom_nodes[1:-1]  # exclude supports
        if len(interior_nodes) > 0:
            load_per_node = spec.primary_load / len(interior_nodes)
            for nid in interior_nodes:
                loads.append(PointLoad(node_id=nid, fy=-load_per_node))
    else:
        # Center point load (default)
        mid_idx = n_panels // 2
        loads.append(PointLoad(
            node_id=bottom_nodes[mid_idx],
            fy=-spec.primary_load,
        ))

    return loads


def generate_structure(spec: EngineeringSpec) -> Structure:
    """
    Generate a structure from an engineering specification.

    Dispatches to the appropriate topology generator.
    """
    generators = {
        # Planar (z = 0 everywhere)
        StructureType.PRATT: generate_pratt_truss,
        StructureType.HOWE: generate_howe_truss,
        StructureType.WARREN: generate_warren_truss,
        # Spatial (genuine 3D geometry)
        StructureType.SPACE_TRUSS: generate_space_truss,
    }

    # Validate the geometry inputs here, once, rather than letting each
    # generator fail on a division by zero deep inside its layout loop.
    if spec.num_panels < 1:
        raise ValueError(
            f"num_panels must be at least 1, got {spec.num_panels}. A truss "
            f"needs at least one panel to have any geometry."
        )
    if spec.span <= 0:
        raise ValueError(f"span must be positive, got {spec.span} m.")
    if spec.height <= 0:
        raise ValueError(f"height must be positive, got {spec.height} m.")

    generator = generators.get(spec.structure_type)
    if generator is None:
        # No silent fallback: a requested type with no generator is an error,
        # not a quietly-substituted Pratt truss the user never asked for.
        requested = getattr(spec.structure_type, "value", spec.structure_type)
        raise ValueError(
            f"No topology generator implemented for structure_type="
            f"'{requested}'. Supported: "
            f"{', '.join(t.value for t in generators)}."
        )

    structure = generator(spec)

    # Contract check: what came back must match what was asked for. A spatial
    # request that yields planar geometry is the exact silent-fallback failure
    # this project must never ship — so it raises instead of rendering.
    if spec.structure_type.is_spatial:
        assert_is_genuinely_spatial(structure)
    else:
        if any(abs(n.z) > 1e-9 for n in structure.nodes):
            raise ValueError(
                f"Generator contract violated: '{spec.structure_type.value}' is a "
                "PLANAR type but produced nodes with non-zero z."
            )

    return structure
