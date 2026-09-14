import pandas as pd

from meteotracker_qc.temporal_drift.candidates import build_temporal_candidate_masks

FLAG_COLS = [
    "qc_temp_isolated_spike", "qc_temp_impossible", "qc_gps_jump", "qc_spatial_jump",
    "qc_isolated_position_outlier", "qc_gps_freeze", "qc_sensor_stabilization",
    "qc_post_stop_recovery", "qc_low_ventilation_possible", "qc_temp_rate_anomaly",
    "qc_possible_gps_freeze",
]


def _row(**overrides):
    base = {
        "time_utc": pd.Timestamp("2026-02-13T09:00:00Z"),
        "canonical_latitude": 44.4949, "canonical_longitude": 11.3426,
        "canonical_temperature_c": 12.5,
        "keep_permissive": True, "keep_recommended": True, "keep_restrictive": True,
    }
    for col in FLAG_COLS:
        base[col] = False
    base.update(overrides)
    return pd.DataFrame([base])


def test_clean_point_is_candidate_under_all_three_profiles():
    df = build_temporal_candidate_masks(_row())
    assert df["temporal_candidate_permissive"].iloc[0]
    assert df["temporal_candidate_recommended"].iloc[0]
    assert df["temporal_candidate_conservative"].iloc[0]
    assert df["temporal_candidate_primary_reason"].iloc[0] is None


def test_missing_timestamp_excluded_from_all_profiles():
    df = build_temporal_candidate_masks(_row(time_utc=pd.NaT))
    assert not df["temporal_candidate_permissive"].iloc[0]
    assert not df["temporal_candidate_recommended"].iloc[0]
    assert not df["temporal_candidate_conservative"].iloc[0]
    assert df["temporal_candidate_primary_reason"].iloc[0] == "MISSING_TIMESTAMP"


def test_missing_coordinates_excluded():
    df = build_temporal_candidate_masks(_row(canonical_latitude=None))
    assert not df["temporal_candidate_recommended"].iloc[0]
    assert "MISSING_COORDINATES" in df["temporal_candidate_exclusion_reasons"].iloc[0]


def test_missing_temperature_excluded():
    df = build_temporal_candidate_masks(_row(canonical_temperature_c=None))
    assert not df["temporal_candidate_recommended"].iloc[0]
    assert df["temporal_candidate_primary_reason"].iloc[0] == "MISSING_TEMPERATURE"


def test_keep_recommended_false_excludes_recommended_only_when_no_hard_flag():
    df = build_temporal_candidate_masks(_row(keep_recommended=False))
    assert not df["temporal_candidate_recommended"].iloc[0]
    assert df["temporal_candidate_permissive"].iloc[0]


def test_gps_freeze_confirmed_excludes_all_three_profiles():
    df = build_temporal_candidate_masks(_row(qc_gps_freeze=True, keep_permissive=True, keep_recommended=True, keep_restrictive=True))
    assert not df["temporal_candidate_permissive"].iloc[0]
    assert not df["temporal_candidate_recommended"].iloc[0]
    assert not df["temporal_candidate_conservative"].iloc[0]


def test_sensor_stabilization_excludes_recommended_but_not_permissive():
    df = build_temporal_candidate_masks(_row(qc_sensor_stabilization=True))
    assert df["temporal_candidate_permissive"].iloc[0]
    assert not df["temporal_candidate_recommended"].iloc[0]


def test_optional_flags_excluded_only_under_conservative():
    for flag in ["qc_post_stop_recovery", "qc_low_ventilation_possible", "qc_temp_rate_anomaly", "qc_possible_gps_freeze"]:
        df = build_temporal_candidate_masks(_row(**{flag: True}))
        assert df["temporal_candidate_recommended"].iloc[0], f"{flag} must not exclude recommended by default"
        assert not df["temporal_candidate_conservative"].iloc[0], f"{flag} must exclude conservative"


def test_segment_break_flag_does_not_exclude_any_profile():
    df = _row()
    df["qc_segment_break"] = True
    out = build_temporal_candidate_masks(df)
    assert out["temporal_candidate_recommended"].iloc[0], "qc_segment_break is a valid measurement, not a per-point exclusion"


def test_multiple_failures_pick_deterministic_primary_reason():
    df = build_temporal_candidate_masks(_row(qc_temp_impossible=True, qc_gps_freeze=True))
    primary = df["temporal_candidate_primary_reason"].iloc[0]
    assert primary == "qc_temp_impossible"
    reasons = df["temporal_candidate_exclusion_reasons"].iloc[0]
    assert "qc_temp_impossible" in reasons and "qc_gps_freeze" in reasons
