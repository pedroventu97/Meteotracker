"""Assembles the section-11 GeoPackage: outputs/repeated_routes/repeated_routes.gpkg.

Layers: campaign_tracks, campaign_parts, repeated_segments, segment_passages,
pairwise_matches, excluded_or_low_quality_tracks. All geometries in WGS84
(EPSG:4326) for interoperability, per section 4.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString

from .tracks import CampaignTracks

WGS84 = "EPSG:4326"


def _campaign_geometry(tracks: CampaignTracks) -> LineString | MultiLineString | None:
    lines = []
    for part in tracks.parts:
        pts = list(zip(part.points["Lon"], part.points["Lat"]))
        if len(pts) >= 2:
            lines.append(LineString(pts))
    if not lines:
        return None
    if len(lines) == 1:
        return lines[0]
    return MultiLineString(lines)


def build_campaign_layers(
    campaign_tracks_by_id: dict[str, CampaignTracks], inventory_df: pd.DataFrame,
    *, geographic_epsg: int = 4326,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    quality_by_campaign = dict(zip(inventory_df["campaign_id"], inventory_df["campaign_quality_flag"]))

    track_rows, part_rows, excluded_rows = [], [], []
    for campaign_id, tracks in campaign_tracks_by_id.items():
        quality = quality_by_campaign.get(campaign_id, "excluded")
        geom = _campaign_geometry(tracks)
        n_parts = len(tracks.parts)
        total_length_m = sum(p.total_length_m for p in tracks.parts)
        record = {
            "campaign_id": campaign_id, "campaign_quality_flag": quality,
            "n_parts": n_parts, "total_length_m": total_length_m, "geometry": geom,
        }
        if geom is not None:
            if quality in ("high", "medium"):
                track_rows.append(record)
            else:
                excluded_rows.append(record)

        for part in tracks.parts:
            part_geom = LineString(list(zip(part.points["Lon"], part.points["Lat"]))) if len(part.points) >= 2 else None
            if part_geom is None:
                continue
            part_rows.append({
                "campaign_id": campaign_id, "campaign_part_id": part.campaign_part_id,
                "track_id": part.track_id, "campaign_quality_flag": quality,
                "n_points": len(part.points), "length_m": part.total_length_m,
                "start_datetime": part.start_time.tz_convert("Europe/Rome").isoformat(),
                "end_datetime": part.end_time.tz_convert("Europe/Rome").isoformat(),
                "geometry": part_geom,
            })

    def _gdf(rows):
        if not rows:
            return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=f"EPSG:{geographic_epsg}")
        return gpd.GeoDataFrame(rows, geometry=[r["geometry"] for r in rows], crs=f"EPSG:{geographic_epsg}")

    return _gdf(track_rows), _gdf(part_rows), _gdf(excluded_rows)


def write_geopackage(
    path: str | Path,
    campaign_tracks_gdf: gpd.GeoDataFrame,
    campaign_parts_gdf: gpd.GeoDataFrame,
    excluded_gdf: gpd.GeoDataFrame,
    segments_df: pd.DataFrame,
    passages_df: pd.DataFrame,
    matches_df: pd.DataFrame,
    *, memberships_df: pd.DataFrame | None = None, geographic_epsg: int = 4326,
    match_support_df: pd.DataFrame | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    layers: list[tuple[str, gpd.GeoDataFrame]] = [
        ("campaign_tracks", campaign_tracks_gdf),
        ("campaign_parts", campaign_parts_gdf),
        ("excluded_or_low_quality_tracks", excluded_gdf),
    ]

    if not segments_df.empty:
        layers.append(("repeated_segments", gpd.GeoDataFrame(segments_df, geometry="geometry", crs=f"EPSG:{geographic_epsg}")))
    else:
        layers.append(("repeated_segments", gpd.GeoDataFrame(columns=segments_df.columns, geometry=[], crs=f"EPSG:{geographic_epsg}")))

    if not passages_df.empty:
        layers.append(("segment_passages", gpd.GeoDataFrame(passages_df, geometry="geometry", crs=f"EPSG:{geographic_epsg}")))
    else:
        layers.append(("segment_passages", gpd.GeoDataFrame(columns=passages_df.columns, geometry=[], crs=f"EPSG:{geographic_epsg}")))

    if not matches_df.empty:
        matches_valid = matches_df[matches_df["geometry"].notna()].copy()
        layers.append(("pairwise_matches", gpd.GeoDataFrame(matches_valid, geometry="geometry", crs=f"EPSG:{geographic_epsg}")))
    else:
        layers.append(("pairwise_matches", gpd.GeoDataFrame(columns=matches_df.columns if len(matches_df.columns) else ["geometry"], geometry=[], crs=f"EPSG:{geographic_epsg}")))

    if memberships_df is not None:
        layers.append(('point_segment_memberships', gpd.GeoDataFrame(
            memberships_df, geometry='geometry', crs=f'EPSG:{geographic_epsg}',
        )))

    for layer_name, gdf in layers:
        gdf.to_file(path, layer=layer_name, driver="GPKG")

    if memberships_df is not None:
        connection = sqlite3.connect(path)
        try:
            with connection:
                connection.execute('CREATE UNIQUE INDEX memberships_semantic_key ON point_segment_memberships '
                                   '(repeated_segment_id, segment_passage_id, source_file, source_row)')
                connection.execute('CREATE UNIQUE INDEX memberships_id ON point_segment_memberships (membership_id)')
                if match_support_df is not None:
                    # Native GeoPackage attributes table: provenance has no geometry.
                    connection.execute('PRAGMA foreign_keys = ON')
                    connection.execute('CREATE TABLE point_segment_match_support ('
                                       'membership_id TEXT NOT NULL, supporting_match_id TEXT NOT NULL, '
                                       'PRIMARY KEY (membership_id, supporting_match_id), '
                                       'FOREIGN KEY (membership_id) REFERENCES point_segment_memberships(membership_id))')
                    connection.executemany('INSERT INTO point_segment_match_support VALUES (?, ?)',
                                           match_support_df[['membership_id', 'supporting_match_id']].itertuples(index=False, name=None))
                    connection.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, description) "
                                       "VALUES ('point_segment_match_support', 'attributes', 'point_segment_match_support', "
                                       "'Match provenance for unique scientific point memberships')")
        finally:
            connection.close()
