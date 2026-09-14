"""Section J: temporal_change_diagnosis + sensor_drift_interpretation.
Deliberately conservative vocabulary -- SENSOR_DRIFT is never a value either
field can take. Classification is rule-based via rules.py, never a hidden
severity blend of the underlying method results.
"""
from __future__ import annotations

import pandas as pd

from .rules import evaluate_scope

INSTRUMENT_EFFECT_TREND_THRESHOLD_C_PER_MIN = 0.02  # ~1.2 C/hour -- large enough to be atmospherically unusual for a short urban transect


def prepare_diagnosis_metrics(
    assessability_status: str, method1: dict, method2_primary: dict,
    nonlinear_result: dict, uncertainty: dict,
) -> dict:
    ci_low, ci_high = method2_primary.get("confidence_interval_low"), method2_primary.get("confidence_interval_high")
    ci_excludes_zero = 0
    if pd.notna(ci_low) and pd.notna(ci_high):
        ci_excludes_zero = 1 if (ci_low > 0 and ci_high > 0) or (ci_low < 0 and ci_high < 0) else 0

    any_instability = 1 if (
        uncertainty.get("ci_too_wide") or uncertainty.get("dominated_by_single_location")
        or uncertainty.get("leave_one_group_out_unstable") or uncertainty.get("direction_consistency") == "dependent"
    ) else 0

    trend = method2_primary.get("trend_c_per_min")
    method1_trend = method1.get("trend_c_per_min")
    # method1/method2 still run (and can return numerically extreme values, e.g.
    # -0.34 C/min) on sessions that never reach ASSESSABLE, because the trend-estimation
    # code has no awareness of the assessability gate. Null the estimate fields here so
    # "check temporal_internal_assessability_status before reading a trend value" is
    # enforced by the output schema itself rather than left to every downstream reader
    # to remember. Safe to do after ci_excludes_zero above: every policy rule that reads
    # these fields (SDI-EXT-01, TCD-SUP-01) sits at a lower priority than the
    # assessability/diagnosis short-circuits (TCD-NA-01, TCD-IR-01, SDI-NA-01), which
    # always match first for non-ASSESSABLE sessions and are evaluated first-match-wins.
    if assessability_status != "ASSESSABLE":
        trend = float("nan")
        method1_trend = float("nan")
        ci_low = float("nan")
        ci_high = float("nan")

    return {
        "temporal_internal_assessability_status": assessability_status,
        "method_agreement": uncertainty.get("method_agreement"),
        "any_instability_flag": any_instability,
        "temporal_model_form": nonlinear_result.get("temporal_model_form"),
        "trend_supported_flag": ci_excludes_zero,
        "primary_trend_c_per_min": trend,
        "abs_primary_trend_c_per_min": abs(trend) if pd.notna(trend) else float("nan"),
        "primary_confidence_interval_low": ci_low, "primary_confidence_interval_high": ci_high,
        "method1_trend_c_per_min": method1_trend,
    }


def classify_temporal_change_diagnosis(metrics: pd.DataFrame, policy_df: pd.DataFrame) -> pd.DataFrame:
    return evaluate_scope(metrics, policy_df, scope="temporal_change_diagnosis")


def classify_sensor_drift_interpretation(metrics_with_diagnosis: pd.DataFrame, policy_df: pd.DataFrame) -> pd.DataFrame:
    return evaluate_scope(metrics_with_diagnosis, policy_df, scope="sensor_drift_interpretation")
