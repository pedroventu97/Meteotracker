import pandas as pd

from meteotracker_qc.session_qc.session_status import compute_session_status

POLICY = pd.read_csv("config/session_qc_policy.csv")
PROFILE = "recommended_session"


def _row(**overrides):
    base = dict(
        canonical_campaign_id="c", source_file="f.csv", n_raw=2000,
        nominal_time_span_s=2000.0, observed_sampling_duration_s=1990.0,
        gap_fraction_of_nominal_span=0.01, n_segments=2,
        gps_valid_fraction=0.97, gps_freeze_fraction=0.03, spatial_jump_fraction=0.0,
        temp_valid_fraction=1.0, impossible_value_fraction=0.0, thermal_problem_fraction=0.005,
        low_ventilation_possible_fraction=0.1, stabilization_fraction=0.1,
        observed_distance_km=5.0, longest_valid_segment_distance_km=4.8,
        is_reduced_schema=False, canonical_fields_present_fraction=1.0,
        keep_fraction_recommended=0.95, keep_fraction_permissive=1.0, keep_fraction_restrictive=0.8,
    )
    base.update(overrides)
    return pd.DataFrame([base])


def test_near_perfect_session_passes():
    df = compute_session_status(_row(), POLICY, PROFILE)
    assert df["session_qc_status"].iloc[0] == "PASS"
    for dim in ["sampling_integrity", "gps_quality", "thermal_signal", "ventilation_risk", "stabilization_quality", "spatial_continuity", "schema_completeness"]:
        assert df[f"{dim}_status"].iloc[0] == "OK", dim


def test_pass_with_warnings_from_moderate_freeze():
    df = compute_session_status(_row(gps_freeze_fraction=0.20), POLICY, PROFILE)
    assert df["gps_quality_status"].iloc[0] == "WARNING"
    assert df["session_qc_status"].iloc[0] == "PASS_WITH_WARNINGS"


def test_partial_from_low_keep_fraction():
    df = compute_session_status(_row(keep_fraction_recommended=0.40, gps_valid_fraction=0.7), POLICY, PROFILE)
    assert df["session_qc_status"].iloc[0] == "PARTIAL"


def test_partial_from_long_gap_even_with_decent_keep_fraction():
    # Mirrors Bologna-Ravenna: keep_fraction_recommended is fine (0.87) but
    # the gap fraction alone must still force PARTIAL.
    df = compute_session_status(_row(keep_fraction_recommended=0.87, gap_fraction_of_nominal_span=0.84, n_segments=5), POLICY, PROFILE)
    assert df["sampling_integrity_status"].iloc[0] in {"WARNING", "POOR"}
    assert df["session_qc_status"].iloc[0] == "PARTIAL"


def test_reject_only_from_genuine_data_absence():
    df = compute_session_status(_row(gps_valid_fraction=0.01, temp_valid_fraction=0.01), POLICY, PROFILE)
    assert df["session_qc_status"].iloc[0] == "REJECT"


def test_keep_recommended_zero_alone_does_not_force_reject():
    df = compute_session_status(
        _row(keep_fraction_recommended=0.0, gps_valid_fraction=0.69, temp_valid_fraction=1.0, nominal_time_span_s=122.0, observed_sampling_duration_s=122.0),
        POLICY, PROFILE,
    )
    assert df["session_qc_status"].iloc[0] != "REJECT"


def test_too_short_session_is_not_assessable():
    df = compute_session_status(_row(nominal_time_span_s=20.0, observed_sampling_duration_s=20.0), POLICY, PROFILE)
    assert df["sampling_integrity_status"].iloc[0] == "NOT_ASSESSABLE"
    assert df["session_qc_status"].iloc[0] == "NOT_ASSESSABLE"


def test_reduced_schema_flagged_poor():
    df = compute_session_status(_row(is_reduced_schema=True, canonical_fields_present_fraction=0.3), POLICY, PROFILE)
    assert df["schema_completeness_status"].iloc[0] == "POOR"


def test_ventilation_risk_dimension_never_poor_at_session_level():
    df = compute_session_status(_row(low_ventilation_possible_fraction=0.99), POLICY, PROFILE)
    assert df["ventilation_risk_status"].iloc[0] in {"OK", "WARNING", "NOT_ASSESSABLE"}


def test_session_primary_and_secondary_reasons_present_for_non_pass():
    df = compute_session_status(_row(gps_freeze_fraction=0.32, gap_fraction_of_nominal_span=0.5), POLICY, PROFILE)
    row = df.iloc[0]
    assert pd.notna(row["session_primary_reason"])
    assert row["session_reason_count"] >= 1
