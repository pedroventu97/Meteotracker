from __future__ import annotations

import numpy as np
import pandas as pd

# Canonical column registry: canonical_name -> candidate original header names
# (priority order), unit, expected kind. All four raw schema variants observed
# in data/raw/ (42/43/44/5-column) use identical header spelling for shared
# fields -- they differ only in *which* columns are present, not in naming --
# so normalization here is presence detection + numeric coercion, not name
# aliasing. The candidate-list form is kept so a future export using different
# header text only needs a registry edit, not a code change.
CANONICAL_COLUMNS: dict[str, dict[str, object]] = {
    "timestamp_raw": {"candidates": ["Time"], "unit": "ISO8601 string", "kind": "text"},
    "latitude": {"candidates": ["Lat"], "unit": "degrees", "kind": "numeric"},
    "longitude": {"candidates": ["Lon"], "unit": "degrees", "kind": "numeric"},
    "temperature_c": {"candidates": ["Temp[°C]"], "unit": "C", "kind": "numeric"},
    "humidity_pct": {"candidates": ["Hum[%]"], "unit": "%", "kind": "numeric"},
    "pressure_mbar": {"candidates": ["Press[mbar]"], "unit": "mbar", "kind": "numeric"},
    "altitude_m": {"candidates": ["Alt[m]"], "unit": "m", "kind": "numeric"},
    "speed_device_kmh_raw": {"candidates": ["Speed[km/h]"], "unit": "km/h", "kind": "numeric"},
    "radiation_raw": {"candidates": ["Radiation[]"], "unit": "unitless (undeclared)", "kind": "numeric"},
    "bluetooth_rssi_dbm": {"candidates": ["BT[dBm]"], "unit": "dBm", "kind": "numeric"},
    "dewpoint_device_c": {"candidates": ["DP[°C]"], "unit": "C", "kind": "numeric"},
    "theta_device_k": {"candidates": ["θ[K]"], "unit": "K", "kind": "numeric"},
    "device_delta_temp_c_per_s": {"candidates": ["delta Temp[°C/sec]"], "unit": "C/s", "kind": "numeric"},
}

MISSING_VALUE_SENTINELS = ["-"]


def normalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add canonical-named numeric columns alongside the original raw columns.

    Never drops or renames original columns -- every ``canonical_*`` column is
    a pure addition. A source column that is absent for this file's schema
    variant (e.g. the 5-column reduced re-exports) becomes an all-NA canonical
    column, never an invented value. Returns ``(df_with_canonical_columns,
    schema_report)`` where ``schema_report`` has one row per canonical field:
    ``canonical_name, original_name, present, conversion_applied,
    n_non_missing, pct_non_missing, unit``.
    """
    out = df.copy()
    report_rows: list[dict[str, object]] = []
    n_rows = len(out)
    for canonical_name, spec in CANONICAL_COLUMNS.items():
        candidates = spec["candidates"]
        original_name = next((c for c in candidates if c in df.columns), None)
        out_col = f"canonical_{canonical_name}"
        if original_name is None:
            if spec["kind"] == "text":
                out[out_col] = pd.Series(pd.NA, index=out.index, dtype="object")
            else:
                out[out_col] = pd.Series(np.nan, index=out.index, dtype="float64")
            report_rows.append({
                "canonical_name": canonical_name,
                "original_name": None,
                "present": False,
                "conversion_applied": "none (column absent for this schema variant)",
                "n_non_missing": 0,
                "pct_non_missing": np.nan,
                "unit": spec["unit"],
            })
            continue

        raw_series = df[original_name]
        if spec["kind"] == "numeric":
            converted = pd.to_numeric(raw_series.replace(MISSING_VALUE_SENTINELS, np.nan), errors="coerce")
            conversion = "to_numeric, '-' sentinel -> NaN"
            n_non_missing = int(converted.notna().sum())
        else:
            converted = raw_series
            conversion = "passthrough"
            n_non_missing = int(raw_series.notna().sum())

        out[out_col] = converted
        report_rows.append({
            "canonical_name": canonical_name,
            "original_name": original_name,
            "present": True,
            "conversion_applied": conversion,
            "n_non_missing": n_non_missing,
            "pct_non_missing": (n_non_missing / n_rows) if n_rows else np.nan,
            "unit": spec["unit"],
        })
    return out, pd.DataFrame(report_rows)


def missing_required_fields(df: pd.DataFrame, required_canonical_names: list[str]) -> list[str]:
    """Return canonical field names required by a check but not usably present
    (column absent, or present but 100% missing) in this normalized frame.

    Callers use this to decide whether to compute a check at all, versus
    reporting it as not evaluable (reason code MISSING_REQUIRED_FIELD) rather
    than silently treating an unevaluated check as a pass.
    """
    missing = []
    for name in required_canonical_names:
        col = f"canonical_{name}"
        if col not in df.columns or df[col].notna().sum() == 0:
            missing.append(name)
    return missing
