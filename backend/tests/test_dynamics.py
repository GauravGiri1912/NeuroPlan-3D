"""
Modal analysis and IS 1893:2016 response-spectrum seismic analysis.

Validation strategy:
  1. SDOF closed form omega = sqrt(k/m) — a single axial bar with mass
     lumped at its free end is exactly a spring-mass oscillator.
  2. Orthogonality: phi_i^T M phi_j = delta_ij is a MATHEMATICAL property
     of the generalized eigenproblem, verified directly — this checks
     solver correctness independent of any code-specific content.
  3. Design-spectrum continuity at its own published breakpoints — a
     correctly transcribed spectrum must be continuous where two
     branches meet, regardless of confidence in the source numbers.
"""
import math
import pytest

from server.core.fea.dynamics import (
    solve_modal, assemble_lumped_mass_matrix, design_spectrum_sa_g,
    response_spectrum_analysis, SoilType, SeismicZone, ZONE_FACTOR,
    _SPECTRUM_BREAKPOINTS,
)
from server.core.fea.assembly import assemble_global_stiffness
from server.core.fea.boundary import get_constrained_dofs
from server.core.generator.topology import generate_structure
from server.models.structure import (
    Structure, Node, Member, Support, SupportType, CrossSection,
    MATERIAL_LIBRARY, EngineeringSpec,
)

SECTION = CrossSection(outer_diameter=0.1143, wall_thickness=0.0064)


def _sdof_bar(length=4.0):
    return Structure(
        nodes=[Node(0, 0, 0, 0), Node(1, length, 0, 0)],
        members=[Member(0, 0, 1, "A36", SECTION)],
        supports=[
            Support(node_id=0, support_type=SupportType.PIN),
            Support(node_id=1, support_type=SupportType.ROLLER_X, dx=False, dy=True, dz=True),
        ],
        loads=[],
    )


# ─────────────────────────────────────────────
# Modal analysis — closed form and mathematical properties
# ─────────────────────────────────────────────

def test_sdof_natural_frequency_matches_spring_mass_closed_form():
    length = 4.0
    material = MATERIAL_LIBRARY["A36"]
    k = SECTION.area * material.E / length
    m_free_end = material.density * SECTION.area * length / 2.0
    omega_expected = math.sqrt(k / m_free_end)

    result = solve_modal(_sdof_bar(length), n_modes=1)
    mode = result.modes[0]

    assert mode.angular_frequency == pytest.approx(omega_expected, rel=1e-9)
    assert mode.frequency_hz == pytest.approx(omega_expected / (2 * math.pi), rel=1e-9)
    assert mode.modal_mass == pytest.approx(1.0, rel=1e-9)


def test_longer_bar_has_lower_frequency():
    """k ~ 1/L, m ~ L, so omega ~ 1/L — a longer bar must vibrate slower."""
    short = solve_modal(_sdof_bar(2.0), n_modes=1).modes[0]
    long = solve_modal(_sdof_bar(8.0), n_modes=1).modes[0]
    assert long.angular_frequency < short.angular_frequency


def test_frequencies_are_sorted_ascending():
    structure = generate_structure(EngineeringSpec())
    result = solve_modal(structure, n_modes=6)
    freqs = [m.frequency_hz for m in result.modes]
    assert freqs == sorted(freqs)
    assert all(f > 0 for f in freqs)


def test_mode_shapes_are_mass_orthonormal():
    """
    phi_i^T M phi_j = delta_ij is a mathematical property of the
    generalized eigenproblem — a real, code-independent correctness test.
    """
    structure = generate_structure(EngineeringSpec())
    result = solve_modal(structure, n_modes=6)

    K, dof_map = assemble_global_stiffness(structure)
    constrained = get_constrained_dofs(structure.supports, dof_map)
    import numpy as np
    free = np.setdiff1d(np.arange(K.shape[0]), np.asarray(sorted(constrained)))
    M_ff = np.diag(assemble_lumped_mass_matrix(structure)[free])

    Phi = np.array([m.mode_shape[free] for m in result.modes]).T
    gram = Phi.T @ M_ff @ Phi
    assert gram == pytest.approx(np.eye(len(result.modes)), abs=1e-8)


