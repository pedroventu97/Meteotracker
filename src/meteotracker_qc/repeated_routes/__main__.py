"""CLI entry point: python -m meteotracker_qc.repeated_routes ...

Reads the canonical raw campaigns (via the campaign manifest), never modifies
data/raw, and writes deterministic outputs under --output-dir. See section 18
of the Phase 1 spec / reports/repeated_routes_phase1.md for details.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .memberships import membership_metrics
from .pipeline import REPO_ROOT, run_pipeline, write_outputs
from .provenance import build_provenance, write_provenance
from .sensitivity import run_sensitivity_analysis
from .viz import generate_all_figures


def _setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("meteotracker_qc.repeated_routes")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Meteotracker Phase 1: repeated-route inventory")
    parser.add_argument("--profile", default="recommended", choices=["permissive", "recommended", "restrictive"],
                         help="QC profile used to standardize campaigns (config/qc_<profile>.yaml)")
    parser.add_argument("--config", default="recommended",
                         help="Repeated-routes matching config: a preset name (config/repeated_routes_<name>.yaml) or a path to a YAML file")
    parser.add_argument("--output-dir", default="outputs/repeated_routes", help="Output directory")
    parser.add_argument("--raw-dir", default="data/raw", help="Canonical raw-data directory")
    parser.add_argument("--manifest", default="data/manifests/campaign_manifest.csv", help="Campaign manifest CSV")
    parser.add_argument("--qc-output-dir", default="outputs/recommended", help="Where standardized QC outputs live/are written")
    parser.add_argument("--skip-qc-refresh", action="store_true", help="Reuse existing QC outputs instead of re-running run_qc")
    parser.add_argument("--skip-sensitivity", action="store_true", help="Skip the sensitivity analysis sweep")
    parser.add_argument("--skip-figures", action="store_true", help="Skip diagnostic figure generation")
    parser.add_argument("--full-rebuild", action="store_true",
                        help="Ignore reusable track/pair entries and rebuild the complete cache")
    parser.add_argument("--cache-dir", default=None,
                        help="Cache directory (default: <output-dir>/cache)")
    args = parser.parse_args(argv)

    output_dir = (REPO_ROOT / args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir)
    raw_dir = (REPO_ROOT / args.raw_dir).resolve() if not Path(args.raw_dir).is_absolute() else Path(args.raw_dir)
    manifest_path = (REPO_ROOT / args.manifest).resolve() if not Path(args.manifest).is_absolute() else Path(args.manifest)
    qc_output_dir = (REPO_ROOT / args.qc_output_dir).resolve() if not Path(args.qc_output_dir).is_absolute() else Path(args.qc_output_dir)
    qc_config_path = REPO_ROOT / "config" / f"qc_{args.profile}.yaml"
    cache_dir = Path(args.cache_dir) if args.cache_dir else output_dir / "cache"
    if not cache_dir.is_absolute():
        cache_dir = (REPO_ROOT / cache_dir).resolve()

    logger = _setup_logging(output_dir / "pipeline.log")

    try:
        rr_config = load_config(args.config)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc

    try:
        result = run_pipeline(
            raw_dir=raw_dir, qc_output_dir=qc_output_dir, qc_config_path=qc_config_path, qc_profile=args.profile,
            manifest_path=manifest_path, rr_config=rr_config, refresh_qc=not args.skip_qc_refresh, log=logger,
            cache_dir=cache_dir, full_rebuild=args.full_rebuild,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error("Pipeline failed: %s", exc)
        raise SystemExit(1) from exc

    write_outputs(result, output_dir)
    logger.info("Wrote campaign_inventory.csv, candidate_pairs.csv, comparison_opportunities.csv, repeated_routes.gpkg to %s", output_dir)

    input_files = [manifest_path] + [raw_dir / s for s in result.inventory_df["source_file"]]
    provenance = build_provenance(
        repo_root=REPO_ROOT, input_files=input_files, qc_profile=args.profile,
        rr_config=rr_config, qc_config_path=qc_config_path,
    )
    provenance["timings_seconds"] = result.timings
    provenance["candidate_stats"] = result.candidate_stats
    provenance["membership_metrics"] = membership_metrics(result.point_segment_memberships, result.point_segment_match_support)
    provenance["cache_stats"] = result.cache_stats
    provenance["full_rebuild"] = args.full_rebuild
    write_provenance(output_dir / "provenance.json", provenance)

    if not args.skip_sensitivity:
        logger.info("Running sensitivity analysis")
        sensitivity_df = run_sensitivity_analysis(
            result.parts_by_track, result.usable_parts, result.standardized_by_campaign, rr_config,
        )
        sensitivity_df.to_csv(output_dir / "sensitivity_summary.csv", index=False)
        logger.info("Wrote sensitivity_summary.csv (%d configurations)", len(sensitivity_df))

    if not args.skip_figures:
        logger.info("Generating diagnostic figures")
        figures_dir = output_dir / "figures"
        generate_all_figures(result, figures_dir, rr_config)
        logger.info("Wrote figures to %s", figures_dir)

    logger.info(
        "Done: %d campaigns, %d repeated segments, %.1f km total shared length",
        len(result.inventory_df), len(result.segments_df),
        float(result.segments_df["segment_length_m"].sum() / 1000.0) if not result.segments_df.empty else 0.0,
    )


if __name__ == "__main__":
    main()
