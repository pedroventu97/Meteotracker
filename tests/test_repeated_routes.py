from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pyproj import Transformer

from meteotracker_qc.repeated_routes.candidates import build_candidate_pairs
from meteotracker_qc.repeated_routes.config import RepeatedRoutesConfig
from meteotracker_qc.repeated_routes.matching import match_tracks
from meteotracker_qc.repeated_routes.segments import consolidate_segments
from meteotracker_qc.repeated_routes.timebins import describe_timestamp
from meteotracker_qc.repeated_routes.tracks import (
    PartTrack,
    prepare_campaign_tracks,
    resample_track,
)

CFG = RepeatedRoutesConfig()
_FWD = Transformer.from_crs("EPSG:4326", f"EPSG:{CFG.crs_metric_epsg}", always_xy=True)
_INV = Transformer.from_crs(f"EPSG:{CFG.crs_metric_epsg}", "EPSG:4326", always_xy=True)
T0 = pd.Timestamp("2026-06-01 08:00:00", tz="UTC")

# A base point near Bologna, in the metric (UTM 32N) CRS, used as the origin for all
# synthetic straight-line tracks below.
X0, Y0 = 400000.0, 4930000.0


def make_points_df(x0: float, y0: float, dx: float, dy: float, n: int, t0: pd.Timestamp, dt_s: float = 1.0) -> pd.DataFrame:
    """A synthetic, already-cleaned points dataframe (as tracks.prepare_campaign_tracks
    would produce internally): straight line from (x0,y0) in metric CRS, step (dx,dy)."""
    x = x0 + np.arange(n) * dx
    y = y0 + np.arange(n) * dy
    t = pd.date_range(t0, periods=n, freq=pd.Timedelta(seconds=dt_s), tz="UTC")
    lon, lat = _INV.transform(x, y)
    df = pd.DataFrame({
        "source_row": np.arange(n), "time_utc": t, "Lat": lat, "Lon": lon,
        "Speed[km/h]": 30.0, "x_m": x, "y_m": y,
    })
    step = np.hypot(np.diff(x, prepend=x[0]), np.diff(y, prepend=y[0]))
    step[0] = 0.0
    df["cum_distance_m"] = np.cumsum(step)
    return df


def make_part(campaign_id: str, part_id: int, points_df: pd.DataFrame, cfg: RepeatedRoutesConfig = CFG) -> PartTrack:
    resampled = resample_track(points_df, cfg, _INV)
    resampled = resampled.assign(campaign_id=campaign_id, campaign_part_id=part_id)
    return PartTrack(campaign_id=campaign_id, campaign_part_id=part_id, points=points_df, resampled=resampled)


def make_standardized(x0, y0, dx, dy, n, t0, dt_s=1.0, valid: np.ndarray | None = None) -> pd.DataFrame:
    """A synthetic dataframe shaped like meteotracker_qc's QC-standardized output,
    for exercising tracks.prepare_campaign_tracks end-to-end (cleaning, part
    splitting, resampling) rather than the lower-level helpers directly."""
    x = x0 + np.arange(n) * dx
    y = y0 + np.arange(n) * dy
    t = pd.to_datetime(t0) + pd.to_timedelta(np.cumsum(np.r_[0, np.full(n - 1, dt_s)]), unit="s")
    lon, lat = _INV.transform(x, y)
    df = pd.DataFrame({
        "source_row": np.arange(n), "time_utc": t, "Lat": lat, "Lon": lon, "Speed[km/h]": 30.0,
        "use_for_route_mapping": True, "qc_coord_missing": False,
    })
    if valid is not None:
        df.loc[~valid, "use_for_route_mapping"] = False
    return df


# --- 1. Two nearly identical tracks, same direction -----------------------------------

def test_two_nearly_identical_tracks_same_direction():
    a = make_points_df(X0, Y0, 0, 5, 100, T0)  # 500 m due north
    b = make_points_df(X0 + 3, Y0, 0, 5, 100, T0 + pd.Timedelta(hours=1))  # 3 m parallel offset
    part_a, part_b = make_part("campA", 1, a), make_part("campB", 1, b)
    matches = match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, CFG)
    assert len(matches) == 1
    assert matches[0]["direction_class"] == "same_direction"
    assert matches[0]["shared_length_m"] > 450
    assert matches[0]["mean_matching_distance_m"] < 5


# --- 2. Two nearly identical tracks, opposite direction --------------------------------

def test_two_nearly_identical_tracks_opposite_direction():
    a = make_points_df(X0, Y0, 0, 5, 100, T0)
    b_rev = make_points_df(X0 + 3, Y0 + 495, 0, -5, 100, T0 + pd.Timedelta(hours=2))
    part_a, part_b = make_part("campA", 1, a), make_part("campC", 1, b_rev)
    matches = match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, CFG)
    assert len(matches) == 1
    assert matches[0]["direction_class"] == "opposite_direction"


# --- 3. One track entirely contained within a longer one -------------------------------

