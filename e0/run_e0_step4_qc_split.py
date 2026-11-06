"""E0 Step 4: QC (recommended) on 55 canonical campaigns + split assignments.

Writes ONLY under outputs/e0_qc_split_<timestamp>/. No historical overwrite, no git.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(r"D:\projects\Meteotracker")
sys.path.insert(0, str(ROOT / "src"))

from meteotracker_qc.pipeline import MeteotrackerQC  # noqa: E402

ROME = ZoneInfo("Europe/Rome")
FORBIDDEN_PREFIXES = (
    "recommended_20261015",
    "corridor_passages_20261015",
    "repeated_routes_20261015",
    "pass_anomaly_20261015",
    "short_dt_anomaly_20261015",
    "lst_campaigns_multiday_20261018",
)


def assert_safe_output_root(output_root: Path) -> None:
    resolved = output_root.resolve()
    outputs = (ROOT / "outputs").resolve()
    if not str(resolved).startswith(str(outputs)):
        raise SystemExit(f"Refusing output outside outputs/: {resolved}")
    name = resolved.name
    if not name.startswith("e0_qc_split_"):
        raise SystemExit(f"Refusing non e0_qc_split_* root: {name}")
    for bad in FORBIDDEN_PREFIXES:
        if bad in name or name.startswith(bad):
            raise SystemExit(f"Refusing forbidden path pattern: {name}")
    # never equal historical trees
    for hist in outputs.iterdir():
        if hist.resolve() == resolved and not name.startswith("e0_qc_split_"):
            raise SystemExit(f"Refusing overwrite of {hist}")


def load_canonical_manifest(path: Path) -> pd.DataFrame:
    m = pd.read_csv(path)
    ex = m["exclude_from_analysis"].astype(str).str.lower().isin(["true", "1", "yes"])
    return m.loc[~ex].copy()


def campaign_out_dir(canonical_id: str, output_root: Path) -> Path:
    return output_root / "campaigns" / canonical_id


def summarize_campaign(df: pd.DataFrame, canonical_id: str, source_file: str, metrics_path: Path | None) -> dict:
    flag_cols = [c for c in df.columns if c.startswith("qc_") and df[c].dtype == bool]
    # also treat 0/1 qc flags
    for c in df.columns:
        if c.startswith("qc_") and c not in flag_cols:
            if df[c].dropna().isin([0, 1, True, False]).all() and c not in (
                "qc_severity",
            ):
                try:
                    if set(pd.Series(df[c].dropna().unique()).astype(str)) <= {"0", "1", "True", "False", "true", "false"}:
                        flag_cols.append(c)
                except Exception:
                    pass
    # prefer boolean-like from flag policy names present
    active = {}
    for c in df.columns:
        if not c.startswith("qc_"):
            continue
        if c in ("qc_severity",):
            continue
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            active[c] = int(s.fillna(False).sum())
        else:
            try:
                active[c] = int(pd.to_numeric(s, errors="coerce").fillna(0).astype(bool).sum())
            except Exception:
                continue

    aoi_out = int(df["qc_coord_outside_aoi"].fillna(False).astype(bool).sum()) if "qc_coord_outside_aoi" in df.columns else None
    row = {
        "canonical_campaign_id": canonical_id,
        "source_file": source_file,
        "n_rows": int(len(df)),
        "n_keep_strict": int(df["keep_strict"].sum()) if "keep_strict" in df.columns else None,
        "n_keep_relaxed": int(df["keep_relaxed"].sum()) if "keep_relaxed" in df.columns else None,
        "n_keep_recommended": int(df["keep_recommended"].sum()) if "keep_recommended" in df.columns else None,
        "n_aoi_outside": aoi_out,
        "n_flags_total_row_events": int(sum(active.values())),
        "n_flag_codes_active": int(sum(1 for v in active.values() if v > 0)),
        "max_qc_severity": int(df["qc_severity"].max()) if "qc_severity" in df.columns and len(df) else None,
    }
    # severity histogram
    if "qc_severity" in df.columns:
        vc = df["qc_severity"].value_counts().to_dict()
        for k, v in vc.items():
            row[f"n_severity_{k}"] = int(v)
    # top flag codes into JSON sidecar string
    top = sorted(active.items(), key=lambda kv: kv[1], reverse=True)[:15]
    row["top_flags_json"] = json.dumps(dict(top), ensure_ascii=False)
    if metrics_path and metrics_path.exists():
        row["metrics_path"] = str(metrics_path)
    return row


def main() -> int:
    started = datetime.now(ROME)
    stamp = started.strftime("%Y%m%dT%H%M")
    output_root = ROOT / "outputs" / f"e0_qc_split_{stamp}"
    assert_safe_output_root(output_root)
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "campaigns").mkdir()
    (output_root / "logs").mkdir()

    log_path = output_root / "logs" / "step4_run.log"
    def log(msg: str) -> None:
        line = f"{datetime.now(ROME).isoformat(timespec='seconds')} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    log(f"START output_root={output_root}")
    log(f"Safety OK under e0_qc_split_*; historical 20261015/18 trees untouched")

    # reference inventory (do not regenerate unless needed)
    inv_src = ROOT / "outputs" / "recommended_20261015T0835" / "inventory.csv"
    if inv_src.exists():
        shutil.copy2(inv_src, output_root / "inventory_reference_recommended_20261015T0835.csv")
        log(f"Copied inventory reference from {inv_src.name}")

    manifest = load_canonical_manifest(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    log(f"Canonical campaigns: {len(manifest)}")

    config_path = ROOT / "config" / "qc_recommended.yaml"
    qc = MeteotrackerQC(config_path)
    log(f"QC profile={qc.profile_name} config={config_path}")

    raw_root = ROOT / "data" / "raw"
    summaries = []
    failures = []
    flag_frames = []
    attempted = 0
    succeeded = 0

    for i, row in enumerate(manifest.itertuples(index=False), start=1):
        attempted += 1
        source_file = getattr(row, "source_file")
        canonical_id = getattr(row, "canonical_campaign_id")
        file_sha = getattr(row, "file_sha256", None)
        dup_type = getattr(row, "duplicate_type", None)
        if isinstance(dup_type, float) and np.isnan(dup_type):
            dup_type = None
        input_csv = raw_root / source_file
        out_dir = campaign_out_dir(canonical_id, output_root)
        log(f"[{i}/{len(manifest)}] QC {canonical_id} <- {source_file}")
        try:
            if not input_csv.exists():
                raise FileNotFoundError(f"missing raw csv: {input_csv}")
            out_dir.mkdir(parents=True, exist_ok=True)
            # Skip heavy PNGs; still write parquet/csv/metrics via process_file
            standardized = qc.process_file(input_csv, out_dir, diagnostics=False)
            stem = input_csv.stem
            ft_path = out_dir / f"{stem}_flag_table.csv"
            ft = qc.emit_flag_table(
                standardized,
                ft_path,
                canonical_campaign_id=canonical_id,
                source_file=source_file,
                file_sha256=None if (isinstance(file_sha, float) and np.isnan(file_sha)) else file_sha,
                duplicate_type=None if dup_type is None else str(dup_type),
                config_fingerprint="qc_recommended.yaml",
                code_commit="NO_COMMIT_step4_local",
            )
            flag_frames.append(ft)
            metrics_path = out_dir / f"{stem}_metrics.json"
            summaries.append(summarize_campaign(standardized, canonical_id, source_file, metrics_path))
            # free memory: drop large frame
            del standardized
            succeeded += 1
            log(f"  OK rows_flags={len(ft)} -> {ft_path.name}")
        except Exception as e:
            failures.append(
                {
                    "canonical_campaign_id": canonical_id,
                    "source_file": source_file,
                    "error": str(e),
                    "traceback": traceback.format_exc()[-2000:],
                }
            )
            log(f"  FAIL {e}")
            continue

    # campaign summary
    summary_df = pd.DataFrame(summaries)
    summary_path = output_root / "campaign_summary_E0.csv"
    summary_df.to_csv(summary_path, index=False)
    log(f"Wrote {summary_path.name} n={len(summary_df)}")

    fail_df = pd.DataFrame(failures)
    fail_path = output_root / "FAILED_CAMPAIGNS.csv"
    fail_df.to_csv(fail_path, index=False)
    log(f"Failures: {len(failures)} -> {fail_path.name}")

    # concatenated flag table
    if flag_frames:
        all_flags = pd.concat(flag_frames, ignore_index=True)
        # stable flag_id remumber? keep per-campaign ids but add global index
        all_flags.insert(0, "flag_row_id", np.arange(1, len(all_flags) + 1, dtype=int))
        ft_all_csv = output_root / "flag_table_E0.csv"
        all_flags.to_csv(ft_all_csv, index=False)
        try:
            all_flags.to_parquet(output_root / "flag_table_E0.parquet", index=False)
        except Exception as e:
            log(f"parquet flag_table skip: {e}")
        log(f"flag_table_E0 rows={len(all_flags)}")
        # counts
        code_col = "flag_code" if "flag_code" in all_flags.columns else None
        sev_col = "severity" if "severity" in all_flags.columns else ("flag_severity" if "flag_severity" in all_flags.columns else None)
        counts = {
            "n_flag_rows": int(len(all_flags)),
            "top_flag_codes": all_flags[code_col].value_counts().head(20).to_dict() if code_col else {},
            "severity_breakdown": all_flags[sev_col].value_counts().to_dict() if sev_col else {},
            "columns": list(all_flags.columns),
        }
        (output_root / "flag_table_E0_counts.json").write_text(
            json.dumps(counts, indent=2, default=str), encoding="utf-8"
        )
    else:
        all_flags = pd.DataFrame()
        log("WARNING: no flag tables produced")

    run_meta = {
        "started_local_europe_rome": started.isoformat(timespec="seconds"),
        "finished_local_europe_rome": datetime.now(ROME).isoformat(timespec="seconds"),
        "output_root": str(output_root),
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": len(failures),
        "qc_profile": "recommended",
        "config_path": str(config_path),
        "diagnostics": False,
        "n_flag_rows": int(len(all_flags)),
        "forbidden_trees_untouched": True,
        "git_commit": False,
        "raw_untouched": True,
    }
    (output_root / "STEP4_QC_RUN_META.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
    # pointer for split script
    (output_root / "OUTPUT_ROOT.txt").write_text(str(output_root), encoding="utf-8")
    log(f"DONE QC attempted={attempted} succeeded={succeeded} failed={len(failures)}")
    print(str(output_root))
    return 0 if succeeded > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
