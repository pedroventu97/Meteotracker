"""Section P / Section Q scenario #43: sensitivity sweep across the 3
aggregation configurations (permissive_session/recommended_session/
conservative_session). Re-applies already-computed segment/session metrics
under each profile's own rows in config/session_qc_policy.csv -- never
recomputes point-level flags, never auto-selects a "best" profile.
"""
from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.session_qc.sensitivity import (
    AGGREGATION_PROFILES,
    campaigns_that_change_class,
    run_segment_sensitivity,
    run_session_sensitivity,
    summarize_status_counts,
)
from meteotracker_qc.session_qc.session_status import compute_session_status

ROOT = Path(__file__).resolve().parent.parent
SHORT_21_ROWS = "04-27__20260427T07_28_18_mtdicambo_AC4D162B317E_Bologna-Bologna__a768d6fc15"
SHORT_91_ROWS = "07-04_2025_moto__20250704T09_31_26_private_6D17FE6E-7C39-270E-9083-54ABA0F52166_Bologna-Bologna__e9e4deafbf"
BOLOGNA_RAVENNA = "06-04__20260604T11_40_32_mtdicambo_AC4D162B317E_Bologna-Ravenna__5bd4095200"


@pytest.fixture(scope="module")
def session_metrics_and_policy(scientific_workspace):
    ROOT = scientific_workspace
    session_qc = pd.read_csv(ROOT / "outputs" / "session_qc" / "session_qc_inventory.csv")
    policy = pd.read_csv(ROOT / "config" / "session_qc_policy.csv")
    metric_cols = [c for c in session_qc.columns if not c.endswith(("_status", "_reason_code", "_matched_rule_id"))]
    metric_cols = [c for c in metric_cols if c not in {
        "session_qc_status", "session_qc_reason_code", "session_qc_matched_rule_id",
        "session_primary_reason", "session_secondary_reasons", "session_reason_count", "session_reason_families",
    }]
    manifest = pd.read_csv(ROOT / "data/manifests/campaign_manifest.csv")
    names = {"short21.csv": SHORT_21_ROWS, "short91.csv": SHORT_91_ROWS, "gap.csv": BOLOGNA_RAVENNA}
    mapping = {row.canonical_campaign_id: names[Path(row.source_file).name] for row in manifest.itertuples() if Path(row.source_file).name in names}
    metrics = session_qc[metric_cols].copy()
    metrics["canonical_campaign_id"] = metrics["canonical_campaign_id"].replace(mapping)
    return metrics, policy


def test_sensitivity_csv_exists_and_covers_all_three_profiles(scientific_workspace):
    ROOT = scientific_workspace
    df = pd.read_csv(ROOT / "outputs" / "session_qc" / "session_qc_sensitivity.csv")
    session_qc = pd.read_csv(ROOT / "outputs" / "session_qc" / "session_qc_inventory.csv")
    n_campaigns = session_qc["canonical_campaign_id"].nunique()
    assert set(df["profile"].unique()) == set(AGGREGATION_PROFILES)
    assert df["canonical_campaign_id"].nunique() == n_campaigns
    for profile in AGGREGATION_PROFILES:
        assert (df["profile"] == profile).sum() == n_campaigns


def test_no_best_profile_field_is_produced(session_metrics_and_policy):
    session_metrics, policy = session_metrics_and_policy
    out = run_session_sensitivity(session_metrics, policy)
    forbidden = {"best_profile", "recommended_profile", "chosen_profile", "winner"}
    assert forbidden.isdisjoint(out.columns)


def test_status_distribution_differs_across_profiles(session_metrics_and_policy):
    session_metrics, policy = session_metrics_and_policy
    out = run_session_sensitivity(session_metrics, policy)
    counts = summarize_status_counts(out, "session_qc_status")
    # Permissive must never be stricter than conservative in aggregate: more
    # PASS-family outcomes under permissive than under conservative.
    pass_family = ["PASS", "PASS_WITH_WARNINGS"]
    permissive_pass = counts.loc["permissive_session", [c for c in pass_family if c in counts.columns]].sum()
    conservative_pass = counts.loc["conservative_session", [c for c in pass_family if c in counts.columns]].sum()
    assert permissive_pass >= conservative_pass


