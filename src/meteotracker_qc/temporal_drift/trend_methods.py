"""Sections G/H: robust trend estimation. Two independent methods are kept
separate (never averaged into one number): Method 1 (pairwise median slope,
this module) and Method 2 (fixed-location-effect "within" estimator, also
this module, plus nonlinear.py for the quadratic candidate).

Both methods share the same minimum-temporal-separation floor
(`MatchingProfile.minimum_temporal_separation_s`, applied once in pairs.py
when a pair is marked VALID/EXCLUDED). Method 1 consumes that filter directly
via `valid_pairs()`. Method 2 pools VISITS rather than pairs, so it cannot
apply the floor by comparing two timestamps directly -- instead
`prepare_model_visits` restricts its input to visits that participate in at
least one temporally-valid pair (see `_visits_with_valid_pair` below), which
is the visit-level projection of the exact same pair-level criterion. This
avoids a second, independently-tunable separation threshold for Method 2.

Every method returns the same schema (Section I): trend_c_per_min,
trend_c_per_hour, confidence_interval_low/high, bootstrap_n_valid,
n_location_groups, n_visits, n_pairs, model_residual_mad,
model_r2_descriptive, leave_one_group_out_stability, dominant_group_fraction
-- so callers (uncertainty.py, outputs.py) can treat all methods uniformly
regardless of which one produced them. Fields that are not meaningful for a
given method (e.g. model_r2_descriptive for the plain pairwise median) are
explicitly NaN, never a fabricated placeholder.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.stats import theilslopes

from .pairs import valid_pairs
from .robust_stats import mad, weighted_mad, weighted_median

MIN_GROUPS_FOR_BOOTSTRAP = 8
DEFAULT_N_BOOTSTRAP = 1000

RESULT_FIELDS = [
    "method", "trend_c_per_min", "trend_c_per_hour", "confidence_interval_low", "confidence_interval_high",
    "bootstrap_n_valid", "n_location_groups", "n_visits", "n_pairs", "model_residual_mad",
    "model_r2_descriptive", "leave_one_group_out_stability", "dominant_group_fraction",
]


def _empty_result(method: str, n_visits: int = 0) -> dict:
    return {
        "method": method, "trend_c_per_min": float("nan"), "trend_c_per_hour": float("nan"),
        "confidence_interval_low": float("nan"), "confidence_interval_high": float("nan"),
        "bootstrap_n_valid": 0, "n_location_groups": 0, "n_visits": n_visits, "n_pairs": 0,
        "model_residual_mad": float("nan"), "model_r2_descriptive": float("nan"),
        "leave_one_group_out_stability": float("nan"), "dominant_group_fraction": float("nan"),
    }


def _group_arrays(pairs: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    out = {}
    for gid, g in pairs.groupby("repeated_location_group_id"):
        out[gid] = (g["pairwise_slope_c_per_min"].to_numpy(dtype=float), g["pair_weight"].to_numpy(dtype=float))
    return out


def pairwise_median_trend(
    pairs: pd.DataFrame, n_visits_total: int = 0, n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    min_groups_for_bootstrap: int = MIN_GROUPS_FOR_BOOTSTRAP, random_state: int | None = 0,
) -> dict:
    """Method 1: group-weighted median of pairwise_slope_c_per_min (each pair
    weighted 1/C(n_visits_in_group,2) so a group's total contribution never
    exceeds another's just because it produced more combinatorial pairs).
    Cluster bootstrap CI resamples repeated_location_group_id with
    replacement -- never individual pairs. Below min_groups_for_bootstrap
    valid groups, the CI is reported as (NaN, NaN) rather than a spuriously
    narrow interval from too few distinct resamples.
    """
    vp = valid_pairs(pairs)
    if vp.empty:
        return _empty_result("pairwise_median", n_visits_total)

    slopes = vp["pairwise_slope_c_per_min"].to_numpy(dtype=float)
    weights = vp["pair_weight"].to_numpy(dtype=float)
    trend_per_min = weighted_median(slopes, weights)
    residual_mad = weighted_mad(slopes, weights)

    group_totals = vp.groupby("repeated_location_group_id")["pair_weight"].sum()
    n_groups = len(group_totals)
    dominant_fraction = float(group_totals.max() / group_totals.sum()) if group_totals.sum() > 0 else float("nan")

    by_group = _group_arrays(vp)
    group_ids = list(by_group.keys())
    logo_estimates = []
    for held_out in group_ids:
        s = np.concatenate([by_group[g][0] for g in group_ids if g != held_out]) if len(group_ids) > 1 else np.array([])
        w = np.concatenate([by_group[g][1] for g in group_ids if g != held_out]) if len(group_ids) > 1 else np.array([])
        if len(s):
            logo_estimates.append(weighted_median(s, w))
    if len(logo_estimates) >= 2:
        logo_spread = float(np.std(logo_estimates))
        denom = max(abs(trend_per_min), 1e-6)
        logo_stability = logo_spread / denom
    else:
        logo_stability = float("nan")

    ci_low, ci_high, n_valid_boot = float("nan"), float("nan"), 0
    if n_groups >= min_groups_for_bootstrap:
        rng = np.random.default_rng(random_state)
        boot_estimates = []
        for _ in range(n_bootstrap):
            draw = rng.choice(group_ids, size=n_groups, replace=True)
            s = np.concatenate([by_group[g][0] for g in draw])
            w = np.concatenate([by_group[g][1] for g in draw])
            boot_estimates.append(weighted_median(s, w))
        boot_estimates = np.array(boot_estimates)
        ci_low, ci_high = float(np.percentile(boot_estimates, 2.5)), float(np.percentile(boot_estimates, 97.5))
        n_valid_boot = int(np.isfinite(boot_estimates).sum())

    return {
        "method": "pairwise_median", "trend_c_per_min": trend_per_min, "trend_c_per_hour": trend_per_min * 60.0,
        "confidence_interval_low": ci_low, "confidence_interval_high": ci_high, "bootstrap_n_valid": n_valid_boot,
        "n_location_groups": n_groups, "n_visits": n_visits_total, "n_pairs": len(vp),
        "model_residual_mad": residual_mad, "model_r2_descriptive": float("nan"),
        "leave_one_group_out_stability": logo_stability, "dominant_group_fraction": dominant_fraction,
    }


# ============================================================
# Method 2: fixed-location-effect ("within") estimator, indexed by VISIT
# (not raw point) to avoid pseudo-replication from high-frequency visits.
# alpha_j (the group's own offset) is never estimated or reported as a
# "true location temperature" -- eliminated entirely by group-demeaning,
# consistent with spec section G's explicit warning against that
# interpretation.
# ============================================================

MIN_VISITS_PER_GROUP_FOR_MODEL = 2
MIN_POOLED_VISITS_FOR_THEILSEN = 4


def _visits_with_valid_pair(pairs: pd.DataFrame) -> set:
    """Visit ids that participate in at least one temporally-valid revisit
    pair (pairs.py already encodes minimum_temporal_separation_s, spatial
    radius, and visit-quality checks into `pair_qc_status`). A visit with NO
    valid pair has no same-group counterpart far enough away in time to
    supply real temporal-contrast evidence -- keeping it in Method 2's pooled
    regression would let a pseudo-replicated near-duplicate reading masquerade
    as a revisit, exactly the risk minimum_temporal_separation_s exists to
    rule out for Method 1's pairs.
    """
    if pairs is None or pairs.empty:
        return set()
    vp = valid_pairs(pairs)
    if vp.empty:
        return set()
    return set(vp["visit_id_earlier"]) | set(vp["visit_id_later"])


def prepare_model_visits(
    visits: pd.DataFrame, pairs: pd.DataFrame, min_visits_per_group: int = MIN_VISITS_PER_GROUP_FOR_MODEL,
) -> pd.DataFrame:
    """Visits usable for Method 2: quality-OK visits that also have at least
    one same-group revisit separated by >= minimum_temporal_separation_s
    (via `_visits_with_valid_pair`, sharing Method 1's threshold rather than
    duplicating it), in groups with enough such visits left to support
    within-group demeaning. A visit can be OK-quality and still be dropped
    here if every other visit in its group is too close in time to it.
    """
    if visits.empty:
        return visits
    ok = visits[visits["visit_qc_status"] == "OK"].copy()
    if ok.empty:
        return ok
    supported_ids = _visits_with_valid_pair(pairs)
    ok = ok[ok["repeated_location_visit_id"].isin(supported_ids)]
    if ok.empty:
        return ok
    counts = ok.groupby("repeated_location_group_id").size()
    valid_groups = counts[counts >= min_visits_per_group].index
    return ok[ok["repeated_location_group_id"].isin(valid_groups)].reset_index(drop=True)


def demean_by_group(model_visits: pd.DataFrame, session_start: pd.Timestamp) -> pd.DataFrame:
    if model_visits.empty:
        return model_visits.assign(t_s=[], t_demeaned=[], T_demeaned=[])
    df = model_visits.copy()
    df["t_s"] = (df["visit_representative_timestamp"] - session_start).dt.total_seconds()
    df["t_demeaned"] = df["t_s"] - df.groupby("repeated_location_group_id")["t_s"].transform("mean")
    df["T_demeaned"] = df["visit_representative_temperature_c"] - df.groupby("repeated_location_group_id")["visit_representative_temperature_c"].transform("mean")
    return df


def _ols_slope(t: np.ndarray, T: np.ndarray) -> float:
    denom = float(np.sum(t ** 2))
    if denom <= 0:
        return float("nan")
    return float(np.sum(t * T) / denom)


def _huber_slope(t: np.ndarray, T: np.ndarray) -> float:
    if len(t) == 0 or np.sum(t ** 2) <= 0:
        return float("nan")
    ols = _ols_slope(t, T)
    resid0 = T - ols * t
    f_scale = max(mad(resid0) * 1.4826, 1e-6)  # 1.4826 * MAD ~ robust sigma estimate under normality

    def resid(beta):
        return T - beta[0] * t

    result = least_squares(resid, x0=[ols], loss="huber", f_scale=f_scale)
    return float(result.x[0])


def _theilsen_slope(t: np.ndarray, T: np.ndarray) -> float:
    if len(t) < MIN_POOLED_VISITS_FOR_THEILSEN or np.allclose(t, t[0]):
        return float("nan")
    slope, _intercept, _low, _high = theilslopes(T, t)
    return float(slope)


def _within_estimator_result(
    method_name: str, slope_fn, demeaned: pd.DataFrame, n_visits_total: int,
    min_groups_for_bootstrap: int, n_bootstrap: int, random_state: int | None,
) -> dict:
    if demeaned.empty:
        return _empty_result(method_name, n_visits_total)

    t_all = demeaned["t_demeaned"].to_numpy(dtype=float)
    T_all = demeaned["T_demeaned"].to_numpy(dtype=float)
    beta = slope_fn(t_all, T_all)
    residuals = T_all - beta * t_all if not np.isnan(beta) else np.full_like(T_all, np.nan)
    residual_mad = mad(residuals)
    T_mad = mad(T_all)
    r2_descriptive = float("nan")
    if T_mad and T_mad > 0 and not np.isnan(residual_mad):
        r2_descriptive = float(1.0 - (residual_mad / T_mad) ** 2)

    group_sizes = demeaned.groupby("repeated_location_group_id").size()
    n_groups = len(group_sizes)
    dominant_fraction = float(group_sizes.max() / group_sizes.sum()) if group_sizes.sum() > 0 else float("nan")

    by_group_t = {g: gdf["t_demeaned"].to_numpy(dtype=float) for g, gdf in demeaned.groupby("repeated_location_group_id")}
    by_group_T = {g: gdf["T_demeaned"].to_numpy(dtype=float) for g, gdf in demeaned.groupby("repeated_location_group_id")}
    group_ids = list(by_group_t.keys())

    logo_estimates = []
    for held_out in group_ids:
        remaining = [g for g in group_ids if g != held_out]
        if not remaining:
            continue
        t = np.concatenate([by_group_t[g] for g in remaining])
        T = np.concatenate([by_group_T[g] for g in remaining])
        est = slope_fn(t, T)
        if not np.isnan(est):
            logo_estimates.append(est)
    if len(logo_estimates) >= 2:
        denom = max(abs(beta), 1e-6) if not np.isnan(beta) else 1e-6
        logo_stability = float(np.std(logo_estimates) / denom)
    else:
        logo_stability = float("nan")

    ci_low, ci_high, n_valid_boot = float("nan"), float("nan"), 0
    if n_groups >= min_groups_for_bootstrap:
        rng = np.random.default_rng(random_state)
        boot_estimates = []
        for _ in range(n_bootstrap):
            draw = rng.choice(group_ids, size=n_groups, replace=True)
            t = np.concatenate([by_group_t[g] for g in draw])
            T = np.concatenate([by_group_T[g] for g in draw])
            est = slope_fn(t, T)
            if not np.isnan(est):
                boot_estimates.append(est)
        if boot_estimates:
            boot_arr = np.array(boot_estimates)
            ci_low, ci_high = float(np.percentile(boot_arr, 2.5)), float(np.percentile(boot_arr, 97.5))
            n_valid_boot = int(len(boot_arr))

    return {
        "method": method_name, "trend_c_per_min": beta * 60.0 if not np.isnan(beta) else float("nan"),
        "trend_c_per_hour": beta * 3600.0 if not np.isnan(beta) else float("nan"),
        "confidence_interval_low": ci_low * 60.0 if not np.isnan(ci_low) else float("nan"),
        "confidence_interval_high": ci_high * 60.0 if not np.isnan(ci_high) else float("nan"),
        "bootstrap_n_valid": n_valid_boot, "n_location_groups": n_groups, "n_visits": len(demeaned),
        "n_pairs": 0, "model_residual_mad": residual_mad, "model_r2_descriptive": r2_descriptive,
        "leave_one_group_out_stability": logo_stability, "dominant_group_fraction": dominant_fraction,
    }


def _boot_kwargs(kwargs: dict) -> dict:
    return {
        "min_groups_for_bootstrap": kwargs.get("min_groups_for_bootstrap", MIN_GROUPS_FOR_BOOTSTRAP),
        "n_bootstrap": kwargs.get("n_bootstrap", DEFAULT_N_BOOTSTRAP),
        "random_state": kwargs.get("random_state", 0),
    }


def fixed_effects_ols_trend(visits: pd.DataFrame, pairs: pd.DataFrame, session_start: pd.Timestamp, **kwargs) -> dict:
    """Baseline only -- not the primary method (spec explicitly favors
    robustness over an OLS/significance-driven choice)."""
    demeaned = demean_by_group(prepare_model_visits(visits, pairs), session_start)
    return _within_estimator_result("fixed_effects_ols", _ols_slope, demeaned, len(visits), **_boot_kwargs(kwargs))


def fixed_effects_huber_trend(visits: pd.DataFrame, pairs: pd.DataFrame, session_start: pd.Timestamp, **kwargs) -> dict:
    """Primary Method-2 estimator: robust to outlier visits, chosen for
    robustness/stability rather than significance (spec section G)."""
    demeaned = demean_by_group(prepare_model_visits(visits, pairs), session_start)
    return _within_estimator_result("fixed_effects_huber", _huber_slope, demeaned, len(visits), **_boot_kwargs(kwargs))


def fixed_effects_theilsen_trend(visits: pd.DataFrame, pairs: pd.DataFrame, session_start: pd.Timestamp, **kwargs) -> dict:
    """Pairwise-robust alternative, only meaningful with >= 4 pooled
    demeaned visits; NaN result (INSUFFICIENT_SUPPORT-equivalent) below
    that, never a degenerate slope."""
    demeaned = demean_by_group(prepare_model_visits(visits, pairs), session_start)
    return _within_estimator_result("fixed_effects_theilsen", _theilsen_slope, demeaned, len(visits), **_boot_kwargs(kwargs))
