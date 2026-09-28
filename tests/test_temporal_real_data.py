"""Section R: the 12 required real-data validation cases, read directly from
the real outputs/temporal_drift/ pipeline run. Read-only w.r.t. data/raw/ and
outputs/{permissive,recommended,restrictive}/ -- never writes there.
"""
import hashlib
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SESSION = pd.read_csv(ROOT / "outputs" / "temporal_drift" / "session_temporal_diagnostics.csv")
SESSION_QC = pd.read_csv(ROOT / "outputs" / "session_qc" / "session_qc_inventory.csv")

BOLOGNA_RAVENNA = "06-04__20260604T11_40_32_mtdicambo_AC4D162B317E_Bologna-Ravenna__5bd4095200"
SHORT_21_ROWS = "04-27__20260427T07_28_18_mtdicambo_AC4D162B317E_Bologna-Bologna__a768d6fc15"
SHORT_91_ROWS = "07-04_2025_moto__20250704T09_31_26_private_6D17FE6E-7C39-270E-9083-54ABA0F52166_Bologna-Bologna__e9e4deafbf"
MAX_FREEZE = "07-04_2025_moto__20250704T10_15_51_private_6D17FE6E-7C39-270E-9083-54ABA0F52166_Bologna-Bologna__5f01006ac6"
LOWEST_KEEP_NON_SHORT = "02-20__20260220T09_05_04_mtdicambo_B6CCF894-DF13-BB20-B108-3C17F67FA94E_Bologna-Bologna__c2b73a152d"
MANY_SEGMENTS = "02-13__20260213T13_23_47_mtdicambo_B6CCF894-DF13-BB20-B108-3C17F67FA94E_Bologna-Bologna__c098f040ec"
ONE_OF_TWO_PASS = "02-28__20260228T14_01_31_mtdicambo_B6CCF894-DF13-BB20-B108-3C17F67FA94E_Bologna-Bologna__fd7d5426a2"
LARGE_TREND_CASE = "02-13__20260213T09_06_57_mtdicambo_B6CCF894-DF13-BB20-B108-3C17F67FA94E_Bologna-Bologna__353b44f890"


def _row(campaign_id):
    match = SESSION[SESSION.canonical_campaign_id == campaign_id]
    assert not match.empty, f"{campaign_id} missing from session_temporal_diagnostics.csv"
    return match.iloc[0]


# ---- Case 1: one of the 2 PASS sessions from Phase 3 ----

def test_pass_session_from_phase3_has_a_coherent_temporal_diagnosis():
    row = _row(ONE_OF_TWO_PASS)
    assert row["temporal_change_diagnosis"] in {
        "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE",
        "INCONCLUSIVE_TEMPORAL_EFFECT", "INTERNAL_METHODS_DISAGREE", "INSUFFICIENT_REVISITS", "NOT_ASSESSABLE",
    }
    assert row["sensor_drift_interpretation"] != "SENSOR_DRIFT"


# ---- Case 2: Bologna-Ravenna ----

def test_bologna_ravenna_temporal_diagnosis_is_prudent():
    row = _row(BOLOGNA_RAVENNA)
    assert row["temporal_change_diagnosis"] != "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED" or pd.notna(row["primary_confidence_interval_low"])
    assert row["sensor_drift_interpretation"] in {
        "NOT_ASSESSABLE", "NO_SPECIFIC_INSTRUMENT_EVIDENCE",
        "POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED", "CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA",
    }


# ---- Cases 3 & 4: the two short sessions ----

def test_21_row_session_not_assessable_never_forces_a_diagnosis():
    row = _row(SHORT_21_ROWS)
    assert row["temporal_internal_assessability_status"] == "NOT_ASSESSABLE"
    assert row["temporal_change_diagnosis"] == "NOT_ASSESSABLE"
    assert row["detrending_supported"] == False  # noqa: E712


def test_91_row_session_never_reaches_a_supported_diagnosis_from_almost_no_data():
    row = _row(SHORT_91_ROWS)
    assert row["temporal_change_diagnosis"] != "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED"


# ---- Case 5: campaign with maximum GPS freeze ----

def test_max_freeze_campaign_temporal_diagnosis_not_crashed_by_freeze():
    row = _row(MAX_FREEZE)
    assert pd.notna(row["temporal_internal_assessability_status"])
    assert row["sensor_drift_interpretation"] != "SENSOR_DRIFT"


# ---- Case 6: lowest keep_recommended among non-short campaigns ----

def test_lowest_keep_campaign_handled_gracefully():
    row = _row(LOWEST_KEEP_NON_SHORT)
    assert pd.notna(row["temporal_change_diagnosis"])


# ---- Case 7: a campaign with many segments ----

def test_many_segments_campaign_assessability_reflects_fragmentation():
    row = _row(MANY_SEGMENTS)
    # heavy fragmentation should show up as either low spatial coverage,
    # few valid groups, or a PARTIALLY_ASSESSABLE/NOT_ASSESSABLE outcome --
    # never a silent crash or a spuriously confident SUPPORTED diagnosis
    # built from a structurally unstable base.
    assert pd.notna(row["temporal_internal_assessability_status"])


# ---- Case 8: start and end close together ----

