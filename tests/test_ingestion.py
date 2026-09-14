from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from meteotracker_qc.ingestion import (
    ValidationResult, manifest_row, promote, sha256_file, unregistered_files, validate_file,
)


HEADERS = "Time,Lat,Lon,Temp[°C],Hum[%],Press[mbar],Speed[km/h]\n"
ROW = "2026-08-01T10:00:00+02:00,44.5,11.3,30,50,1010,20\n"
MANIFEST_COLUMNS = [
    "source_file", "file_sha256", "core_content_hash", "canonical_campaign_id",
    "duplicate_group_id", "duplicate_type", "is_canonical", "canonical_source_file",
    "exclude_from_analysis", "exclude_reason", "keep_raw", "notes",
]


def _manifest(rows=()):
    return pd.DataFrame(list(rows), columns=MANIFEST_COLUMNS)


def _write_valid(root: Path, folder="new", name="campaign.csv") -> Path:
    path = root / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADERS + ROW, encoding="utf-8")
    return path


def test_valid_new_campaign_is_canonical_and_raw_is_unchanged(tmp_path):
    raw = tmp_path / "raw"
    path = _write_valid(raw)
    before = sha256_file(path)
    result = validate_file(path, raw, _manifest())
    assert result.ok and result.classification == "canonical"
    assert result.rows == 1
    assert sha256_file(path) == before


def test_manifest_registration_is_idempotent_by_source_file(tmp_path):
    raw = tmp_path / "raw"
    path = _write_valid(raw)
    result = validate_file(path, raw, _manifest())
    manifest = pd.concat([_manifest(), pd.DataFrame([manifest_row(result)])], ignore_index=True)
    assert unregistered_files(raw, manifest) == []
    assert manifest["source_file"].is_unique


def test_unreadable_or_incompatible_file_blocks_ingestion(tmp_path):
    raw = tmp_path / "raw"
    path = raw / "bad" / "bad.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00not-a-csv")
    result = validate_file(path, raw, _manifest())
    assert not result.ok
    assert result.blocking_errors


def test_missing_required_column_blocks_ingestion(tmp_path):
    raw = tmp_path / "raw"
    path = raw / "bad" / "bad.csv"
    path.parent.mkdir(parents=True)
    path.write_text("Time,Lat,Lon\n2026-01-01T00:00:00Z,44,11\n", encoding="utf-8")
    result = validate_file(path, raw, _manifest())
    assert not result.ok
    assert any("missing required columns" in message for message in result.blocking_errors)


def test_known_trace_is_classified_redundant(tmp_path):
    raw = tmp_path / "raw"
    original = _write_valid(raw, "old", "old.csv")
    original_result = validate_file(original, raw, _manifest())
    manifest = pd.DataFrame([manifest_row(original_result)])
    duplicate = _write_valid(raw, "new", "copy.csv")
    result = validate_file(duplicate, raw, manifest)
    assert result.ok and result.classification == "redundant"
    assert result.canonical_source_file == "old/old.csv"


def test_conflicting_duplicate_evidence_is_ambiguous(tmp_path):
    raw = tmp_path / "raw"
    path = _write_valid(raw)
    probe = validate_file(path, raw, _manifest())
    rows = []
    for campaign_id in ("c1", "c2"):
        row = manifest_row(probe)
        row["source_file"] = f"old/{campaign_id}.csv"
        row["canonical_source_file"] = row["source_file"]
        row["canonical_campaign_id"] = campaign_id
        rows.append(row)
    result = validate_file(path, raw, pd.DataFrame(rows))
    assert not result.ok and result.classification == "ambiguous"


def test_promote_replaces_complete_target(tmp_path):
    stage, root = tmp_path / "stage", tmp_path / "root"
    (stage / "outputs" / "x").mkdir(parents=True)
    (root / "outputs" / "x").mkdir(parents=True)
    (stage / "outputs" / "x" / "new.txt").write_text("new")
    (root / "outputs" / "x" / "old.txt").write_text("old")
    promote(stage, root, [Path("outputs/x")])
    assert (root / "outputs" / "x" / "new.txt").read_text() == "new"
    assert not (root / "outputs" / "x" / "old.txt").exists()


def test_output_campaign_id_is_stable(tmp_path):
    raw = tmp_path / "raw"
    path = _write_valid(raw, "8-1", "trip.csv")
    one = validate_file(path, raw, _manifest()).proposed_campaign_id
    two = validate_file(path, raw, _manifest()).proposed_campaign_id
    assert one == two and one.startswith("8-1__trip__")
