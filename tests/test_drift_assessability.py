import pandas as pd

from meteotracker_qc.session_qc.session_status import compute_drift_assessability

FORBIDDEN_VALUES = {"TEMPORALLY_STABLE", "SENSOR_DRIFT", "BACKGROUND_CHANGE"}


def _ref(n=10, lat_start=44.49, lat_end=44.49, lon_start=11.34, lon_end=11.34, temps=None):
    times = pd.date_range("2026-01-01 09:00:00", periods=n, freq="1s")
    return pd.DataFrame({
        "time_utc": times,
        "canonical_latitude": [lat_start] + [44.495] * (n - 2) + [lat_end],
        "canonical_longitude": [lon_start] + [11.345] * (n - 2) + [lon_end],
        "canonical_temperature_c": temps if temps is not None else [20.0] * n,
    })


def test_drift_vocabulary_never_includes_a_real_diagnosis():
    ref = _ref()
    out = compute_drift_assessability(ref, nominal_time_span_s=200.0, n_segments=1, keep_fraction_recommended=0.9, profile="recommended_session")
    assert out["temporal_drift_assessability"] not in FORBIDDEN_VALUES
    assert out["temporal_drift_assessability"] in {"ASSESSABLE", "PARTIALLY_ASSESSABLE", "NOT_ASSESSABLE"}


def test_too_short_session_is_not_assessable_for_drift():
    ref = _ref(n=3)
    out = compute_drift_assessability(ref, nominal_time_span_s=2.0, n_segments=1, keep_fraction_recommended=0.9, profile="recommended_session")
    assert out["temporal_drift_assessability"] == "NOT_ASSESSABLE"


def test_comparable_start_end_locations_with_good_data_is_assessable():
    ref = _ref(lat_start=44.4900, lat_end=44.4901, lon_start=11.3400, lon_end=11.3401)  # ~15m apart
    out = compute_drift_assessability(ref, nominal_time_span_s=200.0, n_segments=1, keep_fraction_recommended=0.9, profile="recommended_session")
    assert out["start_end_locations_comparable"] is True
    assert out["temporal_drift_assessability"] == "ASSESSABLE"


def test_far_apart_start_end_locations_flagged_with_warning():
    ref = _ref(lat_start=44.4900, lat_end=44.6000, lon_start=11.3400, lon_end=11.5000)  # far apart
    out = compute_drift_assessability(ref, nominal_time_span_s=200.0, n_segments=1, keep_fraction_recommended=0.9, profile="recommended_session")
    assert out["start_end_locations_comparable"] is False
    assert "do_not_interpret" in out["start_end_comparison_warning"]


def test_start_end_temperature_difference_reported_descriptively_only():
    ref = _ref(temps=[20.0] * 9 + [21.5])
    out = compute_drift_assessability(ref, nominal_time_span_s=200.0, n_segments=1, keep_fraction_recommended=0.9, profile="recommended_session")
    assert out["raw_start_end_temperature_difference_c"] == pytest_approx(1.5)
    # Descriptive only -- never promoted into a thermal-quality classification here.
    assert "thermal_quality_status" not in out
    assert "session_qc_status" not in out


def pytest_approx(value):
    import pytest
    return pytest.approx(value, abs=1e-6)
