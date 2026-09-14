import pandas as pd

from meteotracker_qc.session_qc.segment_status import compute_segment_status

POLICY = pd.read_csv("config/session_qc_policy.csv")
PROFILE = "recommended_session"


def _row(**overrides):
    base = dict(
        canonical_campaign_id="c", source_file="f.csv", segment_id=0,
        n_raw=200, n_permissive=200, n_recommended=195, n_restrictive=180,
        observed_sampling_duration_s=200.0, observed_distance_km=1.0,
        valid_duration_recommended_s=195.0, valid_distance_recommended_km=0.98,
        n_short_gaps=0, n_long_gaps=0,
        gps_valid_fraction=0.99, gps_freeze_fraction=0.02, possible_gps_freeze_fraction=0.0,
        spatial_jump_fraction=0.0, isolated_position_outlier_fraction=0.0,
        unrealistic_speed_fraction=0.0, unrealistic_acceleration_fraction=0.0,
        low_speed_device_fraction=0.1, low_speed_gps_fraction=0.1, low_ventilation_possible_fraction=0.05,
        stationary_fraction=0.02, stop_fraction=0.0, post_stop_recovery_fraction=0.0,
        temp_valid_fraction=1.0, temp_spike_fraction=0.0, temp_rate_anomaly_fraction=0.0,
        sensor_plateau_fraction=0.0, impossible_value_fraction=0.0,
        stabilization_fraction=0.05, stabilization_reached=True, stabilization_reached_after_s=10.0,
        stabilization_reason_code="slope_confirmed_stable",
        excluded_recommended_fraction=0.025, primary_exclusion_reason=None, primary_exclusion_family=None,
        secondary_exclusion_reasons="", exclusion_reason_count=0.0, multi_flagged_fraction=0.0,
    )
    base.update(overrides)
    return pd.DataFrame([base])


def test_fully_valid_segment_passes():
    df = compute_segment_status(_row(), POLICY, PROFILE)
    assert df["segment_qc_status"].iloc[0] == "PASS"
    for dim in ["sampling_integrity", "gps_quality", "thermal_quality", "ventilation_risk", "stabilization", "spatial_continuity"]:
        assert df[f"segment_{dim}_status"].iloc[0] == "OK", dim


def test_segment_with_moderate_gps_freeze_gets_warning_rollup():
    df = compute_segment_status(_row(gps_freeze_fraction=0.20), POLICY, PROFILE)
    assert df["segment_gps_quality_status"].iloc[0] == "WARNING"
    assert df["segment_qc_status"].iloc[0] == "PASS_WITH_WARNINGS"


def test_segment_with_high_gps_freeze_gets_poor():
    df = compute_segment_status(_row(gps_freeze_fraction=0.32), POLICY, PROFILE)
    assert df["segment_gps_quality_status"].iloc[0] == "POOR"


def test_segment_partially_valid_gets_partial_rollup():
    df = compute_segment_status(_row(excluded_recommended_fraction=0.7, gps_valid_fraction=0.6), POLICY, PROFILE)
    assert df["segment_qc_status"].iloc[0] == "PARTIAL"


def test_short_segment_is_not_assessable():
    df = compute_segment_status(_row(observed_sampling_duration_s=10.0), POLICY, PROFILE)
    assert df["segment_sampling_integrity_status"].iloc[0] == "NOT_ASSESSABLE"
    assert df["segment_qc_status"].iloc[0] == "NOT_ASSESSABLE"


def test_low_gps_valid_fraction_is_reject_not_partial():
    # Genuine data absence (not just excluded-under-recommended) -> REJECT.
    df = compute_segment_status(_row(gps_valid_fraction=0.02, excluded_recommended_fraction=0.9), POLICY, PROFILE)
    assert df["segment_qc_status"].iloc[0] == "REJECT"


def test_keep_recommended_zero_does_not_force_reject_when_gps_and_temp_are_real():
    # Mirrors the real 91-row short-campaign case: keep_recommended=0 (fully
    # excluded) but GPS and temperature data are genuinely present.
    df = compute_segment_status(
        _row(
            observed_sampling_duration_s=122.0, excluded_recommended_fraction=1.0,
            gps_valid_fraction=0.69, temp_valid_fraction=1.0,
            stabilization_fraction=1.0, stabilization_reached=False,
            stabilization_reason_code="STABILIZATION_NOT_REACHED",
        ),
        POLICY, PROFILE,
    )
    assert df["segment_qc_status"].iloc[0] != "REJECT"
    assert df["segment_qc_status"].iloc[0] == "PARTIAL"


def test_thermal_impossible_value_is_always_poor():
    df = compute_segment_status(_row(impossible_value_fraction=0.01), POLICY, PROFILE)
    assert df["segment_thermal_quality_status"].iloc[0] == "POOR"


def test_thermal_not_assessable_when_temperature_mostly_missing():
    df = compute_segment_status(_row(temp_valid_fraction=0.1), POLICY, PROFILE)
    assert df["segment_thermal_quality_status"].iloc[0] == "NOT_ASSESSABLE"


def test_ventilation_risk_never_poor():
    df = compute_segment_status(_row(low_ventilation_possible_fraction=0.99), POLICY, PROFILE)
    assert df["segment_ventilation_risk_status"].iloc[0] in {"OK", "WARNING", "NOT_ASSESSABLE"}


def test_stabilization_never_reached_is_poor_when_fraction_high():
    df = compute_segment_status(
        _row(stabilization_fraction=0.9, stabilization_reached=False, stabilization_reason_code="STABILIZATION_NOT_REACHED"),
        POLICY, PROFILE,
    )
    assert df["segment_stabilization_status"].iloc[0] == "POOR"


def test_reason_code_present_for_every_non_ok_dimension():
    df = compute_segment_status(_row(gps_freeze_fraction=0.32, temp_spike_fraction=0.5), POLICY, PROFILE)
    row = df.iloc[0]
    for dim in ["gps_quality", "thermal_quality"]:
        status = row[f"segment_{dim}_status"]
        if status != "OK":
            assert pd.notna(row[f"segment_{dim}_reason_code"]), f"{dim} status={status} has no reason code"
