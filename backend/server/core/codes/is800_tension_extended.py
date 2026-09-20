"""
NeuroPlan-3D — IS 800:2007 Extended Tension Checks: Net-Section Rupture
(cl. 6.3) and a Simplified Block Shear Check (cl. 6.4)

Extends the tension-member screening in is800_2007.py, which only
checked gross-section yielding (cl. 6.2). Net-section rupture and block
shear both need bolt-hole geometry, which was not available until
Priority 7's BoltedConnection model existed — this module consumes that
same connection data.

────────────────────────────────────────────────────────────────────────
NET-SECTION RUPTURE (cl. 6.3.3, bolted connections)
────────────────────────────────────────────────────────────────────────
    A_n = A_g - n_holes * d_0 * t
    T_dn = 0.9 * A_n * f_u / gamma_m1

  A_g     gross cross-sectional area
  d_0     bolt hole diameter (bolt diameter + standard clearance,
          consistent with codes/connections.py's HOLE_CLEARANCE table)
  t       ply/member thickness at the connection
  0.9     the code's net-section efficiency factor for this clause
  gamma_m1 = 1.25 (ultimate-stress-governed resistance, Table 5)

This treats the tension member as having holes drilled straight through
its own cross-section thickness `t` — appropriate for a flat plate or
angle leg; for a circular hollow section this is a simplification (CHS
members are usually connected via a welded end plate or slotted gusset
rather than through-bolted), stated explicitly as a limitation.

────────────────────────────────────────────────────────────────────────
BLOCK SHEAR (cl. 6.4.1) — SIMPLIFIED, SINGLE BOLT LINE ONLY
────────────────────────────────────────────────────────────────────────
    T_db = min(
        A_vg*f_y/(sqrt(3)*gamma_m0) + 0.9*A_tn*f_u/gamma_m1  ,
        0.9*A_vn*f_u/(sqrt(3)*gamma_m1) + A_tg*f_y/gamma_m0
    )

  A_vg, A_vn   gross / net area along the SHEAR plane (parallel to load)
  A_tg, A_tn   gross / net area along the TENSION plane (perpendicular)

For a single line of n bolts (spacing = pitch, end distance = e) with
an assumed tension-plane width (edge distance to the free edge, g):

    shear plane length  = e + (n-1)*pitch
    A_vg = t * [e + (n-1)*pitch]
    A_vn = A_vg - (n-0.5)*d_0*t     (n-0.5 holes deducted along the shear
                                     plane — the standard convention for a
                                     line ending at a bolt, per cl. 6.4.1
                                     explanatory examples: n full holes
                                     minus a half-hole for the end bolt's
                                     staggered contribution is a common
                                     simplification; a full multi-row
                                     block-shear geometry is NOT modelled)
    A_tg = t * g
    A_tn = t * (g - d_0/2)   (one hole width deducted, single line)

SCOPE LIMIT stated explicitly: this is a SINGLE BOLT LINE simplification.
Multi-row, staggered-bolt, or gusset-plate-specific block shear geometry
is NOT implemented. This is disclosed in every result, never silently
assumed adequate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .is800_2007 import GAMMA_M0, GAMMA_M1
from .connections import HOLE_CLEARANCE, BoltedConnection

NET_SECTION_EFFICIENCY = 0.9   # cl. 6.3.3


@dataclass
class NetSectionRuptureCheck:
    member_id: int
    gross_area_m2: float
    net_area_m2: float
    demand_n: float
    capacity_n: float
    dc_ratio: float
    status: str
    clause: str = "cl. 6.3.3"
    note: str = (
        "Assumes holes drilled through the member's own thickness (flat "
        "plate/angle convention). For a CHS this is a simplification — "
        "real CHS tension connections are usually welded end plates or "
        "slotted gussets, not through-bolted."
    )


@dataclass
class BlockShearCheck:
    member_id: int
    a_vg_m2: float
    a_vn_m2: float
    a_tg_m2: float
    a_tn_m2: float
    path_1_capacity_n: float
    path_2_capacity_n: float
    capacity_n: float
    demand_n: float
    dc_ratio: float
    status: str
    clause: str = "cl. 6.4.1"
    note: str = (
        "SIMPLIFIED single-bolt-line block shear. Multi-row, staggered "
        "or gusset-specific geometry is NOT modelled."
    )


def hole_diameter_m(bolt_diameter_mm: int) -> float:
    clearance = HOLE_CLEARANCE.get(bolt_diameter_mm, 2e-3)
    return bolt_diameter_mm / 1000.0 + clearance


def check_net_section_rupture(
    member_id: int, axial_force: float, gross_area_m2: float,
    thickness_m: float, bolt_diameter_mm: int, n_holes: int, fu_pa: float,
) -> NetSectionRuptureCheck:
    d0 = hole_diameter_m(bolt_diameter_mm)
    net_area = gross_area_m2 - n_holes * d0 * thickness_m
    capacity = NET_SECTION_EFFICIENCY * net_area * fu_pa / GAMMA_M1
    demand = max(axial_force, 0.0)
    ratio = demand / capacity if capacity > 0 else float("inf")
    return NetSectionRuptureCheck(
        member_id=member_id, gross_area_m2=gross_area_m2, net_area_m2=net_area,
        demand_n=demand, capacity_n=capacity, dc_ratio=ratio,
        status="pass" if ratio <= 1.0 else "fail",
    )


def check_block_shear(
    member_id: int, axial_force: float, connection: BoltedConnection,
    edge_distance_mm: float, fy_pa: float, fu_pa: float,
) -> BlockShearCheck:
    t = connection.ply_thickness_mm / 1000.0
    d0 = hole_diameter_m(connection.bolt_diameter_mm)
    n = connection.bolt_count
    e = connection.end_distance_mm / 1000.0
    pitch = connection.pitch_mm / 1000.0
    g = edge_distance_mm / 1000.0

    shear_len = e + (n - 1) * pitch
    a_vg = t * shear_len
    a_vn = a_vg - (n - 0.5) * d0 * t
    a_tg = t * g
    a_tn = t * (g - d0 / 2.0)

    path_1 = a_vg * fy_pa / (math.sqrt(3) * GAMMA_M0) + NET_SECTION_EFFICIENCY * a_tn * fu_pa / GAMMA_M1
    path_2 = NET_SECTION_EFFICIENCY * a_vn * fu_pa / (math.sqrt(3) * GAMMA_M1) + a_tg * fy_pa / GAMMA_M0
    capacity = min(path_1, path_2)

    demand = max(axial_force, 0.0)
    ratio = demand / capacity if capacity > 0 else float("inf")
    return BlockShearCheck(
        member_id=member_id, a_vg_m2=a_vg, a_vn_m2=a_vn, a_tg_m2=a_tg, a_tn_m2=a_tn,
        path_1_capacity_n=path_1, path_2_capacity_n=path_2, capacity_n=capacity,
        demand_n=demand, dc_ratio=ratio, status="pass" if ratio <= 1.0 else "fail",
    )