def test_mass_participation_never_exceeds_one_hundred_percent():
    structure = generate_structure(EngineeringSpec())
    result = solve_modal(structure, n_modes=6)
    assert result.mass_participation_x_percent <= 100.0 + 1e-6
    assert result.mass_participation_y_percent <= 100.0 + 1e-6


def test_lumped_mass_matches_self_weight_mass_exactly():
    """The dynamics mass model must be the SAME mass as the self-weight load."""
    from server.core.fea.load_cases import compute_self_weight
    structure = generate_structure(EngineeringSpec())
    sw = compute_self_weight(structure)
    M_diag = assemble_lumped_mass_matrix(structure)
    assert sum(M_diag) / 3.0 == pytest.approx(sw.total_mass_kg, rel=1e-9)


def test_zero_mass_free_dof_is_rejected_not_silently_solved():
    """An unconnected free node with no mass must be reported, not ignored."""
    structure = generate_structure(EngineeringSpec())
    structure.nodes.append(Node(999, 100.0, 100.0, 100.0))
    with pytest.raises(ValueError, match="zero mass"):
        solve_modal(structure)


# ─────────────────────────────────────────────
# Design spectrum — continuity and formula checks
# ─────────────────────────────────────────────

@pytest.mark.parametrize("soil", list(SoilType))
def test_spectrum_is_continuous_at_its_own_breakpoints(soil):
    t2, coeff = _SPECTRUM_BREAKPOINTS[soil]
    assert design_spectrum_sa_g(0.10, soil) == pytest.approx(2.5, abs=1e-9)
    assert design_spectrum_sa_g(t2, soil) == pytest.approx(2.5, abs=1e-9)
    assert design_spectrum_sa_g(t2 + 1e-6, soil) == pytest.approx(2.5, rel=1e-4)


def test_spectrum_rises_linearly_below_the_plateau():
    assert design_spectrum_sa_g(0.0, SoilType.MEDIUM) == pytest.approx(1.0)
    assert design_spectrum_sa_g(0.05, SoilType.MEDIUM) == pytest.approx(1.75)


def test_spectrum_decays_as_one_over_t_past_the_plateau():
    for soil in SoilType:
        t2, coeff = _SPECTRUM_BREAKPOINTS[soil]
        for t in (t2 + 0.5, 2.0, 4.0):
            if t <= 4.0:
                assert design_spectrum_sa_g(t, soil) == pytest.approx(coeff / t, rel=1e-9)


def test_spectrum_rejects_periods_beyond_four_seconds():
    with pytest.raises(ValueError, match="4.0"):
        design_spectrum_sa_g(4.5, SoilType.MEDIUM)


def test_soft_soil_amplifies_more_than_rock_at_long_period():
    """Physically: soft soil sustains higher spectral demand at long T."""
    t = 2.0
    assert design_spectrum_sa_g(t, SoilType.SOFT) > design_spectrum_sa_g(t, SoilType.ROCK_HARD)


def test_zone_factors_are_monotonically_increasing_with_severity():
    ordered = [ZONE_FACTOR[z] for z in (SeismicZone.II, SeismicZone.III,
                                        SeismicZone.IV, SeismicZone.V)]
    assert ordered == sorted(ordered)


# ─────────────────────────────────────────────
# Response spectrum analysis
# ─────────────────────────────────────────────

def test_response_spectrum_runs_on_the_real_generated_truss():
    structure = generate_structure(EngineeringSpec())
    result = response_spectrum_analysis(
        structure, SeismicZone.IV, SoilType.MEDIUM,
        importance_factor=1.0, response_reduction_factor=3.0, direction="x",
    )
    assert result.base_shear_srss_n > 0
    assert len(result.mode_contributions) == len(result.modal.modes)
    assert result.nodal_forces.shape[0] == 3 * len(structure.nodes)


