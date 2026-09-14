import math

import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.config import get_profile, load_matching_policy
from meteotracker_qc.temporal_drift.grouping import (
    bearing_relation, build_linkage, compute_groups_and_visits, cut_groups,
    estimate_visit_bearing, grouping_eligible_mask, verify_group_diameters,
)

M_PER_DEG_LAT = 111320.0
BASE_LAT, BASE_LON = 44.4949, 11.3426


def _lat_offset_m(meters: float) -> float:
    return meters / M_PER_DEG_LAT


def _row(t, lat=BASE_LAT, lon=BASE_LON, temp=12.0, segment_id=0, candidate=True, **overrides):
    base = {
        "time_utc": pd.Timestamp("2026-02-13T09:00:00Z") + pd.Timedelta(seconds=t),
        "canonical_latitude": lat, "canonical_longitude": lon, "canonical_temperature_c": temp,
        "segment_id": segment_id, "temporal_candidate_recommended": candidate, "temporal_candidate_conservative": candidate,
        "qc_stop_event": False, "qc_stationary": False, "qc_coord_repeated": False,
    }
    base.update(overrides)
    return base


def _profile(name="temporal_recommended"):
    return get_profile(load_matching_policy(), name)


# ---- chain-effect avoidance ----

def test_complete_linkage_avoids_chain_effect():
    lat_a, lat_b, lat_c = BASE_LAT, BASE_LAT + _lat_offset_m(14), BASE_LAT + _lat_offset_m(28)
    df = pd.DataFrame([
        _row(0, lat=lat_a), _row(60, lat=lat_b), _row(120, lat=lat_c),
    ])
    mask = grouping_eligible_mask(df, "temporal_candidate_recommended")
    link = build_linkage(df, mask)
    labels = cut_groups(link, radius_m=15.0)
    # A-B = 14m (<=15, mergeable), B-C = 14m (<=15, mergeable), A-C = 28m (>15).
    # Single-linkage would chain all three together; complete-linkage must not.
    assert labels.loc[0] == labels.loc[1], "A and B (14m apart) should share a group"
    assert labels.loc[0] != labels.loc[2], "A and C (28m apart) must NOT be forced into the same group via B"


def test_group_diameter_verification_matches_actual_max_distance():
    lat_a, lat_b = BASE_LAT, BASE_LAT + _lat_offset_m(9)
    df = pd.DataFrame([_row(0, lat=lat_a), _row(60, lat=lat_b)])
    mask = grouping_eligible_mask(df, "temporal_candidate_recommended")
    link = build_linkage(df, mask)
    labels = cut_groups(link, radius_m=15.0)
    diam = verify_group_diameters(link, labels)
    assert list(diam.values())[0] == pytest.approx(9.0, abs=0.5)


# ---- radius sensitivity ----

@pytest.mark.parametrize("radius_m,expect_merged", [(5.0, False), (10.0, True), (20.0, True), (30.0, True)])
def test_radius_variants_control_merge_of_8m_apart_points(radius_m, expect_merged):
    lat_b = BASE_LAT + _lat_offset_m(8)
    df = pd.DataFrame([_row(0), _row(60, lat=lat_b)])
    mask = grouping_eligible_mask(df, "temporal_candidate_recommended")
    link = build_linkage(df, mask)
    labels = cut_groups(link, radius_m=radius_m)
    merged = labels.loc[0] == labels.loc[1]
    assert merged == expect_merged


# ---- visits: merge / split ----

def test_two_visits_at_the_same_place_are_recognized():
    rows = [_row(0), _row(5), _row(4000), _row(4005)]  # two clusters of 2 points, far apart in time
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    assert len(groups) == 1
    assert groups.iloc[0]["group_n_visits"] == 2
    assert groups.iloc[0]["group_valid"]
    assert len(visits) == 2


def test_consecutive_points_within_merge_gap_are_one_visit_not_two():
    rows = [_row(0), _row(10), _row(20), _row(29)]  # all within 30s of each other
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    assert len(visits) == 1
    assert visits.iloc[0]["visit_n_points"] == 4


def test_gap_exceeding_merge_threshold_splits_into_two_visits():
    rows = [_row(0), _row(10), _row(200), _row(210)]  # gap of 190s > visit_merge_gap_s(30)
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    assert len(visits) == 2


# ---- exclusions from grouping ----

def test_stop_event_excluded_from_grouping_even_if_temporal_candidate():
    df = pd.DataFrame([_row(0, qc_stop_event=True)])
    mask = grouping_eligible_mask(df, "temporal_candidate_recommended")
    assert not mask.iloc[0]


def test_stationary_point_excluded_from_grouping():
    df = pd.DataFrame([_row(0, qc_stationary=True)])
    mask = grouping_eligible_mask(df, "temporal_candidate_recommended")
    assert not mask.iloc[0]


def test_coord_repeated_quantization_duplicate_excluded_from_grouping():
    df = pd.DataFrame([_row(0, qc_coord_repeated=True)])
    mask = grouping_eligible_mask(df, "temporal_candidate_recommended")
    assert not mask.iloc[0]


