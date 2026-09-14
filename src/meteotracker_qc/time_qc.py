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


def estimate_expected_sampling_interval_s(
    dt_s: pd.Series,
    *,
    min_samples_for_estimate: int = 20,
    fallback_dt_s: float = 1.0,
    outlier_multiplier: float = 8.0,
) -> float:
    """Estimate a campaign's native sampling interval from its own dt_s values.

    Uses only positive, finite dt_s values, discards a first-pass median's own
    gaps (anything beyond `outlier_multiplier` times that median) before taking
    a second, gap-free median. Falls back to `fallback_dt_s` when too few clean
    samples are available (small synthetic fixtures included) so callers never
    have to special-case a missing estimate.
    """
    positive = dt_s[(dt_s > 0) & np.isfinite(dt_s)]
    if len(positive) < min_samples_for_estimate:
        return float(fallback_dt_s)
    first_pass_median = float(positive.median())
    if not np.isfinite(first_pass_median) or first_pass_median <= 0:
        return float(fallback_dt_s)
    clean = positive[positive <= outlier_multiplier * first_pass_median]
    if clean.empty:
        return first_pass_median
    return float(clean.median())


def detect_time_issues(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
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

    time_cfg = (config or {}).get("time", {})
    min_samples = int(time_cfg.get("min_samples_for_cadence_estimate", 20))
    fallback_dt_s = float(time_cfg.get("fallback_expected_dt_s", 1.0))
    outlier_multiplier = float(time_cfg.get("outlier_multiplier", 8.0))
    gap_short_multiplier = float(time_cfg.get("gap_short_multiplier", 2.0))
    gap_long_multiplier = float(time_cfg.get("gap_long_multiplier", 5.0))
    gap_absolute_floor_s = float(time_cfg.get("gap_absolute_floor_s", 1.0))

    expected_dt_s = estimate_expected_sampling_interval_s(
        out["dt_s"],
        min_samples_for_estimate=min_samples,
        fallback_dt_s=fallback_dt_s,
        outlier_multiplier=outlier_multiplier,
    )
    out["sampling_interval_expected_seconds"] = expected_dt_s
    out["sampling_interval_ratio"] = out["dt_s"] / expected_dt_s

    short_threshold = max(gap_short_multiplier * expected_dt_s, gap_absolute_floor_s)
    long_threshold = max(gap_long_multiplier * expected_dt_s, gap_absolute_floor_s, short_threshold)

    out["timestamp_order_valid"] = ~out["qc_time_order"]
    out["qc_nonmonotonic_timestamp"] = out["qc_time_order"]
    out["qc_duplicate_timestamp"] = out["qc_time_duplicate"]

    is_gap = out["dt_s"] > short_threshold
    out["qc_sampling_gap_short"] = is_gap & (out["dt_s"] <= long_threshold)
    out["qc_sampling_gap_long"] = out["dt_s"] > long_threshold
    # Legacy-compatibility aliases: qc_time_gap used to be the sole gap signal
    # (dt_s > 2.0, hardcoded) and qc_new_segment the sole segment-break signal.
    out["qc_time_gap"] = is_gap
    out["qc_segment_break"] = out["qc_sampling_gap_long"] | out["qc_time_nonpositive_dt"]
    out["qc_new_segment"] = out["qc_segment_break"]
    out["segment_id"] = out["qc_segment_break"].cumsum()

    break_reason = np.where(out["qc_time_nonpositive_dt"], "nonpositive_dt", "long_gap")
    start_reason_at_row = pd.Series(
        np.where(out["qc_segment_break"], break_reason, "campaign_start"), index=out.index
    )
    first_reason_per_segment = start_reason_at_row.groupby(out["segment_id"]).first()
    out["segment_start_reason"] = out["segment_id"].map(first_reason_per_segment)

    end_reason_per_segment = first_reason_per_segment.shift(-1)
    if len(end_reason_per_segment) > 0:
        end_reason_per_segment.iloc[-1] = "campaign_end"
    out["segment_end_reason"] = out["segment_id"].map(end_reason_per_segment)

    return out
