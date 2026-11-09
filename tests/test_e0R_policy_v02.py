"""E0-QC-R R6: flag-table severities derived per profile from the v0.2 policy -> agree with keep_<profile> by
construction; v0.2 files consistent; policy selectable by config without touching v0.1 files."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from meteotracker_qc.flag_table import build_flag_table, load_flag_schema, resolve_severities, severity_from_policy
from meteotracker_qc.policy import PROFILE_ORDER, apply_flag_policy

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "flag_policy_E0R_v0.2.csv"
SCHEMA = ROOT / "e0" / "qc_flag_schema_E0_v0.2.yaml"


def test_severity_from_policy_rule():
    pol = pd.DataFrame({"flag_name": ["a", "b", "c", "d", "e", "f"],
                        "action": ["EXCLUDE_ALL_SCIENTIFIC", "EXCLUDE_RECOMMENDED", "EXCLUDE_RESTRICTIVE",
                                   "WARNING_ONLY", "INFO_ONLY", "NOT_APPLICABLE"]})
    assert severity_from_policy(pol, "permissive") == {"a": "exclude", "b": "warn", "c": "warn", "d": "warn", "e": "info"}
    assert severity_from_policy(pol, "recommended")["b"] == "exclude"
    assert severity_from_policy(pol, "recommended")["c"] == "warn"
    assert severity_from_policy(pol, "restrictive")["c"] == "exclude"
    assert "f" not in severity_from_policy(pol, "restrictive")


@pytest.mark.parametrize("profile", PROFILE_ORDER)
def test_flag_table_agrees_with_keep_by_construction(profile):
    pol = pd.read_csv(POLICY)
    schema = load_flag_schema(SCHEMA)
    rng = np.random.default_rng(1)
    n = 500
    df = pd.DataFrame({c: rng.random(n) < 0.05 for c in pol.flag_name})
    df["source_row"] = np.arange(n)
    keep = apply_flag_policy(df, pol, profile)[f"keep_{profile}"]
    ft = build_flag_table(df, canonical_campaign_id="c", source_file="f.csv", qc_profile=profile, schema=schema,
                          policy_df=pol)
    ex_rows = set(ft.loc[ft.severity == "exclude", "source_row"])
    ft_keep = ~df["source_row"].isin(ex_rows)
    assert (ft_keep.to_numpy() == keep.to_numpy()).all()
    assert set(ft.qc_profile) == {profile}
    legacy = set(schema["legacy_aliases"])
    assert not (set(ft.flag_code) & legacy)


def test_v02_schema_and_policy_are_consistent():
    pol = pd.read_csv(POLICY)
    schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    assert schema["severity_source"] == "policy"
    for p in PROFILE_ORDER:
        resolve_severities(schema, p, pol)  # raises on drift
    acts = dict(zip(pol.flag_name, pol.action))
    for alias in schema["legacy_aliases"]:
        assert acts.get(alias) == "NOT_APPLICABLE", alias
    assert pol.flag_name.is_unique


def test_schema_code_missing_from_policy_raises():
    schema = {"severity_source": "policy", "flag_codes": [{"code": "qc_not_in_policy"}]}
    with pytest.raises(ValueError):
        resolve_severities(schema, "recommended", pd.DataFrame({"flag_name": ["qc_x"], "action": ["INFO_ONLY"]}))


def test_v01_files_untouched_and_v02_selected_by_config():
    s01 = yaml.safe_load((ROOT / "e0" / "qc_flag_schema_E0_v0.1.yaml").read_text(encoding="utf-8"))
    assert "severity_source" not in s01
    for p in PROFILE_ORDER:
        y1 = yaml.safe_load((ROOT / "config" / f"qc_{p}.yaml").read_text(encoding="utf-8"))
        y2 = yaml.safe_load((ROOT / "config" / f"qc_E0R_{p}_v0.2.yaml").read_text(encoding="utf-8"))
        assert "policy_file" not in y1
        assert y2["policy_file"] == "flag_policy_E0R_v0.2.csv"
        # thresholds identical: only policy/schema keys and the explicit R1 switch differ
        y2c = {k: v for k, v in y2.items() if k not in ("policy_file", "flag_schema")}
        y2c["time"] = {k: v for k, v in y2c["time"].items() if k != "legacy_nonpositive_dt_segment_break"}
        assert y2c == y1


def test_pipeline_uses_policy_file_from_config():
    from meteotracker_qc.pipeline import MeteotrackerQC
    qc = MeteotrackerQC(ROOT / "config" / "qc_E0R_recommended_v0.2.yaml")
    assert qc.policy_path.name == "flag_policy_E0R_v0.2.csv"
    assert "qc_duplicate_record" in set(qc.flag_policy.flag_name)
    assert qc.flag_schema_path.name == "qc_flag_schema_E0_v0.2.yaml"
    old = MeteotrackerQC(ROOT / "config" / "qc_recommended.yaml")
    assert old.policy_path.name == "flag_policy.csv" and old.flag_schema_path is None
