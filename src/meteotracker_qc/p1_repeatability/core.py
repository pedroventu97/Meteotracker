"""Core computations for P1 repeatability (E0). Pure functions on pandas/numpy; no I/O."""
from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

PROFILES = ("permissive", "recommended", "restrictive")
PAIR_TYPES = ("diff_day", "same_day_diff_campaign", "same_campaign")


@dataclass(frozen=True)
class Params:
    cell_m: float = 50.0          # 2-D grid cell (EPSG:32632) used as common along-track support
    gap_s: float = 120.0          # time gap that splits a campaign's visit to a location into passes
    min_pts_pass: int = 10        # min kept points per pass
    min_pts_cell: int = 2         # min points per pass x cell
    min_common_cells: int = 4     # min common cells for a pass pair (>= 200 m with 50 m cells)
    min_campaigns_loc: int = 3    # location eligible if >= this many distinct campaigns have passes
    min_detr_s: float = 30.0      # min pass duration for the within-pass linear detrend
    min_pts_loc_cell: int = 10    # location-level: min points per (location, campaign) cell
    min_common_locs: int = 4      # location-level: min shared locations per campaign pair
    n_boot: int = 1000
    seed: int = 20261109

    def as_dict(self) -> dict:
        return asdict(self)


def _epoch_s(t: pd.Series) -> np.ndarray:
    """Seconds since epoch, independent of the datetime64 unit (pandas 3 may use us/ms instead of ns)."""
    t = pd.to_datetime(t, utc=True)
    return (t - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy()


def pair_type(ca, cb, da, db) -> str:
    if ca == cb:
        return "same_campaign"
    if da == db:
        return "same_day_diff_campaign"
    return "diff_day"


# --------------------------------------------------------------------------------------------
# Pass-level analysis
# --------------------------------------------------------------------------------------------
def build_passes(pts: pd.DataFrame, loc_col: str, p: Params) -> pd.DataFrame:
    """pts: kept points with columns campaign, day, t (datetime64 UTC), T, x, y, <loc_col>.
    Returns points with pass_id, T_centered (=T) and T_detr (T minus within-pass linear fit vs time)."""
    d = pts.dropna(subset=[loc_col, "T"]).sort_values(["campaign", loc_col, "t"]).copy()
    if d.empty:
        return d.assign(pass_id=pd.Series(dtype=str), T_detr=pd.Series(dtype=float))
    ts = _epoch_s(d["t"])
    key = (d["campaign"].astype(str) + "|" + d[loc_col].astype(str)).to_numpy()
    new = np.r_[True, (key[1:] != key[:-1]) | (np.diff(ts) > p.gap_s)]
    d["pass_num"] = np.cumsum(new)
    d["ts"] = ts
    n = d.groupby("pass_num")["T"].transform("size")
    d = d[n >= p.min_pts_pass].copy()
    # within-pass linear detrend vs time (as pass_anomaly anom_detr)
    g = d.groupby("pass_num")
    tm = g["ts"].transform("mean")
    dt = d["ts"] - tm
    Tm = g["T"].transform("mean")
    sxx = (dt * dt).groupby(d["pass_num"]).transform("sum")
    sxy = (dt * (d["T"] - Tm)).groupby(d["pass_num"]).transform("sum")
    slope = np.where(sxx > 0, sxy / sxx.replace(0, np.nan), 0.0)
    dur = g["ts"].transform(lambda s: s.max() - s.min())
    d["T_detr"] = np.where(dur >= p.min_detr_s, d["T"] - Tm - slope * dt, np.nan)
    d["pass_id"] = d["campaign"].astype(str).str[-10:] + "|" + d[loc_col].astype(str) + "|" + d["pass_num"].astype(str)
    d["cell_i"] = np.floor(d["x"] / p.cell_m).astype(np.int64)
    d["cell_j"] = np.floor(d["y"] / p.cell_m).astype(np.int64)
    d["cell"] = d["cell_i"].astype(str) + "_" + d["cell_j"].astype(str)
    return d


def pass_pairs(passes: pd.DataFrame, loc_col: str, variant: str, p: Params, eligible_locs=None):
    """Build all pass pairs within a location sharing >= min_common_cells cells.
    variant: 'centered' (T, centred per pair over common cells) or 'detrended' (T_detr).
    Returns (pairs DataFrame, long DataFrame of pair x common cell values)."""
    col = "T" if variant == "centered" else "T_detr"
    d = passes.dropna(subset=[col])
    if eligible_locs is not None:
        d = d[d[loc_col].isin(eligible_locs)]
    cellv = d.groupby(["pass_id", "cell"]).agg(v=(col, "mean"), n=(col, "size"), tm=("ts", "mean"),
                                              ci=("cell_i", "first"), cj=("cell_j", "first"),
                                              route=("route", "first"))
    cellv = cellv[cellv["n"] >= p.min_pts_cell].reset_index()
    # 500 m spatial block of the 50 m cell (exact when 500 is a multiple of cell_m: floor(x/500)=floor(floor(x/50)/10))
    f = int(round(500.0 / p.cell_m))
    cellv["block"] = (cellv["ci"] // f).astype(str) + "_" + (cellv["cj"] // f).astype(str)
    pinfo = d.groupby("pass_id").agg(loc=(loc_col, "first"), campaign=("campaign", "first"), day=("day", "first"),
                                     t0=("ts", "min"))
    cellv = cellv.merge(pinfo[["loc"]], left_on="pass_id", right_index=True)
    pairs, longs = [], []
    pid = 0
    for loc, g in cellv.groupby("loc"):
        ids = g["pass_id"].unique()
        if len(ids) < 2:
            continue
        V = g.pivot(index="pass_id", columns="cell", values="v")
        TM = g.pivot(index="pass_id", columns="cell", values="tm")
        meta = g.drop_duplicates("cell").set_index("cell")[["block", "route"]]
        mask = V.notna().to_numpy()
        common = mask.astype(np.int32) @ mask.T.astype(np.int32)
        idx = V.index.to_numpy()
        for a, b in zip(*np.where(np.triu(common >= p.min_common_cells, 1))):
            m = mask[a] & mask[b]
            cells = V.columns[m]
            ua = V.iloc[a].to_numpy()[m]
            ub = V.iloc[b].to_numpy()[m]
            pa, pb = idx[a], idx[b]
            ca, cb = pinfo.at[pa, "campaign"], pinfo.at[pb, "campaign"]
            da, db = pinfo.at[pa, "day"], pinfo.at[pb, "day"]
            dtm = float(np.median(np.abs(TM.iloc[a].to_numpy()[m] - TM.iloc[b].to_numpy()[m]))) / 60.0
            pairs.append(dict(pair_id=pid, loc=loc, pass_a=pa, pass_b=pb, ca=ca, cb=cb, day_a=da, day_b=db,
                              pair_type=pair_type(ca, cb, da, db), dt_min=dtm, n_common=int(m.sum())))
            longs.append(pd.DataFrame(dict(pair_id=pid, cell=cells, ua=ua, ub=ub,
                                           block=meta.loc[cells, "block"].to_numpy(),
                                           route=meta.loc[cells, "route"].to_numpy())))
            pid += 1
    if not pairs:
        return pd.DataFrame(), pd.DataFrame()
    P = pd.DataFrame(pairs)
    L = pd.concat(longs, ignore_index=True)
    S = pair_stats_from_long(L)
    P = P.merge(S, on="pair_id")
    return P, L


def pair_stats_from_long(L: pd.DataFrame, min_common: int = 1) -> pd.DataFrame:
    """Per-pair stats from long (pair_id, ua, ub): n, cov, sd2=sqrt(var_a var_b), r, msd (mean sq. diff of centred)."""
    codes, uniq = pd.factorize(L["pair_id"])
    n = np.bincount(codes).astype(float)
    ma = np.bincount(codes, L["ua"].to_numpy()) / n
    mb = np.bincount(codes, L["ub"].to_numpy()) / n
    a = L["ua"].to_numpy() - ma[codes]
    b = L["ub"].to_numpy() - mb[codes]
    cov = np.bincount(codes, a * b) / n
    va = np.bincount(codes, a * a) / n
    vb = np.bincount(codes, b * b) / n
    msd = np.bincount(codes, (a - b) ** 2) / n
    sd2 = np.sqrt(va * vb)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(sd2 > 0, cov / sd2, np.nan)
    out = pd.DataFrame(dict(pair_id=uniq, n=n, cov=cov, sd2=sd2, r=r, msd=msd, offset=ma - mb))
    return out[out["n"] >= min_common]


def _stat(cov, sd2, n, r, msd, w):
    ww = w * n
    den = (ww * sd2).sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        R = (ww * cov).sum(axis=-1) / den
        z = np.arctanh(np.clip(np.nan_to_num(r, nan=0.0), -0.999, 0.999))
        wz = w * np.isfinite(r)
        rf = np.tanh((wz * z).sum(axis=-1) / wz.sum(axis=-1))
        rmsd = np.sqrt((ww * msd).sum(axis=-1) / ww.sum(axis=-1))
    return R, rf, rmsd


def pooled(P: pd.DataFrame) -> dict:
    if P is None or len(P) == 0:
        return dict(n_pairs=0)
    cs = sorted(set(P["ca"]) | set(P["cb"]))
    R, rf, rmsd = _stat(P["cov"].to_numpy(), P["sd2"].to_numpy(), P["n"].to_numpy(), P["r"].to_numpy(),
                        P["msd"].to_numpy(), np.ones(len(P)))
    days = sorted(set(P["day_a"]) | set(P["day_b"])) if "day_a" in P else []
    out = dict(n_pairs=int(len(P)), n_campaigns=len(cs), n_days=len(days),
               R=float(R), fisher_r=float(rf), rmsd_c=float(rmsd), median_r=float(np.nanmedian(P["r"])))
    if "loc" in P:
        out["n_locations"] = int(P["loc"].nunique())
    if "dt_min" in P:
        out["median_dt_min"] = float(P["dt_min"].median())
    return out


def bootstrap_pooled(P: pd.DataFrame, n_boot: int, rng: np.random.Generator) -> dict:
    """Campaign-cluster bootstrap (resampling unit = canonical_campaign_id). Pair weight = product of the two
    campaigns' multiplicities (different campaigns) or the multiplicity (same campaign)."""
    if P is None or len(P) < 2:
        return {}
    cs = sorted(set(P["ca"]) | set(P["cb"]))
    ix = {c: i for i, c in enumerate(cs)}
    ia = P["ca"].map(ix).to_numpy()
    ib = P["cb"].map(ix).to_numpy()
    same = ia == ib
    M = rng.multinomial(len(cs), np.full(len(cs), 1.0 / len(cs)), size=n_boot).astype(float)
    W = np.where(same[None, :], M[:, ia], M[:, ia] * M[:, ib])
    keep = W.sum(axis=1) > 0
    W = W[keep]
    R, rf, rmsd = _stat(P["cov"].to_numpy()[None, :], P["sd2"].to_numpy()[None, :], P["n"].to_numpy()[None, :],
                        P["r"].to_numpy()[None, :], P["msd"].to_numpy()[None, :], W)

    def ci(x):
        x = x[np.isfinite(x)]
        return [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))] if len(x) else [np.nan, np.nan]

    out = dict(R_ci=ci(R), fisher_r_ci=ci(rf), rmsd_ci=ci(rmsd), n_boot_valid=int(keep.sum()))
    out["R_ci_includes_0"] = bool(out["R_ci"][0] <= 0 <= out["R_ci"][1])
    out["fisher_r_ci_includes_0"] = bool(out["fisher_r_ci"][0] <= 0 <= out["fisher_r_ci"][1])
    return out


