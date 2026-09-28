from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod

from .time_qc import classify_timezone

GEOD = Geod(ellps="WGS84")
LOCAL_TZ = "Europe/Rome"


def infer_device_id(name: str) -> str:
    parts = name.split("_")
    if len(parts) >= 2:
        return parts[-2] if parts[-2] not in {"private", "mtdicambo"} else parts[-1].split(".")[0]
    return "unknown"


def infer_profile(name: str) -> str:
    if "private" in name:
        return "private"
    if "mtdicambo" in name:
        return "mtdicambo"
    return "unknown"


def infer_nominal_date(name: str) -> str | None:
    m = re.search(r"(\d{8})T(\d{6})", name)
    if m:
        return m.group(1)
    return None


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_csvs(input_dir: str | Path) -> pd.DataFrame:
    rows = []
    for path in sorted(Path(input_dir).rglob("*.csv")):
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        # timestamp parsing: keep the original series for timestamp_start/end,
        # and also emit UTC/local fields derived from explicit offsets when present.
        time_col = df.iloc[:, 0]
        ts = pd.to_datetime(time_col, errors="coerce")
        parsed_utc = pd.to_datetime(time_col, errors="coerce", utc=True, format="mixed")
        timezone_original, _ = classify_timezone(path.name, time_col)
        valid_ts = ts.dropna()
        valid_utc = parsed_utc.dropna()
        if not valid_ts.empty:
            ts_sorted = valid_ts.sort_values()
            dt = ts_sorted.diff().dt.total_seconds().dropna()
            dt_median = float(dt.median()) if len(dt) > 0 else np.nan
            dt_p01 = float(dt.quantile(0.01)) if len(dt) > 0 else np.nan
            dt_p99 = float(dt.quantile(0.99)) if len(dt) > 0 else np.nan
            gap_count = int((dt > 2).sum()) if len(dt) > 0 else 0
            gap_duration = float(dt[dt > 2].sum()) if len(dt) > 0 else 0.0
        else:
            dt_median = dt_p01 = dt_p99 = gap_count = gap_duration = np.nan
        if not valid_utc.empty:
            time_utc_start = valid_utc.min()
            time_utc_end = valid_utc.max()
            time_local_start = time_utc_start.tz_convert(LOCAL_TZ)
            time_local_end = time_utc_end.tz_convert(LOCAL_TZ)
        else:
            time_utc_start = time_utc_end = time_local_start = time_local_end = pd.NaT

        lat = pd.to_numeric(df.get("Lat", pd.Series(dtype=float)), errors="coerce")
        lon = pd.to_numeric(df.get("Lon", pd.Series(dtype=float)), errors="coerce")
        dist_total = 0.0
        if len(lat) >= 2 and len(lon) >= 2:
            for i in range(1, len(df)):
                if pd.isna(lat.iloc[i]) or pd.isna(lat.iloc[i - 1]) or pd.isna(lon.iloc[i]) or pd.isna(lon.iloc[i - 1]):
                    continue
                _, _, d = GEOD.inv(float(lon.iloc[i - 1]), float(lat.iloc[i - 1]), float(lon.iloc[i]), float(lat.iloc[i]))
                dist_total += d

        temp = pd.to_numeric(df.get("Temp[°C]", pd.Series(dtype=float)), errors="coerce")
        humidity = pd.to_numeric(df.get("Hum[%]", pd.Series(dtype=float)), errors="coerce")
        pressure = pd.to_numeric(df.get("Press[mbar]", pd.Series(dtype=float)), errors="coerce")
        speed = pd.to_numeric(df.get("Speed[km/h]", pd.Series(dtype=float)), errors="coerce")

        rows.append(
            {
                "file_name": path.name,
                "device_id": infer_device_id(path.name),
                "profile_type": infer_profile(path.name),
                "nominal_date": infer_nominal_date(path.name),
                "timestamp_start": valid_ts.min() if not valid_ts.empty else pd.NaT,
                "timestamp_end": valid_ts.max() if not valid_ts.empty else pd.NaT,
                "timezone_original": timezone_original,
                "time_utc_start": time_utc_start,
                "time_utc_end": time_utc_end,
                "time_local_start": time_local_start,
                "time_local_end": time_local_end,
                "duration_s": float((valid_ts.max() - valid_ts.min()).total_seconds()) if not valid_ts.empty else np.nan,
                "n_rows": int(len(df)),
                "n_columns": int(df.shape[1]),
                "median_dt_s": dt_median,
                "dt_p01": dt_p01,
                "dt_p99": dt_p99,
                "gap_count": gap_count,
                "gap_duration_s": gap_duration,
                "bbox_lat_min": float(lat.min()) if lat.notna().any() else np.nan,
                "bbox_lat_max": float(lat.max()) if lat.notna().any() else np.nan,
                "bbox_lon_min": float(lon.min()) if lon.notna().any() else np.nan,
                "bbox_lon_max": float(lon.max()) if lon.notna().any() else np.nan,
                "distance_total_m": float(dist_total),
                "temp_min_c": float(temp.min()) if temp.notna().any() else np.nan,
                "temp_mean_c": float(temp.mean()) if temp.notna().any() else np.nan,
                "temp_max_c": float(temp.max()) if temp.notna().any() else np.nan,
                "humidity_min_pct": float(humidity.min()) if humidity.notna().any() else np.nan,
                "humidity_mean_pct": float(humidity.mean()) if humidity.notna().any() else np.nan,
                "humidity_max_pct": float(humidity.max()) if humidity.notna().any() else np.nan,
                "pressure_min_mbar": float(pressure.min()) if pressure.notna().any() else np.nan,
                "pressure_mean_mbar": float(pressure.mean()) if pressure.notna().any() else np.nan,
                "pressure_max_mbar": float(pressure.max()) if pressure.notna().any() else np.nan,
                "speed_min_kmh": float(speed.min()) if speed.notna().any() else np.nan,
                "speed_median_kmh": float(speed.median()) if speed.notna().any() else np.nan,
                "speed_max_kmh": float(speed.max()) if speed.notna().any() else np.nan,
                "missing_fraction": float(df.isna().mean().mean()) if len(df) else np.nan,
                "empty_columns": [c for c in df.columns if df[c].isna().all()],
                "apparent_schema": "42-col" if len(df.columns) == 42 else "other",
                "source_hash": hash_file(path),
            }
        )
    return pd.DataFrame(rows)
