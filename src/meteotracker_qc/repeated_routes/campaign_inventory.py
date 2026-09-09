"""Builds outputs/repeated_routes/campaign_inventory.csv (section 2 of the spec).

One row per canonical campaign. Reuses the QC flags already computed by the
existing pipeline (see tracks.valid_geometry_mask for the exact correspondence)
and the campaign-part geometry built in tracks.py -- no QC logic is reimplemented.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Geod

from .config import RepeatedRoutesConfig
from .timebins import describe_timestamp
from .tracks import CampaignTracks, valid_geometry_mask

GEOD = Geod(ellps="WGS84")


def _raw_distance_km(df: pd.DataFrame) -> float:
    lat = pd.to_numeric(df["Lat"], errors="coerce").to_numpy()
    lon = pd.to_numeric(df["Lon"], errors="coerce").to_numpy()
    if len(lat) < 2:
        return 0.0
    valid = ~np.isnan(lat) & ~np.isnan(lon)
    pair_valid = valid[:-1] & valid[1:]
    if not pair_valid.any():
        return 0.0
    lon1, lat1 = lon[:-1][pair_valid], lat[:-1][pair_valid]
    lon2, lat2 = lon[1:][pair_valid], lat[1:][pair_valid]
    _, _, dist = GEOD.inv(lon1, lat1, lon2, lat2)
    return float(np.sum(dist)) / 1000.0


def classify_campaign_quality(
    *, duration_minutes: float, n_points_valid: int, valid_fraction: float,
    gap_ratio: float, freeze_fraction: float, cfg: RepeatedRoutesConfig,
) -> str:
    if duration_minutes < cfg.min_campaign_duration_minutes_excluded or n_points_valid < cfg.min_campaign_valid_points_excluded:
        return "excluded"
    if (
        valid_fraction >= cfg.quality_valid_fraction_high
        and gap_ratio <= cfg.quality_gap_ratio_high
        and freeze_fraction <= cfg.quality_freeze_fraction_high
    ):
        return "high"
    if (
        valid_fraction >= cfg.quality_valid_fraction_medium
        and gap_ratio <= cfg.quality_gap_ratio_medium
        and freeze_fraction <= cfg.quality_freeze_fraction_medium
    ):
        return "medium"
    return "low"


def build_campaign_inventory_row(
    campaign_id: str, source_file: str, standardized: pd.DataFrame,
    tracks: CampaignTracks, cfg: RepeatedRoutesConfig,
) -> dict:
    n_points_raw = int(len(standardized))
    mask = valid_geometry_mask(standardized, cfg)
    n_points_valid = int(mask.sum())
    valid_fraction = n_points_valid / n_points_raw if n_points_raw else 0.0

    time_valid = standardized["time_utc"].dropna().sort_values()
    if not time_valid.empty:
        start_dt_utc = time_valid.iloc[0]
        end_dt_utc = time_valid.iloc[-1]
        duration_s = float((end_dt_utc - start_dt_utc).total_seconds())
    else:
        start_dt_utc = end_dt_utc = pd.NaT
        duration_s = 0.0
    duration_minutes = duration_s / 60.0

    dt_s = pd.to_numeric(standardized.get("dt_s"), errors="coerce").dropna()
    mean_dt = float(dt_s.mean()) if not dt_s.empty else np.nan
    median_dt = float(dt_s.median()) if not dt_s.empty else np.nan
    gap_mask = dt_s > cfg.inventory_gap_threshold_s
    has_gaps = bool(gap_mask.any())
    max_gap_s = float(dt_s.max()) if not dt_s.empty else np.nan
    gap_seconds_total = float(dt_s[gap_mask].sum()) if has_gaps else 0.0
    gap_ratio = gap_seconds_total / duration_s if duration_s > 0 else 0.0

    speed = pd.to_numeric(standardized.loc[mask, "Speed[km/h]"], errors="coerce").dropna()
    mean_speed = float(speed.mean()) if not speed.empty else np.nan
    median_speed = float(speed.median()) if not speed.empty else np.nan

    lat_valid = pd.to_numeric(standardized.loc[mask, "Lat"], errors="coerce")
    lon_valid = pd.to_numeric(standardized.loc[mask, "Lon"], errors="coerce")
    if lat_valid.notna().any():
        bbox = (float(lon_valid.min()), float(lat_valid.min()), float(lon_valid.max()), float(lat_valid.max()))
        centroid = (float(lon_valid.mean()), float(lat_valid.mean()))
    else:
        bbox = (np.nan, np.nan, np.nan, np.nan)
        centroid = (np.nan, np.nan)

    n_stationary = int(standardized["qc_stationary"].sum())
    n_repeated_coord = int(standardized["qc_coord_repeated"].sum())
    n_possible_freeze = int(standardized["qc_possible_gps_freeze"].sum())
    n_freeze = int(standardized["qc_gps_freeze"].sum())
    freeze_fraction = n_freeze / n_points_raw if n_points_raw else 0.0

    quality_flag = classify_campaign_quality(
        duration_minutes=duration_minutes, n_points_valid=n_points_valid,
        valid_fraction=valid_fraction, gap_ratio=gap_ratio, freeze_fraction=freeze_fraction, cfg=cfg,
    )

    distance_valid_km = sum(p.total_length_m for p in tracks.parts) / 1000.0

    row = {
        "campaign_id": campaign_id,
        "source_file": source_file,
        "start_datetime": start_dt_utc.tz_convert("Europe/Rome").isoformat() if pd.notna(start_dt_utc) else None,
        "end_datetime": end_dt_utc.tz_convert("Europe/Rome").isoformat() if pd.notna(end_dt_utc) else None,
        "duration_minutes": duration_minutes,
        "n_points_raw": n_points_raw,
        "n_points_valid": n_points_valid,
        "valid_fraction": valid_fraction,
        "distance_raw_km": _raw_distance_km(standardized),
        "distance_valid_km": distance_valid_km,
        "mean_sampling_interval_seconds": mean_dt,
        "median_sampling_interval_seconds": median_dt,
        "mean_speed_kmh": mean_speed,
        "median_speed_kmh": median_speed,
        "bounding_box_min_lon": bbox[0],
        "bounding_box_min_lat": bbox[1],
        "bounding_box_max_lon": bbox[2],
        "bounding_box_max_lat": bbox[3],
        "centroid_lon": centroid[0],
        "centroid_lat": centroid[1],
        "n_stationary_points": n_stationary,
        "n_repeated_coordinate_points": n_repeated_coord,
        "n_possible_gps_freeze_points": n_possible_freeze,
        "n_gps_freeze_points": n_freeze,
        "has_timestamp_gaps": has_gaps,
        "max_timestamp_gap_seconds": max_gap_s,
        "gap_ratio": gap_ratio,
        "n_campaign_parts": len(tracks.parts),
        "campaign_quality_flag": quality_flag,
    }
    if pd.notna(start_dt_utc):
        row.update({f"local_{k}": v for k, v in describe_timestamp(start_dt_utc, cfg).items()})
    if pd.notna(end_dt_utc):
        row["local_end_time"] = describe_timestamp(end_dt_utc, cfg)["local_time"]
    return row


def build_campaign_inventory(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    ordered_cols = [
        "campaign_id", "source_file", "start_datetime", "end_datetime",
        "local_local_date", "local_local_time", "local_end_time",
        "local_month", "local_day_of_week", "local_time_bin",
        "duration_minutes", "n_points_raw", "n_points_valid", "valid_fraction",
        "distance_raw_km", "distance_valid_km",
        "mean_sampling_interval_seconds", "median_sampling_interval_seconds",
        "mean_speed_kmh", "median_speed_kmh",
        "bounding_box_min_lon", "bounding_box_min_lat", "bounding_box_max_lon", "bounding_box_max_lat",
        "centroid_lon", "centroid_lat",
        "n_stationary_points", "n_repeated_coordinate_points", "n_possible_gps_freeze_points", "n_gps_freeze_points",
        "has_timestamp_gaps", "max_timestamp_gap_seconds", "gap_ratio", "n_campaign_parts",
        "campaign_quality_flag",
    ]
    cols = [c for c in ordered_cols if c in df.columns] + [c for c in df.columns if c not in ordered_cols]
    return df[cols].rename(columns={
        "local_local_date": "date", "local_local_time": "start_time", "local_end_time": "end_time",
        "local_month": "month", "local_day_of_week": "day_of_week", "local_time_bin": "start_time_bin",
    })
