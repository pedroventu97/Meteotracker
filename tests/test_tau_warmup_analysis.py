"""Tests for the e0 skeleton tau_warmup_analysis.py (synthetic data only; no field data exist yet)."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("tau_warmup_analysis", ROOT / "e0" / "tau_warmup_analysis.py")
ta = importlib.util.module_from_spec(_spec)
sys.modules["tau_warmup_analysis"] = ta
_spec.loader.exec_module(ta)


def _step(tau, n=1200, t_step=120, a=20.0, b=10.0, bias=0.3, quant=True, seed=0):
    t = np.arange(n, dtype=float)
    ref = np.where(t < t_step, a, b) + np.random.default_rng(seed).normal(0, 0.01, n)
    y, _ = ta._filt(ref, tau); y = y + (a - y[0]) * math.exp(-1 / tau) ** t   # start in equilibrium at a
    mt = y + bias
    return t, ref, (np.round(mt, 1) if quant else mt)


@pytest.mark.parametrize("tau", [8.0, 25.0, 43.0])
def test_fit_recovers_tau_from_quantized_step(tau):
    t, ref, mt = _step(tau)
    f = ta.fit_first_order(mt, ref, n_boot=30)
    assert abs(f.tau_s - tau) <= max(1.5, 0.08 * tau)
    assert f.tau_ci95_s[0] <= f.tau_s <= f.tau_ci95_s[1]
    assert abs(f.bias_c - 0.3) < 0.06


def test_fit_detects_delay():
    t, ref, mt = _step(20.0, quant=False)
    mt_d = np.concatenate([np.full(3, mt[0]), mt[:-3]])
    f = ta.fit_first_order(mt_d, ref, n_boot=0)
    assert f.delay_s == 3 and abs(f.tau_s - 20.0) <= 1.0


def test_time_to_stability_matches_exponential():
    t = np.arange(0, 1600, 1.0)
    for tau, b in [(60.0, 2.0), (120.0, 1.0)]:
        err = 0.4 + b * np.exp(-t / tau)
        expected = tau * math.log(b / 0.2)
        got = ta.time_to_stability(t, err, 0.2)
        assert expected - 10 <= got <= expected + 10


def test_time_to_stability_edge_cases():
    t = np.arange(0, 1600, 1.0)
    assert ta.time_to_stability(t, np.full_like(t, 0.5), 0.2) == 0.0
    e = np.zeros_like(t); e[(t >= 890) & (t < 900)] = 1.0
    assert ta.time_to_stability(t, e, 0.2) == math.inf
    with pytest.raises(ValueError):
        ta.time_to_stability(np.arange(0, 1000, 1.0), np.zeros(1000), 0.2)


def test_ucb_matches_table():
    assert round(ta.ucb95_one_sided(0, 20), 3) == 0.139
    assert round(ta.ucb95_one_sided(1, 30), 3) == 0.149
    assert round(ta.ucb95_one_sided(2, 30), 3) == 0.195


def _groups(cold, n_i=10, n_w=10, val=50.0):
    return np.asarray(cold, float), np.full(n_i, val), np.full(n_w, val)


def test_decision_selects_300_when_all_fast_but_physics_bounds():
    c, i, w = _groups([200.0] * 20)
    d = ta.decide_cap(c, i, w, tau_ucb95_s=40.0, dT0_p95_c=10.0)     # physics bound 40*ln(50)=156 s
    assert d["status"] == "SELECTED" and d["selected_s"] == 300


def test_decision_extend_then_conservative():
    c, i, w = _groups([200.0] * 19 + [400.0])                         # 1/20 > 300: point ok, UCB 0.216 > 0.20
    d1 = ta.decide_cap(c, i, w, tau_ucb95_s=30.0, dT0_p95_c=5.0, phase=1)
    assert d1["status"] == "EXTEND_TO_PHASE_2" and d1["candidate"] == 300
    c2, i, w = _groups([200.0] * 27 + [400.0] * 3)                    # 3/30: point 0.10, UCB 0.239
    d2 = ta.decide_cap(c2, i, w, tau_ucb95_s=30.0, dT0_p95_c=5.0, phase=2)
    assert d2["status"] == "PROVISIONAL_CONSERVATIVE" and d2["selected_s"] == 600


def test_decision_none_and_insufficient():
    c, i, w = _groups([700.0] * 20)
    assert ta.decide_cap(c, i, w, 30.0, 5.0)["status"] == "NONE_PASSES"
    c, i, w = _groups([100.0] * 12)
    assert ta.decide_cap(c, i, w, 30.0, 5.0)["status"] == "INSUFFICIENT_DATA"


def test_decision_cells_block_condition_dependence():
    c, i, w = _groups([100.0] * 20)
    cells = {"sun_bigdT": [100.0, 100.0, 400.0, 400.0, 100.0], "other": [100.0] * 15}
    d = ta.decide_cap(c, i, w, 30.0, 5.0, cells_cold=cells)
    assert d["status"] == "SELECTED" and d["selected_s"] == 600


def test_read_mt_csv_parses_offset_and_missing(tmp_path):
    p = tmp_path / "TAU_FIELD_x_MT.csv"
    p.write_text("Time,Lat,Lon,Temp[°C],Hum[%]\n2026-11-12T08:00:00+01:00,44,11,10.6,63\n"
                 "2026-11-12T08:00:01+01:00,44,11,-,63\n2026-11-12T08:00:02+01:00,44,11,10.5,63\n", encoding="utf-8")
    df = ta.read_mt_csv(p)
    assert len(df) == 2 and str(df.time_utc.iloc[0]) == "2026-11-12 07:00:00+00:00"
    ref = pd.DataFrame({"time_utc": pd.date_range("2026-11-12T07:00:00Z", periods=3, freq="1s"), "temp_c": [10.0, 10.1, 10.2]})
    al = ta.align_to_ref(df, ref, "2026-11-12T07:00:00Z")
    assert list(al.t_s) == [0.0, 1.0, 2.0] and list(al.mt) == [10.6, 10.6, 10.5]