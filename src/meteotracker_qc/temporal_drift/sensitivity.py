"""Section M: sensitivity sweep across a motivated, reduced design (never a
full cartesian product) -- 13 named geometry/profile rows already declared
in config/repeated_location_matching.csv (3 operational profiles + 10
sensitivity-only radius/separation/interaction rows) plus 5 QC-flag
inclusion variants at the recommended geometry (4 singles + all-included) =
18 configurations. Never auto-selects the configuration that produces the
most pairs, the narrowest CI, or the most "significant" trend -- the sweep
only classifies STABILITY, it does not pick a winner.
"""
from __future__ import annotations

import pandas as pd

from .assessability import (
    add_derived_assessability_columns, classify_assessability, compute_session_assessability_metrics,
)
from .candidates import RECOMMENDED_HARD_EXCLUSION_FLAGS, _apply_flag_exclusions, _base_valid, _bool_col
from .config import OPTIONAL_QC_FLAGS, get_profile, load_matching_policy
from .diagnosis import classify_temporal_change_diagnosis, prepare_diagnosis_metrics
from .grouping import compute_groups_and_visits
from .pairs import build_pairs
from .trend_methods import fixed_effects_huber_trend, pairwise_median_trend
from .uncertainty import compute_uncertainty_flags

SENSITIVITY_BOOTSTRAP_N = 200  # reduced from the main run's 1000 -- ~18 configs x 34 campaigns must stay tractable
SENSITIVITY_GEOMETRY_PROFILES = [
    "temporal_permissive", "temporal_recommended", "temporal_conservative",
    "sens_radius_5m", "sens_radius_10m", "sens_radius_20m", "sens_radius_30m",
    "sens_sep_60s", "sens_sep_180s", "sens_sep_600s",
    "sens_extreme_tight", "sens_extreme_loose", "sens_profile_conservative_radius5",
]
QC_FLAG_SWEEP_CONFIGS = [
    ("qc_include_post_stop_recovery", ["qc_post_stop_recovery"]),
    ("qc_include_low_ventilation", ["qc_low_ventilation_possible"]),
    ("qc_include_temp_rate_anomaly", ["qc_temp_rate_anomaly"]),
    ("qc_include_possible_gps_freeze", ["qc_possible_gps_freeze"]),
    ("qc_include_all_optional_flags", list(OPTIONAL_QC_FLAGS)),
]


def _custom_recommended_mask(df: pd.DataFrame, extra_exclusion_flags: list[str]) -> pd.Series:
    base_valid, _reasons = _base_valid(df)
    keep_recommended = _bool_col(df, "keep_recommended")
    valid = base_valid & keep_recommended
    dummy_reasons = pd.Series([[] for _ in range(len(df))], index=df.index)
    valid, _ = _apply_flag_exclusions(df, valid, dummy_reasons, RECOMMENDED_HARD_EXCLUSION_FLAGS + extra_exclusion_flags)
    return valid


def run_single_configuration(
    df: pd.DataFrame, config_name: str, profile_name: str, matching_policy: pd.DataFrame,
    temporal_drift_policy: pd.DataFrame, extra_qc_exclusions: list[str] | None = None,
    n_bootstrap: int = SENSITIVITY_BOOTSTRAP_N, random_state: int = 0,
) -> dict:
    profile = get_profile(matching_policy, profile_name)
    candidate_col = "_temporal_candidate_sensitivity"
    work = df.copy()
    if extra_qc_exclusions:
        work[candidate_col] = _custom_recommended_mask(work, extra_qc_exclusions)
    else:
        base_col = {
            "temporal_permissive": "temporal_candidate_permissive",
            "temporal_conservative": "temporal_candidate_conservative",
        }.get(profile.qc_profile, "temporal_candidate_recommended")
        work[candidate_col] = work[base_col]

    groups, visits, obs = compute_groups_and_visits(work, candidate_col, profile)
    pairs = build_pairs(visits, work, profile)
    session_start, session_end = work["time_utc"].min(), work["time_utc"].max()

    assess_metrics = compute_session_assessability_metrics(work, candidate_col, groups, visits, pairs, session_start, session_end)
    assess_df = add_derived_assessability_columns(pd.DataFrame([assess_metrics]))
    assessability = classify_assessability(assess_df, temporal_drift_policy).iloc[0]

    method1 = pairwise_median_trend(pairs, n_visits_total=len(visits), n_bootstrap=n_bootstrap, random_state=random_state)
    method2 = fixed_effects_huber_trend(visits, pairs, session_start, n_bootstrap=n_bootstrap, random_state=random_state)
    uncertainty = compute_uncertainty_flags(method1, method2, pairs)

    diag_metrics = prepare_diagnosis_metrics(
        assessability["status"], method1, method2, {"temporal_model_form": "LINEAR"}, uncertainty,
    )
    diagnosis = classify_temporal_change_diagnosis(pd.DataFrame([diag_metrics]), temporal_drift_policy).iloc[0]

    return {
        "config_name": config_name, "profile_name": profile_name,
        "extra_qc_exclusions": ";".join(extra_qc_exclusions) if extra_qc_exclusions else "",
        "n_groups_valid": assess_metrics["n_repeated_location_groups_valid"],
        "n_pairs_valid": assess_metrics["n_repeated_location_pairs_valid"],
        "assessability_status": assessability["status"],
        "method1_trend_c_per_min": method1["trend_c_per_min"],
        "method2_trend_c_per_min": method2["trend_c_per_min"],
        "method_agreement": uncertainty["method_agreement"],
        "temporal_change_diagnosis": diagnosis["status"],
    }


