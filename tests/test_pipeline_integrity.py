import pandas as pd
from meteotracker_qc.config_resources import resource

from meteotracker_qc.time_qc import detect_time_issues
from meteotracker_qc.gps_qc import detect_gps_issues
from meteotracker_qc.pipeline import MeteotrackerQC, _campaign_output_dir


def test_row_preservation_under_time_and_gps_processing():
    df = pd.DataFrame(
        {
            "Time": pd.to_datetime([
                "2026-01-01 09:00:02",
                "2026-01-01 09:00:00",
                "2026-01-01 09:00:01",
                "2026-01-01 09:00:03",
            ]),
            "Lat": [44.49, 44.49, 44.49, 44.50],
            "Lon": [11.34, 11.34, 11.34, 11.34],
        }
    )
    time_out = detect_time_issues(df)
    gps_out = detect_gps_issues(time_out)

    assert len(gps_out) == len(df)
    assert gps_out["source_row"].tolist() == [0, 1, 2, 3]
    assert gps_out["time_raw"].tolist() == df["Time"].tolist()


def test_time_coordinate_alignment_regression_fixture():
    df = pd.DataFrame(
        {
            "Time": pd.to_datetime([
                "2026-01-01 09:00:05",
                "2026-01-01 09:00:01",
                "2026-01-01 09:00:02",
                "2026-01-01 09:00:00",
            ]),
            "Lat": [44.50, 44.49, 44.49, 44.49],
            "Lon": [11.34, 11.34, 11.34, 11.34],
        }
    )
    out = detect_gps_issues(detect_time_issues(df))

    aligned_time = out["time_utc"].dt.tz_localize(None)
    assert aligned_time.iloc[0] == pd.Timestamp("2026-01-01 09:00:05")
    assert aligned_time.iloc[1] == pd.Timestamp("2026-01-01 09:00:01")
    assert aligned_time.iloc[2] == pd.Timestamp("2026-01-01 09:00:02")
    assert aligned_time.iloc[3] == pd.Timestamp("2026-01-01 09:00:00")
    assert out["source_row"].tolist() == [0, 1, 2, 3]


def test_row_preservation_is_kept_across_processing_pipeline():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01", "2026-01-01 09:00:02"]),
        "Lat": [44.49, 44.49, 44.49],
        "Lon": [11.34, 11.34, 11.34],
        "Temp[°C]": [20.0, 20.5, 21.0],
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert len(out) == len(df)
    assert out["source_row"].tolist() == [0, 1, 2]


def test_time_coordinate_temperature_association_is_preserved():
    df = pd.DataFrame({
        "Time": pd.to_datetime(["2026-01-01 09:00:00", "2026-01-01 09:00:01", "2026-01-01 09:00:02"]),
        "Lat": [44.49, 44.49, 44.49],
        "Lon": [11.34, 11.34, 11.34],
        "Temp[°C]": [20.0, 21.0, 22.0],
    })
    out = detect_gps_issues(detect_time_issues(df))
    assert out["time_raw"].iloc[1] == df["Time"].iloc[1]
    assert out["Lat"].iloc[1] == df["Lat"].iloc[1]
    assert out["Temp[°C]"].iloc[1] == df["Temp[°C]"].iloc[1]


def test_campaign_output_dir_is_unique_for_same_stem_in_different_folders(tmp_path):
    input_root = tmp_path / "runs"
    input_root.mkdir()
    first = input_root / "a" / "same_name.csv"
    second = input_root / "b" / "same_name.csv"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("Time,Lat,Lon\n2026-01-01 09:00:00,44.49,11.34\n", encoding="utf-8")
    second.write_text("Time,Lat,Lon\n2026-01-01 09:00:00,44.49,11.34\n", encoding="utf-8")

    out_root = tmp_path / "out"
    first_dir = _campaign_output_dir(first, input_root, out_root)
    second_dir = _campaign_output_dir(second, input_root, out_root)

    assert first_dir != second_dir
    assert first_dir.name != second_dir.name


def test_ambiguous_timezone_campaign_is_not_satellite_eligible(tmp_path, monkeypatch):
    (tmp_path / "flag_policy.csv").write_bytes(resource("flag_policy.csv").read_bytes())
    config_path = tmp_path / "qc.yaml"
    config_path.write_text("filtering:\n  relaxed_keep_threshold: 1\n  strict_keep_threshold: 0\n", encoding="utf-8")
    csv_path = tmp_path / "campagna.csv"
    csv_path.write_text(
        "Time,Lat,Lon,Temp[°C],Hum[%],Press[mbar],Speed[km/h]\n"
        "2026-01-01 09:00:00,44.49,11.34,20.0,50.0,1010.0,0.0\n"
        "2026-01-01 09:00:01,44.49,11.34,20.1,50.0,1010.0,0.0\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("meteotracker_qc.pipeline.classify_timezone", lambda file_name, time_series: ("ambiguous", 0.4))
    qc = MeteotrackerQC(config_path)
    out = qc.process_file(csv_path, tmp_path / "out")

    assert out["timezone_classification"].iloc[0] == "ambiguous"
    assert not out["use_for_satellite_comparison"].any()
