"""Section K: experimental detrended product. Never touches the official
temperature -- entirely separate columns, produced only for sessions that
clear the eligibility bar, and only ever written to a dedicated experimental
CSV (outputs.py), never merged back into permissive/recommended/restrictive.

Simplification documented here and in the final report (residual limit):
even when temporal_model_form == NONLINEAR_CANDIDATE, detrending still uses
the LINEAR Method-2-primary slope. The quadratic coefficients were fit on
PER-GROUP-demeaned time (t - group_mean), and expanding beta2*(t-group_mean)^2
mixes the linear and quadratic terms with each group's own mean -- so the
fitted beta1/beta2 are not directly portable to a single absolute-time trend
function the way the linear beta is (the linear slope IS portable: only the
per-group intercept was removed, not the time axis). Building a correct
common-quadratic-after-fixed-effects detrending function is a bigger
methodological undertaking than this phase's simplification allows; linear
detrending is applied as the conservative, sound (not confounded) choice.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EXTRAPOLATION_CAP_MULTIPLIER = 1.5


def is_detrending_eligible(
    assessability_status: str, temporal_change_diagnosis: str,
    sensitivity_stability_class: str | None, method2_primary: dict,
) -> tuple[bool, list[str]]:
    warnings = []
    if assessability_status != "ASSESSABLE":
        return False, ["NOT_ELIGIBLE_ASSESSABILITY_INSUFFICIENT"]
    if temporal_change_diagnosis not in {"TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "POSSIBLE_NONLINEAR_BACKGROUND_CHANGE"}:
        return False, ["NOT_ELIGIBLE_DIAGNOSIS_NOT_SUPPORTED"]
    if sensitivity_stability_class is not None and sensitivity_stability_class not in {"STABLE", "MODERATELY_SENSITIVE"}:
        return False, ["NOT_ELIGIBLE_SENSITIVITY_UNSTABLE"]
    dominant = method2_primary.get("dominant_group_fraction")
    if pd.notna(dominant) and dominant > 0.45:
        return False, ["NOT_ELIGIBLE_DOMINATED_BY_SINGLE_GROUP"]
    if temporal_change_diagnosis == "POSSIBLE_NONLINEAR_BACKGROUND_CHANGE":
        warnings.append("NONLINEAR_DETREND_NOT_IMPLEMENTED_USING_LINEAR_APPROXIMATION")
    return True, warnings


def compute_experimental_detrending(
    df: pd.DataFrame, candidate_col: str, session_start: pd.Timestamp, session_end: pd.Timestamp,
    method2_primary: dict, eligible: bool, base_warnings: list[str] | None = None,
    extrapolation_cap_multiplier: float = EXTRAPOLATION_CAP_MULTIPLIER,
) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["time_utc"] = df["time_utc"]
    out["temp_original_c"] = df["canonical_temperature_c"]

    if not eligible or pd.isna(session_start) or pd.isna(session_end):
        out["temporal_trend_candidate_c"] = np.nan
        out["temp_detrended_experimental_c"] = np.nan
        out["detrending_supported"] = False
        out["detrending_method"] = "NONE"
        out["detrending_reference_time"] = pd.NaT
        out["detrending_warning_codes"] = ";".join(base_warnings) if base_warnings else "NOT_ELIGIBLE"
        return out

    beta_per_min = method2_primary.get("trend_c_per_min")
    if pd.isna(beta_per_min):
        out["temporal_trend_candidate_c"] = np.nan
        out["temp_detrended_experimental_c"] = np.nan
        out["detrending_supported"] = False
        out["detrending_method"] = "NONE"
        out["detrending_reference_time"] = pd.NaT
        out["detrending_warning_codes"] = "NOT_ELIGIBLE_NO_TREND_ESTIMATE"
        return out

    beta_per_s = beta_per_min / 60.0
    t_ref = session_start + (session_end - session_start) / 2
    candidate_time_span_s = (session_end - session_start).total_seconds()
    cap_s = extrapolation_cap_multiplier * candidate_time_span_s / 2.0  # cap measured from t_ref on each side

    t_offset_s = (df["time_utc"] - t_ref).dt.total_seconds()
    within_cap = t_offset_s.abs() <= cap_s

    trend = beta_per_s * t_offset_s
    detrended = out["temp_original_c"] - trend

    warning_codes = pd.Series("", index=df.index)
    is_candidate = df[candidate_col].astype(bool) if candidate_col in df.columns else pd.Series(True, index=df.index)
    warning_codes.loc[~is_candidate & within_cap] = "EXTRAPOLATED_FROM_MODEL"
    warning_codes.loc[~within_cap] = "EXTRAPOLATION_RANGE_EXCEEDED"

    trend_out = trend.where(within_cap, np.nan)
    detrended_out = detrended.where(within_cap, np.nan)

    base = ";".join(base_warnings) if base_warnings else ""
    out["temporal_trend_candidate_c"] = trend_out
    out["temp_detrended_experimental_c"] = detrended_out
    out["detrending_supported"] = True
    out["detrending_method"] = "fixed_effects_huber_linear"
    out["detrending_reference_time"] = t_ref
    out["detrending_warning_codes"] = warning_codes.apply(lambda w: ";".join(c for c in [base, w] if c))
    return out


def session_mean_deltas(detrending_df: pd.DataFrame, session_start: pd.Timestamp, session_end: pd.Timestamp) -> dict:
    """delta_session_mean_raw_c / delta_session_mean_detrended_experimental_c:
    how far the session's overall mean temperature sits from the raw
    temperature interpolated exactly AT the reference time, before vs after
    detrending -- a well-behaved detrending should pull this closer to zero
    (a single trip no longer has an average biased by when within the
    session most candidate points happen to fall), never used as a
    pass/fail criterion by itself. The reference value is linearly
    interpolated at t_ref (not snapped to the nearest sampled row) so the
    two deltas are directly comparable without a discretization bias.
    """
    valid = detrending_df["temp_original_c"].notna()
    if not valid.any():
        return {"delta_session_mean_raw_c": float("nan"), "delta_session_mean_detrended_experimental_c": float("nan")}
    raw_mean = detrending_df.loc[valid, "temp_original_c"].mean()
    detrended_valid = detrending_df["temp_detrended_experimental_c"].notna()
    detrended_mean = detrending_df.loc[detrended_valid, "temp_detrended_experimental_c"].mean() if detrended_valid.any() else float("nan")

    t_ref_series = detrending_df["detrending_reference_time"].dropna()
    if t_ref_series.empty or "time_utc" not in detrending_df.columns:
        ref_temp = float(detrending_df.loc[valid, "temp_original_c"].iloc[len(detrending_df.loc[valid]) // 2])
    else:
        t_ref = t_ref_series.iloc[0]
        sub = detrending_df.loc[valid].sort_values("time_utc")
        offsets = (sub["time_utc"] - t_ref).dt.total_seconds().to_numpy()
        temps = sub["temp_original_c"].to_numpy(dtype=float)
        ref_temp = float(np.interp(0.0, offsets, temps))

    return {
        "delta_session_mean_raw_c": float(raw_mean - ref_temp),
        "delta_session_mean_detrended_experimental_c": float(detrended_mean - ref_temp) if pd.notna(detrended_mean) else float("nan"),
    }
