import numpy as np
import pandas as pd

from meteotracker_qc.time_qc import detect_time_issues, estimate_expected_sampling_interval_s


def test_timestamp_duplicate_and_gap_flags():
    df = pd.DataFrame(
        {
            "Time": pd.to_datetime([
                "2026-01-01 09:00:00",
                "2026-01-01 09:00:00",
                "2026-01-01 09:00:01",
                "2026-01-01 09:00:05",
            ])
        }
    )
    out = detect_time_issues(df)
    assert out["qc_time_duplicate"].sum() >= 1
    assert out["qc_time_gap"].sum() == 1


def test_regular_timestamps_have_no_time_flags():
    df = pd.DataFrame({"Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01", "2026-01-01 09:00:02"])})
    out = detect_time_issues(df)
    assert not out["qc_time_duplicate"].any()
    assert not out["qc_time_gap"].any()
    assert not out["qc_time_order"].any()


def test_out_of_order_timestamps_are_flagged():
    df = pd.DataFrame({"Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:02", "2026-01-01 09:00:01"])})
    out = detect_time_issues(df)
    assert out["qc_time_order"].iloc[2]


def test_duplicate_timestamp_is_flagged():
    df = pd.DataFrame({"Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:00", "2026-01-01 09:00:01"])})
    out = detect_time_issues(df)
    assert out["qc_time_duplicate"].sum() >= 1


def test_duplicate_timestamp_with_different_measurements_preserves_rows():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:00"]),
        "Temp[°C]": [10.0, 11.0],
    })
    out = detect_time_issues(df)
    assert len(out) == len(df)
    assert out["qc_time_duplicate"].sum() == 2


def test_non_interpretable_timestamp_is_flagged():
    df = pd.DataFrame({"Time": ["not-a-timestamp", "2026-01-01 09:00:00"]})
    out = detect_time_issues(df)
    assert out["qc_time_parse"].iloc[0]


def test_temporal_gap_is_flagged():
    df = pd.DataFrame({"Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:00", "2026-01-01 09:00:05"])})
    out = detect_time_issues(df)
    assert out["qc_time_gap"].sum() >= 1


def test_explicit_utc_timestamp_is_classified_with_high_confidence():
    df = pd.DataFrame({"Time": ["2026-01-01T09:00:00+00:00"]})
    out = detect_time_issues(df)
    assert out["time_timezone_interpretation"].iloc[0] == "explicit_offset"
    assert out["timezone_confidence"].iloc[0] == 1.0


def test_naive_local_timestamp_is_not_treated_as_explicit():
    df = pd.DataFrame({"Time": ["2026-01-01 09:00:00"]})
    out = detect_time_issues(df)
    assert out["time_timezone_interpretation"].iloc[0] == "naive_or_unknown"
    assert out["timezone_confidence"].iloc[0] == 0.0


def test_cet_to_cest_transition_is_preserved():
    df = pd.DataFrame({"Time": ["2026-03-29T01:30:00+01:00", "2026-03-29T03:30:00+02:00"]})
    out = detect_time_issues(df)
    assert out["time_utc"].notna().all()


def _regular_session(n: int, step_s: float, start="2026-01-01 09:00:00"):
    times = pd.date_range(start, periods=n, freq=pd.Timedelta(seconds=step_s))
    return pd.DataFrame({"Time": times})


def test_estimate_expected_sampling_interval_1s_campaign():
    dt = pd.Series([1.0] * 30)
    assert estimate_expected_sampling_interval_s(dt) == 1.0


def test_estimate_expected_sampling_interval_2s_campaign():
    dt = pd.Series([2.0] * 30)
    assert estimate_expected_sampling_interval_s(dt) == 2.0


def test_estimate_expected_sampling_interval_excludes_its_own_gaps():
    dt = pd.Series([1.0] * 24 + [50.0])
    # 25 clean samples >= default min_samples_for_estimate(20); the one 50s
    # outlier must not drag the estimate away from the true 1 Hz cadence.
    assert estimate_expected_sampling_interval_s(dt) == 1.0


