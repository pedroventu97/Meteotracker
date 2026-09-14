"""Section H: nonlinear (quadratic-only, never a flexible spline/LOWESS)
candidate model. Only attempted for sessions with enough groups, >=3
distinct time windows, and sufficient duration -- gated explicitly, never
run by default. Validated via leave-one-GROUP-out cross-validation (never
leave-one-row-out, which would leak within-group structure). A guard against
absorbing real spatial contrast: a genuine temporal effect should look
similar whether estimated from same_direction or opposite_direction visits;
a lane/side-of-road artifact typically would not.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from .robust_stats import mad
from .trend_methods import _huber_slope, _ols_slope, demean_by_group, prepare_model_visits

MIN_GROUPS_FOR_NONLINEAR = 5
MIN_TIME_WINDOWS_FOR_NONLINEAR = 3
MIN_DURATION_S_FOR_NONLINEAR = 1800.0
IMPROVEMENT_MARGIN = 0.15  # quadratic must beat linear CV residual MAD by >=15% (not just numerically)
MIN_POOLED_FOR_DIRECTION_CHECK = 6
DIRECTION_DISAGREEMENT_BETA2_FLOOR = 1e-8


def _quadratic_slope(t: np.ndarray, T: np.ndarray) -> tuple[float, float]:
    if len(t) < 3 or np.sum(t ** 2) <= 0:
        return float("nan"), float("nan")
    ols_lin = _ols_slope(t, T)
    resid0 = T - ols_lin * t
    f_scale = max(mad(resid0) * 1.4826, 1e-6)

    def resid(beta):
        return T - beta[0] * t - beta[1] * t ** 2

    result = least_squares(resid, x0=[ols_lin, 0.0], loss="huber", f_scale=f_scale)
    return float(result.x[0]), float(result.x[1])


def is_nonlinear_eligible(n_groups: int, n_time_windows: int, nominal_time_span_s: float) -> bool:
    return (
        n_groups >= MIN_GROUPS_FOR_NONLINEAR
        and n_time_windows >= MIN_TIME_WINDOWS_FOR_NONLINEAR
        and pd.notna(nominal_time_span_s) and nominal_time_span_s >= MIN_DURATION_S_FOR_NONLINEAR
    )


def _direction_consistency_check(demeaned: pd.DataFrame) -> bool | None:
    """Returns True (consistent / not testable), False (disagreement), or
    None if there isn't enough data in one of the two subsets to check at
    all -- callers should treat None as "benefit of the doubt", documented.
    """
    same = demeaned[demeaned["visit_direction_class"] == "same_direction"] if "visit_direction_class" in demeaned.columns else demeaned.iloc[0:0]
    opposite = demeaned[demeaned["visit_direction_class"] == "opposite_direction"] if "visit_direction_class" in demeaned.columns else demeaned.iloc[0:0]
    if len(same) < MIN_POOLED_FOR_DIRECTION_CHECK or len(opposite) < MIN_POOLED_FOR_DIRECTION_CHECK:
        return None
    _b1_same, b2_same = _quadratic_slope(same["t_demeaned"].to_numpy(dtype=float), same["T_demeaned"].to_numpy(dtype=float))
    _b1_opp, b2_opp = _quadratic_slope(opposite["t_demeaned"].to_numpy(dtype=float), opposite["T_demeaned"].to_numpy(dtype=float))
    if np.isnan(b2_same) or np.isnan(b2_opp):
        return None
    if abs(b2_same) < DIRECTION_DISAGREEMENT_BETA2_FLOOR and abs(b2_opp) < DIRECTION_DISAGREEMENT_BETA2_FLOOR:
        return True
    return bool(np.sign(b2_same) == np.sign(b2_opp))


def evaluate_nonlinear_candidate(
    visits: pd.DataFrame, pairs: pd.DataFrame, session_start: pd.Timestamp, n_groups_valid: int,
    n_time_windows: int, nominal_time_span_s: float,
) -> dict:
    result = {
        "temporal_model_form": "NONE", "nonlinear_cv_linear_residual_mad": float("nan"),
        "nonlinear_cv_quadratic_residual_mad": float("nan"), "nonlinear_cv_improvement_fraction": float("nan"),
        "nonlinear_direction_consistent": None, "nonlinear_quadratic_beta1_c_per_s": float("nan"),
        "nonlinear_quadratic_beta2_c_per_s2": float("nan"),
    }
    if visits.empty:
        return result

    if not is_nonlinear_eligible(n_groups_valid, n_time_windows, nominal_time_span_s):
        result["temporal_model_form"] = "INSUFFICIENT_SUPPORT"
        return result

    model_visits = prepare_model_visits(visits, pairs)
    demeaned = demean_by_group(model_visits, session_start)
    if "visit_direction_class" not in demeaned.columns and "visit_direction_class" in visits.columns:
        demeaned = demeaned.merge(visits[["repeated_location_visit_id", "visit_direction_class"]], on="repeated_location_visit_id", how="left")
    group_ids = demeaned["repeated_location_group_id"].unique().tolist()
    if len(group_ids) < MIN_GROUPS_FOR_NONLINEAR:
        result["temporal_model_form"] = "INSUFFICIENT_SUPPORT"
        return result

    by_t = {g: gdf["t_demeaned"].to_numpy(dtype=float) for g, gdf in demeaned.groupby("repeated_location_group_id")}
    by_T = {g: gdf["T_demeaned"].to_numpy(dtype=float) for g, gdf in demeaned.groupby("repeated_location_group_id")}

    lin_abs_resid, quad_abs_resid = [], []
    for held_out in group_ids:
        remaining = [g for g in group_ids if g != held_out]
        t_train = np.concatenate([by_t[g] for g in remaining])
        T_train = np.concatenate([by_T[g] for g in remaining])
        beta_lin = _huber_slope(t_train, T_train)
        beta1, beta2 = _quadratic_slope(t_train, T_train)
        t_test, T_test = by_t[held_out], by_T[held_out]
        if np.isnan(beta_lin) or np.isnan(beta1):
            continue
        lin_abs_resid.append(np.abs(T_test - beta_lin * t_test))
        quad_abs_resid.append(np.abs(T_test - beta1 * t_test - beta2 * t_test ** 2))

    if not lin_abs_resid:
        result["temporal_model_form"] = "INSUFFICIENT_SUPPORT"
        return result

    lin_mad = float(np.median(np.concatenate(lin_abs_resid)))
    quad_mad = float(np.median(np.concatenate(quad_abs_resid)))
    improvement = (lin_mad - quad_mad) / lin_mad if lin_mad > 0 else 0.0
    direction_ok = _direction_consistency_check(demeaned)

    beta1_full, beta2_full = _quadratic_slope(
        demeaned["t_demeaned"].to_numpy(dtype=float), demeaned["T_demeaned"].to_numpy(dtype=float)
    )

    result.update({
        "nonlinear_cv_linear_residual_mad": lin_mad, "nonlinear_cv_quadratic_residual_mad": quad_mad,
        "nonlinear_cv_improvement_fraction": improvement, "nonlinear_direction_consistent": direction_ok,
        "nonlinear_quadratic_beta1_c_per_s": beta1_full, "nonlinear_quadratic_beta2_c_per_s2": beta2_full,
    })

    if improvement >= IMPROVEMENT_MARGIN and direction_ok is not False:
        result["temporal_model_form"] = "NONLINEAR_CANDIDATE"
    else:
        result["temporal_model_form"] = "LINEAR"
    return result
