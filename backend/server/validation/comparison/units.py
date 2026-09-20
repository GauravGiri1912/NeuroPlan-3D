"""
NeuroPlan-3D — Explicit Unit Conversions for Validation

Every conversion used anywhere in the validation feature goes through one
of these named functions. This exists so a unit bug is a one-line, tested
fix in exactly one place, never a silent multiply scattered across the
comparison code.
"""


def mm_to_m(value_mm: float) -> float:
    return value_mm / 1000.0


def m_to_mm(value_m: float) -> float:
    return value_m * 1000.0


def kn_to_n(value_kn: float) -> float:
    return value_kn * 1000.0


def n_to_kn(value_n: float) -> float:
    return value_n / 1000.0


def mpa_to_pa(value_mpa: float) -> float:
    return value_mpa * 1.0e6


def pa_to_mpa(value_pa: float) -> float:
    return value_pa / 1.0e6


def cm2_to_m2(value_cm2: float) -> float:
    return value_cm2 * 1.0e-4


def m2_to_cm2(value_m2: float) -> float:
    return value_m2 * 1.0e4


def microstrain_to_strain(value_ue: float) -> float:
    return value_ue * 1.0e-6


def strain_to_microstrain(value_strain: float) -> float:
    return value_strain * 1.0e6