def test_higher_zone_factor_increases_base_shear():
    structure = generate_structure(EngineeringSpec())
    low = response_spectrum_analysis(structure, SeismicZone.II, SoilType.MEDIUM,
                                     1.0, 3.0, "x")
    high = response_spectrum_analysis(structure, SeismicZone.V, SoilType.MEDIUM,
                                      1.0, 3.0, "x")
    assert high.base_shear_srss_n > low.base_shear_srss_n
    assert high.base_shear_srss_n / low.base_shear_srss_n == pytest.approx(
        ZONE_FACTOR[SeismicZone.V] / ZONE_FACTOR[SeismicZone.II], rel=1e-6
    )


def test_higher_response_reduction_factor_decreases_base_shear():
    """R in the denominator: a more ductile system gets a smaller design force."""
    structure = generate_structure(EngineeringSpec())
    ductile = response_spectrum_analysis(structure, SeismicZone.IV, SoilType.MEDIUM,
                                         1.0, response_reduction_factor=5.0, direction="x")
    brittle = response_spectrum_analysis(structure, SeismicZone.IV, SoilType.MEDIUM,
                                         1.0, response_reduction_factor=1.5, direction="x")
    assert ductile.base_shear_srss_n < brittle.base_shear_srss_n


def test_mode_dominating_the_excited_direction_governs_base_shear():
    """The mode with the largest effective mass in X should give the largest V_i."""
    structure = generate_structure(EngineeringSpec())
    result = response_spectrum_analysis(structure, SeismicZone.IV, SoilType.MEDIUM,
                                        1.0, 3.0, direction="x")
    dominant_mode = max(result.modal.modes, key=lambda m: m.effective_mass_x)
    dominant_contribution = max(result.mode_contributions, key=lambda c: c.base_shear_n)
    assert dominant_contribution.mode_number == dominant_mode.mode_number


def test_zero_response_reduction_factor_is_rejected():
    structure = generate_structure(EngineeringSpec())
    with pytest.raises(ValueError, match="positive"):
        response_spectrum_analysis(structure, SeismicZone.IV, SoilType.MEDIUM, 1.0, 0.0)


def test_invalid_direction_is_rejected():
    structure = generate_structure(EngineeringSpec())
    with pytest.raises(ValueError, match="direction"):
        response_spectrum_analysis(structure, SeismicZone.IV, SoilType.MEDIUM, 1.0, 3.0, direction="y")


def test_result_states_srss_not_cqc():
    structure = generate_structure(EngineeringSpec())
    result = response_spectrum_analysis(structure, SeismicZone.IV, SoilType.MEDIUM, 1.0, 3.0)
    assert result.combination_method == "SRSS"
    assert "CQC" in result.combination_caveat
    assert "not implemented" in result.combination_caveat.lower()


def test_result_declares_its_own_scope_limits():
    structure = generate_structure(EngineeringSpec())
    result = response_spectrum_analysis(structure, SeismicZone.IV, SoilType.MEDIUM, 1.0, 3.0)
    for topic in ("time-history", "torsional", "vertical seismic", "soil-structure"):
        assert topic in result.scope_note.lower()


def test_live_load_mass_fraction_increases_total_seismic_mass():
    """
    PointLoad defaults to LoadCaseType.LIVE (see models/structure.py), so
    the structure generated from EngineeringSpec already carries its
    primary_load as a LIVE case — the fraction applies to ALL live loads
    present, not only ones a caller adds afterward. expected_added sums
    every live load's |fy|, matching what the function actually does.
    """
    from server.models.structure import PointLoad, LoadCaseType
    structure = generate_structure(EngineeringSpec())
    live_node = structure.nodes[len(structure.nodes) // 2].id
    structure.loads.append(PointLoad(node_id=live_node, fy=-10_000.0))

    total_live_fy = sum(abs(l.fy) for l in structure.loads if l.case == LoadCaseType.LIVE)

    base = solve_modal(structure, n_modes=1, live_load_mass_fraction=0.0)
    with_live = solve_modal(structure, n_modes=1, live_load_mass_fraction=0.25)
    assert with_live.total_mass_kg > base.total_mass_kg
    expected_added = 0.25 * total_live_fy / 9.80665
    assert with_live.total_mass_kg - base.total_mass_kg == pytest.approx(expected_added, rel=1e-6)
