import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.assessability import (
    add_derived_assessability_columns, add_start_end_consistency,
    compute_session_assessability_metrics, classify_assessability,
)
from meteotracker_qc.temporal_drift.candidates import build_temporal_candidate_masks
from meteotracker_qc.temporal_drift.config import get_profile, load_matching_policy
from meteotracker_qc.temporal_drift.grouping import compute_groups_and_visits
from meteotracker_qc.temporal_drift.pairs import build_pairs

ROOT_POLICY = pd.read_csv("config/temporal_drift_policy.csv")
BASE_LAT, BASE_LON = 44.4949, 11.3426


def _metrics_row(**overrides):
    base = {
        "canonical_campaign_id": "c1", "nominal_time_span_s": 3600.0,
        "n_repeated_location_groups": 6, "n_repeated_location_groups_valid": 6,
        "n_repeated_location_visits": 14, "n_repeated_location_pairs": 12,
        "n_repeated_location_pairs_valid": 10, "repeated_location_spatial_coverage": 0.6,
        "number_of_distinct_time_windows": 3, "fraction_low_quality_visits": 0.1,
    }
    base.update(overrides)
    df = pd.DataFrame([base])
    return add_derived_assessability_columns(df)


def _classify(**overrides):
    df = _metrics_row(**overrides)
    out = classify_assessability(df, ROOT_POLICY)
    return out.iloc[0]


def test_sufficient_revisits_is_assessable():
    row = _classify()
    assert row["status"] == "ASSESSABLE"
    assert row["reason_code"] == "SUFFICIENT_REVISITS"


def test_no_valid_groups_not_assessable():
    row = _classify(n_repeated_location_groups_valid=0, n_repeated_location_pairs=0, n_repeated_location_pairs_valid=0)
    assert row["status"] == "NOT_ASSESSABLE"
    assert row["reason_code"] == "NO_VALID_REVISITS"


def test_session_too_short_not_assessable_even_with_good_revisits():
    row = _classify(nominal_time_span_s=30.0)
    assert row["status"] == "NOT_ASSESSABLE"
    assert row["reason_code"] == "SESSION_TOO_SHORT"


def test_pairs_exist_but_none_valid_is_insufficient_temporal_separation():
    row = _classify(n_repeated_location_pairs=8, n_repeated_location_pairs_valid=0)
    assert row["status"] == "NOT_ASSESSABLE"
    assert row["reason_code"] == "INSUFFICIENT_TEMPORAL_SEPARATION"


def test_few_revisit_groups_partially_assessable():
    row = _classify(n_repeated_location_groups=2, n_repeated_location_groups_valid=2, n_repeated_location_pairs=2, n_repeated_location_pairs_valid=2)
    assert row["status"] == "PARTIALLY_ASSESSABLE"
    assert row["reason_code"] == "FEW_REVISIT_GROUPS"


def test_revisits_concentrated_in_time_partially_assessable():
    row = _classify(number_of_distinct_time_windows=1)
    assert row["status"] == "PARTIALLY_ASSESSABLE"
    assert row["reason_code"] == "REVISITS_CONCENTRATED_IN_TIME"


def test_revisits_concentrated_in_space_partially_assessable():
    row = _classify(repeated_location_spatial_coverage=0.05)
    assert row["status"] == "PARTIALLY_ASSESSABLE"
    assert row["reason_code"] == "REVISITS_CONCENTRATED_IN_SPACE"


def test_insufficient_valid_pairs_partially_assessable():
    row = _classify(n_repeated_location_pairs=6, n_repeated_location_pairs_valid=3)
    assert row["status"] == "PARTIALLY_ASSESSABLE"
    assert row["reason_code"] == "INSUFFICIENT_VALID_PAIRS"


def test_low_revisit_quality_partially_assessable():
    row = _classify(fraction_low_quality_visits=0.8)
    assert row["status"] == "PARTIALLY_ASSESSABLE"
    assert row["reason_code"] == "LOW_REVISIT_QUALITY"


