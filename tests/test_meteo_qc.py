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
