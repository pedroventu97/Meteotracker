from pathlib import Path

import pandas as pd

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

ALLOWED_EVIDENCE_SOURCES = {
    "thesis_documented", "device_documentation", "audit_observed",
    "data_distribution", "engineering_default", "sensitivity_selected",
}
ALLOWED_DIMENSION_STATUS = {"OK", "WARNING", "POOR", "NOT_ASSESSABLE"}
ALLOWED_ROLLUP_STATUS = {"PASS", "PASS_WITH_WARNINGS", "PARTIAL", "REJECT", "NOT_ASSESSABLE"}
ALLOWED_SUITABILITY_STATUS = {
    "YES", "YES_WITH_LIMITATIONS", "PARTIAL", "NO", "NOT_ASSESSABLE",
    "NOT_ASSESSABLE_EXTERNAL_DATA_REQUIRED",
}
ALLOWED_OPERATORS = {">", ">=", "<", "<=", "==", "!=", "is_null", "not_null", "in", "not_in", "always"}
PROFILES = {"permissive_session", "recommended_session", "conservative_session"}


def _policy():
    return pd.read_csv(CONFIG_DIR / "session_qc_policy.csv")


def _suitability():
    return pd.read_csv(CONFIG_DIR / "session_suitability_policy.csv")


def test_session_qc_policy_parses_with_expected_columns():
    df = _policy()
    expected = [
        "rule_id", "level", "dimension", "profile", "metric", "operator", "threshold", "unit",
        "resulting_status", "reason_code", "priority", "evidence_source", "rationale",
        "sensitivity_values", "enabled",
    ]
    assert list(df.columns) == expected
    assert len(df) > 0
    assert df["rule_id"].is_unique


def test_session_suitability_policy_parses_with_expected_columns():
    df = _suitability()
    expected = [
        "rule_id", "analysis_type", "metric", "operator", "threshold", "unit",
        "resulting_status", "reason_code", "priority", "evidence_source", "rationale",
    ]
    assert list(df.columns) == expected
    assert len(df) > 0
    assert df["rule_id"].is_unique


def test_session_qc_policy_operators_and_evidence_sources_are_valid():
    df = _policy()
    assert set(df["operator"].unique()) <= ALLOWED_OPERATORS
    assert set(df["evidence_source"].unique()) <= ALLOWED_EVIDENCE_SOURCES
    assert set(df["profile"].unique()) == PROFILES
    assert set(df["level"].unique()) == {"segment", "session"}


def test_session_qc_policy_resulting_status_matches_vocabulary_per_dimension_kind():
    df = _policy()
    rollup = df[df["dimension"] == "rollup"]
    dims = df[df["dimension"] != "rollup"]
    assert set(rollup["resulting_status"].unique()) <= ALLOWED_ROLLUP_STATUS
    assert set(dims["resulting_status"].unique()) <= ALLOWED_DIMENSION_STATUS


def test_session_suitability_resulting_status_is_valid():
    df = _suitability()
    assert set(df["resulting_status"].unique()) <= ALLOWED_SUITABILITY_STATUS


def test_satellite_coincidence_is_always_not_assessable_external_data_required():
    df = _suitability()
    sat = df[df["analysis_type"] == "satellite_coincidence"]
    assert len(sat) >= 1
    assert set(sat["resulting_status"].unique()) == {"NOT_ASSESSABLE_EXTERNAL_DATA_REQUIRED"}


def test_every_level_dimension_profile_combination_has_a_catch_all_rule():
    df = _policy()
    enabled = df[df["enabled"].astype(bool)]
    combos = enabled[["level", "dimension", "profile"]].drop_duplicates()
    missing = []
    for _, row in combos.iterrows():
        sub = enabled[
            (enabled.level == row.level) & (enabled.dimension == row.dimension) & (enabled.profile == row.profile)
        ]
        if "always" not in sub["operator"].tolist():
            missing.append((row.level, row.dimension, row.profile))
    assert not missing, f"missing catch-all rules: {missing}"


def test_not_assessable_rules_have_lowest_priority_number_in_their_group():
    df = _policy()
    enabled = df[df["enabled"].astype(bool)]
    combos = enabled[["level", "dimension", "profile"]].drop_duplicates()
    for _, row in combos.iterrows():
        sub = enabled[
            (enabled.level == row.level) & (enabled.dimension == row.dimension) & (enabled.profile == row.profile)
        ]
        na_rows = sub[sub["resulting_status"] == "NOT_ASSESSABLE"]
        if na_rows.empty:
            continue
        min_na_priority = na_rows["priority"].min()
        other_priorities = sub.loc[sub["resulting_status"] != "NOT_ASSESSABLE", "priority"]
        if not other_priorities.empty:
            assert min_na_priority <= other_priorities.min(), (
                f"NOT_ASSESSABLE does not have the lowest priority for {row.level}/{row.dimension}/{row.profile}"
            )


def test_ventilation_risk_dimension_never_resolves_to_poor():
    df = _policy()
    vent = df[(df["dimension"].isin(["ventilation_risk"])) & (df["enabled"].astype(bool))]
    assert "POOR" not in vent["resulting_status"].unique(), "ventilation_risk must never be POOR (risk signal, not a confirmed thermal error)"


def test_gap_fraction_poor_threshold_is_cleared_by_bologna_ravenna_in_all_profiles():
    # Bologna-Ravenna's measured gap_fraction_of_nominal_span = 0.841418
    # (outputs/session_qc real run) -- must exceed the POOR threshold under
    # every one of the 3 aggregation profiles, per the session_qc_report's
    # explicit design goal (section O).
    df = _policy()
    gap_poor_rows = df[
        (df["dimension"].isin(["sampling_integrity", "spatial_continuity"]))
        & (df["metric"] == "gap_fraction_of_nominal_span")
        & (df["resulting_status"] == "POOR")
        & (df["level"] == "session")
    ]
    assert len(gap_poor_rows) >= 3
    assert (gap_poor_rows["threshold"].astype(float) < 0.841418).all()
