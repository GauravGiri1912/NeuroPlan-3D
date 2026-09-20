"""
NeuroPlan-3D — Fatigue SCREENING (IS 800:2007 fatigue methodology, commonly referenced as Section 13 — see note below)

────────────────────────────────────────────────────────────────────────
WHY THE DETAIL-CATEGORY STRENGTH IS A REQUIRED INPUT, NOT A LOOKUP
────────────────────────────────────────────────────────────────────────
IS 800:2007 classifies connection/member details into categories
(commonly cited as Table 26, within the section addressing fatigue —
NeuroPlan does not assert the exact section number with full
confidence, having gotten a different section-number citation wrong
elsewhere in this codebase; verify against the code text directly),
each with its own reference fatigue strength
sigma_c at 2x10^6 cycles and its own S-N slope. This module does NOT
embed that table: transcribing multiple detail-category strength values
from memory risks getting individual entries wrong in a way that is hard
for a user to notice, which is precisely the kind of fabrication this
project's engineering-credibility system exists to prevent. Instead, the
S-N METHODOLOGY (the actual mathematics of fatigue-life estimation) is
implemented rigorously and exactly, and the caller supplies the detail
category's sigma_c and slope, sourced directly from IS 800 Table 26 (or
another governing code) by the user.

────────────────────────────────────────────────────────────────────────
FORMULATION — S-N CURVE (cl. 13.3)
────────────────────────────────────────────────────────────────────────
For a constant-amplitude stress range Delta_sigma, the number of cycles
to failure is given by the standard detail-category S-N relationship:

    N = N_ref * (sigma_c / Delta_sigma)^m

  sigma_c  — reference fatigue strength at N_ref = 2x10^6 cycles
  m        — inverse slope of the log(N)-log(stress range) line
             (m = 3 for normal-stress detail categories is the
             near-universal convention across detail-category fatigue
             codes — IS 800, Eurocode 3 EN 1993-1-9, BS 5400 — and is
             used as the default here, but is exposed as a parameter
             since some categories/codes use a different exponent, e.g.
             a bilinear S-N curve with m=5 below the constant-amplitude
             fatigue limit.)

Usage ratio for a design life of n_design cycles at range Delta_sigma:

    U = n_design / N

Palmgren-Miner cumulative damage, for multiple distinct stress ranges
each occurring n_i times:

    D = sum_i (n_i / N_i),   fails when D >= 1.0

────────────────────────────────────────────────────────────────────────
STRESS RANGE FROM TWO ANALYSIS CASES
────────────────────────────────────────────────────────────────────────
This solver is static; "cycles" are not tracked internally. A fatigue
screen is built by solving TWO real cases (e.g. "unloaded" and "fully
loaded", or two extreme positions of a moving load) through the actual
production solver, and taking the stress range as

    Delta_sigma = |stress_case_A - stress_case_B|

per member. This is provided by the caller (see
`stress_range_from_results`), keeping every number traceable to an
actual solve.

────────────────────────────────────────────────────────────────────────
WHAT THIS DOES NOT DO
────────────────────────────────────────────────────────────────────────
  - No embedded IS 800 Table 26 detail-category catalogue.
  - No variable-amplitude cycle counting (rainflow) from a real load
    history — only explicit, user-supplied (range, cycle-count) pairs.
  - No constant-amplitude fatigue limit / cut-off (single-slope S-N only
    unless the caller supplies a second (sigma_c, m, N_ref) segment).
  - No weld-specific or bolt-specific detail provisions beyond the
    generic S-N methodology.
"""
from __future__ import annotations

from dataclasses import dataclass, field

N_REF_DEFAULT = 2_000_000
M_DEFAULT = 3.0


@dataclass
class FatigueDetailCategory:
    """
    A fatigue detail category, per IS 800 Table 26 (or another governing
    code) — SUPPLIED BY THE CALLER, never assumed.
    """
    name: str
    sigma_c_mpa: float          # reference fatigue strength at n_ref cycles
    m: float = M_DEFAULT
    n_ref: int = N_REF_DEFAULT
    source: str = "User-supplied — see IS 800:2007 Table 26"


@dataclass
class FatigueCheck:
    member_id: int
    stress_range_mpa: float
    detail_category: str
    sigma_c_mpa: float
    m: float
    n_ref: int
    permissible_cycles: float
    design_cycles: float
    usage_ratio: float
    status: str      # "pass" | "fail" | "not_applicable"
    note: str = ""


