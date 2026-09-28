"""CLI: three-panel campaign/Bologna-boundary/repeated-coverage figure.

Panel A - full extent of all 34 canonical campaigns, with the Bologna municipal
boundary overlaid for geographic context.
Panel B - zoom on the Bologna municipal boundary (+10-15% margin), showing all
campaign-track portions falling in that view.
Panel C - same extent as panel B, with the 50 m repeated-passage density grid
(outputs/spatial_density/meteotracker_coverage_50m.gpkg) colored by
n_campaigns, tracks overlaid thin/transparent, boundary drawn on top.

Reads canonical campaigns via the campaign manifest (same source as
repeated_routes/viz.py's "All campaigns" figure and build_spatial_density.py),
never modifies data/raw. Requires an already-built density grid (run
build_spatial_density.py first) and a Bologna municipal boundary vector file
supplied by the caller -- no boundary is fabricated or approximated here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meteotracker_qc.repeated_routes.config import load_config  # noqa: E402
from meteotracker_qc.spatial_density.pipeline import run_density_analysis  # noqa: E402

TRACK_COLOR = "#334155"
BOUNDARY_COLOR = "#0a0a0a"
DENSITY_CLASS_BIN_EDGES = [0, 1, 2, 4, 7, np.inf]
DENSITY_CLASS_LABELS = ["1 campaign", "2 campaigns", "3-4 campaigns", "5-7 campaigns", ">=8 campaigns"]
DENSITY_CLASS_COLORS = ["#deebf7", "#9ecae1", "#4292c6", "#2171b5", "#08306b"]


def load_boundary(path: Path, layer: str | None, name_field: str | None, name_value: str | None, target_epsg: int) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Bologna municipal boundary file not found: {path}. This script does not fabricate or "
            f"approximate a boundary -- supply an authoritative vector file (ISTAT 'Confini delle "
            f"unita amministrative' or the Comune di Bologna open-data boundary) and pass it via --boundary."
        )
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"Boundary file {path} has no CRS defined -- cannot safely reproject/overlay.")
    source_crs = gdf.crs
    if name_field and name_value:
        if name_field not in gdf.columns:
            raise KeyError(
                f"--boundary-name-field '{name_field}' not found in {path} columns: {list(gdf.columns)}"
            )
        matched = gdf.loc[gdf[name_field].astype(str).str.strip().str.casefold() == name_value.strip().casefold()]
        if matched.empty:
            raise ValueError(
                f"No feature with {name_field} == '{name_value}' found in {path}. "
                f"Available values (sample): {sorted(gdf[name_field].astype(str).unique())[:20]}"
            )
        gdf = matched
    reprojected = gdf.to_crs(epsg=target_epsg)
    print(f"Boundary source: {path} (layer={layer}), source CRS={source_crs}, "
          f"selected {len(gdf)} feature(s) via {name_field}=={name_value!r}, reprojected to EPSG:{target_epsg}",
          flush=True)
    return reprojected


def classify_density(gdf: gpd.GeoDataFrame, column: str = "n_campaigns") -> gpd.GeoDataFrame:
    out = gdf.loc[gdf[column] > 0].copy()
    out["density_class"] = pd.cut(
        out[column], bins=DENSITY_CLASS_BIN_EDGES, labels=DENSITY_CLASS_LABELS, right=True,
    )
    return out


def plot_tracks(ax, campaign_tracks_by_id, linewidth: float = 0.5, alpha: float = 0.55) -> None:
    for tracks in campaign_tracks_by_id.values():
        for part in tracks.parts:
            ax.plot(part.points["x_m"], part.points["y_m"], linewidth=linewidth, alpha=alpha, color=TRACK_COLOR)


def draw_boundary(ax, boundary_gdf: gpd.GeoDataFrame, label: str | None = None, linewidth: float = 2.2) -> None:
    boundary_gdf.plot(ax=ax, facecolor=BOUNDARY_COLOR, alpha=0.06, edgecolor="none", zorder=4)
    boundary_gdf.boundary.plot(ax=ax, color=BOUNDARY_COLOR, linewidth=linewidth, zorder=5)
    if label:
        minx, miny, maxx, maxy = boundary_gdf.total_bounds
        ax.annotate(
            label, xy=((minx + maxx) / 2, maxy), xytext=(0, 6), textcoords="offset points",
            ha="center", va="bottom", fontsize=8, color=BOUNDARY_COLOR, zorder=6,
            annotation_clip=False,
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="34-campaign / Bologna-boundary / density three-panel figure")
    parser.add_argument("--boundary", required=True, help="Path to Bologna municipal boundary vector file (.shp/.geojson/.gpkg)")
    parser.add_argument("--boundary-layer", default=None, help="Layer name if --boundary is a multi-layer GPKG")
    parser.add_argument("--boundary-name-field", default=None, help="Attribute used to select Bologna (e.g. COMUNE, PRO_COM)")
    parser.add_argument("--boundary-name-value", default=None, help="Value of --boundary-name-field identifying Bologna")
    parser.add_argument("--density-gpkg", default="outputs/spatial_density/meteotracker_coverage_50m.gpkg")
    parser.add_argument("--profile", default="recommended", choices=["permissive", "recommended", "restrictive"])
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--manifest", default="data/manifests/campaign_manifest.csv")
    parser.add_argument("--qc-output-dir", default="outputs/recommended")
    parser.add_argument("--output-dir", default="outputs/figures")
    parser.add_argument("--margin-fraction", type=float, default=0.125, help="Zoom margin around the boundary bounds (10-15%% recommended)")
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args(argv)

    rr_config = load_config(args.profile)
    raw_dir = REPO_ROOT / args.raw_dir
    manifest_path = REPO_ROOT / args.manifest
    qc_output_dir = REPO_ROOT / args.qc_output_dir
    output_dir = REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading canonical campaigns via manifest {manifest_path} ...", flush=True)
    campaign_tracks_by_id, _xy_by_campaign, inventory_df = run_density_analysis(
        raw_dir, qc_output_dir, manifest_path, rr_config,
    )
    n_campaigns_loaded = len(campaign_tracks_by_id)
    print(f"Loaded {n_campaigns_loaded} canonical campaigns (per data/manifests/campaign_manifest.csv, "
          f"exclude_from_analysis == False)", flush=True)

    all_x = np.concatenate([part.points["x_m"].to_numpy() for t in campaign_tracks_by_id.values() for part in t.parts])
    all_y = np.concatenate([part.points["y_m"].to_numpy() for t in campaign_tracks_by_id.values() for part in t.parts])
    print(f"Campaign bounds (EPSG:{rr_config.crs_metric_epsg}): "
          f"x=[{all_x.min():.0f}, {all_x.max():.0f}], y=[{all_y.min():.0f}, {all_y.max():.0f}]", flush=True)

    boundary_gdf = load_boundary(
        Path(args.boundary), args.boundary_layer, args.boundary_name_field, args.boundary_name_value,
        target_epsg=rr_config.crs_metric_epsg,
    )
    b_minx, b_miny, b_maxx, b_maxy = boundary_gdf.total_bounds
    print(f"Boundary bounds (EPSG:{rr_config.crs_metric_epsg}): "
          f"x=[{b_minx:.0f}, {b_maxx:.0f}], y=[{b_miny:.0f}, {b_maxy:.0f}]", flush=True)

    campaign_extent_intersects = not (
        all_x.max() < b_minx or all_x.min() > b_maxx or all_y.max() < b_miny or all_y.min() > b_maxy
    )
    if not campaign_extent_intersects:
        print("WARNING: campaign bounding box does not overlap the boundary bounding box at all -- "
              "check CRS/reprojection before trusting this figure.", flush=True)

    density_path = REPO_ROOT / args.density_gpkg
    if not density_path.exists():
        raise FileNotFoundError(f"Density grid not found: {density_path}. Run scripts/build_spatial_density.py first.")
    density_gdf = gpd.read_file(density_path, layer="coverage_cells")
    if density_gdf.crs.to_epsg() != rr_config.crs_metric_epsg:
        density_gdf = density_gdf.to_crs(epsg=rr_config.crs_metric_epsg)

    margin_x = (b_maxx - b_minx) * args.margin_fraction
    margin_y = (b_maxy - b_miny) * args.margin_fraction
    zoom_xlim = (b_minx - margin_x, b_maxx + margin_x)
    zoom_ylim = (b_miny - margin_y, b_maxy + margin_y)

    zoom_bbox_geom = gpd.GeoSeries(gpd.points_from_xy(
        [zoom_xlim[0], zoom_xlim[1]], [zoom_ylim[0], zoom_ylim[1]],
    ), crs=density_gdf.crs).union_all().envelope
    density_in_zoom = density_gdf.loc[density_gdf.intersects(zoom_bbox_geom) & (density_gdf["n_campaigns"] > 0)]
    print(f"Density cells within panel B/C zoom extent: {len(density_in_zoom)}", flush=True)
    if len(density_in_zoom):
        nc = density_in_zoom["n_campaigns"]
        print(f"  n_campaigns within zoom: max={nc.max()}, median={nc.median():.1f}, "
              f"q90={nc.quantile(0.9):.1f}, q99={nc.quantile(0.99):.1f}", flush=True)
        print(f"  frequency by class: {nc.value_counts().sort_index().to_dict()}", flush=True)

    density_classed = classify_density(density_in_zoom)

    full_extent_aspect = (all_x.max() - all_x.min()) / max(all_y.max() - all_y.min(), 1e-6)
    width_ratios = [min(max(full_extent_aspect, 1.0), 3.0), 1.0, 1.0]
    fig, (ax_a, ax_b, ax_c) = plt.subplots(
        1, 3, figsize=(6.5 * sum(width_ratios), 7.5),
        gridspec_kw={"width_ratios": width_ratios}, constrained_layout=True,
    )

    plot_tracks(ax_a, campaign_tracks_by_id)
    draw_boundary(ax_a, boundary_gdf, label="Comune di Bologna")
    ax_a.set_title(f"All Meteotracker campaigns — full extent (n={n_campaigns_loaded})")
    ax_a.set_xlabel(f"Easting (m, EPSG:{rr_config.crs_metric_epsg})")
    ax_a.set_ylabel(f"Northing (m, EPSG:{rr_config.crs_metric_epsg})")
    ax_a.set_aspect("equal")
    ax_a.grid(True, linewidth=0.3, alpha=0.3)

    plot_tracks(ax_b, campaign_tracks_by_id)
    draw_boundary(ax_b, boundary_gdf)
    ax_b.set_xlim(*zoom_xlim)
    ax_b.set_ylim(*zoom_ylim)
    ax_b.set_title("Campaign coverage within Bologna")
    ax_b.set_xlabel(f"Easting (m, EPSG:{rr_config.crs_metric_epsg})")
    ax_b.set_ylabel(f"Northing (m, EPSG:{rr_config.crs_metric_epsg})")
    ax_b.set_aspect("equal")
    ax_b.grid(True, linewidth=0.3, alpha=0.3)

    if not density_classed.empty:
        density_classed.plot(
            ax=ax_c,
            color=[DENSITY_CLASS_COLORS[DENSITY_CLASS_LABELS.index(c)] for c in density_classed["density_class"]],
            zorder=2,
        )
        handles = [
            plt.Rectangle((0, 0), 1, 1, facecolor=color, edgecolor="none")
            for color in DENSITY_CLASS_COLORS
        ]
        ax_c.legend(handles, DENSITY_CLASS_LABELS, title="Distinct campaigns per 50 m cell",
                    loc="lower left", fontsize=7, title_fontsize=7, framealpha=0.9)
    plot_tracks(ax_c, campaign_tracks_by_id, linewidth=0.3, alpha=0.25)
    draw_boundary(ax_c, boundary_gdf)
    ax_c.set_xlim(*zoom_xlim)
    ax_c.set_ylim(*zoom_ylim)
    ax_c.set_title("Repeated coverage — number of distinct campaigns per 50 m cell")
    ax_c.set_xlabel(f"Easting (m, EPSG:{rr_config.crs_metric_epsg})")
    ax_c.set_ylabel(f"Northing (m, EPSG:{rr_config.crs_metric_epsg})")
    ax_c.set_aspect("equal")
    ax_c.grid(True, linewidth=0.3, alpha=0.3)

    png_path = output_dir / "all_campaigns_bologna_density.png"
    pdf_path = output_dir / "all_campaigns_bologna_density.pdf"
    fig.savefig(png_path, dpi=args.dpi)
    fig.savefig(pdf_path)
    plt.close(fig)
    print(f"Wrote {png_path}", flush=True)
    print(f"Wrote {pdf_path}", flush=True)


if __name__ == "__main__":
    main()
