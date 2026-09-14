"""Section C: point-level candidate masks for the temporal-drift diagnosis.

`qc_segment_break` is deliberately NOT part of any point-level mask here: a
row flagged qc_segment_break is a valid measurement, only marking where a new
segment starts after a discontinuity. The spec's "assenza di qc_segment_break
sul collegamento interessato" is a LINK-level requirement (never build a pair
whose connecting edge silently crosses an unacknowledged break) -- irrelevant
here since crossing a real gap between two separate visits is an explicitly
*valid* revisit (spec principle B.3), not an exclusion. It resurfaces as the
descriptive `crosses_segment_break` field in pairs.py.
"""
from __future__ import annotations

import pandas as pd

from .config import OPTIONAL_QC_FLAGS

BASE_REQUIRED_COLUMNS = ["time_utc", "canonical_latitude", "canonical_longitude", "canonical_temperature_c"]

RECOMMENDED_HARD_EXCLUSION_FLAGS = [
    "qc_temp_isolated_spike", "qc_temp_impossible", "qc_gps_jump", "qc_spatial_jump",
    "qc_isolated_position_outlier", "qc_gps_freeze", "qc_sensor_stabilization",
]

CONSERVATIVE_EXTRA_EXCLUSION_FLAGS = list(OPTIONAL_QC_FLAGS)

# Family priority for deterministic primary-reason selection when several
# conditions fail at once (mirrors the family-priority tie-break pattern
# already used in session_qc for qc_primary_reason / session_primary_reason).
_REASON_PRIORITY = {
    "MISSING_TIMESTAMP": 0, "MISSING_COORDINATES": 1, "MISSING_TEMPERATURE": 2,
    "NOT_KEPT_BY_POINT_QC": 3,
    "qc_temp_impossible": 10, "qc_gps_freeze": 11, "qc_spatial_jump": 12,
    "qc_gps_jump": 13, "qc_isolated_position_outlier": 14, "qc_temp_isolated_spike": 15,
    "qc_sensor_stabilization": 16,
    "qc_post_stop_recovery": 20, "qc_low_ventilation_possible": 21,
    "qc_temp_rate_anomaly": 22, "qc_possible_gps_freeze": 23,
}


def _base_valid(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    reasons = pd.Series([[] for _ in range(len(df))], index=df.index)
    valid = pd.Series(True, index=df.index)
    checks = [
        ("time_utc", "MISSING_TIMESTAMP"), ("canonical_latitude", "MISSING_COORDINATES"),
        ("canonical_longitude", "MISSING_COORDINATES"), ("canonical_temperature_c", "MISSING_TEMPERATURE"),
    ]
    for col, reason in checks:
        bad = df[col].isna()
        valid &= ~bad
        for i in df.index[bad]:
            if reason not in reasons.at[i]:
                reasons.at[i].append(reason)
    return valid, reasons


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].fillna(False).astype(bool)


def _apply_flag_exclusions(df: pd.DataFrame, valid: pd.Series, reasons: pd.Series, flags: list[str]) -> tuple[pd.Series, pd.Series]:
    for flag in flags:
        bad = _bool_col(df, flag)
        valid = valid & ~bad
        for i in df.index[bad]:
            if flag not in reasons.at[i]:
                reasons.at[i].append(flag)
    return valid, reasons


def build_temporal_candidate_masks(df: pd.DataFrame) -> pd.DataFrame:
    """Adds temporal_candidate_{permissive,recommended,conservative},
    temporal_candidate_exclusion_reasons, temporal_candidate_primary_reason.
    """
    out = df.copy()
    base_valid, reasons = _base_valid(df)

    keep_permissive = _bool_col(df, "keep_permissive")
    keep_recommended = _bool_col(df, "keep_recommended")
    keep_restrictive = _bool_col(df, "keep_restrictive")

    permissive_valid = base_valid & keep_permissive
    permissive_reasons = reasons.copy()
    not_kept_permissive = base_valid & ~keep_permissive
    for i in df.index[not_kept_permissive]:
        permissive_reasons.at[i].append("NOT_KEPT_BY_POINT_QC")
    permissive_valid, permissive_reasons = _apply_flag_exclusions(
        df, permissive_valid, permissive_reasons, ["qc_gps_freeze", "qc_spatial_jump", "qc_temp_impossible"]
    )

    recommended_valid = base_valid & keep_recommended
    recommended_reasons = reasons.copy()
    not_kept_recommended = base_valid & ~keep_recommended
    for i in df.index[not_kept_recommended]:
        recommended_reasons.at[i].append("NOT_KEPT_BY_POINT_QC")
    recommended_valid, recommended_reasons = _apply_flag_exclusions(
        df, recommended_valid, recommended_reasons, RECOMMENDED_HARD_EXCLUSION_FLAGS
    )

    conservative_valid = base_valid & keep_restrictive
    conservative_reasons = reasons.copy()
    not_kept_conservative = base_valid & ~keep_restrictive
    for i in df.index[not_kept_conservative]:
        conservative_reasons.at[i].append("NOT_KEPT_BY_POINT_QC")
    conservative_valid, conservative_reasons = _apply_flag_exclusions(
        df, conservative_valid, conservative_reasons,
        RECOMMENDED_HARD_EXCLUSION_FLAGS + CONSERVATIVE_EXTRA_EXCLUSION_FLAGS,
    )

    out["temporal_candidate_permissive"] = permissive_valid
    out["temporal_candidate_recommended"] = recommended_valid
    out["temporal_candidate_conservative"] = conservative_valid
    # exclusion_reasons/primary_reason reported against the recommended
    # profile (the main candidate per spec section C), joined for CSV output.
    out["temporal_candidate_exclusion_reasons"] = recommended_reasons.apply(lambda r: ";".join(r))
    out["temporal_candidate_primary_reason"] = recommended_reasons.apply(_primary_reason)
    return out


def _primary_reason(reason_list: list[str]) -> str | None:
    if not reason_list:
        return None
    return sorted(reason_list, key=lambda r: (_REASON_PRIORITY.get(r, 99), r))[0]
