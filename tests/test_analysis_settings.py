"""Initial Gate 2.1 runtime contract; uses only synthetic data."""
import json

import pandas as pd
import pytest
import yaml

from meteotracker_qc.analysis_settings import DEFAULT_ACTIVE, describe_settings, preset_payload, validate_settings
from meteotracker_qc.pipeline import MeteotrackerQC
from scientific_fixtures import empty_workspace, write_route


@pytest.fixture
def root(tmp_path):
    return empty_workspace(tmp_path / "analisi città con spazi")


@pytest.mark.parametrize("profile", ["recommended", "permissive", "restrictive"])
def test_runtime_defaults_leave_official_yaml_unchanged(root, profile):
    path = root / "config" / f"qc_{profile}.yaml"
    before = path.read_bytes()
    settings = describe_settings(root / "config", profile)
    runtime = dict(settings["config"])
    runtime.pop("analysis_controls")
    assert runtime == yaml.safe_load(before)
    assert settings["differences"] == {}
    assert path.read_bytes() == before
    assert not next(g for g in settings["groups"] if g["id"] == "invalid_coordinates")["available"]


@pytest.mark.parametrize("overrides", [
    {"unknown.value": 1}, {"gps.gps_jump_distance_m": -1},
    {"gps.gps_jump_distance_m": True}, {"gps.gps_jump_distance_m": float("nan")},
    {"gps.gps_jump_distance_m": {"value": 30, "unit": "km"}},
    {"warmup.window_size": 1.5}, {"physical_limits.temp_min_c": 65},
    {"time.gap_short_multiplier": 100},
])
def test_runtime_rejects_invalid_parameters(root, overrides):
    with pytest.raises(ValueError):
        validate_settings(root / "config", overrides=overrides)


def test_runtime_diff_and_preset_metadata(root):
    active = [g for g in DEFAULT_ACTIVE if g != "warmup"]
    result = validate_settings(root / "config", active_controls=active,
                               overrides={"gps.gps_jump_distance_m": {"value": 90, "unit": "m"}})
    assert result["disabled_controls"] == ["warmup"]
    assert result["differences"]["gps.gps_jump_distance_m"] == {"from": 80, "value": 90, "unit": "m"}
    preset = preset_payload(result, "Prova", "Sintetico")
    assert preset["schema_version"] == 1 and preset["date"] and preset["config_fingerprint"]
    json.dumps(preset, allow_nan=False)
    with pytest.raises(ValueError):
        validate_settings(root / "config", active_controls=[])


def test_disabled_controls_reach_engine_before_policy(root):
    raw = root / "data/raw/batch città/corsa.csv"
    write_route(raw, n=21)
    source = pd.read_csv(raw)
    source.loc[10, "Temp[°C]"] = 90
    source.to_csv(raw, index=False)
    before = {p.name: p.read_bytes() for p in (root / "config").iterdir()}
    base = MeteotrackerQC(root / "config/qc_recommended.yaml")
    checked = base.process_file(raw, root / "temporary/default", diagnostics=False)
    settings = validate_settings(root / "config", active_controls=[g for g in DEFAULT_ACTIVE if g not in {"warmup", "temperature", "ventilation"}])
    # Runtime config is in memory; official YAML is never edited.
    base.config = settings["config"]
    custom = base.process_file(raw, root / "temporary/custom", diagnostics=False)
    assert checked["qc_temp_impossible"].any() and checked["qc_sensor_stabilization"].any()
    assert not custom["qc_temp_impossible"].any() and not custom["qc_sensor_stabilization"].any()
    assert custom["keep_recommended"].sum() > checked["keep_recommended"].sum()
    assert (custom["stabilization_window_end_reason"] == "DISABLED").all()
    assert (custom["ventilation_evidence_class"] == "DISABLED").all()
    assert custom["source_row"].is_unique and len(custom) == len(source)
    assert {p.name: p.read_bytes() for p in (root / "config").iterdir()} == before
