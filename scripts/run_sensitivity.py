"""Sensitivity analysis for the QC v2 pipeline.

Two parts:
1. Profile comparison: reuses the already-generated outputs/{permissive,
   recommended,restrictive} trees (real, full pipeline reruns, each with its
   own config) to compare kept rows, valid distance, and valid duration per
   campaign across all three profiles at once.
2. Isolated recovery_min_duration_s sweep (15/30/60 s): re-applies
   detect_stop_events to the already-standardized recommended-profile
   parquet per campaign, holding every other threshold fixed at recommended's
   values, so this one parameter's effect can be read in isolation.

Read-only w.r.t. data/raw/. Writes only under outputs/sensitivity/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from meteotracker_qc.ventilation_qc import detect_stop_events  # noqa: E402

SENSITIVITY_OUT = ROOT / "outputs" / "sensitivity"
SENSITIVITY_OUT.mkdir(parents=True, exist_ok=True)

PROFILES = ["permissive", "recommended", "restrictive"]


def build_profile_comparison() -> pd.DataFrame:
    rows = []
    recommended_dirs = sorted((ROOT / "outputs" / "recommended").glob("*"))
    recommended_dirs = [d for d in recommended_dirs if d.is_dir()]

    for camp_dir in recommended_dirs:
        campaign_id = camp_dir.name
        row = {"campaign_id": campaign_id}
        for profile in PROFILES:
            profile_dir = ROOT / "outputs" / profile / campaign_id
            parquet_files = list(profile_dir.glob("*_standardized.parquet"))
            if not parquet_files:
                continue
            df = pd.read_parquet(parquet_files[0])
            keep_col = f"keep_{profile}"
            n_rows = len(df)
            n_kept = int(df[keep_col].sum()) if keep_col in df.columns else None
            distance_valid_m = float(df.loc[df[keep_col], "distance_from_previous_m"].sum()) if "distance_from_previous_m" in df.columns else None
            valid_time = df.loc[df[keep_col], "time_utc"].dropna() if "time_utc" in df.columns else pd.Series(dtype="datetime64[ns]")
            duration_valid_s = float((valid_time.max() - valid_time.min()).total_seconds()) if len(valid_time) >= 2 else 0.0
            row.update({
                f"n_rows_{profile}": n_rows,
                f"n_kept_{profile}": n_kept,
                f"pct_kept_{profile}": (n_kept / n_rows) if n_rows else None,
                f"distance_valid_km_{profile}": distance_valid_m / 1000.0 if distance_valid_m is not None else None,
                f"duration_valid_min_{profile}": duration_valid_s / 60.0,
            })
        if "pct_kept_permissive" in row and "pct_kept_restrictive" in row and row["pct_kept_permissive"] is not None and row["pct_kept_restrictive"] is not None:
            row["pct_kept_loss_permissive_to_restrictive"] = row["pct_kept_permissive"] - row["pct_kept_restrictive"]
        rows.append(row)
    return pd.DataFrame(rows)


def build_recovery_sweep() -> pd.DataFrame:
    base_config_path = ROOT / "config" / "qc_recommended.yaml"
    base_config = yaml.safe_load(base_config_path.read_text(encoding="utf-8"))

    recommended_dirs = sorted((ROOT / "outputs" / "recommended").glob("*"))
    recommended_dirs = [d for d in recommended_dirs if d.is_dir()]

    sweep_values = [15.0, 30.0, 60.0]
    rows = []
    for camp_dir in recommended_dirs:
        campaign_id = camp_dir.name
        parquet_files = list(camp_dir.glob("*_standardized.parquet"))
        if not parquet_files:
            continue
        base_df = pd.read_parquet(parquet_files[0])
        n_rows = len(base_df)
        for recovery_s in sweep_values:
            cfg = {**base_config, "stops": {**base_config.get("stops", {}), "recovery_min_duration_s": recovery_s}}
            out = detect_stop_events(base_df, config=cfg)
            n_recovery_rows = int(out["qc_post_stop_recovery"].sum())
            rows.append({
                "campaign_id": campaign_id,
                "recovery_min_duration_s": recovery_s,
                "n_rows": n_rows,
                "n_post_stop_recovery_rows": n_recovery_rows,
                "pct_post_stop_recovery_rows": n_recovery_rows / n_rows if n_rows else None,
                "n_stop_events": int(out["stop_event_id"].dropna().nunique()) if "stop_event_id" in out.columns else None,
            })
    return pd.DataFrame(rows)


def main() -> None:
    profile_comparison = build_profile_comparison()
    profile_comparison.to_csv(SENSITIVITY_OUT / "sensitivity_profile_comparison_v2.csv", index=False)
    print(f"sensitivity_profile_comparison_v2.csv: {len(profile_comparison)} campaigns")

    totals = {}
    for profile in PROFILES:
        col = f"n_kept_{profile}"
        if col in profile_comparison.columns:
            totals[profile] = int(profile_comparison[col].sum())
    print(f"totals (kept rows by profile, true per-profile runs): {totals}")

    recovery_sweep = build_recovery_sweep()
    recovery_sweep.to_csv(SENSITIVITY_OUT / "sensitivity_recovery_duration_sweep.csv", index=False)
    print(f"sensitivity_recovery_duration_sweep.csv: {len(recovery_sweep)} rows")
    print(recovery_sweep.groupby("recovery_min_duration_s")["pct_post_stop_recovery_rows"].agg(["mean", "max"]))


if __name__ == "__main__":
    main()
