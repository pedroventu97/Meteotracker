from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.candidates import build_temporal_candidate_masks
from meteotracker_qc.temporal_drift.config import load_matching_policy
from meteotracker_qc.temporal_drift_pipeline import process_campaign, run_temporal_drift

ROOT = Path(__file__).resolve().parent.parent
MATCHING_POLICY = load_matching_policy(ROOT)
TDA_POLICY = pd.read_csv(ROOT / "config" / "temporal_drift_policy.csv")
BASE_LAT, BASE_LON = 44.4949, 11.3426
T0 = pd.Timestamp("2026-02-13T09:00:00Z")

FLAG_COLS = [
    "qc_temp_isolated_spike", "qc_temp_impossible", "qc_gps_jump", "qc_spatial_jump",
    "qc_isolated_position_outlier", "qc_gps_freeze", "qc_sensor_stabilization",
    "qc_post_stop_recovery", "qc_low_ventilation_possible", "qc_temp_rate_anomaly",
    "qc_possible_gps_freeze", "qc_stop_event", "qc_stationary", "qc_coord_repeated", "qc_segment_break",
]


def _row(t, lat, lon, temp, **overrides):
    base = {
        "time_utc": T0 + pd.Timedelta(seconds=t), "canonical_latitude": lat, "canonical_longitude": lon,
        "canonical_temperature_c": temp, "segment_id": 0, "keep_permissive": True, "keep_recommended": True,
        "keep_restrictive": True,
    }
    for flag in FLAG_COLS:
        base[flag] = False
    base.update(overrides)
    return base


def _synthetic_campaign_df(n_groups=8, trend_c_per_min=0.04):
    rows = []
    for gi in range(n_groups):
        lat = BASE_LAT + gi * (100.0 / 111320.0)
        t_early, t_late = gi * 20, 3600 + gi * 20
        temp_early = 10.0 + t_early * (trend_c_per_min / 60.0)
        temp_late = 10.0 + t_late * (trend_c_per_min / 60.0)
        rows += [
            _row(t_early, lat, BASE_LON, temp_early), _row(t_early + 5, lat, BASE_LON, temp_early + 0.01),
            _row(t_late, lat, BASE_LON, temp_late), _row(t_late + 5, lat, BASE_LON, temp_late + 0.01),
        ]
    return build_temporal_candidate_masks(pd.DataFrame(rows))


def test_process_campaign_runs_end_to_end_on_synthetic_data():
    df = _synthetic_campaign_df()
    result = process_campaign("synthetic_c1", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=50, sensitivity_n_bootstrap=20)
    assert set(result.keys()) >= {"session_row", "groups", "visits", "pairs", "model_comparison", "sensitivity", "detrending_df", "observations"}
    assert result["session_row"]["canonical_campaign_id"] == "synthetic_c1"


def test_session_row_has_key_diagnostic_fields():
    df = _synthetic_campaign_df()
    result = process_campaign("synthetic_c1", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=50, sensitivity_n_bootstrap=20)
    row = result["session_row"]
    for key in [
        "temporal_internal_assessability_status", "temporal_change_diagnosis", "sensor_drift_interpretation",
        "temporal_sensitivity_stability_class", "detrending_supported", "method1_trend_c_per_min", "primary_trend_c_per_min",
    ]:
        assert key in row, f"missing {key}"


def test_model_comparison_has_five_method_rows_including_nonlinear():
    df = _synthetic_campaign_df()
    result = process_campaign("synthetic_c1", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=50, sensitivity_n_bootstrap=20)
    methods = set(result["model_comparison"]["method"])
    assert methods == {"pairwise_median", "fixed_effects_ols", "fixed_effects_huber", "fixed_effects_theilsen", "nonlinear_quadratic"}


def test_sensitivity_has_18_configurations():
    df = _synthetic_campaign_df()
    result = process_campaign("synthetic_c1", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=50, sensitivity_n_bootstrap=20)
    assert len(result["sensitivity"]) == 18


