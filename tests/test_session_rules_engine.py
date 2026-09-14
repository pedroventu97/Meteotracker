import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.session_qc.rules_engine import (
    aggregate_session_reasons,
    evaluate_dimension,
    evaluate_dimensions,
)


def _policy_row(**kwargs):
    base = dict(
        rule_id="R", level="session", dimension="dim", profile="recommended_session",
        metric="m", operator=">", threshold=0.0, unit="fraction", resulting_status="OK",
        reason_code="", priority=99, evidence_source="engineering_default", rationale="",
        sensitivity_values="", enabled=True,
    )
    base.update(kwargs)
    return base


def test_first_match_wins_not_worst_status():
    policy = pd.DataFrame([
        _policy_row(rule_id="A", metric="x", operator=">", threshold=0.5, resulting_status="WARNING", priority=10, reason_code="WARN"),
        _policy_row(rule_id="B", metric="x", operator=">", threshold=0.9, resulting_status="POOR", priority=20, reason_code="POOR_CODE"),
        _policy_row(rule_id="C", operator="always", resulting_status="OK", priority=99),
    ])
    df = pd.DataFrame({"x": [0.95]})
    out = evaluate_dimension(df, policy, level="session", dimension="dim", profile="recommended_session")
    # A (priority 10) fires first even though B (priority 20) would also be
    # satisfied and represents a "worse" status -- first-match-wins by design.
    assert out["status"].iloc[0] == "WARNING"
    assert out["matched_rule_id"].iloc[0] == "A"


def test_not_assessable_precondition_takes_precedence():
    policy = pd.DataFrame([
        _policy_row(rule_id="NA", metric="n_raw", operator="<", threshold=5, resulting_status="NOT_ASSESSABLE", priority=0, reason_code="TOO_SHORT"),
        _policy_row(rule_id="POOR", metric="freeze", operator=">", threshold=0.1, resulting_status="POOR", priority=10, reason_code="HIGH_GPS_FREEZE"),
        _policy_row(rule_id="OK", operator="always", resulting_status="OK", priority=99),
    ])
    df = pd.DataFrame({"n_raw": [2], "freeze": [0.9]})  # would also satisfy POOR
    out = evaluate_dimension(df, policy, level="session", dimension="dim", profile="recommended_session")
    assert out["status"].iloc[0] == "NOT_ASSESSABLE"
    assert out["reason_code"].iloc[0] == "TOO_SHORT"


def test_missing_catch_all_raises():
    policy = pd.DataFrame([
        _policy_row(rule_id="A", metric="x", operator=">", threshold=0.5, resulting_status="WARNING", priority=10),
    ])
    df = pd.DataFrame({"x": [0.1]})
    with pytest.raises(ValueError, match="catch-all"):
        evaluate_dimension(df, policy, level="session", dimension="dim", profile="recommended_session")


def test_catch_all_resolves_rows_that_match_nothing_else():
    policy = pd.DataFrame([
        _policy_row(rule_id="A", metric="x", operator=">", threshold=0.5, resulting_status="WARNING", priority=10, reason_code="W"),
        _policy_row(rule_id="OK", operator="always", resulting_status="OK", priority=99),
    ])
    df = pd.DataFrame({"x": [0.1, 0.9]})
    out = evaluate_dimension(df, policy, level="session", dimension="dim", profile="recommended_session")
    assert out["status"].tolist() == ["OK", "WARNING"]


@pytest.mark.parametrize("operator,threshold,value,expected", [
    (">", 5, 6, True), (">", 5, 5, False),
    (">=", 5, 5, True), ("<", 5, 4, True), ("<=", 5, 5, True),
    ("==", 5, 5, True), ("!=", 5, 6, True),
    ("is_null", None, np.nan, True), ("not_null", None, 1.0, True),
])
def test_all_numeric_operators(operator, threshold, value, expected):
    policy = pd.DataFrame([
        _policy_row(rule_id="A", metric="x", operator=operator, threshold=threshold, resulting_status="POOR", priority=10, reason_code="X"),
        _policy_row(rule_id="OK", operator="always", resulting_status="OK", priority=99),
    ])
    df = pd.DataFrame({"x": [value]})
    out = evaluate_dimension(df, policy, level="session", dimension="dim", profile="recommended_session")
    assert (out["status"].iloc[0] == "POOR") == expected


