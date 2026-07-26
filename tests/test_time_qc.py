import pandas as pd

from meteotracker_qc.time_qc import detect_time_issues


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
