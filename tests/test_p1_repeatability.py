import numpy as np
import pandas as pd

from meteotracker_qc.p1_repeatability import Params, bootstrap_pooled, build_passes, icc_oneway, pass_pairs, pooled


def _synthetic(signal=1.0, noise=0.1, n_camp=5, seed=0):
    rng = np.random.default_rng(seed)
    xs = np.arange(0, 1000, 5.0)  # 200 points along a 1 km straight line, 5 m apart
    prof = signal * np.sin(xs / 120.0)
    rows = []
    for c in range(n_camp):
        t0 = pd.Timestamp("2026-06-01T08:00Z") + pd.Timedelta(days=c)
        for rep in range(2):  # two passes per campaign, 30 min apart (same campaign)
            ts = t0 + pd.to_timedelta(rep * 1800 + np.arange(len(xs)), unit="s")
            T = 20 + c + prof + rng.normal(0, noise, len(xs))
            rows.append(pd.DataFrame(dict(campaign=f"c{c}", day=str(t0.date()), t=ts, T=T, x=680000 + xs,
                                          y=4920000.0, route="cv2_x", spatial_block_id="1360_9840", alt=50.0)))
    return pd.concat(rows, ignore_index=True)


def test_repeatable_signal_gives_high_R_and_types():
    p = Params(n_boot=200)
    d = _synthetic()
    ps = build_passes(d, "route", p)
    assert ps.pass_id.nunique() == 10
    P, L = pass_pairs(ps, "route", "centered", p)
    assert set(P.pair_type) == {"same_campaign", "diff_day"}
    assert (P.pair_type == "same_campaign").sum() == 5
    o = pooled(P[P.pair_type == "diff_day"])
    assert o["R"] > 0.9 and o["n_campaigns"] == 5
    b = bootstrap_pooled(P[P.pair_type == "diff_day"], 200, np.random.default_rng(1))
    assert b["R_ci"][0] > 0.8 and not b["R_ci_includes_0"]


def test_noise_only_gives_R_near_zero():
    p = Params(n_boot=200)
    d = _synthetic(signal=0.0, noise=0.5, n_camp=6, seed=3)
    P, _ = pass_pairs(build_passes(d, "route", p), "route", "centered", p)
    o = pooled(P[P.pair_type == "diff_day"])
    assert abs(o["R"]) < 0.2


def test_icc_oneway():
    cells = pd.DataFrame(dict(loc=np.repeat(list("abcd"), 5), a=np.repeat([1.0, -1.0, 0.5, -0.5], 5)
                              + np.random.default_rng(0).normal(0, 0.05, 20)))
    assert icc_oneway(cells) > 0.95