def test_track_entirely_contained_in_longer_track():
    a_long = make_points_df(X0, Y0, 0, 5, 200, T0)  # 1000 m
    b_sub = make_points_df(X0 + 2, Y0 + 300, 0, 5, 80, T0 + pd.Timedelta(hours=3))  # 400 m, fully inside [0,1000]
    part_a, part_b = make_part("campD", 1, a_long), make_part("campE", 1, b_sub)
    matches = match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, CFG)
    assert len(matches) == 1
    m = matches[0]
    assert m["a_start_m"] > 0 and m["a_end_m"] < a_long["cum_distance_m"].iloc[-1]
    assert m["shared_length_m"] > 350


# --- 4. Two tracks sharing only a middle sub-stretch, each extending beyond it ---------

def test_only_a_common_sub_stretch():
    a = make_points_df(X0, Y0, 0, 5, 140, T0)  # 0..700 m
    b = make_points_df(X0 + 2, Y0 + 300, 0, 5, 140, T0 + pd.Timedelta(hours=4))  # covers 300..1000 m
    part_a, part_b = make_part("campF", 1, a), make_part("campG", 1, b)
    matches = match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, CFG)
    assert len(matches) == 1
    m = matches[0]
    assert 300 <= m["shared_length_m"] <= 420
    # A's matched span should sit near its own tail, not cover the whole 700 m track
    assert m["a_end_m"] > m["a_start_m"]
    assert m["a_start_m"] > 200


# --- 5. Two parallel streets that must NOT be merged ------------------------------------

def test_parallel_streets_not_merged():
    a = make_points_df(X0, Y0, 0, 5, 100, T0)
    c_parallel = make_points_df(X0 + 60, Y0, 0, 5, 100, T0 + pd.Timedelta(hours=5))  # 60 m away, tolerance=20 m
    part_a, part_c = make_part("campA", 1, a), make_part("campH", 1, c_parallel)
    matches = match_tracks(part_a.track_id, part_a.resampled, part_c.track_id, part_c.resampled, CFG)
    assert matches == []


# --- 6. Two tracks that only share a crossing point --------------------------------------

def test_tracks_sharing_only_a_crossing():
    a = make_points_df(X0, Y0, 0, 5, 100, T0)  # north-south line
    d_cross = make_points_df(X0 - 100, Y0 + 250, 5, 0, 40, T0 + pd.Timedelta(hours=6))  # east-west, crosses near the middle
    part_a, part_d = make_part("campA", 1, a), make_part("campI", 1, d_cross)
    matches = match_tracks(part_a.track_id, part_a.resampled, part_d.track_id, part_d.resampled, CFG)
    assert matches == []  # crossing is far shorter than minimum_shared_length_m


# --- 7. A track with a GPS-freeze block: frozen points must be excluded ----------------

def test_gps_freeze_points_excluded_from_geometry():
    n = 150
    valid = np.ones(n, dtype=bool)
    valid[50:66] = False  # a 16-point "freeze" stretch flagged invalid by the QC layer
    std = make_standardized(X0, Y0, 0, 5, n, T0, valid=valid)
    tracks = prepare_campaign_tracks("freeze_campaign", std, CFG)
    assert len(tracks.parts) == 1
    total_valid_points = sum(len(p.points) for p in tracks.parts)
    assert total_valid_points == int(valid.sum())


# --- 8. A track with a large temporal gap must split into two parts --------------------

def test_large_temporal_gap_splits_into_two_parts():
    n = 200
    t = pd.date_range(T0, periods=100, freq="1s", tz="UTC")
    t = t.append(pd.date_range(t[-1] + pd.Timedelta(seconds=300), periods=100, freq="1s", tz="UTC"))
    x = X0 + np.arange(n) * 5.0
    y = np.full(n, Y0)
    lon, lat = _INV.transform(x, y)
    std = pd.DataFrame({
        "source_row": np.arange(n), "time_utc": t, "Lat": lat, "Lon": lon, "Speed[km/h]": 18.0,
        "use_for_route_mapping": True, "qc_coord_missing": False,
    })
    tracks = prepare_campaign_tracks("gap_campaign", std, CFG)
    assert len(tracks.parts) == 2
    assert tracks.parts[0].campaign_part_id != tracks.parts[1].campaign_part_id


# --- 9. Two separate parts of the same campaign must not be linked by a straight line ---

def test_separate_parts_not_linearly_interpolated_across_gap():
    n = 200
    t = pd.date_range(T0, periods=100, freq="1s", tz="UTC")
    t = t.append(pd.date_range(t[-1] + pd.Timedelta(seconds=300), periods=100, freq="1s", tz="UTC"))
    x = X0 + np.arange(n) * 5.0
    y = np.full(n, Y0)
    lon, lat = _INV.transform(x, y)
    std = pd.DataFrame({
        "source_row": np.arange(n), "time_utc": t, "Lat": lat, "Lon": lon, "Speed[km/h]": 18.0,
        "use_for_route_mapping": True, "qc_coord_missing": False,
    })
    tracks = prepare_campaign_tracks("gap_campaign2", std, CFG)
    assert len(tracks.parts) == 2
    # Each part's own resampled polyline must stay within its own 495 m span -- if the
    # two parts had been bridged into one track, cum_distance/resampling would run to ~995 m.
    for part in tracks.parts:
        assert part.total_length_m < 500


