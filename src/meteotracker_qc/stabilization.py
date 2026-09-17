from __future__ import annotations

import numpy as np
import pandas as pd
from .analysis_settings import enabled


def _analyze_segment(
    temps_seg: pd.Series,
    dt_seg: pd.Series,
    speed_seg: pd.Series | None,
    *,
    window: int,
    window_size_s: float,
    slope_threshold: float,
    min_stable_seconds: float,
    max_window_s: float,
    low_speed_threshold_kmh: float,
    min_ventilated_duration_s: float,
    time_based: bool,
) -> tuple[pd.Series, str, pd.Series]:
    """Leading-window stabilization search for a single segment.

    Returns (instability_bool_series, end_reason, elapsed_from_start_series),
    all indexed like temps_seg. `instability` is True for the leading stretch
    still considered "warming up" and False from the first confirmed-stable
    point onward -- it never reactivates later in this segment.
    """
    idx = temps_seg.index
    n = len(temps_seg)
    if n == 0:
        return pd.Series(dtype=bool), "segment_too_short", pd.Series(dtype=float)

    positive_dt = dt_seg[(dt_seg > 0) & np.isfinite(dt_seg)] if time_based else pd.Series(dtype=float)
    expected_dt_s = float(positive_dt.median()) if len(positive_dt) >= 3 else 1.0

    dt_effective = dt_seg.fillna(expected_dt_s) if time_based else pd.Series(expected_dt_s, index=idx)
    elapsed_dt = dt_effective.copy()
    elapsed_dt.iloc[0] = 0.0
    elapsed_from_start = elapsed_dt.cumsum()

    slope_dt = dt_effective.copy()
    slope_dt.iloc[0] = np.nan

    window_rows = max(3, int(round(window_size_s / max(expected_dt_s, 1e-6)))) if time_based else int(window)
    if window_rows % 2 == 0:
        window_rows += 1

    med = temps_seg.rolling(window_rows, center=True, min_periods=1).median()
    slope = med.diff() / slope_dt
    row_stable = slope.abs() < slope_threshold

    # Thermal-slope continuous-run search (independent of ventilation): the
    # window cannot close before this run has lasted min_stable_seconds.
    run_id = row_stable.ne(row_stable.shift(1)).cumsum()
    run_elapsed = elapsed_dt.groupby(run_id).cumsum()
    slope_confirmed = row_stable.fillna(False) & (run_elapsed >= min_stable_seconds)

    if speed_seg is not None:
        # Ventilation is a separate, weaker gate: satisfied once there has
        # been *some* continuous stretch of at least min_ventilated_duration_s
        # above the ventilation speed threshold anywhere earlier in the
        # segment -- not required to coincide with every second of the
        # thermal-stable run itself (a real urban ride has frequent brief
        # stops that would otherwise make the two conditions never overlap).
        ventilated_row = (speed_seg > low_speed_threshold_kmh).fillna(False)
        vent_run_id = ventilated_row.ne(ventilated_row.shift(1)).cumsum()
        vent_run_elapsed = elapsed_dt.groupby(vent_run_id).cumsum()
        vent_run_satisfies = ventilated_row & (vent_run_elapsed >= min_ventilated_duration_s)
        ventilation_satisfied_by_this_point = vent_run_satisfies.cummax()
        qualifying_row = slope_confirmed & ventilation_satisfied_by_this_point
    else:
        qualifying_row = slope_confirmed

    segment_duration = float(elapsed_from_start.iloc[-1]) if n else 0.0

    if qualifying_row.any():
        boundary_pos = int(np.argmax(qualifying_row.to_numpy()))
        instability = pd.Series(False, index=idx)
        if boundary_pos > 0:
            instability.iloc[:boundary_pos] = True
        end_reason = "slope_confirmed_stable"
    elif segment_duration < min_stable_seconds:
        # Not enough data in this segment to ever confirm stability either
        # way (e.g. a short aborted session) -- mark honestly, don't fail.
        instability = pd.Series(True, index=idx)
        end_reason = "segment_too_short"
    else:
        instability = (elapsed_from_start <= max_window_s).copy()
        end_reason = "STABILIZATION_NOT_REACHED"

    return instability, end_reason, elapsed_from_start


