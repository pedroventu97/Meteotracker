import itertools

import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.nonlinear import (
    MIN_DURATION_S_FOR_NONLINEAR, MIN_GROUPS_FOR_NONLINEAR, evaluate_nonlinear_candidate,
    is_nonlinear_eligible,
)

T0 = pd.Timestamp("2026-02-13T09:00:00Z")


def _visits(rows, direction=None):
    out = []
    for i, (g, t, temp, qc) in enumerate(rows):
        row = {
            "repeated_location_group_id": g, "repeated_location_visit_id": f"{g}_{i}",
            "visit_representative_timestamp": T0 + pd.Timedelta(seconds=t),
            "visit_representative_temperature_c": temp, "visit_qc_status": qc,
            "visit_direction_class": "same_direction",
        }
        out.append(row)
    return pd.DataFrame(out)


def _pairs(visits, min_sep_s=300.0):
    """Same minimal synthetic-pairs helper as test_temporal_trend_fixed_effects.py."""
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


def test_eligibility_requires_enough_groups_windows_and_duration():
    assert not is_nonlinear_eligible(2, 4, 5000.0)
    assert not is_nonlinear_eligible(6, 1, 5000.0)
    assert not is_nonlinear_eligible(6, 4, 100.0)
    assert is_nonlinear_eligible(6, 4, 5000.0)


def test_not_attempted_with_too_few_groups():
    rows = [(f"g{i}", t, 10.0, "OK") for i in range(3) for t in (0, 600)]
    visits = _visits(rows)
    out = evaluate_nonlinear_candidate(visits, _pairs(visits), T0, n_groups_valid=3, n_time_windows=4, nominal_time_span_s=5000.0)
    assert out["temporal_model_form"] == "INSUFFICIENT_SUPPORT"


def test_not_attempted_with_too_few_time_windows():
    rows = [(f"g{i}", t, 10.0, "OK") for i in range(MIN_GROUPS_FOR_NONLINEAR + 1) for t in (0, 600)]
    visits = _visits(rows)
    out = evaluate_nonlinear_candidate(visits, _pairs(visits), T0, n_groups_valid=MIN_GROUPS_FOR_NONLINEAR + 1, n_time_windows=1, nominal_time_span_s=5000.0)
    assert out["temporal_model_form"] == "INSUFFICIENT_SUPPORT"


def test_not_attempted_with_too_short_duration():
    rows = [(f"g{i}", t, 10.0, "OK") for i in range(MIN_GROUPS_FOR_NONLINEAR + 1) for t in (0, 600)]
    visits = _visits(rows)
    out = evaluate_nonlinear_candidate(visits, _pairs(visits), T0, n_groups_valid=MIN_GROUPS_FOR_NONLINEAR + 1, n_time_windows=4, nominal_time_span_s=100.0)
    assert out["temporal_model_form"] == "INSUFFICIENT_SUPPORT"


def test_empty_visits_gives_none_form():
    empty_visits = pd.DataFrame(columns=["repeated_location_group_id", "visit_representative_timestamp", "visit_representative_temperature_c", "visit_qc_status"])
    empty_pairs = pd.DataFrame(columns=["visit_id_earlier", "visit_id_later", "pair_qc_status"])
    out = evaluate_nonlinear_candidate(empty_visits, empty_pairs, T0, 10, 4, 5000.0)
    assert out["temporal_model_form"] == "NONE"


def test_linear_preferred_when_no_real_curvature():
    rows = []
    n_groups = 8
    for gi in range(n_groups):
        base = 10.0 + gi * 2.0
        rows.append((f"g{gi}", 0, base, "OK"))
        rows.append((f"g{gi}", 900, base + 0.5, "OK"))
        rows.append((f"g{gi}", 1800, base + 1.0, "OK"))  # perfectly linear within each group
    visits = _visits(rows)
    out = evaluate_nonlinear_candidate(visits, _pairs(visits), T0, n_groups_valid=n_groups, n_time_windows=3, nominal_time_span_s=1800.0 * 2)
    assert out["temporal_model_form"] == "LINEAR"


def test_nonlinear_candidate_accepted_with_clear_quadratic_pattern_and_enough_support():
    rows = []
    n_groups = 8
    for gi in range(n_groups):
        base = 10.0 + gi * 2.0
        for t_s in (0, 900, 1800, 2700):
            # quadratic within-group shape: accelerating rise
            t_hr = t_s / 3600.0
            rows.append((f"g{gi}", t_s, base + 3.0 * t_hr ** 2, "OK"))
    visits = _visits(rows)
    out = evaluate_nonlinear_candidate(visits, _pairs(visits), T0, n_groups_valid=n_groups, n_time_windows=4, nominal_time_span_s=2700.0)
    assert out["temporal_model_form"] == "NONLINEAR_CANDIDATE"
    assert out["nonlinear_cv_improvement_fraction"] > 0


def test_direction_disagreement_downgrades_to_linear_even_with_cv_improvement():
    rows_same, rows_opp = [], []
    n_groups = 8
    for gi in range(n_groups):
        base = 10.0 + gi * 2.0
        for t_s in (0, 900, 1800, 2700):
            t_hr = t_s / 3600.0
            rows_same.append((f"g{gi}s", t_s, base + 3.0 * t_hr ** 2, "OK"))
            rows_opp.append((f"g{gi}o", t_s, base - 3.0 * t_hr ** 2, "OK"))  # opposite-sign curvature
    visits_same = _visits(rows_same)
    visits_opp = _visits(rows_opp)
    visits_opp["visit_direction_class"] = "opposite_direction"
    visits = pd.concat([visits_same, visits_opp], ignore_index=True)
    out = evaluate_nonlinear_candidate(visits, _pairs(visits), T0, n_groups_valid=2 * n_groups, n_time_windows=4, nominal_time_span_s=2700.0)
    assert out["nonlinear_direction_consistent"] is False
    assert out["temporal_model_form"] != "NONLINEAR_CANDIDATE"


# ---- Method 2 hardening: the nonlinear candidate shares prepare_model_visits ----

def test_nonlinear_visits_too_close_in_time_excluded_from_quadratic_fit():
    # Same shape as the accepted-quadratic-candidate test, but every visit's
    # revisit partner in its group is now only 100s away (below the 300s
    # floor) -- prepare_model_visits must empty every group out, so the
    # candidate can never reach NONLINEAR_CANDIDATE from this data.
    rows = []
    n_groups = 8
    for gi in range(n_groups):
        base = 10.0 + gi * 2.0
        for t_s in (0, 60, 120, 180):  # max pairwise gap 180s, all below the 300s floor
            t_hr = t_s / 3600.0
            rows.append((f"g{gi}", t_s, base + 3.0 * t_hr ** 2, "OK"))
    visits = _visits(rows)
    pairs = _pairs(visits, min_sep_s=300.0)
    # nominal_time_span_s/n_time_windows are passed independently of the
    # visit offsets above (they describe the whole session, not this
    # cluster) so eligibility gating passes and the assertion isolates the
    # effect of the temporal-separation filter, not the duration gate.
    out = evaluate_nonlinear_candidate(visits, pairs, T0, n_groups_valid=n_groups, n_time_windows=4, nominal_time_span_s=2700.0)
    assert out["temporal_model_form"] == "INSUFFICIENT_SUPPORT"
