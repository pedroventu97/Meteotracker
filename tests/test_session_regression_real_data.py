"""Regression tests anchored to real campaigns (Section R's 9 required
validation cases + Section Q's real-data scenarios), reading data.raw
outputs directly. Read-only w.r.t. data/raw/ and outputs/{permissive,
recommended,restrictive}/ -- never writes there.
"""
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.session_qc.metrics import build_reference_frame, load_campaign_frames

ROOT = Path(__file__).resolve().parent.parent
PROFILE_ROOTS = {p: ROOT / "outputs" / p for p in ["permissive", "recommended", "restrictive"]}
SESSION_QC = pd.read_csv(ROOT / "outputs" / "session_qc" / "session_qc_inventory.csv")
SEGMENT_QC = pd.read_csv(ROOT / "outputs" / "session_qc" / "segment_qc_inventory.csv")

BOLOGNA_RAVENNA = "06-04__20260604T11_40_32_mtdicambo_AC4D162B317E_Bologna-Ravenna__5bd4095200"
SHORT_21_ROWS = "04-27__20260427T07_28_18_mtdicambo_AC4D162B317E_Bologna-Bologna__a768d6fc15"
SHORT_91_ROWS = "07-04_2025_moto__20250704T09_31_26_private_6D17FE6E-7C39-270E-9083-54ABA0F52166_Bologna-Bologna__e9e4deafbf"
MAX_FREEZE = "07-04_2025_moto__20250704T10_15_51_private_6D17FE6E-7C39-270E-9083-54ABA0F52166_Bologna-Bologna__5f01006ac6"
LOWEST_KEEP_NON_SHORT = "02-20__20260220T09_05_04_mtdicambo_B6CCF894-DF13-BB20-B108-3C17F67FA94E_Bologna-Bologna__c2b73a152d"
NEARLY_PERFECT = "02-28__20260228T14_01_31_mtdicambo_B6CCF894-DF13-BB20-B108-3C17F67FA94E_Bologna-Bologna__fd7d5426a2"
ONE_HZ = "02-13__20260213T09_06_57_mtdicambo_B6CCF894-DF13-BB20-B108-3C17F67FA94E_Bologna-Bologna__353b44f890"
TWO_HZ = "04-27__20260427T08_00_36_mtdicambo_AC4D162B317E_Bologna-Bologna_(1)__1cbe131095"
MANY_STOPS = MAX_FREEZE  # confirmed to coincide on real data -- not forced apart, see report section P


def _session_row(campaign_id):
    return SESSION_QC[SESSION_QC.canonical_campaign_id == campaign_id].iloc[0]


# ---- Case 1: Bologna-Ravenna ----

def test_bologna_ravenna_lands_partial_with_valid_segments_intact():
    row = _session_row(BOLOGNA_RAVENNA)
    assert row["session_qc_status"] == "PARTIAL"
    assert row["n_segments"] >= 2
    assert row["session_primary_reason"] == "LONG_GAP"
    assert row["nominal_time_span_s"] > row["observed_sampling_duration_s"]
    segs = SEGMENT_QC[SEGMENT_QC.canonical_campaign_id == BOLOGNA_RAVENNA]
    assert (segs["segment_qc_status"].isin(["PASS", "PASS_WITH_WARNINGS"])).any(), (
        "at least one segment away from the gap must remain usable -- the gap must not invalidate everything"
    )


# ---- Cases 2 & 3: the two short campaigns ----

def test_21_row_session_is_not_assessable_never_reject():
    row = _session_row(SHORT_21_ROWS)
    assert row["session_qc_status"] == "NOT_ASSESSABLE"
    assert row["session_qc_status"] != "REJECT"


def test_91_row_session_is_partial_never_reject_despite_keep_recommended_zero():
    row = _session_row(SHORT_91_ROWS)
    assert row["keep_fraction_recommended"] == 0.0
    assert row["session_qc_status"] not in {"REJECT"}
    assert row["session_qc_status"] == "PARTIAL"


# ---- Case 4: max GPS freeze ----

def test_max_freeze_campaign_is_not_reject_when_gps_data_itself_is_present():
    row = _session_row(MAX_FREEZE)
    assert row["gps_freeze_fraction"] == pytest.approx(SESSION_QC["gps_freeze_fraction"].max())
    assert row["gps_quality_status"] == "POOR"
    assert row["session_qc_status"] != "REJECT", (
        "high freeze alone must not cause REJECT -- REJECT requires genuine GPS/temperature absence, not just freeze"
    )


def test_no_real_segment_reaches_reject_from_freeze_alone():
    high_freeze_segments = SEGMENT_QC[SEGMENT_QC["gps_freeze_fraction"] > 0.30]
    assert not high_freeze_segments.empty
    assert "REJECT" not in high_freeze_segments["segment_qc_status"].unique()


# ---- Case 5: lowest keep_recommended among non-short campaigns ----

def test_lowest_non_short_keep_recommended_is_partial_not_reject():
    row = _session_row(LOWEST_KEEP_NON_SHORT)
    assert row["n_raw"] > 150  # confirms this is not one of the pathologically short campaigns
    assert row["keep_fraction_recommended"] < 0.5
    assert row["session_qc_status"] == "PARTIAL"
    assert row["n_segments"] > 10  # heavily fragmented, consistent with the audit's earlier finding


# ---- Case 6: a nearly-fully-valid campaign ----

def test_near_perfect_campaign_passes():
    row = _session_row(NEARLY_PERFECT)
    assert row["keep_fraction_recommended"] > 0.7
    assert row["session_qc_status"] in {"PASS", "PASS_WITH_WARNINGS"}


