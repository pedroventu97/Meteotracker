"""Section L: verify experimental detrending doesn't erase real urban
spatial gradients. Purely descriptive thresholds (0.1/0.25/0.5 C) -- never
automatic validity criteria, only reporting levels, per the spec.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

OVERDETRENDING_RATIO_THRESHOLD = 0.7
SEVERE_CONTRAST_REDUCTION_THRESHOLD = 0.5
LARGE_ADJUSTMENT_ABS_C = 2.0
HIGH_CORRELATION_THRESHOLD = 0.9


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def compute_conservation_metrics(
    detrending_df: pd.DataFrame, observation_group_ids: pd.Series,
) -> dict:
    """observation_group_ids: repeated_location_group_id indexed like
    detrending_df, NaN/absent for rows not part of any spatial group.
    """
    both_valid = detrending_df["temp_original_c"].notna() & detrending_df["temp_detrended_experimental_c"].notna()
    raw = detrending_df.loc[both_valid, "temp_original_c"].to_numpy(dtype=float)
    detrended = detrending_df.loc[both_valid, "temp_detrended_experimental_c"].to_numpy(dtype=float)

    correlation = _pearson(raw, detrended)
    rank_correlation = float("nan")
    if len(raw) >= 2 and np.std(raw) > 0 and np.std(detrended) > 0:
        rank_correlation = float(spearmanr(raw, detrended).statistic)

    trend = detrending_df["temporal_trend_candidate_c"].dropna().to_numpy(dtype=float)
    abs_trend = np.abs(trend)
    frac_gt = {
        thr: (float(np.mean(abs_trend > thr)) if len(abs_trend) else float("nan"))
        for thr in (0.1, 0.25, 0.5)
    }
    max_adjustment = float(np.max(abs_trend)) if len(abs_trend) else float("nan")

    between_ratio, within_ratio = float("nan"), float("nan")
    grouped = observation_group_ids.loc[both_valid] if len(observation_group_ids) else pd.Series(dtype=object)
    if len(grouped) and grouped.notna().any():
        gdf = pd.DataFrame({
            "group": grouped.to_numpy(), "raw": detrending_df.loc[both_valid, "temp_original_c"].to_numpy(),
            "detrended": detrending_df.loc[both_valid, "temp_detrended_experimental_c"].to_numpy(),
        }).dropna(subset=["group"])
        if gdf["group"].nunique() >= 2:
            raw_group_means = gdf.groupby("group")["raw"].mean()
            det_group_means = gdf.groupby("group")["detrended"].mean()
            between_raw = float(raw_group_means.var(ddof=0))
            between_det = float(det_group_means.var(ddof=0))
            within_raw = float(gdf.groupby("group")["raw"].var(ddof=0).mean())
            within_det = float(gdf.groupby("group")["detrended"].var(ddof=0).mean())
            if between_raw > 0:
                between_ratio = between_det / between_raw
            if within_raw > 0:
                within_ratio = within_det / within_raw

    flags = []
    if pd.notna(between_ratio) and between_ratio < SEVERE_CONTRAST_REDUCTION_THRESHOLD:
        flags.append("SPATIAL_CONTRAST_REDUCED_EXCESSIVELY")
    elif pd.notna(between_ratio) and between_ratio < OVERDETRENDING_RATIO_THRESHOLD:
        flags.append("POSSIBLE_OVERDETRENDING")
    if pd.notna(max_adjustment) and max_adjustment > LARGE_ADJUSTMENT_ABS_C:
        flags.append("LARGE_EXPERIMENTAL_ADJUSTMENT")
    if not flags and pd.notna(correlation) and correlation > HIGH_CORRELATION_THRESHOLD:
        flags.append("SPATIAL_PATTERN_PRESERVED")

    return {
        "correlation_raw_vs_detrended": correlation, "rank_correlation_raw_vs_detrended": rank_correlation,
        "between_location_variance_ratio": between_ratio, "within_location_variance_ratio": within_ratio,
        "fraction_of_points_with_adjustment_gt_0_1c": frac_gt[0.1],
        "fraction_of_points_with_adjustment_gt_0_25c": frac_gt[0.25],
        "fraction_of_points_with_adjustment_gt_0_5c": frac_gt[0.5],
        "max_absolute_adjustment_c": max_adjustment, "conservation_flags": ";".join(flags),
    }
