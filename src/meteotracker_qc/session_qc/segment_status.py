"""6 segment-level quality dimensions + segment_qc_status rollup, evaluated
via the generic rules_engine against config/session_qc_policy.csv (level="segment").
"""
from __future__ import annotations

import pandas as pd

from .rules_engine import evaluate_dimension, evaluate_dimensions

SEGMENT_DIMENSIONS = [
    "sampling_integrity",
    "gps_quality",
    "thermal_quality",
    "ventilation_risk",
    "stabilization",
    "spatial_continuity",
]


def add_derived_segment_columns(segment_metrics: pd.DataFrame) -> pd.DataFrame:
    """Ratio columns used only for classification, kept out of metrics.py to
    keep that module limited to raw sums (see reports/session_qc_report.md
    section B)."""
    out = segment_metrics.copy()
    denom = out["observed_distance_km"].where(out["observed_distance_km"] > 0)
    out["distance_valid_ratio"] = (out["valid_distance_recommended_km"] / denom).fillna(0.0)
    return out


def compute_segment_status(segment_metrics: pd.DataFrame, policy_df: pd.DataFrame, profile: str) -> pd.DataFrame:
    df = add_derived_segment_columns(segment_metrics)
    df = evaluate_dimensions(
        df, policy_df, level="segment", dimensions=SEGMENT_DIMENSIONS, profile=profile, column_prefix="segment_"
    )
    rollup = evaluate_dimension(df, policy_df, level="segment", dimension="rollup", profile=profile)
    df["segment_qc_status"] = rollup["status"]
    df["segment_qc_reason_code"] = rollup["reason_code"]
    df["segment_qc_matched_rule_id"] = rollup["matched_rule_id"]
    return df
