from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from meteotracker_qc.pipeline import run_qc  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Meteotracker QC pipeline")
    parser.add_argument("--input", required=True, help="Input directory containing CSV files")
    parser.add_argument("--output", required=True, help="Output directory for standardized and flagged data")
    parser.add_argument("--config", default="config/qc_recommended.yaml", help="QC configuration YAML path")
    parser.add_argument(
        "--manifest",
        default=None,
        help="Campaign manifest CSV (default: <input>/../manifests/campaign_manifest.csv if present)",
    )
    parser.add_argument(
        "--include-all-files",
        action="store_true",
        help="Process every CSV under --input, including files the manifest marks as redundant "
             "re-exports. Default behavior processes only canonical campaigns.",
    )
    args = parser.parse_args()

    run_qc(
        Path(args.input),
        Path(args.output),
        Path(args.config),
        include_all_files=args.include_all_files,
        manifest_path=Path(args.manifest) if args.manifest else None,
    )


if __name__ == "__main__":
    main()
