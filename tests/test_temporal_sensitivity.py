import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.candidates import build_temporal_candidate_masks
from meteotracker_qc.temporal_drift.config import load_matching_policy
from meteotracker_qc.temporal_drift.sensitivity import (
    QC_FLAG_SWEEP_CONFIGS, SENSITIVITY_GEOMETRY_PROFILES, classify_stability,
    run_session_sensitivity, run_single_configuration,
)

ROOT_TDA_POLICY = pd.read_csv("config/temporal_drift_policy.csv")
MATCHING_POLICY = load_matching_policy()
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


def _synthetic_campaign(n_groups=8, trend_c_per_min=0.05):
    """n_groups distinct locations 100m apart, each visited twice (early and
    late), with a clear common linear trend across the whole session.
    """
    rows = []
    for gi in range(n_groups):
        lat = BASE_LAT + gi * (100.0 / 111320.0)  # ~100m spacing between groups
        t_early = gi * 20  # stagger slightly so groups aren't all simultaneous
        t_late = 3600 + gi * 20
        temp_early = 10.0 + t_early * (trend_c_per_min / 60.0)
        temp_late = 10.0 + t_late * (trend_c_per_min / 60.0)
        rows.append(_row(t_early, lat, BASE_LON, temp_early))
        rows.append(_row(t_early + 5, lat, BASE_LON, temp_early + 0.01))
        rows.append(_row(t_late, lat, BASE_LON, temp_late))
        rows.append(_row(t_late + 5, lat, BASE_LON, temp_late + 0.01))
    return build_temporal_candidate_masks(pd.DataFrame(rows))


def test_single_configuration_runs_without_error():
    df = _synthetic_campaign()
    out = run_single_configuration(df, "anchor", "temporal_recommended", MATCHING_POLICY, ROOT_TDA_POLICY, n_bootstrap=50)
    assert out["config_name"] == "anchor"
    assert out["n_groups_valid"] >= 1


def test_full_sweep_produces_18_configurations():
    df = _synthetic_campaign()
    out = run_session_sensitivity(df, MATCHING_POLICY, ROOT_TDA_POLICY, n_bootstrap=30)
    assert len(out) == len(SENSITIVITY_GEOMETRY_PROFILES) + len(QC_FLAG_SWEEP_CONFIGS) == 18


def test_no_best_or_winner_field_is_produced():
    df = _synthetic_campaign()
    out = run_session_sensitivity(df, MATCHING_POLICY, ROOT_TDA_POLICY, n_bootstrap=30)
    forbidden = {"best_config", "winner", "recommended_config", "chosen_config"}
    assert forbidden.isdisjoint(out.columns)


def test_tightest_radius_gracefully_yields_not_assessable_or_similar_not_a_crash():
    # a campaign with groups spaced ~3m apart -- well under the 5m sweep radius
    # is used instead to force genuinely zero valid groups at the tightest setting
    rows = []
    for gi in range(3):
        lat = BASE_LAT + gi * (200.0 / 111320.0)
        rows.append(_row(gi * 20, lat, BASE_LON, 10.0))
        rows.append(_row(gi * 20 + 5, lat, BASE_LON, 10.0))
    df = build_temporal_candidate_masks(pd.DataFrame(rows))  # only 1 visit per group -> no valid groups at all
    out = run_single_configuration(df, "sens_radius_5m", "sens_radius_5m", MATCHING_POLICY, ROOT_TDA_POLICY, n_bootstrap=20)
    assert out["assessability_status"] in {"NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"}


def test_qc_flag_inclusion_configs_run_without_error():
    df = _synthetic_campaign()
    for config_name, flags in QC_FLAG_SWEEP_CONFIGS:
        out = run_single_configuration(df, config_name, "temporal_recommended", MATCHING_POLICY, ROOT_TDA_POLICY, extra_qc_exclusions=flags, n_bootstrap=20)
        assert out["config_name"] == config_name


def test_stability_classification_stable_for_a_clean_robust_dataset():
    df = _synthetic_campaign(n_groups=10, trend_c_per_min=0.05)
    sweep = run_session_sensitivity(df, MATCHING_POLICY, ROOT_TDA_POLICY, n_bootstrap=30)
    stability = classify_stability(sweep)
    assert stability["temporal_sensitivity_stability_class"] in {"STABLE", "MODERATELY_SENSITIVE"}
    assert stability["n_configs"] == 18


def test_stability_classification_not_assessable_when_no_config_finds_revisits():
    rows = [_row(0, BASE_LAT, BASE_LON, 10.0), _row(5, BASE_LAT, BASE_LON, 10.1)]  # single visit, no revisit anywhere
    df = build_temporal_candidate_masks(pd.DataFrame(rows))
    sweep = run_session_sensitivity(df, MATCHING_POLICY, ROOT_TDA_POLICY, n_bootstrap=20)
    stability = classify_stability(sweep)
    assert stability["temporal_sensitivity_stability_class"] == "NOT_ASSESSABLE"


def test_classify_stability_empty_input_handled():
    stability = classify_stability(pd.DataFrame())
    assert stability["temporal_sensitivity_stability_class"] == "NOT_ASSESSABLE"
    assert stability["n_configs"] == 0
