from __future__ import annotations

import numpy as np
import pandas as pd


def dew_point_from_temp_humidity(temp_c: pd.Series, rh_pct: pd.Series) -> pd.Series:
    temp_k = temp_c + 273.15
    rh = np.clip(rh_pct, 0, 100)
    # Magnus approximation, valid for meteorological ranges and used only as a derived diagnostic.
    gamma = np.log(rh / 100.0) + 17.27 * temp_c / (temp_c + 237.3)
    return ((237.3 * gamma) / (17.27 - gamma)).clip(-100, 100)


def potential_temperature(temp_c: pd.Series, pressure_mbar: pd.Series) -> pd.Series:
    p = pressure_mbar / 1000.0
    theta_k = (temp_c + 273.15) * (1000.0 / p) ** 0.286
    return theta_k


def recompute_derived_variables(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    temp = pd.to_numeric(out.get("Temp[°C]", pd.Series(dtype=float)), errors="coerce")
    rh = pd.to_numeric(out.get("Hum[%]", pd.Series(dtype=float)), errors="coerce")
    press = pd.to_numeric(out.get("Press[mbar]", pd.Series(dtype=float)), errors="coerce")
    out["dewpoint_recomputed_c"] = dew_point_from_temp_humidity(temp, rh)
    out["theta_recomputed_k"] = potential_temperature(temp, press)
    out["dewpoint_difference_c"] = (pd.to_numeric(out.get("DP[°C]", pd.Series(dtype=float)), errors="coerce") - out["dewpoint_recomputed_c"])
    out["theta_difference_k"] = (pd.to_numeric(out.get("θ[K]", pd.Series(dtype=float)), errors="coerce") - out["theta_recomputed_k"])
    return out
