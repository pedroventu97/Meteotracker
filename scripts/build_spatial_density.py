"""CLI: repeated-passage density grid over the 34 canonical campaigns.

Reads canonical campaigns via the campaign manifest (same source as
repeated_routes/viz.py's "All campaigns" figure), never modifies data/raw,
and writes deterministic outputs under --output-dir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meteotracker_qc.repeated_routes.config import load_config  # noqa: E402
from meteotracker_qc.spatial_density.pipeline import (  # noqa: E402
    build_density_grid, run_density_analysis, sensitivity_summary,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Repeated-passage spatial density grid (34 canonical campaigns)")
    parser.add_argument("--profile", default="recommended", choices=["permissive", "recommended", "restrictive"])
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--manifest", default="data/manifests/campaign_manifest.csv")
    parser.add_argument("--qc-output-dir", default="outputs/recommended")
    parser.add_argument("--output-dir", default="outputs/spatial_density")
    parser.add_argument("--primary-cell-size-m", type=float, default=50.0)
    parser.add_argument("--sensitivity-cell-sizes-m", type=float, nargs="+", default=[25.0, 50.0, 100.0])
    args = parser.parse_args(argv)

    raw_dir = REPO_ROOT / args.raw_dir
    manifest_path = REPO_ROOT / args.manifest
    qc_output_dir = REPO_ROOT / args.qc_output_dir
    output_dir = REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    rr_config = load_config(args.profile)

    print(f"Loading canonical campaigns via manifest {manifest_path} ...", flush=True)
    campaign_tracks_by_id, xy_by_campaign, inventory_df = run_density_analysis(
        raw_dir, qc_output_dir, manifest_path, rr_config,
    )
    print(f"Loaded {len(campaign_tracks_by_id)} canonical campaigns", flush=True)

    primary = args.primary_cell_size_m
    print(f"Building primary {primary:g} m density grid ...", flush=True)
    primary_gdf = build_density_grid(campaign_tracks_by_id, xy_by_campaign, primary, rr_config.crs_metric_epsg)
    print(f"Primary grid: {len(primary_gdf)} cells total, "
          f"{(primary_gdf['n_observations'] > 0).sum()} traversed", flush=True)

    gpkg_path = output_dir / f"meteotracker_coverage_{int(primary)}m.gpkg"
    csv_path = output_dir / f"meteotracker_coverage_{int(primary)}m.csv"
    if gpkg_path.exists():
        gpkg_path.unlink()
    primary_gdf.to_file(gpkg_path, layer="coverage_cells", driver="GPKG")
    primary_gdf.drop(columns="geometry").to_csv(csv_path, index=False)
    print(f"Wrote {gpkg_path}", flush=True)
    print(f"Wrote {csv_path}", flush=True)

    print(f"Running sensitivity sweep over {args.sensitivity_cell_sizes_m} m ...", flush=True)
    sens_df = sensitivity_summary(
        campaign_tracks_by_id, xy_by_campaign, args.sensitivity_cell_sizes_m, rr_config.crs_metric_epsg,
    )
    sens_path = output_dir / "sensitivity_cell_size_comparison.csv"
    sens_df.to_csv(sens_path, index=False)
    print(sens_df.to_string(index=False), flush=True)
    print(f"Wrote {sens_path}", flush=True)


if __name__ == "__main__":
    main()
