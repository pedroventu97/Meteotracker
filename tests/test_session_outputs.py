import json
from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.session_qc.outputs import (
    build_segment_reason_codes,
    build_session_reason_codes,
    write_campaign_json,
    write_policy_snapshot,
)
from meteotracker_qc.session_qc.segment_status import SEGMENT_DIMENSIONS
from meteotracker_qc.session_qc.session_status import SESSION_DIMENSIONS

ROOT = Path(__file__).resolve().parent.parent
SESSION_QC_OUT = ROOT / "outputs" / "session_qc"


def _n_canonical_campaigns(ROOT) -> int:
    manifest = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    return int((~manifest["exclude_from_analysis"].astype(bool)).sum())

REQUIRED_CSVS = [
    "segment_qc_inventory.csv", "session_qc_inventory.csv", "session_suitability_inventory.csv",
    "session_reason_codes.csv", "segment_reason_codes.csv", "session_qc_policy_effective.csv",
]


@pytest.mark.parametrize("filename", REQUIRED_CSVS)
def test_required_output_csv_exists_and_parses(scientific_workspace, filename):
    ROOT = scientific_workspace
    SESSION_QC_OUT = ROOT / "outputs/session_qc"
    path = SESSION_QC_OUT / filename
    assert path.exists(), f"missing required output: {path}"
    df = pd.read_csv(path)
    assert len(df) > 0


def test_session_qc_inventory_has_only_the_canonical_campaigns(scientific_workspace):
    ROOT = scientific_workspace
    SESSION_QC_OUT = ROOT / "outputs/session_qc"
    df = pd.read_csv(SESSION_QC_OUT / "session_qc_inventory.csv")
    assert len(df) == _n_canonical_campaigns(ROOT)
    assert df["canonical_campaign_id"].is_unique


def test_segment_qc_inventory_campaigns_are_subset_of_session_inventory(scientific_workspace):
    ROOT = scientific_workspace
    SESSION_QC_OUT = ROOT / "outputs/session_qc"
    seg = pd.read_csv(SESSION_QC_OUT / "segment_qc_inventory.csv")
    sess = pd.read_csv(SESSION_QC_OUT / "session_qc_inventory.csv")
    assert set(seg["canonical_campaign_id"].unique()) == set(sess["canonical_campaign_id"].unique())
    # n_raw must add up from segments to session, per campaign.
    seg_totals = seg.groupby("canonical_campaign_id")["n_raw"].sum()
    sess_totals = sess.set_index("canonical_campaign_id")["n_raw"]
    pd.testing.assert_series_equal(seg_totals.sort_index(), sess_totals.sort_index(), check_names=False)


def test_suitability_inventory_is_n_canonical_times_6_long_format(scientific_workspace):
    ROOT = scientific_workspace
    SESSION_QC_OUT = ROOT / "outputs/session_qc"
    df = pd.read_csv(SESSION_QC_OUT / "session_suitability_inventory.csv")
    assert len(df) == _n_canonical_campaigns(ROOT) * 6
    assert set(df["analysis_type"].unique()) == {
        "spatial_mapping", "route_comparison", "temporal_drift_analysis",
        "satellite_coincidence", "environment_class_analysis", "full_route_statistics",
    }


def test_every_campaign_has_a_valid_json_file(scientific_workspace):
    ROOT = scientific_workspace
    SESSION_QC_OUT = ROOT / "outputs/session_qc"
    sess = pd.read_csv(SESSION_QC_OUT / "session_qc_inventory.csv")
    for campaign_id in sess["canonical_campaign_id"]:
        json_path = SESSION_QC_OUT / "campaigns" / campaign_id / "session_qc.json"
        assert json_path.exists(), json_path
        with open(json_path, encoding="utf-8") as f:
            payload = json.load(f)
        assert payload["canonical_campaign_id"] == campaign_id
        assert "session" in payload and "segments" in payload and "suitability" in payload
        assert payload["session"]["session_qc_status"] in {"PASS", "PASS_WITH_WARNINGS", "PARTIAL", "REJECT", "NOT_ASSESSABLE"}
        assert len(payload["segments"]) >= 1
        assert len(payload["suitability"]) == 6


