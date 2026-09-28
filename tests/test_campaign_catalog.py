from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.analysis_settings import settings_fingerprint
from meteotracker_qc.campaign_catalog import (
    AUDIT_ROOT,
    CATALOG_COLUMNS,
    MATCHING_ALGORITHM_VERSION,
    assert_official_path,
    build_campaign_catalog,
    parse_route,
    write_campaign_catalog,
)
from meteotracker_qc.inventory import inventory_csvs
from meteotracker_qc.repeated_routes.memberships import MEMBERSHIP_KEY
from meteotracker_qc.repeated_routes.pipeline import PipelineResult, write_outputs
from meteotracker_qc.session_qc_pipeline import CONFIG_VERSION
from meteotracker_qc.time_qc import classify_timezone, detect_time_issues
from scientific_fixtures import empty_workspace, write_route


JULY22_ORIGINAL = "2026-07-22T10:42:34+02:00"
JULY22_UTC = "2026-07-22T08:42:34+00:00"


def _catalog_workspace(tmp_path: Path) -> Path:
    root = empty_workspace(tmp_path)
    write_route(root / "data/raw/7-22/20260722T08_42_34_mtdicambo_AC4D162B317E_Bologna-Sasso Marconi.csv", n=30)
    raw = root / "data/raw/7-22/20260722T08_42_34_mtdicambo_AC4D162B317E_Bologna-Sasso Marconi.csv"
    frame = pd.read_csv(raw)
    frame["Time"] = pd.date_range("2026-07-22T10:42:34+02:00", periods=len(frame), freq="s")
    frame.to_csv(raw, index=False)
    from meteotracker_qc.ingestion import core_content_hash, sha256_file
    from meteotracker_qc.pipeline import _campaign_output_dir

    campaign_id = "7-22__20260722T08_42_34_mtdicambo_AC4D162B317E_Bologna-Sasso_Marconi__bcc4dea3ed"
    source_file = "7-22/20260722T08_42_34_mtdicambo_AC4D162B317E_Bologna-Sasso Marconi.csv"
    pd.DataFrame([{
        "source_file": source_file,
        "file_sha256": sha256_file(raw),
        "core_content_hash": core_content_hash(raw),
        "canonical_campaign_id": campaign_id,
        "duplicate_group_id": "",
        "duplicate_type": "",
        "is_canonical": True,
        "canonical_source_file": source_file,
        "exclude_from_analysis": False,
        "exclude_reason": "",
        "keep_raw": True,
        "notes": "test",
    }]).to_csv(root / "data/manifests/campaign_manifest.csv", index=False)

    qc = detect_time_issues(pd.read_csv(raw))
    product_dir = _campaign_output_dir(raw, root / "data/raw", root / "outputs/recommended")
    product_dir.mkdir(parents=True)
    qc.to_parquet(product_dir / f"{raw.stem}_standardized.parquet", index=False)
    pd.DataFrame([{
        "canonical_campaign_id": campaign_id,
        "source_file": raw.name,
        "n_raw": len(qc),
        "n_recommended": int(len(qc) * 0.8),
        "keep_fraction_recommended": 0.8,
        "session_qc_status": "PASS_WITH_WARNINGS",
        "campaign_start_timestamp": "2026-07-22 08:42:34+00:00",
        "campaign_end_timestamp": pd.Timestamp(qc["time_utc"].max()).isoformat(),
        "qc_config_fingerprint": settings_fingerprint(root / "config"),
        "qc_version": CONFIG_VERSION,
    }]).to_csv(root / "outputs/session_qc/session_qc_inventory.csv", index=False)
    pd.DataFrame([
        {"canonical_campaign_id": campaign_id, "analysis_type": "spatial_mapping", "suitability_status": "YES"},
        {"canonical_campaign_id": campaign_id, "analysis_type": "route_comparison", "suitability_status": "YES"},
    ]).to_csv(root / "outputs/session_qc/session_suitability_inventory.csv", index=False)
    return root


def test_july22_offset_converts_exactly_to_utc():
    parsed = pd.to_datetime(JULY22_ORIGINAL, utc=True)
    assert parsed == pd.Timestamp(JULY22_UTC)
    assert parsed.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-07-22T08:42:34Z"


def test_qc_preserves_original_offset_and_utc_local_split():
    frame = pd.DataFrame({
        "Time": [JULY22_ORIGINAL, "2026-07-22T10:42:35+02:00"],
        "Lat": [44.5, 44.5],
        "Lon": [11.3, 11.31],
    })
    out = detect_time_issues(frame)
    assert str(out.loc[0, "time_original"]) == JULY22_ORIGINAL
    assert pd.Timestamp(out.loc[0, "time_utc"]) == pd.Timestamp(JULY22_UTC)
    assert str(out.loc[0, "time_timezone_interpretation"]) == "explicit_offset"
    local = pd.Timestamp(out.loc[0, "time_local"]).tz_convert("Europe/Rome")
    assert local.utcoffset().total_seconds() == 2 * 3600
    assert classify_timezone("file.csv", frame["Time"]) == ("explicit_offset", 1.0)


def test_inventory_records_explicit_offset_instead_of_unknown(tmp_path):
    path = tmp_path / "20260722T08_42_34_mtdicambo_AC4D162B317E_Bologna-Sasso Marconi.csv"
    pd.DataFrame({
        "Time": [JULY22_ORIGINAL],
        "Lat": [44.5],
        "Lon": [11.3],
        "Temp[°C]": [30],
        "Hum[%]": [50],
        "Press[mbar]": [1010],
        "Speed[km/h]": [20],
    }).to_csv(path, index=False)
    inventory = inventory_csvs(tmp_path)
    assert inventory.loc[0, "timezone_original"] == "explicit_offset"
    assert pd.Timestamp(inventory.loc[0, "time_utc_start"]) == pd.Timestamp(JULY22_UTC)
    local = pd.Timestamp(inventory.loc[0, "time_local_start"])
    assert local.tz_convert("Europe/Rome").isoformat().startswith("2026-07-22T10:42:34")