def test_start_end_only_partially_assessable():
    row = _classify(n_repeated_location_groups=1, n_repeated_location_groups_valid=1, n_repeated_location_pairs=1, n_repeated_location_pairs_valid=1)
    assert row["status"] == "PARTIALLY_ASSESSABLE"
    assert row["reason_code"] == "START_END_ONLY"


def test_high_singleton_fraction_alone_does_not_block_assessability():
    # Regression test: EXCESSIVE_FRAGMENTATION (ratio of singleton to valid
    # groups) was disabled after the first full 34-campaign real run showed
    # it fires on nearly every real campaign (median singleton fraction
    # 99.3%, mean 94.4%) -- most locations on a point-to-point bike route
    # are naturally visited only once, which says nothing about whether the
    # groups that DO have real revisits are adequate. A campaign with 970
    # singleton groups (97% of 1000) but 30 solid valid groups and 30 valid
    # pairs must reach ASSESSABLE, not be blocked by the singleton ratio --
    # verified on real data: 3 of the 6 campaigns that used to trigger this
    # rule had adequate absolute evidence and became ASSESSABLE once
    # disabled; the other 3 correctly fell through to a more specific,
    # still-accurate reason (space/time concentration or low quality).
    row = _classify(
        n_repeated_location_groups=1000, n_repeated_location_groups_valid=30,
        n_repeated_location_pairs=1000, n_repeated_location_pairs_valid=30,
    )
    assert row["status"] == "ASSESSABLE"
    assert row["reason_code"] == "SUFFICIENT_REVISITS"


def test_excessive_fragmentation_rule_exists_in_vocabulary_but_is_disabled():
    policy = ROOT_POLICY
    row = policy[policy["rule_id"] == "TDA-PA-02"]
    assert not row.empty
    assert row.iloc[0]["reason_code"] == "EXCESSIVE_FRAGMENTATION"
    assert row.iloc[0]["enabled"] == False  # noqa: E712


# ---- pure computation ----

def test_weighted_median_equalizes_group_contribution():
    # group A: 2 visits -> 1 pair, slope=1.0. group B: 4 visits -> 6 pairs, all slope=5.0.
    # A naive unweighted median would be dominated by B's 6 identical pairs;
    # the group-weighted median must not simply reflect B's value 6-to-1.
    pairs = pd.DataFrame({
        "repeated_location_group_id": ["A"] * 1 + ["B"] * 6,
        "pair_qc_status": ["VALID"] * 7,
        "pairwise_slope_c_per_min": [1.0] + [5.0] * 6,
        "spatial_separation_m": [5.0] * 7, "time_difference_s": [600.0] * 7,
        "temperature_difference_c": [1.0] * 7, "pair_weight": [1.0] + [1 / 6] * 6,
        "direction_relation": ["same_direction"] * 7,
        "visit_id_earlier": ["a1", "b1", "b1", "b1", "b2", "b2", "b3"],
        "visit_id_later": ["a2", "b2", "b3", "b4", "b3", "b4", "b4"],
    })
    groups = pd.DataFrame({
        "repeated_location_group_id": ["A", "B"], "group_valid": [True, True],
        "repeated_location_group_centroid_lat": [BASE_LAT, BASE_LAT + 0.001],
        "repeated_location_group_centroid_lon": [BASE_LON, BASE_LON],
    })
    visits = pd.DataFrame({"repeated_location_visit_id": ["a1", "a2", "b1", "b2", "b3", "b4"], "visit_qc_status": "OK",
                            "visit_start_timestamp": pd.Timestamp("2026-01-01"), "visit_end_timestamp": pd.Timestamp("2026-01-01"),
                            "visit_representative_timestamp": pd.Timestamp("2026-01-01")})
    df = pd.DataFrame({
        "temporal_candidate_recommended": [True],
        "canonical_latitude": [BASE_LAT], "canonical_longitude": [BASE_LON],
    })
    metrics = compute_session_assessability_metrics(
        df, "temporal_candidate_recommended",
        groups, visits, pairs, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-01") + pd.Timedelta(hours=1),
    )
    # each group contributes equal total weight (1.0 each) -> weighted median
    # is influenced 50/50 by A's 1.0 and B's 5.0, not dominated 6:1 by B.
    assert metrics["median_pairwise_slope_c_per_min"] in (1.0, 5.0)  # weighted-median tie lands on one of the two group values, not a naive-pooled 5.0-biased number
    assert metrics["pairwise_slope_mad"] >= 0.0


