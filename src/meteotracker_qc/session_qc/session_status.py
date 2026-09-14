"""7 session-level quality dimensions + session_qc_status rollup, plus the
deliberately non-diagnostic `temporal_drift_assessability` (Section I --
this module never classifies drift itself, only whether enough data exists
for a *future* diagnosis to be attempted).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Geod

from .rules_engine import aggregate_session_reasons, evaluate_dimension, evaluate_dimensions

GEOD = Geod(ellps="WGS84")

SESSION_DIMENSIONS = [
    "sampling_integrity",
    "gps_quality",
    "thermal_signal",
    "ventilation_risk",
    "stabilization_quality",
    "spatial_continuity",
    "schema_completeness",
]

DRIFT_MIN_DURATION_S = {"permissive_session": 15.0, "recommended_session": 30.0, "conservative_session": 60.0}
DRIFT_LOCATION_THRESHOLD_M = 300.0


def add_derived_session_columns(session_metrics: pd.DataFrame) -> pd.DataFrame:
    out = session_metrics.copy()
    denom = out["observed_distance_km"].where(out["observed_distance_km"] > 0)
    out["longest_segment_distance_ratio"] = (out["longest_valid_segment_distance_km"] / denom).fillna(0.0)
    return out


def compute_session_status(session_metrics: pd.DataFrame, policy_df: pd.DataFrame, profile: str) -> pd.DataFrame:
    df = add_derived_session_columns(session_metrics)
    df = evaluate_dimensions(df, policy_df, level="session", dimensions=SESSION_DIMENSIONS, profile=profile, column_prefix="")
    rollup = evaluate_dimension(df, policy_df, level="session", dimension="rollup", profile=profile)
    df["session_qc_status"] = rollup["status"]
    df["session_qc_matched_rule_id"] = rollup["matched_rule_id"]

    dimension_reason_codes = {dim: df[f"{dim}_reason_code"] for dim in SESSION_DIMENSIONS}
    reasons = aggregate_session_reasons(dimension_reason_codes, rollup["reason_code"])
    for col in reasons.columns:
        df[col] = reasons[col]
    return df


def _first_last_valid(ref: pd.DataFrame) -> tuple[pd.Series | None, pd.Series | None]:
    time_valid = ref["time_utc"].notna()
    coord_valid = ref.get("canonical_latitude", pd.Series(dtype=float)).notna() & ref.get("canonical_longitude", pd.Series(dtype=float)).notna()
    both_valid = time_valid & coord_valid
    if both_valid.sum() < 2:
        return None, None
    valid_rows = ref.loc[both_valid].sort_values("time_utc")
    return valid_rows.iloc[0], valid_rows.iloc[-1]


def compute_drift_assessability(ref: pd.DataFrame, nominal_time_span_s: float, n_segments: int, keep_fraction_recommended: float, profile: str) -> dict:
    """Never a real drift diagnosis (no TEMPORALLY_STABLE / SENSOR_DRIFT /
    BACKGROUND_CHANGE classes exist here) -- only whether enough comparable
    data exists for a *future* diagnosis. See Section I.
    """
    first, last = _first_last_valid(ref)
    start_temp = end_temp = None
    start_time = end_time = None
    locations_comparable = False
    comparison_warning = "insufficient_start_end_data"

    if first is not None:
        start_temp = float(first["canonical_temperature_c"]) if pd.notna(first.get("canonical_temperature_c")) else None
        end_temp = float(last["canonical_temperature_c"]) if pd.notna(last.get("canonical_temperature_c")) else None
        start_time, end_time = first["time_utc"], last["time_utc"]
        _, _, dist_m = GEOD.inv(
            float(first["canonical_longitude"]), float(first["canonical_latitude"]),
            float(last["canonical_longitude"]), float(last["canonical_latitude"]),
        )
        locations_comparable = bool(dist_m <= DRIFT_LOCATION_THRESHOLD_M)
        comparison_warning = (
            "locations_close_enough_to_compare_but_this_is_not_a_drift_diagnosis" if locations_comparable
            else "start_and_end_locations_are_far_apart_do_not_interpret_the_difference_as_drift"
        )

    raw_temp_diff = (end_temp - start_temp) if (start_temp is not None and end_temp is not None) else None
    raw_time_diff_s = (end_time - start_time).total_seconds() if (start_time is not None and end_time is not None) else None

    min_duration = DRIFT_MIN_DURATION_S.get(profile, 30.0)
    if nominal_time_span_s < min_duration or first is None:
        assessability = "NOT_ASSESSABLE"
    elif locations_comparable and n_segments <= 2 and keep_fraction_recommended >= 0.5:
        assessability = "ASSESSABLE"
    elif keep_fraction_recommended >= 0.3:
        assessability = "PARTIALLY_ASSESSABLE"
    else:
        assessability = "NOT_ASSESSABLE"

    return {
        "temporal_drift_assessability": assessability,
        "start_temperature_c": start_temp,
        "end_temperature_c": end_temp,
        "raw_start_end_temperature_difference_c": raw_temp_diff,
        "raw_start_end_time_difference_s": raw_time_diff_s,
        "start_end_locations_comparable": locations_comparable,
        "start_end_comparison_warning": comparison_warning,
    }
