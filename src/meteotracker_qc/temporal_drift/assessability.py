"""Section F: session-level assessability metrics + temporal_internal_
assessability_status. Never defined from raw pair count alone -- combines
number of distinct spatial groups, temporal distribution (distinct time
windows), spatial coverage, dependency structure (pairs pooled per group,
not counted as independent), point quality, concentration, and overall
session duration.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import MatchingProfile
from .pairs import valid_pairs
from .robust_stats import mad as _mad_impl
from .robust_stats import weighted_median as _weighted_median_impl
from .rules import evaluate_scope

N_TIME_WINDOWS = 4


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _bbox_diagonal_m(lats: pd.Series, lons: pd.Series) -> float:
    lats, lons = lats.dropna(), lons.dropna()
    if len(lats) < 2:
        return 0.0
    return _haversine_m(lats.min(), lons.min(), lats.max(), lons.max())


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    return _weighted_median_impl(values, weights)


def _mad(values: np.ndarray) -> float:
    return _mad_impl(values)


def compute_session_assessability_metrics(
    df: pd.DataFrame, candidate_col: str, groups: pd.DataFrame, visits: pd.DataFrame,
    pairs: pd.DataFrame, session_start: pd.Timestamp, session_end: pd.Timestamp,
) -> dict:
    n_raw = len(df)
    candidate_mask = df[candidate_col].astype(bool)
    n_candidates = int(candidate_mask.sum())
    candidate_fraction = (n_candidates / n_raw) if n_raw else float("nan")

    vpairs = valid_pairs(pairs)
    n_groups = len(groups)
    n_groups_valid = int(groups["group_valid"].sum()) if n_groups else 0
    n_visits = len(visits)
    n_pairs = len(pairs)
    n_pairs_valid = len(vpairs)

    all_lats, all_lons = df.loc[candidate_mask, "canonical_latitude"], df.loc[candidate_mask, "canonical_longitude"]
    span_all = _bbox_diagonal_m(all_lats, all_lons)
    valid_group_ids = set(groups.loc[groups["group_valid"], "repeated_location_group_id"]) if n_groups else set()
    valid_group_rows = groups[groups["repeated_location_group_id"].isin(valid_group_ids)]
    span_groups = _bbox_diagonal_m(valid_group_rows["repeated_location_group_centroid_lat"], valid_group_rows["repeated_location_group_centroid_lon"])
    spatial_coverage = (span_groups / span_all) if span_all > 0 else float("nan")
    spatial_coverage = min(1.0, spatial_coverage) if not math.isnan(spatial_coverage) else spatial_coverage

    nominal_span_s = (session_end - session_start).total_seconds() if pd.notna(session_start) and pd.notna(session_end) else float("nan")

    if n_pairs_valid:
        visit_ids_in_valid_pairs = set(vpairs["visit_id_earlier"]) | set(vpairs["visit_id_later"])
        involved_visits = visits[visits["repeated_location_visit_id"].isin(visit_ids_in_valid_pairs)]
        time_span_s = (involved_visits["visit_end_timestamp"].max() - involved_visits["visit_start_timestamp"].min()).total_seconds()
        earliest_s = (involved_visits["visit_start_timestamp"].min() - session_start).total_seconds() if pd.notna(session_start) else float("nan")
        latest_s = (involved_visits["visit_end_timestamp"].max() - session_start).total_seconds() if pd.notna(session_start) else float("nan")

        if nominal_span_s and nominal_span_s > 0 and not math.isnan(nominal_span_s):
            bin_edges = np.linspace(0.0, nominal_span_s, N_TIME_WINDOWS + 1)
            offsets = (involved_visits["visit_representative_timestamp"] - session_start).dt.total_seconds().to_numpy()
            bins = np.clip(np.digitize(offsets, bin_edges[1:-1]), 0, N_TIME_WINDOWS - 1)
            n_windows = int(len(set(bins.tolist())))
        else:
            n_windows = 1 if len(involved_visits) else 0

        n_groups_same = int(vpairs.loc[vpairs["direction_relation"] == "same_direction", "repeated_location_group_id"].nunique())
        n_groups_opposite = int(vpairs.loc[vpairs["direction_relation"] == "opposite_direction", "repeated_location_group_id"].nunique())

        sep = vpairs["spatial_separation_m"].to_numpy(dtype=float)
        tdiff = vpairs["time_difference_s"].to_numpy(dtype=float)
        tempdiff = vpairs["temperature_difference_c"].to_numpy(dtype=float)
        slope = vpairs["pairwise_slope_c_per_min"].to_numpy(dtype=float)
        weights = vpairs["pair_weight"].to_numpy(dtype=float)

        median_sep = float(np.median(sep))
        median_tdiff = float(np.median(tdiff))
        median_tempdiff = float(np.median(tempdiff))
        median_slope = _weighted_median(slope, weights)
        slope_mad = _mad(slope)
    else:
        time_span_s = 0.0
        earliest_s = float("nan")
        latest_s = float("nan")
        n_windows = 0
        n_groups_same = 0
        n_groups_opposite = 0
        median_sep = median_tdiff = median_tempdiff = median_slope = slope_mad = float("nan")

    fraction_low_quality_visits = float((visits["visit_qc_status"] != "OK").mean()) if n_visits else float("nan")

    return {
        "n_temporal_candidate_points": n_candidates, "temporal_candidate_fraction": candidate_fraction,
        "n_repeated_location_groups": n_groups, "n_repeated_location_groups_valid": n_groups_valid,
        "n_repeated_location_visits": n_visits, "n_repeated_location_pairs": n_pairs,
        "n_repeated_location_pairs_valid": n_pairs_valid, "repeated_location_spatial_coverage": spatial_coverage,
        "repeated_location_time_span_s": time_span_s, "earliest_valid_revisit_s": earliest_s,
        "latest_valid_revisit_s": latest_s, "number_of_distinct_time_windows": n_windows,
        "number_of_groups_with_same_direction_pairs": n_groups_same,
        "number_of_groups_with_opposite_direction_pairs": n_groups_opposite,
        "median_pair_spatial_separation_m": median_sep, "median_pair_time_difference_s": median_tdiff,
        "median_pair_temperature_difference_c": median_tempdiff, "median_pairwise_slope_c_per_min": median_slope,
        "pairwise_slope_mad": slope_mad, "nominal_time_span_s": nominal_span_s,
        "fraction_low_quality_visits": fraction_low_quality_visits,
    }


def add_derived_assessability_columns(session_metrics: pd.DataFrame) -> pd.DataFrame:
    """Materializes composite (AND-of-conditions) booleans as 0/1 columns so
    the single-metric rules engine (rules.py) can reference them directly --
    same pattern already used by session_qc's add_derived_segment_columns /
    add_derived_session_columns for the equivalent reason.
    """
    out = session_metrics.copy()
    pairs_total = out["n_repeated_location_pairs"].fillna(0)
    pairs_valid = out["n_repeated_location_pairs_valid"].fillna(0)
    groups_total = out["n_repeated_location_groups"].fillna(0)
    groups_valid = out["n_repeated_location_groups_valid"].fillna(0)

    out["has_pairs_but_none_valid"] = ((pairs_total > 0) & (pairs_valid == 0)).astype(int)
    out["single_valid_group_single_pair"] = ((groups_valid == 1) & (pairs_valid == 1)).astype(int)
    out["single_valid_group_multi_pair"] = ((groups_valid == 1) & (pairs_valid > 1)).astype(int)
    out["groups_mostly_invalid"] = ((groups_valid >= 1) & (groups_total > 3 * groups_valid)).astype(int)
    return out


def add_start_end_consistency(metrics: dict, start_end_locations_comparable, start_temperature_c,
                               end_temperature_c, raw_start_end_time_difference_s) -> dict:
    """start_end_pair_available / start_end_pair_consistent_with_revisits:
    connects Phase 3's preliminary start/end comparison (never sufficient
    proof alone, per spec principle B.2) to the revisit-based median slope
    computed here, purely as a consistency cross-check -- never a
    replacement for the revisit-based estimate.
    """
    available = bool(start_end_locations_comparable) and pd.notna(start_temperature_c) and pd.notna(end_temperature_c)
    metrics["start_end_pair_available"] = available
    if not available or math.isnan(metrics.get("median_pairwise_slope_c_per_min", float("nan"))) or not raw_start_end_time_difference_s:
        metrics["start_end_pair_consistent_with_revisits"] = None
        return metrics
    raw_diff = float(end_temperature_c) - float(start_temperature_c)
    predicted_diff = metrics["median_pairwise_slope_c_per_min"] * (raw_start_end_time_difference_s / 60.0)
    same_sign = (raw_diff == 0 and abs(predicted_diff) < 0.05) or (np.sign(raw_diff) == np.sign(predicted_diff))
    magnitude_ok = abs(raw_diff) < 1e-9 or 0.33 <= abs(predicted_diff / raw_diff) <= 3.0 if raw_diff != 0 else True
    metrics["start_end_pair_consistent_with_revisits"] = bool(same_sign and magnitude_ok)
    return metrics


def classify_assessability(session_metrics: pd.DataFrame, policy_df: pd.DataFrame) -> pd.DataFrame:
    return evaluate_scope(session_metrics, policy_df, scope="temporal_internal_assessability")
