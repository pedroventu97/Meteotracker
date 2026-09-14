import itertools

import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.trend_methods import (
    MIN_GROUPS_FOR_BOOTSTRAP, demean_by_group, fixed_effects_huber_trend,
    fixed_effects_ols_trend, fixed_effects_theilsen_trend, prepare_model_visits,
)

T0 = pd.Timestamp("2026-02-13T09:00:00Z")


def _visits(rows):
    """rows: list of (group_id, offset_seconds, temp, qc_status)."""
    return pd.DataFrame([
        {
            "repeated_location_group_id": g, "repeated_location_visit_id": f"{g}_{i}",
            "visit_representative_timestamp": T0 + pd.Timedelta(seconds=t),
            "visit_representative_temperature_c": temp, "visit_qc_status": qc,
        }
        for i, (g, t, temp, qc) in enumerate(rows)
    ])


def _pairs(visits, min_sep_s=300.0):
    """Minimal synthetic pairs frame: every combinatorial pair within a
    group, VALID iff the two visits are >= min_sep_s apart in time (mirrors
    pairs.py's EXCLUDED_INSUFFICIENT_TEMPORAL_SEPARATION criterion, without
    needing the full lat/lon/segment scaffolding build_pairs() requires).
    Rows with a missing/invalid (NaT) timestamp on either side can never
    satisfy the separation floor and are always EXCLUDED, matching
    time_diff_s coming out as NaN (NaN < threshold is always False in
    pandas/numpy, so this needs an explicit isna check here).
    """
    rows = []
    for gid, g in visits.groupby("repeated_location_group_id"):
        g = g.sort_values("visit_representative_timestamp", na_position="last").reset_index(drop=True)
        ids = g["repeated_location_visit_id"].tolist()
        times = g["visit_representative_timestamp"].tolist()
        for i, j in itertools.combinations(range(len(ids)), 2):
            ti, tj = times[i], times[j]
            if pd.isna(ti) or pd.isna(tj):
                status = "EXCLUDED"
            else:
                dt = (tj - ti).total_seconds()
                status = "VALID" if dt >= min_sep_s else "EXCLUDED"
            rows.append({"visit_id_earlier": ids[i], "visit_id_later": ids[j], "pair_qc_status": status})
    return pd.DataFrame(rows, columns=["visit_id_earlier", "visit_id_later", "pair_qc_status"])


def test_prepare_model_visits_drops_low_quality_and_singleton_groups():
    rows = [("g1", 0, 10.0, "OK"), ("g1", 600, 10.5, "OK"), ("g2", 0, 11.0, "LOW_POINT_COUNT"), ("g3", 0, 12.0, "OK")]
    visits = _visits(rows)
    out = prepare_model_visits(visits, _pairs(visits))
    assert set(out["repeated_location_group_id"]) == {"g1"}


def test_known_positive_within_group_trend_recovered():
    rows = []
    for gi in range(6):
        rows.append((f"g{gi}", 0, 10.0 + gi * 3.0, "OK"))       # large static offset per group
        rows.append((f"g{gi}", 1200, 10.0 + gi * 3.0 + 1.0, "OK"))  # +1C after 1200s within EACH group -> 0.05 C/min
    visits = _visits(rows)
    out = fixed_effects_huber_trend(visits, _pairs(visits), T0, random_state=1)
    assert out["trend_c_per_min"] == pytest.approx(0.05, abs=0.005)


def test_known_negative_within_group_trend_recovered():
    rows = []
    for gi in range(6):
        rows.append((f"g{gi}", 0, 10.0 + gi * 3.0, "OK"))
        rows.append((f"g{gi}", 1200, 10.0 + gi * 3.0 - 1.0, "OK"))
    visits = _visits(rows)
    out = fixed_effects_huber_trend(visits, _pairs(visits), T0, random_state=1)
    assert out["trend_c_per_min"] < 0


