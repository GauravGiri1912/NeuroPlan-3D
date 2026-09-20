"""
NeuroPlan-3D — Fire: Elevated-Temperature Strength/Stiffness Reduction

────────────────────────────────────────────────────────────────────────
WHY EUROCODE'S REDUCTION FACTORS, NOT AN "IS 800" TABLE
────────────────────────────────────────────────────────────────────────
IS 800:2007 does not publish its own numerical table of strength/
stiffness reduction factors for carbon steel at elevated temperature
(NeuroPlan deliberately does not assert which section number addresses
fire, since it cannot verify the current edition's exact section
numbering without the source text in hand). The values used here —
k_y,theta (effective yield strength reduction) and k_E,theta (elastic
modulus reduction) — are the internationally standard values from
EN 1993-1-2 Table 3.1, the customary reference Indian practitioners use
for this exact purpose in the absence of an IS 800 table. This is stated
explicitly, not presented as an IS 800 clause. A real fire-engineering
assessment must cross-check the CURRENT edition of the governing code
before use — this module is a screening estimate, not a certified fire
design.

────────────────────────────────────────────────────────────────────────
FORMULATION
────────────────────────────────────────────────────────────────────────
At steel temperature theta (deg C):

    f_y,theta = k_y,theta(theta) * f_y      (effective yield strength)
    E_theta   = k_E,theta(theta) * E        (elastic modulus)

k_y,theta and k_E,theta are read from the standard tabulated points below
via LINEAR INTERPOLATION between adjacent table temperatures — this is
the same interpolation method the source table itself specifies.

The reduced properties are substituted for the material's E and f_y, and
the structure is RE-SOLVED through the actual production solver at those
reduced properties (this reuses the existing self-weight/live load
pipeline — fire is applied as a property reduction, not a new load case).
Member utilisation at temperature is then

    utilisation_theta = |stress| / f_y,theta

WHAT THIS DOES NOT DO
  - No thermal expansion / restraint forces during heating (see
    fea/thermal.py for that, entirely separate physics — this module
    only reduces strength/stiffness, it does not apply a thermal load).
  - No char/insulation/protection modelling, no time-temperature (heating
    curve) analysis, no section factor (Am/V) based heating-rate
    calculation.
  - No fire-specific member classification (Section 12's qualitative
    guidance is not encoded here).
  - Assumes UNIFORM temperature across the whole structure at the
    instant evaluated — not a real fire's spatial/temporal gradient.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# EN 1993-1-2 Table 3.1 — reduction factors for carbon steel at elevated
# temperature. (temperature_C, k_y_theta, k_E_theta)
_REDUCTION_TABLE: list[tuple[float, float, float]] = [
    (20, 1.00, 1.00),
    (100, 1.00, 1.00),
    (200, 1.00, 0.90),
    (300, 1.00, 0.80),
    (400, 1.00, 0.70),
    (500, 0.78, 0.60),
    (600, 0.47, 0.31),
    (700, 0.23, 0.13),
    (800, 0.11, 0.09),
    (900, 0.06, 0.0675),
    (1000, 0.04, 0.0450),
    (1100, 0.02, 0.0225),
    (1200, 0.00, 0.00),
]

SOURCE_CITATION = (
    "EN 1993-1-2 (Eurocode 3, Part 1-2) Table 3.1 — used because "
    "IS 800:2007 Section 12 does not publish its own numeric reduction "
    "table. Cross-check against the current governing code before use."
)


def _interpolate(temperature_c: float, column: int) -> float:
    if temperature_c <= _REDUCTION_TABLE[0][0]:
        return _REDUCTION_TABLE[0][column]
    if temperature_c >= _REDUCTION_TABLE[-1][0]:
        return _REDUCTION_TABLE[-1][column]
    for (t0, ky0, ke0), (t1, ky1, ke1) in zip(_REDUCTION_TABLE, _REDUCTION_TABLE[1:]):
        if t0 <= temperature_c <= t1:
            frac = (temperature_c - t0) / (t1 - t0)
            v0 = (ky0, ke0)[column - 1]
            v1 = (ky1, ke1)[column - 1]
            return v0 + frac * (v1 - v0)
    raise AssertionError("unreachable")


def yield_reduction_factor(temperature_c: float) -> float:
    """k_y,theta — effective yield strength reduction factor."""
    return _interpolate(temperature_c, 1)


def modulus_reduction_factor(temperature_c: float) -> float:
    """k_E,theta — elastic modulus reduction factor."""
    return _interpolate(temperature_c, 2)


@dataclass
class ElevatedTemperatureProperties:
    material_key: str
    temperature_c: float
    k_y_theta: float
    k_e_theta: float
    original_fy_pa: float
    original_e_pa: float
    reduced_fy_pa: float
    reduced_e_pa: float


def reduced_properties(
    material_key: str, fy_pa: float, e_pa: float, temperature_c: float
) -> ElevatedTemperatureProperties:
    ky = yield_reduction_factor(temperature_c)
    ke = modulus_reduction_factor(temperature_c)
    return ElevatedTemperatureProperties(
        material_key=material_key, temperature_c=temperature_c,
        k_y_theta=ky, k_e_theta=ke,
        original_fy_pa=fy_pa, original_e_pa=e_pa,
        reduced_fy_pa=fy_pa * ky, reduced_e_pa=e_pa * ke,
    )


@dataclass
class FireMemberCheck:
    member_id: int
    stress_mpa: float
    reduced_fy_mpa: float
    utilisation: float
    status: str


@dataclass
class FireScreeningReport:
    title: str = "FIRE SCREENING (elevated-temperature strength check)"
    temperature_c: float = 20.0
    properties_by_material: dict[str, ElevatedTemperatureProperties] = field(default_factory=dict)
    checks: list[FireMemberCheck] = field(default_factory=list)
    n_failed: int = 0
    max_utilisation: float = 0.0
    source_citation: str = SOURCE_CITATION
    disclaimer: str = (
        "Strength/stiffness reduction only — no heating-rate, insulation, "
        "char or time-temperature modelling. Assumes UNIFORM temperature "
        "across the whole structure. Not a substitute for a certified "
        "fire-resistance design."
    )


def screen_fire(member_results, temperature_c: float,
               fy_by_member: dict[int, float], material_key_by_member: dict[int, str],
               original_e_by_material: dict[str, float],
               original_fy_by_material: dict[str, float]) -> FireScreeningReport:
    """
    Build the report from already-computed stresses (from a solve run at
    the REDUCED modulus — see server/api or a wiring layer for how E is
    substituted before calling solve()).
    """
    report = FireScreeningReport(temperature_c=temperature_c)
    for key, fy in original_fy_by_material.items():
        e = original_e_by_material.get(key, 0.0)
        report.properties_by_material[key] = reduced_properties(key, fy, e, temperature_c)

    worst = -1.0
    for result in member_results:
        material_key = material_key_by_member.get(result.member_id)
        props = report.properties_by_material.get(material_key)
        if props is None:
            continue
        stress_mpa = abs(result.stress) / 1e6
        fy_theta_mpa = props.reduced_fy_pa / 1e6
        utilisation = stress_mpa / fy_theta_mpa if fy_theta_mpa > 0 else float("inf")
        status = "pass" if utilisation <= 1.0 else "fail"
        report.checks.append(FireMemberCheck(
            member_id=result.member_id, stress_mpa=stress_mpa,
            reduced_fy_mpa=fy_theta_mpa, utilisation=utilisation, status=status,
        ))
        if status == "fail":
            report.n_failed += 1
        worst = max(worst, utilisation)

    report.max_utilisation = max(worst, 0.0)
    return report
