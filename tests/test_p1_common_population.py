import numpy as np
import pandas as pd

from meteotracker_qc.p1_repeatability import Params
from meteotracker_qc.p1_repeatability import common as cp


def _points(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(4):
        day = f"2026-06-0{c + 1}"
        t0 = pd.Timestamp(f"{day}T10:00:00Z")
        x = np.arange(0, 400, 5.0)
        signal = np.sin(x / 60.0)
        for i, xi in enumerate(x):
            rows.append(dict(campaign=f"c{c}", day=day, t=t0 + pd.Timedelta(seconds=i), T=20 + signal[i] +
                             rng.normal(0, .2), x=xi, y=0.0, alt=50.0 + xi / 100, route="r1", spatial_block_id="b1"))
    return pd.DataFrame(rows)


def test_identical_masks_give_identical_R_and_zero_difference():
    d = _points()
    p = Params(min_pts_pass=10)
    passes = cp.prepare_passes(d, "route", p)
    allk = pd.Series(True, index=d.index)
    masks = {"a": allk, "b": allk.copy()}
    cv = cp.cell_values(passes, masks, "centered", p)
    P, L = cp.common_pairs(passes, "route", cv, list(masks), p)
    st = cp.per_mask_stats(P, L, list(masks))
    C = cp.compare_masks(st, "a", 200, 1)
    assert len(P) == 6  # 4 campaigns -> 6 diff-day pairs
    assert C.R.iloc[0] == C.R.iloc[1] and abs(C.dR_vs_ref.iloc[1]) < 1e-12
    assert C.R.iloc[0] > 0.5


def test_common_population_drops_cells_missing_in_any_mask():
    d = _points()
    p = Params(min_pts_pass=10)
    passes = cp.prepare_passes(d, "route", p)
    allk = pd.Series(True, index=d.index)
    hole = allk & ~((d.campaign == "c0") & (d.x < 100))  # mask b removes the first 100 m of campaign c0
    cv = cp.cell_values(passes, {"a": allk, "b": hole}, "centered", p)
    P1, L1 = cp.common_pairs(passes, "route", cv, ["a"], p)
    P2, L2 = cp.common_pairs(passes, "route", cv, ["a", "b"], p)
    assert len(L2) < len(L1)
    st = cp.per_mask_stats(P2, L2, ["a", "b"])
    assert (st["a"]["n"].to_numpy() == st["b"]["n"].to_numpy()).all()  # same cells for both masks
    S = cp.pair_count_sensitivity(st, (2, "all"), 5, 50, 3)
    assert set(S["mask"]) == {"a", "b"}
