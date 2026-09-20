"""
NeuroPlan-3D — Connection SCREENING (Priority 7)

NOT a connection finite-element analysis. This evaluates closed-form
capacity equations from IS 800:2007 Section 10 for connections the user
explicitly defines, and compares them against the real member force from
the solver.

────────────────────────────────────────────────────────────────────────
WHY A CONNECTION MUST BE DECLARED
────────────────────────────────────────────────────────────────────────
The structural model carries no connection information: joints are ideal
pins. Bolt diameter, grade, count, plate thickness, edge distance and
pitch simply do not exist in it. They cannot be inferred from a member
force — many valid connections carry the same load.

So NeuroPlan does not guess. A member with no declared connection is
reported as NOT MODELED. That is a real limitation, stated plainly,
rather than a fabricated check.

────────────────────────────────────────────────────────────────────────
IMPLEMENTED — IS 800:2007 Section 10
────────────────────────────────────────────────────────────────────────
cl. 10.4.3 — Design shear capacity of a bearing-type bolt
    V_dsb = V_nsb / gamma_mb,   gamma_mb = 1.25
    V_nsb = (f_ub / sqrt(3)) * (n_n * A_nb + n_s * A_sb)
        n_n  shear planes passing through the THREADED portion
        A_nb net tensile stress area of the bolt
        n_s  shear planes passing through the unthreaded SHANK
        A_sb nominal shank area

cl. 10.3.4 — Design bearing capacity of a bolt on the connected plate
    V_dpb = V_npb / gamma_mb
    V_npb = 2.5 * k_b * d * t * f_u
    k_b   = min( e/(3*d_0),  p/(3*d_0) - 0.25,  f_ub/f_u,  1.0 )
        e   end distance, p pitch, d_0 hole diameter, t ply thickness

cl. 10.5.7.1 / 10.5.3.1 — Fillet weld
    throat a = 0.7 * s            (90 degree fillet)
    f_wd = (f_u / sqrt(3)) / gamma_mw,  gamma_mw = 1.25 shop / 1.50 site
    capacity = a * L_w * f_wd

────────────────────────────────────────────────────────────────────────
NOT IMPLEMENTED — declared, never silently skipped
────────────────────────────────────────────────────────────────────────
See UNSUPPORTED_CONNECTION_CHECKS.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

# cl. 5.4.1, Table 5
GAMMA_MB = 1.25      # bolts
GAMMA_MW_SHOP = 1.25
GAMMA_MW_SITE = 1.50

# Bolt ultimate tensile stress by property class (IS 1367 / Table 1 of IS 800).
BOLT_GRADE_FUB = {
    "4.6": 400e6,
    "4.8": 420e6,
    "5.6": 500e6,
    "8.8": 800e6,
    "10.9": 1000e6,
}

# Net tensile stress area A_nb, in m^2 (IS 1367-3 / standard ISO metric coarse).
BOLT_STRESS_AREA = {
    12: 84.3e-6, 16: 157.0e-6, 20: 245.0e-6,
    22: 303.0e-6, 24: 353.0e-6, 30: 561.0e-6,
}

# Standard clearance hole = bolt diameter + clearance (cl. 10.2.1, Table 19).
HOLE_CLEARANCE = {12: 1e-3, 16: 2e-3, 20: 2e-3, 22: 2e-3, 24: 2e-3, 30: 3e-3}


class ConnectionType(str, Enum):
    BOLTED_SHEAR = "bolted_shear"
    FILLET_WELD = "fillet_weld"
    NOT_DEFINED = "not_defined"


class ConnectionStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_MODELED = "not_modeled"


@dataclass
class BoltedConnection:
    """A bearing-type bolted connection at one member end."""
    member_id: int
    bolt_diameter_mm: int
    bolt_grade: str
    bolt_count: int
    shear_planes_threaded: int = 1
    shear_planes_shank: int = 0
    ply_thickness_mm: float = 8.0
    end_distance_mm: float = 35.0
    pitch_mm: float = 50.0
    plate_fu_pa: float = 410e6      # Fe 410 plate, the common Indian grade


@dataclass
class WeldedConnection:
    """A fillet-welded connection at one member end."""
    member_id: int
    weld_size_mm: float
    weld_length_mm: float
    shop_weld: bool = True
    parent_fu_pa: float = 410e6


@dataclass
class ConnectionCheck:
    member_id: int
    connection_type: ConnectionType
    clause: str
    check_name: str
    equation: str
    inputs: dict[str, str] = field(default_factory=dict)
    demand: float = 0.0
    capacity: float = 0.0
    dc_ratio: float = 0.0
    status: ConnectionStatus = ConnectionStatus.NOT_MODELED
    note: str = ""
    code: str = "IS 800"
    edition: str = "2007"


@dataclass
class ConnectionSummary:
    """
    One member's connection, rolled up to its GOVERNING check.

    A bolted connection produces two checks (shear, bearing); this
    identifies whichever of those actually governs — by demand/capacity
    ratio, never by declaration order or a hardcoded preference — so a
    reader gets one clear answer instead of having to compare two rows.
    """
    member_id: int
    connection_type: ConnectionType
    governing_check_name: str
    governing_clause: str
    demand: float
    capacity: float
    dc_ratio: float
    status: ConnectionStatus
    note: str = ""


@dataclass
class ConnectionScreeningReport:
    title: str = "CONNECTION SCREENING"
    checks: list[ConnectionCheck] = field(default_factory=list)
    summaries: list[ConnectionSummary] = field(default_factory=list)
    members_without_connection: list[int] = field(default_factory=list)
    n_failed: int = 0
    max_dc_ratio: float = 0.0
    governing_member_id: int | None = None
    unsupported_checks: list[str] = field(default_factory=list)
    disclaimer: str = (
        "CONNECTION SCREENING, not connection analysis. Closed-form "
        "capacity equations only — no finite-element modelling of the "
        "joint, no gusset plate design, no prying, no stiffness or "
        "eccentricity effects. A member with no declared connection is "
        "reported as NOT MODELED, never assumed adequate."
    )


UNSUPPORTED_CONNECTION_CHECKS = [
    "Gusset plate design and plate buckling — geometry not modelled.",
    "Block shear of the connected ply (cl. 6.4) — requires the full bolt "
    "group layout.",
    "Prying action in tension connections (cl. 10.4.7).",
    "Connection ROTATIONAL STIFFNESS — the solver assumes ideal pins, so a "
    "semi-rigid joint would change the analysis itself, not just this check.",
    "Eccentricity between member centroid and bolt group centroid.",
    "Slip-critical / friction-grip behaviour (cl. 10.4.3 HSFG).",
    "Weld group geometry under combined force and moment.",
    "Fatigue of the connection detail (Section 13).",
    "Bolt tension and combined shear-plus-tension interaction (cl. 10.3.6).",
]


def bolt_shear_capacity(diameter_mm: int, grade: str, count: int,
                        planes_threaded: int = 1, planes_shank: int = 0) -> tuple[float, dict]:
    """cl. 10.4.3 — V_dsb = (f_ub/sqrt(3))(n_n A_nb + n_s A_sb) / gamma_mb."""
    if grade not in BOLT_GRADE_FUB:
        raise ValueError(f"Unknown bolt grade '{grade}'. Known: {sorted(BOLT_GRADE_FUB)}")
    if diameter_mm not in BOLT_STRESS_AREA:
        raise ValueError(f"No stress area for M{diameter_mm}. Known: {sorted(BOLT_STRESS_AREA)}")

    fub = BOLT_GRADE_FUB[grade]
    anb = BOLT_STRESS_AREA[diameter_mm]
    asb = math.pi * (diameter_mm / 1000.0) ** 2 / 4.0

    per_bolt = (fub / math.sqrt(3.0)) * (planes_threaded * anb + planes_shank * asb)
    capacity = count * per_bolt / GAMMA_MB

    return capacity, {
        "f_ub": f"{fub/1e6:.0f} MPa",
        "A_nb": f"{anb*1e6:.0f} mm^2",
        "A_sb": f"{asb*1e6:.0f} mm^2",
        "n_bolts": str(count),
        "gamma_mb": f"{GAMMA_MB:.2f}",
        "V_dsb per bolt": f"{per_bolt/GAMMA_MB/1000:.1f} kN",
    }


def bolt_bearing_capacity(diameter_mm: int, grade: str, count: int,
                          ply_thickness_mm: float, end_distance_mm: float,
                          pitch_mm: float, plate_fu_pa: float) -> tuple[float, dict]:
    """cl. 10.3.4 — V_dpb = 2.5 k_b d t f_u / gamma_mb."""
    d = diameter_mm / 1000.0
    d0 = d + HOLE_CLEARANCE.get(diameter_mm, 2e-3)
    t = ply_thickness_mm / 1000.0
    e = end_distance_mm / 1000.0
    p = pitch_mm / 1000.0
    fub = BOLT_GRADE_FUB[grade]

    kb_terms = {
        "e/(3 d0)": e / (3.0 * d0),
        "p/(3 d0) - 0.25": p / (3.0 * d0) - 0.25,
        "f_ub/f_u": fub / plate_fu_pa,
        "1.0": 1.0,
    }
    kb = min(kb_terms.values())

    per_bolt = 2.5 * kb * d * t * plate_fu_pa
    capacity = count * per_bolt / GAMMA_MB

    return capacity, {
        "d": f"{diameter_mm} mm",
        "d_0": f"{d0*1000:.0f} mm",
        "t": f"{ply_thickness_mm:.1f} mm",
        "f_u": f"{plate_fu_pa/1e6:.0f} MPa",
        "k_b": f"{kb:.3f}",
        "k_b governed by": min(kb_terms, key=kb_terms.get),
        "gamma_mb": f"{GAMMA_MB:.2f}",
    }


def fillet_weld_capacity(size_mm: float, length_mm: float,
                         parent_fu_pa: float, shop: bool = True) -> tuple[float, dict]:
    """cl. 10.5.7.1 — capacity = throat * length * (f_u/sqrt(3))/gamma_mw."""
    throat = 0.7 * size_mm / 1000.0      # cl. 10.5.3.1, 90 degree fillet
    gamma_mw = GAMMA_MW_SHOP if shop else GAMMA_MW_SITE
    fwd = (parent_fu_pa / math.sqrt(3.0)) / gamma_mw
    capacity = throat * (length_mm / 1000.0) * fwd

    return capacity, {
        "weld size s": f"{size_mm:.1f} mm",
        "throat a = 0.7s": f"{throat*1000:.2f} mm",
        "length": f"{length_mm:.0f} mm",
        "f_u": f"{parent_fu_pa/1e6:.0f} MPa",
        "gamma_mw": f"{gamma_mw:.2f} ({'shop' if shop else 'site'})",
        "f_wd": f"{fwd/1e6:.1f} MPa",
    }


def screen_connections(
    member_results,
    bolted: list[BoltedConnection] | None = None,
    welded: list[WeldedConnection] | None = None,
) -> ConnectionScreeningReport:
    """
    Check every DECLARED connection against the real member force.

    Members with no declared connection are listed explicitly so the gap
    is visible in the report.
    """
    bolted = bolted or []
    welded = welded or []
    report = ConnectionScreeningReport(
        unsupported_checks=list(UNSUPPORTED_CONNECTION_CHECKS)
    )

    force_by_member = {m.member_id: abs(m.axial_force) for m in member_results}
    declared = {c.member_id for c in bolted} | {c.member_id for c in welded}
    report.members_without_connection = sorted(
        set(force_by_member) - declared
    )

    def record(check: ConnectionCheck) -> None:
        report.checks.append(check)
        if check.status is ConnectionStatus.FAIL:
            report.n_failed += 1
        if check.status in (ConnectionStatus.PASS, ConnectionStatus.FAIL):
            report.max_dc_ratio = max(report.max_dc_ratio, check.dc_ratio)

    for connection in bolted:
        demand = force_by_member.get(connection.member_id, 0.0)

        shear, shear_inputs = bolt_shear_capacity(
            connection.bolt_diameter_mm, connection.bolt_grade,
            connection.bolt_count, connection.shear_planes_threaded,
            connection.shear_planes_shank,
        )
        ratio = demand / shear if shear > 0 else float("inf")
        record(ConnectionCheck(
            member_id=connection.member_id,
            connection_type=ConnectionType.BOLTED_SHEAR,
            clause="cl. 10.4.3",
            check_name=f"Bolt shear — {connection.bolt_count} x M"
                       f"{connection.bolt_diameter_mm} grade {connection.bolt_grade}",
            equation="V_dsb = (f_ub/sqrt(3))(n_n A_nb + n_s A_sb)/gamma_mb",
            inputs=shear_inputs, demand=demand, capacity=shear, dc_ratio=ratio,
            status=ConnectionStatus.PASS if ratio <= 1.0 else ConnectionStatus.FAIL,
        ))

        bearing, bearing_inputs = bolt_bearing_capacity(
            connection.bolt_diameter_mm, connection.bolt_grade,
            connection.bolt_count, connection.ply_thickness_mm,
            connection.end_distance_mm, connection.pitch_mm,
            connection.plate_fu_pa,
        )
        ratio = demand / bearing if bearing > 0 else float("inf")
        record(ConnectionCheck(
            member_id=connection.member_id,
            connection_type=ConnectionType.BOLTED_SHEAR,
            clause="cl. 10.3.4",
            check_name="Bolt bearing on ply",
            equation="V_dpb = 2.5 k_b d t f_u / gamma_mb",
            inputs=bearing_inputs, demand=demand, capacity=bearing, dc_ratio=ratio,
            status=ConnectionStatus.PASS if ratio <= 1.0 else ConnectionStatus.FAIL,
            note="Block shear (cl. 6.4) is NOT checked and can govern.",
        ))

    for connection in welded:
        demand = force_by_member.get(connection.member_id, 0.0)
        capacity, inputs = fillet_weld_capacity(
            connection.weld_size_mm, connection.weld_length_mm,
            connection.parent_fu_pa, connection.shop_weld,
        )
        ratio = demand / capacity if capacity > 0 else float("inf")
        record(ConnectionCheck(
            member_id=connection.member_id,
            connection_type=ConnectionType.FILLET_WELD,
            clause="cl. 10.5.7.1",
            check_name="Fillet weld — shear on throat",
            equation="capacity = 0.7 s * L_w * (f_u/sqrt(3))/gamma_mw",
            inputs=inputs, demand=demand, capacity=capacity, dc_ratio=ratio,
            status=ConnectionStatus.PASS if ratio <= 1.0 else ConnectionStatus.FAIL,
        ))

    for member_id in report.members_without_connection:
        report.checks.append(ConnectionCheck(
            member_id=member_id,
            connection_type=ConnectionType.NOT_DEFINED,
            clause="-",
            check_name="Connection",
            equation="-",
            demand=force_by_member.get(member_id, 0.0),
            capacity=0.0, dc_ratio=0.0,
            status=ConnectionStatus.NOT_MODELED,
            note=(
                "NOT MODELED — no connection declared for this member. "
                "Bolt/weld details cannot be inferred from the member force, "
                "so no capacity is assumed."
            ),
        ))

    # Roll each member's checks up to a single GOVERNING check — the one
    # with the highest demand/capacity ratio among its PASS/FAIL checks
    # (never a hardcoded preference for shear over bearing, or the
    # opposite). A member with only a NOT_MODELED check governs by that.
    by_member: dict[int, list[ConnectionCheck]] = {}
    for check in report.checks:
        by_member.setdefault(check.member_id, []).append(check)

    worst_dc = -1.0
    for member_id, member_checks in by_member.items():
        real = [c for c in member_checks if c.status in (ConnectionStatus.PASS, ConnectionStatus.FAIL)]
        governing_check = max(real, key=lambda c: c.dc_ratio) if real else member_checks[0]

        report.summaries.append(ConnectionSummary(
            member_id=member_id,
            connection_type=governing_check.connection_type,
            governing_check_name=governing_check.check_name,
            governing_clause=governing_check.clause,
            demand=governing_check.demand,
            capacity=governing_check.capacity,
            dc_ratio=governing_check.dc_ratio,
            status=governing_check.status,
            note=governing_check.note,
        ))

        # Only a member with an actual declared (PASS/FAIL) check can be
        # "governing" — with nothing declared anywhere, there is no real
        # finding to point to, so governing_member_id stays None rather
        # than arbitrarily picking a NOT_MODELED member.
        if real and governing_check.dc_ratio > worst_dc:
            worst_dc = governing_check.dc_ratio
            report.governing_member_id = member_id

    report.summaries.sort(key=lambda s: s.member_id)
    return report
