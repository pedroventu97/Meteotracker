"""Official campaign catalog: a consolidated view of existing Meteotracker products.

This module does not assign new identities. `canonical_campaign_id` remains the
manifest key. The catalog never reads `outputs/audit/`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .analysis_settings import settings_fingerprint
from .ingestion import unregistered_files, validate_file
from .pipeline import _campaign_output_dir
from .repeated_routes.provenance import MATCHING_ALGORITHM_VERSION, matching_config_fingerprint
from .session_qc_pipeline import CONFIG_VERSION

UNAVAILABLE = "NOT_AVAILABLE"
UNKNOWN = "UNKNOWN"
OFFICIAL_REPEATED_ROUTES = Path("outputs/repeated_routes")
OFFICIAL_CATALOG = Path("outputs/campaign_catalog.csv")
OFFICIAL_CATALOG_PROVENANCE = Path("outputs/campaign_catalog_provenance.json")
AUDIT_ROOT = Path("outputs/audit")
LOCAL_TZ = "Europe/Rome"

CATALOG_COLUMNS = [
    "canonical_campaign_id",
    "source_file",
    "source_sha256",
    "date_local",
    "time_start_utc",
    "time_end_utc",
    "time_start_local",
    "time_end_local",
    "time_original_start",
    "time_original_end",
    "timezone_interpretation",
    "route_origin",
    "route_destination",
    "n_raw_points",
    "n_keep_recommended",
    "keep_fraction_recommended",
    "session_qc_status",
    "spatial_mapping",
    "route_comparison",
    "recommended_product",
    "recommended_product_sha256",
    "qc_config_fingerprint",
    "qc_version",
    "core_content_hash",
    "source_git_commit",
    "catalog_generated_at_utc",
]


def assert_official_path(path: Path, workspace: Path) -> Path:
    resolved = path.resolve()
    audit = (workspace / AUDIT_ROOT).resolve()
    try:
        resolved.relative_to(audit)
    except ValueError:
        return resolved
    raise ValueError(f"Official catalog/products must not be read from or written to audit path: {resolved}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(workspace: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True, timeout=10, check=True,
        )
        return result.stdout.strip() or UNAVAILABLE
    except Exception:
        return UNAVAILABLE


def canonical_manifest(workspace: Path) -> pd.DataFrame:
    manifest = pd.read_csv(workspace / "data/manifests/campaign_manifest.csv")
    excluded = manifest["exclude_from_analysis"].astype(str).str.lower().isin({"true", "1", "yes"})
    canonical = manifest.loc[~excluded].copy()
    ids = canonical["canonical_campaign_id"].astype(str)
    if ids.isna().any() or (ids == "").any() or not ids.is_unique:
        raise ValueError("Canonical campaign IDs in the manifest must be non-null and unique")
    return canonical


def parse_route(source_file: str) -> tuple[str, str]:
    stem = Path(source_file).stem
    if " (" in stem:
        stem = stem[: stem.rfind(" (")]
    token = stem.split("_")[-1] if "_" in stem else stem
    if "-" not in token:
        return UNKNOWN, UNKNOWN
    origin, destination = token.split("-", 1)
    origin, destination = origin.strip(), destination.strip()
    return origin or UNKNOWN, destination or UNKNOWN


def _iso(value) -> str:
    if value is None:
        return UNAVAILABLE
    try:
        if pd.isna(value):
            return UNAVAILABLE
    except (TypeError, ValueError):
        pass
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return UNAVAILABLE
    return ts.isoformat()


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def recommended_product_path(workspace: Path, source_file: str) -> Path:
    raw_root = workspace / "data/raw"
    return _campaign_output_dir(raw_root / source_file, raw_root, workspace / "outputs/recommended") / (
        f"{Path(source_file).stem}_standardized.parquet"
    )


def times_from_recommended(parquet_path: Path) -> dict[str, str]:
    missing = {
        "time_start_utc": UNAVAILABLE,
        "time_end_utc": UNAVAILABLE,
        "time_start_local": UNAVAILABLE,
        "time_end_local": UNAVAILABLE,
        "time_original_start": UNAVAILABLE,
        "time_original_end": UNAVAILABLE,
        "timezone_interpretation": UNAVAILABLE,
        "date_local": UNAVAILABLE,
    }
    if not parquet_path.exists():
        return missing
    frame = pd.read_parquet(parquet_path)
    utc = frame["time_utc"] if "time_utc" in frame.columns else pd.Series(dtype="datetime64[ns, UTC]")
    utc = pd.to_datetime(utc, utc=True, errors="coerce")
    local = frame["time_local"] if "time_local" in frame.columns else pd.Series(dtype=object)
    local = pd.to_datetime(local, errors="coerce")
    if local.dt.tz is None and utc.notna().any():
        local = utc.dt.tz_convert(LOCAL_TZ)
    original = frame["time_original"] if "time_original" in frame.columns else frame.get("time_raw", pd.Series(dtype=object))
    tz = frame["time_timezone_interpretation"] if "time_timezone_interpretation" in frame.columns else pd.Series(dtype=object)
    date_local = UNAVAILABLE
    if local.notna().any():
        first_local = pd.Timestamp(local.dropna().iloc[0])
        if first_local.tzinfo is None and utc.notna().any():
            first_local = pd.Timestamp(utc.dropna().iloc[0]).tz_convert(LOCAL_TZ)
        date_local = str(first_local.tz_convert(LOCAL_TZ).date()) if first_local.tzinfo else str(first_local.date())
    interpretation = UNAVAILABLE
    if tz.notna().any():
        interpretation = str(tz.dropna().iloc[0])
    return {
        "time_start_utc": _iso(utc.min()) if utc.notna().any() else UNAVAILABLE,
        "time_end_utc": _iso(utc.max()) if utc.notna().any() else UNAVAILABLE,
        "time_start_local": _iso(local.min()) if local.notna().any() else UNAVAILABLE,
        "time_end_local": _iso(local.max()) if local.notna().any() else UNAVAILABLE,
        "time_original_start": str(original.dropna().iloc[0]) if original.dropna().astype(str).str.strip().ne("").any() else UNAVAILABLE,
        "time_original_end": str(original.dropna().iloc[-1]) if original.dropna().astype(str).str.strip().ne("").any() else UNAVAILABLE,
        "timezone_interpretation": interpretation,
        "date_local": date_local,
    }


def times_from_session_qc(row: pd.Series) -> dict[str, str]:
    start = pd.to_datetime(row.get("campaign_start_timestamp"), utc=True, errors="coerce")
    end = pd.to_datetime(row.get("campaign_end_timestamp"), utc=True, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return {}
    return {
        "time_start_utc": start.isoformat(),
        "time_end_utc": end.isoformat(),
        "time_start_local": start.tz_convert(LOCAL_TZ).isoformat(),
        "time_end_local": end.tz_convert(LOCAL_TZ).isoformat(),
        "date_local": str(start.tz_convert(LOCAL_TZ).date()),
    }


def suitability_status(suitability: pd.DataFrame, campaign_id: str, analysis_type: str) -> str:
    if suitability.empty:
        return UNAVAILABLE
    selected = suitability.loc[
        (suitability["canonical_campaign_id"].astype(str) == campaign_id)
        & (suitability["analysis_type"] == analysis_type)
    ]
    if selected.empty:
        return UNAVAILABLE
    value = selected.iloc[0]["suitability_status"]
    return UNAVAILABLE if pd.isna(value) or value == "" else str(value)


def pending_raw_rows(workspace: Path, manifest: pd.DataFrame) -> list[dict[str, object]]:
    raw_root = workspace / "data/raw"
    if not raw_root.exists():
        return []
    rows = []
    for path in unregistered_files(raw_root, manifest):
        result = validate_file(path, raw_root, manifest)
        rows.append({
            "source_file": result.source_file,
            "file_sha256": result.file_sha256,
            "classification": result.classification,
            "proposed_campaign_id": result.proposed_campaign_id or UNAVAILABLE,
            "ok": result.ok,
            "blocking_errors": "; ".join(result.blocking_errors) if result.blocking_errors else "",
            "warnings": "; ".join(result.warnings) if result.warnings else "",
            "time_start_utc": result.time_start_utc or UNAVAILABLE,
            "time_end_utc": result.time_end_utc or UNAVAILABLE,
            "rows": result.rows,
            "promotion_status": "PENDING_RAW_NOT_IN_MANIFEST",
        })
    return rows


def build_campaign_catalog(workspace: str | Path) -> tuple[pd.DataFrame, dict[str, object]]:
    workspace = Path(workspace).resolve()
    catalog_path = assert_official_path(workspace / OFFICIAL_CATALOG, workspace)
    assert_official_path(workspace / OFFICIAL_REPEATED_ROUTES, workspace)
    generated_at = datetime.now(timezone.utc).isoformat()
    commit = git_commit(workspace)
    canonical = canonical_manifest(workspace)
    full_manifest = pd.read_csv(workspace / "data/manifests/campaign_manifest.csv")
    session_qc = _read_csv_if_exists(workspace / "outputs/session_qc/session_qc_inventory.csv")
    suitability = _read_csv_if_exists(workspace / "outputs/session_qc/session_suitability_inventory.csv")
    session_by_id = (
        session_qc.set_index("canonical_campaign_id") if not session_qc.empty and "canonical_campaign_id" in session_qc.columns
        else pd.DataFrame()
    )
    try:
        fingerprint = settings_fingerprint(workspace / "config")
    except FileNotFoundError:
        fingerprint = UNAVAILABLE
    matching_fp = UNAVAILABLE
    matching_version = MATCHING_ALGORITHM_VERSION
    rr_prov_path = workspace / OFFICIAL_REPEATED_ROUTES / "provenance.json"
    if rr_prov_path.exists():
        payload = json.loads(rr_prov_path.read_text(encoding="utf-8"))
        matching_fp = payload.get("matching_config_fingerprint") or UNAVAILABLE
        matching_version = payload.get("matching_algorithm_version") or MATCHING_ALGORITHM_VERSION
    elif (workspace / "config/repeated_routes_recommended.yaml").exists():
        from .repeated_routes.config import load_config
        matching_fp = matching_config_fingerprint(
            load_config(str(workspace / "config/repeated_routes_recommended.yaml")),
            workspace / "config/repeated_routes_recommended.yaml",
        )

    rows = []
    for record in canonical.to_dict("records"):
        campaign_id = str(record["canonical_campaign_id"])
        source_file = str(record["source_file"])
        session_row = session_by_id.loc[campaign_id] if campaign_id in session_by_id.index else None
        product = recommended_product_path(workspace, source_file)
        times = times_from_recommended(product)
        if times["time_start_utc"] == UNAVAILABLE and session_row is not None:
            times.update({k: v for k, v in times_from_session_qc(session_row).items() if times.get(k, UNAVAILABLE) == UNAVAILABLE})
        session_fingerprint = UNAVAILABLE
        if session_row is not None and "qc_config_fingerprint" in session_row.index and pd.notna(session_row["qc_config_fingerprint"]):
            session_fingerprint = str(session_row["qc_config_fingerprint"])
        elif fingerprint != UNAVAILABLE:
            session_fingerprint = fingerprint
        n_raw = int(session_row["n_raw"]) if session_row is not None and pd.notna(session_row.get("n_raw")) else UNAVAILABLE
        n_keep = int(session_row["n_recommended"]) if session_row is not None and pd.notna(session_row.get("n_recommended")) else UNAVAILABLE
        keep_fraction = (
            float(session_row["keep_fraction_recommended"])
            if session_row is not None and pd.notna(session_row.get("keep_fraction_recommended"))
            else UNAVAILABLE
        )
        origin, destination = parse_route(source_file)
        raw_path = workspace / "data/raw" / source_file
        source_hash = str(record.get("file_sha256") or UNAVAILABLE)
        if raw_path.exists() and source_hash in {"", "nan", UNAVAILABLE}:
            source_hash = sha256_file(raw_path)
        rows.append({
            "canonical_campaign_id": campaign_id,
            "source_file": source_file,
            "source_sha256": source_hash,
            "date_local": times["date_local"],
            "time_start_utc": times["time_start_utc"],
            "time_end_utc": times["time_end_utc"],
            "time_start_local": times["time_start_local"],
            "time_end_local": times["time_end_local"],
            "time_original_start": times["time_original_start"],
            "time_original_end": times["time_original_end"],
            "timezone_interpretation": times["timezone_interpretation"],
            "route_origin": origin,
            "route_destination": destination,
            "n_raw_points": n_raw,
            "n_keep_recommended": n_keep,
            "keep_fraction_recommended": keep_fraction,
            "session_qc_status": str(session_row["session_qc_status"]) if session_row is not None else UNAVAILABLE,
            "spatial_mapping": suitability_status(suitability, campaign_id, "spatial_mapping"),
            "route_comparison": suitability_status(suitability, campaign_id, "route_comparison"),
            "recommended_product": product.relative_to(workspace).as_posix() if product.exists() else UNAVAILABLE,
            "recommended_product_sha256": sha256_file(product) if product.exists() else UNAVAILABLE,
            "qc_config_fingerprint": session_fingerprint,
            "qc_version": str(session_row["qc_version"]) if session_row is not None and "qc_version" in session_row.index and pd.notna(session_row.get("qc_version")) else CONFIG_VERSION,
            "core_content_hash": str(record.get("core_content_hash") or UNAVAILABLE),
            "source_git_commit": commit,
            "catalog_generated_at_utc": generated_at,
        })

    catalog = pd.DataFrame(rows, columns=CATALOG_COLUMNS)
    pending = pending_raw_rows(workspace, full_manifest)
    provenance = {
        "product_status": "OFFICIAL",
        "canonical_definition": (
            "A campaign is canonical iff it is listed in data/manifests/campaign_manifest.csv "
            "with exclude_from_analysis=false and a unique non-empty canonical_campaign_id. "
            "The catalog is a view of that identity plus existing QC/session-QC/recommended products."
        ),
        "generated_at_utc": generated_at,
        "source_git_commit": commit,
        "qc_version": CONFIG_VERSION,
        "qc_config_fingerprint": fingerprint,
        "matching_algorithm_version": matching_version,
        "matching_config_fingerprint": matching_fp,
        "n_canonical_campaigns": int(len(catalog)),
        "n_pending_raw_files": int(len(pending)),
        "pending_raw_files": pending,
        "official_paths": {
            "campaign_catalog": OFFICIAL_CATALOG.as_posix(),
            "recommended": "outputs/recommended",
            "session_qc": "outputs/session_qc",
            "repeated_routes": OFFICIAL_REPEATED_ROUTES.as_posix(),
            "memberships": "outputs/repeated_routes/point_segment_memberships.csv",
        },
        "audit_root": AUDIT_ROOT.as_posix(),
        "audit_not_used": True,
        "unavailable_policy": (
            "NOT_AVAILABLE means the upstream official product did not exist at catalog generation. "
            "UNKNOWN means the value could not be parsed from an existing product without invention."
        ),
    }
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    return catalog, provenance


def write_campaign_catalog(workspace: str | Path) -> dict[str, Path]:
    workspace = Path(workspace).resolve()
    catalog, provenance = build_campaign_catalog(workspace)
    catalog_path = assert_official_path(workspace / OFFICIAL_CATALOG, workspace)
    provenance_path = assert_official_path(workspace / OFFICIAL_CATALOG_PROVENANCE, workspace)
    catalog.to_csv(catalog_path, index=False)
    provenance["catalog_sha256"] = sha256_file(catalog_path)
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {"catalog": catalog_path, "provenance": provenance_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the official Meteotracker campaign catalog")
    parser.add_argument("--workspace", default=".", help="Meteotracker workspace root")
    args = parser.parse_args(argv)
    paths = write_campaign_catalog(args.workspace)
    print(f"catalog: {paths['catalog']}")
    print(f"provenance: {paths['provenance']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
