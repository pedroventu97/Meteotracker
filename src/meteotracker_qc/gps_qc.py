from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Geod


GEOD = Geod(ellps="WGS84")


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def detect_gps_issues(df: pd.DataFrame, speed_mode: str = "auto", config: dict | None = None) -> pd.DataFrame:
    out = df.copy()
    cfg = config or {}
    gps_cfg = cfg.get("gps", {})
    jump_distance_m = float(gps_cfg.get("gps_jump_distance_m", 80.0))
    jump_dt_s = float(gps_cfg.get("gps_jump_dt_s", 2.0))
    acceleration_abs = float(gps_cfg.get("acceleration_ms2_abs", 5.0))

    if "time_utc" not in out.columns:
        out["time_utc"] = pd.to_datetime(out.get("Time"), errors="coerce", utc=True)
    if "dt_s" not in out.columns:
        out["dt_s"] = pd.Series(np.nan, index=out.index, dtype=float)
    valid_time = out["time_utc"].notna()
    if valid_time.any():
        out.loc[valid_time, "dt_s"] = out.loc[valid_time, "time_utc"].diff().dt.total_seconds()
    if "segment_id" not in out.columns:
        out["segment_id"] = 0
    lat = _to_numeric(out.get("Lat", pd.Series(index=out.index, dtype=float)))
    lon = _to_numeric(out.get("Lon", pd.Series(index=out.index, dtype=float)))
    dt_s = pd.to_numeric(out.get("dt_s", pd.Series(index=out.index, dtype=float)), errors="coerce")
    reg_speed = pd.to_numeric(out.get("Speed[km/h]", pd.Series(index=out.index, dtype=float)), errors="coerce")

    out["distance_step_m"] = np.nan
    out["speed_gps_kmh"] = np.nan
    out["acceleration_gps_ms2"] = np.nan
    out["qc_coord_missing"] = lat.isna() | lon.isna()
    out["qc_coord_repeated"] = False
    out["qc_coord_outside_aoi"] = False
    out["qc_gps_jump"] = False
    out["qc_possible_gps_freeze"] = False
    out["qc_gps_freeze"] = False
    out["qc_speed_disagreement"] = False
    out["qc_impossible_acceleration"] = False
    out["qc_stationary"] = False

    valid = (~lat.isna()) & (~lon.isna()) & out["time_utc"].notna()
    if valid.sum() < 2:
        return out

    for i in range(1, len(out)):
        if not valid.iloc[i] or not valid.iloc[i - 1]:
            continue
        step_dt = out["dt_s"].iloc[i]
        if pd.isna(step_dt) or step_dt <= 0:
            continue
        if step_dt > 2.0:
            continue
        if out["segment_id"].iloc[i] != out["segment_id"].iloc[i - 1]:
            continue

        _, _, distance = GEOD.inv(float(lon.iloc[i - 1]), float(lat.iloc[i - 1]), float(lon.iloc[i]), float(lat.iloc[i]))
        out.at[i, "distance_step_m"] = distance
        out.at[i, "speed_gps_kmh"] = distance / step_dt * 3.6

        if i > 1 and pd.notna(out["speed_gps_kmh"].iloc[i]) and pd.notna(out["speed_gps_kmh"].iloc[i - 1]):
            pt = float(out["speed_gps_kmh"].iloc[i])
            pt_prev = float(out["speed_gps_kmh"].iloc[i - 1])
            out.at[i, "acceleration_gps_ms2"] = (pt - pt_prev) / max(step_dt, 1.0)

    coord_equal = (lat == lat.shift(1)) & (lon == lon.shift(1))
    coord_equal = coord_equal.fillna(False)
    out["qc_coord_repeated"] = coord_equal

    speed_low = out["speed_gps_kmh"].fillna(0) <= 0.5
    speed_low = speed_low.fillna(False)
    reported_speed_low = reg_speed.fillna(0) <= 0.5
    repeated_block = coord_equal & (coord_equal.shift(1, fill_value=False) | coord_equal.shift(-1, fill_value=False))

    out["qc_stationary"] = coord_equal & speed_low & reported_speed_low
    out["qc_possible_gps_freeze"] = repeated_block & (~reported_speed_low)
    out["qc_gps_freeze"] = repeated_block & speed_low & reported_speed_low

    out["qc_gps_jump"] = (out["distance_step_m"] > jump_distance_m) & (dt_s <= jump_dt_s)
    out["qc_speed_disagreement"] = out["speed_gps_kmh"] > float(gps_cfg.get("max_speed_kmh_absolute", 150.0))
    out["qc_impossible_acceleration"] = out["acceleration_gps_ms2"].abs() > acceleration_abs
    return out