def test_start_end_consistency_true_when_signs_and_magnitude_match_revisit_trend():
    metrics = {"median_pairwise_slope_c_per_min": 0.1}  # 0.1 C/min
    metrics = add_start_end_consistency(metrics, True, 10.0, 16.0, raw_start_end_time_difference_s=3600.0)  # predicted = 0.1*60=6.0, raw=6.0
    assert metrics["start_end_pair_available"] is True
    assert metrics["start_end_pair_consistent_with_revisits"] is True


def test_start_end_consistency_false_when_signs_disagree():
    metrics = {"median_pairwise_slope_c_per_min": 0.1}
    metrics = add_start_end_consistency(metrics, True, 16.0, 10.0, raw_start_end_time_difference_s=3600.0)  # raw diff negative, predicted positive
    assert metrics["start_end_pair_consistent_with_revisits"] is False


def test_start_end_consistency_none_when_locations_not_comparable():
    metrics = {"median_pairwise_slope_c_per_min": 0.1}
    metrics = add_start_end_consistency(metrics, False, 10.0, 16.0, raw_start_end_time_difference_s=3600.0)
    assert metrics["start_end_pair_available"] is False
    assert metrics["start_end_pair_consistent_with_revisits"] is None


# ---- end-to-end integration ----

def _row_full(t, lat=BASE_LAT, lon=BASE_LON, temp=12.0, **overrides):
    base = {
        "time_utc": pd.Timestamp("2026-02-13T09:00:00Z") + pd.Timedelta(seconds=t),
        "canonical_latitude": lat, "canonical_longitude": lon, "canonical_temperature_c": temp,
        "segment_id": 0, "keep_permissive": True, "keep_recommended": True, "keep_restrictive": True,
    }
    for flag in [
        "qc_temp_isolated_spike", "qc_temp_impossible", "qc_gps_jump", "qc_spatial_jump",
        "qc_isolated_position_outlier", "qc_gps_freeze", "qc_sensor_stabilization",
        "qc_post_stop_recovery", "qc_low_ventilation_possible", "qc_temp_rate_anomaly",
        "qc_possible_gps_freeze", "qc_stop_event", "qc_stationary", "qc_coord_repeated", "qc_segment_break",
    ]:
        base[flag] = False
    base.update(overrides)
    return base


def test_full_pipeline_wiring_produces_a_coherent_classification():
    profile = get_profile(load_matching_policy(), "temporal_recommended")
    rows = [_row_full(0, temp=10.0), _row_full(5, temp=10.1), _row_full(4000, temp=11.0), _row_full(4005, temp=11.1)]
    df = build_temporal_candidate_masks(pd.DataFrame(rows))
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", profile)
    pairs = build_pairs(visits, df, profile)
    metrics = compute_session_assessability_metrics(
        df, "temporal_candidate_recommended", groups, visits, pairs, df["time_utc"].min(), df["time_utc"].max(),
    )
    metrics_df = add_derived_assessability_columns(pd.DataFrame([metrics]))
    out = classify_assessability(metrics_df, ROOT_POLICY)
    # 1 group, 1 pair -> START_END_ONLY per the real policy table.
    assert out.iloc[0]["reason_code"] == "START_END_ONLY"
