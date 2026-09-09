"""Consolidate compatible corridor evidence without consuming overlapping passages."""
from __future__ import annotations

from collections import defaultdict

import hashlib

import numpy as np
from scipy.stats import spearmanr
import pandas as pd
from shapely.geometry import LineString

from .config import RepeatedRoutesConfig
from .corridors import canonical_matches, corridor_groups
from .matching import project_onto_line
from .timebins import classify_time_bin, hour_decimal
from .tracks import PartTrack, valid_geometry_mask


def _quality_flag(mean_distance_m: float, cfg: RepeatedRoutesConfig) -> str:
    if not np.isfinite(mean_distance_m):
        return "low"
    if mean_distance_m <= cfg.segment_quality_distance_high_m:
        return "high"
    if mean_distance_m <= cfg.segment_quality_distance_medium_m:
        return "medium"
    return "low"


def _slice(df: pd.DataFrame, col: str, lo: float, hi: float) -> pd.DataFrame:
    return df[(df[col] >= lo) & (df[col] <= hi)]


SEGMENT_COLUMNS = [
    "repeated_segment_id", "segment_length_m", "n_passages", "n_campaigns", "n_distinct_dates",
    "n_same_direction", "n_opposite_direction", "first_datetime", "last_datetime",
    "mean_matching_distance_m", "p90_matching_distance_m", "mean_overlap_fraction",
    "matching_quality", "reference_track_id", "geometry", "corridor_id",
]

PASSAGE_COLUMNS = [
    "repeated_segment_id", "campaign_id", "campaign_part_id", "track_id", "passage_id", "date", "time_bin",
    "passage_start_datetime", "passage_end_datetime", "duration_seconds", "direction_class",
    "mean_speed_kmh", "median_speed_kmh", "n_original_points", "n_resampled_points", "valid_fraction",
    "shared_length_m", "overlap_fraction", "mean_distance_from_reference_m", "p90_distance_from_reference_m",
    "passage_quality_flag", "is_reference", "geometry",
    "track_part_id", "segment_passage_id", "track_start_m", "track_end_m",
    "normalized_direction", "reference_start_m", "reference_end_m",
]


