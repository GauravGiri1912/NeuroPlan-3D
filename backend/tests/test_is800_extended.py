"""
IS 800:2007 extended tension checks: net-section rupture (cl. 6.3.3) and
simplified single-bolt-line block shear (cl. 6.4.1).

Hand-verified worked example (M20 bolt, d0=22mm, Fe410 plate, t=8mm):

  NET SECTION (A_g=2000 mm^2, 2 holes):
      A_n = 2000 - 2*22*8 = 1648 mm^2
      T_dn = 0.9*1648e-6*410e6/1.25 = 486,489.6 N

  BLOCK SHEAR (3 bolts, e=35mm, pitch=50mm, edge g=40mm, fy=250MPa):
      shear_len = 35 + 2*50 = 135mm;  A_vg = 8*135 = 1080 mm^2
      A_vn = 1080 - 2.5*22*8 = 640 mm^2
      A_tg = 8*40 = 320 mm^2;  A_tn = 8*(40-11) = 232 mm^2
      path1 = 1080e-6*250e6/(sqrt(3)*1.10) + 0.9*232e-6*410e6/1.25
            = 141,776.4 + 68,423.2 = 210,199.6 N
      path2 = 0.9*640e-6*410e6/(sqrt(3)*1.25) + 320e-6*250e6/1.10
            = 108,894.99 + 72,727.27 = 181,622.3 N  (~181,804.9 exact)
      capacity = min(path1, path2) = path2
"""
import math
import pytest

from server.core.codes.is800_tension_extended import (
    check_net_section_rupture, check_block_shear, hole_diameter_m,
    NET_SECTION_EFFICIENCY,
)
from server.core.codes.is800_2007 import GAMMA_M0, GAMMA_M1
from server.core.codes.connections import BoltedConnection

D0_M20 = hole_diameter_m(20)


def test_hole_diameter_includes_standard_clearance():
    assert D0_M20 == pytest.approx(0.022, rel=1e-9)


def test_net_section_rupture_matches_hand_calculation():
    check = check_net_section_rupture(
        member_id=0, axial_force=200_000.0, gross_area_m2=0.002,
        thickness_m=0.008, bolt_diameter_mm=20, n_holes=2, fu_pa=410e6,
    )
    expected_an = 0.002 - 2 * D0_M20 * 0.008
    expected_capacity = NET_SECTION_EFFICIENCY * expected_an * 410e6 / GAMMA_M1

    assert check.net_area_m2 == pytest.approx(expected_an, rel=1e-9)
    assert check.capacity_n == pytest.approx(expected_capacity, rel=1e-9)
    assert check.capacity_n == pytest.approx(486_489.6, rel=1e-4)
    assert check.status == "pass"


def test_more_holes_reduces_net_section_capacity():
    one_hole = check_net_section_rupture(0, 100_000.0, 0.002, 0.008, 20, 1, 410e6)
    three_holes = check_net_section_rupture(0, 100_000.0, 0.002, 0.008, 20, 3, 410e6)
    assert three_holes.capacity_n < one_hole.capacity_n


def test_overloaded_net_section_fails():
    check = check_net_section_rupture(0, 500_000.0, 0.002, 0.008, 20, 2, 410e6)
    assert check.dc_ratio > 1.0
    assert check.status == "fail"


def test_net_section_flags_the_chs_simplification():
    check = check_net_section_rupture(0, 100_000.0, 0.002, 0.008, 20, 2, 410e6)
    assert "CHS" in check.note
    assert "simplification" in check.note


def test_block_shear_matches_hand_calculation():
    connection = BoltedConnection(
        member_id=0, bolt_diameter_mm=20, bolt_grade="8.8", bolt_count=3,
        ply_thickness_mm=8.0, end_distance_mm=35.0, pitch_mm=50.0,
    )
    check = check_block_shear(
        member_id=0, axial_force=150_000.0, connection=connection,
        edge_distance_mm=40.0, fy_pa=250e6, fu_pa=410e6,
    )

    t, n, e, p, g = 0.008, 3, 0.035, 0.050, 0.040
    shear_len = e + (n - 1) * p
    a_vg = t * shear_len
    a_vn = a_vg - (n - 0.5) * D0_M20 * t
    a_tg = t * g
    a_tn = t * (g - D0_M20 / 2)
    path1 = a_vg * 250e6 / (math.sqrt(3) * GAMMA_M0) + 0.9 * a_tn * 410e6 / GAMMA_M1
    path2 = 0.9 * a_vn * 410e6 / (math.sqrt(3) * GAMMA_M1) + a_tg * 250e6 / GAMMA_M0
    expected_capacity = min(path1, path2)

    assert check.a_vg_m2 == pytest.approx(a_vg, rel=1e-9)
    assert check.a_vn_m2 == pytest.approx(a_vn, rel=1e-9)
    assert check.a_tg_m2 == pytest.approx(a_tg, rel=1e-9)
    assert check.a_tn_m2 == pytest.approx(a_tn, rel=1e-9)
    assert check.path_1_capacity_n == pytest.approx(path1, rel=1e-9)
    assert check.path_2_capacity_n == pytest.approx(path2, rel=1e-9)
    assert check.capacity_n == pytest.approx(expected_capacity, rel=1e-9)
    assert check.capacity_n == pytest.approx(181_804.9, rel=1e-4)
    assert check.capacity_n == check.path_2_capacity_n   # path 2 governs here


def test_block_shear_capacity_is_the_minimum_of_the_two_paths():
    connection = BoltedConnection(
        member_id=0, bolt_diameter_mm=20, bolt_grade="8.8", bolt_count=3,
        ply_thickness_mm=8.0, end_distance_mm=35.0, pitch_mm=50.0,
    )
    check = check_block_shear(0, 100_000.0, connection, 40.0, 250e6, 410e6)
    assert check.capacity_n == pytest.approx(min(check.path_1_capacity_n, check.path_2_capacity_n))


def test_more_bolts_increases_block_shear_capacity():
    base = BoltedConnection(member_id=0, bolt_diameter_mm=20, bolt_grade="8.8",
                            bolt_count=2, ply_thickness_mm=8.0,
                            end_distance_mm=35.0, pitch_mm=50.0)
    more = BoltedConnection(member_id=0, bolt_diameter_mm=20, bolt_grade="8.8",
                            bolt_count=5, ply_thickness_mm=8.0,
                            end_distance_mm=35.0, pitch_mm=50.0)
    c_base = check_block_shear(0, 100_000.0, base, 40.0, 250e6, 410e6)
    c_more = check_block_shear(0, 100_000.0, more, 40.0, 250e6, 410e6)
    assert c_more.capacity_n > c_base.capacity_n


def test_overloaded_block_shear_fails():
    connection = BoltedConnection(member_id=0, bolt_diameter_mm=20, bolt_grade="8.8",
                                  bolt_count=2, ply_thickness_mm=6.0,
                                  end_distance_mm=30.0, pitch_mm=40.0)
    check = check_block_shear(0, 400_000.0, connection, 30.0, 250e6, 410e6)
    assert check.status == "fail"


def test_block_shear_discloses_the_single_line_simplification():
    connection = BoltedConnection(member_id=0, bolt_diameter_mm=20, bolt_grade="8.8",
                                  bolt_count=2, ply_thickness_mm=8.0,
                                  end_distance_mm=35.0, pitch_mm=50.0)
    check = check_block_shear(0, 50_000.0, connection, 40.0, 250e6, 410e6)
    assert "SIMPLIFIED single-bolt-line" in check.note
    assert "NOT modelled" in check.note
