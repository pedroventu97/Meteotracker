from pathlib import Path

import pandas as pd

from meteotracker_qc.schema import missing_required_fields, normalize_columns

RAW_ROOT = Path(__file__).resolve().parent / "fixtures" / "schema"

# Synthetic values under the exact headers of the four observed export schemas.
# No acquisition data is required or copied into the portable suite.
SCHEMA_VARIANT_FILES = {
    f"{width}-col": RAW_ROOT / f"{width}-col.csv" for width in (42, 43, 44, 5)
}


def test_schema_variant_files_exist():
    for label, path in SCHEMA_VARIANT_FILES.items():
        assert path.exists(), f"expected {label} fixture file missing: {path}"
        assert len(pd.read_csv(path).columns) == int(label.split("-")[0])


def test_42_col_and_44_col_variants_have_speed_and_radiation_present():
    for label in ("42-col", "43-col", "44-col"):
        df = pd.read_csv(SCHEMA_VARIANT_FILES[label])
        out, report = normalize_columns(df)
        speed_row = report.loc[report["canonical_name"] == "speed_device_kmh_raw"].iloc[0]
        assert speed_row["present"]
        assert out["canonical_speed_device_kmh_raw"].notna().any()


def test_5_col_variant_has_only_time_lat_lon_alt_temp_present():
    df = pd.read_csv(SCHEMA_VARIANT_FILES["5-col"])
    out, report = normalize_columns(df)

    present = set(report.loc[report["present"], "canonical_name"])
    assert present == {"timestamp_raw", "latitude", "longitude", "altitude_m", "temperature_c"}

    # Original columns are never dropped or renamed.
    for original_col in ["Time", "Lat", "Lon", "Alt[m]", "Temp[°C]"]:
        assert original_col in out.columns

    # Absent fields become all-NA canonical columns, never invented values.
    assert out["canonical_speed_device_kmh_raw"].isna().all()
    assert out["canonical_humidity_pct"].isna().all()
    speed_report_row = report.loc[report["canonical_name"] == "speed_device_kmh_raw"].iloc[0]
    assert not speed_report_row["present"]
    assert speed_report_row["n_non_missing"] == 0


def test_missing_sentinel_dash_becomes_nan_not_a_string():
    df = pd.DataFrame({
        "Time": ["2026-01-01T09:00:00+01:00", "2026-01-01T09:00:01+01:00"],
        "Lat": [44.49, 44.49],
        "Lon": [11.34, 11.34],
        "Temp[°C]": [20.0, 20.1],
        "Radiation[]": ["-", "0.8"],
    })
    out, report = normalize_columns(df)
    assert out["canonical_radiation_raw"].iloc[0] != out["canonical_radiation_raw"].iloc[0]  # NaN
    assert out["canonical_radiation_raw"].iloc[1] == 0.8


def test_missing_required_fields_flags_absent_and_all_missing_columns():
    df = pd.DataFrame({
        "Time": ["2026-01-01T09:00:00+01:00"],
        "Lat": [44.49],
        "Lon": [11.34],
        "Temp[°C]": [20.0],
        "Hum[%]": ["-"],
    })
    out, _ = normalize_columns(df)
    missing = missing_required_fields(out, ["temperature_c", "humidity_pct", "speed_device_kmh_raw"])
    assert missing == ["humidity_pct", "speed_device_kmh_raw"]
    assert missing_required_fields(out, ["temperature_c"]) == []