def test_short_21_row_campaign_changes_class_between_permissive_and_conservative(session_metrics_and_policy):
    session_metrics, policy = session_metrics_and_policy
    out = run_session_sensitivity(session_metrics, policy)
    row_permissive = out[(out.canonical_campaign_id == SHORT_21_ROWS) & (out.profile == "permissive_session")].iloc[0]
    row_conservative = out[(out.canonical_campaign_id == SHORT_21_ROWS) & (out.profile == "conservative_session")].iloc[0]
    assert row_permissive["session_qc_status"] != row_conservative["session_qc_status"]
    assert row_conservative["session_qc_status"] == "NOT_ASSESSABLE"
    # Never REJECT under any aggregation configuration, per principle B.3.
    assert (out[out.canonical_campaign_id == SHORT_21_ROWS]["session_qc_status"] != "REJECT").all()


def test_short_91_row_campaign_never_rejects_under_any_profile(session_metrics_and_policy):
    session_metrics, policy = session_metrics_and_policy
    out = run_session_sensitivity(session_metrics, policy)
    rows = out[out.canonical_campaign_id == SHORT_91_ROWS]
    assert (rows["session_qc_status"] != "REJECT").all()


def test_bologna_ravenna_gap_exceeds_poor_threshold_under_all_three_profiles(session_metrics_and_policy):
    session_metrics, policy = session_metrics_and_policy
    out = run_session_sensitivity(session_metrics, policy)
    rows = out[out.canonical_campaign_id == BOLOGNA_RAVENNA]
    assert (rows["session_qc_status"] == "PARTIAL").all(), (
        "the long inter-segment gap must be flagged under every aggregation profile, never pass unnoticed"
    )


def test_some_campaigns_change_class_across_profiles(session_metrics_and_policy):
    session_metrics, policy = session_metrics_and_policy
    out = run_session_sensitivity(session_metrics, policy)
    changed = campaigns_that_change_class(out)
    assert not changed.empty
    assert set(changed["canonical_campaign_id"]) <= set(session_metrics["canonical_campaign_id"])


def test_permissive_never_stricter_than_conservative_per_campaign(session_metrics_and_policy):
    session_metrics, policy = session_metrics_and_policy
    out = run_session_sensitivity(session_metrics, policy)
    severity = {"REJECT": 0, "NOT_ASSESSABLE": 1, "PARTIAL": 2, "PASS_WITH_WARNINGS": 3, "PASS": 4}
    wide = out.pivot(index="canonical_campaign_id", columns="profile", values="session_qc_status")
    permissive_rank = wide["permissive_session"].map(severity)
    conservative_rank = wide["conservative_session"].map(severity)
    assert (permissive_rank >= conservative_rank).all(), (
        "a campaign must never be classified worse under the more lenient profile than under the stricter one"
    )


def test_segment_sensitivity_also_covers_all_three_profiles(scientific_workspace):
    ROOT = scientific_workspace
    segment_metrics = pd.read_csv(ROOT / "outputs" / "session_qc" / "segment_qc_inventory.csv")
    policy = pd.read_csv(ROOT / "config" / "session_qc_policy.csv")
    metric_cols = [c for c in segment_metrics.columns if not c.endswith(("_status", "_reason_code", "_matched_rule_id"))]
    metric_cols = [c for c in metric_cols if c not in {
        "segment_qc_status", "segment_qc_reason_code", "segment_qc_matched_rule_id",
    }]
    out = run_segment_sensitivity(segment_metrics[metric_cols], policy)
    assert set(out["profile"].unique()) == set(AGGREGATION_PROFILES)
    n_segments = segment_metrics.shape[0]
    for profile in AGGREGATION_PROFILES:
        assert (out["profile"] == profile).sum() == n_segments


def test_compute_session_status_runs_standalone_for_each_profile(session_metrics_and_policy):
    session_metrics, policy = session_metrics_and_policy
    for profile in AGGREGATION_PROFILES:
        out = compute_session_status(session_metrics, policy, profile)
        assert out["session_qc_status"].notna().all()
