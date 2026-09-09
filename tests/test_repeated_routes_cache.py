from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from meteotracker_qc.repeated_routes.cache import (
    RepeatedRoutesCache, pair_metadata, stable_hash, track_metadata,
)
from meteotracker_qc.repeated_routes.candidates import build_candidate_pairs
from meteotracker_qc.repeated_routes.config import RepeatedRoutesConfig
from meteotracker_qc.repeated_routes.pipeline import match_candidate_pairs
from meteotracker_qc.repeated_routes.segments import consolidate_segments
from meteotracker_qc.repeated_routes.tracks import PartTrack


def _part(campaign: str, offset: float = 0.0, start: float = 0.0, end: float = 500.0) -> PartTrack:
    s = np.arange(start, end + 10.0, 10.0)
    x = np.full(len(s), 400000.0 + offset)
    y = 4930000.0 + s
    time = pd.date_range("2026-01-01", periods=len(s), freq="1s", tz="UTC")
    points = pd.DataFrame({
        "source_row": np.arange(len(s)), "time_utc": time, "Lat": 44.5,
        "Lon": 11.3, "Speed[km/h]": 30.0, "x_m": x, "y_m": y,
        "cum_distance_m": s - start, "use_for_route_mapping": True,
        "qc_coord_missing": False,
    })
    resampled = pd.DataFrame({
        "distance_along_track_m": s - start, "timestamp_interpolated": time,
        "longitude": 11.3, "latitude": 44.5, "x_m": x, "y_m": y,
        "direction_bearing": 0.0, "source_point_before": np.arange(len(s)),
        "source_point_after": np.arange(len(s)), "interpolation_fraction": 0.0,
        "campaign_id": campaign, "campaign_part_id": 1,
    })
    return PartTrack(campaign, 1, points, resampled)


def test_track_key_invalidates_raw_config_crs_algorithm_and_dependencies(tmp_path, monkeypatch):
    import meteotracker_qc.repeated_routes.cache as cache_mod

    raw = tmp_path / "raw.csv"
    standardized = tmp_path / "standardized.parquet"
    qc = tmp_path / "qc.yaml"
    raw.write_bytes(b"raw-a")
    standardized.write_bytes(b"parquet-a")
    qc.write_bytes(b"qc-a")
    cfg = RepeatedRoutesConfig()

    def key(config=cfg):
        return stable_hash(track_metadata(
            campaign_id="c1", source_file="c1.csv", raw_path=raw,
            standardized_path=standardized, qc_config_path=qc, rr_config=config,
        ))

    baseline = key()
    raw.write_bytes(b"raw-b")
    assert key() != baseline
    raw.write_bytes(b"raw-a")
    qc.write_bytes(b"qc-b")
    assert key() != baseline
    qc.write_bytes(b"qc-a")
    assert key(dataclasses.replace(cfg, crs_metric_epsg=32633)) != baseline
    assert key(dataclasses.replace(cfg, resampling_distance_m=5.0)) != baseline
    monkeypatch.setattr(cache_mod, "TRACK_ALGORITHM_VERSION", "track-v-next")
    assert key() != baseline
    monkeypatch.setattr(cache_mod, "TRACK_ALGORITHM_VERSION", "track-v1")
    monkeypatch.setattr(cache_mod, "CACHE_SCHEMA_VERSION", 999)
    assert key() != baseline
    monkeypatch.setattr(cache_mod, "CACHE_SCHEMA_VERSION", 2)
    monkeypatch.setattr(cache_mod, "geometry_dependency_versions", lambda: {"shapely": "next"})
    assert key() != baseline


def test_progressive_pair_cache_reuses_old_old_and_matches_full(tmp_path):
    cfg = RepeatedRoutesConfig()
    a, b, c = _part("a", 0), _part("b", 2), _part("c", -2)
    old = [a, b]
    all_parts = [a, b, c]
    keys = {"a": "ka", "b": "kb", "c": "kc"}

    old_candidates, _ = build_candidate_pairs(old, cfg)
    stats1 = {"pair_hits": 0, "pair_misses": 0}
    match_candidate_pairs(old_candidates, {p.track_id: p for p in old}, keys, cfg,
                          cache_dir=tmp_path, cache_stats=stats1)
    assert stats1 == {"pair_hits": 0, "pair_misses": 1}

    candidates, _ = build_candidate_pairs(all_parts, cfg)
    stats2 = {"pair_hits": 0, "pair_misses": 0}
    incremental = match_candidate_pairs(candidates, {p.track_id: p for p in all_parts}, keys, cfg,
                                        cache_dir=tmp_path, cache_stats=stats2)
    assert stats2 == {"pair_hits": 1, "pair_misses": 2}

    full = match_candidate_pairs(candidates, {p.track_id: p for p in all_parts}, keys, cfg,
                                 cache_dir=None, full_rebuild=True)
    assert incremental == full
    stats3 = {"pair_hits": 0, "pair_misses": 0}
    repeated = match_candidate_pairs(candidates, {p.track_id: p for p in all_parts}, keys, cfg,
                                     cache_dir=tmp_path, cache_stats=stats3)
    assert repeated == full
    assert stats3 == {"pair_hits": 3, "pair_misses": 0}


