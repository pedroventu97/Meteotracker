from __future__ import annotations

import numpy as np
import pandas as pd


def _parse_timestamp_series(series: pd.Series, *, utc: bool) -> pd.Series:
    values = pd.Series(series, copy=False).astype(object)
    parsed = pd.to_datetime(values, errors="coerce", utc=utc, format="mixed")
    return pd.Series(parsed, index=series.index)


def normalize_timestamp_series(series: pd.Series) -> pd.Series:
    """Parse timestamps from common file formats and return UTC-normalized timestamps."""
    parsed = _parse_timestamp_series(series, utc=True)
    return parsed.dt.tz_convert(None)


def classify_timezone(file_name: str, time_series: pd.Series) -> tuple[str, float]:
    """Classify timestamp handling at the campaign level without silently assuming naive values are local."""
    parsed = _parse_timestamp_series(time_series, utc=True)
    explicit_tz = time_series.astype(str).str.contains(r"[+-]\d{2}:\d{2}$", regex=True)
    if explicit_tz.any():
        return "explicit_offset", 1.0
    if parsed.notna().any():
        return "ambiguous", 0.4
    return "invalid", 0.0


def detect_time_issues(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["source_row"] = np.arange(len(out), dtype=int)
    out["time_raw"] = out.get("Time")
    out["time_original"] = out.get("Time")

    explicit_tz = out["time_raw"].astype(str).str.contains(r"[+-]\d{2}:\d{2}$", regex=True)
    out["time_timezone_interpretation"] = np.where(explicit_tz, "explicit_offset", "naive_or_unknown")
    out["timezone_confidence"] = np.where(explicit_tz, 1.0, 0.0)

    parsed_all = _parse_timestamp_series(out.get("Time"), utc=True)

    out["time_parsed_naive"] = parsed_all.dt.tz_convert(None)
    out["time_utc"] = parsed_all
    out["time_local"] = out["time_utc"].dt.tz_convert("Europe/Rome")

    out["qc_time_parse"] = out["time_utc"].isna()
    out["elapsed_s"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["dt_s"] = pd.Series(np.nan, index=out.index, dtype=float)

    valid = out["time_utc"].notna()
    if valid.any():
        first_valid = out.loc[valid, "time_utc"].iloc[0]
        out.loc[valid, "elapsed_s"] = (out.loc[valid, "time_utc"] - first_valid).dt.total_seconds()
        dt_raw = out.loc[valid, "time_utc"].diff().dt.total_seconds()
        out.loc[valid, "dt_s"] = dt_raw

    out["qc_time_order"] = out["time_utc"].diff().lt(pd.Timedelta(0))
    out["qc_time_duplicate"] = out["time_utc"].duplicated(keep=False)
    out["qc_time_nonpositive_dt"] = out["dt_s"] <= 0
    out["qc_time_gap"] = out["dt_s"] > 2.0
    out["qc_new_segment"] = out["qc_time_gap"] | out["qc_time_nonpositive_dt"]
    out["segment_id"] = out["qc_new_segment"].cumsum()
    return out