def test_static_spatial_offset_alone_never_produces_a_spurious_trend():
    # The core justification for the within-estimator: group A is always
    # visited early and is much cooler (10C), group B is always visited late
    # and much warmer (20C) -- a NAIVE pooled regression on raw (t, T)
    # without demeaning would show a large apparent trend purely from this
    # confound, even though neither group individually has ANY internal
    # time-temperature relationship.
    rows = [
        ("A", 0, 10.0, "OK"), ("A", 300, 10.0, "OK"), ("A", 600, 10.0, "OK"),
        ("B", 3000, 20.0, "OK"), ("B", 3300, 20.0, "OK"), ("B", 3600, 20.0, "OK"),
    ]
    visits = _visits(rows)

    naive_t = (visits["visit_representative_timestamp"] - T0).dt.total_seconds().to_numpy()
    naive_T = visits["visit_representative_temperature_c"].to_numpy()
    naive_slope_per_s = np.polyfit(naive_t, naive_T, 1)[0]
    assert naive_slope_per_s * 60 > 0.1, "sanity check: the confound really would look like a strong trend without demeaning"

    pairs = _pairs(visits)
    out_ols = fixed_effects_ols_trend(visits, pairs, T0)
    out_huber = fixed_effects_huber_trend(visits, pairs, T0, random_state=1)
    assert out_ols["trend_c_per_min"] == pytest.approx(0.0, abs=1e-9)
    assert out_huber["trend_c_per_min"] == pytest.approx(0.0, abs=1e-9)


def test_demean_by_group_produces_zero_group_means():
    rows = [("g1", 0, 10.0, "OK"), ("g1", 600, 12.0, "OK"), ("g2", 0, 20.0, "OK"), ("g2", 300, 22.0, "OK")]
    visits = _visits(rows)
    demeaned = demean_by_group(prepare_model_visits(visits, _pairs(visits)), T0)
    group_means = demeaned.groupby("repeated_location_group_id")["T_demeaned"].mean()
    assert np.allclose(group_means.to_numpy(), 0.0, atol=1e-9)


def test_outlier_visit_handled_more_robustly_by_huber_than_ols():
    rows = []
    for gi in range(6):
        rows.append((f"g{gi}", 0, 10.0, "OK"))
        rows.append((f"g{gi}", 1200, 10.05, "OK"))  # tiny real trend, ~0.0025 C/min
    rows.append(("g_outlier", 0, 10.0, "OK"))
    rows.append(("g_outlier", 1200, 60.0, "OK"))  # wild outlier group
    visits = _visits(rows)
    pairs = _pairs(visits)
    out_ols = fixed_effects_ols_trend(visits, pairs, T0)
    out_huber = fixed_effects_huber_trend(visits, pairs, T0, random_state=1)
    assert abs(out_huber["trend_c_per_min"]) < abs(out_ols["trend_c_per_min"]), "Huber must be pulled toward the outlier less than plain OLS"


def test_dominant_group_fraction_high_when_one_group_has_most_visits():
    rows = [("dominant", i * 100, 10.0 + i * 0.01, "OK") for i in range(10)]
    rows += [("g1", 0, 11.0, "OK"), ("g1", 600, 11.1, "OK")]
    visits = _visits(rows)
    out = fixed_effects_huber_trend(visits, _pairs(visits), T0, random_state=1)
    assert out["dominant_group_fraction"] > 0.7


def test_theilsen_insufficient_support_below_minimum_pooled_visits():
    rows = [("g1", 0, 10.0, "OK"), ("g1", 600, 11.0, "OK")]
    visits = _visits(rows)
    out = fixed_effects_theilsen_trend(visits, _pairs(visits), T0)
    assert np.isnan(out["trend_c_per_min"])


def test_theilsen_recovers_trend_with_enough_pooled_visits():
    rows = []
    for gi in range(4):
        rows.append((f"g{gi}", 0, 10.0 + gi, "OK"))
        rows.append((f"g{gi}", 1200, 10.0 + gi + 1.0, "OK"))
    visits = _visits(rows)
    out = fixed_effects_theilsen_trend(visits, _pairs(visits), T0)
    assert out["trend_c_per_min"] == pytest.approx(0.05, abs=0.01)


def test_bootstrap_ci_below_floor_is_nan_for_fixed_effects_too():
    rows = []
    for gi in range(MIN_GROUPS_FOR_BOOTSTRAP - 3):
        rows.append((f"g{gi}", 0, 10.0, "OK"))
        rows.append((f"g{gi}", 600, 10.5, "OK"))
    visits = _visits(rows)
    out = fixed_effects_huber_trend(visits, _pairs(visits), T0, random_state=1)
    assert np.isnan(out["confidence_interval_low"])


