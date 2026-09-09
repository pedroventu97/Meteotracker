"""Loads the canonical campaigns this pipeline operates on.

Reuses the existing QC pipeline (meteotracker_qc.pipeline.run_qc) unchanged to
(re)produce the standardized per-campaign outputs, then reads them back. Never
reads or writes anything under data/raw except as a read-only input to run_qc.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd

from ..pipeline import _campaign_output_dir, run_qc


@dataclasses.dataclass
class CampaignSource:
    campaign_id: str
    source_file: str  # path relative to data/raw, as recorded in the campaign manifest
    output_dir: Path
    standardized_path: Path


def refresh_qc_outputs(raw_dir: Path, qc_output_dir: Path, qc_config_path: Path, manifest_path: Path) -> pd.DataFrame:
    """Re-run the existing, unmodified QC pipeline over the canonical campaigns."""
    return run_qc(
        input_dir=raw_dir,
        output_dir=qc_output_dir,
        config_path=qc_config_path,
        include_all_files=False,
        manifest_path=manifest_path,
    )


def list_canonical_campaigns(raw_dir: Path, qc_output_dir: Path, manifest_path: Path) -> list[CampaignSource]:
    manifest = pd.read_csv(manifest_path)
    canonical = manifest.loc[~manifest["exclude_from_analysis"].astype(bool)]
    sources = []
    for _, row in canonical.iterrows():
        rel_path = Path(row["source_file"])
        raw_csv = raw_dir / rel_path
        out_dir = _campaign_output_dir(raw_csv, raw_dir, qc_output_dir)
        standardized = out_dir / f"{raw_csv.stem}_standardized.parquet"
        sources.append(CampaignSource(
            campaign_id=raw_csv.stem,
            source_file=rel_path.as_posix(),
            output_dir=out_dir,
            standardized_path=standardized,
        ))
    return sources


def load_standardized(source: CampaignSource) -> pd.DataFrame:
    if not source.standardized_path.exists():
        raise FileNotFoundError(
            f"Missing standardized QC output for campaign '{source.campaign_id}': "
            f"{source.standardized_path}. Run the QC pipeline first (e.g. run_qc.py, "
            f"or let repeated_routes refresh it automatically)."
        )
    df = pd.read_parquet(source.standardized_path)
    df["source_file"] = source.source_file
    return df
