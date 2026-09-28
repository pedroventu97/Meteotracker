import pytest
from pathlib import Path

import numpy as np
import pandas as pd

from meteotracker_qc.stabilization import detect_sensor_stabilization

RAW_ROOT = Path(__file__).resolve().parent.parent / "data" / "raw"


def test_sensor_stabilization_detects_warm_up():
    temperatures = pd.Series([25.0, 25.1, 25.4, 25.5, 25.6, 25.7, 25.8, 25.9, 26.0, 26.1])
    out = detect_sensor_stabilization(temperatures, window=3, min_stable_seconds=5)
    assert "qc_sensor_stabilization" in out.columns
    assert out["qc_sensor_stabilization"].sum() >= 1


def test_warm_up_is_detected():
    temps = pd.Series([20.0, 20.2, 20.4, 20.6, 20.8, 21.0])
    out = detect_sensor_stabilization(temps)
    assert out["qc_sensor_stabilization"].sum() >= 1


def _is_leading_window(flags: pd.Series) -> bool:
    """True if `flags` is True for some prefix and False for the rest (never
    reactivates once it turns False)."""
    values = flags.to_numpy()
    if not values.any():
        return True
    first_false = np.argmin(values) if not values.all() else len(values)
    if first_false == len(values):
        return True
    return not values[first_false:].any()


def _ramp_then_flat_session(ramp_len=20, flat_len=40, rate_c_per_s=-0.2, step_s=1.0):
    times = pd.date_range("2026-01-01 09:00:00", periods=ramp_len + flat_len, freq=pd.Timedelta(seconds=step_s))
    ramp = [20.0 + i * rate_c_per_s for i in range(ramp_len)]
    flat_value = ramp[-1]
    temps = pd.Series(ramp + [flat_value] * flat_len)
    segment_id = pd.Series(0, index=temps.index)
    return temps, pd.Series(times), segment_id


def test_stabilization_concentrated_in_leading_rows():
    temps, time_utc, segment_id = _ramp_then_flat_session()
    config = {"warmup": {"slope_threshold_c_per_s": 0.02, "min_stable_seconds": 10, "window_size_s": 5.0}}
    out = detect_sensor_stabilization(temps, config=config, time_utc=time_utc, segment_id=segment_id)
    flags = out["qc_sensor_stabilization"]
    assert _is_leading_window(flags)
    assert flags.iloc[:15].any()  # flagged during the ramp
    assert not flags.iloc[-10:].any()  # settled well before the end


def test_late_thermal_anomaly_does_not_reactivate_stabilization():
    temps, time_utc, segment_id = _ramp_then_flat_session(ramp_len=20, flat_len=40)
    temps = temps.copy()
    temps.iloc[50:54] = temps.iloc[50] + 5.0  # a late, sharp real-looking transition
    config = {"warmup": {"slope_threshold_c_per_s": 0.02, "min_stable_seconds": 10, "window_size_s": 5.0}}
    out = detect_sensor_stabilization(temps, config=config, time_utc=time_utc, segment_id=segment_id)
    flags = out["qc_sensor_stabilization"]
    assert _is_leading_window(flags)
    assert not flags.iloc[48:].any()  # the late anomaly itself is never (re-)flagged as stabilization


def test_stabilization_works_at_1s_cadence():
    temps, time_utc, segment_id = _ramp_then_flat_session(step_s=1.0)
    config = {"warmup": {"slope_threshold_c_per_s": 0.02, "min_stable_seconds": 10, "window_size_s": 5.0}}
    out = detect_sensor_stabilization(temps, config=config, time_utc=time_utc, segment_id=segment_id)
    assert out["qc_sensor_stabilization"].sum() > 0
    assert _is_leading_window(out["qc_sensor_stabilization"])


def test_stabilization_works_at_2s_cadence():
    temps, time_utc, segment_id = _ramp_then_flat_session(step_s=2.0)
    config = {"warmup": {"slope_threshold_c_per_s": 0.02, "min_stable_seconds": 10, "window_size_s": 5.0}}
    out = detect_sensor_stabilization(temps, config=config, time_utc=time_utc, segment_id=segment_id)
    assert out["qc_sensor_stabilization"].sum() > 0
    assert _is_leading_window(out["qc_sensor_stabilization"])