def test_empty_visits_yields_empty_result():
    empty_visits = pd.DataFrame(columns=["repeated_location_group_id", "repeated_location_visit_id", "visit_representative_timestamp", "visit_representative_temperature_c", "visit_qc_status"])
    empty_pairs = pd.DataFrame(columns=["visit_id_earlier", "visit_id_later", "pair_qc_status"])
    out = fixed_effects_huber_trend(empty_visits, empty_pairs, T0)
    assert np.isnan(out["trend_c_per_min"])


# ============================================================
# Method 2 hardening: minimum temporal separation floor, shared with
# Method 1 via the visit's participation in a temporally-valid pair
# (see _visits_with_valid_pair in trend_methods.py).
# ============================================================

def test_visits_separated_less_than_threshold_are_dropped_from_the_model():
    # Two visits in the same group only 100s apart, threshold 300s: neither
    # visit has a valid same-group pair, so the whole group must vanish from
    # Method 2's pooled input (not just have its pair excluded, since Method
    # 2 has no pair-level exclusion mechanism of its own).
    rows = [("g1", 0, 10.0, "OK"), ("g1", 100, 10.2, "OK"), ("g2", 0, 12.0, "OK"), ("g2", 500, 12.5, "OK")]
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    out = prepare_model_visits(visits, pairs)
    assert set(out["repeated_location_group_id"]) == {"g2"}


def test_visits_separated_exactly_at_threshold_are_kept():
    # Exactly at the floor (not strictly below it) must count as valid,
    # matching pairs.py's strict "<" exclusion condition.
    rows = [("g1", 0, 10.0, "OK"), ("g1", 300, 10.5, "OK")]
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    out = prepare_model_visits(visits, pairs)
    assert set(out["repeated_location_group_id"]) == {"g1"}
    assert len(out) == 2


def test_visits_separated_beyond_threshold_are_kept():
    rows = [("g1", 0, 10.0, "OK"), ("g1", 900, 11.0, "OK")]
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    out = prepare_model_visits(visits, pairs)
    assert set(out["repeated_location_group_id"]) == {"g1"}


def test_unordered_timestamps_still_correctly_evaluated():
    # The later visit appears first in the input frame; the separation
    # decision must depend on actual elapsed time, not row order.
    rows = [("g1", 900, 11.0, "OK"), ("g1", 0, 10.0, "OK")]
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    out = prepare_model_visits(visits, pairs)
    assert set(out["repeated_location_group_id"]) == {"g1"}
    assert len(out) == 2


def test_missing_timestamp_visit_excluded_without_crash():
    rows = [("g1", 0, 10.0, "OK"), ("g1", 900, 11.0, "OK")]
    visits = _visits(rows)
    visits.loc[len(visits)] = {
        "repeated_location_group_id": "g1", "repeated_location_visit_id": "g1_bad",
        "visit_representative_timestamp": pd.NaT, "visit_representative_temperature_c": 10.5,
        "visit_qc_status": "OK",
    }
    pairs = _pairs(visits, min_sep_s=300.0)
    out = prepare_model_visits(visits, pairs)
    # The two well-separated real visits remain usable; the NaT visit never
    # forms a valid pair with anything and is dropped, not crashed on.
    assert "g1_bad" not in set(out["repeated_location_visit_id"])
    assert set(out["repeated_location_visit_id"]) == {"g1_0", "g1_1"}


def test_multiple_visits_in_same_group_only_temporally_supported_ones_kept():
    # Three visits: A-B are 100s apart (too close), A-C and B-C are >=300s
    # apart (valid). A and B each still have a valid partner (C), so all
    # three visits should be retained -- Method 2 drops individual
    # UNSUPPORTED visits, not whole groups, whenever at least one temporally
    # valid pair anchors them.
    rows = [("g1", 0, 10.0, "OK"), ("g1", 100, 10.1, "OK"), ("g1", 400, 10.4, "OK")]
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    out = prepare_model_visits(visits, pairs)
    assert set(out["repeated_location_visit_id"]) == {"g1_0", "g1_1", "g1_2"}


