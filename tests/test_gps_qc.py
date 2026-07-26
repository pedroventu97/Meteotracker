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
