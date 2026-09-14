"""Section D: repeated-location spatial groups + visit construction.

Spatial clustering uses complete-linkage (`scipy.cluster.hierarchy.linkage`,
method="complete") cut at `spatial_radius_m` via `fcluster(..., criterion=
"distance")`. Complete-linkage's merge criterion IS the maximum pairwise
distance between the two sub-clusters being merged, so cutting the dendrogram
at threshold t guarantees every resulting cluster has intra-cluster diameter
<= t by construction -- this is what makes it immune to the single-linkage
"chain effect" (A near B, B near C, A far from C, all three end up together).
`verify_group_diameters` re-checks this post-hoc anyway (defense in depth,
also required explicitly by the spec as a final compactness check).

Grouping additionally excludes points that would inflate groups with
pseudo-replicated or non-revisit observations, even though the same points
may be legitimate temporal_candidate points for other purposes: frozen
coordinates (already excluded upstream by qc_gps_freeze), qc_stop_event
(a real stop is not "passing through"), qc_stationary (near-zero-motion
points), and qc_coord_repeated (GNSS quantization duplicates).
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import ClusterWarning, fcluster, linkage
from scipy.spatial.distance import pdist

from .config import MatchingProfile
from .projection import build_local_transformer, inverse_xy_to_lonlat, project_xy

GROUPING_EXCLUDE_FLAGS = ["qc_stop_event", "qc_stationary", "qc_coord_repeated"]

DEFAULT_MIN_BEARING_DISPLACEMENT_M = 3.0
DEFAULT_MAX_BEARING_LOOKAROUND = 30
SAME_DIRECTION_MAX_DEG = 45.0
OPPOSITE_DIRECTION_MIN_DEG = 135.0


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].fillna(False).astype(bool)


def grouping_eligible_mask(df: pd.DataFrame, candidate_col: str) -> pd.Series:
    mask = df[candidate_col].astype(bool)
    for flag in GROUPING_EXCLUDE_FLAGS:
        mask = mask & ~_bool_col(df, flag)
    return mask


@dataclass
class LinkageResult:
    transformer: object
    xy: np.ndarray
    Z: np.ndarray | None
    idx: pd.Index


def build_linkage(df: pd.DataFrame, mask: pd.Series) -> LinkageResult | None:
    idx = df.index[mask]
    if len(idx) < 2:
        return None
    sub = df.loc[idx]
    transformer = build_local_transformer(sub["canonical_latitude"], sub["canonical_longitude"])
    x, y = project_xy(transformer, sub["canonical_latitude"], sub["canonical_longitude"])
    xy = np.column_stack([x, y])
    # scipy's linkage() heuristically warns when a small observation matrix
    # happens to look symmetric/hollow/non-negative, as if it might actually
    # be a (mistakenly passed) precomputed distance matrix. Our input is
    # always genuine (x, y) coordinates from project_xy, never a distance
    # matrix, so this specific warning is a known false positive at small N
    # and is safe to suppress here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ClusterWarning)
        Z = linkage(xy, method="complete")
    return LinkageResult(transformer=transformer, xy=xy, Z=Z, idx=idx)


def cut_groups(link: LinkageResult, radius_m: float) -> pd.Series:
    """Cluster labels (int, 1-indexed) as a Series indexed like link.idx."""
    labels = fcluster(link.Z, t=radius_m, criterion="distance")
    return pd.Series(labels, index=link.idx, name="repeated_location_group_id")


def verify_group_diameters(link: LinkageResult, labels: pd.Series) -> dict[int, float]:
    diam: dict[int, float] = {}
    label_arr = labels.to_numpy()
    for g in np.unique(label_arr):
        pos = np.where(label_arr == g)[0]
        if len(pos) < 2:
            diam[int(g)] = 0.0
            continue
        diam[int(g)] = float(pdist(link.xy[pos]).max())
    return diam


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _circular_mean_deg(angles_deg: list[float]) -> float:
    rad = np.radians(angles_deg)
    s, c = np.mean(np.sin(rad)), np.mean(np.cos(rad))
    return float((np.degrees(np.arctan2(s, c)) + 360.0) % 360.0)


def _search_context_point(segment_ids: np.ndarray, lats: np.ndarray, lons: np.ndarray, boundary_pos: int,
                           step: int, min_displacement_m: float, max_lookaround: int) -> tuple[float, float] | None:
    """Walk `step` (+1 or -1) positions away from boundary_pos within the same
    segment, looking for a point at least min_displacement_m away, to use as
    the outward reference for bearing estimation.
    """
    seg = segment_ids[boundary_pos]
    lat0, lon0 = lats[boundary_pos], lons[boundary_pos]
    n = len(segment_ids)
    pos = boundary_pos + step
    steps = 0
    while 0 <= pos < n and steps < max_lookaround:
        if segment_ids[pos] != seg:
            return None
        if not (np.isnan(lats[pos]) or np.isnan(lons[pos])):
            d = _haversine_m(lat0, lon0, lats[pos], lons[pos])
            if d >= min_displacement_m:
                return float(lats[pos]), float(lons[pos])
        pos += step
        steps += 1
    return None


def estimate_visit_bearing(full_segment_ids: np.ndarray, full_lats: np.ndarray, full_lons: np.ndarray,
                            visit_first_pos: int, visit_last_pos: int,
                            min_displacement_m: float = DEFAULT_MIN_BEARING_DISPLACEMENT_M,
                            max_lookaround: int = DEFAULT_MAX_BEARING_LOOKAROUND) -> float:
    """Returns a bearing in degrees, or NaN if not estimable (too few context
    points, insufficient displacement, or a segment/campaign boundary right
    at the visit's edge).
    """
    entry = _search_context_point(full_segment_ids, full_lats, full_lons, visit_first_pos,
                                   step=-1, min_displacement_m=min_displacement_m, max_lookaround=max_lookaround)
    exitp = _search_context_point(full_segment_ids, full_lats, full_lons, visit_last_pos,
                                   step=+1, min_displacement_m=min_displacement_m, max_lookaround=max_lookaround)
    bearings = []
    if entry is not None:
        bearings.append(_bearing_deg(entry[0], entry[1], full_lats[visit_first_pos], full_lons[visit_first_pos]))
    if exitp is not None:
        bearings.append(_bearing_deg(full_lats[visit_last_pos], full_lons[visit_last_pos], exitp[0], exitp[1]))
    if not bearings:
        return float("nan")
    return _circular_mean_deg(bearings)


def bearing_relation(bearing_a: float, bearing_b: float) -> str:
    if math.isnan(bearing_a) or math.isnan(bearing_b):
        return "unavailable"
    diff = abs(bearing_a - bearing_b) % 360.0
    diff = min(diff, 360.0 - diff)
    if diff <= SAME_DIRECTION_MAX_DEG:
        return "same_direction"
    if diff >= OPPOSITE_DIRECTION_MIN_DEG:
        return "opposite_direction"
    return "unclear"


def _median_timestamp(ts: pd.Series) -> pd.Timestamp:
    """Dtype-agnostic median (never round-trips through int64 nanoseconds --
    real parquet data here is datetime64[us], not [ns], and a hardcoded
    nanosecond assumption silently produced 1970-epoch garbage timestamps).
    """
    sorted_ts = ts.sort_values().reset_index(drop=True)
    n = len(sorted_ts)
    if n % 2 == 1:
        return sorted_ts.iloc[n // 2]
    lower, upper = sorted_ts.iloc[n // 2 - 1], sorted_ts.iloc[n // 2]
    return lower + (upper - lower) / 2


def compute_groups_and_visits(df: pd.DataFrame, candidate_col: str, profile: MatchingProfile) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (groups_df, visits_df, observation_assignment_df). All empty
    (but correctly-columned) if fewer than 2 eligible points exist.
    """
    mask = grouping_eligible_mask(df, candidate_col)
    link = build_linkage(df, mask)
    group_cols = [
        "repeated_location_group_id", "repeated_location_group_centroid_lat",
        "repeated_location_group_centroid_lon", "group_n_points", "group_n_visits",
        "group_diameter_m", "group_valid", "group_warning_codes",
    ]
    visit_cols = [
        "repeated_location_group_id", "repeated_location_visit_id",
        "repeated_location_group_centroid_lat", "repeated_location_group_centroid_lon",
        "distance_to_group_centroid_m", "visit_start_timestamp", "visit_end_timestamp",
        "visit_representative_timestamp", "visit_representative_temperature_c",
        "visit_representative_lat", "visit_representative_lon",
        "visit_n_points", "visit_duration_s", "visit_direction_class", "visit_bearing_deg",
        "visit_segment_ids", "visit_qc_status",
    ]
    obs_cols = ["row_index", "repeated_location_group_id", "repeated_location_visit_id", "distance_to_group_centroid_m"]
    if link is None:
        return (pd.DataFrame(columns=group_cols), pd.DataFrame(columns=visit_cols), pd.DataFrame(columns=obs_cols))

    labels = cut_groups(link, profile.spatial_radius_m)
    diameters = verify_group_diameters(link, labels)

    full_segment_ids = df["segment_id"].to_numpy()
    full_lats = df["canonical_latitude"].to_numpy(dtype=float)
    full_lons = df["canonical_longitude"].to_numpy(dtype=float)
    pos_of_index = {idx_val: pos for pos, idx_val in enumerate(df.index)}

    group_rows, visit_rows, obs_rows = [], [], []
    for group_id, group_idx in labels.groupby(labels).groups.items():
        group_df = df.loc[group_idx].copy()
        group_df["_x"] = link.xy[[link.idx.get_loc(i) for i in group_idx], 0]
        group_df["_y"] = link.xy[[link.idx.get_loc(i) for i in group_idx], 1]
        cx, cy = group_df["_x"].mean(), group_df["_y"].mean()
        centroid_lon, centroid_lat = inverse_xy_to_lonlat(link.transformer, cx, cy)

        group_df = group_df.sort_values("time_utc")
        gaps_s = group_df["time_utc"].diff().dt.total_seconds()
        new_visit = gaps_s.isna() | (gaps_s > profile.visit_merge_gap_s)
        visit_local_id = new_visit.cumsum()

        visit_bearings: dict[int, float] = {}
        first_visit_local_id = None
        for local_id, visit_df in group_df.groupby(visit_local_id):
            first_pos = pos_of_index[visit_df.index[0]]
            last_pos = pos_of_index[visit_df.index[-1]]
            bearing = estimate_visit_bearing(full_segment_ids, full_lats, full_lons, first_pos, last_pos)
            visit_bearings[local_id] = bearing
            if first_visit_local_id is None:
                first_visit_local_id = local_id
        reference_bearing = visit_bearings.get(first_visit_local_id, float("nan"))

        n_visits_in_group = int(visit_local_id.max())
        for local_id, visit_df in group_df.groupby(visit_local_id):
            visit_id = f"{group_id}_{local_id}"
            vx, vy = visit_df["_x"].mean(), visit_df["_y"].mean()
            dist_centroid = float(np.hypot(vx - cx, vy - cy))
            n_points = len(visit_df)
            temp_c = float(visit_df["canonical_temperature_c"].median())
            rep_ts = _median_timestamp(visit_df["time_utc"])
            duration_s = float((visit_df["time_utc"].max() - visit_df["time_utc"].min()).total_seconds())
            seg_ids = ";".join(sorted({str(s) for s in visit_df["segment_id"].unique()}))
            qc_status = "OK" if n_points >= profile.minimum_points_per_visit else "LOW_POINT_COUNT"
            bearing = visit_bearings[local_id]
            direction_class = "unavailable" if local_id == first_visit_local_id else bearing_relation(reference_bearing, bearing)
            if local_id == first_visit_local_id and not math.isnan(bearing):
                direction_class = "same_direction"

            visit_rows.append({
                "repeated_location_group_id": group_id, "repeated_location_visit_id": visit_id,
                "repeated_location_group_centroid_lat": centroid_lat, "repeated_location_group_centroid_lon": centroid_lon,
                "distance_to_group_centroid_m": dist_centroid,
                "visit_start_timestamp": visit_df["time_utc"].min(), "visit_end_timestamp": visit_df["time_utc"].max(),
                "visit_representative_timestamp": rep_ts, "visit_representative_temperature_c": temp_c,
                "visit_representative_lat": float(visit_df["canonical_latitude"].mean()),
                "visit_representative_lon": float(visit_df["canonical_longitude"].mean()),
                "visit_n_points": n_points, "visit_duration_s": duration_s,
                "visit_direction_class": direction_class, "visit_bearing_deg": bearing,
                "visit_segment_ids": seg_ids, "visit_qc_status": qc_status,
            })
            for row_idx in visit_df.index:
                dx = group_df.at[row_idx, "_x"] - cx
                dy = group_df.at[row_idx, "_y"] - cy
                obs_rows.append({
                    "row_index": row_idx, "repeated_location_group_id": group_id,
                    "repeated_location_visit_id": visit_id, "distance_to_group_centroid_m": float(np.hypot(dx, dy)),
                })

        warnings = []
        if diameters.get(group_id, 0.0) > profile.maximum_group_diameter_m + 1e-6:
            warnings.append("LARGE_WITHIN_GROUP_SPREAD")
        direction_classes_seen = {v["visit_direction_class"] for v in visit_rows if v["repeated_location_group_id"] == group_id}
        if {"same_direction", "opposite_direction"} <= direction_classes_seen:
            warnings.append("DIRECTIONAL_CONTEXT_DIFFERENCE")
        if diameters.get(group_id, 0.0) > 0.6 * profile.maximum_group_diameter_m:
            warnings.append("POSSIBLE_DIFFERENT_MICROENVIRONMENT")

        group_rows.append({
            "repeated_location_group_id": group_id, "repeated_location_group_centroid_lat": centroid_lat,
            "repeated_location_group_centroid_lon": centroid_lon, "group_n_points": len(group_idx),
            "group_n_visits": n_visits_in_group, "group_diameter_m": diameters.get(group_id, 0.0),
            "group_valid": n_visits_in_group >= 2, "group_warning_codes": ";".join(warnings),
        })

    return pd.DataFrame(group_rows, columns=group_cols), pd.DataFrame(visit_rows, columns=visit_cols), pd.DataFrame(obs_rows, columns=obs_cols)
