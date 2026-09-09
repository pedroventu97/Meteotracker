"""Pairwise sub-track matching (sections 7-9 of the spec).

Operates purely on resampled-track dataframes (metric x_m/y_m + arc-length
distance_along_track_m + direction_bearing) so it is independent of how the
tracks were produced -- this keeps it directly unit-testable on synthetic data.

Method (transparent, geometric, no map matching):
1. Project every resampled point of track A onto track B's polyline (and
   separately B onto A) -- perpendicular distance + arc-length position.
2. Points within ``matching_tolerance_m`` are "matched"; consecutive matched
   points form a run, bridging internal gaps up to ``maximum_internal_gap_m``.
3. A run must be long enough (``minimum_shared_length_m``,
   ``minimum_consecutive_matches``), must have an independently-detected
   reciprocal run on the other track covering the same span (mutual
   verification), and its along-A vs along-B span lengths must agree within
   ``minimum_overlap_fraction``.
4. Direction is classified from the sign/strength of the Spearman correlation
   between along-A and along-B position, corroborated by the circular
   difference between the two runs' mean bearings.
"""
from __future__ import annotations

import dataclasses
import json

import numpy as np
import pandas as pd
from scipy import stats
from shapely.geometry import LineString, Point

from .config import RepeatedRoutesConfig


def circular_bearing_diff(b1: float, b2: float) -> float:
    d = abs(b1 - b2) % 360
    return d if d <= 180 else 360 - d


def circular_mean_bearing(bearings: np.ndarray) -> float:
    b = bearings[np.isfinite(bearings)]
    if len(b) == 0:
        return float("nan")
    rad = np.radians(b)
    return float(np.degrees(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) % 360)


