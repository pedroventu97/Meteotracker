"""Bare loader for config/repeated_location_matching.csv -- values only, no
classification logic (that lives in rules.py, loaded later once
assessability.py/diagnosis.py actually need it). Kept separate so grouping.py
and pairs.py can read real threshold values without hardcoding them ahead of
the declarative rules engine existing.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..config_resources import read_policy

MATCHING_COLUMNS = [
    "profile_name", "spatial_radius_m", "maximum_group_diameter_m",
    "minimum_temporal_separation_s", "visit_merge_gap_s", "minimum_points_per_visit",
    "minimum_groups_for_model", "minimum_time_windows", "direction_handling",
    "qc_profile", "evidence_source", "rationale",
]

OPERATIONAL_PROFILES = ["temporal_permissive", "temporal_recommended", "temporal_conservative"]
MAIN_PROFILE = "temporal_recommended"

OPTIONAL_QC_FLAGS = [
    "qc_post_stop_recovery", "qc_low_ventilation_possible",
    "qc_temp_rate_anomaly", "qc_possible_gps_freeze",
]


def load_matching_policy(root: Path | None = None) -> pd.DataFrame:
    df = read_policy("repeated_location_matching.csv", root)
    missing = set(MATCHING_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"repeated_location_matching.csv missing columns: {missing}")
    return df


class MatchingProfile:
    """Read-only view of a single row of repeated_location_matching.csv."""

    def __init__(self, row: pd.Series):
        self.profile_name = str(row["profile_name"])
        self.spatial_radius_m = float(row["spatial_radius_m"])
        self.maximum_group_diameter_m = float(row["maximum_group_diameter_m"])
        self.minimum_temporal_separation_s = float(row["minimum_temporal_separation_s"])
        self.visit_merge_gap_s = float(row["visit_merge_gap_s"])
        self.minimum_points_per_visit = int(row["minimum_points_per_visit"])
        self.minimum_groups_for_model = int(row["minimum_groups_for_model"])
        self.minimum_time_windows = int(row["minimum_time_windows"])
        self.direction_handling = str(row["direction_handling"])
        self.qc_profile = str(row["qc_profile"])
        self.evidence_source = str(row["evidence_source"])


def get_profile(matching_policy: pd.DataFrame, profile_name: str) -> MatchingProfile:
    rows = matching_policy.loc[matching_policy["profile_name"] == profile_name]
    if rows.empty:
        raise ValueError(f"unknown matching profile: {profile_name}")
    return MatchingProfile(rows.iloc[0])
