"""Writers for the 8 machine-readable outputs (7 CSV + 1 JSON per campaign)
under outputs/temporal_drift/. Mirrors session_qc/outputs.py's _json_safe /
write_campaign_json convention for consistency across phases.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def _json_safe(value):
    if isinstance(value, pd.Timestamp):
        return value.isoformat() if pd.notna(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if pd.isna(value) if not isinstance(value, (list, dict)) else False:
        return None
    return value


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _json_safe(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def write_campaign_json(
    campaign_id: str, session_row: dict, groups: pd.DataFrame, visits: pd.DataFrame,
    pairs: pd.DataFrame, model_comparison: pd.DataFrame, sensitivity: pd.DataFrame,
    output_root: Path, config_version: str,
) -> Path:
    payload = {
        "canonical_campaign_id": campaign_id, "config_version": config_version,
        "session": {k: _json_safe(v) for k, v in session_row.items()},
        "groups": _records(groups), "visits": _records(visits), "pairs": _records(pairs),
        "model_comparison": _records(model_comparison), "sensitivity": _records(sensitivity),
    }
    out_dir = output_root / "campaigns" / campaign_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "temporal_diagnostics.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return out_path


def write_detrended_experimental_csv(campaign_id: str, detrending_df: pd.DataFrame, output_root: Path) -> Path:
    out_dir = output_root / "campaigns" / campaign_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "detrended_experimental.csv"
    detrending_df.to_csv(out_path, index=False)
    return out_path
