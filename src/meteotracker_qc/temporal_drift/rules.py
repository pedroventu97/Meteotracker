"""Thin first-match-wins rule engine for config/temporal_drift_policy.csv.

session_qc/rules_engine.py::evaluate_dimension is hard-coupled to
level/dimension/profile filtering columns that temporal_drift_policy.csv
does not have (its schema is rule_id,scope,metric,operator,threshold,unit,
resulting_status,reason_code,priority,evidence_source,rationale,
sensitivity_values,enabled -- dictated by the spec). Rather than force that
schema to fit evaluate_dimension, this module reuses the one genuinely
schema-agnostic piece of it (`_evaluate_condition`, a pure per-row predicate)
inside a new, equally-strict scope-only first-match-wins loop.
"""
from __future__ import annotations

import pandas as pd

from ..session_qc.rules_engine import _evaluate_condition


def evaluate_scope(subjects_df: pd.DataFrame, policy_df: pd.DataFrame, scope: str) -> pd.DataFrame:
    rules = policy_df[
        (policy_df["scope"] == scope) & (policy_df["enabled"].astype(bool))
    ].sort_values("priority", kind="stable")

    if rules.empty:
        raise ValueError(f"no enabled rules for scope={scope!r}")
    if "always" not in rules["operator"].to_list():
        raise ValueError(f"no catch-all ('always') rule for scope={scope!r}")

    idx = subjects_df.index
    status = pd.Series(pd.NA, index=idx, dtype="object")
    reason_code = pd.Series(pd.NA, index=idx, dtype="object")
    matched_rule_id = pd.Series(pd.NA, index=idx, dtype="object")
    evidence_source = pd.Series(pd.NA, index=idx, dtype="object")

    unresolved = pd.Series(True, index=idx)
    for _, rule in rules.iterrows():
        if not unresolved.any():
            break
        cond = _evaluate_condition(subjects_df, rule["metric"], rule["operator"], rule["threshold"])
        fire = cond.reindex(idx, fill_value=False) & unresolved
        if not fire.any():
            continue
        status.loc[fire] = rule["resulting_status"]
        reason_code.loc[fire] = rule["reason_code"]
        matched_rule_id.loc[fire] = rule["rule_id"]
        evidence_source.loc[fire] = rule["evidence_source"]
        unresolved &= ~fire

    if unresolved.any():
        raise AssertionError(f"{int(unresolved.sum())} subjects unresolved for scope={scope!r} despite a catch-all rule")

    return pd.DataFrame({
        "status": status, "reason_code": reason_code,
        "matched_rule_id": matched_rule_id, "evidence_source": evidence_source,
    })
