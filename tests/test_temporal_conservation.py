import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.conservation import compute_conservation_metrics

T0 = pd.Timestamp("2026-02-13T09:00:00Z")


def _detrending_df(raw, detrended, trend):
    n = len(raw)
    return pd.DataFrame({
        "time_utc": [T0 + pd.Timedelta(seconds=i * 60) for i in range(n)],
        "temp_original_c": raw, "temp_detrended_experimental_c": detrended,
        "temporal_trend_candidate_c": trend,
    })


def test_small_uniform_trend_preserves_spatial_pattern():
    # 2 groups with a clear 5C spatial offset; a tiny 0.01C/point adjustment
    # from detrending must not meaningfully disturb that.
    n_per_group = 20
    raw = [10.0 + 0.01 * i for i in range(n_per_group)] + [15.0 + 0.01 * i for i in range(n_per_group)]
    trend = [0.01 * i for i in range(n_per_group)] * 2
    detrended = [r - t for r, t in zip(raw, trend)]
    groups = pd.Series(["A"] * n_per_group + ["B"] * n_per_group)
    df = _detrending_df(raw, detrended, trend)
    out = compute_conservation_metrics(df, groups)
    assert out["correlation_raw_vs_detrended"] > 0.9
    assert "SPATIAL_PATTERN_PRESERVED" in out["conservation_flags"]
    assert out["between_location_variance_ratio"] > 0.9


def test_overdetrending_flagged_when_between_group_variance_collapses():
    # The "detrended" values here have been (artificially, for the test)
    # collapsed to the same value regardless of group -- simulating a
    # detrending step that wrongly absorbed the real spatial signal.
    n_per_group = 20
    raw = [10.0] * n_per_group + [20.0] * n_per_group
    detrended = [15.0] * (2 * n_per_group)  # groups now indistinguishable
    trend = [-5.0] * n_per_group + [5.0] * n_per_group
    groups = pd.Series(["A"] * n_per_group + ["B"] * n_per_group)
    df = _detrending_df(raw, detrended, trend)
    out = compute_conservation_metrics(df, groups)
    assert out["between_location_variance_ratio"] == pytest.approx(0.0, abs=1e-6)
    assert "SPATIAL_CONTRAST_REDUCED_EXCESSIVELY" in out["conservation_flags"]


def test_moderate_contrast_reduction_flagged_as_possible_overdetrending():
    n_per_group = 20
    raw = [10.0] * n_per_group + [20.0] * n_per_group
    # detrended group means moved closer together (contrast reduced to ~60%) but not collapsed
    detrended = [11.0] * n_per_group + [19.0] * n_per_group
    trend = [-1.0] * n_per_group + [1.0] * n_per_group
    groups = pd.Series(["A"] * n_per_group + ["B"] * n_per_group)
    df = _detrending_df(raw, detrended, trend)
    out = compute_conservation_metrics(df, groups)
    assert 0.5 < out["between_location_variance_ratio"] < 0.7
    assert "POSSIBLE_OVERDETRENDING" in out["conservation_flags"]


def test_large_adjustment_flagged():
    raw = [10.0] * 10
    trend = [3.0] * 10  # exceeds the 2.0C large-adjustment threshold
    detrended = [r - t for r, t in zip(raw, trend)]
    groups = pd.Series(["A"] * 10)
    df = _detrending_df(raw, detrended, trend)
    out = compute_conservation_metrics(df, groups)
    assert out["max_absolute_adjustment_c"] == pytest.approx(3.0)
    assert "LARGE_EXPERIMENTAL_ADJUSTMENT" in out["conservation_flags"]


def test_adjustment_fraction_thresholds_computed_correctly():
    trend = [0.05, 0.15, 0.3, 0.6, 0.05]
    raw = [10.0] * 5
    detrended = [r - t for r, t in zip(raw, trend)]
    groups = pd.Series(["A"] * 5)
    df = _detrending_df(raw, detrended, trend)
    out = compute_conservation_metrics(df, groups)
    assert out["fraction_of_points_with_adjustment_gt_0_1c"] == pytest.approx(3 / 5)
    assert out["fraction_of_points_with_adjustment_gt_0_25c"] == pytest.approx(2 / 5)
    assert out["fraction_of_points_with_adjustment_gt_0_5c"] == pytest.approx(1 / 5)


def test_no_group_data_gives_nan_variance_ratios_gracefully():
    raw = [10.0, 10.5, 11.0]
    trend = [0.1, 0.1, 0.1]
    detrended = [r - t for r, t in zip(raw, trend)]
    df = _detrending_df(raw, detrended, trend)
    out = compute_conservation_metrics(df, pd.Series([], dtype=object))
    assert np.isnan(out["between_location_variance_ratio"])
    assert np.isnan(out["within_location_variance_ratio"])
