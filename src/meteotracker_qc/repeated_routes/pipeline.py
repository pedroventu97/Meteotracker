"""Phase-1 orchestration: campaign inventory -> tracks -> candidates -> matches -> segments -> outputs."""
from __future__ import annotations

import dataclasses
import logging
import json
import time
from pathlib import Path

import pandas as pd

from . import candidates as candidates_mod
from .cache import RepeatedRoutesCache, pair_metadata, stable_hash, track_metadata
from . import geopackage
from .campaign_inventory import build_campaign_inventory, build_campaign_inventory_row
from .config import RepeatedRoutesConfig
from .dataload import list_canonical_campaigns, load_standardized, refresh_qc_outputs
from .matching import match_tracks
from .memberships import build_point_segment_tables, membership_metrics, MEMBERSHIP_COLUMNS, SUPPORT_COLUMNS
from .scoring import build_comparison_opportunities
from .segments import consolidate_segments
from .tracks import CampaignTracks, PartTrack, prepare_campaign_tracks

REPO_ROOT = Path(__file__).resolve().parents[3]

logger = logging.getLogger("meteotracker_qc.repeated_routes")


def match_candidate_pairs(
    candidate_pairs_df: pd.DataFrame, parts_by_track: dict[str, PartTrack],
    track_cache_keys: dict[str, str], rr_config: RepeatedRoutesConfig,
    *, cache_dir: Path | None = None, full_rebuild: bool = False,
    cache_stats: dict[str, int] | None = None,
) -> list[dict]:
    """Match candidates in dataframe order, safely reusing only exact pair keys."""
    stats = cache_stats if cache_stats is not None else {"pair_hits": 0, "pair_misses": 0}
    cache = RepeatedRoutesCache(cache_dir) if cache_dir is not None else None
    pairwise_matches: list[dict] = []
    try:
        for _, row in candidate_pairs_df.iterrows():
            part_a = parts_by_track[row["track_id_a"]]
            part_b = parts_by_track[row["track_id_b"]]
            matches = None
            pair_key = ""
            metadata = None
            requested_ids = (part_a.track_id, part_b.track_id)
            if cache is not None:
                metadata = pair_metadata(
                    part_a, track_cache_keys[part_a.campaign_id],
                    part_b, track_cache_keys[part_b.campaign_id], rr_config,
                )
                pair_key, matches = cache.load_pair(metadata, requested_ids) if not full_rebuild else (stable_hash(metadata), None)
            if matches is None:
                matches = match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, rr_config)
                stats["pair_misses"] = stats.get("pair_misses", 0) + 1
                if cache is not None and metadata is not None:
                    cache.save_pair(pair_key, metadata, requested_ids, matches)
            else:
                stats["pair_hits"] = stats.get("pair_hits", 0) + 1
            pairwise_matches.extend(matches)
    finally:
        if cache is not None:
            cache.close()
    return pairwise_matches


@dataclasses.dataclass
class PipelineResult:
    inventory_df: pd.DataFrame
    candidate_pairs_df: pd.DataFrame
    candidate_stats: dict
    segments_df: pd.DataFrame
    passages_df: pd.DataFrame
    matches_df: pd.DataFrame
    comparison_df: pd.DataFrame
    campaign_tracks_by_id: dict[str, CampaignTracks]
    standardized_by_campaign: dict[str, pd.DataFrame]
    parts_by_track: dict[str, PartTrack]
    usable_parts: list[PartTrack]
    timings: dict[str, float]
    cache_stats: dict[str, int]
    point_segment_memberships: pd.DataFrame = dataclasses.field(default_factory=lambda: pd.DataFrame(columns=MEMBERSHIP_COLUMNS))
    point_segment_match_support: pd.DataFrame = dataclasses.field(default_factory=lambda: pd.DataFrame(columns=SUPPORT_COLUMNS))
    geographic_epsg: int = 4326