# --------------------------------------------------------------------------------------------
# Location-level analysis (between-location vs between-campaign variance)
# --------------------------------------------------------------------------------------------
def campaign_anomalies(pts: pd.DataFrame) -> pd.DataFrame:
    """Point anomalies relative to the campaign: centered (T - campaign mean), detrended (T - linear fit vs time),
    detr_alt (residual of T ~ time + altitude, linear, per campaign). Descriptive; altitude partialling is linear only."""
    out = []
    for c, g in pts.dropna(subset=["T"]).groupby("campaign"):
        g = g.copy()
        ts = _epoch_s(g["t"])
        ts = ts - ts.mean()
        T = g["T"].to_numpy()
        g["a_centered"] = T - T.mean()
        X = np.c_[np.ones_like(ts), ts]
        g["a_detrended"] = T - X @ np.linalg.lstsq(X, T, rcond=None)[0]
        alt = g["alt"].to_numpy()
        ok = np.isfinite(alt)
        g["a_detr_alt"] = np.nan
        if ok.sum() > 20 and np.nanstd(alt) > 0:
            X2 = np.c_[np.ones(ok.sum()), ts[ok], alt[ok]]
            g.loc[ok, "a_detr_alt"] = T[ok] - X2 @ np.linalg.lstsq(X2, T[ok], rcond=None)[0]
        out.append(g)
    return pd.concat(out) if out else pts.iloc[0:0]


