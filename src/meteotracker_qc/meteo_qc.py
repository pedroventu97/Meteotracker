from __future__ import annotations

import numpy as np
import pandas as pd


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def detect_meteo_issues(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    cfg = config or {}
    out = df.copy()
    temp = _coerce_numeric(out.get("Temp[°C]", pd.Series(index=out.index, dtype=float)))
    humidity = _coerce_numeric(out.get("Hum[%]", pd.Series(index=out.index, dtype=float)))
    pressure = _coerce_numeric(out.get("Press[mbar]", pd.Series(index=out.index, dtype=float)))

    temp_low = float(cfg.get("temp_min_c", -40))
    temp_high = float(cfg.get("temp_max_c", 60))
    humidity_low = float(cfg.get("humidity_min_pct", 0))
    humidity_high = float(cfg.get("humidity_max_pct", 100))
    pressure_low = float(cfg.get("pressure_min_mbar", 850))
    pressure_high = float(cfg.get("pressure_max_mbar", 1100))

    out["qc_temp_impossible"] = (temp < temp_low) | (temp > temp_high)
    out["qc_temp_suspect"] = False
    out["qc_temp_spike"] = False
    out["qc_humidity_impossible"] = (humidity < humidity_low) | (humidity > humidity_high)
    out["qc_humidity_suspect"] = False
    out["qc_pressure_impossible"] = (pressure < pressure_low) | (pressure > pressure_high)
    out["qc_pressure_suspect"] = False

    rolling = temp.rolling(5, center=True, min_periods=3).median()
    mad = temp.rolling(5, center=True, min_periods=3).apply(lambda x: np.median(np.abs(x - np.median(x))))
    spike = (temp - rolling).abs() > (3 * mad + 0.2)
    out["qc_temp_spike"] = spike.fillna(False)

    return out