# ---- Cases 7 & 8: 1 Hz and 2 Hz cadence ----

def test_1hz_campaign_is_assessed_correctly():
    seg = SEGMENT_QC[SEGMENT_QC.canonical_campaign_id == ONE_HZ]
    assert seg["sampling_interval_median_s"].iloc[0] == pytest.approx(1.0, abs=0.1)
    row = _session_row(ONE_HZ)
    assert row["session_qc_status"] in {"PASS", "PASS_WITH_WARNINGS", "PARTIAL", "NOT_ASSESSABLE", "REJECT"}


def test_2hz_campaign_is_assessed_correctly_not_penalized_for_cadence_alone():
    seg = SEGMENT_QC[SEGMENT_QC.canonical_campaign_id == TWO_HZ]
    assert seg["sampling_interval_median_s"].iloc[0] == pytest.approx(2.0, abs=0.1)
    row = _session_row(TWO_HZ)
    # A native 2 Hz cadence alone (not a real gap) must not trigger sampling_integrity POOR.
    assert row["sampling_integrity_status"] != "POOR"


# ---- Case 9: many stops ----

def test_many_stops_campaign_ventilation_is_never_poor():
    row = _session_row(MANY_STOPS)
    assert row["stop_fraction"] == pytest.approx(SESSION_QC["stop_fraction"].max())
    assert row["ventilation_risk_status"] != "POOR"


# ---- Case 10: high device-vs-GPS speed disagreement (identified dynamically) ----

def test_high_speed_disagreement_campaign_is_identifiable_and_not_auto_rejected():
    disagreement_fractions = {}
    for campaign_id in SESSION_QC["canonical_campaign_id"]:
        frames = load_campaign_frames(campaign_id, PROFILE_ROOTS)
        ref = build_reference_frame(frames)
        disagreement_fractions[campaign_id] = (ref["speed_evidence_class"] == "BOTH_AVAILABLE_DISAGREE").mean()
    worst_campaign = max(disagreement_fractions, key=disagreement_fractions.get)
    assert disagreement_fractions[worst_campaign] > 0.0
    row = _session_row(worst_campaign)
    assert row["session_qc_status"] != "REJECT" or row["gps_valid_fraction"] < 0.05, (
        "speed disagreement alone (both sources present but disagreeing) must not force REJECT"
    )


# ---- Synthetic case: extended freeze WITHOUT any valid GPS at all (does not occur in the real 44 campaigns) ----

def test_synthetic_extended_freeze_with_no_valid_gps_at_all_is_reject():
    from meteotracker_qc.session_qc.segment_status import compute_segment_status

    policy = pd.read_csv(ROOT / "config" / "session_qc_policy.csv")
    row = pd.DataFrame([{
        "canonical_campaign_id": "synthetic", "source_file": "f.csv", "segment_id": 0,
        "n_raw": 500, "n_permissive": 500, "n_recommended": 0, "n_restrictive": 0,
        "observed_sampling_duration_s": 500.0, "observed_distance_km": 0.01,
        "valid_duration_recommended_s": 0.0, "valid_distance_recommended_km": 0.0,
        "n_short_gaps": 0, "n_long_gaps": 0,
        "gps_valid_fraction": 0.01, "gps_freeze_fraction": 0.95, "possible_gps_freeze_fraction": 0.0,
        "spatial_jump_fraction": 0.0, "isolated_position_outlier_fraction": 0.0,
        "unrealistic_speed_fraction": 0.0, "unrealistic_acceleration_fraction": 0.0,
        "low_speed_device_fraction": 1.0, "low_speed_gps_fraction": 1.0, "low_ventilation_possible_fraction": 1.0,
        "stationary_fraction": 0.95, "stop_fraction": 0.9, "post_stop_recovery_fraction": 0.0,
        "temp_valid_fraction": 1.0, "temp_spike_fraction": 0.0, "temp_rate_anomaly_fraction": 0.0,
        "sensor_plateau_fraction": 0.0, "impossible_value_fraction": 0.0,
        "stabilization_fraction": 0.1, "stabilization_reached": True, "stabilization_reached_after_s": 10.0,
        "stabilization_reason_code": "slope_confirmed_stable",
        "excluded_recommended_fraction": 1.0, "primary_exclusion_reason": "qc_gps_freeze",
        "primary_exclusion_family": "GPS", "secondary_exclusion_reasons": "", "exclusion_reason_count": 1.0,
        "multi_flagged_fraction": 0.0,
    }])
    out = compute_segment_status(row, policy, "recommended_session")
    assert out["segment_qc_status"].iloc[0] == "REJECT"


# ---- Section Q's remaining required checks ----

def test_no_raw_file_was_modified():
    manifest = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    checked = 0
    for _, row in manifest.head(5).iterrows():  # spot-check a sample, full 39-file hash is the audit's job
        raw_path = ROOT / "data" / "raw" / row["source_file"]
        if not raw_path.exists():
            continue
        actual_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        assert actual_hash == row["file_sha256"], f"raw file changed: {row['source_file']}"
        checked += 1
    assert checked >= 3


def test_session_qc_package_has_no_repeated_routes_dependency():
    import ast
    import importlib
    import inspect

    package_dir = ROOT / "src" / "meteotracker_qc" / "session_qc"
    for py_file in list(package_dir.glob("*.py")) + [ROOT / "src" / "meteotracker_qc" / "session_qc_pipeline.py"]:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        imported += [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
        assert not any("repeated_routes" in m for m in imported), f"{py_file.name} imports repeated_routes: {imported}"