def test_multiple_visits_middle_one_dropped_when_isolated_in_time():
    # A(0), B(150), C(400): A-B too close (150s), B-C too close (250s), A-C
    # valid (400s). B has no valid partner at all and must be dropped, while
    # A and C remain (they support each other).
    rows = [("g1", 0, 10.0, "OK"), ("g1", 150, 10.1, "OK"), ("g1", 400, 10.4, "OK")]
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    out = prepare_model_visits(visits, pairs)
    assert set(out["repeated_location_visit_id"]) == {"g1_0", "g1_2"}


def test_filter_eliminates_all_pairs_yields_empty_model_and_nan_trend():
    rows = [("g1", 0, 10.0, "OK"), ("g1", 50, 10.1, "OK"), ("g2", 0, 12.0, "OK"), ("g2", 60, 12.1, "OK")]
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    prepared = prepare_model_visits(visits, pairs)
    assert prepared.empty
    out = fixed_effects_huber_trend(visits, pairs, T0, random_state=1)
    assert np.isnan(out["trend_c_per_min"])
    assert out["n_visits"] == len(visits)  # n_visits_total is still reported, only the model input is empty


def test_method1_stays_valid_while_method2_becomes_not_assessable():
    # A single group whose two visits are 100s apart: Method 1 builds the
    # pair regardless (kept with EXCLUDED status, but pairwise_median_trend
    # only needs pair rows to exist -- here we simulate the "Method 1 has
    # other valid data elsewhere" scenario directly by checking Method 2 in
    # isolation collapses to NaN while the pair-level table a Method-1 caller
    # would use still reflects the real underlying data, not a crash.
    from meteotracker_qc.temporal_drift.trend_methods import pairwise_median_trend

    close_rows = [("g1", 0, 10.0, "OK"), ("g1", 100, 10.1, "OK")]
    close_visits = _visits(close_rows)
    close_pairs = _pairs(close_visits, min_sep_s=300.0)  # both pairs excluded -> Method 2 empty

    far_rows = [("g1", 0, 10.0, "OK"), ("g1", 400, 10.4, "OK")]
    far_visits = _visits(far_rows)
    far_pairs = _pairs(far_visits, min_sep_s=300.0)
    far_pairs["pairwise_slope_c_per_min"] = [(10.4 - 10.0) / (400 / 60.0)]
    far_pairs["pair_weight"] = [1.0]
    far_pairs["repeated_location_group_id"] = ["g1"]

    method2_close = fixed_effects_huber_trend(close_visits, close_pairs, T0, random_state=1)
    method1_far = pairwise_median_trend(far_pairs, n_visits_total=len(far_visits))

    assert np.isnan(method2_close["trend_c_per_min"])
    assert not np.isnan(method1_far["trend_c_per_min"])


def test_both_methods_remain_valid_with_adequately_separated_revisits():
    from meteotracker_qc.temporal_drift.trend_methods import pairwise_median_trend

    rows = []
    for gi in range(6):
        rows.append((f"g{gi}", 0, 10.0 + gi * 2.0, "OK"))
        rows.append((f"g{gi}", 900, 10.0 + gi * 2.0 + 0.5, "OK"))
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    pairs["pairwise_slope_c_per_min"] = 0.5 / (900 / 60.0)
    pairs["pair_weight"] = 1.0
    pairs["repeated_location_group_id"] = [f"g{i}" for i in range(6)]

    method1 = pairwise_median_trend(pairs, n_visits_total=len(visits))
    method2 = fixed_effects_huber_trend(visits, pairs, T0, random_state=1)

    assert not np.isnan(method1["trend_c_per_min"])
    assert not np.isnan(method2["trend_c_per_min"])


def test_hardening_does_not_change_prepare_model_visits_for_well_separated_real_shaped_data():
    # Regression guard: sessions whose real revisits are comfortably beyond
    # the separation floor (the common real-data case per the 34-campaign
    # audit) must produce IDENTICAL model input before/after hardening --
    # the filter only ever removes visits that were already too close.
    rows = []
    for gi in range(10):
        rows.append((f"g{gi}", 0, 10.0 + gi, "OK"))
        rows.append((f"g{gi}", 3600, 11.0 + gi, "OK"))
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    out = prepare_model_visits(visits, pairs)
    assert len(out) == len(visits)
    assert set(out["repeated_location_visit_id"]) == set(visits["repeated_location_visit_id"])
