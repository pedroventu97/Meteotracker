import pandas as pd
import pytest

from meteotracker_qc.session_qc.diagnostics import plot_campaign_diagnostic, select_campaigns_for_diagnostics

@pytest.fixture
def session_qc(scientific_workspace):
    return pd.read_csv(scientific_workspace / "outputs/session_qc/session_qc_inventory.csv")


def test_selection_includes_partial_reject_not_assessable(session_qc):
    SESSION_QC = session_qc
    selected = select_campaigns_for_diagnostics(SESSION_QC)
    flagged = SESSION_QC[SESSION_QC["session_qc_status"].isin(["PARTIAL", "REJECT", "NOT_ASSESSABLE"])]
    assert set(flagged["canonical_campaign_id"]) <= set(selected)


def test_selection_excludes_a_clean_pass_campaign():
    SESSION_QC = pd.DataFrame([{"canonical_campaign_id": "clean", "session_qc_status": "PASS", "nominal_time_span_s": 600}])
    passing = SESSION_QC[SESSION_QC["session_qc_status"] == "PASS"]
    if passing.empty:
        pytest.skip("no PASS campaigns in the current real run")
    selected = set(select_campaigns_for_diagnostics(SESSION_QC))
    # A campaign that is PASS with no POOR dimension and above the minimum
    # duration should not need a diagnostic figure.
    for _, row in passing.iterrows():
        dims_ok = all(
            row.get(f"{dim}_status", "OK") != "POOR"
            for dim in ["sampling_integrity", "gps_quality", "thermal_signal", "ventilation_risk", "stabilization_quality", "spatial_continuity", "schema_completeness"]
        )
        if dims_ok and row["nominal_time_span_s"] >= 30:
            assert row["canonical_campaign_id"] not in selected


def test_plot_runs_without_error_for_a_synthetic_short_and_long_campaign(tmp_path, scientific_workspace, session_qc):
    from pathlib import Path

    from meteotracker_qc.session_qc.metrics import build_reference_frame, load_campaign_frames

    SESSION_QC = session_qc
    profile_roots = {p: scientific_workspace / "outputs" / p for p in ["permissive", "recommended", "restrictive"]}
    ordered = SESSION_QC.sort_values("nominal_time_span_s")
    for campaign_id in ordered.iloc[[0, -1]]["canonical_campaign_id"]:
        frames = load_campaign_frames(campaign_id, profile_roots)
        ref = build_reference_frame(frames)
        session_row = SESSION_QC[SESSION_QC.canonical_campaign_id == campaign_id].iloc[0]
        out_path = tmp_path / f"{campaign_id}.png"
        plot_campaign_diagnostic(ref, session_row, out_path)
        assert out_path.exists()
        assert out_path.stat().st_size > 0
