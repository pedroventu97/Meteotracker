from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.diagnostics import (
    plot_campaign_temporal_diagnostic, select_campaigns_for_diagnostics,
)

T0 = pd.Timestamp("2026-02-13T09:00:00Z")


def _session_row(**overrides):
    base = {
        "canonical_campaign_id": "c1", "temporal_internal_assessability_status": "ASSESSABLE",
        "temporal_change_diagnosis": "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE",
        "sensor_drift_interpretation": "NO_SPECIFIC_INSTRUMENT_EVIDENCE", "method_agreement": "METHODS_AGREE",
        "temporal_model_form": "LINEAR", "temporal_sensitivity_stability_class": "STABLE",
        "detrending_supported": False, "n_repeated_location_groups_valid": 5, "n_repeated_location_visits": 10,
        "n_repeated_location_pairs_valid": 8, "method1_trend_c_per_min": 0.01, "primary_trend_c_per_min": 0.01,
        "primary_confidence_interval_low": -0.01, "primary_confidence_interval_high": 0.03,
        "dominated_by_single_location": False, "start_end_pair_consistent_with_revisits": None,
    }
    base.update(overrides)
    return pd.Series(base)


def _session_df(rows):
    return pd.DataFrame([r if isinstance(r, dict) else r.to_dict() for r in rows])


def test_selection_includes_assessable_sessions():
    df = _session_df([_session_row(canonical_campaign_id="c1", temporal_internal_assessability_status="ASSESSABLE"),
                       _session_row(canonical_campaign_id="c2", temporal_internal_assessability_status="NOT_ASSESSABLE",
                                    temporal_change_diagnosis="NOT_ASSESSABLE", n_repeated_location_pairs_valid=0)])
    selected = select_campaigns_for_diagnostics(df)
    assert "c1" in selected


def test_selection_includes_supported_diagnosis():
    df = _session_df([_session_row(canonical_campaign_id="c1", temporal_internal_assessability_status="PARTIALLY_ASSESSABLE",
                                    temporal_change_diagnosis="TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", n_repeated_location_pairs_valid=0)])
    selected = select_campaigns_for_diagnostics(df)
    assert "c1" in selected


def test_selection_includes_methods_disagree():
    df = _session_df([_session_row(canonical_campaign_id="c1", temporal_internal_assessability_status="PARTIALLY_ASSESSABLE",
                                    temporal_change_diagnosis="INTERNAL_METHODS_DISAGREE", method_agreement="METHODS_DISAGREE", n_repeated_location_pairs_valid=0)])
    selected = select_campaigns_for_diagnostics(df)
    assert "c1" in selected


def test_selection_includes_highly_sensitive():
    df = _session_df([_session_row(canonical_campaign_id="c1", temporal_internal_assessability_status="PARTIALLY_ASSESSABLE",
                                    temporal_change_diagnosis="INCONCLUSIVE_TEMPORAL_EFFECT", temporal_sensitivity_stability_class="HIGHLY_SENSITIVE", n_repeated_location_pairs_valid=0)])
    selected = select_campaigns_for_diagnostics(df)
    assert "c1" in selected


def test_selection_excludes_a_clean_not_assessable_low_pair_session():
    # 6 other campaigns with more pairs (and otherwise clean status) ensure
    # c1 doesn't get pulled in only because it's trivially "top 5" among 1.
    other_rows = [
        _session_row(canonical_campaign_id=f"other{i}", n_repeated_location_pairs_valid=20 + i)
        for i in range(6)
    ]
    target = _session_row(canonical_campaign_id="c1", temporal_internal_assessability_status="NOT_ASSESSABLE",
                           temporal_change_diagnosis="NOT_ASSESSABLE", n_repeated_location_pairs_valid=0)
    df = _session_df(other_rows + [target])
    selected = select_campaigns_for_diagnostics(df)
    assert "c1" not in selected


def test_plot_runs_without_error_and_produces_a_file(tmp_path):
    times = [T0 + pd.Timedelta(seconds=i * 60) for i in range(30)]
    df = pd.DataFrame({
        "time_utc": times, "canonical_temperature_c": [10.0 + 0.01 * i for i in range(30)],
        "temporal_candidate_recommended": [i % 3 == 0 for i in range(30)],
    })
    groups = pd.DataFrame({"repeated_location_group_id": [1, 2], "group_n_visits": [2, 2]})
    visits = pd.DataFrame({
        "repeated_location_group_id": [1, 1, 2, 2],
        "visit_representative_timestamp": [times[0], times[15], times[5], times[25]],
    })
    pairs = pd.DataFrame({
        "time_difference_s": [900.0, 1200.0], "temperature_difference_c": [0.15, -0.1],
        "pair_qc_status": ["VALID", "EXCLUDED"], "repeated_location_group_id": [1, 2],
        "pairwise_slope_c_per_min": [0.01, -0.005],
    })
    sensitivity = pd.DataFrame({"config_name": ["anchor", "sens_radius_5m"], "method2_trend_c_per_min": [0.01, 0.02]})
    session_row = _session_row()
    out_path = tmp_path / "c1_temporal_diagnostic.png"
    plot_campaign_temporal_diagnostic("c1", df, groups, visits, pairs, session_row, sensitivity, None, out_path)
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_plot_handles_empty_groups_visits_pairs_gracefully(tmp_path):
    times = [T0 + pd.Timedelta(seconds=i * 60) for i in range(10)]
    df = pd.DataFrame({"time_utc": times, "canonical_temperature_c": [10.0] * 10, "temporal_candidate_recommended": [False] * 10})
    empty = pd.DataFrame()
    out_path = tmp_path / "c1_empty.png"
    plot_campaign_temporal_diagnostic("c1", df, empty, empty, empty, _session_row(), empty, None, out_path)
    assert out_path.exists()
