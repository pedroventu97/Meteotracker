import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.gps_qc import detect_gps_issues, evaluate_coord_outside_aoi, _resolve_aoi_path
from meteotracker_qc.flag_table import build_flag_table, load_flag_schema, severity_lookup


def test_aoi_path_resolves_from_project_tree():
    path = _resolve_aoi_path({"aoi_geojson": "data/aoi/bologna_e0_aoi_v0.1.geojson"})
    assert path is not None
    assert path.is_file()
    assert path.name == "bologna_e0_aoi_v0.1.geojson"


def test_coord_outside_aoi_inside_outside_and_missing():
    # Bologna center inside; Milan clearly outside; missing -> NA
    df = pd.DataFrame(
        {
            "Time": pd.to_datetime(
                [
                    "2026-01-01 09:00:00",
                    "2026-01-01 09:00:01",
                    "2026-01-01 09:00:02",
                ]
            ),
            "Lat": [44.4949, 45.4642, np.nan],
            "Lon": [11.3426, 9.1900, 11.3426],
        }
    )
    out = detect_gps_issues(df)
    assert out.loc[0, "qc_coord_outside_aoi"] is False or out.loc[0, "qc_coord_outside_aoi"] == False
    assert bool(out.loc[1, "qc_coord_outside_aoi"]) is True
    assert pd.isna(out.loc[2, "qc_coord_outside_aoi"])
    assert bool(out.loc[2, "qc_coord_missing"]) is True


def test_evaluate_coord_outside_aoi_helper_direct():
    aoi = _resolve_aoi_path({})
    assert aoi is not None
    lat = pd.Series([44.4949, 45.0, np.nan])
    lon = pd.Series([11.3426, 9.0, 11.0])
    series = evaluate_coord_outside_aoi(lat, lon, aoi_path=aoi)
    assert series.iloc[0] == False
    assert series.iloc[1] == True
    assert pd.isna(series.iloc[2])


def test_flag_table_emits_row_for_coord_missing():
    schema = load_flag_schema()
    severities = severity_lookup(schema, "recommended")
    assert severities["qc_coord_missing"] == "exclude"
    assert severities["qc_coord_outside_aoi"] == "warn"

    df = pd.DataFrame(
        {
            "qc_coord_missing": [False, True, False],
            "qc_coord_outside_aoi": [False, pd.NA, True],
        }
    )
    table = build_flag_table(
        df,
        canonical_campaign_id="TEST_CAMPAIGN",
        source_file="demo/test.csv",
        file_sha256="abcdef0123456789deadbeef",
        qc_profile="recommended",
        schema=schema,
        config_fingerprint="fp-test",
        code_commit="TBD",
        applied_at=pd.Timestamp("2026-11-05T16:00:00", tz="Europe/Rome").to_pydatetime(),
    )
    codes = set(table["flag_code"])
    assert "qc_coord_missing" in codes
    assert "qc_coord_outside_aoi" in codes
    missing_rows = table[table["flag_code"] == "qc_coord_missing"]
    assert len(missing_rows) == 1
    assert missing_rows.iloc[0]["source_row"] == 1
    assert missing_rows.iloc[0]["observation_id"] == "abcdef012345:1"
    assert missing_rows.iloc[0]["severity"] == "exclude"
    assert missing_rows.iloc[0]["reversible"] is True or missing_rows.iloc[0]["reversible"] == True
    outside_rows = table[table["flag_code"] == "qc_coord_outside_aoi"]
    assert len(outside_rows) == 1
    assert outside_rows.iloc[0]["severity"] == "warn"
    assert outside_rows.iloc[0]["source_row"] == 2
    # NA outside_aoi on row 1 must not emit a flag
    assert list(table["source_row"]).count(1) == 1


def test_flag_table_file_level_duplicate():
    schema = load_flag_schema()
    table = build_flag_table(
        pd.DataFrame({"qc_coord_missing": [False]}),
        canonical_campaign_id="DUP_CAMPAIGN",
        source_file="x.csv",
        file_sha256="1234567890ab",
        duplicate_type="byte-identical",
        schema=schema,
    )
    assert (table["flag_code"] == "DUP_BYTE_IDENTICAL").any()
    dup = table[table["flag_code"] == "DUP_BYTE_IDENTICAL"].iloc[0]
    assert dup["source_row"] == -1
    assert dup["severity"] == "exclude"