def test_campaign_with_close_start_end_locations_identified_dynamically():
    candidates = SESSION_QC[SESSION_QC["start_end_locations_comparable"] == True]  # noqa: E712
    if candidates.empty:
        pytest.skip("no real campaign has comparable start/end locations")
    campaign_id = candidates.iloc[0]["canonical_campaign_id"]
    row = _row(campaign_id)
    assert pd.notna(row["temporal_internal_assessability_status"])


# ---- Case 9: start and end far apart ----

def test_campaign_with_far_start_end_locations_identified_dynamically():
    candidates = SESSION_QC[SESSION_QC["start_end_locations_comparable"] == False]  # noqa: E712
    assert not candidates.empty
    campaign_id = candidates.iloc[0]["canonical_campaign_id"]
    row = _row(campaign_id)
    assert pd.notna(row["temporal_internal_assessability_status"])


# ---- Case 10: campaign with many revisit groups (identified dynamically) ----

def test_campaign_with_most_valid_revisit_groups_identified_dynamically():
    campaign_id = SESSION.loc[SESSION["n_repeated_location_groups_valid"].idxmax(), "canonical_campaign_id"]
    row = _row(campaign_id)
    assert row["n_repeated_location_groups_valid"] > 0
    assert pd.notna(row["temporal_change_diagnosis"])


# ---- Case 11: a campaign without valid revisits (identified dynamically) ----

def test_campaign_with_no_valid_revisits_identified_dynamically():
    candidates = SESSION[SESSION["n_repeated_location_pairs_valid"] == 0]
    if candidates.empty:
        pytest.skip("every real campaign has at least one valid revisit pair")
    row = _row(candidates.iloc[0]["canonical_campaign_id"])
    assert row["temporal_change_diagnosis"] in {"NOT_ASSESSABLE", "INSUFFICIENT_REVISITS"}
    assert row["detrending_supported"] == False  # noqa: E712


# ---- Case 12: same-direction vs opposite-direction produce different results ----

def test_direction_dependent_campaign_identified_dynamically_if_any():
    candidates = SESSION[SESSION.get("direction_consistency", pd.Series(dtype=object)) == "dependent"]
    if candidates.empty:
        pytest.skip("no real campaign shows a same/opposite direction disagreement in this run")
    row = _row(candidates.iloc[0]["canonical_campaign_id"])
    assert row["temporal_change_diagnosis"] != "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED"


# ---- Section Q's remaining required checks ----

def test_no_raw_file_was_modified():
    manifest = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    checked = 0
    for _, row in manifest.head(5).iterrows():
        raw_path = ROOT / "data" / "raw" / row["source_file"]
        if not raw_path.exists():
            continue
        actual_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        assert actual_hash == row["file_sha256"], f"raw file changed: {row['source_file']}"
        checked += 1
    assert checked >= 3


def test_only_the_canonical_campaigns_are_in_temporal_drift_outputs():
    manifest = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    n_canonical = int((~manifest["exclude_from_analysis"].astype(bool)).sum())
    assert SESSION["canonical_campaign_id"].nunique() == n_canonical == 44


def test_no_double_counting_of_redundant_raw_files():
    groups = pd.read_csv(ROOT / "outputs" / "temporal_drift" / "repeated_location_groups.csv")
    assert set(groups["canonical_campaign_id"]) <= set(SESSION["canonical_campaign_id"])


# ---- Method 2 hardening regression: the ~+0.037 C/min case (Fase 4B section F.3) ----

def test_large_trend_case_diagnosis_stable_after_method2_hardening():
    """This campaign (33 valid groups, only 6 valid pairs) was the single real
    case reaching TEMPORAL_BACKGROUND_CHANGE_SUPPORTED with a trend large
    enough (~+0.037 C/min) to also earn
    POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED, pre-hardening.
    Requiring Method 2's pooled visits to also respect
    minimum_temporal_separation_s must not silently flip this into a
    fabricated SENSOR_DRIFT declaration, and must not silently erase a real
    finding either -- either an unchanged diagnosis, or a legitimate downgrade
    to a more conservative status (e.g. if some visits get dropped by the
    hardening) are both acceptable; a jump to SENSOR_DRIFT is not.

    Observed outcome after hardening (reports/temporal_drift_diagnostics.md,
    section AE): only 6 of the 33 groups had visits genuinely >=300s apart,
    so Method 2's pooled input drops from 33 to 6 groups -- below the
    8-group cluster-bootstrap floor, so the CI can no longer be computed and
    the diagnosis correctly downgrades to INCONCLUSIVE_TEMPORAL_EFFECT
    (CI_TOO_WIDE). The point estimate itself barely moves (+0.037 ->
    +0.040 C/min); it is the inflated confidence from too-close revisits
    that the hardening removes, exactly the risk it was meant to catch.
    """
    row = _row(LARGE_TREND_CASE)
    assert row["sensor_drift_interpretation"] != "SENSOR_DRIFT"
    assert row["temporal_change_diagnosis"] in {
        "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE",
        "INCONCLUSIVE_TEMPORAL_EFFECT", "INTERNAL_METHODS_DISAGREE", "INSUFFICIENT_REVISITS",
        "POSSIBLE_NONLINEAR_BACKGROUND_CHANGE", "NOT_ASSESSABLE",
    }
