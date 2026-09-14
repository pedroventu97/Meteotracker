"""Writers for outputs/session_qc/*: 7 CSVs + one JSON per canonical campaign."""
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
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def build_segment_reason_codes(segment_qc: pd.DataFrame, segment_dimensions: list[str]) -> pd.DataFrame:
    reason_cols = [f"segment_{d}_reason_code" for d in segment_dimensions] + ["segment_qc_reason_code"]
    rows = []
    for _, row in segment_qc.iterrows():
        seen = set()
        for col in reason_cols:
            code = row.get(col)
            if pd.isna(code) or code == "" or code in seen:
                continue
            seen.add(code)
            rows.append({
                "canonical_campaign_id": row["canonical_campaign_id"],
                "segment_id": row["segment_id"],
                "reason_code": code,
                "source_column": col,
            })
    return pd.DataFrame(rows)


def build_session_reason_codes(session_qc: pd.DataFrame, session_dimensions: list[str]) -> pd.DataFrame:
    reason_cols = [f"{d}_reason_code" for d in session_dimensions] + ["session_primary_reason"]
    rows = []
    for _, row in session_qc.iterrows():
        seen = set()
        for col in reason_cols:
            code = row.get(col)
            if pd.isna(code) or code == "" or code in seen:
                continue
            seen.add(code)
            rows.append({
                "canonical_campaign_id": row["canonical_campaign_id"],
                "reason_code": code,
                "source_column": col,
            })
    return pd.DataFrame(rows)


def write_policy_snapshot(policy_df: pd.DataFrame, profile: str, output_path: Path) -> None:
    snapshot = policy_df[(policy_df["profile"] == profile) & (policy_df["enabled"].astype(bool))]
    snapshot.to_csv(output_path, index=False)


def write_campaign_json(
    campaign_id: str,
    session_row: pd.Series,
    segment_rows: pd.DataFrame,
    suitability_rows: pd.DataFrame,
    output_root: Path,
    config_version: str,
) -> Path:
    session_dict = {k: _json_safe(v) for k, v in session_row.items()}
    segments_list = [{k: _json_safe(v) for k, v in seg.items()} for _, seg in segment_rows.iterrows()]
    suitability_dict = {}
    for _, s in suitability_rows.iterrows():
        suitability_dict[s["analysis_type"]] = {
            "status": _json_safe(s["suitability_status"]),
            "reason_codes": _json_safe(s["reason_codes"]),
            "qualifying_segments": s["qualifying_segments"].split(";") if s["qualifying_segments"] else [],
            "limiting_dimensions": _json_safe(s["limiting_dimensions"]),
        }
    payload = {
        "canonical_campaign_id": campaign_id,
        "config_version": config_version,
        "session": session_dict,
        "segments": segments_list,
        "suitability": suitability_dict,
    }
    campaign_dir = Path(output_root) / "campaigns" / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    out_path = campaign_dir / "session_qc.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return out_path