def icc_oneway(cells: pd.DataFrame, val: str = "a", grp: str = "loc", weights=None) -> float:
    """ICC(1) one-way random effects with unbalanced groups: share of variance of campaign-cell anomalies that is
    between locations. Optional integer weights (bootstrap multiplicities)."""
    w = np.ones(len(cells)) if weights is None else np.asarray(weights, float)
    m = w > 0
    if m.sum() < 3:
        return np.nan
    c = cells.loc[m]
    w = w[m]
    y = c[val].to_numpy()
    gcodes, _ = pd.factorize(c[grp])
    ng = np.bincount(gcodes, w)
    k = len(ng)
    N = w.sum()
    if k < 2 or N - k <= 0:
        return np.nan
    gm = np.bincount(gcodes, w * y) / ng
    mu = (w * y).sum() / N
    ssb = (ng * (gm - mu) ** 2).sum()
    ssw = (w * (y - gm[gcodes]) ** 2).sum()
    msb = ssb / (k - 1)
    msw = ssw / (N - k)
    k0 = (N - (ng ** 2).sum() / N) / (k - 1)
    den = msb + (k0 - 1) * msw
    return float((msb - msw) / den) if den > 0 else np.nan


def location_level(anom: pd.DataFrame, loc_col: str, variant: str, p: Params, rng=None, n_boot=0):
    """Location x campaign mean anomalies; ICC between locations; inter-campaign correlation of location
    anomaly vectors (pairs of campaigns on different days / same day), RMSD of repeat visits."""
    col = f"a_{variant}"
    d = anom.dropna(subset=[loc_col, col])
    cells = d.groupby([loc_col, "campaign"]).agg(a=(col, "mean"), n=(col, "size"), day=("day", "first")).reset_index()
    cells = cells[cells["n"] >= p.min_pts_loc_cell].rename(columns={loc_col: "loc"})
    nc = cells.groupby("loc")["campaign"].nunique()
    cells = cells[cells["loc"].isin(nc[nc >= p.min_campaigns_loc].index)]
    res = dict(n_locations=int(cells["loc"].nunique()), n_cells=int(len(cells)), n_campaigns=int(cells["campaign"].nunique()))
    if len(cells) < 3:
        return res, cells, pd.DataFrame()
    # campaign-centre within the eligible subset so that the campaign main effect is removed
    cells["a"] = cells["a"] - cells.groupby("campaign")["a"].transform("mean")
    res["icc_between_location"] = icc_oneway(cells)
    # campaign pairs
    W = cells.pivot(index="campaign", columns="loc", values="a")
    dayof = cells.drop_duplicates("campaign").set_index("campaign")["day"]
    rows = []
    for a, b in itertools.combinations(W.index, 2):
        m = W.loc[a].notna() & W.loc[b].notna()
        if m.sum() < p.min_common_locs:
            continue
        rows.append(dict(ca=a, cb=b, day_a=dayof[a], day_b=dayof[b], pair_type=pair_type(a, b, dayof[a], dayof[b]),
                         pair_id=len(rows), _ua=W.loc[a][m].to_numpy(), _ub=W.loc[b][m].to_numpy()))
    if rows:
        L = pd.concat([pd.DataFrame(dict(pair_id=r["pair_id"], ua=r["_ua"], ub=r["_ub"])) for r in rows])
        P = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]).merge(
            pair_stats_from_long(L), on="pair_id")
    else:
        P = pd.DataFrame()
    for pt in ("diff_day", "same_day_diff_campaign"):
        sub = P[P["pair_type"] == pt] if len(P) else P
        o = pooled(sub)
        res[f"campaign_pairs_{pt}"] = o
    if rng is not None and n_boot:
        # ICC uncertainty: leave-one-campaign jackknife (normal approx.). A cluster bootstrap that duplicates
        # campaigns creates identical replicate cells inside a location and biases ICC upward, so it is not used here.
        cs = sorted(cells["campaign"].unique())
        jk = np.array([icc_oneway(cells[cells["campaign"] != c]) for c in cs])
        jk = jk[np.isfinite(jk)]
        if len(jk) > 2 and np.isfinite(res["icc_between_location"]):
            n = len(jk)
            se = float(np.sqrt((n - 1) / n * ((jk - jk.mean()) ** 2).sum()))
            v = res["icc_between_location"]
            ci = [v - 1.96 * se, v + 1.96 * se]
            res.update(icc_ci=ci, icc_ci_method="jackknife_leave_one_campaign_normal", icc_jackknife_se=se,
                       icc_jackknife_min=float(jk.min()), icc_jackknife_max=float(jk.max()),
                       icc_ci_includes_0=bool(ci[0] <= 0 <= ci[1]))
        for pt in ("diff_day", "same_day_diff_campaign"):
            sub = P[P["pair_type"] == pt] if len(P) else P
            if len(sub) >= 2:
                res[f"campaign_pairs_{pt}"].update(bootstrap_pooled(sub, n_boot, rng))
    return res, cells, P
