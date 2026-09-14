import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.session_qc.metrics import (
    _one_group_metrics,
    _union,
    compute_segment_metrics,
    compute_session_metrics,
    valid_interval_mask,
)

FAMILY_LOOKUP = {
    "qc_gps_freeze": "GPS", "qc_sensor_stabilization": "STABILIZATION",
    "qc_temp_isolated_spike": "THERMAL", "qc_sampling_gap_long": "TEMPORAL",
}


def _make_ref(times, segment_id, **overrides):
    n = len(times)
    times = pd.to_datetime(times)
    df = pd.DataFrame({
        "time_utc": times,
        "dt_s": pd.Series(times).diff().dt.total_seconds(),
        "segment_id": segment_id,
        "segment_start_reason": ["campaign_start"] + ["long_gap"] * (n - 1) if n > 0 else [],
        "segment_end_reason": ["campaign_end"] * n,
        "qc_segment_break": [False] * n,
        "qc_sampling_gap_long": [False] * n,
        "qc_sampling_gap_short": [False] * n,
        "distance_from_previous_m": [np.nan] + [10.0] * (n - 1),
        "gps_valid": [True] * n,
        "keep_permissive_true": [True] * n,
        "keep_recommended_true": [True] * n,
        "keep_restrictive_true": [True] * n,
        "sampling_interval_expected_seconds": [1.0] * n,
        "qc_primary_reason": [None] * n,
        "qc_exclusion_reasons_recommended": [""] * n,
        "qc_reason_count": [0] * n,
        "canonical_temperature_c": [20.0] * n,
        "stabilization_window_end_reason": ["slope_confirmed_stable"] * n,
        "stabilization_seconds_from_segment_start": list(range(n)),
        "source_row": list(range(n)),
    })
    for k, v in overrides.items():
        df[k] = v
    return df


def _fix_first_row_break_reasons(df):
    # segment_start_reason should be constant per real segment_id; simplify
    # by overwriting with a single sensible per-segment value in tests that
    # don't care about it.
    df["segment_start_reason"] = df.groupby("segment_id")["segment_start_reason"].transform("first")
    return df


def test_point_to_segment_aggregation():
    times = pd.date_range("2026-01-01 09:00:00", periods=10, freq="1s")
    df = _make_ref(times, segment_id=[0] * 5 + [1] * 5)
    seg = compute_segment_metrics(df, "campaign_x", "file.csv", FAMILY_LOOKUP)
    assert len(seg) == 2
    assert seg["n_raw"].sum() == 10
    assert seg.loc[seg.segment_id == 0, "n_raw"].iloc[0] == 5
    assert seg.loc[seg.segment_id == 1, "n_raw"].iloc[0] == 5


def test_segment_to_session_aggregation_n_raw_matches():
    times = pd.date_range("2026-01-01 09:00:00", periods=12, freq="1s")
    df = _make_ref(times, segment_id=[0] * 4 + [1] * 4 + [2] * 4)
    seg = compute_segment_metrics(df, "campaign_x", "file.csv", FAMILY_LOOKUP)
    session = compute_session_metrics(df, seg, "campaign_x", "file.csv", FAMILY_LOOKUP)
    assert session["n_raw"] == 12 == seg["n_raw"].sum()
    assert session["n_segments"] == 3


def test_nominal_time_span_differs_from_observed_across_a_gap():
    times = list(pd.date_range("2026-01-01 09:00:00", periods=10, freq="1s"))
    gap_s = 500.0
    # Shift the tail so the actual gap between row 4 and row 5 is exactly
    # gap_s (the unshifted 1s step between them is absorbed into the shift).
    shift = pd.Timedelta(seconds=gap_s) - pd.Timedelta(seconds=1)
    times = times[:5] + [t + shift for t in times[5:]]
    segment_id = [0] * 5 + [1] * 5
    df = _make_ref(times, segment_id)
    df.loc[5, "qc_segment_break"] = True
    df.loc[5, "qc_sampling_gap_long"] = True
    df.loc[5, "distance_from_previous_m"] = np.nan  # no distance carried across the gap

    seg = compute_segment_metrics(df, "c", "f.csv", FAMILY_LOOKUP)
    session = compute_session_metrics(df, seg, "c", "f.csv", FAMILY_LOOKUP)

    # nominal span includes the gap, observed excludes it
    assert session["nominal_time_span_s"] > session["observed_sampling_duration_s"]
    assert session["nominal_time_span_s"] - session["observed_sampling_duration_s"] == pytest.approx(gap_s)


def test_gap_not_counted_as_observed_time():
    times = list(pd.date_range("2026-01-01 09:00:00", periods=6, freq="1s"))
    gap_s = 1000.0
    shift = pd.Timedelta(seconds=gap_s) - pd.Timedelta(seconds=1)
    times = times[:3] + [t + shift for t in times[3:]]
    df = _make_ref(times, segment_id=[0, 0, 0, 1, 1, 1])
    df.loc[3, "qc_segment_break"] = True
    df.loc[3, "qc_sampling_gap_long"] = True

    session = compute_session_metrics(df, compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP), "c", "f", FAMILY_LOOKUP)
    assert session["missing_gap_duration_s"] == pytest.approx(gap_s)
    # 5 positive 1s steps observed (2 within segment 0, 2 within segment 1); the gap step itself excluded
    assert session["observed_sampling_duration_s"] == pytest.approx(4.0)


