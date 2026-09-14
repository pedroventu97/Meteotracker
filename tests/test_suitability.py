import pandas as pd

from meteotracker_qc.session_qc.suitability import ANALYSIS_TYPES, compute_all_suitability, evaluate_suitability

SUITABILITY_POLICY = pd.read_csv("config/session_suitability_policy.csv")


def _session_row(**overrides):
    base = dict(
        canonical_campaign_id="c", n_raw=2000, gps_valid_fraction=0.97,
        valid_distance_recommended_km=4.5, longest_valid_segment_distance_km=4.3,
        recommended_to_observed_distance_ratio=0.9, recommended_to_observed_time_ratio=0.9,
        n_segments=2, gps_freeze_fraction=0.03, nominal_time_span_s=2000.0,
        keep_fraction_recommended=0.9, gap_fraction_of_nominal_span=0.02,
    )
    base.update(overrides)
    return pd.DataFrame([base])


def test_all_six_analysis_types_have_rules():
    assert len(ANALYSIS_TYPES) == 6
    for analysis_type in ANALYSIS_TYPES:
        out = evaluate_suitability(_session_row(), SUITABILITY_POLICY, analysis_type)
        assert out["suitability_status"].notna().all(), analysis_type


def test_satellite_coincidence_always_not_assessable_external_data_required():
    out = evaluate_suitability(_session_row(), SUITABILITY_POLICY, "satellite_coincidence")
    assert out["suitability_status"].iloc[0] == "NOT_ASSESSABLE_EXTERNAL_DATA_REQUIRED"
    # Even a "perfect" session cannot escape this -- no satellite metadata exists in the repo.
    out2 = evaluate_suitability(_session_row(gps_valid_fraction=1.0, n_segments=1), SUITABILITY_POLICY, "satellite_coincidence")
    assert out2["suitability_status"].iloc[0] == "NOT_ASSESSABLE_EXTERNAL_DATA_REQUIRED"


def test_spatial_mapping_yes_for_good_session():
    out = evaluate_suitability(_session_row(), SUITABILITY_POLICY, "spatial_mapping")
    assert out["suitability_status"].iloc[0] == "YES"


def test_spatial_mapping_no_for_no_valid_gps():
    out = evaluate_suitability(_session_row(gps_valid_fraction=0.01), SUITABILITY_POLICY, "spatial_mapping")
    assert out["suitability_status"].iloc[0] == "NO"


def test_route_comparison_does_not_import_repeated_routes():
    import ast
    import inspect

    import meteotracker_qc.session_qc.suitability as suitability_module
    tree = ast.parse(inspect.getsource(suitability_module))
    imported_modules = [
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    ] + [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not any("repeated_routes" in m for m in imported_modules), imported_modules


def test_temporal_drift_analysis_suitability_is_about_sufficiency_not_absence_of_drift():
    out = evaluate_suitability(_session_row(), SUITABILITY_POLICY, "temporal_drift_analysis")
    # Never any drift-classification vocabulary leaking into suitability status.
    assert out["suitability_status"].iloc[0] not in {"TEMPORALLY_STABLE", "SENSOR_DRIFT", "BACKGROUND_CHANGE"}
    assert out["suitability_status"].iloc[0] in {"YES_WITH_LIMITATIONS", "PARTIAL", "NO", "NOT_ASSESSABLE"}


def test_full_route_statistics_distinct_from_spatial_mapping_for_fragmented_session():
    fragmented = _session_row(n_segments=20, recommended_to_observed_time_ratio=0.3)
    mapping = evaluate_suitability(fragmented, SUITABILITY_POLICY, "spatial_mapping")
    full_route = evaluate_suitability(fragmented, SUITABILITY_POLICY, "full_route_statistics")
    # Fragmented session can still map locally (YES/YES_WITH_LIMITATIONS/PARTIAL)
    # while being explicitly unusable for whole-route statistics (NO).
    assert full_route["suitability_status"].iloc[0] == "NO"
    assert mapping["suitability_status"].iloc[0] != "NO"


def test_compute_all_suitability_produces_long_format_per_campaign():
    sessions = pd.concat([_session_row(canonical_campaign_id="a"), _session_row(canonical_campaign_id="b")], ignore_index=True)
    segments = pd.DataFrame({
        "canonical_campaign_id": ["a", "a", "b"],
        "segment_id": [0, 1, 0],
        "segment_qc_status": ["PASS", "PARTIAL", "PASS_WITH_WARNINGS"],
    })
    out = compute_all_suitability(sessions, SUITABILITY_POLICY, segments)
    assert len(out) == 2 * len(ANALYSIS_TYPES)
    assert set(out["canonical_campaign_id"].unique()) == {"a", "b"}
    a_mapping = out[(out.canonical_campaign_id == "a") & (out.analysis_type == "spatial_mapping")].iloc[0]
    assert "0" in a_mapping["qualifying_segments"].split(";")