def permissible_cycles(stress_range_mpa: float, category: FatigueDetailCategory) -> float:
    """N = N_ref * (sigma_c / Delta_sigma)^m."""
    if stress_range_mpa <= 0:
        return float("inf")
    return category.n_ref * (category.sigma_c_mpa / stress_range_mpa) ** category.m


def check_fatigue(
    member_id: int,
    stress_range_mpa: float,
    design_cycles: float,
    category: FatigueDetailCategory,
) -> FatigueCheck:
    if stress_range_mpa <= 0:
        return FatigueCheck(
            member_id=member_id, stress_range_mpa=0.0, detail_category=category.name,
            sigma_c_mpa=category.sigma_c_mpa, m=category.m, n_ref=category.n_ref,
            permissible_cycles=float("inf"), design_cycles=design_cycles,
            usage_ratio=0.0, status="not_applicable",
            note="No stress reversal/range at this member for the two cases supplied.",
        )

    n_perm = permissible_cycles(stress_range_mpa, category)
    ratio = design_cycles / n_perm if n_perm > 0 else float("inf")
    return FatigueCheck(
        member_id=member_id, stress_range_mpa=stress_range_mpa,
        detail_category=category.name, sigma_c_mpa=category.sigma_c_mpa,
        m=category.m, n_ref=category.n_ref, permissible_cycles=n_perm,
        design_cycles=design_cycles, usage_ratio=ratio,
        status="pass" if ratio <= 1.0 else "fail",
        note=(
            f"N = {category.n_ref:,} * ({category.sigma_c_mpa:.0f}/"
            f"{stress_range_mpa:.1f})^{category.m:.0f} = {n_perm:,.0f} cycles permissible "
            f"against {design_cycles:,.0f} design cycles."
        ),
    )


def miners_cumulative_damage(
    ranges_and_cycles: list[tuple[float, float]],
    category: FatigueDetailCategory,
) -> tuple[float, list[float]]:
    """
    Palmgren-Miner: D = sum(n_i / N_i). Returns (D, per-range damage list).
    D >= 1.0 indicates the cumulative-damage fatigue check fails.
    """
    per_range_damage = []
    total = 0.0
    for stress_range, n_actual in ranges_and_cycles:
        n_perm = permissible_cycles(stress_range, category)
        damage = n_actual / n_perm if n_perm > 0 and n_perm != float("inf") else 0.0
        per_range_damage.append(damage)
        total += damage
    return total, per_range_damage


def stress_range_from_results(member_results_a, member_results_b) -> dict[int, float]:
    """
    Per-member stress range (MPa) between two solved cases, matched by
    member_id. Both inputs are lists of MemberResult from two REAL solver
    runs — see module docstring.
    """
    stress_a = {m.member_id: m.stress for m in member_results_a}
    stress_b = {m.member_id: m.stress for m in member_results_b}
    common_ids = set(stress_a) & set(stress_b)
    return {
        mid: abs(stress_a[mid] - stress_b[mid]) / 1e6
        for mid in common_ids
    }


@dataclass
class FatigueScreeningReport:
    title: str = "FATIGUE SCREENING"
    checks: list[FatigueCheck] = field(default_factory=list)
    n_failed: int = 0
    governing_member_id: int | None = None
    max_usage_ratio: float = 0.0
    disclaimer: str = (
        "FATIGUE SCREENING using the IS 800:2007 fatigue S-N "
        "methodology. The detail-category reference strength (sigma_c) "
        "and slope (m) are SUPPLIED, not looked up from an embedded code "
        "table — verify them against IS 800 Table 26 (or the governing "
        "code) before use. No rainflow cycle counting, no constant- "
        "amplitude fatigue limit, no weld/bolt-specific provisions beyond "
        "the generic S-N relationship."
    )


def screen_fatigue(
    stress_ranges_mpa: dict[int, float],
    design_cycles: float,
    category: FatigueDetailCategory,
) -> FatigueScreeningReport:
    report = FatigueScreeningReport()
    worst_ratio = -1.0
    for member_id, stress_range in sorted(stress_ranges_mpa.items()):
        check = check_fatigue(member_id, stress_range, design_cycles, category)
        report.checks.append(check)
        if check.status == "fail":
            report.n_failed += 1
        if check.usage_ratio > worst_ratio:
            worst_ratio = check.usage_ratio
            report.governing_member_id = member_id
    report.max_usage_ratio = max(worst_ratio, 0.0)
    return report
