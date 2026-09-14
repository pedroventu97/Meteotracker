import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.trend_methods import (
    MIN_GROUPS_FOR_BOOTSTRAP, pairwise_median_trend,
)


def _pairs(group_slopes: dict[str, list[float]]) -> pd.DataFrame:
    rows = []
    for gid, slopes in group_slopes.items():
        n_pairs = len(slopes)
        weight = 1.0 / n_pairs
        for i, slope in enumerate(slopes):
            rows.append({
                "repeated_location_group_id": gid, "pair_qc_status": "VALID",
                "pairwise_slope_c_per_min": slope, "pair_weight": weight,
                "visit_id_earlier": f"{gid}_e{i}", "visit_id_later": f"{gid}_l{i}",
            })
    return pd.DataFrame(rows)


def test_empty_pairs_yields_empty_result():
    out = pairwise_median_trend(pd.DataFrame(columns=["repeated_location_group_id", "pair_qc_status", "pairwise_slope_c_per_min", "pair_weight"]))
    assert out["method"] == "pairwise_median"
    assert np.isnan(out["trend_c_per_min"])
    assert out["n_pairs"] == 0


def test_known_positive_trend_recovered():
    pairs = _pairs({f"g{i}": [0.05, 0.06, 0.04] for i in range(10)})
    out = pairwise_median_trend(pairs, random_state=1)
    assert out["trend_c_per_min"] == pytest.approx(0.05, abs=0.02)
    assert out["trend_c_per_hour"] == pytest.approx(out["trend_c_per_min"] * 60)


def test_known_negative_trend_recovered():
    pairs = _pairs({f"g{i}": [-0.05, -0.06, -0.04] for i in range(10)})
    out = pairwise_median_trend(pairs, random_state=1)
    assert out["trend_c_per_min"] < 0


def test_null_trend_near_zero():
    pairs = _pairs({f"g{i}": [0.001, -0.001, 0.0005] for i in range(10)})
    out = pairwise_median_trend(pairs, random_state=1)
    assert abs(out["trend_c_per_min"]) < 0.01


def test_outlier_handled_robustly_by_median():
    slopes_by_group = {f"g{i}": [0.05] for i in range(9)}
    slopes_by_group["g_outlier"] = [50.0]  # one wild outlier group
    pairs = _pairs(slopes_by_group)
    out = pairwise_median_trend(pairs, random_state=1)
    assert out["trend_c_per_min"] == pytest.approx(0.05, abs=0.02), "a single extreme group must not drag the median"


def test_dominant_group_fraction_reflects_weight_concentration():
    # one group has many surviving valid pairs relative to others (unequal
    # weight totals after exclusion), the rest have exactly one pair each.
    pairs = _pairs({"dominant": [0.1] * 5, **{f"g{i}": [0.1] for i in range(5)}})
    # manually inflate the dominant group's weight to simulate unequal survival
    pairs.loc[pairs["repeated_location_group_id"] == "dominant", "pair_weight"] = 1.0
    out = pairwise_median_trend(pairs, random_state=1)
    assert out["dominant_group_fraction"] > 0.4


def test_leave_one_group_out_unstable_at_a_near_tie_split():
    # A median is robust to a MINORITY outlier by design (that's the whole
    # point of using one) -- genuine instability requires a near-50/50 split
    # where removing either side's group flips which value the median lands
    # on. 2 groups at 0.05 vs 2 groups at 5.0 is exactly that near-tie.
    pairs = _pairs({"a1": [0.05], "a2": [0.05], "b1": [5.0], "b2": [5.0]})
    out = pairwise_median_trend(pairs, random_state=1)
    assert out["leave_one_group_out_stability"] > 1.0


def test_leave_one_group_out_stable_for_homogeneous_groups():
    pairs = _pairs({f"g{i}": [0.05 + 0.001 * i] for i in range(9)})
    out = pairwise_median_trend(pairs, random_state=1)
    assert out["leave_one_group_out_stability"] < 0.1


def test_bootstrap_ci_not_computed_below_minimum_groups_floor():
    pairs = _pairs({f"g{i}": [0.05] for i in range(MIN_GROUPS_FOR_BOOTSTRAP - 2)})
    out = pairwise_median_trend(pairs, random_state=1)
    assert np.isnan(out["confidence_interval_low"])
    assert np.isnan(out["confidence_interval_high"])
    assert out["bootstrap_n_valid"] == 0


def test_bootstrap_ci_computed_at_or_above_minimum_groups_floor():
    pairs = _pairs({f"g{i}": [0.05, 0.06] for i in range(MIN_GROUPS_FOR_BOOTSTRAP)})
    out = pairwise_median_trend(pairs, n_bootstrap=200, random_state=1)
    assert not np.isnan(out["confidence_interval_low"])
    assert out["confidence_interval_low"] <= out["trend_c_per_min"] <= out["confidence_interval_high"]
    assert out["bootstrap_n_valid"] == 200


def test_bootstrap_resamples_groups_not_individual_pairs():
    # A group with many pairs vs a group with one pair must each be drawn as
    # a single resampling unit -- verified indirectly: bootstrap CI width
    # should not collapse to near-zero just because one group has lots of
    # (dependent) pairs.
    pairs = _pairs({"big": [0.05] * 20, **{f"g{i}": [0.05 + 0.01 * i] for i in range(9)}})
    out = pairwise_median_trend(pairs, n_bootstrap=300, random_state=2)
    assert out["confidence_interval_high"] - out["confidence_interval_low"] > 0.0