def test_estimate_expected_sampling_interval_falls_back_below_min_samples():
    dt = pd.Series([2.0] * 5)
    assert estimate_expected_sampling_interval_s(dt, fallback_dt_s=1.0) == 1.0


def test_adaptive_cadence_regular_1s_session_no_gap_flags():
    df = _regular_session(30, 1.0)
    out = detect_time_issues(df)
    assert out["sampling_interval_expected_seconds"].iloc[0] == 1.0
    assert not out["qc_sampling_gap_short"].any()
    assert not out["qc_sampling_gap_long"].any()
    assert not out["qc_segment_break"].any()
    assert (out["segment_id"] == 0).all()


def test_adaptive_cadence_regular_2s_session_no_gap_flags():
    df = _regular_session(30, 2.0)
    out = detect_time_issues(df)
    assert out["sampling_interval_expected_seconds"].iloc[0] == 2.0
    assert not out["qc_sampling_gap_short"].any()
    assert not out["qc_sampling_gap_long"].any()
    assert not out["qc_segment_break"].any()


def test_short_gap_flagged_without_segment_break():
    df = _regular_session(25, 1.0)
    times = df["Time"].tolist()
    # Shift row 10 and everything after it forward by 2s, so row 10 sits 3s
    # (between short=2.0 and long=5.0) after row 9, while every row from 10
    # onward keeps its own regular 1s cadence relative to the shifted point.
    times_after = [t + pd.Timedelta(seconds=2.0) for t in times[10:]]
    df["Time"] = times[:10] + times_after
    out = detect_time_issues(df)
    assert out["qc_sampling_gap_short"].iloc[10]
    assert not out["qc_sampling_gap_long"].iloc[10]
    assert not out["qc_segment_break"].iloc[10]
    assert (out["segment_id"] == 0).all()


def test_long_gap_triggers_segment_break_and_new_segment_id():
    df = _regular_session(25, 1.0)
    times = df["Time"].tolist()
    times_after = [t + pd.Timedelta(seconds=30.0) for t in times[10:]]
    df["Time"] = times[:10] + times_after
    out = detect_time_issues(df)
    assert out["qc_sampling_gap_long"].iloc[10]
    assert out["qc_segment_break"].iloc[10]
    assert out["segment_id"].iloc[9] == 0
    assert out["segment_id"].iloc[10] == 1
    assert (out["segment_id"].iloc[10:] == 1).all()
    # Valid points on both sides of the gap are preserved, not dropped.
    assert len(out) == len(df)


def test_segment_start_and_end_reason_vocabulary_is_deterministic():
    df = _regular_session(25, 1.0)
    times = df["Time"].tolist()
    times_after = [t + pd.Timedelta(seconds=30.0) for t in times[10:]]
    df["Time"] = times[:10] + times_after
    out = detect_time_issues(df)
    assert out["segment_start_reason"].iloc[0] == "campaign_start"
    assert out["segment_end_reason"].iloc[0] == "long_gap"
    assert out["segment_start_reason"].iloc[10] == "long_gap"
    assert out["segment_end_reason"].iloc[-1] == "campaign_end"
    allowed = {"campaign_start", "long_gap", "nonpositive_dt", "campaign_end"}
    assert set(out["segment_start_reason"].unique()) <= allowed
    assert set(out["segment_end_reason"].unique()) <= allowed


def test_duplicate_timestamp_alias_matches_legacy_column():
    df = pd.DataFrame({"Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:00", "2026-01-01 09:00:01"])})
    out = detect_time_issues(df)
    assert out["qc_duplicate_timestamp"].tolist() == out["qc_time_duplicate"].tolist()


def test_nonmonotonic_timestamp_alias_matches_legacy_column():
    df = pd.DataFrame({"Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:02", "2026-01-01 09:00:01"])})
    out = detect_time_issues(df)
    assert out["qc_nonmonotonic_timestamp"].tolist() == out["qc_time_order"].tolist()
    assert out["timestamp_order_valid"].tolist() == (~out["qc_time_order"]).tolist()
