"""6 usable_for_* analysis-suitability categories, evaluated against
config/session_suitability_policy.csv. Deliberately does not import or read
anything from repeated_routes/ (route_comparison stays a suitability
*signal*, never an actual route-matching computation).
"""
from __future__ import annotations

import pandas as pd

from .rules_engine import _evaluate_condition

ANALYSIS_TYPES = [
    "spatial_mapping",
    "route_comparison",
    "temporal_drift_analysis",
    "satellite_coincidence",
    "environment_class_analysis",
    "full_route_statistics",
]


def evaluate_suitability(session_metrics: pd.DataFrame, suitability_policy: pd.DataFrame, analysis_type: str) -> pd.DataFrame:
    rules = suitability_policy[suitability_policy["analysis_type"] == analysis_type].sort_values("priority", kind="stable")
    if rules.empty:
        raise ValueError(f"no rules for analysis_type={analysis_type!r}")
    if "always" not in rules["operator"].tolist():
        raise ValueError(f"no catch-all rule for analysis_type={analysis_type!r}")

    idx = session_metrics.index
    status = pd.Series(pd.NA, index=idx, dtype="object")
    reason_code = pd.Series(pd.NA, index=idx, dtype="object")
    matched_rule = pd.Series(pd.NA, index=idx, dtype="object")
    limiting_metric = pd.Series(pd.NA, index=idx, dtype="object")

    unresolved = pd.Series(True, index=idx)
    for _, rule in rules.iterrows():
        if not unresolved.any():
            break
        cond = _evaluate_condition(session_metrics, rule["metric"], rule["operator"], rule["threshold"])
        fire = cond.reindex(idx, fill_value=False) & unresolved
        if not fire.any():
            continue
        status.loc[fire] = rule["resulting_status"]
        reason_code.loc[fire] = rule["reason_code"] if pd.notna(rule["reason_code"]) and rule["reason_code"] != "" else pd.NA
        matched_rule.loc[fire] = rule["rule_id"]
        limiting_metric.loc[fire] = rule["metric"]
        unresolved = unresolved & ~fire

    out = pd.DataFrame(index=idx)
    out["analysis_type"] = analysis_type
    out["suitability_status"] = status
    out["reason_codes"] = reason_code
    out["matched_rule_id"] = matched_rule
    out["limiting_dimensions"] = limiting_metric
    return out


def compute_all_suitability(session_metrics: pd.DataFrame, suitability_policy: pd.DataFrame, segment_metrics: pd.DataFrame) -> pd.DataFrame:
    """Long format, one row per (canonical_campaign_id, analysis_type) --
    qualifying_segments is a variable-length list per campaign, awkward as
    wide columns (see Section N)."""
    rows = []
    for analysis_type in ANALYSIS_TYPES:
        result = evaluate_suitability(session_metrics, suitability_policy, analysis_type).reset_index(drop=True)
        campaigns = session_metrics["canonical_campaign_id"].reset_index(drop=True)
        for i, campaign_id in enumerate(campaigns):
            qualifying = []
            if "segment_qc_status" in segment_metrics.columns:
                qualifying = segment_metrics.loc[
                    (segment_metrics["canonical_campaign_id"] == campaign_id)
                    & segment_metrics["segment_qc_status"].isin(["PASS", "PASS_WITH_WARNINGS"]),
                    "segment_id",
                ].tolist()
            rows.append({
                "canonical_campaign_id": campaign_id,
                "analysis_type": analysis_type,
                "suitability_status": result.loc[i, "suitability_status"],
                "reason_codes": result.loc[i, "reason_codes"],
                "qualifying_segments": ";".join(str(s) for s in qualifying),
                "limiting_dimensions": result.loc[i, "limiting_dimensions"],
            })
    return pd.DataFrame(rows)
