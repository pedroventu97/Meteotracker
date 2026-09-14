import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

ALLOWED_EVIDENCE_SOURCES = {
    "thesis_documented", "device_documentation", "audit_observed",
    "data_distribution", "engineering_default", "sensitivity_selected",
}
ALLOWED_ACTIONS = {
    "INFO_ONLY", "WARNING_ONLY", "EXCLUDE_RECOMMENDED", "EXCLUDE_RESTRICTIVE",
    "EXCLUDE_ALL_SCIENTIFIC", "SEGMENT_BREAK", "NOT_APPLICABLE",
}
YAML_CONFIGS = ["qc_permissive.yaml", "qc_recommended.yaml", "qc_restrictive.yaml"]
THR_ID_PATTERN = re.compile(r"#\s*(THR-[A-Z0-9-]+)")


ALLOWED_REASON_FAMILIES = {
    "TEMPORAL", "GPS", "STABILIZATION", "THERMAL", "VENTILATION", "SPATIAL", "SCHEMA",
}


def test_flag_policy_csv_parses_with_expected_columns():
    df = pd.read_csv(CONFIG_DIR / "flag_policy.csv")
    assert list(df.columns) == ["flag_name", "action", "rationale", "false_positive_risk_note", "reason_family"]
    assert len(df) > 0
    assert df["flag_name"].notna().all()
    assert df["flag_name"].is_unique
    unknown_families = set(df["reason_family"].dropna().unique()) - ALLOWED_REASON_FAMILIES
    assert not unknown_families, f"unexpected reason_family values: {unknown_families}"


def test_threshold_provenance_csv_parses_with_expected_columns():
    df = pd.read_csv(CONFIG_DIR / "threshold_provenance.csv")
    expected = [
        "threshold_id", "parameter_name", "value", "unit", "profile",
        "applicable_scope", "evidence_source", "source_reference", "rationale",
        "sensitivity_values",
    ]
    assert list(df.columns) == expected
    assert len(df) > 0


def test_every_flag_policy_action_is_in_allowed_vocabulary():
    df = pd.read_csv(CONFIG_DIR / "flag_policy.csv")
    unknown = set(df["action"].unique()) - ALLOWED_ACTIONS
    assert not unknown, f"unexpected action values: {unknown}"


def test_every_provenance_evidence_source_is_in_allowed_vocabulary():
    df = pd.read_csv(CONFIG_DIR / "threshold_provenance.csv")
    unknown = set(df["evidence_source"].unique()) - ALLOWED_EVIDENCE_SOURCES
    assert not unknown, f"unexpected evidence_source values: {unknown}"


@pytest.mark.parametrize("yaml_name", YAML_CONFIGS)
def test_every_documented_threshold_key_has_a_provenance_row(yaml_name):
    provenance = pd.read_csv(CONFIG_DIR / "threshold_provenance.csv")
    known_ids = set(provenance["threshold_id"].unique())
    text = (CONFIG_DIR / yaml_name).read_text(encoding="utf-8")
    referenced_ids = set(THR_ID_PATTERN.findall(text))
    assert referenced_ids, f"{yaml_name} has no THR-* comments at all -- expected several"
    missing = referenced_ids - known_ids
    assert not missing, f"{yaml_name} references threshold ids with no provenance row: {missing}"
