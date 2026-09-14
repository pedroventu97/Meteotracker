import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.detrending import (
    compute_experimental_detrending, is_detrending_eligible, session_mean_deltas,
)

T0 = pd.Timestamp("2026-02-13T09:00:00Z")


def _df(n=60, step_s=60, temp_fn=None):
    times = [T0 + pd.Timedelta(seconds=i * step_s) for i in range(n)]
    temps = [temp_fn(i) if temp_fn else 10.0 for i in range(n)]
    return pd.DataFrame({
        "time_utc": times, "canonical_temperature_c": temps,
        "temporal_candidate_recommended": [True] * n,
    })


def _m2(trend=0.0, dominant=0.2):
    return {"trend_c_per_min": trend, "dominant_group_fraction": dominant}


def test_not_eligible_when_assessability_insufficient():
    eligible, warnings = is_detrending_eligible("PARTIALLY_ASSESSABLE", "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "STABLE", _m2())
    assert eligible is False
    assert "NOT_ELIGIBLE_ASSESSABILITY_INSUFFICIENT" in warnings


def test_not_eligible_when_diagnosis_not_supported():
    eligible, warnings = is_detrending_eligible("ASSESSABLE", "INCONCLUSIVE_TEMPORAL_EFFECT", "STABLE", _m2())
    assert eligible is False
    assert "NOT_ELIGIBLE_DIAGNOSIS_NOT_SUPPORTED" in warnings


def test_not_eligible_when_sensitivity_unstable():
    eligible, warnings = is_detrending_eligible("ASSESSABLE", "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "HIGHLY_SENSITIVE", _m2())
    assert eligible is False
    assert "NOT_ELIGIBLE_SENSITIVITY_UNSTABLE" in warnings


def test_not_eligible_when_dominated_by_single_group():
    eligible, warnings = is_detrending_eligible("ASSESSABLE", "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "STABLE", _m2(dominant=0.6))
    assert eligible is False
    assert "NOT_ELIGIBLE_DOMINATED_BY_SINGLE_GROUP" in warnings


def test_eligible_when_all_conditions_met():
    eligible, warnings = is_detrending_eligible("ASSESSABLE", "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "STABLE", _m2())
    assert eligible is True
    assert warnings == []


def test_nonlinear_diagnosis_adds_linear_approximation_warning():
    eligible, warnings = is_detrending_eligible("ASSESSABLE", "POSSIBLE_NONLINEAR_BACKGROUND_CHANGE", "STABLE", _m2())
    assert eligible is True
    assert "NONLINEAR_DETREND_NOT_IMPLEMENTED_USING_LINEAR_APPROXIMATION" in warnings


def test_original_temperature_column_is_never_modified():
    df = _df(temp_fn=lambda i: 10.0 + i * 0.1)
    session_end = df["time_utc"].max()
    out = compute_experimental_detrending(df, "temporal_candidate_recommended", T0, session_end, _m2(trend=0.05), eligible=True)
    assert (out["temp_original_c"] == df["canonical_temperature_c"]).all()


def test_reference_time_is_session_midpoint_and_trend_is_zero_there():
    df = _df(n=60, step_s=60)
    session_end = df["time_utc"].max()
    out = compute_experimental_detrending(df, "temporal_candidate_recommended", T0, session_end, _m2(trend=0.05), eligible=True)
    t_ref = out["detrending_reference_time"].iloc[0]
    expected_ref = T0 + (session_end - T0) / 2
    assert t_ref == expected_ref
    closest_idx = (df["time_utc"] - t_ref).abs().idxmin()
    # closest sample is at most half a 60s step (30s) away from t_ref -> at
    # 0.05 C/min that's at most 0.025 C of residual trend at that row.
    assert abs(out.loc[closest_idx, "temporal_trend_candidate_c"]) <= 0.026


def test_known_trend_is_removed_making_detrended_series_flatter():
    slope_c_per_min = 0.05
    df = _df(n=60, step_s=60, temp_fn=lambda i: 10.0 + (i * 60) * (slope_c_per_min / 60.0))
    session_end = df["time_utc"].max()
    out = compute_experimental_detrending(df, "temporal_candidate_recommended", T0, session_end, _m2(trend=slope_c_per_min), eligible=True)
    raw_std = df["canonical_temperature_c"].std()
    detrended_std = out["temp_detrended_experimental_c"].dropna().std()
    assert detrended_std < raw_std * 0.1


def test_extrapolation_beyond_cap_yields_nan_and_warning():
    # session span is short (60*60=3600s), a row far outside 1.5x that from
    # t_ref must be capped.
    df = _df(n=60, step_s=60)
    session_end = df["time_utc"].max()
    far_row = pd.DataFrame({"time_utc": [session_end + pd.Timedelta(hours=5)], "canonical_temperature_c": [12.0], "temporal_candidate_recommended": [False]})
    df2 = pd.concat([df, far_row], ignore_index=True)
    out = compute_experimental_detrending(df2, "temporal_candidate_recommended", T0, session_end, _m2(trend=0.05), eligible=True)
    last = out.iloc[-1]
    assert pd.isna(last["temp_detrended_experimental_c"])
    assert "EXTRAPOLATION_RANGE_EXCEEDED" in last["detrending_warning_codes"]


def test_non_candidate_in_range_row_gets_extrapolated_from_model_warning():
    df = _df(n=10, step_s=60, temp_fn=lambda i: 10.0 + i * 0.01)
    df.loc[5, "temporal_candidate_recommended"] = False
    session_end = df["time_utc"].max()
    out = compute_experimental_detrending(df, "temporal_candidate_recommended", T0, session_end, _m2(trend=0.02), eligible=True)
    assert "EXTRAPOLATED_FROM_MODEL" in out.loc[5, "detrending_warning_codes"]
    assert pd.notna(out.loc[5, "temp_detrended_experimental_c"])


def test_not_eligible_produces_all_nan_detrended_columns():
    df = _df()
    session_end = df["time_utc"].max()
    out = compute_experimental_detrending(df, "temporal_candidate_recommended", T0, session_end, _m2(), eligible=False, base_warnings=["NOT_ELIGIBLE_DIAGNOSIS_NOT_SUPPORTED"])
    assert out["temp_detrended_experimental_c"].isna().all()
    assert (out["detrending_supported"] == False).all()  # noqa: E712
    assert (out["detrending_warning_codes"] == "NOT_ELIGIBLE_DIAGNOSIS_NOT_SUPPORTED").all()


def test_session_mean_deltas_smaller_after_successful_detrending():
    # Non-uniform sampling (candidate points concentrated in the second,
    # warmer half of a linear-trend session) biases the raw mean away from
    # the true reference-time value; a correct detrending should remove
    # that bias regardless of how the sampling is distributed in time.
    slope_c_per_min = 0.05
    session_span_s = 3600.0
    offsets = list(np.linspace(0, session_span_s * 0.3, 10)) + list(np.linspace(session_span_s * 0.7, session_span_s, 30))
    times = [T0 + pd.Timedelta(seconds=o) for o in offsets]
    temps = [10.0 + o * (slope_c_per_min / 60.0) for o in offsets]
    df = pd.DataFrame({"time_utc": times, "canonical_temperature_c": temps, "temporal_candidate_recommended": [True] * len(times)})
    session_end = T0 + pd.Timedelta(seconds=session_span_s)
    out = compute_experimental_detrending(df, "temporal_candidate_recommended", T0, session_end, _m2(trend=slope_c_per_min), eligible=True)
    deltas = session_mean_deltas(out, T0, session_end)
    assert abs(deltas["delta_session_mean_detrended_experimental_c"]) < abs(deltas["delta_session_mean_raw_c"]) * 0.05