def test_catalog_one_row_per_id_with_fingerprint_and_hash(tmp_path):
    root = _catalog_workspace(tmp_path)
    catalog, provenance = build_campaign_catalog(root)
    assert list(catalog.columns) == CATALOG_COLUMNS
    assert catalog["canonical_campaign_id"].is_unique
    assert len(catalog) == 1
    row = catalog.iloc[0]
    assert (root / "data/raw" / row["source_file"]).exists()
    from meteotracker_qc.ingestion import sha256_file
    assert row["source_sha256"] == sha256_file(root / "data/raw" / row["source_file"])
    assert row["session_qc_status"] == "PASS_WITH_WARNINGS"
    assert row["qc_config_fingerprint"] == settings_fingerprint(root / "config")
    assert row["qc_version"] == CONFIG_VERSION
    assert row["source_git_commit"]
    assert row["spatial_mapping"] == "YES"
    assert row["route_comparison"] == "YES"
    assert row["timezone_interpretation"] == "explicit_offset"
    assert pd.Timestamp(row["time_start_utc"]) == pd.Timestamp(JULY22_UTC)
    assert "+02:00" in str(row["time_original_start"])
    assert provenance["audit_not_used"] is True
    assert provenance["qc_version"] == CONFIG_VERSION
    assert provenance["matching_algorithm_version"] == MATCHING_ALGORITHM_VERSION


def test_catalog_write_and_pending_raw_not_promoted(tmp_path):
    root = _catalog_workspace(tmp_path)
    write_route(root / "data/raw/8-1/20260801T08_39_06_mtdicambo_AC4D162B317E_Anzola dell'Emilia-Bologna.csv", n=12)
    paths = write_campaign_catalog(root)
    catalog = pd.read_csv(paths["catalog"])
    payload = json.loads(paths["provenance"].read_text(encoding="utf-8"))
    assert len(catalog) == 1
    assert payload["n_pending_raw_files"] == 1
    assert payload["pending_raw_files"][0]["promotion_status"] == "PENDING_RAW_NOT_IN_MANIFEST"
    assert "canonical_session" not in catalog.columns


def test_official_path_rejects_audit(tmp_path):
    root = empty_workspace(tmp_path)
    with pytest.raises(ValueError, match="audit"):
        assert_official_path(root / AUDIT_ROOT / "reference44/outputs/repeated_routes", root)


def test_write_outputs_keeps_many_to_many_memberships(tmp_path):
    from shapely.geometry import Point
    point = Point(11.3, 44.5)
    memberships = pd.DataFrame([
        {"membership_id": "m1", "repeated_segment_id": "seg_a", "segment_passage_id": "p1",
         "campaign_id": "c1", "source_file": "a.csv", "source_row": 10, "geometry": point},
        {"membership_id": "m2", "repeated_segment_id": "seg_b", "segment_passage_id": "p2",
         "campaign_id": "c1", "source_file": "a.csv", "source_row": 10, "geometry": point},
    ])
    support = pd.DataFrame([
        {"membership_id": "m1", "supporting_match_id": "match_1"},
        {"membership_id": "m2", "supporting_match_id": "match_2"},
    ])
    result = PipelineResult(
        inventory_df=pd.DataFrame([{"campaign_id": "c1", "source_file": "a.csv", "campaign_quality_flag": "high"}]),
        candidate_pairs_df=pd.DataFrame(),
        candidate_stats={},
        segments_df=pd.DataFrame([
            {"repeated_segment_id": "seg_a", "geometry": point},
            {"repeated_segment_id": "seg_b", "geometry": point},
        ]),
        passages_df=pd.DataFrame([
            {"segment_passage_id": "p1", "geometry": point},
            {"segment_passage_id": "p2", "geometry": point},
        ]),
        matches_df=pd.DataFrame(columns=["supporting_match_id", "repeated_segment_id", "geometry"]),
        comparison_df=pd.DataFrame(),
        campaign_tracks_by_id={},
        standardized_by_campaign={},
        parts_by_track={},
        usable_parts=[],
        timings={},
        cache_stats={},
        point_segment_memberships=memberships,
        point_segment_match_support=support,
    )
    official = tmp_path / "outputs" / "repeated_routes"
    write_outputs(result, official)
    audit = tmp_path / "outputs" / "audit" / "reference44"
    audit.mkdir(parents=True)
    (audit / "copied.csv").write_text("not-official", encoding="utf-8")
    out = pd.read_csv(official / "point_segment_memberships.csv")
    assert not out.duplicated(MEMBERSHIP_KEY).any()
    assert out.groupby(["source_file", "source_row"]).repeated_segment_id.nunique().max() == 2
    assert (official / "repeated_segments.csv").exists()
    assert (official / "segment_passages.csv").exists()
    assert (official / "point_segment_match_support.csv").exists()
    assert "copied.csv" not in {p.name for p in official.iterdir()}
    assert out["campaign_id"].tolist() == ["c1", "c1"]


def test_parse_route_from_existing_filename_pattern():
    assert parse_route("7-22/20260722T08_42_34_mtdicambo_AC4D162B317E_Bologna-Sasso Marconi.csv") == (
        "Bologna", "Sasso Marconi",
    )
    assert parse_route("7-22/20260722T09_17_03_mtdicambo_AC4D162B317E_Sasso Marconi-Bologna.csv") == (
        "Sasso Marconi", "Bologna",
    )
