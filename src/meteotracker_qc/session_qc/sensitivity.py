"""Session-level (Section P) sensitivity sweep across the 3 aggregation
configurations (permissive_session / recommended_session /
conservative_session). Re-applies the already-computed segment/session
metrics against each profile's own rows in config/session_qc_policy.csv --
never recomputes point-level QC flags. Deliberately produces no "best
profile" field: choosing recommended_session is a documented, motivated
decision in reports/session_qc_report.md, not an automatic pick.
"""
from __future__ import annotations

import pandas as pd

from .segment_status import compute_segment_status
from .session_status import compute_session_status

AGGREGATION_PROFILES = ["permissive_session", "recommended_session", "conservative_session"]


def run_session_sensitivity(session_metrics: pd.DataFrame, policy_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for profile in AGGREGATION_PROFILES:
        session_qc = compute_session_status(session_metrics, policy_df, profile)
        for _, row in session_qc.iterrows():
            rows.append({
                "canonical_campaign_id": row["canonical_campaign_id"],
                "profile": profile,
                "session_qc_status": row["session_qc_status"],
                "session_primary_reason": row["session_primary_reason"],
                "keep_fraction_recommended": row["keep_fraction_recommended"],
                "gap_fraction_of_nominal_span": row["gap_fraction_of_nominal_span"],
                "n_segments": row["n_segments"],
                "sampling_integrity_status": row["sampling_integrity_status"],
                "gps_quality_status": row["gps_quality_status"],
                "stabilization_quality_status": row["stabilization_quality_status"],
                "spatial_continuity_status": row["spatial_continuity_status"],
            })
    return pd.DataFrame(rows)


def run_segment_sensitivity(segment_metrics: pd.DataFrame, policy_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for profile in AGGREGATION_PROFILES:
        segment_qc = compute_segment_status(segment_metrics, policy_df, profile)
        for _, row in segment_qc.iterrows():
            rows.append({
                "canonical_campaign_id": row["canonical_campaign_id"],
                "segment_id": row["segment_id"],
                "profile": profile,
                "segment_qc_status": row["segment_qc_status"],
            })
    return pd.DataFrame(rows)


def summarize_status_counts(sensitivity_long: pd.DataFrame, status_col: str) -> pd.DataFrame:
    return (
        sensitivity_long.groupby(["profile", status_col]).size().unstack(fill_value=0)
        .reindex(AGGREGATION_PROFILES)
    )


def campaigns_that_change_class(sensitivity_long: pd.DataFrame, status_col: str = "session_qc_status") -> pd.DataFrame:
    wide = sensitivity_long.pivot(index="canonical_campaign_id", columns="profile", values=status_col)
    changed = wide[wide.nunique(axis=1) > 1].reset_index()
    return changed