def project_onto_line(line: LineString, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Perpendicular distance and arc-length position of each (x,y) onto ``line``."""
    dist = np.empty(len(xs))
    arc = np.empty(len(xs))
    for i in range(len(xs)):
        p = Point(xs[i], ys[i])
        dist[i] = line.distance(p)
        arc[i] = line.project(p)
    return dist, arc


def contiguous_runs(matched: np.ndarray) -> list[tuple[int, int]]:
    runs = []
    start = None
    for i, m in enumerate(matched):
        if m and start is None:
            start = i
        elif not m and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(matched) - 1))
    return runs


def bridge_runs(runs: list[tuple[int, int]], s: np.ndarray, max_gap_m: float) -> list[tuple[int, int]]:
    if not runs:
        return runs
    merged = [runs[0]]
    for r in runs[1:]:
        prev = merged[-1]
        if s[r[0]] - s[prev[1]] <= max_gap_m:
            merged[-1] = (prev[0], r[1])
        else:
            merged.append(r)
    return merged


def _direction_from_correlation(corr: float, cfg: RepeatedRoutesConfig) -> str:
    if not np.isfinite(corr) or abs(corr) < cfg.direction_correlation_threshold:
        return "direction_uncertain"
    return "same_direction" if corr > 0 else "opposite_direction"


def _direction_from_bearing(bearing_diff: float, cfg: RepeatedRoutesConfig) -> str:
    if bearing_diff <= cfg.bearing_same_direction_max_deg:
        return "same_direction"
    if bearing_diff >= cfg.bearing_opposite_direction_min_deg:
        return "opposite_direction"
    return "direction_uncertain"


def _combine_direction(corr_dir: str, bearing_dir: str) -> str:
    if corr_dir == bearing_dir:
        return corr_dir
    if corr_dir == "direction_uncertain":
        return bearing_dir
    if bearing_dir == "direction_uncertain":
        return corr_dir
    return "direction_uncertain"  # the two signals disagree outright


@dataclasses.dataclass
class RunResult:
    from_start_idx: int
    from_end_idx: int
    to_start_s: float
    to_end_s: float
    s_from_matched: np.ndarray
    s_to_matched: np.ndarray
    dist_matched: np.ndarray


def find_runs(resampled_from: pd.DataFrame, line_to: LineString, cfg: RepeatedRoutesConfig) -> list[RunResult]:
    xs = resampled_from["x_m"].to_numpy()
    ys = resampled_from["y_m"].to_numpy()
    s = resampled_from["distance_along_track_m"].to_numpy()
    if len(xs) == 0:
        return []
    dist, arc = project_onto_line(line_to, xs, ys)
    matched = dist <= cfg.matching_tolerance_m

    raw_runs = contiguous_runs(matched)
    runs = bridge_runs(raw_runs, s, cfg.maximum_internal_gap_m)

    results = []
    for start, end in runs:
        n_matched = int(matched[start:end + 1].sum())
        length = float(s[end] - s[start])
        if n_matched < cfg.minimum_consecutive_matches or length < cfg.minimum_shared_length_m:
            continue
        idx = np.arange(start, end + 1)
        matched_idx = idx[matched[start:end + 1]]
        results.append(RunResult(
            from_start_idx=start, from_end_idx=end,
            to_start_s=float(np.min(arc[matched_idx])), to_end_s=float(np.max(arc[matched_idx])),
            s_from_matched=s[matched_idx], s_to_matched=arc[matched_idx],
            dist_matched=dist[matched_idx],
        ))
    return results


def _run_bearing(df: pd.DataFrame, start: int, end: int) -> float:
    return circular_mean_bearing(df["direction_bearing"].iloc[start:end + 1].to_numpy(dtype=float))


def match_tracks(
    track_id_a: str, resampled_a: pd.DataFrame,
    track_id_b: str, resampled_b: pd.DataFrame,
    cfg: RepeatedRoutesConfig,
) -> list[dict]:
    """Return reconciled shared-segment candidates between two resampled tracks."""
    if len(resampled_a) < 2 or len(resampled_b) < 2:
        return []
    line_a = LineString(list(zip(resampled_a["x_m"], resampled_a["y_m"])))
    line_b = LineString(list(zip(resampled_b["x_m"], resampled_b["y_m"])))
    if line_a.length == 0 or line_b.length == 0:
        return []

    runs_a = find_runs(resampled_a, line_b, cfg)
    runs_b = find_runs(resampled_b, line_a, cfg)

    matches: list[dict] = []
    for ra in runs_a:
        a_start = float(resampled_a["distance_along_track_m"].iloc[ra.from_start_idx])
        a_end = float(resampled_a["distance_along_track_m"].iloc[ra.from_end_idx])
        a_length = a_end - a_start
        b_span_lo, b_span_hi = min(ra.to_start_s, ra.to_end_s), max(ra.to_start_s, ra.to_end_s)
        b_length = b_span_hi - b_span_lo
        if max(a_length, b_length) <= 0:
            continue
        overlap_fraction = min(a_length, b_length) / max(a_length, b_length)

        if overlap_fraction < cfg.minimum_overlap_fraction:
            continue
        for reciprocal in runs_b:
            rb_lo, rb_hi = sorted((reciprocal.to_start_s, reciprocal.to_end_s))
            overlap_len = min(a_end, rb_hi) - max(a_start, rb_lo)
            if overlap_len <= 0 or overlap_len / a_length < cfg.reciprocal_overlap_min_fraction:
                continue
            # Reuse reciprocal evidence, but only its intersection with this run's
            # projected interval belongs to this particular passage.
            b_s = resampled_b["distance_along_track_m"].to_numpy()
            b_lo = max(b_span_lo, float(b_s[reciprocal.from_start_idx]))
            b_hi = min(b_span_hi, float(b_s[reciprocal.from_end_idx]))
            if b_hi - b_lo < cfg.minimum_shared_length_m:
                continue
            # Cropping reciprocal evidence changes the emitted span: apply the
            # existing overlap threshold to those actual intervals as well.
            emitted_overlap = min(a_length, b_hi - b_lo) / max(a_length, b_hi - b_lo)
            if emitted_overlap < cfg.minimum_overlap_fraction:
                continue
            if len(ra.s_from_matched) >= 3:
                corr, _ = stats.spearmanr(ra.s_from_matched, ra.s_to_matched)
            else:
                corr = float("nan")
            corr_dir = _direction_from_correlation(corr, cfg)

            bearing_a = _run_bearing(resampled_a, ra.from_start_idx, ra.from_end_idx)
            b_start_idx = int(np.searchsorted(b_s, b_lo, side="left"))
            b_end_idx = int(np.searchsorted(b_s, b_hi, side="right") - 1)
            bearing_b = _run_bearing(resampled_b, b_start_idx, b_end_idx)
            if np.isfinite(bearing_a) and np.isfinite(bearing_b):
                bearing_diff = circular_bearing_diff(bearing_a, bearing_b)
                bearing_dir = _direction_from_bearing(bearing_diff, cfg)
            else:
                bearing_diff = float("nan")
                bearing_dir = "direction_uncertain"

            direction_class = _combine_direction(corr_dir, bearing_dir)

            b_start_m = b_lo
            b_end_m = b_hi
            reciprocal_mask = (reciprocal.s_from_matched >= b_lo) & (reciprocal.s_from_matched <= b_hi)
            reciprocal_dist = reciprocal.dist_matched[reciprocal_mask]
            all_dist = np.concatenate([ra.dist_matched, reciprocal_dist])

            matches.append({
                "track_id_a": track_id_a, "track_id_b": track_id_b,
                "a_start_m": min(a_start, a_end), "a_end_m": max(a_start, a_end),
                "b_start_m": min(b_start_m, b_end_m), "b_end_m": max(b_start_m, b_end_m),
                "shared_length_m": float(min(a_length, b_hi - b_lo)),
                "overlap_fraction": float(emitted_overlap),
                "direction_class": direction_class,
                "direction_correlation": float(corr) if np.isfinite(corr) else None,
                "bearing_diff_deg": float(bearing_diff) if np.isfinite(bearing_diff) else None,
                "mean_matching_distance_m": float(np.mean(all_dist)),
                "p90_matching_distance_m": float(np.percentile(all_dist, 90)),
                "n_matched_points_a": int(len(ra.s_from_matched)),
                "n_matched_points_b": int(reciprocal_mask.sum()),
            })
    # Identical interval evidence is one semantic match, regardless of discovery order.
    unique = {}
    for match in matches:
        key = tuple(match[k] for k in ("track_id_a", "track_id_b", "a_start_m", "a_end_m", "b_start_m", "b_end_m"))
        if key not in unique or json.dumps(match, sort_keys=True) < json.dumps(unique[key], sort_keys=True):
            unique[key] = match
    return [unique[key] for key in sorted(unique)]
