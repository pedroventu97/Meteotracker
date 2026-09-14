import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.outputs import (
    _json_safe, write_campaign_json, write_detrended_experimental_csv,
)


def test_json_safe_handles_numpy_and_nan():
    assert _json_safe(np.int64(5)) == 5
    assert _json_safe(np.float64(1.5)) == 1.5
    assert _json_safe(np.float64(float("nan"))) is None
    assert _json_safe(np.bool_(True)) is True
    assert _json_safe(pd.Timestamp("2026-01-01", tz="UTC")) == pd.Timestamp("2026-01-01", tz="UTC").isoformat()
    assert _json_safe(pd.NaT) is None
    assert _json_safe("hello") == "hello"


def test_write_campaign_json_produces_valid_json_with_expected_top_level_keys(tmp_path):
    session_row = {"canonical_campaign_id": "c1", "temporal_change_diagnosis": "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE", "some_nan": float("nan")}
    groups = pd.DataFrame([{"repeated_location_group_id": 1, "group_n_visits": 2}])
    visits = pd.DataFrame([{"repeated_location_visit_id": "1_1"}])
    pairs = pd.DataFrame([{"repeated_location_pair_id": "p1"}])
    model_comparison = pd.DataFrame([{"method": "pairwise_median", "trend_c_per_min": 0.05}])
    sensitivity = pd.DataFrame([{"config_name": "anchor"}])

    out_path = write_campaign_json("c1", session_row, groups, visits, pairs, model_comparison, sensitivity, tmp_path, "v1")
    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert set(payload.keys()) == {"canonical_campaign_id", "config_version", "session", "groups", "visits", "pairs", "model_comparison", "sensitivity"}
    assert payload["session"]["some_nan"] is None
    assert payload["config_version"] == "v1"
    assert len(payload["groups"]) == 1


def test_write_detrended_experimental_csv(tmp_path):
    df = pd.DataFrame({"temp_original_c": [10.0, 10.5], "temp_detrended_experimental_c": [10.0, 10.4]})
    out_path = write_detrended_experimental_csv("c1", df, tmp_path)
    assert out_path.exists()
    reloaded = pd.read_csv(out_path)
    assert list(reloaded.columns) == ["temp_original_c", "temp_detrended_experimental_c"]
    assert len(reloaded) == 2
