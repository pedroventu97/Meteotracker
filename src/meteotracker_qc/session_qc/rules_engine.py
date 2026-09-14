"""Generic rule-evaluation engine for config/session_qc_policy.csv, the
numeric-threshold analog of policy.py::apply_flag_policy(). See
reports/session_qc_report.md section B for the full design rationale
(first-match-wins by priority, NOT_ASSESSABLE preconditions as ordinary
lower-priority rows, mandatory catch-all per (level, dimension, profile)).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DIMENSION_FAMILY = {
    "sampling_integrity": "TEMPORAL",
    "gps_quality": "GPS",
    "thermal_quality": "THERMAL",
    "thermal_signal": "THERMAL",
    "ventilation_risk": "VENTILATION",
    "stabilization": "STABILIZATION",
    "stabilization_quality": "STABILIZATION",
    "spatial_continuity": "SPATIAL",
    "schema_completeness": "SCHEMA",
}

STATUS_VOCABULARY_DIMENSION = {"OK", "WARNING", "POOR", "NOT_ASSESSABLE"}
STATUS_VOCABULARY_ROLLUP = {"PASS", "PASS_WITH_WARNINGS", "PARTIAL", "REJECT", "NOT_ASSESSABLE"}


def _evaluate_condition(df: pd.DataFrame, metric: str, operator: str, threshold) -> pd.Series:
    if operator == "always":
        return pd.Series(True, index=df.index)
    if metric not in df.columns:
        return pd.Series(False, index=df.index)
    col = df[metric]
    if operator == "is_null":
        return col.isna()
    if operator == "not_null":
        return col.notna()
    if operator == "in":
        values = str(threshold).split("|")
        return col.astype(str).isin(values)
    if operator == "not_in":
        values = str(threshold).split("|")
        return ~col.astype(str).isin(values)
    if operator in ("==", "!="):
        try:
            t = float(threshold)
            numeric_col = pd.to_numeric(col, errors="coerce")
            return (numeric_col == t) if operator == "==" else (numeric_col != t)
        except (ValueError, TypeError):
            as_str = col.astype(str)
            return (as_str == str(threshold)) if operator == "==" else (as_str != str(threshold))
    if operator in (">", ">=", "<", "<="):
        t = float(threshold)
        numeric_col = pd.to_numeric(col, errors="coerce")
        if operator == ">":
            return numeric_col > t
        if operator == ">=":
            return numeric_col >= t
        if operator == "<":
            return numeric_col < t
        return numeric_col <= t
    raise ValueError(f"unknown operator: {operator}")


def evaluate_dimension(
    subjects_df: pd.DataFrame,
    policy_df: pd.DataFrame,
    *,
    level: str,
    dimension: str,
    profile: str,
) -> pd.DataFrame:
    """First-match-wins evaluation of every enabled rule for
    (level, dimension, profile), sorted by ascending priority. Returns a
    DataFrame indexed like subjects_df with columns: status, reason_code,
    matched_rule_id, evidence_source, metric_name, metric_value, threshold.
    """
    rules = policy_df[
        (policy_df["level"] == level)
        & (policy_df["dimension"] == dimension)
        & (policy_df["profile"] == profile)
        & (policy_df["enabled"].astype(bool))
    ].sort_values("priority", kind="stable")

    if rules.empty:
        raise ValueError(f"no enabled rules for level={level!r} dimension={dimension!r} profile={profile!r}")
    if "always" not in rules["operator"].to_list():
        raise ValueError(f"no catch-all ('always') rule for level={level!r} dimension={dimension!r} profile={profile!r}")

    idx = subjects_df.index
    out = pd.DataFrame(index=idx)
    out["status"] = pd.Series(pd.NA, index=idx, dtype="object")
    out["reason_code"] = pd.Series(pd.NA, index=idx, dtype="object")
    out["matched_rule_id"] = pd.Series(pd.NA, index=idx, dtype="object")
    out["evidence_source"] = pd.Series(pd.NA, index=idx, dtype="object")
    out["metric_name"] = pd.Series(pd.NA, index=idx, dtype="object")
    out["metric_value"] = pd.Series(np.nan, index=idx, dtype="object")
    out["threshold"] = pd.Series(np.nan, index=idx, dtype="object")

    unresolved = pd.Series(True, index=idx)
    for _, rule in rules.iterrows():
        if not unresolved.any():
            break
        cond = _evaluate_condition(subjects_df, rule["metric"], rule["operator"], rule["threshold"])
        fire = cond.reindex(idx, fill_value=False) & unresolved
        if not fire.any():
            continue
        out.loc[fire, "status"] = rule["resulting_status"]
        out.loc[fire, "reason_code"] = rule["reason_code"] if pd.notna(rule["reason_code"]) and rule["reason_code"] != "" else pd.NA
        out.loc[fire, "matched_rule_id"] = rule["rule_id"]
        out.loc[fire, "evidence_source"] = rule["evidence_source"]
        out.loc[fire, "metric_name"] = rule["metric"]
        if rule["metric"] in subjects_df.columns:
            out.loc[fire, "metric_value"] = subjects_df.loc[fire, rule["metric"]].astype(object)
        out.loc[fire, "threshold"] = rule["threshold"]
        unresolved = unresolved & ~fire

    if unresolved.any():
        raise AssertionError(
            f"{int(unresolved.sum())} subjects unresolved for level={level!r} dimension={dimension!r} "
            f"profile={profile!r} despite a catch-all rule -- this should be unreachable."
        )
    return out


def evaluate_dimensions(
    subjects_df: pd.DataFrame,
    policy_df: pd.DataFrame,
    *,
    level: str,
    dimensions: list[str],
    profile: str,
    column_prefix: str = "",
) -> pd.DataFrame:
    """Evaluate several dimensions and merge `<prefix><dimension>_status` (plus
    `_reason_code`/`_matched_rule_id`) columns onto a copy of subjects_df.
    """
    out = subjects_df.copy()
    for dimension in dimensions:
        result = evaluate_dimension(subjects_df, policy_df, level=level, dimension=dimension, profile=profile)
        out[f"{column_prefix}{dimension}_status"] = result["status"]
        out[f"{column_prefix}{dimension}_reason_code"] = result["reason_code"]
        out[f"{column_prefix}{dimension}_matched_rule_id"] = result["matched_rule_id"]
    return out


def aggregate_session_reasons(dimension_reason_codes: dict[str, pd.Series], rollup_reason_code: pd.Series) -> pd.DataFrame:
    """Build session_primary_reason / session_secondary_reasons /
    session_reason_count / session_reason_families from the reason codes
    that fired across all dimensions plus the rollup rule itself.
    session_primary_reason is deterministic by construction: it is exactly
    the reason code of whichever rollup rule decided session_qc_status
    (see rules_engine's first-match-wins semantics) -- not a second,
    independently-computed mode.
    """
    idx = rollup_reason_code.index
    primary = rollup_reason_code.copy()

    secondary = pd.Series([[] for _ in range(len(idx))], index=idx)
    families = pd.Series([set() for _ in range(len(idx))], index=idx)
    for dimension, codes in dimension_reason_codes.items():
        family = DIMENSION_FAMILY.get(dimension, "")
        for pos, i in enumerate(idx):
            code = codes.get(i)
            if pd.isna(code) or code == "":
                continue
            primary_code = primary.get(i)
            if pd.isna(primary_code) or code != primary_code:
                secondary.iloc[pos].append(code)
            families.iloc[pos].add(family)

    out = pd.DataFrame(index=idx)
    out["session_primary_reason"] = primary
    out["session_secondary_reasons"] = secondary.apply(lambda lst: ";".join(sorted(set(lst))))
    all_codes = [
        {c for c in ([primary.iloc[i]] + secondary.iloc[i]) if pd.notna(c) and c != ""}
        for i in range(len(idx))
    ]
    out["session_reason_count"] = [len(s) for s in all_codes]
    out["session_reason_families"] = families.apply(lambda s: ";".join(sorted(f for f in s if f)))
    return out
