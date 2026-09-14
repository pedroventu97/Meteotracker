from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.config import (
    MATCHING_COLUMNS, OPERATIONAL_PROFILES, get_profile, load_matching_policy,
)

ROOT = Path(__file__).resolve().parent.parent


def test_matching_policy_has_expected_columns():
    df = load_matching_policy(ROOT)
    assert list(df.columns) == MATCHING_COLUMNS


def test_all_three_operational_profiles_present():
    df = load_matching_policy(ROOT)
    for name in OPERATIONAL_PROFILES:
        assert (df["profile_name"] == name).sum() == 1


def test_operational_profiles_are_never_sensitivity_selected():
    # Operational profiles may be engineering_default or, once a real-data
    # correction is made (e.g. minimum_points_per_visit for temporal_recommended,
    # corrected after the first full 34-campaign run), data_distribution --
    # they must never be sensitivity_selected (that vocabulary is reserved
    # for sweep-only configurations, see test_sensitivity_only_rows_never_reused_as_operational).
    df = load_matching_policy(ROOT)
    operational = df[df["profile_name"].isin(OPERATIONAL_PROFILES)]
    assert operational["evidence_source"].isin(["engineering_default", "data_distribution"]).all()


def test_no_profile_attributes_radius_or_separation_to_thesis_or_audit():
    df = load_matching_policy(ROOT)
    assert not df["evidence_source"].isin(["thesis_documented", "audit_observed"]).any()


def test_visit_merge_gap_always_below_smallest_swept_separation():
    df = load_matching_policy(ROOT)
    assert (df["visit_merge_gap_s"] < 60).all()


def test_profiles_are_monotonic_in_severity():
    permissive = get_profile(load_matching_policy(ROOT), "temporal_permissive")
    recommended = get_profile(load_matching_policy(ROOT), "temporal_recommended")
    conservative = get_profile(load_matching_policy(ROOT), "temporal_conservative")
    assert permissive.spatial_radius_m > recommended.spatial_radius_m > conservative.spatial_radius_m
    assert permissive.minimum_temporal_separation_s < recommended.minimum_temporal_separation_s < conservative.minimum_temporal_separation_s
    assert permissive.minimum_groups_for_model < recommended.minimum_groups_for_model < conservative.minimum_groups_for_model


def test_get_profile_unknown_name_raises():
    df = load_matching_policy(ROOT)
    with pytest.raises(ValueError):
        get_profile(df, "not_a_real_profile")


def test_sensitivity_only_rows_never_reused_as_operational():
    df = load_matching_policy(ROOT)
    sensitivity_rows = df[df["evidence_source"] == "sensitivity_selected"]
    assert set(sensitivity_rows["profile_name"]).isdisjoint(set(OPERATIONAL_PROFILES))
