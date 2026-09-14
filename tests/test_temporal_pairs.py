import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.candidates import build_temporal_candidate_masks
from meteotracker_qc.temporal_drift.config import get_profile, load_matching_policy
from meteotracker_qc.temporal_drift.grouping import compute_groups_and_visits
from meteotracker_qc.temporal_drift.pairs import build_pairs, valid_pairs

BASE_LAT, BASE_LON = 44.4949, 11.3426


def _profile(name="temporal_recommended"):
    return get_profile(load_matching_policy(), name)


def _visit(group_id, visit_id, ts, temp, lat=BASE_LAT, lon=BASE_LON, bearing=0.0, seg="0", qc_status="OK"):
    return {
        "repeated_location_group_id": group_id, "repeated_location_visit_id": visit_id,
        "repeated_location_group_centroid_lat": lat, "repeated_location_group_centroid_lon": lon,
        "distance_to_group_centroid_m": 0.0, "visit_start_timestamp": ts, "visit_end_timestamp": ts,
        "visit_representative_timestamp": ts, "visit_representative_temperature_c": temp,
        "visit_representative_lat": lat, "visit_representative_lon": lon,
        "visit_n_points": 2, "visit_duration_s": 5.0, "visit_direction_class": "same_direction",
        "visit_bearing_deg": bearing, "visit_segment_ids": seg, "visit_qc_status": qc_status,
    }


T0 = pd.Timestamp("2026-02-13T09:00:00Z")


def _full_df_empty():
    return pd.DataFrame({"time_utc": pd.Series([], dtype="datetime64[ns, UTC]"), "qc_segment_break": pd.Series([], dtype=bool)})


# ---- 18: valid pair ----

def test_valid_pair_built_with_correct_slope():
    visits = pd.DataFrame([
        _visit("g1", "v1", T0, 10.0),
        _visit("g1", "v2", T0 + pd.Timedelta(seconds=600), 11.0),
    ])
    pairs = build_pairs(visits, _full_df_empty(), _profile())
    assert len(pairs) == 1
    row = pairs.iloc[0]
    assert row["pair_qc_status"] == "VALID"
    assert row["time_difference_s"] == pytest.approx(600.0)
    assert row["temperature_difference_c"] == pytest.approx(1.0)
    assert row["pairwise_slope_c_per_min"] == pytest.approx(0.1)


# ---- 22: excluded for insufficient temporal separation ----

def test_pair_excluded_for_insufficient_temporal_separation():
    visits = pd.DataFrame([
        _visit("g1", "v1", T0, 10.0),
        _visit("g1", "v2", T0 + pd.Timedelta(seconds=100), 10.5),  # < 300s (temporal_recommended)
    ])
    pairs = build_pairs(visits, _full_df_empty(), _profile())
    row = pairs.iloc[0]
    assert row["pair_qc_status"] == "EXCLUDED"
    assert "EXCLUDED_INSUFFICIENT_TEMPORAL_SEPARATION" in row["pair_exclusion_reasons"]
    assert len(pairs) == 1, "excluded pairs must still appear in output, never dropped"


# ---- 21: excluded for spatial separation ----

def test_pair_excluded_when_spatial_separation_exceeds_radius():
    visits = pd.DataFrame([
        _visit("g1", "v1", T0, 10.0, lat=BASE_LAT, lon=BASE_LON),
        _visit("g1", "v2", T0 + pd.Timedelta(seconds=600), 10.5, lat=BASE_LAT + 0.01, lon=BASE_LON),  # ~1.1km away
    ])
    pairs = build_pairs(visits, _full_df_empty(), _profile())
    row = pairs.iloc[0]
    assert "EXCLUDED_SPATIAL_SEPARATION_EXCEEDS_RADIUS" in row["pair_exclusion_reasons"]


# ---- low visit quality ----

def test_pair_excluded_when_either_visit_is_low_quality():
    visits = pd.DataFrame([
        _visit("g1", "v1", T0, 10.0, qc_status="LOW_POINT_COUNT"),
        _visit("g1", "v2", T0 + pd.Timedelta(seconds=600), 10.5),
    ])
    pairs = build_pairs(visits, _full_df_empty(), _profile())
    assert "EXCLUDED_LOW_VISIT_QUALITY" in pairs.iloc[0]["pair_exclusion_reasons"]


# ---- 19/20: spike / freeze exclusion propagates end-to-end (candidates -> grouping -> pairs) ----