def test_reason_codes_present_for_every_non_ok_or_non_pass_status(scientific_workspace):
    ROOT = scientific_workspace
    SESSION_QC_OUT = ROOT / "outputs/session_qc"
    seg = pd.read_csv(SESSION_QC_OUT / "segment_qc_inventory.csv")
    for dim in SEGMENT_DIMENSIONS:
        non_ok = seg[seg[f"segment_{dim}_status"] != "OK"]
        assert non_ok[f"segment_{dim}_reason_code"].notna().all(), f"missing reason code for non-OK segment_{dim}_status"
    sess = pd.read_csv(SESSION_QC_OUT / "session_qc_inventory.csv")
    for dim in SESSION_DIMENSIONS:
        non_ok = sess[sess[f"{dim}_status"] != "OK"]
        assert non_ok[f"{dim}_reason_code"].notna().all(), f"missing reason code for non-OK {dim}_status"
    non_pass = sess[sess["session_qc_status"] != "PASS"]
    assert non_pass["session_primary_reason"].notna().all()


def test_no_double_counting_of_redundant_files(scientific_workspace):
    ROOT = scientific_workspace
    SESSION_QC_OUT = ROOT / "outputs/session_qc"
    manifest = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    canonical = manifest.loc[~manifest["exclude_from_analysis"].astype(bool)]
    n_canonical = len(canonical)
    assert n_canonical == 8
    assert manifest["exclude_from_analysis"].astype(bool).sum() == 1

    sess = pd.read_csv(SESSION_QC_OUT / "session_qc_inventory.csv")
    assert set(sess["canonical_campaign_id"]) == set(canonical["canonical_campaign_id"])

    # If a redundant file's rows were double-counted (either as an extra row or
    # folded a second time into an existing row), the total n_raw would exceed the
    # true raw-row count for the canonical files -- computed directly from
    # data/raw/ (never hardcoded) so this stays correct as campaigns are added.
    total_raw_rows = 0
    for source_file in canonical["source_file"]:
        raw_path = ROOT / "data" / "raw" / source_file
        assert raw_path.exists(), f"raw file missing: {source_file}"
        with open(raw_path, encoding="utf-8", errors="ignore") as f:
            total_raw_rows += sum(1 for _ in f) - 1  # minus header row
    assert len(sess) == n_canonical
    assert int(sess["n_raw"].sum()) == total_raw_rows


def test_policy_snapshot_matches_declared_profile(scientific_workspace):
    ROOT = scientific_workspace
    SESSION_QC_OUT = ROOT / "outputs/session_qc"
    policy = pd.read_csv(ROOT / "config" / "session_qc_policy.csv")
    snapshot = pd.read_csv(SESSION_QC_OUT / "session_qc_policy_effective.csv")
    assert set(snapshot["profile"].unique()) == {"recommended_session"}
    expected = policy[(policy["profile"] == "recommended_session") & (policy["enabled"].astype(bool))]
    assert len(snapshot) == len(expected)


def test_build_reason_code_helpers_are_deduplicated_per_subject():
    seg_qc = pd.DataFrame([{
        "canonical_campaign_id": "c", "segment_id": 0,
        "segment_sampling_integrity_reason_code": "LONG_GAP",
        "segment_gps_quality_reason_code": "LONG_GAP",  # duplicate on purpose
        "segment_thermal_quality_reason_code": None,
        "segment_ventilation_risk_reason_code": None,
        "segment_stabilization_reason_code": None,
        "segment_spatial_continuity_reason_code": None,
        "segment_qc_reason_code": "LONG_GAP",
    }])
    out = build_segment_reason_codes(seg_qc, SEGMENT_DIMENSIONS)
    assert len(out) == 1  # deduplicated, not one row per source column
    assert out["reason_code"].iloc[0] == "LONG_GAP"