def test_stabilization_interrupted_by_initial_gap_becomes_restart_recovery():
    # A very short first segment (3 rows, well under min_stable_seconds) is
    # immediately followed by a gap -- segment 0 can never confirm stability
    # (segment_too_short) and is entirely flagged qc_sensor_stabilization;
    # segment 1 (after the gap) is a restart, not a session start, so any
    # instability there must show up as qc_segment_restart_recovery instead.
    times = pd.date_range("2026-01-01 09:00:00", periods=3, freq="1s").tolist()
    times += [t + pd.Timedelta(seconds=60) for t in pd.date_range("2026-01-01 09:00:10", periods=30, freq="1s")]
    time_utc = pd.Series(times)
    segment_id = pd.Series([0, 0, 0] + [1] * 30)
    temps = pd.Series([20.0, 20.1, 20.2] + [22.0 - i * 0.15 for i in range(30)])
    config = {"warmup": {"slope_threshold_c_per_s": 0.02, "min_stable_seconds": 10, "window_size_s": 5.0}}
    out = detect_sensor_stabilization(temps, config=config, time_utc=time_utc, segment_id=segment_id)
    assert out["qc_sensor_stabilization"].iloc[:3].all()
    assert not out["qc_sensor_stabilization"].iloc[3:].any()
    assert out["qc_segment_restart_recovery"].iloc[:3].sum() == 0
    assert out["qc_segment_restart_recovery"].iloc[3:].any()


def test_stabilization_never_reached_is_capped_by_max_window():
    n = 40
    times = pd.date_range("2026-01-01 09:00:00", periods=n, freq="1s")
    # Oscillating temperature: slope never settles below the threshold.
    temps = pd.Series([20.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(n)])
    segment_id = pd.Series(0, index=temps.index)
    config = {"warmup": {"slope_threshold_c_per_s": 0.02, "min_stable_seconds": 10, "max_window_s": 15.0, "window_size_s": 5.0}}
    out = detect_sensor_stabilization(temps, config=config, time_utc=pd.Series(times), segment_id=segment_id)
    assert (out["stabilization_window_end_reason"] == "STABILIZATION_NOT_REACHED").all()
    flags = out["qc_sensor_stabilization"]
    assert flags.iloc[:15].all()  # capped leading window (max_window_s=15s @ 1 Hz)
    assert not flags.iloc[16:].any()
    assert _is_leading_window(flags)  # still never reactivates, even capped


def test_min_stable_seconds_is_actually_used():
    temps, time_utc, segment_id = _ramp_then_flat_session(ramp_len=10, flat_len=50, rate_c_per_s=-0.3)
    base_cfg = {"warmup": {"slope_threshold_c_per_s": 0.02, "window_size_s": 5.0}}
    short_cfg = {"warmup": {**base_cfg["warmup"], "min_stable_seconds": 5}}
    long_cfg = {"warmup": {**base_cfg["warmup"], "min_stable_seconds": 30}}
    out_short = detect_sensor_stabilization(temps, config=short_cfg, time_utc=time_utc, segment_id=segment_id)
    out_long = detect_sensor_stabilization(temps, config=long_cfg, time_utc=time_utc, segment_id=segment_id)
    assert out_long["qc_sensor_stabilization"].sum() > out_short["qc_sensor_stabilization"].sum()


@pytest.mark.real_data
def test_real_data_regression_stabilization_no_longer_scattered_mid_trip():
    """Regression for the audit finding: on the real 06-20 campaign, the old
    whole-trip detector flagged 130 rows, 127 of them (98%) after row 120.
    The fixed detector must be a genuine leading window (never reactivates).
    """
    from meteotracker_qc.gps_qc import detect_gps_issues
    from meteotracker_qc.time_qc import detect_time_issues

    csv_path = RAW_ROOT / "06-20" / "20260620T12_48_24_mtdicambo_AC4D162B317E_Bologna-Bologna.csv"
    assert csv_path.exists(), f"regression fixture missing: {csv_path}"
    raw = pd.read_csv(csv_path, na_values=["-"])
    t = detect_time_issues(raw)
    g = detect_gps_issues(t)
    out = detect_sensor_stabilization(
        g["Temp[°C]"], time_utc=g["time_utc"], segment_id=g["segment_id"], speed_kmh=g["speed_device_kmh"]
    )
    flags = out["qc_sensor_stabilization"]
    assert flags.sum() > 0
    assert _is_leading_window(flags)
    n_flagged = int(flags.sum())
    idx_true = np.flatnonzero(flags.to_numpy())
    n_beyond_120 = int((idx_true > 120).sum())
    # The old bug flagged 127/130 (98%) beyond row 120; the fix must not
    # reproduce that pattern of *scattered* late reactivation. Some flagged
    # rows legitimately beyond row 120 are fine (a slow-to-stabilize leading
    # window), as long as the region is contiguous from row 0 (already
    # checked by _is_leading_window above).
    assert idx_true[0] == 0
