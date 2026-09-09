"""Safe, repeatable ingestion of newly delivered Meteotracker acquisitions."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .inventory import inventory_csvs
from .pipeline import MeteotrackerQC, _campaign_output_dir, run_qc

REQUIRED_COLUMNS = {"Time", "Lat", "Lon", "Temp[°C]", "Hum[%]", "Press[mbar]", "Speed[km/h]"}
PROFILE_NAMES = ("permissive", "recommended", "restrictive")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def core_content_hash(path: Path) -> str:
    frame = pd.read_csv(path, usecols=lambda c: c in {"Time", "Lat", "Lon"}, encoding="utf-8-sig")
    if not {"Time", "Lat", "Lon"}.issubset(frame.columns):
        raise ValueError("missing Time/Lat/Lon columns")
    core = frame[["Time", "Lat", "Lon"]].copy()
    core["Time"] = core["Time"].astype(str).str.strip()
    core["Lat"] = pd.to_numeric(core["Lat"], errors="coerce").round(6)
    core["Lon"] = pd.to_numeric(core["Lon"], errors="coerce").round(6)
    text = "\n".join(f"{t}|{lat}|{lon}" for t, lat, lon in core.itertuples(index=False))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ValidationResult:
    source_file: str
    file_sha256: str
    core_content_hash: str
    size_bytes: int
    rows: int
    columns: int
    classification: str
    canonical_source_file: str
    duplicate_group_id: str
    blocking_errors: list[str]
    warnings: list[str]
    time_start_utc: str | None
    time_end_utc: str | None
    duplicate_timestamps: int
    missing_coordinates: int
    proposed_campaign_id: str

    @property
    def ok(self) -> bool:
        return not self.blocking_errors and self.classification != "ambiguous"


def _bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def validate_file(path: Path, raw_root: Path, manifest: pd.DataFrame) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    rel = path.relative_to(raw_root).as_posix()
    file_hash = sha256_file(path)
    try:
        core_hash = core_content_hash(path)
        frame = pd.read_csv(path, na_values=["-"])
    except Exception as exc:
        return ValidationResult(rel, file_hash, "", path.stat().st_size, 0, 0, "invalid", "", "",
                                [f"CSV unreadable: {type(exc).__name__}: {exc}"], [], None, None, 0, 0, "")

    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        errors.append("missing required columns: " + ", ".join(missing))
    times = pd.to_datetime(frame.get("Time"), errors="coerce", utc=True)
    bad_times = int(times.isna().sum())
    if bad_times:
        errors.append(f"{bad_times} timestamps are not parseable")
    if not times.dropna().is_monotonic_increasing:
        errors.append("timestamps are not monotonically increasing")
    lat = pd.to_numeric(frame.get("Lat"), errors="coerce")
    lon = pd.to_numeric(frame.get("Lon"), errors="coerce")
    missing_coordinates = int((lat.isna() | lon.isna()).sum())
    if missing_coordinates:
        errors.append(f"{missing_coordinates} rows have missing coordinates")
    if ((~lat.between(-90, 90)) | (~lon.between(-180, 180))).fillna(False).any():
        errors.append("coordinates outside WGS84 latitude/longitude bounds")
    duplicate_timestamps = int(frame.get("Time", pd.Series(dtype=object)).duplicated().sum())
    if duplicate_timestamps:
        warnings.append(f"{duplicate_timestamps} duplicate timestamps (handled by QC flags)")

    hash_matches = manifest.loc[manifest.get("file_sha256", pd.Series(dtype=str)).astype(str) == file_hash]
    core_matches = manifest.loc[manifest.get("core_content_hash", pd.Series(dtype=str)).astype(str) == core_hash]
    matches = pd.concat([hash_matches, core_matches]).drop_duplicates(subset=["source_file"])
    canonical_ids = set(matches.get("canonical_campaign_id", pd.Series(dtype=str)).dropna().astype(str))
    if len(canonical_ids) > 1:
        classification, canonical_source, duplicate_group = "ambiguous", "", ""
        errors.append("duplicate evidence points to more than one canonical campaign")
    elif len(matches):
        classification = "redundant"
        canonical_source = str(matches.iloc[0].get("canonical_source_file") or matches.iloc[0]["source_file"])
        duplicate_group = str(matches.iloc[0].get("duplicate_group_id") or "")
    else:
        classification, canonical_source, duplicate_group = "canonical", rel, ""

    proposed_id = _campaign_output_dir(path, raw_root, Path("unused")).name
    return ValidationResult(
        rel, file_hash, core_hash, path.stat().st_size, len(frame), len(frame.columns), classification,
        canonical_source, duplicate_group, errors, warnings,
        str(times.min()) if times.notna().any() else None, str(times.max()) if times.notna().any() else None,
        duplicate_timestamps, missing_coordinates, proposed_id,
    )


def unregistered_files(raw_root: Path, manifest: pd.DataFrame) -> list[Path]:
    registered = set(manifest["source_file"].astype(str))
    return [p for p in sorted(raw_root.rglob("*.csv"))
            if "original_delivery" not in p.parts and p.relative_to(raw_root).as_posix() not in registered]


def manifest_row(result: ValidationResult) -> dict[str, object]:
    canonical = result.classification == "canonical"
    return {
        "source_file": result.source_file,
        "file_sha256": result.file_sha256,
        "core_content_hash": result.core_content_hash,
        "canonical_campaign_id": result.proposed_campaign_id if canonical else "",
        "duplicate_group_id": result.duplicate_group_id,
        "duplicate_type": "" if canonical else "same Time/Lat/Lon trace",
        "is_canonical": canonical,
        "canonical_source_file": result.canonical_source_file,
        "exclude_from_analysis": not canonical,
        "exclude_reason": "" if canonical else "redundant re-export",
        "keep_raw": True,
        "notes": f"{result.columns} columns; {result.rows} rows" + ("; canonical" if canonical else "; redundant"),
    }


def check_campaign(root: Path, campaign: str, run_pipeline_check: bool = True) -> dict[str, object]:
    raw_root = root / "data" / "raw"
    manifest_path = root / "data" / "manifests" / "campaign_manifest.csv"
    manifest = pd.read_csv(manifest_path)
    candidates = unregistered_files(raw_root, manifest)
    selected = [p for p in candidates if p.parent.name == campaign]
    if not selected:
        already = [p for p in raw_root.joinpath(campaign).glob("*.csv")
                   if p.relative_to(raw_root).as_posix() in set(manifest["source_file"].astype(str))]
        return {"campaign": campaign, "status": "already_registered" if already else "not_found",
                "unregistered": [p.relative_to(raw_root).as_posix() for p in candidates], "results": []}
    results = [validate_file(p, raw_root, manifest) for p in selected]
    if run_pipeline_check and all(r.ok for r in results):
        with tempfile.TemporaryDirectory(prefix="meteotracker_ingest_check_") as tmp:
            for profile in PROFILE_NAMES:
                run_qc(raw_root / campaign, Path(tmp) / profile, root / "config" / f"qc_{profile}.yaml",
                       include_all_files=True)
    status = "pass" if all(r.ok for r in results) else "fail"
    planned = []
    for result in results:
        if result.classification == "canonical":
            planned.extend([f"outputs/{profile}/{result.proposed_campaign_id}/" for profile in PROFILE_NAMES])
    planned.extend([
        "data/manifests/campaign_manifest.csv", "outputs/*/inventory.csv", "outputs/session_qc/",
        "outputs/repeated_routes/", "outputs/spatial_density/", "outputs/temporal_drift/",
        f"outputs/ingestion/{campaign}_ingestion_report.json",
    ])
    return {"campaign": campaign, "status": status,
            "unregistered": [p.relative_to(raw_root).as_posix() for p in candidates],
            "results": [asdict(r) | {"ok": r.ok} for r in results], "planned_official_targets": planned}


def write_ingestion_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def apply_manifest_and_qc(root: Path, campaign: str, staging_root: Path, check: dict[str, object]) -> dict[str, object]:
    """Build the new manifest, all three QC profiles and Session QC in staging."""
    raw_root = root / "data" / "raw"
    source_manifest = root / "data" / "manifests" / "campaign_manifest.csv"
    manifest = pd.read_csv(source_manifest)
    result_objects = [ValidationResult(**{k: v for k, v in item.items() if k != "ok"}) for item in check["results"]]
    for result in result_objects:
        if result.source_file not in set(manifest["source_file"].astype(str)):
            manifest = pd.concat([manifest, pd.DataFrame([manifest_row(result)])], ignore_index=True)
    staged_manifest = staging_root / "data" / "manifests" / "campaign_manifest.csv"
    staged_manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(staged_manifest, index=False)

    staged_config = staging_root / "config"
    shutil.copytree(root / "config", staged_config, dirs_exist_ok=True)
    inventory = inventory_csvs(raw_root)
    for profile in PROFILE_NAMES:
        target = staging_root / "outputs" / profile
        shutil.copytree(root / "outputs" / profile, target, dirs_exist_ok=True)
        qc = MeteotrackerQC(root / "config" / f"qc_{profile}.yaml")
        for result in result_objects:
            if result.classification == "canonical":
                raw_path = raw_root / result.source_file
                qc.process_file(raw_path, _campaign_output_dir(raw_path, raw_root, target))
        inventory.to_csv(target / "inventory.csv", index=False)

    from .session_qc_pipeline import run_session_qc
    shutil.copytree(root / "outputs" / "session_qc", staging_root / "outputs" / "session_qc", dirs_exist_ok=True)
    session = run_session_qc(root=staging_root, output_root=staging_root / "outputs" / "session_qc")
    return {"manifest": manifest, "inventory": inventory, "session": session,
            "canonical_ids": sorted(manifest.loc[~_bool_series(manifest["exclude_from_analysis"]), "canonical_campaign_id"].astype(str))}


def promote(staging_root: Path, root: Path, relative_targets: list[Path]) -> None:
    """Promote staged paths with rollback. Existing paths are restored on failure."""
    backup_root = staging_root / "_rollback"
    moved: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for rel in relative_targets:
            source, destination, backup = staging_root / rel, root / rel, backup_root / rel
            if not source.exists():
                raise FileNotFoundError(f"staged target missing: {source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                destination.replace(backup)
                moved.append((backup, destination))
            source.replace(destination)
            installed.append(destination)
    except Exception:
        for destination in reversed(installed):
            if destination.is_dir():
                shutil.rmtree(destination)
            elif destination.exists():
                destination.unlink()
        for backup, destination in reversed(moved):
            backup.replace(destination)
        raise


def build_log_payload(root: Path, campaign: str, check: dict[str, object], before: int, after: int) -> dict[str, object]:
    return {
        "campaign": campaign, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "applied", "canonical_campaigns_before": before, "canonical_campaigns_after": after,
        "validation": check, "raw_hashes_after": {
            item["source_file"]: sha256_file(root / "data" / "raw" / item["source_file"])
            for item in check["results"]
        },
    }
