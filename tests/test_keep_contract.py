from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.config_resources import read_policy
from meteotracker_qc.pipeline import MeteotrackerQC
from meteotracker_qc.policy import apply_flag_policy
from meteotracker_qc.session_qc.metrics import build_reference_frame
from scientific_fixtures import empty_workspace, write_route


@pytest.mark.parametrize("flag, expected", [
    ("qc_temp_impossible", [False, False, False]),
    ("qc_spatial_jump", [True, False, False]),
    ("qc_duplicate_timestamp", [True, True, False]),
    ("qc_coord_missing", [True, True, True]),
])
def test_declared_policy_exclusions_have_distinct_profile_meanings(flag, expected):
    policy = read_policy("flag_policy.csv")
    result = apply_flag_policy(pd.DataFrame({flag: [True]}), policy, "recommended")
    assert [bool(result[f"keep_{p}"].iloc[0]) for p in ("permissive", "recommended", "restrictive")] == expected


def test_information_subflags_do_not_count_the_same_jump_again():
    flags = pd.DataFrame({"qc_gps_jump": [True], "qc_isolated_position_outlier": [True], "qc_spatial_jump": [True]})
    result = apply_flag_policy(flags, read_policy("flag_policy.csv"), "recommended")
    assert result["qc_severity"].iloc[0] == 1
    assert result["qc_exclusion_reasons"].iloc[0] == "qc_spatial_jump"


def test_real_profile_trees_are_authoritative_not_policy_projections(tmp_path):
    root = empty_workspace(tmp_path / "profiles")
    raw = root / "data/raw/route.csv"
    write_route(raw, n=151)
    frame = pd.read_csv(raw)
    # A small isolated detour is above the existing restrictive excess threshold
    # and below the existing recommended threshold. Configurations are untouched.
    frame.loc[100, "Lon"] += 0.000252
    from pyproj import Geod
    frame["Time"] = pd.date_range("2026-01-01T10:00:00Z", periods=len(frame), freq="2s").astype(str)
    _, _, distances = Geod(ellps="WGS84").inv(frame.Lon.to_numpy()[:-1], frame.Lat.to_numpy()[:-1],
                                               frame.Lon.to_numpy()[1:], frame.Lat.to_numpy()[1:])
    frame["Speed[km/h]"] = [9.0, *(distances * 3.6 / 2)]
    frame.to_csv(raw, index=False)
    frames = {}
    for profile in ("permissive", "recommended", "restrictive"):
        qc = MeteotrackerQC(root / f"config/qc_{profile}.yaml")
        frames[profile] = qc.process_file(raw, root / "outputs" / profile / "route")
        output = frames[profile]
        assert len(output) == len(frame)
        assert output.source_row.tolist() == list(range(len(frame)))
        assert output.keep_strict.equals(output.qc_severity <= qc.config["filtering"]["strict_keep_threshold"])
        assert output.keep_relaxed.equals(output.qc_severity <= qc.config["filtering"]["relaxed_keep_threshold"])
        assert output.qc_severity.equals(output[f"qc_severity_{profile}"])
    assert not frames["recommended"].loc[100, "qc_spatial_jump"]
    assert frames["restrictive"].loc[100, "qc_spatial_jump"]
    assert frames["recommended"].loc[100, "keep_restrictive"]
    assert not frames["restrictive"].loc[100, "keep_restrictive"]
    reference = build_reference_frame(frames)
    assert not reference.loc[100, "keep_restrictive_true"]
    assert reference.keep_permissive_true.equals(frames["permissive"].keep_permissive)
    assert reference.keep_recommended_true.equals(frames["recommended"].keep_recommended)


def test_missing_policy_cannot_manufacture_all_kept_data(tmp_path):
    path = tmp_path / "qc.yaml"
    path.write_text("profile_name: recommended\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="flag_policy"):
        MeteotrackerQC(path)


@pytest.mark.parametrize("policy", [pd.DataFrame(), pd.DataFrame({"flag_name": ["qc_temp_impossible"], "action": ["TYPO"]})])
def test_invalid_policy_is_explicitly_rejected(policy):
    with pytest.raises(ValueError):
        apply_flag_policy(pd.DataFrame({"qc_temp_impossible": [True]}), policy, "recommended")


def _frames():
    return {p: pd.DataFrame({"source_row": [0, 1], "source_file": ["a.csv"] * 2,
                            f"keep_{p}": [True, False]}) for p in ("permissive", "recommended", "restrictive")}


def test_legacy_keep_alias_is_not_accepted_as_a_profile():
    frames = _frames()
    frames["permissive"] = frames["permissive"].rename(columns={"keep_permissive": "keep_relaxed"})
    with pytest.raises(ValueError, match="Incompatible permissive"):
        build_reference_frame(frames)


@pytest.mark.parametrize("corruption", ["order", "count", "file", "null", "string"])
def test_profile_identity_and_boolean_contract_are_checked(corruption):
    frames = _frames()
    frame = frames["permissive"]
    if corruption == "order":
        frame["source_row"] = [1, 0]
    elif corruption == "count":
        frames["permissive"] = frame.iloc[:1]
    elif corruption == "file":
        frame["source_file"] = "different.csv"
    elif corruption == "null":
        frame["keep_permissive"] = pd.Series([True, None], dtype="boolean")
    else:
        frame["keep_permissive"] = ["True", "False"]
    with pytest.raises(ValueError):
        build_reference_frame(frames)
