"""Track cleaning, campaign-part segmentation, CRS transform and fixed-step resampling.

Implements sections 3-5 of the Phase 1 spec: build one clean, temporally ordered
trajectory per campaign, split it into continuous ``campaign_part_id`` pieces
wherever a gap or an implausible jump would otherwise be bridged by a straight
line, and resample each part at a fixed spatial step for geometric comparison.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
from pyproj import Transformer

from .config import RepeatedRoutesConfig


def _forward_transformer(cfg: RepeatedRoutesConfig) -> Transformer:
    return Transformer.from_crs(f"EPSG:{cfg.crs_geographic_epsg}", f"EPSG:{cfg.crs_metric_epsg}", always_xy=True)


def _inverse_transformer(cfg: RepeatedRoutesConfig) -> Transformer:
    return Transformer.from_crs(f"EPSG:{cfg.crs_metric_epsg}", f"EPSG:{cfg.crs_geographic_epsg}", always_xy=True)


def valid_geometry_mask(df: pd.DataFrame, cfg: RepeatedRoutesConfig) -> pd.Series:
    """The 'recommended' geometry mask: use_for_route_mapping AND non-missing coords.

    use_for_route_mapping (= gps_valid = ~(qc_gps_freeze | qc_gps_jump)) is the column
    the existing pipeline designates for route-mapping use, but it does not by itself
    exclude qc_coord_missing rows (documented gap in reports/targeted_qc_audit.md,
    section C.8). That exclusion is applied here explicitly, without modifying gps_qc.py.
    """
    mask = pd.Series(True, index=df.index)
    if cfg.require_qc_route_mapping:
        mask &= df["use_for_route_mapping"].astype(bool)
    if cfg.exclude_missing_coordinates:
        mask &= ~df["qc_coord_missing"].astype(bool)
    return mask


def clean_and_order(df: pd.DataFrame, cfg: RepeatedRoutesConfig) -> pd.DataFrame:
    """Return valid points, time-ordered, with exact-duplicate timestamps/coords collapsed."""
    mask = valid_geometry_mask(df, cfg) & df["time_utc"].notna()
    columns = ["source_row", "time_utc", "Lat", "Lon", "Speed[km/h]"]
    if "source_file" in df:
        columns.append("source_file")
    valid = df.loc[mask, columns].copy()
    valid = valid.sort_values("time_utc", kind="stable")
    valid = valid.drop_duplicates(subset="time_utc", keep="first")
    lat = valid["Lat"].astype(float).round(7)
    lon = valid["Lon"].astype(float).round(7)
    dup_coord = (lat == lat.shift(1)) & (lon == lon.shift(1))
    valid = valid.loc[~dup_coord.fillna(False)]
    return valid.reset_index(drop=True)


def remove_isolated_gps_outliers(df: pd.DataFrame, cfg: RepeatedRoutesConfig) -> pd.DataFrame:
    """Drop single-point GPS spikes that the upstream QC gps_jump flag misses.

    gps_qc.py only flags a jump if the absolute distance exceeds gps_jump_distance_m
    (80m by default) within gps_jump_dt_s -- a implausible-but-under-80m spike (e.g.
    ~45m in 1s, ~160 km/h in a city campaign) passes through as "valid". Rather than
    letting every such isolated spike fracture a campaign into a spurious new part
    (see reports/repeated_routes_phase1.md, "Limiti"), a point is dropped as an
    outlier only when: (a) reaching it from the previous kept point implies a speed
    above part_split_max_speed_kmh within part_split_jump_dt_s, AND (b) skipping it
    entirely reconnects the previous kept point to the *next* point at a plausible
    speed. Genuine sustained implausible motion (not just one bad point) still
    reaches assign_campaign_parts unchanged and is split into a new part there.
    """
    n = len(df)
    if n < 3:
        return df
    time_col = df["time_utc"].reset_index(drop=True)
    x = df["x_m"].to_numpy()
    y = df["y_m"].to_numpy()
    keep = np.ones(n, dtype=bool)
    prev = 0
    i = 1
    while i < n - 1:
        dt = (time_col.iloc[i] - time_col.iloc[prev]).total_seconds()
        if 0 < dt <= cfg.part_split_jump_dt_s:
            dist = float(np.hypot(x[i] - x[prev], y[i] - y[prev]))
            implied_speed = dist / dt * 3.6
            if implied_speed > cfg.part_split_max_speed_kmh:
                dt2 = (time_col.iloc[i + 1] - time_col.iloc[prev]).total_seconds()
                if 0 < dt2 <= cfg.part_split_jump_dt_s:
                    dist2 = float(np.hypot(x[i + 1] - x[prev], y[i + 1] - y[prev]))
                    if dist2 / dt2 * 3.6 <= cfg.part_split_max_speed_kmh:
                        keep[i] = False
                        i += 1
                        continue
        prev = i
        i += 1
    return df.loc[keep].reset_index(drop=True)


def assign_campaign_parts(df: pd.DataFrame, cfg: RepeatedRoutesConfig) -> pd.DataFrame:
    """Add campaign_part_id, splitting on long temporal gaps or implausible jumps.

    Operates on already-cleaned, time-ordered points with metric x_m/y_m columns.
    """
    n = len(df)
    part_id = np.ones(n, dtype=int)
    if n == 0:
        out = df.copy()
        out["campaign_part_id"] = pd.Series(dtype=int)
        return out
    current = 1
    time_col = df["time_utc"].reset_index(drop=True)
    x = df["x_m"].to_numpy()
    y = df["y_m"].to_numpy()
    for i in range(1, n):
        dt = (time_col.iloc[i] - time_col.iloc[i - 1]).total_seconds()
        new_part = dt > cfg.part_split_time_gap_s
        if not new_part and 0 < dt <= cfg.part_split_jump_dt_s:
            dist = float(np.hypot(x[i] - x[i - 1], y[i] - y[i - 1]))
            implied_speed_kmh = dist / dt * 3.6
            new_part = implied_speed_kmh > cfg.part_split_max_speed_kmh
        if new_part:
            current += 1
        part_id[i] = current
    out = df.copy()
    out["campaign_part_id"] = part_id
    return out


def resample_track(points: pd.DataFrame, cfg: RepeatedRoutesConfig, inverse_transformer: Transformer) -> pd.DataFrame:
    """Resample one continuous part at a fixed spatial step (section 5).

    ``points`` must be time-ordered, deduplicated, with x_m/y_m/cum_distance_m columns.
    Never interpolates across parts -- callers must pass a single campaign_part's points.
    """
    n = len(points)
    if n == 0:
        return pd.DataFrame(columns=[
            "distance_along_track_m", "timestamp_interpolated", "longitude", "latitude",
            "direction_bearing", "source_point_before", "source_point_after", "interpolation_fraction",
        ])

    step = cfg.resampling_distance_m
    total = float(points["cum_distance_m"].iloc[-1])
    if total <= 0:
        targets = [0.0]
    else:
        n_steps = int(total // step)
        targets = [i * step for i in range(n_steps + 1)]
        if targets[-1] < total:
            targets.append(total)

    cum = points["cum_distance_m"].to_numpy()
    x = points["x_m"].to_numpy()
    y = points["y_m"].to_numpy()
    src_row = points["source_row"].to_numpy()
    time_series = points["time_utc"].reset_index(drop=True)

    idx_after = np.searchsorted(cum, targets, side="left")
    idx_after = np.clip(idx_after, 1, max(n - 1, 1))

    rows = []
    for d, j in zip(targets, idx_after):
        i = int(j) - 1
        c0, c1 = cum[i], cum[j]
        frac = (d - c0) / (c1 - c0) if c1 > c0 else 0.0
        frac = min(max(frac, 0.0), 1.0)
        xi = x[i] + frac * (x[j] - x[i])
        yi = y[i] + frac * (y[j] - y[i])
        ti = time_series.iloc[i] + frac * (time_series.iloc[j] - time_series.iloc[i])
        rows.append((d, ti, xi, yi, int(src_row[i]), int(src_row[j]), frac))

    resampled = pd.DataFrame(rows, columns=[
        "distance_along_track_m", "timestamp_interpolated", "x_m", "y_m",
        "source_point_before", "source_point_after", "interpolation_fraction",
    ])

    xs = resampled["x_m"].to_numpy()
    ys = resampled["y_m"].to_numpy()
    bearing = np.full(len(resampled), np.nan)
    if len(resampled) >= 2:
        ddx = np.diff(xs)
        ddy = np.diff(ys)
        b = np.degrees(np.arctan2(ddx, ddy)) % 360
        bearing[:-1] = b
        bearing[-1] = b[-1]
    resampled["direction_bearing"] = bearing

    lon, lat = inverse_transformer.transform(xs, ys)
    resampled["longitude"] = lon
    resampled["latitude"] = lat
    return resampled[[
        "distance_along_track_m", "timestamp_interpolated", "longitude", "latitude", "x_m", "y_m",
        "direction_bearing", "source_point_before", "source_point_after", "interpolation_fraction",
    ]]


@dataclasses.dataclass
class PartTrack:
    campaign_id: str
    campaign_part_id: int
    points: pd.DataFrame  # clean, time-ordered points with x_m/y_m/cum_distance_m
    resampled: pd.DataFrame

    @property
    def total_length_m(self) -> float:
        if self.points.empty:
            return 0.0
        return float(self.points["cum_distance_m"].iloc[-1])

    @property
    def start_time(self) -> pd.Timestamp:
        return self.points["time_utc"].iloc[0]

    @property
    def end_time(self) -> pd.Timestamp:
        return self.points["time_utc"].iloc[-1]

    @property
    def track_id(self) -> str:
        return f"{self.campaign_id}::part{self.campaign_part_id}"


@dataclasses.dataclass
class CampaignTracks:
    campaign_id: str
    parts: list[PartTrack]
    n_valid_points_before_part_filter: int


def prepare_campaign_tracks(campaign_id: str, standardized: pd.DataFrame, cfg: RepeatedRoutesConfig) -> CampaignTracks:
    clean = clean_and_order(standardized, cfg)
    if clean.empty:
        return CampaignTracks(campaign_id=campaign_id, parts=[], n_valid_points_before_part_filter=0)

    fwd = _forward_transformer(cfg)
    inv = _inverse_transformer(cfg)
    x, y = fwd.transform(clean["Lon"].to_numpy(dtype=float), clean["Lat"].to_numpy(dtype=float))
    clean = clean.assign(x_m=x, y_m=y)
    clean = remove_isolated_gps_outliers(clean, cfg)
    clean = assign_campaign_parts(clean, cfg)

    parts: list[PartTrack] = []
    for part_id, group in clean.groupby("campaign_part_id"):
        g = group.sort_values("time_utc", kind="stable").reset_index(drop=True)
        if len(g) < cfg.min_part_points:
            continue
        dx = g["x_m"].diff().fillna(0.0)
        dy = g["y_m"].diff().fillna(0.0)
        step_distance = np.hypot(dx, dy)
        g = g.assign(cum_distance_m=step_distance.cumsum())
        if float(g["cum_distance_m"].iloc[-1]) <= 0:
            continue  # degenerate part: all points coincide, no track to match against
        resampled = resample_track(g, cfg, inv)
        resampled = resampled.assign(campaign_id=campaign_id, campaign_part_id=int(part_id))
        parts.append(PartTrack(campaign_id=campaign_id, campaign_part_id=int(part_id), points=g, resampled=resampled))

    return CampaignTracks(campaign_id=campaign_id, parts=parts, n_valid_points_before_part_filter=len(clean))
