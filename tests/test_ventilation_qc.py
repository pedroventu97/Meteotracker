import numpy as np
import pandas as pd

from meteotracker_qc.gps_qc import detect_gps_issues
from meteotracker_qc.time_qc import detect_time_issues
from meteotracker_qc.ventilation_qc import detect_low_speed_and_ventilation, detect_stop_events


def _prepared(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    return detect_gps_issues(detect_time_issues(df, config=config), config=config)


def test_low_speed_is_not_automatically_excluded_anywhere_by_this_module():
    # This module only produces flags/diagnostics; it must never drop rows.
    times = pd.date_range("2026-01-01 09:00:00", periods=10, freq="1s")
    df = pd.DataFrame({
        "Time": times,
        "Lat": [44.49] * 10,
        "Lon": [11.34] * 10,
        "Speed[km/h]": [3.0] * 10,
    })
    out = detect_low_speed_and_ventilation(_prepared(df))
    assert len(out) == len(df)
    assert out["qc_low_speed_device"].all()
    assert out["qc_low_ventilation_possible"].any()


def test_low_speed_at_night_and_during_day_are_both_labeled_not_auto_high_risk():
    times_night = pd.date_range("2026-01-01 02:00:00", periods=5, freq="1s")
    times_day = pd.date_range("2026-01-01 12:00:00", periods=5, freq="1s")
    df_night = pd.DataFrame({"Time": times_night, "Lat": [44.49] * 5, "Lon": [11.34] * 5, "Speed[km/h]": [2.0] * 5})
    df_day = pd.DataFrame({"Time": times_day, "Lat": [44.49] * 5, "Lon": [11.34] * 5, "Speed[km/h]": [2.0] * 5})

    out_night = detect_low_speed_and_ventilation(_prepared(df_night))
    out_day = detect_low_speed_and_ventilation(_prepared(df_day))

    assert (out_night["local_hour_bucket"] == "night").all()
    assert (out_day["local_hour_bucket"] == "day").all()
    # Same low-speed evidence in both cases -- the day/night distinction is
    # exposed as context, not folded into a different qc_low_ventilation_possible value.
    assert out_night["qc_low_ventilation_possible"].tolist() == out_day["qc_low_ventilation_possible"].tolist()


def test_ventilation_evidence_class_both_below_threshold():
    times = pd.date_range("2026-01-01 09:00:00", periods=3, freq="1s")
    df = pd.DataFrame({"Time": times, "Lat": [44.49] * 3, "Lon": [11.34] * 3, "Speed[km/h]": [1.0] * 3})
    out = detect_low_speed_and_ventilation(_prepared(df))
    assert (out["ventilation_evidence_class"].iloc[1:] == "BOTH_BELOW_THRESHOLD").all()


def test_radiation_context_uses_campaign_relative_median_not_absolute_cutoff():
    df = pd.DataFrame({
        "Time": pd.date_range("2026-01-01 09:00:00", periods=4, freq="1s"),
        "Lat": [44.49] * 4,
        "Lon": [11.34] * 4,
        "Radiation[]": [0.1, 0.2, 5.0, 8.0],
    })
    out = detect_low_speed_and_ventilation(_prepared(df))
    assert out["radiation_context"].iloc[0] == "present_low_relative"
    assert out["radiation_context"].iloc[3] == "present_high_relative"


def test_stop_event_and_post_stop_recovery_lifecycle():
    n = 40
    times = pd.date_range("2026-01-01 09:00:00", periods=n, freq="1s")
    lat = [44.4900 + 0.0002 * i for i in range(10)]  # moving
    lat += [lat[-1]] * 15  # stopped for 15s (>= min_significant_stop_s default 10)
    lat += [lat[-1] + 0.0002 * (i + 1) for i in range(15)]  # moving again (recovery)
    speed = [20.0] * 10 + [0.0] * 15 + [20.0] * 15
    df = pd.DataFrame({"Time": times, "Lat": lat, "Lon": [11.34] * n, "Speed[km/h]": speed})
    prepared = _prepared(df)
    out = detect_stop_events(prepared, config={"stops": {"min_significant_stop_s": 10.0, "recovery_min_duration_s": 5.0}})

    assert out["qc_stop_event"].iloc[12:24].any()
    assert out["stop_event_id"].notna().any()
    assert out["qc_post_stop_recovery"].iloc[25:30].any()
    # Recovery must eventually end (not flagged forever) once movement has
    # been sustained past recovery_min_duration_s.
    assert not out["qc_post_stop_recovery"].iloc[-1]


def test_recovery_is_time_based_at_1s_and_2s_cadence():
    def _build(step_s):
        n = 30
        times = pd.date_range("2026-01-01 09:00:00", periods=n, freq=pd.Timedelta(seconds=step_s))
        lat = [44.4900 + 0.0002 * i for i in range(8)]
        lat += [lat[-1]] * 12
        lat += [lat[-1] + 0.0002 * (i + 1) for i in range(10)]
        speed = [20.0] * 8 + [0.0] * 12 + [20.0] * 10
        return pd.DataFrame({"Time": times, "Lat": lat, "Lon": [11.34] * n, "Speed[km/h]": speed})

    config = {"stops": {"min_significant_stop_s": 10.0, "recovery_min_duration_s": 5.0}}
    for step_s in (1.0, 2.0):
        df = _build(step_s)
        prepared = _prepared(df, config=config)
        out = detect_stop_events(prepared, config=config)
        assert out["qc_post_stop_recovery"].any(), f"no recovery detected at step_s={step_s}"
        assert not out["qc_post_stop_recovery"].iloc[-1], f"recovery never ends at step_s={step_s}"


def test_stop_duration_resets_after_movement_resumes():
    n = 20
    times = pd.date_range("2026-01-01 09:00:00", periods=n, freq="1s")
    lat = [44.49] * 12 + [44.49 + 0.0002 * i for i in range(1, 9)]
    speed = [0.0] * 12 + [20.0] * 8
    df = pd.DataFrame({"Time": times, "Lat": lat, "Lon": [11.34] * n, "Speed[km/h]": speed})
    out = detect_stop_events(_prepared(df))
    assert out["stop_duration_s"].iloc[-1] == 0.0
