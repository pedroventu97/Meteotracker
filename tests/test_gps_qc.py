import numpy as np
import pandas as pd

from meteotracker_qc.time_qc import detect_time_issues
from meteotracker_qc.gps_qc import detect_gps_issues


def test_gps_freeze_and_jump_detection():
    df = pd.DataFrame(
        {
            "Time": pd.to_datetime([
                "2026-01-01 09:00:00",
                "2026-01-01 09:00:01",
                "2026-01-01 09:00:02",
                "2026-01-01 09:00:03",
                "2026-01-01 09:00:04",
            ]),
            "Lat": [44.49, 44.49, 44.49, 44.49, 44.50],
            "Lon": [11.34, 11.34, 11.34, 11.34, 11.34],
        }
    )
    out = detect_gps_issues(df)
    assert out["qc_gps_freeze"].sum() >= 3
    assert out["qc_gps_jump"].sum() >= 1


def test_missing_coordinates_are_flagged():
    df = pd.DataFrame({"Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01"]), "Lat": [44.49, np.nan], "Lon": [11.34, 11.34]})
    out = detect_gps_issues(detect_time_issues(df))
    assert out["qc_coord_missing"].sum() >= 1


def test_true_stationary_event_with_zero_speed_is_flagged():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01", "2026-01-01 09:00:02"]),
        "Lat": [44.49, 44.49, 44.49],
        "Lon": [11.34, 11.34, 11.34],
        "Speed[km/h]": [0.0, 0.0, 0.0],
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert out["qc_stationary"].sum() >= 1


def test_repeated_coordinates_without_speed_are_not_confused_with_stationary():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01", "2026-01-01 09:00:02"]),
        "Lat": [44.49, 44.49, 44.49],
        "Lon": [11.34, 11.34, 11.34],
        "Speed[km/h]": [10.0, 10.0, 10.0],
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert out["qc_coord_repeated"].sum() >= 1
    assert out["qc_stationary"].sum() == 0


def test_possible_gps_freeze_is_flagged():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01", "2026-01-01 09:00:02"]),
        "Lat": [44.49, 44.49, 44.49],
        "Lon": [11.34, 11.34, 11.34],
        "Speed[km/h]": [5.0, 5.0, 5.0],
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert out["qc_possible_gps_freeze"].sum() >= 1


def test_freeze_followed_by_jump_is_flagged():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01", "2026-01-01 09:00:02", "2026-01-01 09:00:03"]),
        "Lat": [44.49, 44.49, 44.49, 44.50],
        "Lon": [11.34, 11.34, 11.34, 11.34],
        "Speed[km/h]": [0.0, 0.0, 0.0, 0.0],
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert out["qc_gps_freeze"].sum() >= 1
    assert out["qc_gps_jump"].sum() >= 1


def test_single_gps_jump_is_flagged():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01"]),
        "Lat": [44.49, 44.50],
        "Lon": [11.34, 11.34],
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert out["qc_gps_jump"].sum() >= 1


def test_impossible_acceleration_is_flagged():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01", "2026-01-01 09:00:02"]),
        "Lat": [44.49, 44.5000, 44.5020],
        "Lon": [11.34, 11.34, 11.34],
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert out["qc_speed_disagreement"].sum() >= 1 or out["qc_impossible_acceleration"].sum() >= 1