def test_observations_enriched_with_qc_context():
    df = _synthetic_campaign_df()
    result = process_campaign("synthetic_c1", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=50, sensitivity_n_bootstrap=20)
    obs = result["observations"]
    assert "canonical_temperature_c" in obs.columns
    assert "time_utc" in obs.columns
    assert len(obs) > 0


def test_run_temporal_drift_on_one_synthetic_small_campaign_writes_outputs(tmp_path, scientific_workspace):
    ROOT = scientific_workspace
    campaign_id = pd.read_csv(ROOT / "data/manifests/campaign_manifest.csv").query("source_file.str.endswith('short21.csv')", engine="python")["canonical_campaign_id"].iloc[0]
    result = run_temporal_drift(root=ROOT, output_root=tmp_path, campaign_ids=[campaign_id], main_n_bootstrap=50, sensitivity_n_bootstrap=20)
    assert result["campaign_ids"] == [campaign_id]
    for fname in [
        "session_temporal_diagnostics.csv", "repeated_location_groups.csv", "repeated_location_visits.csv",
        "repeated_location_pairs.csv", "repeated_location_observations.csv", "temporal_model_comparison.csv",
        "temporal_drift_sensitivity.csv", "temporal_policy_effective.csv", "detrending_validation.csv",
    ]:
        assert (tmp_path / fname).exists(), f"missing {fname}"
    assert (tmp_path / "campaigns" / campaign_id / "temporal_diagnostics.json").exists()


def test_default_campaign_discovery_is_scoped_to_session_qc_not_raw_directory_scan(scientific_workspace):
    ROOT = scientific_workspace
    # Regression test: a first attempt discovered campaign_ids by scanning
    # outputs/recommended/'s subdirectories directly. That directory can grow
    # independently (a concurrent Phase-1 ingestion run added 10 more real
    # campaigns there without session_qc/temporal_drift being re-run for
    # them), which silently pulled 44 campaigns into a temporal_drift run
    # meant to stay scoped to the 34 already covered by session_qc -- a real
    # scope violation caught before it produced a mis-scoped full run.
    from meteotracker_qc.temporal_drift_pipeline import discover_canonical_campaign_ids

    session_qc_inventory = pd.read_csv(ROOT / "outputs" / "session_qc" / "session_qc_inventory.csv")
    session_qc_ids = set(session_qc_inventory["canonical_campaign_id"])
    recommended_dirs = {d.name for d in (ROOT / "outputs" / "recommended").iterdir() if d.is_dir()}

    discovered = set(discover_canonical_campaign_ids(ROOT, session_qc_inventory))
    assert discovered == session_qc_ids
    if len(recommended_dirs) > len(session_qc_ids):
        assert discovered != recommended_dirs, (
            "outputs/recommended/ has grown beyond session_qc's campaign set -- "
            "discovery must stay scoped to session_qc, not the raw directory listing"
        )


def test_manifest_session_qc_and_temporal_drift_campaign_sets_agree(scientific_workspace):
    ROOT = scientific_workspace
    # Fase 4B requirement: after Session QC and Temporal Drift are both
    # re-run on the 44-canonical-campaign manifest, all three "what counts as
    # a canonical campaign" sources must agree exactly -- manifest
    # (exclude_from_analysis == False), session_qc_inventory.csv, and
    # session_temporal_diagnostics.csv. A mismatch here means one of the two
    # pipelines was run against a stale or partial campaign list.
    manifest = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    manifest_ids = set(manifest.loc[~manifest["exclude_from_analysis"].astype(bool), "canonical_campaign_id"])

    session_qc_ids = set(pd.read_csv(ROOT / "outputs" / "session_qc" / "session_qc_inventory.csv")["canonical_campaign_id"])
    temporal_drift_ids = set(pd.read_csv(ROOT / "outputs" / "temporal_drift" / "session_temporal_diagnostics.csv")["canonical_campaign_id"])

    assert manifest_ids == session_qc_ids, f"manifest vs session_qc mismatch: {manifest_ids ^ session_qc_ids}"
    assert manifest_ids == temporal_drift_ids, f"manifest vs temporal_drift mismatch: {manifest_ids ^ temporal_drift_ids}"
    assert len(manifest_ids) == 8


