"""Section E: revisit pair construction. All C(n_visits,2) pairs are built
per group (not just consecutive-in-time pairs), earlier/later tagged
chronologically. Excluded pairs are KEPT with reason codes, never dropped
from output -- only excluded from the trend estimation input.

`crosses_segment_break` and a same-segment mismatch are DESCRIPTIVE only:
crossing a gap/segment boundary between two visits is an explicitly valid
revisit per spec principle B.3, never an automatic exclusion.

`pair_weight` = 1/C(n_visits_in_group, 2): every valid pair in a group with
many visits otherwise outweighs a group with few visits by construction
(O(n^2) pairs vs O(n) real information) when later pooled across groups for
the Method-1 weighted median (trend_methods.py) -- this weight equalizes each
group's total contribution regardless of how many pairs it produces.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

from .config import MatchingProfile
from .grouping import bearing_relation

PAIR_COLUMNS = [
    "repeated_location_pair_id", "repeated_location_group_id", "visit_id_earlier", "visit_id_later",
    "timestamp_earlier", "timestamp_later", "time_difference_s", "temperature_earlier_c",
    "temperature_later_c", "temperature_difference_c", "pairwise_slope_c_per_min",
    "spatial_separation_m", "direction_relation", "same_segment", "crosses_segment_break",
    "pair_qc_status", "pair_exclusion_reasons", "pair_weight",
]


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _segment_break_between(full_df: pd.DataFrame, t_start: pd.Timestamp, t_end: pd.Timestamp) -> bool:
    if "qc_segment_break" not in full_df.columns:
        return False
    between = (full_df["time_utc"] > t_start) & (full_df["time_utc"] < t_end)
    return bool(full_df.loc[between, "qc_segment_break"].fillna(False).any())


def build_pairs(visits: pd.DataFrame, full_df: pd.DataFrame, profile: MatchingProfile) -> pd.DataFrame:
    if visits.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    rows = []
    for group_id, group_visits in visits.groupby("repeated_location_group_id"):
        group_visits = group_visits.sort_values("visit_representative_timestamp").reset_index(drop=True)
        n_visits = len(group_visits)
        if n_visits < 2:
            continue
        n_pairs_in_group = n_visits * (n_visits - 1) // 2
        weight = 1.0 / n_pairs_in_group

        for i, j in itertools.combinations(range(n_visits), 2):
            v1, v2 = group_visits.iloc[i], group_visits.iloc[j]
            earlier, later = (v1, v2) if v1["visit_representative_timestamp"] <= v2["visit_representative_timestamp"] else (v2, v1)

            time_diff_s = (later["visit_representative_timestamp"] - earlier["visit_representative_timestamp"]).total_seconds()
            temp_diff = float(later["visit_representative_temperature_c"] - earlier["visit_representative_temperature_c"])
            slope_c_per_min = (temp_diff / (time_diff_s / 60.0)) if time_diff_s > 0 else np.nan
            spatial_sep = _haversine_m(
                earlier["visit_representative_lat"], earlier["visit_representative_lon"],
                later["visit_representative_lat"], later["visit_representative_lon"],
            )
            direction_relation = bearing_relation(earlier["visit_bearing_deg"], later["visit_bearing_deg"])
            seg_earlier = set(str(earlier["visit_segment_ids"]).split(";"))
            seg_later = set(str(later["visit_segment_ids"]).split(";"))
            same_segment = bool(seg_earlier & seg_later)
            crosses_break = _segment_break_between(full_df, earlier["visit_end_timestamp"], later["visit_start_timestamp"])

            reasons = []
            if time_diff_s < profile.minimum_temporal_separation_s:
                reasons.append("EXCLUDED_INSUFFICIENT_TEMPORAL_SEPARATION")
            if earlier["visit_qc_status"] != "OK" or later["visit_qc_status"] != "OK":
                reasons.append("EXCLUDED_LOW_VISIT_QUALITY")
            if spatial_sep > profile.spatial_radius_m:
                reasons.append("EXCLUDED_SPATIAL_SEPARATION_EXCEEDS_RADIUS")
            if pd.isna(earlier["visit_representative_temperature_c"]) or pd.isna(later["visit_representative_temperature_c"]):
                reasons.append("EXCLUDED_INVALID_TEMPERATURE")

            rows.append({
                "repeated_location_pair_id": f"{group_id}_{earlier['repeated_location_visit_id']}_{later['repeated_location_visit_id']}",
                "repeated_location_group_id": group_id,
                "visit_id_earlier": earlier["repeated_location_visit_id"], "visit_id_later": later["repeated_location_visit_id"],
                "timestamp_earlier": earlier["visit_representative_timestamp"], "timestamp_later": later["visit_representative_timestamp"],
                "time_difference_s": time_diff_s, "temperature_earlier_c": float(earlier["visit_representative_temperature_c"]),
                "temperature_later_c": float(later["visit_representative_temperature_c"]), "temperature_difference_c": temp_diff,
                "pairwise_slope_c_per_min": slope_c_per_min, "spatial_separation_m": spatial_sep,
                "direction_relation": direction_relation, "same_segment": same_segment, "crosses_segment_break": crosses_break,
                "pair_qc_status": "VALID" if not reasons else "EXCLUDED",
                "pair_exclusion_reasons": ";".join(reasons), "pair_weight": weight,
            })

    return pd.DataFrame(rows, columns=PAIR_COLUMNS)


def valid_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    return pairs.loc[pairs["pair_qc_status"] == "VALID"]
