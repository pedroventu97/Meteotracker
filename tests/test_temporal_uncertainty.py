import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.uncertainty import (
    compute_uncertainty_flags, direction_consistency_from_pairs, is_ci_too_wide,
    is_dominated_by_single_location, is_leave_one_group_out_unstable, methods_agree,
)


def _m2(trend=0.05, ci_low=0.02, ci_high=0.08, dominant=0.2, logo=0.1):
    return {"trend_c_per_min": trend, "confidence_interval_low": ci_low, "confidence_interval_high": ci_high,
            "dominant_group_fraction": dominant, "leave_one_group_out_stability": logo}


def _m1(trend=0.05):
    return {"trend_c_per_min": trend}


def test_methods_agree_same_sign():
    assert methods_agree(_m1(0.05), _m2(trend=0.06)) == "METHODS_AGREE"


def test_methods_disagree_opposite_sign():
    assert methods_agree(_m1(0.05), _m2(trend=-0.05)) == "METHODS_DISAGREE"


def test_methods_disagree_when_either_is_nan():
    assert methods_agree(_m1(float("nan")), _m2()) == "METHODS_DISAGREE"


def test_dominant_group_flagged_above_threshold():
    assert is_dominated_by_single_location(_m2(dominant=0.6)) is True
    assert is_dominated_by_single_location(_m2(dominant=0.2)) is False


def test_logo_instability_flagged_above_threshold():
    assert is_leave_one_group_out_unstable(_m2(logo=0.8)) is True
    assert is_leave_one_group_out_unstable(_m2(logo=0.1)) is False


def test_ci_too_wide_when_no_bootstrap_computed():
    assert is_ci_too_wide(_m2(ci_low=float("nan"), ci_high=float("nan"))) is True


def test_ci_too_wide_when_width_large_relative_to_trend():
    assert is_ci_too_wide(_m2(trend=0.01, ci_low=-0.5, ci_high=0.5)) is True


def test_ci_not_too_wide_when_narrow_and_informative():
    assert is_ci_too_wide(_m2(trend=0.05, ci_low=0.03, ci_high=0.07)) is False


def _pairs_with_directions(same_slopes, opp_slopes):
    rows = []
    for i, s in enumerate(same_slopes):
        rows.append({"pair_qc_status": "VALID", "direction_relation": "same_direction", "pairwise_slope_c_per_min": s, "pair_weight": 1.0})
    for i, s in enumerate(opp_slopes):
        rows.append({"pair_qc_status": "VALID", "direction_relation": "opposite_direction", "pairwise_slope_c_per_min": s, "pair_weight": 1.0})
    return pd.DataFrame(rows)


def test_direction_consistency_consistent():
    pairs = _pairs_with_directions([0.05, 0.05, 0.05], [0.04, 0.06, 0.05])
    assert direction_consistency_from_pairs(pairs) == "consistent"


def test_direction_consistency_dependent():
    pairs = _pairs_with_directions([0.1, 0.1, 0.1], [-0.1, -0.1, -0.1])
    assert direction_consistency_from_pairs(pairs) == "dependent"


def test_direction_consistency_not_testable_with_too_few_pairs():
    pairs = _pairs_with_directions([0.05], [0.04])
    assert direction_consistency_from_pairs(pairs) == "not_testable"


def test_compute_uncertainty_flags_joins_reason_codes():
    pairs = _pairs_with_directions([0.1, 0.1, 0.1], [-0.1, -0.1, -0.1])
    flags = compute_uncertainty_flags(_m1(0.05), _m2(trend=0.05, dominant=0.6, logo=0.8), pairs)
    codes = flags["uncertainty_reason_codes"].split(";")
    assert "DOMINATED_BY_SINGLE_LOCATION" in codes
    assert "DIRECTION_DEPENDENT_RESULT" in codes
    assert "UNSTABLE_LEAVE_ONE_GROUP_OUT" in codes


def test_compute_uncertainty_flags_clean_case_has_no_extra_codes():
    pairs = _pairs_with_directions([0.05, 0.05], [0.05, 0.05])
    flags = compute_uncertainty_flags(_m1(0.05), _m2(trend=0.05, dominant=0.2, logo=0.1), pairs)
    assert flags["method_agreement"] == "METHODS_AGREE"
    assert flags["dominated_by_single_location"] is False
    assert flags["leave_one_group_out_unstable"] is False
    assert flags["ci_too_wide"] is False