# --- 10. A shared run below the minimum length must be rejected -------------------------

def test_segment_below_minimum_length_rejected():
    cfg = CFG
    a = make_points_df(X0, Y0, 0, 5, 20, T0)  # 95 m, well under minimum_shared_length_m=250
    b = make_points_df(X0 + 2, Y0, 0, 5, 20, T0 + pd.Timedelta(hours=7))
    part_a, part_b = make_part("campJ", 1, a, cfg), make_part("campK", 1, b, cfg)
    matches = match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, cfg)
    assert matches == []


# --- 11. A distance just past the tolerance must not match; just under it must --------

def test_distance_boundary_around_tolerance():
    a = make_points_df(X0, Y0, 0, 5, 100, T0)
    just_inside = make_points_df(X0 + (CFG.matching_tolerance_m - 1), Y0, 0, 5, 100, T0 + pd.Timedelta(hours=8))
    just_outside = make_points_df(X0 + (CFG.matching_tolerance_m + 1), Y0, 0, 5, 100, T0 + pd.Timedelta(hours=9))
    part_a = make_part("campA", 1, a)
    part_in = make_part("campL", 1, just_inside)
    part_out = make_part("campM", 1, just_outside)
    matches_in = match_tracks(part_a.track_id, part_a.resampled, part_in.track_id, part_in.resampled, CFG)
    matches_out = match_tracks(part_a.track_id, part_a.resampled, part_out.track_id, part_out.resampled, CFG)
    assert len(matches_in) == 1
    assert matches_out == []


# --- 12. Four campaigns on the same corridor consolidate into ONE repeated segment -----

def test_four_campaigns_consolidate_into_one_segment():
    parts = {}
    for i, (offset, hour) in enumerate([(0, 0), (2, 1), (-2, 5), (1, 20)]):
        df = make_points_df(X0 + offset, Y0, 0, 5, 100, T0 + pd.Timedelta(hours=hour))
        p = make_part(f"camp{i}", 1, df)
        parts[p.track_id] = p
    part_list = list(parts.values())
    candidate_df, _stats = build_candidate_pairs(part_list, CFG)

    pairwise_matches = []
    for _, row in candidate_df.iterrows():
        pa, pb = parts[row["track_id_a"]], parts[row["track_id_b"]]
        pairwise_matches.extend(match_tracks(pa.track_id, pa.resampled, pb.track_id, pb.resampled, CFG))

    standardized = {}
    for p in part_list:
        df = p.points.copy()
        df["use_for_route_mapping"] = True
        df["qc_coord_missing"] = False
        standardized[p.campaign_id] = df

    segments_df, passages_df, _matches_df = consolidate_segments(parts, pairwise_matches, standardized, CFG)
    assert len(segments_df) == 1
    assert int(segments_df.iloc[0]["n_passages"]) == 4
    assert int(segments_df.iloc[0]["n_campaigns"]) == 4
    assert len(passages_df) == 4


# --- 13. Europe/Rome local-time handling (including a DST transition) -------------------

def test_europe_rome_local_time_handling():
    # 2026-06-01 08:00 UTC is CEST (+02:00) in summer -> local 10:00
    summer = pd.Timestamp("2026-06-01 08:00:00", tz="UTC")
    desc = describe_timestamp(summer, CFG)
    assert desc["local_time"] == "10:00:00"
    assert desc["local_hour_decimal"] == pytest.approx(10.0)

    # 2026-01-15 08:00 UTC is CET (+01:00) in winter -> local 09:00
    winter = pd.Timestamp("2026-01-15 08:00:00", tz="UTC")
    desc_winter = describe_timestamp(winter, CFG)
    assert desc_winter["local_time"] == "09:00:00"


# --- 14. Deterministic results across repeated runs -------------------------------------

def test_deterministic_repeated_pipeline_runs():
    a = make_points_df(X0, Y0, 0, 5, 100, T0)
    b = make_points_df(X0 + 3, Y0, 0, 5, 100, T0 + pd.Timedelta(hours=1))
    part_a, part_b = make_part("campA", 1, a), make_part("campB", 1, b)

    matches_1 = match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, CFG)
    matches_2 = match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, CFG)
    assert matches_1 == matches_2

    standardized = {}
    for p in (part_a, part_b):
        df = p.points.copy()
        df["use_for_route_mapping"] = True
        df["qc_coord_missing"] = False
        standardized[p.campaign_id] = df
    parts_by_track = {part_a.track_id: part_a, part_b.track_id: part_b}

    seg1, pass1, _ = consolidate_segments(parts_by_track, matches_1, standardized, CFG)
    seg2, pass2, _ = consolidate_segments(parts_by_track, matches_2, standardized, CFG)
    pd.testing.assert_frame_equal(seg1.drop(columns=["geometry"]), seg2.drop(columns=["geometry"]))
    pd.testing.assert_frame_equal(pass1.drop(columns=["geometry"]), pass2.drop(columns=["geometry"]))
