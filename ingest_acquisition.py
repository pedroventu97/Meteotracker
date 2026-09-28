from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from meteotracker_qc.ingestion import (  # noqa: E402
    PROFILE_NAMES, apply_manifest_and_qc, build_log_payload, check_campaign, promote,
    write_ingestion_report,
)


def _run_aggregates(staging: Path, canonical_ids: list[str], *, full_rebuild: bool = False) -> dict[str, object]:
    from meteotracker_qc.repeated_routes.config import load_config
    from meteotracker_qc.repeated_routes.pipeline import run_pipeline, write_outputs
    from meteotracker_qc.repeated_routes.sensitivity import run_sensitivity_analysis
    from meteotracker_qc.repeated_routes.viz import generate_all_figures
    from meteotracker_qc.spatial_density.pipeline import build_density_grid, run_density_analysis, sensitivity_summary
    from meteotracker_qc.temporal_drift_pipeline import run_temporal_drift

    outputs = staging / "outputs"
    manifest = staging / "data" / "manifests" / "campaign_manifest.csv"
    raw = ROOT / "data" / "raw"
    for name in ("repeated_routes", "spatial_density", "temporal_drift"):
        shutil.copytree(ROOT / "outputs" / name, outputs / name, dirs_exist_ok=True)

    rr_cfg = load_config(str(ROOT / "config" / "repeated_routes_recommended.yaml"))
    rr = run_pipeline(
        raw_dir=raw,
        qc_output_dir=outputs / "recommended",
        qc_config_path=ROOT / "config" / "qc_recommended.yaml",
        qc_profile="recommended",
        manifest_path=manifest,
        rr_config=rr_cfg,
        refresh_qc=False,
        cache_dir=outputs / "repeated_routes" / "cache",
        full_rebuild=full_rebuild,
    )
    write_outputs(rr, outputs / "repeated_routes")
    stale_path = outputs / "repeated_routes" / "stale_artifacts.json"
    if full_rebuild:
        run_sensitivity_analysis(rr.parts_by_track, rr.usable_parts, rr.standardized_by_campaign, rr_cfg).to_csv(
            outputs / "repeated_routes" / "sensitivity_summary.csv", index=False)
        generate_all_figures(rr, outputs / "repeated_routes" / "figures", rr_cfg)
        if stale_path.exists():
            stale_path.unlink()
    else:
        campaign_set_hash = hashlib.sha256("\n".join(canonical_ids).encode("utf-8")).hexdigest()
        stale_path.write_text(json.dumps({
            "stale": True,
            "artifacts": ["sensitivity_summary.csv", "figures/"],
            "reason": "Ordinary incremental ingestion does not rebuild global sensitivity or figures.",
            "current_campaign_set_sha256": campaign_set_hash,
            "current_campaign_ids": canonical_ids,
            "regenerate_command": "python -m meteotracker_qc.repeated_routes --skip-qc-refresh --full-rebuild",
        }, indent=2), encoding="utf-8")

    tracks, xy, _ = run_density_analysis(raw, outputs / "recommended", manifest, rr_cfg)
    grid = build_density_grid(tracks, xy, 50.0, rr_cfg.crs_metric_epsg)
    gpkg = outputs / "spatial_density" / "meteotracker_coverage_50m.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    grid.to_file(gpkg, layer="coverage_cells", driver="GPKG")
    grid.drop(columns="geometry").to_csv(outputs / "spatial_density" / "meteotracker_coverage_50m.csv", index=False)
    sensitivity_summary(tracks, xy, [25.0, 50.0, 100.0], rr_cfg.crs_metric_epsg).to_csv(
        outputs / "spatial_density" / "sensitivity_cell_size_comparison.csv", index=False)

    run_temporal_drift(root=staging, output_root=outputs / "temporal_drift",
                       campaign_ids=canonical_ids, progress=True)
    return {"cache_stats": rr.cache_stats, "repeated_routes_timings": rr.timings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and ingest a Meteotracker acquisition safely")
    parser.add_argument("--campaign", required=True, help="Raw acquisition directory below data/raw")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Non-destructive validation and temporary QC run")
    mode.add_argument("--apply", action="store_true", help="Validate, stage, verify and atomically promote official outputs")
    parser.add_argument("--skip-heavy-aggregates", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--full-rebuild", action="store_true",
                        help="Rebuild all repeated-route pairs, sensitivity and figures instead of using caches")
    args = parser.parse_args(argv)

    check = check_campaign(ROOT, args.campaign, run_pipeline_check=True)
    print(json.dumps(check, indent=2, ensure_ascii=False, default=str))
    if args.check:
        return 0 if check["status"] in {"pass", "already_registered"} else 2
    if check["status"] == "already_registered" and not args.full_rebuild:
        print("Already registered; apply is a no-op.")
        return 0
    if check["status"] not in {"pass", "already_registered"}:
        print("Apply blocked because validation did not pass.", file=sys.stderr)
        return 2

    import pandas as pd
    current = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    before = int((~current["exclude_from_analysis"].astype(bool)).sum())
    with tempfile.TemporaryDirectory(prefix="meteotracker_ingest_apply_") as tmp:
        staging = Path(tmp)
        built = apply_manifest_and_qc(ROOT, args.campaign, staging, check)
        aggregate_report = None
        if not args.skip_heavy_aggregates:
            aggregate_report = _run_aggregates(staging, built["canonical_ids"], full_rebuild=args.full_rebuild)
        after = len(built["canonical_ids"])
        report = build_log_payload(ROOT, args.campaign, check, before, after)
        report["repeated_routes_mode"] = "full_rebuild" if args.full_rebuild else "incremental"
        report["repeated_routes"] = aggregate_report
        report_path = staging / "outputs" / "ingestion" / f"{args.campaign}_ingestion_report.json"
        write_ingestion_report(report_path, report)
        targets = [Path("data/manifests/campaign_manifest.csv")]
        targets += [Path("outputs") / p for p in (*PROFILE_NAMES, "session_qc")]
        if not args.skip_heavy_aggregates:
            targets += [Path("outputs") / p for p in ("repeated_routes", "spatial_density", "temporal_drift")]
        targets += [Path("outputs/ingestion")]
        promote(staging, ROOT, targets)
    print(f"Applied {args.campaign}: canonical campaigns {before} -> {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