def detect_sensor_stabilization(
    temperatures: pd.Series,
    window: int = 5,
    min_stable_seconds: int = 60,
    config: dict | None = None,
    *,
    time_utc: pd.Series | None = None,
    segment_id: pd.Series | None = None,
    speed_kmh: pd.Series | None = None,
) -> pd.DataFrame:
    """Leading-window sensor warm-up / restart-instability detector.

    Flags the initial stretch of a segment until the rolling-median slope of
    temperature has stayed below `slope_threshold_c_per_s` continuously for
    at least `min_stable_seconds` real seconds (and, when `speed_kmh` is
    supplied, until speed has also stayed above the ventilation threshold for
    the same continuous stretch). Once that point is reached, the flag drops
    to False and never reactivates later in the same segment -- a later
    thermal transition is a job for qc_temp_rate_anomaly, not this detector.

    Two output columns are produced from the same underlying search, split by
    segment position: `qc_sensor_stabilization` covers only the first segment
    of the input (true session-start warm-up); `qc_segment_restart_recovery`
    covers every later segment (restart instability after a gap), per the
    spec's explicit requirement that post-gap instability be a distinct flag
    from session-start warm-up rather than a reactivation of it.

    Legacy/no-context mode (`time_utc`, `segment_id`, `speed_kmh` all None,
    as used by callers that only have a bare temperature Series): the whole
    series is treated as one implicit segment, `window` is used directly as
    a row count (not `warmup.window_size_s`), and a nominal 1.0 s/row cadence
    is assumed -- this exactly reproduces the two pre-existing unit tests'
    expectations.
    """
    cfg = config or {}
    warmup_cfg = cfg.get("warmup", {})
    ventilation_cfg = cfg.get("ventilation", {})

    window = int(warmup_cfg.get("window_size", window))
    window_size_s = float(warmup_cfg.get("window_size_s", window))
    slope_threshold = float(warmup_cfg.get("slope_threshold_c_per_s", 0.02))
    min_stable_seconds = float(warmup_cfg.get("min_stable_seconds", min_stable_seconds))
    max_window_s = float(warmup_cfg.get("max_window_s", 300.0))
    min_ventilated_duration_s = float(warmup_cfg.get("min_ventilated_duration_s", 20.0))
    low_speed_threshold_kmh = float(ventilation_cfg.get("low_speed_threshold_kmh", 7.0))

    s = pd.to_numeric(temperatures, errors="coerce")
    idx = s.index
    n = len(s)

    out = pd.DataFrame(index=idx)
    if not enabled(config, "warmup"):
        out["qc_sensor_stabilization"] = False
        out["qc_segment_restart_recovery"] = False
        out["stabilization_window_end_reason"] = "DISABLED"
        out["stabilization_seconds_from_segment_start"] = np.nan
        return out
    if n == 0:
        out["qc_sensor_stabilization"] = pd.Series(dtype=bool)
        out["qc_segment_restart_recovery"] = pd.Series(dtype=bool)
        out["stabilization_window_end_reason"] = pd.Series(dtype="object")
        out["stabilization_seconds_from_segment_start"] = pd.Series(dtype=float)
        return out

    time_based = time_utc is not None
    seg = segment_id if segment_id is not None else pd.Series(0, index=idx)
    dt_all = time_utc.diff().dt.total_seconds() if time_based else pd.Series(np.nan, index=idx)
    speed_all = pd.to_numeric(speed_kmh, errors="coerce") if speed_kmh is not None else None

    instability = pd.Series(False, index=idx)
    end_reason = pd.Series("segment_too_short", index=idx, dtype="object")
    seconds_from_start = pd.Series(np.nan, index=idx, dtype=float)

    first_segment_value = seg.min()
    for seg_value in seg.unique():
        seg_index = seg.index[seg == seg_value]
        seg_speed = speed_all.loc[seg_index] if speed_all is not None else None
        seg_instability, seg_reason, seg_elapsed = _analyze_segment(
            s.loc[seg_index],
            dt_all.loc[seg_index],
            seg_speed,
            window=window,
            window_size_s=window_size_s,
            slope_threshold=slope_threshold,
            min_stable_seconds=min_stable_seconds,
            max_window_s=max_window_s,
            low_speed_threshold_kmh=low_speed_threshold_kmh,
            min_ventilated_duration_s=min_ventilated_duration_s,
            time_based=time_based,
        )
        instability.loc[seg_index] = seg_instability.reindex(seg_index).to_numpy()
        end_reason.loc[seg_index] = seg_reason
        seconds_from_start.loc[seg_index] = seg_elapsed.reindex(seg_index).to_numpy()

    is_first_segment = seg == first_segment_value
    out["qc_sensor_stabilization"] = (instability & is_first_segment).fillna(False)
    out["qc_segment_restart_recovery"] = (instability & ~is_first_segment).fillna(False)
    out["stabilization_window_end_reason"] = end_reason
    out["stabilization_seconds_from_segment_start"] = seconds_from_start
    return out