def run_session_sensitivity(
    df: pd.DataFrame, matching_policy: pd.DataFrame | None = None, temporal_drift_policy: pd.DataFrame | None = None,
    n_bootstrap: int = SENSITIVITY_BOOTSTRAP_N, random_state: int = 0,
) -> pd.DataFrame:
    matching_policy = matching_policy if matching_policy is not None else load_matching_policy()
    if temporal_drift_policy is None:
        raise ValueError("temporal_drift_policy must be provided (no implicit default path in this function)")

    rows = []
    for profile_name in SENSITIVITY_GEOMETRY_PROFILES:
        rows.append(run_single_configuration(
            df, profile_name, profile_name, matching_policy, temporal_drift_policy,
            extra_qc_exclusions=None, n_bootstrap=n_bootstrap, random_state=random_state,
        ))
    for config_name, flags in QC_FLAG_SWEEP_CONFIGS:
        rows.append(run_single_configuration(
            df, config_name, "temporal_recommended", matching_policy, temporal_drift_policy,
            extra_qc_exclusions=flags, n_bootstrap=n_bootstrap, random_state=random_state,
        ))
    return pd.DataFrame(rows)


def classify_stability(sensitivity_df: pd.DataFrame) -> dict:
    """Never selects a 'winning' configuration -- only characterizes how much
    the diagnosis and trend sign move across the sweep. Explicitly does not
    reward configurations that produce more pairs, tighter CIs, or more
    'significant' trends.
    """
    if sensitivity_df.empty:
        return {"temporal_sensitivity_stability_class": "NOT_ASSESSABLE", "n_configs": 0, "n_distinct_diagnoses": 0, "diagnosis_change_fraction": float("nan")}

    diagnoses = sensitivity_df["temporal_change_diagnosis"]
    n_distinct = diagnoses.nunique()
    n_configs = len(sensitivity_df)
    modal_diagnosis = diagnoses.mode().iloc[0]
    diagnosis_change_fraction = float((diagnoses != modal_diagnosis).mean())

    trend = sensitivity_df["method2_trend_c_per_min"].dropna()
    sign_changes = float("nan")
    if len(trend) >= 2:
        signs = trend.apply(lambda x: 1 if x > 0.005 else (-1 if x < -0.005 else 0))
        sign_changes = float((signs != signs.mode().iloc[0]).mean())

    if n_configs == 0 or diagnoses.eq("NOT_ASSESSABLE").all():
        stability_class = "NOT_ASSESSABLE"
    elif diagnosis_change_fraction <= 0.1 and (pd.isna(sign_changes) or sign_changes <= 0.1):
        stability_class = "STABLE"
    elif diagnosis_change_fraction <= 0.4 and (pd.isna(sign_changes) or sign_changes <= 0.3):
        stability_class = "MODERATELY_SENSITIVE"
    else:
        stability_class = "HIGHLY_SENSITIVE"

    return {
        "temporal_sensitivity_stability_class": stability_class, "n_configs": n_configs,
        "n_distinct_diagnoses": int(n_distinct), "diagnosis_change_fraction": diagnosis_change_fraction,
        "trend_sign_change_fraction": sign_changes,
    }
