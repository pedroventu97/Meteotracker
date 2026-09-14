"""Section I: cross-method concordance / stability reason codes. Computed
from Method 1 (pairwise median) and Method 2-primary (fixed_effects_huber)
results plus the direction-split pairs, feeding directly into diagnosis.py's
rule-based classification (never a hidden severity blend).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .pairs import valid_pairs
from .robust_stats import weighted_median

DOMINANT_GROUP_FRACTION_THRESHOLD = 0.45
LOGO_INSTABILITY_THRESHOLD = 0.5
CI_WIDTH_ABSOLUTE_THRESHOLD_C_PER_MIN = 0.5
CI_WIDTH_RELATIVE_MULTIPLE = 4.0
METHOD_AGREEMENT_SIGN_TOLERANCE_C_PER_MIN = 0.005  # trends smaller than this are treated as "no direction" for sign comparison
MIN_PAIRS_PER_DIRECTION_FOR_CHECK = 3
DIRECTION_SLOPE_DISAGREEMENT_C_PER_MIN = 0.05


def _sign_or_zero(x: float, tolerance: float) -> int:
    if pd.isna(x) or abs(x) < tolerance:
        return 0
    return 1 if x > 0 else -1


def methods_agree(method1: dict, method2_primary: dict) -> str:
    t1, t2 = method1.get("trend_c_per_min"), method2_primary.get("trend_c_per_min")
    if pd.isna(t1) or pd.isna(t2):
        return "METHODS_DISAGREE"  # cannot confirm agreement without both estimates
    s1 = _sign_or_zero(t1, METHOD_AGREEMENT_SIGN_TOLERANCE_C_PER_MIN)
    s2 = _sign_or_zero(t2, METHOD_AGREEMENT_SIGN_TOLERANCE_C_PER_MIN)
    return "METHODS_AGREE" if s1 == s2 else "METHODS_DISAGREE"


def is_dominated_by_single_location(method2_primary: dict) -> bool:
    frac = method2_primary.get("dominant_group_fraction")
    return bool(pd.notna(frac) and frac > DOMINANT_GROUP_FRACTION_THRESHOLD)


def is_leave_one_group_out_unstable(method2_primary: dict) -> bool:
    stability = method2_primary.get("leave_one_group_out_stability")
    return bool(pd.notna(stability) and stability > LOGO_INSTABILITY_THRESHOLD)


def is_ci_too_wide(method2_primary: dict) -> bool:
    low, high, trend = method2_primary.get("confidence_interval_low"), method2_primary.get("confidence_interval_high"), method2_primary.get("trend_c_per_min")
    if pd.isna(low) or pd.isna(high):
        return True  # no bootstrap CI computed at all (below the minimum-groups floor) counts as non-informative
    width = high - low
    if width > CI_WIDTH_ABSOLUTE_THRESHOLD_C_PER_MIN:
        return True
    if pd.notna(trend) and abs(trend) > 1e-9 and width > CI_WIDTH_RELATIVE_MULTIPLE * abs(trend):
        return True
    return False


def direction_consistency_from_pairs(pairs: pd.DataFrame) -> str:
    """same_direction vs opposite_direction valid-pair slopes -- 'consistent',
    'dependent' (disagree beyond tolerance), or 'not_testable' (insufficient
    pairs in one or both subsets).
    """
    vp = valid_pairs(pairs)
    same = vp[vp["direction_relation"] == "same_direction"]
    opp = vp[vp["direction_relation"] == "opposite_direction"]
    if len(same) < MIN_PAIRS_PER_DIRECTION_FOR_CHECK or len(opp) < MIN_PAIRS_PER_DIRECTION_FOR_CHECK:
        return "not_testable"
    slope_same = weighted_median(same["pairwise_slope_c_per_min"].to_numpy(dtype=float), same["pair_weight"].to_numpy(dtype=float))
    slope_opp = weighted_median(opp["pairwise_slope_c_per_min"].to_numpy(dtype=float), opp["pair_weight"].to_numpy(dtype=float))
    if pd.isna(slope_same) or pd.isna(slope_opp):
        return "not_testable"
    if abs(slope_same - slope_opp) > DIRECTION_SLOPE_DISAGREEMENT_C_PER_MIN:
        return "dependent"
    return "consistent"


def compute_uncertainty_flags(method1: dict, method2_primary: dict, pairs: pd.DataFrame) -> dict:
    agreement = methods_agree(method1, method2_primary)
    dominant = is_dominated_by_single_location(method2_primary)
    unstable_logo = is_leave_one_group_out_unstable(method2_primary)
    ci_wide = is_ci_too_wide(method2_primary)
    direction = direction_consistency_from_pairs(pairs)

    reason_codes = []
    reason_codes.append(agreement)
    if dominant:
        reason_codes.append("DOMINATED_BY_SINGLE_LOCATION")
    if direction == "dependent":
        reason_codes.append("DIRECTION_DEPENDENT_RESULT")
    if unstable_logo:
        reason_codes.append("UNSTABLE_LEAVE_ONE_GROUP_OUT")
    if ci_wide:
        reason_codes.append("CI_TOO_WIDE")
    # TREND_ROBUST_ACROSS_SENSITIVITY / TREND_SENSITIVE_TO_MATCHING_RADIUS /
    # TREND_SENSITIVE_TO_QC_PROFILE are computed later, once the sensitivity
    # sweep (sensitivity.py, M10) actually exists -- not decidable from a
    # single configuration's results alone.

    return {
        "method_agreement": agreement, "dominated_by_single_location": dominant,
        "leave_one_group_out_unstable": unstable_logo, "ci_too_wide": ci_wide,
        "direction_consistency": direction,
        "uncertainty_reason_codes": ";".join(c for c in reason_codes if c),
    }
