import pandas as pd

from meteotracker_qc.stabilization import detect_sensor_stabilization


def test_sensor_stabilization_detects_warm_up():
    temperatures = pd.Series([25.0, 25.1, 25.4, 25.5, 25.6, 25.7, 25.8, 25.9, 26.0, 26.1])
    out = detect_sensor_stabilization(temperatures, window=3, min_stable_seconds=5)
    assert "qc_sensor_stabilization" in out.columns
    assert out["qc_sensor_stabilization"].sum() >= 1


def test_warm_up_is_detected():
    temps = pd.Series([20.0, 20.2, 20.4, 20.6, 20.8, 21.0])
    out = detect_sensor_stabilization(temps)
    assert out["qc_sensor_stabilization"].sum() >= 1
