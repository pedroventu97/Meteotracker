from __future__ import annotations

import numpy as np
import pandas as pd


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def detect_meteo_issues(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """Note: `config` is the *full* pipeline config (like detect_gps_issues /
    detect_sensor_stabilization), not just the `physical_limits` sub-dict --
    this function reads `config["physical_limits"]` and `config["thermal"]`
    internally. The sole caller (pipeline.py) is updated accordingly; no test
    passes a non-None config, so this is not a breaking change here.
    """
    cfg = config or {}
    physical_cfg = cfg.get("physical_limits", {})
    thermal_cfg = cfg.get("thermal", {})
    out = df.copy()
    temp = _coerce_numeric(out.get("Temp[°C]", pd.Series(index=out.index, dtype=float)))
    humidity = _coerce_numeric(out.get("Hum[%]", pd.Series(index=out.index, dtype=float)))
    pressure = _coerce_numeric(out.get("Press[mbar]", pd.Series(index=out.index, dtype=float)))

    temp_low = float(physical_cfg.get("temp_min_c", -40))
    temp_high = float(physical_cfg.get("temp_max_c", 60))
    humidity_low = float(physical_cfg.get("humidity_min_pct", 0))
    humidity_high = float(physical_cfg.get("humidity_max_pct", 100))
    pressure_low = float(physical_cfg.get("pressure_min_mbar", 850))
    pressure_high = float(physical_cfg.get("pressure_max_mbar", 1100))

    out["qc_temp_impossible"] = (temp < temp_low) | (temp > temp_high)
    out["qc_humidity_impossible"] = (humidity < humidity_low) | (humidity > humidity_high)
    out["qc_pressure_impossible"] = (pressure < pressure_low) | (pressure > pressure_high)
    # Documented, unimplemented placeholders (a softer "contextually
    # implausible but not physically impossible" band). Never fabricated as
    # False -- left as nullable/NA so a reader cannot mistake "not computed"
    # for "checked and fine". See reports/targeted_qc_implementation.md for
    # why this pass did not find real data justifying implementing them.
    out["qc_temp_suspect"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out["qc_humidity_suspect"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out["qc_pressure_suspect"] = pd.Series(pd.NA, index=out.index, dtype="boolean")

    dt_s = _coerce_numeric(out.get("dt_s", pd.Series(index=out.index, dtype=float)))
    segment_id = out.get("segment_id", pd.Series(0, index=out.index))

    spike_window_s = float(thermal_cfg.get("spike_window_s", 5.0))
    spike_mad_multiplier = float(thermal_cfg.get("spike_mad_multiplier", 3.0))
    spike_floor_c = float(thermal_cfg.get("spike_floor_c", 0.2))
    rate_anomaly_threshold = float(thermal_cfg.get("rate_anomaly_threshold_c_per_s", 0.25))
    rate_anomaly_persistence_s = float(thermal_cfg.get("rate_anomaly_persistence_s", 20.0))
    plateau_std_epsilon = float(thermal_cfg.get("plateau_std_epsilon_c", 0.02))
    plateau_min_duration_s = float(thermal_cfg.get("plateau_min_duration_s", 120.0))

    if "sampling_interval_expected_seconds" in out.columns and out["sampling_interval_expected_seconds"].notna().any():
        expected_dt_s = float(out["sampling_interval_expected_seconds"].iloc[0])
    else:
        expected_dt_s = 1.0  # legacy/no-context fallback, matches the old hardcoded window=5 rows @ 1 Hz

    window_rows = max(3, int(round(spike_window_s / max(expected_dt_s, 1e-6))))
    if window_rows % 2 == 0:
        window_rows += 1  # keep an odd, centered window like the legacy implementation

    rolling = temp.rolling(window_rows, center=True, min_periods=3).median()
    mad = temp.rolling(window_rows, center=True, min_periods=3).apply(lambda x: np.median(np.abs(x - np.median(x))))
    spike = (temp - rolling).abs() > (spike_mad_multiplier * mad + spike_floor_c)
    out["qc_temp_isolated_spike"] = spike.fillna(False)
    out["qc_temp_spike"] = out["qc_temp_isolated_spike"]  # deprecated legacy-compatibility alias

    # Rate of change, gated on segment continuity: never evaluated across a
    # gap (NaN there, not a fabricated value).
    same_segment_prev = segment_id == segment_id.shift(1)
    temp_rate_c_per_s = (temp.diff() / dt_s).where(same_segment_prev)
    out["temp_rate_c_per_s"] = temp_rate_c_per_s

    elevated = (temp_rate_c_per_s.abs() > rate_anomaly_threshold).fillna(False)
    sign_at_elevated = np.sign(temp_rate_c_per_s).where(elevated, 0)
    run_change = elevated.ne(elevated.shift(1)) | (sign_at_elevated != sign_at_elevated.shift(1))
    run_id = run_change.cumsum()
    run_duration_s = dt_s.fillna(0.0).groupby(run_id).transform("sum")
    # A same-signed elevated run lasting >= rate_anomaly_persistence_s is a
    # real, sustained urban-microclimate transition, not an anomaly -- the
    # thesis's own qualitative description of crossing different
    # environments. De-escalate every row in such a run, not just its start.
    sustained = elevated & (run_duration_s >= rate_anomaly_persistence_s)
    out["qc_temp_rate_anomaly"] = elevated & ~sustained

    plateau_window_rows = max(3, int(round(plateau_min_duration_s / max(expected_dt_s, 1e-6))))
    rolling_std = temp.rolling(plateau_window_rows, min_periods=max(3, plateau_window_rows // 2)).std()
    out["qc_sensor_plateau_possible"] = (rolling_std < plateau_std_epsilon).fillna(False)

    return out
