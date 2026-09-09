"""Candidate-pair prefilter (section 6): avoid O(n^2) point-level comparison.

Builds a buffered-polygon spatial index (shapely STRtree, metric CRS) over every
campaign part and only proposes track pairs whose buffered footprints actually
intersect for detailed pairwise matching.
"""
from __future__ import annotations

import pandas as pd
from shapely.geometry import LineString
from shapely.strtree import STRtree

from .config import RepeatedRoutesConfig
from .tracks import PartTrack


def build_candidate_pairs(parts: list[PartTrack], cfg: RepeatedRoutesConfig) -> tuple[pd.DataFrame, dict]:
    # The buffer must never be smaller than the matching tolerance, or the prefilter
    # could discard pairs that pairwise matching would otherwise have accepted.
    buffer_m = max(cfg.candidate_buffer_m, cfg.matching_tolerance_m)
    valid_parts = [p for p in parts if len(p.resampled) >= 2]
    geoms = [
        LineString(list(zip(p.resampled["x_m"], p.resampled["y_m"]))).buffer(buffer_m)
        for p in valid_parts
    ]
    tree = STRtree(geoms)

    rows = []
    seen: set[tuple[str, str]] = set()
    for i, geom in enumerate(geoms):
        part_a = valid_parts[i]
        for j in tree.query(geom, predicate="intersects"):
            j = int(j)
            if j <= i:
                continue
            part_b = valid_parts[j]
            key = (part_a.track_id, part_b.track_id)
            if key in seen:
                continue
            seen.add(key)
            inter_area = float(geom.intersection(geoms[j]).area)
            date_a = part_a.start_time.tz_convert("Europe/Rome").date().isoformat()
            date_b = part_b.start_time.tz_convert("Europe/Rome").date().isoformat()
            rows.append({
                "track_id_a": part_a.track_id, "track_id_b": part_b.track_id,
                "campaign_id_a": part_a.campaign_id, "campaign_id_b": part_b.campaign_id,
                "campaign_part_id_a": part_a.campaign_part_id, "campaign_part_id_b": part_b.campaign_part_id,
                "date_a": date_a, "date_b": date_b, "same_date": date_a == date_b,
                "bbox_overlap": True, "approximate_shared_area_m2": inter_area,
                "candidate_status": "candidate",
            })

    n_total_pairs = len(valid_parts) * (len(valid_parts) - 1) // 2
    n_candidates = len(rows)
    stats = {
        "n_tracks_considered": len(valid_parts),
        "n_total_pairs": n_total_pairs,
        "n_candidate_pairs": n_candidates,
        "n_excluded_by_prefilter": n_total_pairs - n_candidates,
    }
    return pd.DataFrame(rows), stats
