"""
NeuroPlan-3D — Validation Comparison Engine

Computes comparison metrics between experimental measurements and
NeuroPlan solver output. Every metric is computed from the actual values
passed in — nothing here is a lookup table or a cached "expected" result.

R² is only computed when there are enough independent points for it to be
meaningful (n >= 4 is used as a floor — below that, a correlation
coefficient is close to guaranteed-high by construction and is not
reported, per the explicit instruction not to display statistically
meaningless metrics for tiny datasets).
"""
from __future__ import annotations

import math

from ..models import ComparisonResult, ComparisonSummary, ParameterStatus

MIN_POINTS_FOR_R2 = 4


def compare_point(
    sensor_id: str,
    node_id: int | None,
    quantity: str,
    experimental_value: float,
    neuroplan_value: float,
    units: str,
    mapping_status: ParameterStatus,
    mapping_note: str = "",
) -> ComparisonResult:
    """One experimental-vs-NeuroPlan comparison, with both raw errors."""
    absolute_error = abs(neuroplan_value - experimental_value)
    relative_error = (
        absolute_error / abs(experimental_value)
        if abs(experimental_value) > 1e-12
        else None
    )
    return ComparisonResult(
        sensor_id=sensor_id,
        node_id=node_id,
        quantity=quantity,
        experimental_value=experimental_value,
        neuroplan_value=neuroplan_value,
        units=units,
        absolute_error=absolute_error,
        relative_error=relative_error,
        mapping_status=mapping_status,
        mapping_note=mapping_note,
    )


def summarize(results: list[ComparisonResult]) -> ComparisonSummary:
    """
    Aggregate statistics over a set of comparisons.

    Only comparisons with a numerically defined relative error contribute
    to relative-error statistics (a zero experimental value has no
    meaningful relative error and is excluded from that average, not
    treated as 0% or infinite).
    """
    n = len(results)
    if n == 0:
        return ComparisonSummary(n_points=0)

    abs_errors = [r.absolute_error for r in results]
    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(e * e for e in abs_errors) / n)
    max_abs_error = max(abs_errors)

    rel_errors = [r.relative_error for r in results if r.relative_error is not None]
    max_rel_error = max(rel_errors) if rel_errors else None

    r_squared = None
    r_squared_note = ""
    if n < MIN_POINTS_FOR_R2:
        r_squared_note = (
            f"R² not computed: only {n} comparison point(s) — "
            f"a correlation statistic is not meaningful below "
            f"{MIN_POINTS_FOR_R2} independent points."
        )
    else:
        exp_vals = [r.experimental_value for r in results]
        pred_vals = [r.neuroplan_value for r in results]
        mean_exp = sum(exp_vals) / n
        ss_tot = sum((v - mean_exp) ** 2 for v in exp_vals)
        ss_res = sum((e - p) ** 2 for e, p in zip(exp_vals, pred_vals))
        if ss_tot > 1e-12:
            r_squared = 1.0 - ss_res / ss_tot
        else:
            r_squared_note = "R² not computed: experimental values have zero variance."

    return ComparisonSummary(
        n_points=n,
        mae=mae,
        rmse=rmse,
        max_absolute_error=max_abs_error,
        max_relative_error=max_rel_error,
        r_squared=r_squared,
        r_squared_note=r_squared_note,
    )