def test_stop_dominated_visit_does_not_create_a_spurious_revisit():
    # Real revisit (2 clean visits) plus a cluster of stop-event points at the
    # same spot that must NOT be counted as a third visit.
    rows = [_row(0), _row(5), _row(4000), _row(4005), _row(4010, qc_stop_event=True), _row(4015, qc_stop_event=True)]
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    assert len(visits) == 2, "the two stop-event points must not form a third visit"


def test_non_candidate_points_never_enter_any_group():
    rows = [_row(0), _row(5, candidate=False), _row(10)]
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    assert 1 not in obs["row_index"].tolist()


# ---- visits across segments ----

def test_visits_can_span_different_segment_ids():
    rows = [_row(0, segment_id=0), _row(5, segment_id=0), _row(4000, segment_id=1), _row(4005, segment_id=1)]
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    assert len(visits) == 2
    seg_ids_per_visit = set(visits["visit_segment_ids"])
    assert seg_ids_per_visit == {"0", "1"}


# ---- robust aggregation ----

def test_visit_representative_temperature_uses_median_not_mean():
    rows = [_row(0, temp=12.0), _row(5, temp=12.2), _row(10, temp=40.0)]  # one wild outlier
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    assert visits.iloc[0]["visit_representative_temperature_c"] == pytest.approx(12.2, abs=0.01)


def test_visit_representative_timestamp_falls_within_the_visit_own_time_range():
    # Regression test: an earlier implementation round-tripped through int64
    # nanoseconds assuming datetime64[ns], but real parquet data here is
    # datetime64[us] -- that mismatch silently produced 1970-epoch garbage.
    rows = [_row(0), _row(10), _row(20)]
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    visit = visits.iloc[0]
    assert visit["visit_start_timestamp"] <= visit["visit_representative_timestamp"] <= visit["visit_end_timestamp"]
    assert visit["visit_representative_timestamp"].year >= 2026


def test_low_point_count_visit_flagged_under_conservative():
    # temporal_conservative requires >=3 points/visit (a real, data-derived
    # ~23rd-percentile cutoff -- see build_repeated_location_matching.py).
    # visit 1: a single point (below the minimum); visit 2: three points, meets it.
    rows = [_row(0), _row(4000), _row(4005), _row(4010)]
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_conservative", _profile("temporal_conservative"))
    visits_by_n = visits.set_index("visit_n_points")
    assert visits_by_n.loc[1, "visit_qc_status"] == "LOW_POINT_COUNT"
    assert visits_by_n.loc[3, "visit_qc_status"] == "OK"


def test_single_point_visit_is_ok_under_recommended_per_real_data_evidence():
    # Regression test for a real miscalibration found on the first full
    # 34-campaign run: minimum_points_per_visit=2 for temporal_recommended
    # excluded the majority (57.2%) of real visits, whose median point count
    # is exactly 1 (a bike pass covers a 15m group radius in a few seconds,
    # often yielding just one GPS+temperature reading there). Corrected to 1
    # (evidence_source=data_distribution). A single-point visit must be OK,
    # not LOW_POINT_COUNT, under the recommended profile.
    rows = [_row(0), _row(4000)]
    df = pd.DataFrame(rows)
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    assert (visits["visit_n_points"] == 1).all()
    assert (visits["visit_qc_status"] == "OK").all()


# ---- direction ----

def test_bearing_relation_same_direction_under_45deg():
    assert bearing_relation(10.0, 30.0) == "same_direction"


def test_bearing_relation_opposite_direction_over_135deg():
    assert bearing_relation(10.0, 200.0) == "opposite_direction"


def test_bearing_relation_unclear_in_between():
    assert bearing_relation(0.0, 90.0) == "unclear"


def test_bearing_relation_unavailable_when_nan():
    assert bearing_relation(float("nan"), 90.0) == "unavailable"


def test_direction_unavailable_when_visit_has_no_surrounding_context():
    # A visit with no points before/after it anywhere in the campaign (the
    # whole df is just the revisit itself) cannot have a bearing estimated.
    segs = np.array([0, 0])
    lats = np.array([BASE_LAT, BASE_LAT])
    lons = np.array([BASE_LON, BASE_LON])
    bearing = estimate_visit_bearing(segs, lats, lons, visit_first_pos=0, visit_last_pos=1)
    assert math.isnan(bearing)


def test_direction_estimated_from_approach_and_departure_trajectory():
    # A straight trajectory passing through the revisit point twice, in the
    # same direction both times (north-heading approach/exit before and after).
    lat0 = BASE_LAT
    rows = []
    t = 0
    for i in range(5):
        rows.append(_row(t, lat=lat0 + _lat_offset_m(i * 10), segment_id=0))
        t += 5
    for i in range(2):  # the revisit cluster itself
        rows.append(_row(t, lat=lat0 + _lat_offset_m(45), segment_id=0))
        t += 5
    for i in range(5):
        rows.append(_row(t, lat=lat0 + _lat_offset_m(45 + (i + 1) * 10), segment_id=0))
        t += 5
    df = pd.DataFrame(rows)
    full_segment_ids = df["segment_id"].to_numpy()
    full_lats = df["canonical_latitude"].to_numpy(dtype=float)
    full_lons = df["canonical_longitude"].to_numpy(dtype=float)
    bearing = estimate_visit_bearing(full_segment_ids, full_lats, full_lons, visit_first_pos=5, visit_last_pos=6)
    assert 0 <= bearing < 45 or bearing > 315  # heading north