def consolidate_segments(
    parts_by_track: dict[str, PartTrack],
    pairwise_matches: list[dict],
    standardized_by_campaign: dict[str, pd.DataFrame],
    cfg: RepeatedRoutesConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pairwise_matches = canonical_matches(pairwise_matches)
    if not pairwise_matches:
        empty_matches = pd.DataFrame(columns=list(pairwise_matches and pairwise_matches[0].keys() or []) + ["repeated_segment_id", "geometry"])
        return pd.DataFrame(columns=SEGMENT_COLUMNS), pd.DataFrame(columns=PASSAGE_COLUMNS), empty_matches

    run_instances = []
    for m_idx, m in enumerate(pairwise_matches):
        run_instances.append({"track_id": m["track_id_a"], "s_start": m["a_start_m"], "s_end": m["a_end_m"], "match_idx": m_idx})
        run_instances.append({"track_id": m["track_id_b"], "s_start": m["b_start_m"], "s_end": m["b_end_m"], "match_idx": m_idx})

    groups = corridor_groups(parts_by_track, pairwise_matches, cfg)
    components = {i: [2*m+side for m in group for side in (0,1)] for i,group in enumerate(groups)}

    segment_rows = []
    passage_rows = []
    match_to_segments: dict[int, set[str]] = {i: set() for i in range(len(pairwise_matches))}
    seg_counter = 0

    for member_idxs in components.values():
        track_intervals: dict[str, list] = defaultdict(lambda: [np.inf, -np.inf, []])
        for idx in member_idxs:
            ri = run_instances[idx]
            entry = track_intervals[ri["track_id"]]
            entry[0] = min(entry[0], ri["s_start"])
            entry[1] = max(entry[1], ri["s_end"])
            entry[2].append(ri["match_idx"])

        if len(track_intervals) < 2:
            continue

        ref_track_id, (ref_start, ref_end, _ref_matches) = max(
            track_intervals.items(), key=lambda kv: (kv[1][1] - kv[1][0], kv[0])
        )
        ref_part = parts_by_track[ref_track_id]
        ref_slice = _slice(ref_part.resampled, "distance_along_track_m", ref_start, ref_end)
        if len(ref_slice) < 2:
            continue
        ref_line = LineString(list(zip(ref_slice["x_m"], ref_slice["y_m"])))

        seg_counter += 1
        repeated_segment_id = f"seg_{seg_counter:04d}"

        passages_for_segment = []
        for track_id, (s_start, s_end, match_idxs) in sorted(track_intervals.items()):
            match_idxs = sorted(set(match_idxs))
            part = parts_by_track[track_id]
            r_slice = _slice(part.resampled, "distance_along_track_m", s_start, s_end)
            if len(r_slice) < 2:
                continue

            if track_id == ref_track_id:
                dist_to_ref = np.zeros(len(r_slice))
            else:
                dist_to_ref, _ = project_onto_line(ref_line, r_slice["x_m"].to_numpy(), r_slice["y_m"].to_numpy())

            p_slice = _slice(part.points, "cum_distance_m", s_start, s_end)

            _, projected = project_onto_line(ref_line, r_slice["x_m"].to_numpy(), r_slice["y_m"].to_numpy())
            reference_forward = tuple(ref_line.coords[0]) <= tuple(ref_line.coords[-1])
            forward = projected[-1] >= projected[0]
            normalized_direction = "same_direction" if forward == reference_forward else "opposite_direction"
            direction_class = "same_direction" if forward else "opposite_direction"
            if len(projected)>2:
                corr=float(spearmanr(np.arange(len(projected)),projected).statistic)
                if not np.isfinite(corr) or abs(corr)<cfg.direction_correlation_threshold:
                    direction_class = normalized_direction = "direction_uncertain"

            start_ts = r_slice["timestamp_interpolated"].min()
            end_ts = r_slice["timestamp_interpolated"].max()
            start_ts_local = start_ts.tz_convert("Europe/Rome") if pd.notna(start_ts) else None
            end_ts_local = end_ts.tz_convert("Europe/Rome") if pd.notna(end_ts) else None
            duration_s = (end_ts - start_ts).total_seconds() if pd.notna(start_ts) and pd.notna(end_ts) else np.nan

            speed = pd.to_numeric(p_slice.get("Speed[km/h]"), errors="coerce").dropna() if not p_slice.empty else pd.Series(dtype=float)

            campaign_id = part.campaign_id
            std_df = standardized_by_campaign.get(campaign_id)
            if std_df is not None and pd.notna(start_ts) and pd.notna(end_ts):
                window = std_df[(std_df["time_utc"] >= start_ts) & (std_df["time_utc"] <= end_ts)]
                valid_fraction = float(valid_geometry_mask(window, cfg).mean()) if not window.empty else np.nan
            else:
                valid_fraction = np.nan

            mean_dist_ref = float(np.mean(dist_to_ref)) if len(dist_to_ref) else np.nan
            p90_dist_ref = float(np.percentile(dist_to_ref, 90)) if len(dist_to_ref) else np.nan

            passages_for_segment.append({
                "repeated_segment_id": repeated_segment_id,
                "campaign_id": campaign_id,
                "campaign_part_id": part.campaign_part_id,
                "track_id": track_id,
                "passage_id": f"{repeated_segment_id}__{track_id}",
                "date": start_ts_local.date().isoformat() if start_ts_local is not None else None,
                "time_bin": classify_time_bin(hour_decimal(start_ts_local), cfg) if start_ts_local is not None else None,
                "passage_start_datetime": start_ts_local.isoformat() if start_ts_local is not None else None,
                "passage_end_datetime": end_ts_local.isoformat() if end_ts_local is not None else None,
                "duration_seconds": duration_s,
                "direction_class": direction_class,
                "mean_speed_kmh": float(speed.mean()) if not speed.empty else np.nan,
                "median_speed_kmh": float(speed.median()) if not speed.empty else np.nan,
                "n_original_points": int(len(p_slice)),
                "n_resampled_points": int(len(r_slice)),
                "valid_fraction": valid_fraction,
                "shared_length_m": float(s_end - s_start),
                "overlap_fraction": float(np.mean([pairwise_matches[mi]["overlap_fraction"] for mi in match_idxs])),
                "mean_distance_from_reference_m": mean_dist_ref,
                "p90_distance_from_reference_m": p90_dist_ref,
                "passage_quality_flag": _quality_flag(mean_dist_ref, cfg),
                "is_reference": track_id == ref_track_id,
                "track_part_id": track_id,
                "segment_passage_id": f"{repeated_segment_id}__{track_id}",
                "track_start_m": s_start, "track_end_m": s_end,
                "normalized_direction": normalized_direction,
                "reference_start_m": ref_start, "reference_end_m": ref_end,
                "geometry": LineString(list(zip(r_slice["longitude"], r_slice["latitude"]))),
                "_start_ts_local": start_ts_local,
                "_end_ts_local": end_ts_local,
            })

        if len(passages_for_segment) < 2:
            seg_counter -= 1
            continue

        for idx in member_idxs:
            match_to_segments[run_instances[idx]["match_idx"]].add(repeated_segment_id)

        starts = [p["_start_ts_local"] for p in passages_for_segment if p["_start_ts_local"] is not None]
        ends = [p["_end_ts_local"] for p in passages_for_segment if p["_end_ts_local"] is not None]
        dists = [p["mean_distance_from_reference_m"] for p in passages_for_segment if np.isfinite(p["mean_distance_from_reference_m"])]
        p90s = [p["p90_distance_from_reference_m"] for p in passages_for_segment if np.isfinite(p["p90_distance_from_reference_m"])]
        overlaps = [p["overlap_fraction"] for p in passages_for_segment]
        campaigns = {p["campaign_id"] for p in passages_for_segment}
        dates = {p["date"] for p in passages_for_segment if p["date"]}
        n_same = sum(1 for p in passages_for_segment if p["direction_class"] == "same_direction")
        n_opp = sum(1 for p in passages_for_segment if p["direction_class"] == "opposite_direction")
        mean_dist = float(np.mean(dists)) if dists else np.nan

        normalized_coords = tuple(ref_line.coords)
        normalized_coords = min(normalized_coords, tuple(reversed(normalized_coords)))
        corridor_id = "corridor_" + hashlib.sha256(repr(normalized_coords).encode()).hexdigest()[:20]
        segment_rows.append({
            "repeated_segment_id": repeated_segment_id,
            "segment_length_m": float(ref_end - ref_start),
            "n_passages": len(passages_for_segment),
            "n_campaigns": len(campaigns),
            "n_distinct_dates": len(dates),
            "n_same_direction": n_same,
            "n_opposite_direction": n_opp,
            "first_datetime": min(starts).isoformat() if starts else None,
            "last_datetime": max(ends).isoformat() if ends else None,
            "mean_matching_distance_m": mean_dist,
            "p90_matching_distance_m": float(np.mean(p90s)) if p90s else np.nan,
            "mean_overlap_fraction": float(np.mean(overlaps)) if overlaps else np.nan,
            "matching_quality": _quality_flag(mean_dist, cfg),
            "reference_track_id": ref_track_id,
            "corridor_id": corridor_id,
            "geometry": LineString(list(zip(ref_slice["longitude"], ref_slice["latitude"]))),
        })
        for p in passages_for_segment:
            p.pop("_start_ts_local", None)
            p.pop("_end_ts_local", None)
        passage_rows.extend(passages_for_segment)

    segments_df = pd.DataFrame(segment_rows, columns=SEGMENT_COLUMNS)
    passages_df = pd.DataFrame(passage_rows, columns=PASSAGE_COLUMNS)

    matches_out = []
    for m_idx, m in enumerate(pairwise_matches):
        part_a = parts_by_track[m["track_id_a"]]
        line_slice = _slice(part_a.resampled, "distance_along_track_m", m["a_start_m"], m["a_end_m"])
        geom = LineString(list(zip(line_slice["longitude"], line_slice["latitude"]))) if len(line_slice) >= 2 else None
        for segment_id in sorted(match_to_segments[m_idx]) or [None]:
            row = dict(m)
            row["repeated_segment_id"] = segment_id
            row["geometry"] = geom
            matches_out.append(row)
    matches_df = pd.DataFrame(matches_out)

    return segments_df, passages_df, matches_df
