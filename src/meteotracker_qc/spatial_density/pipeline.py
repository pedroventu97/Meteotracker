"""Orchestrates the repeated-passage density grid over the 34 canonical campaigns.

Reuses ``repeated_routes.pipeline.build_campaign_tracks`` unchanged as the single
source of canonical campaigns and QC-valid tracks -- no QC rule is reimplemented
or modified here. Per grid cell (see ``grid.py`` for the cell/visit definitions)
this computes:

- n_observations: all geolocatable points (non-missing coordinates), any QC status.
- n_valid_observations: the subset also passing ``use_for_route_mapping``
  (~(qc_gps_freeze | qc_gps_jump)), i.e. the points that make up campaign parts.
- n_campaigns: distinct canonical campaigns with >=1 valid visit in the cell.
- n_visits: total independent visits (temporally-contiguous same-cell runs)
  across all campaigns/parts.
- n_same_campaign_revisits: n_visits - n_campaigns (visits beyond the first per
  campaign in that cell -- within-campaign repetition, kept separate from
  between-campaign repetition captured by n_campaigns).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box

from ..repeated_routes.config import RepeatedRoutesConfig
from ..repeated_routes.pipeline import build_campaign_tracks
from ..repeated_routes.tracks import CampaignTracks
from . import grid as gridmod

CELL_COLUMNS = [
    "cell_id", "col", "row",
    "n_observations", "n_valid_observations",
    "n_campaigns", "n_visits", "n_same_campaign_revisits",
    "n_excluded_observations", "pct_excluded",
    "geometry",
]


def raw_xy_by_campaign(
    standardized_by_campaign: dict[str, pd.DataFrame], cfg: RepeatedRoutesConfig,
) -> dict[str, pd.DataFrame]:
    """Metric x_m/y_m for every geolocatable (non-missing-coordinate) raw row,
    regardless of QC freeze/jump status -- the basis for n_observations."""
    fwd = Transformer.from_crs(f"EPSG:{cfg.crs_geographic_epsg}", f"EPSG:{cfg.crs_metric_epsg}", always_xy=True)
    out: dict[str, pd.DataFrame] = {}
    for campaign_id, df in standardized_by_campaign.items():
        geolocatable = df.loc[~df["qc_coord_missing"].astype(bool), ["Lat", "Lon"]].dropna()
        if geolocatable.empty:
            out[campaign_id] = pd.DataFrame(columns=["x_m", "y_m"])
            continue
        x, y = fwd.transform(geolocatable["Lon"].to_numpy(dtype=float), geolocatable["Lat"].to_numpy(dtype=float))
        out[campaign_id] = pd.DataFrame({"x_m": x, "y_m": y})
    return out


def build_density_grid(
    campaign_tracks_by_id: dict[str, CampaignTracks],
    xy_by_campaign: dict[str, pd.DataFrame],
    cell_size_m: float,
    crs_metric_epsg: int,
) -> gpd.GeoDataFrame:
    visit_frames = []
    for campaign_id, tracks in campaign_tracks_by_id.items():
        for part in tracks.parts:
            assigned = gridmod.detect_visits_for_part(part.points, cell_size_m)
            if assigned.empty:
                continue
            assigned["campaign_id"] = campaign_id
            assigned["track_id"] = part.track_id
            visit_frames.append(assigned)

    if visit_frames:
        assigned_all = pd.concat(visit_frames, ignore_index=True)
        visits = (
            assigned_all.groupby(["campaign_id", "track_id", "visit_run_id", "col", "row"])
            .size()
            .rename("n_points")
            .reset_index()
        )
        cell_valid = visits.groupby(["col", "row"]).agg(
            n_valid_observations=("n_points", "sum"),
            n_visits=("n_points", "count"),
            n_campaigns=("campaign_id", "nunique"),
        ).reset_index()
    else:
        cell_valid = pd.DataFrame(columns=["col", "row", "n_valid_observations", "n_visits", "n_campaigns"])

    cell_raw = gridmod.raw_observation_counts(xy_by_campaign, cell_size_m)

    cells = cell_raw.merge(cell_valid, on=["col", "row"], how="outer")
    for c in ("n_observations", "n_valid_observations", "n_visits", "n_campaigns"):
        cells[c] = cells[c].fillna(0).astype("int64")
    cells["n_same_campaign_revisits"] = cells["n_visits"] - cells["n_campaigns"]
    cells["n_excluded_observations"] = cells["n_observations"] - cells["n_valid_observations"]
    cells["pct_excluded"] = np.where(
        cells["n_observations"] > 0, cells["n_excluded_observations"] / cells["n_observations"] * 100.0, np.nan,
    )
    cells["cell_id"] = (
        cells["col"].astype(str) + "_" + cells["row"].astype(str) + f"_{cell_size_m:g}m"
    )

    geoms = [
        box(c * cell_size_m, r * cell_size_m, (c + 1) * cell_size_m, (r + 1) * cell_size_m)
        for c, r in zip(cells["col"], cells["row"])
    ]
    gdf = gpd.GeoDataFrame(cells, geometry=geoms, crs=f"EPSG:{crs_metric_epsg}")
    return gdf[CELL_COLUMNS]


def sensitivity_summary(
    campaign_tracks_by_id: dict[str, CampaignTracks],
    xy_by_campaign: dict[str, pd.DataFrame],
    cell_sizes_m: list[float],
    crs_metric_epsg: int,
) -> pd.DataFrame:
    rows = []
    for cell_size_m in cell_sizes_m:
        gdf = build_density_grid(campaign_tracks_by_id, xy_by_campaign, cell_size_m, crs_metric_epsg)
        traversed = gdf.loc[gdf["n_observations"] > 0]
        n_cells = len(traversed)
        rows.append({
            "cell_size_m": cell_size_m,
            "n_cells_traversed": n_cells,
            "max_n_observations": int(traversed["n_observations"].max()) if n_cells else 0,
            "max_n_campaigns": int(traversed["n_campaigns"].max()) if n_cells else 0,
            "max_n_visits": int(traversed["n_visits"].max()) if n_cells else 0,
            "median_n_campaigns": float(traversed["n_campaigns"].median()) if n_cells else 0.0,
            "pct_cells_ge2_campaigns": float((traversed["n_campaigns"] >= 2).mean() * 100) if n_cells else 0.0,
            "pct_cells_ge3_campaigns": float((traversed["n_campaigns"] >= 3).mean() * 100) if n_cells else 0.0,
            "pct_cells_ge5_campaigns": float((traversed["n_campaigns"] >= 5).mean() * 100) if n_cells else 0.0,
        })
    return pd.DataFrame(rows)


def run_density_analysis(
    raw_dir: Path, qc_output_dir: Path, manifest_path: Path, rr_config: RepeatedRoutesConfig,
) -> tuple[dict[str, CampaignTracks], dict[str, pd.DataFrame], pd.DataFrame]:
    """Loads the 34 canonical campaigns (same path as repeated_routes/viz.py's
    fig_all_campaigns) and returns (campaign_tracks_by_id, xy_by_campaign, inventory_df)."""
    inventory_df, standardized_by_campaign, campaign_tracks_by_id = build_campaign_tracks(
        raw_dir, qc_output_dir, manifest_path, rr_config,
    )
    xy_by_campaign = raw_xy_by_campaign(standardized_by_campaign, rr_config)
    return campaign_tracks_by_id, xy_by_campaign, inventory_df