def test_pair_key_invalidates_part_config_and_algorithm(monkeypatch):
    import meteotracker_qc.repeated_routes.cache as cache_mod

    cfg = RepeatedRoutesConfig()
    a, b = _part("a"), _part("b", 2)
    baseline = stable_hash(pair_metadata(a, "ka", b, "kb", cfg))
    assert stable_hash(pair_metadata(a, "ka-changed", b, "kb", cfg)) != baseline
    b.campaign_part_id = 2
    assert stable_hash(pair_metadata(a, "ka", b, "kb", cfg)) != baseline
    b.campaign_part_id = 1
    assert stable_hash(pair_metadata(a, "ka", b, "kb", dataclasses.replace(cfg, matching_tolerance_m=10))) != baseline
    monkeypatch.setattr(cache_mod, "PAIR_ALGORITHM_VERSION", "pair-v-next")
    assert stable_hash(pair_metadata(a, "ka", b, "kb", cfg)) != baseline


def test_corrupt_pair_cache_is_safe_miss(tmp_path):
    cfg = RepeatedRoutesConfig()
    a, b = _part("a", 0), _part("b", 2)
    keys = {"a": "ka", "b": "kb"}
    candidates, _ = build_candidate_pairs([a, b], cfg)
    parts = {a.track_id: a, b.track_id: b}
    match_candidate_pairs(candidates, parts, keys, cfg, cache_dir=tmp_path)
    pair_path = tmp_path / "pairs.sqlite3"
    pair_path.write_bytes(b"not-json")
    stats = {"pair_hits": 0, "pair_misses": 0}
    recovered = match_candidate_pairs(candidates, parts, keys, cfg, cache_dir=tmp_path, cache_stats=stats)
    assert recovered
    assert stats == {"pair_hits": 0, "pair_misses": 1}


def test_corrupt_track_cache_is_safe_miss(tmp_path):
    cache = RepeatedRoutesCache(tmp_path)
    metadata = {"schema_version": 2, "kind": "campaign-track", "campaign_id": "c"}
    key = stable_hash(metadata)
    cache.save_track(key, metadata, {"value": 1})
    (tmp_path / "tracks" / f"{key}.pickle").write_bytes(b"broken")
    loaded_key, payload = cache.load_track(metadata)
    assert loaded_key == key
    assert payload is None


def test_new_campaign_can_join_historical_components_without_orphans():
    cfg = RepeatedRoutesConfig(minimum_shared_length_m=100.0, minimum_consecutive_matches=5)
    parts = {p.track_id: p for p in [_part("a"), _part("b", 2), _part("c", -2), _part("d", 3), _part("new", 1)]}
    base = {
        "a_start_m": 0.0, "a_end_m": 500.0, "b_start_m": 0.0, "b_end_m": 500.0,
        "shared_length_m": 500.0, "overlap_fraction": 1.0, "direction_class": "same_direction",
        "direction_correlation": 1.0, "bearing_diff_deg": 0.0, "mean_matching_distance_m": 2.0,
        "p90_matching_distance_m": 2.0, "n_matched_points_a": 51, "n_matched_points_b": 51,
    }
    def match(a, b):
        return {**base, "track_id_a": f"{a}::part1", "track_id_b": f"{b}::part1"}
    historical = [match("a", "b"), match("c", "d")]
    std = {p.campaign_id: p.points for p in parts.values()}
    before, _, _ = consolidate_segments(parts, historical, std, cfg)
    after, passages, matches = consolidate_segments(
        parts, historical + [match("a", "new"), match("c", "new")], std, cfg,
    )
    assert len(before) == 2
    assert len(after) == 1
    assert set(passages["repeated_segment_id"]) == set(after["repeated_segment_id"])
    assert set(matches["repeated_segment_id"].dropna()) <= set(after["repeated_segment_id"])
    assert passages.groupby("repeated_segment_id")["campaign_id"].nunique().iloc[0] == 5
