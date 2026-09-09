"""comparison_potential_score / class per repeated_segment (section 13).

Transparent weighted sum of normalized sub-scores, each in [0,1], weights and
normalization caps all in RepeatedRoutesConfig.score_* fields. Weather
diversity is intentionally excluded from this phase (per spec, section 13).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RepeatedRoutesConfig

QUALITY_NUMERIC = {"high": 1.0, "medium": 0.6, "low": 0.3}

TIME_BIN_NAMES = ["night", "early_morning", "morning", "midday", "afternoon", "late_afternoon", "evening"]


def _classify_score(score: float, cfg: RepeatedRoutesConfig) -> str:
    if score >= cfg.score_class_excellent:
        return "excellent"
    if score >= cfg.score_class_good:
        return "good"
    if score >= cfg.score_class_limited:
        return "limited"
    return "poor"


def build_comparison_opportunities(segments_df: pd.DataFrame, passages_df: pd.DataFrame, cfg: RepeatedRoutesConfig) -> pd.DataFrame:
    if segments_df.empty:
        cols = [
            "repeated_segment_id", "segment_length_m", "n_passages", "n_distinct_dates", "n_distinct_time_bins",
            *[f"n_{b}" for b in TIME_BIN_NAMES], "n_same_direction", "n_opposite_direction",
            "date_range_days", "mean_passage_quality", "comparison_potential_score", "comparison_potential_class",
        ]
        return pd.DataFrame(columns=cols)

    w = cfg.score_weights
    rows = []
    for _, seg in segments_df.iterrows():
        seg_id = seg["repeated_segment_id"]
        passages = passages_df[passages_df["repeated_segment_id"] == seg_id]
        dates = passages["date"].dropna().unique()
        time_bin_counts = passages["time_bin"].value_counts()
        n_time_bins = int(passages["time_bin"].dropna().nunique())

        if len(dates) > 0:
            date_ts = pd.to_datetime(dates)
            date_range_days = int((date_ts.max() - date_ts.min()).days)
        else:
            date_range_days = 0

        quality_numeric = passages["passage_quality_flag"].map(QUALITY_NUMERIC).fillna(0.3)
        mean_passage_quality = float(quality_numeric.mean()) if len(quality_numeric) else 0.0
        mean_valid_fraction = float(passages["valid_fraction"].dropna().mean()) if passages["valid_fraction"].notna().any() else 0.0

        date_diversity = min(len(dates) / cfg.score_norm_n_dates, 1.0)
        passage_count = min(int(seg["n_passages"]) / cfg.score_norm_n_passages, 1.0)
        time_bin_diversity = min(n_time_bins / cfg.score_norm_n_time_bins, 1.0)
        segment_length = min(float(seg["segment_length_m"]) / cfg.score_norm_segment_length_m, 1.0)
        geometric_quality = max(0.0, 1.0 - (float(seg["mean_matching_distance_m"]) / cfg.matching_tolerance_m)) if np.isfinite(seg["mean_matching_distance_m"]) else 0.0
        qc_quality = 0.5 * mean_passage_quality / max(QUALITY_NUMERIC.values()) + 0.5 * mean_valid_fraction
        both_directions = int(seg["n_same_direction"]) > 0 and int(seg["n_opposite_direction"]) > 0
        direction_diversity = 1.0 if both_directions else (0.5 if (seg["n_same_direction"] + seg["n_opposite_direction"]) > 0 else 0.0)

        score_0_1 = (
            w["date_diversity"] * date_diversity
            + w["passage_count"] * passage_count
            + w["time_bin_diversity"] * time_bin_diversity
            + w["segment_length"] * segment_length
            + w["geometric_quality"] * geometric_quality
            + w["qc_quality"] * qc_quality
            + w["direction_diversity"] * direction_diversity
        )
        score_100 = round(score_0_1 * 100, 2)

        row = {
            "repeated_segment_id": seg_id,
            "segment_length_m": seg["segment_length_m"],
            "n_passages": seg["n_passages"],
            "n_distinct_dates": len(dates),
            "n_distinct_time_bins": n_time_bins,
            "n_same_direction": seg["n_same_direction"],
            "n_opposite_direction": seg["n_opposite_direction"],
            "date_range_days": date_range_days,
            "mean_passage_quality": mean_passage_quality,
            "comparison_potential_score": score_100,
            "comparison_potential_class": _classify_score(score_100, cfg),
        }
        for b in TIME_BIN_NAMES:
            row[f"n_{b}"] = int(time_bin_counts.get(b, 0))
        rows.append(row)

    df = pd.DataFrame(rows)
    ordered = [
        "repeated_segment_id", "segment_length_m", "n_passages", "n_distinct_dates", "n_distinct_time_bins",
        *[f"n_{b}" for b in TIME_BIN_NAMES], "n_same_direction", "n_opposite_direction",
        "date_range_days", "mean_passage_quality", "comparison_potential_score", "comparison_potential_class",
    ]
    return df[ordered]
