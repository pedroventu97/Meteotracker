from __future__ import annotations

import numpy as np
import pandas as pd


def detect_low_speed_and_ventilation(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """Low-speed / radiative-ventilation-risk evidence, treated as a risk
    signal (per the thesis's own framing of ~7 km/h as a RECS ventilation
    concern) rather than an automatic thermal-error exclusion rule.

    Expects `speed_device_kmh`, `speed_gps_kmh`, `dt_s`, `segment_id` to
    already be present (as produced by gps_qc.py / time_qc.py upstream).
    """
    cfg = config or {}
    vent_cfg = cfg.get("ventilation", {})
    low_speed_threshold_kmh = float(vent_cfg.get("low_speed_threshold_kmh", 7.0))
    day_start_hour = float(vent_cfg.get("day_start_local_hour", 7.0))
    day_end_hour = float(vent_cfg.get("day_end_local_hour", 20.0))

    out = df.copy()
    speed_device = pd.to_numeric(out.get("speed_device_kmh", pd.Series(index=out.index, dtype=float)), errors="coerce")
    speed_gps = pd.to_numeric(out.get("speed_gps_kmh", pd.Series(index=out.index, dtype=float)), errors="coerce")
    dt_s = pd.to_numeric(out.get("dt_s", pd.Series(index=out.index, dtype=float)), errors="coerce")
    segment_id = out.get("segment_id", pd.Series(0, index=out.index))

    device_low = speed_device <= low_speed_threshold_kmh
    gps_low = speed_gps <= low_speed_threshold_kmh
    out["qc_low_speed_device"] = device_low.fillna(False)
    out["qc_low_speed_gps"] = gps_low.fillna(False)

    same_segment_prev = segment_id == segment_id.shift(1)
    dt_effective = dt_s.where(same_segment_prev, 0.0).fillna(0.0)

    def _running_duration(flag: pd.Series) -> pd.Series:
        run_id = flag.ne(flag.shift(1)).cumsum()
        run_elapsed = dt_effective.groupby(run_id).cumsum()
        return run_elapsed.where(flag, 0.0)

    out["low_speed_device_duration_s"] = _running_duration(out["qc_low_speed_device"])
    out["low_speed_gps_duration_s"] = _running_duration(out["qc_low_speed_gps"])

    device_ok = speed_device.notna()
    gps_ok = speed_gps.notna()
    conditions = [
        device_ok & gps_ok & device_low.fillna(False) & gps_low.fillna(False),
        device_ok & gps_ok & device_low.fillna(False) & ~gps_low.fillna(False),
        device_ok & gps_ok & ~device_low.fillna(False) & gps_low.fillna(False),
        device_ok & gps_ok & ~device_low.fillna(False) & ~gps_low.fillna(False),
        device_ok & ~gps_ok & device_low.fillna(False),
        ~device_ok & gps_ok & gps_low.fillna(False),
    ]
    choices = [
        "BOTH_BELOW_THRESHOLD",
        "DEVICE_BELOW_GPS_ABOVE",
        "GPS_BELOW_DEVICE_ABOVE",
        "BOTH_ABOVE_THRESHOLD",
        "DEVICE_BELOW_GPS_MISSING",
        "GPS_BELOW_DEVICE_MISSING",
    ]
    # Default (neither available, or only one available and it is *not* low):
    # a single non-low reading is not strong enough on its own to declare
    # ventilation adequate with confidence -- conservative NOT_ASSESSABLE
    # rather than a 7th positive class not requested by the spec.
    out["ventilation_evidence_class"] = np.select(conditions, choices, default="NOT_ASSESSABLE")

    out["qc_low_ventilation_possible"] = out["ventilation_evidence_class"].isin([
        "BOTH_BELOW_THRESHOLD", "DEVICE_BELOW_GPS_ABOVE", "GPS_BELOW_DEVICE_ABOVE",
        "DEVICE_BELOW_GPS_MISSING", "GPS_BELOW_DEVICE_MISSING",
    ])

    time_local = out.get("time_local")
    if time_local is not None:
        hour = time_local.dt.hour.astype(float) + time_local.dt.minute.astype(float) / 60.0
        is_day = (hour >= day_start_hour) & (hour < day_end_hour)
        bucket = np.where(is_day, "day", "night")
        out["local_hour_bucket"] = pd.Series(bucket, index=out.index).where(time_local.notna())
    else:
        out["local_hour_bucket"] = pd.Series(pd.NA, index=out.index, dtype="object")

    radiation_raw = out.get("Radiation[]")
    if radiation_raw is not None:
        radiation_numeric = pd.to_numeric(radiation_raw, errors="coerce")
    else:
        radiation_numeric = pd.Series(np.nan, index=out.index)
    if radiation_numeric.notna().any():
        median_val = float(radiation_numeric.median())
        context = np.where(
            radiation_numeric.isna(), "not_available",
            np.where(radiation_numeric >= median_val, "present_high_relative", "present_low_relative"),
        )
        out["radiation_context"] = context
    else:
        out["radiation_context"] = "not_available"

    return out


def detect_stop_events(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """Time-based stop lifecycle: qc_stationary (consumed as input, computed
    upstream in gps_qc.py) -> qc_stop_event (a stationary run lasting at
    least `stops.min_significant_stop_s`) -> qc_post_stop_recovery (until
    speed has stayed continuously above the ventilation threshold for
    `stops.recovery_min_duration_s`, on real elapsed time, with no new stop
    and no gap in between).
    """
    cfg = config or {}
    stops_cfg = cfg.get("stops", {})
    vent_cfg = cfg.get("ventilation", {})
    min_significant_stop_s = float(stops_cfg.get("min_significant_stop_s", 10.0))
    recovery_min_duration_s = float(stops_cfg.get("recovery_min_duration_s", 30.0))
    low_speed_threshold_kmh = float(vent_cfg.get("low_speed_threshold_kmh", 7.0))

    out = df.copy()
    n = len(out)
    stationary = out.get("qc_stationary", pd.Series(False, index=out.index)).fillna(False)
    dt_s = pd.to_numeric(out.get("dt_s", pd.Series(index=out.index, dtype=float)), errors="coerce")
    segment_id = out.get("segment_id", pd.Series(0, index=out.index))
    speed_device = pd.to_numeric(out.get("speed_device_kmh", pd.Series(index=out.index, dtype=float)), errors="coerce")
    speed_gps = pd.to_numeric(out.get("speed_gps_kmh", pd.Series(index=out.index, dtype=float)), errors="coerce")

    same_segment_prev = (segment_id == segment_id.shift(1)).to_numpy()
    dt_effective = dt_s.where(pd.Series(same_segment_prev, index=out.index), 0.0).fillna(0.0)

    run_id = stationary.ne(stationary.shift(1)).cumsum()
    run_elapsed = dt_effective.groupby(run_id).cumsum()
    out["stop_duration_s"] = run_elapsed.where(stationary, 0.0)

    run_total_duration = dt_effective.groupby(run_id).transform("sum")
    is_significant_run = stationary & (run_total_duration >= min_significant_stop_s)
    out["qc_stop_event"] = is_significant_run

    significant_run_ids = run_id.where(is_significant_run)
    unique_ids = sorted(pd.unique(significant_run_ids.dropna()))
    id_map = {v: i for i, v in enumerate(unique_ids)}
    out["stop_event_id"] = significant_run_ids.map(id_map).astype("Int64")

    reliable_speed = speed_device.where(speed_device.notna(), speed_gps)
    moving_ok = (reliable_speed > low_speed_threshold_kmh).fillna(False).to_numpy()
    stationary_arr = stationary.to_numpy()
    significant_arr = is_significant_run.to_numpy()
    dt_arr = dt_effective.to_numpy()

    qc_post_stop_recovery = np.zeros(n, dtype=bool)
    recovery_seconds_elapsed = np.full(n, np.nan)

    recovering = False
    elapsed = 0.0
    for i in range(n):
        started_this_row = False
        if i > 0 and significant_arr[i - 1] and not stationary_arr[i] and same_segment_prev[i]:
            recovering = True
            elapsed = 0.0
            started_this_row = True
        if recovering and not started_this_row and (not same_segment_prev[i] or stationary_arr[i]):
            recovering = False
        if recovering:
            if moving_ok[i]:
                elapsed += dt_arr[i]
            recovery_seconds_elapsed[i] = elapsed
            qc_post_stop_recovery[i] = True
            if elapsed >= recovery_min_duration_s:
                recovering = False

    out["qc_post_stop_recovery"] = qc_post_stop_recovery
    out["recovery_seconds_elapsed"] = recovery_seconds_elapsed
    return out
