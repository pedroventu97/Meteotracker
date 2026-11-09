"""E0-QC-R R1: duplicated timestamps (dt == 0) must not open a segment (bug fix) and are handled as flagged duplicates."""
import numpy as np
import pandas as pd

from meteotracker_qc.gps_qc import detect_gps_issues
from meteotracker_qc.meteo_qc import detect_meteo_issues
from meteotracker_qc.stabilization import detect_sensor_stabilization
from meteotracker_qc.time_qc import detect_time_issues


def _frame(times, temps=None, lat=None, lon=None, speed=None):
    n = len(times)
    return pd.DataFrame({
        "Time": times,
        "Lat": lat if lat is not None else 44.49 + np.arange(n) * 5e-5,
        "Lon": lon if lon is not None else np.full(n, 11.34),
        "Temp[°C]": temps if temps is not None else np.full(n, 20.0),
        "Speed[km/h]": speed if speed is not None else np.full(n, 20.0),
    })


def _ts(seconds):
    base = pd.Timestamp("2026-06-01T10:00:00+02:00")
    return [(base + pd.Timedelta(seconds=float(s))).isoformat() for s in seconds]


def test_dt0_does_not_open_a_segment_and_is_flagged():
    # 2-0-2 jitter pattern seen in E0: the sample at t+1 is stamped t
    out = detect_time_issues(_frame(_ts([0, 1, 3, 3, 5, 6, 7])))
    assert out["segment_id"].nunique() == 1
    assert not out["qc_segment_break"].any()
    assert out["qc_duplicate_timestamp"].sum() == 2  # both rows sharing the instant
    assert out["qc_time_nonpositive_dt"].sum() == 1  # internal signal unchanged
    assert set(out["segment_start_reason"]) == {"campaign_start"}


def test_backward_step_still_opens_a_segment():
    out = detect_time_issues(_frame(_ts([0, 1, 2, 1.0 - 0.5, 3, 4])))
    assert out["segment_id"].nunique() == 2
    assert out["qc_time_backward_dt"].sum() == 1
    assert "backward_dt" in set(out["segment_start_reason"])


def test_legacy_switch_reproduces_pre_fix_segmentation():
    cfg = {"time": {"legacy_nonpositive_dt_segment_break": True}}
    out = detect_time_issues(_frame(_ts([0, 1, 3, 3, 5, 6, 7])), config=cfg)
    assert out["segment_id"].nunique() == 2
    assert "nonpositive_dt" in set(out["segment_start_reason"])


def test_duplicate_record_only_for_identical_content():
    t = _ts([0, 1, 1, 2, 2, 3])
    temps = [20.0, 20.1, 20.1, 20.2, 20.3, 20.3]
    lat = [44.0, 44.001, 44.001, 44.002, 44.0025, 44.003]
    out = detect_time_issues(_frame(t, temps=temps, lat=lat, speed=[10, 10, 10, 10, 10, 10]))
    # row 2 is an exact copy of row 1 (same instant, same content); row 4 shares the instant of row 3 but differs
    assert out["qc_duplicate_record"].tolist() == [False, False, True, False, False, False]
    assert out["qc_duplicate_timestamp"].sum() == 4


def test_no_infinite_kinematics_or_rates_at_dt0():
    f = _frame(_ts([0, 1, 3, 3, 5, 6, 7]), temps=[20, 20.1, 20.2, 20.4, 20.5, 20.5, 20.6])
    out = detect_meteo_issues(detect_gps_issues(detect_time_issues(f)), {})
    for col in ("speed_gps_kmh", "acceleration_gps_mps2", "temp_rate_c_per_s"):
        v = pd.to_numeric(out[col], errors="coerce")
        assert not np.isinf(v).any(), col
    dup_row = out.index[out["dt_s"] == 0][0]
    assert pd.isna(out.loc[dup_row, "speed_gps_kmh"])
    assert not out.loc[dup_row, "qc_unrealistic_speed"]
    assert not out["qc_temp_rate_anomaly"].any()


def test_dt0_does_not_create_restart_recovery_nor_break_stability():
    n = 400
    secs = list(range(n))
    secs_dup = secs[:200] + [199] + secs[200:]  # one duplicated stamp in the middle
    temps = np.r_[np.linspace(25, 20, 60), np.full(n - 60, 20.0)]
    temps_dup = np.r_[temps[:200], temps[199], temps[200:]]
    cfg = {"warmup": {"window_size_s": 5.0, "slope_threshold_c_per_s": 0.02, "min_stable_seconds": 60,
                      "max_window_s": 300.0, "min_ventilated_duration_s": 20.0}}
    res = []
    for s, T in ((secs, temps), (secs_dup, temps_dup)):
        t = detect_time_issues(_frame(_ts(s), temps=T, speed=np.full(len(s), 30.0)))
        w = detect_sensor_stabilization(t["Temp[°C]"], config=cfg, time_utc=t["time_utc"],
                                        segment_id=t["segment_id"], speed_kmh=t["Speed[km/h]"])
        res.append(w)
    assert not res[1]["qc_segment_restart_recovery"].any()
    assert res[0]["qc_sensor_stabilization"].sum() == res[1]["qc_sensor_stabilization"].sum()
