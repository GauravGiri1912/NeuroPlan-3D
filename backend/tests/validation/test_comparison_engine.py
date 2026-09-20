"""
Comparison engine correctness — absolute/relative error, MAE, RMSE, and
the deliberate suppression of R² for small datasets.
"""
import math
import pytest

from server.validation.comparison.engine import compare_point, summarize, MIN_POINTS_FOR_R2
from server.validation.models import ParameterStatus


def test_absolute_and_relative_error():
    r = compare_point("s1", 1, "vertical_displacement", 10.0, 12.0, "mm", ParameterStatus.SOURCED)
    assert r.absolute_error == pytest.approx(2.0)
    assert r.relative_error == pytest.approx(0.2)


def test_relative_error_undefined_for_zero_experimental_value():
    r = compare_point("s1", 1, "x", 0.0, 5.0, "mm", ParameterStatus.SOURCED)
    assert r.relative_error is None


def test_mae_and_rmse_hand_calculated():
    # Errors: 1, 2, 3 -> MAE = 2, RMSE = sqrt((1+4+9)/3) = sqrt(14/3)
    results = [
        compare_point("s1", 1, "x", 10.0, 11.0, "mm", ParameterStatus.SOURCED),
        compare_point("s2", 2, "x", 10.0, 12.0, "mm", ParameterStatus.SOURCED),
        compare_point("s3", 3, "x", 10.0, 13.0, "mm", ParameterStatus.SOURCED),
    ]
    s = summarize(results)
    assert s.mae == pytest.approx(2.0)
    assert s.rmse == pytest.approx(math.sqrt(14 / 3))
    assert s.max_absolute_error == pytest.approx(3.0)


def test_r_squared_suppressed_below_minimum_points():
    assert MIN_POINTS_FOR_R2 >= 4
    results = [
        compare_point(f"s{i}", i, "x", 10.0, 10.0 + i, "mm", ParameterStatus.SOURCED)
        for i in range(MIN_POINTS_FOR_R2 - 1)
    ]
    s = summarize(results)
    assert s.r_squared is None
    assert "not meaningful" in s.r_squared_note.lower() or "not computed" in s.r_squared_note.lower()


def test_r_squared_computed_with_enough_points():
    # Perfect linear correlation -> R^2 = 1
    results = [
        compare_point(f"s{i}", i, "x", float(i), float(i), "mm", ParameterStatus.SOURCED)
        for i in range(1, 6)
    ]
    s = summarize(results)
    assert s.r_squared is not None
    assert s.r_squared == pytest.approx(1.0, abs=1e-9)


def test_empty_comparison_list_is_handled_honestly():
    s = summarize([])
    assert s.n_points == 0
    assert s.mae is None
    assert s.rmse is None


def test_uncertainty_never_fabricated():
    s = summarize([compare_point("s1", 1, "x", 1.0, 1.1, "mm", ParameterStatus.SOURCED)])
    assert "not provided" in s.uncertainty_note.lower()