def test_no_step_computed_across_segment_boundary():
    times = pd.date_range("2026-01-01 09:00:00", periods=10, freq="1s").tolist()
    times_after = [t + pd.Timedelta(seconds=30.0) for t in times[5:]]
    df = pd.DataFrame({
        "Time": times[:5] + times_after,
        "Lat": [44.49 + 0.0001 * i for i in range(10)],
        "Lon": [11.34] * 10,
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert out["segment_id"].iloc[4] == 0
    assert out["segment_id"].iloc[5] == 1
    # First row of the new segment has valid coordinates but no previous-row
    # step is computable across the gap.
    assert out["Lat"].iloc[5] == out["Lat"].iloc[5]  # not NaN
    assert pd.isna(out["distance_from_previous_m"].iloc[5])
    assert pd.isna(out["speed_gps_kmh"].iloc[5])
    assert out["speed_evidence_class"].iloc[5] in {"NOT_EVALUABLE_AFTER_GAP", "DEVICE_ONLY"}


def test_isolated_position_outlier_detected_via_snapback():
    df = pd.DataFrame({
        "Time": pd.date_range("2026-01-01 09:00:00", periods=4, freq="1s"),
        "Lat": [44.4900, 44.4900, 44.4950, 44.4900],
        "Lon": [11.3400, 11.3410, 11.3410, 11.3420],
    })
    config = {"gps": {"gps_jump_distance_m": 1000.0, "gps_jump_dt_s": 2.0, "isolated_outlier_excess_m": 40.0}}
    out = detect_gps_issues(detect_time_issues(df), config=config)
    assert out["qc_isolated_position_outlier"].iloc[2]
    assert out["qc_spatial_jump"].iloc[2]
    assert not out["qc_gps_jump"].iloc[2]  # the loosened distance/dt threshold alone would miss this detour


def test_sustained_route_deviation_is_not_isolated_outlier():
    # A real 90-degree road corner: the path turns once (east -> north) and
    # continues in the new direction -- it never snaps back to the
    # pre-turn heading the way test_isolated_position_outlier_detected_via_snapback
    # does. Any 3-point detour test inherently sees *some* chord-vs-corner
    # excess at a sharp real corner (here ~74 m, vs ~1037 m for a genuine
    # snapback of comparable step size) -- distinguishing the two is a
    # matter of threshold choice, which is exactly what this test checks:
    # a threshold set above the corner's genuine excess does not flag it.
    df = pd.DataFrame({
        "Time": pd.date_range("2026-01-01 09:00:00", periods=5, freq="1s"),
        "Lat": [44.4900, 44.4900, 44.4900, 44.4950, 44.5000],
        "Lon": [11.3400, 11.3410, 11.3420, 11.3420, 11.3420],
    })
    config = {"gps": {"gps_jump_distance_m": 2000.0, "gps_jump_dt_s": 2.0, "isolated_outlier_excess_m": 200.0}}
    out = detect_gps_issues(detect_time_issues(df), config=config)
    assert not out["qc_isolated_position_outlier"].any()
    assert not out["qc_gps_jump"].any()


def test_coord_repeated_tolerance_flags_near_but_not_bit_identical_points():
    close = pd.DataFrame({
        "Time": pd.date_range("2026-01-01 09:00:00", periods=2, freq="1s"),
        "Lat": [44.4900000, 44.4900135],  # ~1.5 m apart
        "Lon": [11.3400000, 11.3400000],
    })
    far = pd.DataFrame({
        "Time": pd.date_range("2026-01-01 09:00:00", periods=2, freq="1s"),
        "Lat": [44.4900000, 44.4900270],  # ~3.0 m apart
        "Lon": [11.3400000, 11.3400000],
    })
    config = {"gps": {"coord_repeated_tolerance_m": 2.0}}
    out_close = detect_gps_issues(detect_time_issues(close), config=config)
    out_far = detect_gps_issues(detect_time_issues(far), config=config)
    assert out_close["qc_coord_repeated"].iloc[1]
    assert not out_far["qc_coord_repeated"].iloc[1]


def _steady_move_df(n=5, speed_col=True):
    times = pd.date_range("2026-01-01 09:00:00", periods=n, freq="1s")
    data = {
        "Time": times,
        "Lat": [44.4900 + 0.0001 * i for i in range(n)],
        "Lon": [11.3400] * n,
    }
    if speed_col:
        data["Speed[km/h]"] = [12.0] * n
    return pd.DataFrame(data)


def test_speed_evidence_both_available_consistent():
    df = _steady_move_df()
    # 0.0001 deg lat/s ~= 11.13 m/s ~= 40.1 km/h GPS-implied speed; set the
    # device reading to match closely so the two sources agree.
    df["Speed[km/h]"] = [40.1] * len(df)
    out = detect_gps_issues(detect_time_issues(df))
    assert (out["speed_evidence_class"].iloc[1:] == "BOTH_AVAILABLE_CONSISTENT").all()
    assert not out["qc_speed_disagreement"].any()


def test_speed_evidence_both_available_disagree():
    df = _steady_move_df()
    df["Speed[km/h]"] = [80.0] * len(df)  # device reports far more than the ~13 km/h GPS-implied speed
    out = detect_gps_issues(detect_time_issues(df))
    assert (out["speed_evidence_class"].iloc[1:] == "BOTH_AVAILABLE_DISAGREE").all()
    assert out["qc_speed_disagreement"].iloc[1:].all()


def test_speed_evidence_device_only_when_gps_missing():
    df = _steady_move_df()
    df.loc[2, "Lat"] = np.nan  # breaks the GPS step computation at rows 2 and 3
    out = detect_gps_issues(detect_time_issues(df))
    assert out["speed_evidence_class"].iloc[2] in {"DEVICE_ONLY", "NOT_EVALUABLE_AFTER_GAP"}
    assert out["speed_device_valid"].iloc[2]
    assert not out["speed_gps_valid"].iloc[2]


def test_speed_evidence_gps_only_when_device_missing():
    df = _steady_move_df(speed_col=False)
    out = detect_gps_issues(detect_time_issues(df))
    assert (out["speed_evidence_class"].iloc[1:] == "GPS_ONLY").all()
    assert not out["speed_device_valid"].any()


def test_speed_evidence_neither_available():
    df = pd.DataFrame({
        "Time": pd.date_range("2026-01-01 09:00:00", periods=3, freq="1s"),
        "Lat": [np.nan, np.nan, np.nan],
        "Lon": [np.nan, np.nan, np.nan],
    })
    out = detect_gps_issues(detect_time_issues(df))
    # Row 0 is structurally a segment start (no previous point to step from)
    # regardless of data availability, so it reports the more specific
    # NOT_EVALUABLE_AFTER_GAP; rows 1+ correctly report NEITHER_AVAILABLE.
    assert (out["speed_evidence_class"].iloc[1:] == "NEITHER_AVAILABLE").all()


def test_gps_freeze_meteo_corroboration_distinguishes_alive_sensor_from_static():
    base = {
        "Time": pd.date_range("2026-01-01 09:00:00", periods=4, freq="1s"),
        "Lat": [44.49, 44.49, 44.49, 44.49],
        "Lon": [11.34, 11.34, 11.34, 11.34],
        "Speed[km/h]": [0.0, 0.0, 0.0, 0.0],
    }
    static_sensor = pd.DataFrame({**base, "Temp[°C]": [20.0, 20.0, 20.0, 20.0]})
    alive_sensor = pd.DataFrame({**base, "Temp[°C]": [20.0, 20.4, 20.8, 21.2]})

    out_static = detect_gps_issues(detect_time_issues(static_sensor))
    out_alive = detect_gps_issues(detect_time_issues(alive_sensor))

    # The confirmed-freeze boolean itself is identical for both (position +
    # speed evidence is the same); the meteo signal is exposed as a separate
    # diagnostic corroboration column, not folded into the hard boolean.
    assert out_static["qc_gps_freeze"].tolist() == out_alive["qc_gps_freeze"].tolist()
    assert not out_static["gps_freeze_meteo_still_varying"].any()
    assert out_alive["gps_freeze_meteo_still_varying"].any()