def test_in_and_not_in_categorical_operators():
    policy = pd.DataFrame([
        _policy_row(rule_id="A", metric="reason", operator="in", threshold="segment_too_short|STABILIZATION_NOT_REACHED", resulting_status="NOT_ASSESSABLE", priority=0, reason_code="NA"),
        _policy_row(rule_id="OK", operator="always", resulting_status="OK", priority=99),
    ])
    df = pd.DataFrame({"reason": ["segment_too_short", "slope_confirmed_stable"]})
    out = evaluate_dimension(df, policy, level="session", dimension="dim", profile="recommended_session")
    assert out["status"].tolist() == ["NOT_ASSESSABLE", "OK"]


def test_row_order_independence():
    policy = pd.DataFrame([
        _policy_row(rule_id="B", metric="x", operator=">", threshold=0.9, resulting_status="POOR", priority=20, reason_code="P"),
        _policy_row(rule_id="A", metric="x", operator=">", threshold=0.5, resulting_status="WARNING", priority=10, reason_code="W"),
        _policy_row(rule_id="OK", operator="always", resulting_status="OK", priority=99),
    ])  # rows deliberately out of priority order in the table itself
    df = pd.DataFrame({"x": [0.95]})
    out = evaluate_dimension(df, policy, level="session", dimension="dim", profile="recommended_session")
    assert out["status"].iloc[0] == "WARNING"  # priority 10 still wins regardless of table row order


def test_evaluate_dimensions_merges_prefixed_columns():
    policy = pd.DataFrame([
        _policy_row(rule_id="A", dimension="gps_quality", metric="freeze", operator=">", threshold=0.2, resulting_status="POOR", priority=10, reason_code="HIGH_GPS_FREEZE"),
        _policy_row(rule_id="OKg", dimension="gps_quality", operator="always", resulting_status="OK", priority=99),
        _policy_row(rule_id="B", dimension="thermal_signal", metric="thermal", operator=">", threshold=0.1, resulting_status="WARNING", priority=10, reason_code="TEMP_RATE_ANOMALIES"),
        _policy_row(rule_id="OKt", dimension="thermal_signal", operator="always", resulting_status="OK", priority=99),
    ])
    df = pd.DataFrame({"freeze": [0.5], "thermal": [0.05]})
    out = evaluate_dimensions(df, policy, level="session", dimensions=["gps_quality", "thermal_signal"], profile="recommended_session")
    assert out["gps_quality_status"].iloc[0] == "POOR"
    assert out["thermal_signal_status"].iloc[0] == "OK"


def test_aggregate_session_reasons_primary_matches_rollup():
    idx = pd.RangeIndex(2)
    rollup_reason = pd.Series(["LONG_GAP", "HIGH_GPS_FREEZE"], index=idx)
    dimension_reasons = {
        "gps_quality": pd.Series(["HIGH_GPS_FREEZE", "HIGH_GPS_FREEZE"], index=idx),
        "sampling_integrity": pd.Series(["LONG_GAP", np.nan], index=idx),
    }
    out = aggregate_session_reasons(dimension_reasons, rollup_reason)
    assert out["session_primary_reason"].tolist() == ["LONG_GAP", "HIGH_GPS_FREEZE"]
    # row 0: primary=LONG_GAP, secondary should include HIGH_GPS_FREEZE (from gps_quality) but not itself
    assert "HIGH_GPS_FREEZE" in out["session_secondary_reasons"].iloc[0]
    assert "LONG_GAP" not in out["session_secondary_reasons"].iloc[0].split(";")
    assert out["session_reason_count"].iloc[0] == 2
    assert "GPS" in out["session_reason_families"].iloc[0]
    assert "TEMPORAL" in out["session_reason_families"].iloc[0]