def test_distance_not_calculated_across_segment_break():
    times = pd.date_range("2026-01-01 09:00:00", periods=4, freq="1s")
    df = _make_ref(times, segment_id=[0, 0, 1, 1])
    df["qc_segment_break"] = [False, False, True, False]
    # Adversarial: even if a stray distance value were present at the break
    # row (should never happen upstream), it must not be counted.
    df["distance_from_previous_m"] = [np.nan, 10.0, 999.0, 10.0]

    session = compute_session_metrics(df, compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP), "c", "f", FAMILY_LOOKUP)
    assert session["observed_distance_km"] == pytest.approx(20.0 / 1000.0)


def test_valid_duration_recommended_excludes_non_kept_intervals():
    times = pd.date_range("2026-01-01 09:00:00", periods=6, freq="1s")
    keep = [True, True, False, True, True, True]
    df = _make_ref(times, segment_id=[0] * 6, keep_recommended_true=keep)
    mask = valid_interval_mask(df, "keep_recommended_true")
    # intervals (1,2] and (2,3] touch the excluded row 2 -> both False
    assert mask.tolist() == [False, True, False, False, True, True]
    session = compute_session_metrics(df, compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP), "c", "f", FAMILY_LOOKUP)
    assert session["valid_duration_recommended_s"] == pytest.approx(3.0)  # 3 valid 1s intervals


def test_valid_distance_recommended_requires_gps_valid_too():
    times = pd.date_range("2026-01-01 09:00:00", periods=4, freq="1s")
    df = _make_ref(
        times, segment_id=[0] * 4,
        distance_from_previous_m=[np.nan, 10.0, 10.0, 10.0],
        gps_valid=[True, True, False, True],
    )
    # Row 2 is not gps_valid -> intervals (1,2] and (2,3] excluded from valid distance;
    # interval (0,1] is unaffected (both its endpoints, rows 0 and 1, are gps_valid).
    session = compute_session_metrics(df, compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP), "c", "f", FAMILY_LOOKUP)
    assert session["valid_distance_recommended_km"] == pytest.approx(10.0 / 1000.0)
    assert session["observed_distance_km"] == pytest.approx(30.0 / 1000.0)


def test_overlapping_flag_fractions_are_not_summed():
    n = 4
    times = pd.date_range("2026-01-01 09:00:00", periods=n, freq="1s")
    df = _make_ref(times, segment_id=[0] * n)
    # Every row triggers BOTH a spike and a rate anomaly -- naive summing
    # would give 200%; the union must give 100%.
    df["qc_temp_isolated_spike"] = [True] * n
    df["qc_temp_rate_anomaly"] = [True] * n
    session = compute_session_metrics(df, compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP), "c", "f", FAMILY_LOOKUP)
    assert session["thermal_problem_fraction"] == pytest.approx(1.0)
    assert session["temp_spike_fraction"] == pytest.approx(1.0)
    assert session["temp_rate_anomaly_fraction"] == pytest.approx(1.0)


def test_nominal_equals_observed_within_a_single_segment_invariant():
    times = pd.date_range("2026-01-01 09:00:00", periods=8, freq="1s")
    df = _make_ref(times, segment_id=[0] * 8)
    seg = compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP)
    row = seg.iloc[0]
    assert row["nominal_time_span_s"] == pytest.approx(row["observed_sampling_duration_s"])


def test_primary_and_secondary_reasons_are_deterministic():
    n = 6
    times = pd.date_range("2026-01-01 09:00:00", periods=n, freq="1s")
    df = _make_ref(
        times, segment_id=[0] * n,
        keep_recommended_true=[False, False, False, True, True, True],
        qc_primary_reason=["qc_gps_freeze", "qc_gps_freeze", "qc_sensor_stabilization", None, None, None],
        qc_exclusion_reasons_recommended=[
            "qc_gps_freeze", "qc_gps_freeze;qc_sensor_stabilization", "qc_sensor_stabilization", "", "", "",
        ],
        qc_reason_count=[1, 2, 1, 0, 0, 0],
    )
    seg = compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP)
    row1 = seg.iloc[0]
    assert row1["primary_exclusion_reason"] == "qc_gps_freeze"  # mode: 2 occurrences vs 1
    assert row1["primary_exclusion_family"] == "GPS"
    assert "qc_sensor_stabilization" in row1["secondary_exclusion_reasons"]
    assert "qc_gps_freeze" not in row1["secondary_exclusion_reasons"]

    # Re-running must give the identical result (determinism, no randomness/order dependence).
    seg2 = compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP)
    assert seg2.iloc[0]["primary_exclusion_reason"] == row1["primary_exclusion_reason"]


def test_multi_flagged_fraction_and_exclusion_reason_count():
    n = 4
    times = pd.date_range("2026-01-01 09:00:00", periods=n, freq="1s")
    df = _make_ref(
        times, segment_id=[0] * n,
        keep_recommended_true=[False, False, True, True],
        qc_reason_count=[2, 1, 0, 0],
    )
    seg = compute_segment_metrics(df, "c", "f", FAMILY_LOOKUP)
    row = seg.iloc[0]
    assert row["multi_flagged_fraction"] == pytest.approx(0.25)  # 1 of 4 rows has count>1
    assert row["exclusion_reason_count"] == pytest.approx(1.5)  # mean over the 2 excluded rows
