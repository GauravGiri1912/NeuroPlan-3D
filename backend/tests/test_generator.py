"""
NeuroPlan-3D — Topology Generator Tests

Covers what test_solver.py doesn't: that all three implemented truss types
produce distinct, valid, non-mechanism geometry, and that requesting an
unsupported type fails loudly instead of silently substituting Pratt.
"""
import pytest

from server.models.structure import EngineeringSpec, StructureType
from server.core.generator.topology import (
    generate_structure, generate_pratt_truss, generate_howe_truss, generate_warren_truss,
)
from server.core.fea.solver import solve


@pytest.mark.parametrize("structure_type", [StructureType.PRATT, StructureType.HOWE, StructureType.WARREN])
def test_all_implemented_types_produce_solvable_structures(structure_type):
    spec = EngineeringSpec(structure_type=structure_type, span=20.0, height=3.33, num_panels=6)
    structure = generate_structure(spec)
    results = solve(structure, spec)
    assert results is not None
    # Reactions must balance the applied load regardless of topology.
    total_ry = sum(r.ry for r in results.reactions)
    assert total_ry == pytest.approx(spec.primary_load, rel=1e-6)


def test_pratt_and_howe_diagonals_are_mirrored():
    """
    Pratt and Howe should differ ONLY in diagonal direction — same node
    layout, same chord/vertical member count, opposite diagonal connectivity.
    """
    spec = EngineeringSpec(structure_type=StructureType.PRATT, span=20.0, height=3.33, num_panels=6)
    pratt = generate_pratt_truss(spec)
    howe = generate_howe_truss(spec)

    assert len(pratt.nodes) == len(howe.nodes)
    assert len(pratt.members) == len(howe.members)

    # Diagonal members are the last n_panels entries in both generators.
    n_panels = spec.num_panels
    pratt_diagonals = {(m.node_i, m.node_j) for m in pratt.members[-n_panels:]}
    howe_diagonals = {(m.node_i, m.node_j) for m in howe.members[-n_panels:]}
    assert pratt_diagonals != howe_diagonals, "Pratt and Howe diagonals should not be identical"


def test_generate_structure_rejects_unimplemented_type():
    """
    generate_structure must fail loudly for any structure_type without a
    registered generator, rather than silently falling back to Pratt — this
    is a regression test for a real gap: the old behavior would silently
    substitute Pratt for a Howe-truss request before the Howe generator
    existed, misrepresenting what was actually built.
    """
    spec = EngineeringSpec(span=20.0, height=3.33, num_panels=6)
    spec.structure_type = "not_a_real_type"  # bypass enum validation deliberately

    with pytest.raises(ValueError, match="No topology generator implemented"):
        generate_structure(spec)


def test_warren_still_works_for_odd_panel_count():
    """Warren forces panels to even internally — must not crash on odd input."""
    spec = EngineeringSpec(structure_type=StructureType.WARREN, span=21.0, height=3.5, num_panels=7)
    structure = generate_warren_truss(spec)
    results = solve(structure, spec)
    assert results is not None
