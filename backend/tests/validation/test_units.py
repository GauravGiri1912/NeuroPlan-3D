"""Unit conversion correctness — each function tested independently."""
import pytest
from server.validation.comparison import units


def test_mm_m_roundtrip():
    assert units.mm_to_m(1000.0) == pytest.approx(1.0)
    assert units.m_to_mm(1.0) == pytest.approx(1000.0)
    assert units.mm_to_m(units.m_to_mm(3.14159)) == pytest.approx(3.14159)


def test_kn_n_roundtrip():
    assert units.kn_to_n(80.0) == pytest.approx(80000.0)
    assert units.n_to_kn(80000.0) == pytest.approx(80.0)


def test_mpa_pa_roundtrip():
    assert units.mpa_to_pa(207639.8) == pytest.approx(207639.8e6)
    assert units.pa_to_mpa(207639.8e6) == pytest.approx(207639.8)


def test_cm2_m2_roundtrip():
    assert units.cm2_to_m2(8.4) == pytest.approx(8.4e-4)
    assert units.m2_to_cm2(8.4e-4) == pytest.approx(8.4)


def test_microstrain_roundtrip():
    assert units.microstrain_to_strain(1000.0) == pytest.approx(1e-3)
    assert units.strain_to_microstrain(1e-3) == pytest.approx(1000.0)
