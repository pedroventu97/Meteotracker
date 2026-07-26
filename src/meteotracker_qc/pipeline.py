from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import yaml

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from .derived_variables import recompute_derived_variables
from .gps_qc import detect_gps_issues
from .inventory import inventory_csvs
from .meteo_qc import detect_meteo_issues
from .stabilization import detect_sensor_stabilization
from .time_qc import classify_timezone, detect_time_issues


def _campaign_output_dir(input_csv: Path, input_root: Path, output_root: Path) -> Path:
    relative_path = input_csv.relative_to(input_root)
    digest = hashlib.sha1(relative_path.as_posix().encode("utf-8")).hexdigest()[:10]
    slug = relative_path.with_suffix("").as_posix().replace("/", "__").replace(" ", "_")
    return output_root / f"{slug}__{digest}"


class MeteotrackerQC:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))

    def _write_diagnostic_artifacts(self, standardized: pd.DataFrame, output_path: Path) -> None:
        temp_series = pd.to_numeric(standardized.get("Temp[°C]", pd.Series(index=standardized.index, dtype=float)), errors="coerce")
        lat_series = pd.to_numeric(standardized.get("Lat", pd.Series(index=standardized.index, dtype=float)), errors="coerce")
        lon_series = pd.to_numeric(standardized.get("Lon", pd.Series(index=standardized.index, dtype=float)), errors="coerce")
        time_series = standardized.get("time_utc", pd.Series(index=standardized.index, dtype="datetime64[ns, UTC]"))

        fig, ax = plt.subplots(figsize=(10, 4))
        if temp_series.notna().any() and time_series.notna().any():
            ax.plot(time_series, temp_series, color="#0f766e", linewidth=1.2)
            ax.set_ylabel("Temp [°C]")
            ax.set_xlabel("Time UTC")
        else:
            ax.text(0.5, 0.5, "Temperature or time data unavailable", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(output_path / "diagnostic_plot.png", dpi=150)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(5, 5))
        if lat_series.notna().any() and lon_series.notna().any():
            ax.plot(lon_series, lat_series, color="#1d4ed8", linewidth=1.0, alpha=0.8)
            ax.scatter(lon_series.iloc[0], lat_series.iloc[0], c="#16a34a", s=20, label="start")
            ax.scatter(lon_series.iloc[-1], lat_series.iloc[-1], c="#dc2626", s=20, label="end")
            ax.set_xlabel("Lon")
            ax.set_ylabel("Lat")
            ax.legend(loc="best", fontsize=8)
        else:
            ax.text(0.5, 0.5, "Geographic data unavailable", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(output_path / "route_map.png", dpi=150)
        plt.close(fig)

    def process_file(self, input_csv: str | Path, output_dir: str | Path) -> pd.DataFrame:
        input_path = Path(input_csv)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        raw = pd.read_csv(input_path)
        raw["source_file"] = input_path.name
        raw["source_row"] = np.arange(len(raw), dtype=int)
        raw["device_id"] = input_path.stem.split("_")[-2] if "_" in input_path.stem else "unknown"
        raw["campaign_id"] = input_path.stem
        standardized = detect_time_issues(raw)
        standardized = detect_gps_issues(standardized, config=self.config)
        standardized = detect_meteo_issues(standardized, self.config.get("physical_limits", {}))
        standardized = recompute_derived_variables(standardized)
        warm = detect_sensor_stabilization(standardized.get("Temp[°C]", pd.Series(dtype=float)), config=self.config)
        standardized = standardized.join(warm)

        # Simple analytical eligibility rules, reversible by flags.
        standardized["instrument_valid"] = True
        standardized["gps_valid"] = ~(standardized["qc_gps_freeze"] | standardized["qc_gps_jump"])
        standardized["use_for_raw_timeseries"] = ~(standardized["qc_time_gap"] | standardized["qc_time_duplicate"])
        standardized["use_for_route_mapping"] = standardized["gps_valid"]
        standardized["use_for_spatial_aggregation"] = standardized["gps_valid"] & (~standardized["qc_sensor_stabilization"])
        standardized["qc_severity"] = standardized[[
            "qc_time_gap", "qc_gps_jump", "qc_temp_spike", "qc_sensor_stabilization"
        ]].astype(int).sum(axis=1)
        standardized["qc_reasons"] = standardized.apply(lambda row: ", ".join([
            name for name in [
                "time_gap" if row["qc_time_gap"] else None,
                "time_duplicate" if row["qc_time_duplicate"] else None,
                "gps_jump" if row["qc_gps_jump"] else None,
                "gps_freeze" if row["qc_gps_freeze"] else None,
                "temp_spike" if row["qc_temp_spike"] else None,
                "sensor_stabilization" if row["qc_sensor_stabilization"] else None,
            ] if name is not None
        ]), axis=1)
        standardized["qc_bitmask"] = standardized["qc_severity"]
        filtering_cfg = self.config.get("filtering", {})
        relaxed_budget = int(filtering_cfg.get("relaxed_keep_threshold", 1))
        strict_budget = int(filtering_cfg.get("strict_keep_threshold", 0))
        standardized["keep_relaxed"] = standardized["qc_severity"] <= relaxed_budget
        standardized["keep_strict"] = standardized["qc_severity"] <= strict_budget
        standardized["timezone_classification"], standardized["timezone_confidence"] = classify_timezone(input_path.name, standardized.get("time_raw", pd.Series(dtype=object)))
        timezone_safe = standardized["timezone_classification"].isin({
            "explicit_utc",
            "explicit_offset",
            "inferred_utc_high_confidence",
            "inferred_local_high_confidence",
        })
        standardized["use_for_satellite_comparison"] = standardized["use_for_raw_timeseries"] & standardized["gps_valid"] & (~standardized["qc_sensor_stabilization"]) & timezone_safe

        config_snapshot = yaml.safe_dump(self.config, sort_keys=False, allow_unicode=True)
        (output_path / "config_used.yaml").write_text(config_snapshot, encoding="utf-8")
        self._write_diagnostic_artifacts(standardized, output_path)

        standardized.to_parquet(output_path / f"{input_path.stem}_standardized.parquet", index=False)
        standardized.to_csv(output_path / f"{input_path.stem}_flagged.csv", index=False)
        standardized.loc[standardized["keep_strict"]].to_csv(output_path / f"{input_path.stem}_strict.csv", index=False)
        standardized.loc[standardized["keep_relaxed"]].to_csv(output_path / f"{input_path.stem}_relaxed.csv", index=False)

        with open(output_path / f"{input_path.stem}_metrics.json", "w", encoding="utf-8") as f:
            json.dump({
                "rows": int(len(standardized)),
                "strict_rows": int(standardized["keep_strict"].sum()),
                "relaxed_rows": int(standardized["keep_relaxed"].sum()),
                "flags": standardized["qc_severity"].describe().to_dict(),
            }, f, indent=2)

        report_text = (
            "# QC diagnostics\n\n"
            f"- File: {input_path.name}\n"
            f"- Rows: {len(standardized)}\n"
            f"- Strict keep: {int(standardized['keep_strict'].sum())}\n"
            f"- Relaxed keep: {int(standardized['keep_relaxed'].sum())}\n"
            f"- Max severity: {int(standardized['qc_severity'].max())}\n"
        )
        (output_path / f"{input_path.stem}_report.md").write_text(report_text, encoding="utf-8")
        return standardized

    def inventory(self, input_dir: str | Path) -> pd.DataFrame:
        return inventory_csvs(input_dir)


def _load_excluded_files(manifest_path: Path) -> set[str]:
    """Read campaign_manifest.csv and return the set of source_file values (relative
    to the raw-data root) that are marked as redundant re-exports, if the manifest
    exists. Returns an empty set (no filtering) if there is no manifest to read."""
    if not manifest_path.exists():
        return set()
    manifest_df = pd.read_csv(manifest_path)
    if "source_file" not in manifest_df.columns or "exclude_from_analysis" not in manifest_df.columns:
        return set()
    excluded = manifest_df.loc[manifest_df["exclude_from_analysis"].astype(bool), "source_file"]
    return set(excluded.astype(str))


def run_qc(
    input_dir: str | Path,
    output_dir: str | Path,
    config_path: str | Path,
    include_all_files: bool = False,
    manifest_path: str | Path | None = None,
) -> pd.DataFrame:
    qc = MeteotrackerQC(config_path)
    input_root = Path(input_dir)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    inventory_df = qc.inventory(input_root)
    inventory_df.to_csv(output_root / "inventory.csv", index=False)

    csv_files = sorted(input_root.rglob("*.csv"))
    if not include_all_files:
        if manifest_path is None:
            manifest_path = input_root.parent / "manifests" / "campaign_manifest.csv"
        excluded = _load_excluded_files(Path(manifest_path))
        if excluded:
            csv_files = [f for f in csv_files if f.relative_to(input_root).as_posix() not in excluded]

    for csv_file in csv_files:
        campaign_dir = _campaign_output_dir(csv_file, input_root, output_root)
        qc.process_file(csv_file, campaign_dir)
    return inventory_df