def test_repeated_routes_never_imported_by_temporal_drift_pipeline():
    import ast
    import meteotracker_qc
    package_root = Path(meteotracker_qc.__file__).resolve().parent
    package_dir = package_root / "temporal_drift"
    files = list(package_dir.glob("*.py")) + [package_root / "temporal_drift_pipeline.py"]
    assert len(files) > 1
    for py_file in files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        imported += [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
        assert not any("repeated_routes" in m for m in imported), f"{py_file.name} imports repeated_routes: {imported}"


# --- End-to-end coverage for the session_row estimate-field precedence fix ------------------
#
# prepare_diagnosis_metrics() (diagnosis.py) already nulls the five estimate fields correctly
# in isolation (see test_temporal_diagnosis.py). These tests instead exercise process_campaign()
# itself, because the previous bug was entirely in temporal_drift_pipeline.py's session_row
# assembly (the **_prefix(method1, ...) / **_prefix(method2_huber, ...) spreads republishing raw,
# un-nulled values) -- a gap a unit test on prepare_diagnosis_metrics() alone cannot see.
#
# main_n_bootstrap/sensitivity_n_bootstrap are kept low (these campaigns are tiny and synthetic,
# not real bootstrap-quality data) purely for speed; the five fields under test are forced to
# deliberate non-NaN sentinel values via monkeypatch regardless of what the real trend/CI
# computation would have produced, so bootstrap size has no bearing on what's being asserted.

ESTIMATE_FIELDS = [
    "method1_trend_c_per_min", "primary_trend_c_per_min", "abs_primary_trend_c_per_min",
    "primary_confidence_interval_low", "primary_confidence_interval_high",
]


def _short_session_df():
    """~2s of data: guaranteed NOT_ASSESSABLE / SESSION_TOO_SHORT, no group-building needed."""
    rows = [_row(0, BASE_LAT, BASE_LON, 10.0), _row(2, BASE_LAT, BASE_LON, 10.1)]
    return build_temporal_candidate_masks(pd.DataFrame(rows))


def _force_nonnull_estimates(monkeypatch, trend_value, ci_low, ci_high):
    """Wrap the real trend_methods so their *real* dataframes still flow through process_campaign()
    end-to-end, but trend_c_per_min/confidence_interval_low/high are forced to deliberate,
    always-present sentinel values -- exactly the "raw method1/method2 already have real numbers"
    scenario the previous bug needed to leak."""
    import meteotracker_qc.temporal_drift_pipeline as pipeline_module

    real_pairwise_median_trend = pipeline_module.pairwise_median_trend
    real_fixed_effects_huber_trend = pipeline_module.fixed_effects_huber_trend

    def _forced(real_func, *args, **kwargs):
        result = dict(real_func(*args, **kwargs))
        result["trend_c_per_min"] = trend_value
        result["trend_c_per_hour"] = trend_value * 60.0
        result["confidence_interval_low"] = ci_low
        result["confidence_interval_high"] = ci_high
        return result

    monkeypatch.setattr(pipeline_module, "pairwise_median_trend", lambda *a, **k: _forced(real_pairwise_median_trend, *a, **k))
    monkeypatch.setattr(pipeline_module, "fixed_effects_huber_trend", lambda *a, **k: _forced(real_fixed_effects_huber_trend, *a, **k))


def test_not_assessable_session_row_nulls_all_five_estimate_fields(monkeypatch):
    _force_nonnull_estimates(monkeypatch, trend_value=0.5, ci_low=0.3, ci_high=0.7)
    df = _short_session_df()
    row = process_campaign("not_assessable_c", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=20, sensitivity_n_bootstrap=10)["session_row"]

    assert row["temporal_internal_assessability_status"] == "NOT_ASSESSABLE"
    for field in ESTIMATE_FIELDS:
        assert pd.isna(row[field]), f"{field} should be NaN for NOT_ASSESSABLE, got {row[field]!r}"


def test_partially_assessable_session_row_nulls_all_five_estimate_fields(monkeypatch):
    _force_nonnull_estimates(monkeypatch, trend_value=0.5, ci_low=0.3, ci_high=0.7)
    df = _synthetic_campaign_df(n_groups=2)
    row = process_campaign("partial_c", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=20, sensitivity_n_bootstrap=10)["session_row"]

    assert row["temporal_internal_assessability_status"] == "PARTIALLY_ASSESSABLE"
    for field in ESTIMATE_FIELDS:
        assert pd.isna(row[field]), f"{field} should be NaN for PARTIALLY_ASSESSABLE, got {row[field]!r}"


def test_assessable_session_row_preserves_estimate_fields(monkeypatch):
    _force_nonnull_estimates(monkeypatch, trend_value=0.5, ci_low=0.3, ci_high=0.7)
    df = _synthetic_campaign_df(n_groups=8)
    row = process_campaign("assessable_c", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=20, sensitivity_n_bootstrap=10)["session_row"]

    assert row["temporal_internal_assessability_status"] == "ASSESSABLE"
    assert row["method1_trend_c_per_min"] == pytest.approx(0.5)
    assert row["primary_trend_c_per_min"] == pytest.approx(0.5)
    assert row["abs_primary_trend_c_per_min"] == pytest.approx(0.5)
    assert row["primary_confidence_interval_low"] == pytest.approx(0.3)
    assert row["primary_confidence_interval_high"] == pytest.approx(0.7)


def test_fields_outside_the_five_are_untouched_by_the_fix(monkeypatch):
    """The fix must be surgical: method1/method2_huber keys other than the five named fields
    (e.g. the *_c_per_hour unit conversions, or method1's own confidence interval, which were
    never part of the leak this fix closes) must still pass through raw, unaltered -- for a
    NOT_ASSESSABLE session too, where the five target fields are now nulled but everything else
    the raw dicts contained must not be."""
    _force_nonnull_estimates(monkeypatch, trend_value=0.5, ci_low=0.3, ci_high=0.7)
    df = _short_session_df()
    row = process_campaign("not_assessable_passthrough", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=20, sensitivity_n_bootstrap=10)["session_row"]

    assert row["temporal_internal_assessability_status"] == "NOT_ASSESSABLE"
    # trend_c_per_min was forced to 0.5 above; a real, unpatched trend_c_per_hour derived from
    # it (0.5*60=30.0) proves the *_per_hour fields still flow straight from the raw dict.
    assert row["primary_trend_c_per_hour"] == pytest.approx(30.0)
    assert row["method1_trend_c_per_hour"] == pytest.approx(30.0)


def test_classification_fields_unaffected_by_forced_raw_values(monkeypatch):
    """Same synthetic input, run once with the real trend/CI computation and once with it
    forced to deliberate non-null sentinels: temporal_change_diagnosis, sensor_drift_interpretation
    and temporal_internal_assessability_status must be identical in both, proving the
    classification never depended on whichever raw numbers method1/method2 happened to produce
    once assessability already routes it to a terminal, non-numeric-dependent rule."""
    df = _short_session_df()
    row_real = process_campaign("cls_real", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=20, sensitivity_n_bootstrap=10)["session_row"]

    _force_nonnull_estimates(monkeypatch, trend_value=0.5, ci_low=0.3, ci_high=0.7)
    row_forced = process_campaign("cls_forced", df, MATCHING_POLICY, TDA_POLICY, main_n_bootstrap=20, sensitivity_n_bootstrap=10)["session_row"]

    for field in ("temporal_change_diagnosis", "sensor_drift_interpretation", "temporal_internal_assessability_status"):
        assert row_real[field] == row_forced[field], f"{field} differs: {row_real[field]!r} vs {row_forced[field]!r}"