def _row_full(t, lat=BASE_LAT, lon=BASE_LON, temp=12.0, **overrides):
    base = {
        "time_utc": T0 + pd.Timedelta(seconds=t), "canonical_latitude": lat, "canonical_longitude": lon,
        "canonical_temperature_c": temp, "segment_id": 0, "keep_permissive": True, "keep_recommended": True,
        "keep_restrictive": True,
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


def test_spike_contaminated_second_visit_never_produces_a_pair():
    rows = [
        _row_full(0), _row_full(5),  # visit 1, clean
        _row_full(4000, qc_temp_isolated_spike=True), _row_full(4005, qc_temp_isolated_spike=True),  # would-be visit 2, all spike
    ]
    df = build_temporal_candidate_masks(pd.DataFrame(rows))
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    pairs = build_pairs(visits, df, _profile())
    assert len(visits) == 1, "the spike-contaminated cluster must never become a visit"
    assert pairs.empty


def test_freeze_contaminated_second_visit_never_produces_a_pair():
    rows = [
        _row_full(0), _row_full(5),
        _row_full(4000, qc_gps_freeze=True), _row_full(4005, qc_gps_freeze=True),
    ]
    df = build_temporal_candidate_masks(pd.DataFrame(rows))
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    pairs = build_pairs(visits, df, _profile())
    assert len(visits) == 1
    assert pairs.empty


# ---- crosses_segment_break is descriptive, never exclusionary ----

def test_crosses_segment_break_is_descriptive_not_exclusionary():
    rows = [
        _row_full(0, canonical_temperature_c=10.0),
        _row_full(5, canonical_temperature_c=10.0),
        _row_full(2000, canonical_temperature_c=10.0, qc_segment_break=True, canonical_latitude=BASE_LAT + 0.02),  # break marker strictly between the two visits
        _row_full(4000, canonical_temperature_c=11.0),
        _row_full(4005, canonical_temperature_c=11.0),
    ]
    df = build_temporal_candidate_masks(pd.DataFrame(rows))
    groups, visits, obs = compute_groups_and_visits(df, "temporal_candidate_recommended", _profile())
    pairs = build_pairs(visits, df, _profile())
    assert len(pairs) == 1
    row = pairs.iloc[0]
    assert row["crosses_segment_break"] is True or row["crosses_segment_break"] == True  # noqa: E712
    assert row["pair_qc_status"] == "VALID", "crossing a segment break must never exclude an otherwise-valid revisit pair"


# ---- 23: pseudo-replication -- pair weight equalizes group contribution ----

def test_pair_weight_equalizes_group_contribution_regardless_of_visit_count():
    visits_small = pd.DataFrame([_visit("g1", f"v{i}", T0 + pd.Timedelta(seconds=i * 600), 10.0 + i) for i in range(2)])
    visits_large = pd.DataFrame([_visit("g2", f"v{i}", T0 + pd.Timedelta(seconds=i * 600), 10.0 + i) for i in range(4)])
    pairs_small = build_pairs(visits_small, _full_df_empty(), _profile())
    pairs_large = build_pairs(visits_large, _full_df_empty(), _profile())
    assert pairs_small["pair_weight"].sum() == pytest.approx(1.0)
    assert pairs_large["pair_weight"].sum() == pytest.approx(1.0)
    assert len(pairs_large) == 6  # C(4,2)
    assert pairs_large["pair_weight"].iloc[0] == pytest.approx(1.0 / 6.0)


def test_pair_ids_unique_and_no_group_with_fewer_than_two_visits_produces_pairs():
    visits = pd.DataFrame([
        _visit("g_lonely", "v1", T0, 10.0),  # only 1 visit, no pair possible
        _visit("g1", "v1", T0, 10.0), _visit("g1", "v2", T0 + pd.Timedelta(seconds=600), 11.0),
    ])
    pairs = build_pairs(visits, _full_df_empty(), _profile())
    assert (pairs["repeated_location_group_id"] == "g_lonely").sum() == 0
    assert pairs["repeated_location_pair_id"].is_unique


def test_valid_pairs_helper_filters_correctly():
    visits = pd.DataFrame([
        _visit("g1", "v1", T0, 10.0), _visit("g1", "v2", T0 + pd.Timedelta(seconds=600), 11.0),
        _visit("g1", "v3", T0 + pd.Timedelta(seconds=650), 11.1),  # too close to v2
    ])
    pairs = build_pairs(visits, _full_df_empty(), _profile())
    vp = valid_pairs(pairs)
    assert (vp["pair_qc_status"] == "VALID").all()
    assert len(vp) < len(pairs)