def build_campaign_tracks(
    raw_dir: Path, qc_output_dir: Path, manifest_path: Path, rr_config: RepeatedRoutesConfig,
    *, qc_config_path: Path | None = None, cache_dir: Path | None = None,
    full_rebuild: bool = False, cache_stats: dict[str, int] | None = None,
    track_cache_keys: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, CampaignTracks]]:
    """Load canonical campaigns and build clean/segmented/resampled tracks for each.

    Returns (campaign_inventory_df, standardized_by_campaign, campaign_tracks_by_id).
    Shared by the main pipeline and the sensitivity analysis (which only re-runs the
    matching/consolidation stages on top of these already-built tracks).
    """
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw data directory not found: {raw_dir}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Campaign manifest not found: {manifest_path}")

    sources = list_canonical_campaigns(raw_dir, qc_output_dir, manifest_path)
    if not sources:
        raise RuntimeError(f"No canonical campaigns found via manifest {manifest_path}")

    standardized_by_campaign: dict[str, pd.DataFrame] = {}
    campaign_tracks_by_id: dict[str, CampaignTracks] = {}
    inventory_rows = []
    cache = RepeatedRoutesCache(cache_dir) if cache_dir is not None else None
    stats = cache_stats if cache_stats is not None else {}
    keys = track_cache_keys if track_cache_keys is not None else {}
    for source in sources:
        payload = None
        key = ""
        metadata = None
        if cache is not None:
            if qc_config_path is None:
                raise ValueError("qc_config_path is required when track caching is enabled")
            metadata = track_metadata(
                campaign_id=source.campaign_id, source_file=source.source_file,
                raw_path=raw_dir / source.source_file, standardized_path=source.standardized_path,
                qc_config_path=qc_config_path, rr_config=rr_config,
            )
            key, payload = cache.load_track(metadata) if not full_rebuild else (stable_hash(metadata), None)
        if payload is not None:
            try:
                df = payload["standardized"]
                tracks = payload["tracks"]
                inventory_row = payload["inventory_row"]
                if tracks.campaign_id != source.campaign_id:
                    raise ValueError("campaign mismatch")
                stats["track_hits"] = stats.get("track_hits", 0) + 1
            except (KeyError, AttributeError, TypeError, ValueError):
                payload = None
        if payload is None:
            df = load_standardized(source)
            tracks = prepare_campaign_tracks(source.campaign_id, df, rr_config)
            inventory_row = build_campaign_inventory_row(
                source.campaign_id, source.source_file, df, tracks, rr_config,
            )
            stats["track_misses"] = stats.get("track_misses", 0) + 1
            if cache is not None and metadata is not None:
                cache.save_track(key, metadata, {
                    "standardized": df, "tracks": tracks, "inventory_row": inventory_row,
                })
        keys[source.campaign_id] = key
        standardized_by_campaign[source.campaign_id] = df
        campaign_tracks_by_id[source.campaign_id] = tracks
        inventory_rows.append(inventory_row)

    inventory_df = build_campaign_inventory(inventory_rows)
    return inventory_df, standardized_by_campaign, campaign_tracks_by_id


