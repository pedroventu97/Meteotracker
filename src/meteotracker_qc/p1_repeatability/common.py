"""P1 on COMMON POPULATIONS (E0-QC-R step G; pre-registered in e0/QC_R_CRITERIA_E0.md).

Passes are defined once on the union population (all points with valid T). A (pass, cell) enters only if EVERY
compared mask keeps >= min_pts_cell points there and yields a finite value; a pass pair enters only with
>= min_common_cells such cells (and a location with >= min_campaigns_loc campaigns). Pair set, cell set and the
campaign-bootstrap weights are therefore identical across masks: differences reflect the masks, not the sample.

Value variants:
  centered   T (centred per pair over common cells, as P1 'centered')
  detrended  T minus a within-pass linear fit vs time, fitted on the mask's kept points (as P1 'detrended')
  detr_alt   residual of T ~ time + altitude, OLS per campaign on the mask's kept points
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .core import Params, _epoch_s, _stat, build_passes, pair_stats_from_long, pair_type

VARIANTS = ("centered", "detrended", "detr_alt")


def _values(d: pd.DataFrame, keep: pd.Series, variant: str, p: Params) -> pd.Series:
    """Per-point value under one mask (NaN where not kept or not computable)."""
    s = d[keep.to_numpy()]
    out = pd.Series(np.nan, index=d.index)
    if s.empty:
        return out
    if variant == "centered":
        out.loc[s.index] = s["T"]
        return out
    if variant == "detrended":
        g = s.groupby("pass_id")
        tm = g["ts"].transform("mean")
        dt = s["ts"] - tm
        Tm = g["T"].transform("mean")
        sxx = (dt * dt).groupby(s["pass_id"]).transform("sum")
        sxy = (dt * (s["T"] - Tm)).groupby(s["pass_id"]).transform("sum")
        slope = np.where(sxx > 0, sxy / sxx.replace(0, np.nan), 0.0)
        dur = g["ts"].transform(lambda x: x.max() - x.min())
        out.loc[s.index] = np.where(dur >= p.min_detr_s, s["T"] - Tm - slope * dt, np.nan)
        return out
    if variant == "detr_alt":
        for _, g in s.groupby("campaign"):
            ok = g["alt"].notna().to_numpy() & g["T"].notna().to_numpy()
            if ok.sum() <= 20 or np.nanstd(g["alt"].to_numpy()[ok]) <= 0:
                continue
            ts = g["ts"].to_numpy()[ok]
            X = np.c_[np.ones(ok.sum()), ts - ts.mean(), g["alt"].to_numpy()[ok]]
            T = g["T"].to_numpy()[ok]
            out.loc[g.index[ok]] = T - X @ np.linalg.lstsq(X, T, rcond=None)[0]
        return out
    raise ValueError(variant)


def cell_values(passes: pd.DataFrame, masks: dict[str, pd.Series], variant: str, p: Params) -> pd.DataFrame:
    """Wide table per (pass_id, cell): n_<m>, v_<m> for every mask, plus loc/campaign/day/route/block."""
    base = passes.groupby(["pass_id", "cell"]).agg(ci=("cell_i", "first"), cj=("cell_j", "first"),
                                                    route=("route", "first")).reset_index()
    for m, keep in masks.items():
        v = _values(passes, keep.reindex(passes.index).fillna(False).astype(bool), variant, p)
        tmp = pd.DataFrame({"pass_id": passes["pass_id"], "cell": passes["cell"], "v": v})
        agg = tmp.dropna(subset=["v"]).groupby(["pass_id", "cell"])["v"].agg(["mean", "size"]).reset_index()
        agg = agg.rename(columns={"mean": f"v_{m}", "size": f"n_{m}"})
        base = base.merge(agg, on=["pass_id", "cell"], how="left")
    return base


def common_pairs(passes: pd.DataFrame, loc_col: str, cv: pd.DataFrame, mask_names, p: Params):
    """Pairs + long table on the common (pass, cell) set for `mask_names`."""
    ok = np.ones(len(cv), dtype=bool)
    for m in mask_names:
        ok &= (cv[f"n_{m}"].fillna(0) >= p.min_pts_cell).to_numpy() & np.isfinite(cv[f"v_{m}"].to_numpy(dtype=float))
    E = cv[ok].copy()
    f = int(round(500.0 / p.cell_m))
    E["block"] = (E["ci"] // f).astype(str) + "_" + (E["cj"] // f).astype(str)
    pinfo = passes.groupby("pass_id").agg(loc=(loc_col, "first"), campaign=("campaign", "first"),
                                          day=("day", "first"))
    E = E.merge(pinfo, left_on="pass_id", right_index=True)
    # location eligibility on passes that can form a pair (>= min_common_cells eligible cells)
    npc = E.groupby("pass_id")["cell"].transform("size")
    Ep = E[npc >= p.min_common_cells]
    nc = Ep.groupby("loc")["campaign"].nunique()
    E = Ep[Ep["loc"].isin(nc[nc >= p.min_campaigns_loc].index)]
    pairs, longs, pid = [], [], 0
    vcols = [f"v_{m}" for m in mask_names]
    for loc, g in E.groupby("loc"):
        ids = g["pass_id"].unique()
        if len(ids) < 2:
            continue
        piv = {c: g.pivot(index="pass_id", columns="cell", values=c) for c in vcols}
        V0 = piv[vcols[0]]
        meta = g.drop_duplicates("cell").set_index("cell")[["block", "route"]]
        mask = V0.notna().to_numpy()
        common = mask.astype(np.int32) @ mask.T.astype(np.int32)
        idx = V0.index.to_numpy()
        for a, b in zip(*np.where(np.triu(common >= p.min_common_cells, 1))):
            mm = mask[a] & mask[b]
            cells = V0.columns[mm]
            pa, pb = idx[a], idx[b]
            ca, cb = pinfo.at[pa, "campaign"], pinfo.at[pb, "campaign"]
            da, db = pinfo.at[pa, "day"], pinfo.at[pb, "day"]
            pairs.append(dict(pair_id=pid, loc=loc, pass_a=pa, pass_b=pb, ca=ca, cb=cb, day_a=da, day_b=db,
                              pair_type=pair_type(ca, cb, da, db), n_common=int(mm.sum())))
            rec = dict(pair_id=pid, cell=cells, block=meta.loc[cells, "block"].to_numpy(),
                       route=meta.loc[cells, "route"].to_numpy())
            for m, c in zip(mask_names, vcols):
                rec[f"ua_{m}"] = piv[c].iloc[a].to_numpy()[mm]
                rec[f"ub_{m}"] = piv[c].iloc[b].to_numpy()[mm]
            longs.append(pd.DataFrame(rec))
            pid += 1
    if not pairs:
        return pd.DataFrame(), pd.DataFrame()
    return pd.DataFrame(pairs), pd.concat(longs, ignore_index=True)


def per_mask_stats(P: pd.DataFrame, L: pd.DataFrame, mask_names) -> dict[str, pd.DataFrame]:
    out = {}
    for m in mask_names:
        S = pair_stats_from_long(L[["pair_id", f"ua_{m}", f"ub_{m}"]].rename(columns={f"ua_{m}": "ua",
                                                                                    f"ub_{m}": "ub"}))
        out[m] = P.merge(S, on="pair_id")
    return out


def boot_weights(P: pd.DataFrame, n_boot: int, seed: int) -> np.ndarray:
    """Campaign-cluster bootstrap weights (same scheme as core.bootstrap_pooled), shared across masks."""
    cs = sorted(set(P["ca"]) | set(P["cb"]))
    ix = {c: i for i, c in enumerate(cs)}
    ia = P["ca"].map(ix).to_numpy()
    ib = P["cb"].map(ix).to_numpy()
    rng = np.random.default_rng(seed)
    M = rng.multinomial(len(cs), np.full(len(cs), 1.0 / len(cs)), size=n_boot).astype(float)
    W = np.where((ia == ib)[None, :], M[:, ia], M[:, ia] * M[:, ib])
    return W[W.sum(axis=1) > 0]


def R_point_and_boot(S: pd.DataFrame, W: np.ndarray):
    a = [S[k].to_numpy() for k in ("cov", "sd2", "n", "r", "msd")]
    R0, _, _ = _stat(*a, np.ones(len(S)))
    RB, _, _ = _stat(*[x[None, :] for x in a], W)
    return float(R0), RB


def ci(x):
    x = np.asarray(x)[np.isfinite(x)]
    return (float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))) if len(x) else (np.nan, np.nan)


def compare_masks(stats: dict[str, pd.DataFrame], ref: str, n_boot: int, seed: int) -> pd.DataFrame:
    """R per mask with campaign-bootstrap CI and paired difference vs `ref` (same weights for every mask)."""
    any_m = next(iter(stats.values()))
    W = boot_weights(any_m, n_boot, seed)
    Rref, Bref = R_point_and_boot(stats[ref], W)
    rows = []
    for m, S in stats.items():
        R, B = R_point_and_boot(S, W)
        lo, hi = ci(B)
        dlo, dhi = ci(B - Bref)
        rows.append(dict(mask=m, n_pairs=len(S), n_campaigns=len(set(S.ca) | set(S.cb)), n_locations=S["loc"].nunique(),
                         n_cells=int(S["n"].sum()), R=R, R_ci_lo=lo, R_ci_hi=hi, R_ci_includes_0=bool(lo <= 0 <= hi),
                         dR_vs_ref=R - Rref, dR_ci_lo=dlo, dR_ci_hi=dhi,
                         dR_ci_includes_0=bool(dlo <= 0 <= dhi) if np.isfinite(dlo) else None))
    return pd.DataFrame(rows)


def pair_count_sensitivity(stats: dict[str, pd.DataFrame], sizes, n_sub: int, n_boot: int, seed: int) -> pd.DataFrame:
    """Subsample the (common) pair set to fixed sizes; the same subsets are used for every mask."""
    any_m = next(iter(stats.values()))
    N = len(any_m)
    rng = np.random.default_rng(seed)
    rows = []
    for n in sizes:
        if n != "all" and n > N:
            continue
        subs = [np.arange(N)] if n == "all" else [np.sort(rng.choice(N, size=n, replace=False)) for _ in range(n_sub)]
        for m, S in stats.items():
            Rs, los, his = [], [], []
            for k, ix in enumerate(subs):
                sub = S.iloc[ix]
                W = boot_weights(sub, n_boot, seed + k)
                R, B = R_point_and_boot(sub, W)
                lo, hi = ci(B)
                Rs.append(R)
                los.append(lo)
                his.append(hi)
            Rs = np.asarray(Rs)
            rows.append(dict(n_pairs=N if n == "all" else n, subset="all" if n == "all" else "random", mask=m,
                             n_subsets=len(subs), R_median=float(np.nanmedian(Rs)),
                             R_p2_5=float(np.nanpercentile(Rs, 2.5)), R_p97_5=float(np.nanpercentile(Rs, 97.5)),
                             boot_ci_lo_median=float(np.nanmedian(los)), boot_ci_hi_median=float(np.nanmedian(his)),
                             share_subsets_ci_excl_0=float(np.mean(np.asarray(los) > 0))))
    return pd.DataFrame(rows)


def prepare_passes(points: pd.DataFrame, loc_col: str, p: Params) -> pd.DataFrame:
    """Union-population passes; adds ts (epoch s)."""
    U = points[points["T"].notna()].copy()
    passes = build_passes(U, loc_col, p)
    if "ts" not in passes:
        passes["ts"] = _epoch_s(passes["t"])
    return passes
