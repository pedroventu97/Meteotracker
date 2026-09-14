import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.rules import evaluate_scope


def _policy(rows):
    cols = ["rule_id", "scope", "metric", "operator", "threshold", "resulting_status", "reason_code", "priority", "enabled", "evidence_source"]
    return pd.DataFrame(rows, columns=cols)


def test_first_match_wins_not_worst_status():
    policy = _policy([
        {"rule_id": "R1", "scope": "s", "metric": "x", "operator": ">", "threshold": 10, "resulting_status": "BAD", "reason_code": "HIGH", "priority": 0, "enabled": True, "evidence_source": "engineering_default"},
        {"rule_id": "R2", "scope": "s", "metric": "x", "operator": "always", "threshold": None, "resulting_status": "OK", "reason_code": None, "priority": 99, "enabled": True, "evidence_source": "engineering_default"},
    ])
    df = pd.DataFrame({"x": [5, 20]})
    out = evaluate_scope(df, policy, "s")
    assert out["status"].tolist() == ["OK", "BAD"]


def test_missing_catchall_raises():
    policy = _policy([
        {"rule_id": "R1", "scope": "s", "metric": "x", "operator": ">", "threshold": 10, "resulting_status": "BAD", "reason_code": "HIGH", "priority": 0, "enabled": True, "evidence_source": "engineering_default"},
    ])
    df = pd.DataFrame({"x": [5]})
    with pytest.raises(ValueError, match="catch-all"):
        evaluate_scope(df, policy, "s")


def test_unknown_scope_raises_empty_rules():
    policy = _policy([
        {"rule_id": "R1", "scope": "other", "metric": "x", "operator": "always", "threshold": None, "resulting_status": "OK", "reason_code": None, "priority": 99, "enabled": True, "evidence_source": "engineering_default"},
    ])
    df = pd.DataFrame({"x": [5]})
    with pytest.raises(ValueError, match="no enabled rules"):
        evaluate_scope(df, policy, "missing_scope")


@pytest.mark.parametrize("operator,threshold,value,expected", [
    (">", 5, 6, "MATCH"), (">=", 5, 5, "MATCH"), ("<", 5, 4, "MATCH"), ("<=", 5, 5, "MATCH"),
    ("==", 5, 5, "MATCH"), ("!=", 5, 6, "MATCH"),
])
def test_numeric_operators(operator, threshold, value, expected):
    policy = _policy([
        {"rule_id": "R1", "scope": "s", "metric": "x", "operator": operator, "threshold": threshold, "resulting_status": expected, "reason_code": None, "priority": 0, "enabled": True, "evidence_source": "engineering_default"},
        {"rule_id": "R2", "scope": "s", "metric": "x", "operator": "always", "threshold": None, "resulting_status": "FALLBACK", "reason_code": None, "priority": 99, "enabled": True, "evidence_source": "engineering_default"},
    ])
    df = pd.DataFrame({"x": [value]})
    out = evaluate_scope(df, policy, "s")
    assert out["status"].iloc[0] == expected


def test_is_null_and_not_null_operators():
    policy = _policy([
        {"rule_id": "R1", "scope": "s", "metric": "x", "operator": "is_null", "threshold": None, "resulting_status": "NULL", "reason_code": None, "priority": 0, "enabled": True, "evidence_source": "engineering_default"},
        {"rule_id": "R2", "scope": "s", "metric": "x", "operator": "always", "threshold": None, "resulting_status": "PRESENT", "reason_code": None, "priority": 99, "enabled": True, "evidence_source": "engineering_default"},
    ])
    df = pd.DataFrame({"x": [None, 1.0]})
    out = evaluate_scope(df, policy, "s")
    assert out["status"].tolist() == ["NULL", "PRESENT"]


def test_in_and_not_in_operators():
    policy = _policy([
        {"rule_id": "R1", "scope": "s", "metric": "x", "operator": "in", "threshold": "a|b", "resulting_status": "MEMBER", "reason_code": None, "priority": 0, "enabled": True, "evidence_source": "engineering_default"},
        {"rule_id": "R2", "scope": "s", "metric": "x", "operator": "always", "threshold": None, "resulting_status": "OTHER", "reason_code": None, "priority": 99, "enabled": True, "evidence_source": "engineering_default"},
    ])
    df = pd.DataFrame({"x": ["a", "c"]})
    out = evaluate_scope(df, policy, "s")
    assert out["status"].tolist() == ["MEMBER", "OTHER"]


def test_disabled_rule_is_skipped():
    policy = _policy([
        {"rule_id": "R1", "scope": "s", "metric": "x", "operator": ">", "threshold": 0, "resulting_status": "BAD", "reason_code": None, "priority": 0, "enabled": False, "evidence_source": "engineering_default"},
        {"rule_id": "R2", "scope": "s", "metric": "x", "operator": "always", "threshold": None, "resulting_status": "OK", "reason_code": None, "priority": 99, "enabled": True, "evidence_source": "engineering_default"},
    ])
    df = pd.DataFrame({"x": [10]})
    out = evaluate_scope(df, policy, "s")
    assert out["status"].iloc[0] == "OK"


def test_row_order_in_dataframe_does_not_affect_priority_resolution():
    policy = _policy([
        {"rule_id": "R2", "scope": "s", "metric": "x", "operator": "always", "threshold": None, "resulting_status": "OK", "reason_code": None, "priority": 99, "enabled": True, "evidence_source": "engineering_default"},
        {"rule_id": "R1", "scope": "s", "metric": "x", "operator": ">", "threshold": 0, "resulting_status": "BAD", "reason_code": None, "priority": 0, "enabled": True, "evidence_source": "engineering_default"},
    ])
    df = pd.DataFrame({"x": [10]})
    out = evaluate_scope(df, policy, "s")
    assert out["status"].iloc[0] == "BAD"


def test_real_temporal_drift_policy_csv_assessability_scope_has_catchall():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    policy = pd.read_csv(root / "config" / "temporal_drift_policy.csv")
    assert "always" in policy.loc[policy["scope"] == "temporal_internal_assessability", "operator"].to_list()