def run_pipeline(
    *, raw_dir: Path, qc_output_dir: Path, qc_config_path: Path, qc_profile: str,
    manifest_path: Path, rr_config: RepeatedRoutesConfig, refresh_qc: bool = True,
    cache_dir: Path | None = None, full_rebuild: bool = False,
    log: logging.Logger | None = None,
) -> PipelineResult:
    log = log or logger
    timings: dict[str, float] = {}
    cache_stats: dict[str, int] = {"track_hits": 0, "track_misses": 0, "pair_hits": 0, "pair_misses": 0}
    track_cache_keys: dict[str, str] = {}

    t0 = time.perf_counter()
    if refresh_qc:
        log.info("Refreshing QC outputs via meteotracker_qc.pipeline.run_qc (profile=%s)", qc_profile)
        refresh_qc_outputs(raw_dir, qc_output_dir, qc_config_path, manifest_path)
    timings["qc_refresh_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    inventory_df, standardized_by_campaign, campaign_tracks_by_id = build_campaign_tracks(
        raw_dir, qc_output_dir, manifest_path, rr_config, qc_config_path=qc_config_path,
        cache_dir=cache_dir, full_rebuild=full_rebuild, cache_stats=cache_stats,
        track_cache_keys=track_cache_keys,
    )
    timings["load_and_track_build_s"] = time.perf_counter() - t0
    log.info("Loaded %d canonical campaigns", len(campaign_tracks_by_id))

    quality_by_campaign = dict(zip(inventory_df["campaign_id"], inventory_df["campaign_quality_flag"]))
    usable_parts: list[PartTrack] = []
    parts_by_track: dict[str, PartTrack] = {}
    for campaign_id, tracks in campaign_tracks_by_id.items():
        if quality_by_campaign.get(campaign_id) == "excluded":
            continue
        for part in tracks.parts:
            usable_parts.append(part)
            parts_by_track[part.track_id] = part
    n_excluded_campaigns = sum(1 for q in quality_by_campaign.values() if q == "excluded")
    log.info(
        "%d/%d campaigns usable for matching (excluded=%d), %d campaign parts total",
        len(campaign_tracks_by_id) - n_excluded_campaigns, len(campaign_tracks_by_id),
        n_excluded_campaigns, len(usable_parts),
    )

    t0 = time.perf_counter()
    candidate_pairs_df, candidate_stats = candidates_mod.build_candidate_pairs(usable_parts, rr_config)
    timings["candidate_prefilter_s"] = time.perf_counter() - t0
    log.info(
        "Candidate prefilter: %d/%d part pairs kept (%d excluded)",
        candidate_stats["n_candidate_pairs"], candidate_stats["n_total_pairs"], candidate_stats["n_excluded_by_prefilter"],
    )

    t0 = time.perf_counter()
    pairwise_matches = match_candidate_pairs(
        candidate_pairs_df, parts_by_track, track_cache_keys, rr_config,
        cache_dir=cache_dir, full_rebuild=full_rebuild, cache_stats=cache_stats,
    )
    timings["pairwise_matching_s"] = time.perf_counter() - t0
    log.info(
        "Pairwise matching: %d candidate pairs -> %d accepted shared-segment matches",
        len(candidate_pairs_df), len(pairwise_matches),
    )

    t0 = time.perf_counter()
    segments_df, passages_df, matches_df = consolidate_segments(
        parts_by_track, pairwise_matches, standardized_by_campaign, rr_config,
    )
    timings["segment_consolidation_s"] = time.perf_counter() - t0
    log.info("Consolidation: %d repeated segments from %d pairwise matches", len(segments_df), len(pairwise_matches))

    point_segment_memberships, point_segment_match_support = build_point_segment_tables(parts_by_track, passages_df, matches_df, rr_config)

    comparison_df = build_comparison_opportunities(segments_df, passages_df, rr_config)

    if cache_dir is not None:
        RepeatedRoutesCache(cache_dir).write_run_manifest({
            "campaign_ids": list(campaign_tracks_by_id),
            "track_cache_keys": track_cache_keys,
            "cache_stats": cache_stats,
            "full_rebuild": full_rebuild,
        })
    log.info(
        "Cache: tracks hit=%d miss=%d; pairs hit=%d miss=%d",
        cache_stats["track_hits"], cache_stats["track_misses"],
        cache_stats["pair_hits"], cache_stats["pair_misses"],
    )

    return PipelineResult(
        inventory_df=inventory_df, candidate_pairs_df=candidate_pairs_df, candidate_stats=candidate_stats,
        segments_df=segments_df, passages_df=passages_df, matches_df=matches_df, comparison_df=comparison_df,
        campaign_tracks_by_id=campaign_tracks_by_id, standardized_by_campaign=standardized_by_campaign,
        parts_by_track=parts_by_track, usable_parts=usable_parts, timings=timings,
        cache_stats=cache_stats, point_segment_memberships=point_segment_memberships,
        point_segment_match_support=point_segment_match_support,
        geographic_epsg=rr_config.crs_geographic_epsg,
    )


def write_outputs(result: PipelineResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result.inventory_df.to_csv(output_dir / "campaign_inventory.csv", index=False)
    result.candidate_pairs_df.to_csv(output_dir / "candidate_pairs.csv", index=False)
    result.comparison_df.to_csv(output_dir / "comparison_opportunities.csv", index=False)

    result.point_segment_memberships.drop(columns=['geometry'], errors='ignore').to_csv(
        output_dir / 'point_segment_memberships.csv', index=False,
    )
    result.matches_df.reindex(columns=['supporting_match_id','repeated_segment_id']).drop_duplicates().to_csv(
        output_dir / 'pairwise_match_segments.csv', index=False,
    )
    result.point_segment_match_support.to_csv(output_dir / "point_segment_match_support.csv", index=False)
    metrics = membership_metrics(result.point_segment_memberships, result.point_segment_match_support)
    (output_dir / 'membership_summary.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    campaign_tracks_gdf, campaign_parts_gdf, excluded_gdf = geopackage.build_campaign_layers(
        result.campaign_tracks_by_id, result.inventory_df, geographic_epsg=result.geographic_epsg,
    )
    geopackage.write_geopackage(
        output_dir / "repeated_routes.gpkg",
        campaign_tracks_gdf, campaign_parts_gdf, excluded_gdf,
        result.segments_df, result.passages_df, result.matches_df,
        memberships_df=result.point_segment_memberships, geographic_epsg=result.geographic_epsg,
        match_support_df=result.point_segment_match_support,
    )
