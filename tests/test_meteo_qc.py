import numpy as np
import pandas as pd

from meteotracker_qc.meteo_qc import detect_meteo_issues


def test_impossible_temperature_and_humidity_flags():
    df = pd.DataFrame(
        {
            "Temp[°C]": [-100, 60, 20],
            "Hum[%]": [-5, 110, 55],
            "Press[mbar]": [800, 1100, 1010],
        }
    )
    out = detect_meteo_issues(df)
    assert out["qc_temp_impossible"].iloc[0]
    assert out["qc_humidity_impossible"].iloc[1]
    assert out["qc_pressure_impossible"].iloc[0]


def test_isolated_temperature_spike_is_flagged():
    df = pd.DataFrame({"Temp[°C]": [20.0, 20.0, 20.0, 20.0, 40.0]})
    out = detect_meteo_issues(df)
    assert out["qc_temp_spike"].sum() >= 1


def test_persistent_temperature_change_is_not_spike():
    df = pd.DataFrame({"Temp[°C]": [20.0, 21.0, 22.0, 23.0, 24.0]})
    out = detect_meteo_issues(df)
    assert not out["qc_temp_spike"].any()


def test_isolated_spike_alias_matches_new_canonical_column():
    df = pd.DataFrame({"Temp[°C]": [20.0, 20.0, 20.0, 20.0, 40.0]})
    out = detect_meteo_issues(df)
    assert out["qc_temp_spike"].tolist() == out["qc_temp_isolated_spike"].tolist()


def test_temp_rate_anomaly_flags_short_isolated_jump():
    df = pd.DataFrame({
        "Temp[°C]": [20.0, 20.0, 20.0, 24.0, 20.0, 20.0, 20.0, 20.0],
        "dt_s": [np.nan, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        "segment_id": [0] * 8,
    })
    config = {"thermal": {"rate_anomaly_threshold_c_per_s": 1.0, "rate_anomaly_persistence_s": 20.0}}
    out = detect_meteo_issues(df, config=config)
    assert out["qc_temp_rate_anomaly"].any()


def test_temp_rate_anomaly_deescalates_for_persistent_real_gradient():
    # A steady +0.15 C/s climb sustained for 30s (>= persistence threshold)
    # must not be flagged as an anomaly -- a real, sustained urban
    # microclimate transition, not a sensor error.
    n = 31
    df = pd.DataFrame({
        "Temp[°C]": [20.0 + 0.15 * i for i in range(n)],
        "dt_s": [np.nan] + [1.0] * (n - 1),
        "segment_id": [0] * n,
    })
    config = {"thermal": {"rate_anomaly_threshold_c_per_s": 0.10, "rate_anomaly_persistence_s": 20.0}}
    out = detect_meteo_issues(df, config=config)
    assert not out["qc_temp_rate_anomaly"].any()


def test_temp_rate_not_evaluated_across_segment_break():
    df = pd.DataFrame({
        "Temp[°C]": [20.0, 20.0, 35.0],
        "dt_s": [np.nan, 1.0, 1.0],
        "segment_id": [0, 0, 1],
    })
    out = detect_meteo_issues(df)
    assert pd.isna(out["temp_rate_c_per_s"].iloc[2])


def test_sensor_plateau_possible_flags_long_constant_stretch():
    n = 130
    df = pd.DataFrame({"Temp[°C]": [20.0] * n})
    config = {"thermal": {"plateau_std_epsilon_c": 0.001, "plateau_min_duration_s": 100.0}}
    out = detect_meteo_issues(df, config=config)
    assert out["qc_sensor_plateau_possible"].any()


def test_sensor_plateau_not_flagged_for_normal_variability():
    n = 130
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"Temp[°C]": 20.0 + np.cumsum(rng.normal(0, 0.05, n))})
    config = {"thermal": {"plateau_std_epsilon_c": 0.001, "plateau_min_duration_s": 100.0}}
    out = detect_meteo_issues(df, config=config)
    assert not out["qc_sensor_plateau_possible"].any()


def test_temp_humidity_pressure_impossible_are_independent_flags():
    df = pd.DataFrame({
        "Temp[°C]": [70.0, 20.0],
        "Hum[%]": [50.0, 150.0],
        "Press[mbar]": [1010.0, 500.0],
    })
    out = detect_meteo_issues(df)
    assert out["qc_temp_impossible"].tolist() == [True, False]
    assert out["qc_humidity_impossible"].tolist() == [False, True]
    assert out["qc_pressure_impossible"].tolist() == [False, True]
