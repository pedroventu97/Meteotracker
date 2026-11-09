"""E0-QC-R empirical evidence (pure functions, no I/O).

Implements the checks pre-registered in e0/QC_R_CRITERIA_E0.md (R1-R5) on per-campaign QC frames produced by
MeteotrackerQC.compute_frame (fixed dt=0 code). Decision rules use the thresholds fixed in that document.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Geod

GEOD = Geod(ellps="WGS84")

# --- thresholds fixed in QC_R_CRITERIA_E0.md -------------------------------------------------------------------
THERMAL_RES_C = 0.1          # R2/R3 minimum consequential transient
POS_HALF_CELL_M = 25.0       # R4/R5 half of the 50 m P1 cell
ACC_DOP_PLAUSIBLE = 2.0      # R4 |a_dop| >= 2 m/s2 -> plausible vehicle dynamics
STEADY_MIN_KMH = 15.0        # R4 steady-cruise sample
STEADY_MAX_ADOP = 0.3        # R4 steady-cruise |a_dop| at i-1, i, i+1
FREEZE_CONSISTENT_MPS = 3.0  # R5 release speed consistent with device speed
REF_WIN = (240.0, 360.0)     # R2/R3 reference window [s]
BIN_S = 10.0
CURVE_MAX_S = 240.0
EARLY_S = 60.0
CAP_WINDOW_S = 300.0
MAJORITY = 0.5               # R4/R5


def _epoch(t: pd.Series) -> np.ndarray:
    t = pd.to_datetime(t, utc=True)
    return (t - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy()


# ---------------------------------------------------------------------------------------------------------------
# R1 duplicated timestamps
# ---------------------------------------------------------------------------------------------------------------
def dt0_rows(df: pd.DataFrame) -> pd.DataFrame:
    """One row per dt == 0 record: content class, neighbouring dt, continuity vs the previous row."""
    dt = pd.to_numeric(df["dt_s"], errors="coerce").to_numpy()
    idx = np.where(dt == 0)[0]
    if len(idx) == 0:
        return pd.DataFrame()
    lat = pd.to_numeric(df.get("Lat"), errors="coerce").to_numpy()
    lon = pd.to_numeric(df.get("Lon"), errors="coerce").to_numpy()
    T = pd.to_numeric(df.get("Temp[°C]"), errors="coerce").to_numpy()
    ok = idx[idx > 0]
    _, _, dist = GEOD.inv(lon[ok - 1], lat[ok - 1], lon[ok], lat[ok])
    rec = pd.DataFrame(dict(source_row=df["source_row"].to_numpy()[ok], dt_prev=dt[ok - 1],
                            dt_next=np.r_[dt, np.nan][ok + 1], step_m=dist, dT_abs=np.abs(T[ok] - T[ok - 1]),
                            exact_copy=df["qc_duplicate_record"].to_numpy()[ok].astype(bool)))
    rec["pattern"] = rec.dt_prev.map(lambda v: "nan" if pd.isna(v) else f"{v:g}") + "-0-" + \
        rec.dt_next.map(lambda v: "nan" if pd.isna(v) else f"{v:g}")
    return rec


def one_second_steps(df: pd.DataFrame) -> pd.DataFrame:
    """Reference distribution of ordinary 1 s steps (same segment) for the R1 continuity comparison."""
    dt = pd.to_numeric(df["dt_s"], errors="coerce")
    m = (dt == 1) & (df["segment_id"] == df["segment_id"].shift(1))
    T = pd.to_numeric(df.get("Temp[°C]"), errors="coerce")
    return pd.DataFrame(dict(step_m=df["distance_from_previous_m"][m], dT_abs=T.diff().abs()[m]))


# ---------------------------------------------------------------------------------------------------------------
# R2 / R3 recovery curves
# ---------------------------------------------------------------------------------------------------------------
def _seg_arrays(df):
    return (_epoch(df["time_utc"]), pd.to_numeric(df["Temp[°C]"], errors="coerce").to_numpy(),
            df["segment_id"].to_numpy())


def gap_events(df: pd.DataFrame) -> pd.DataFrame:
    """Starts of segments k > 0 opened by a real long gap (after the R1 fix)."""
    first_seg = df["segment_id"].min()
    st = df["segment_id"].ne(df["segment_id"].shift(1)) & (df["segment_id"] != first_seg)
    st &= df["segment_start_reason"].astype(str).eq("long_gap")
    i = np.where(st.to_numpy())[0]
    return pd.DataFrame(dict(row=i, kind="gap", duration_s=pd.to_numeric(df["dt_s"], errors="coerce").to_numpy()[i]))


def stop_events(df: pd.DataFrame) -> pd.DataFrame:
    """First moving row after a significant stop (qc_stop_event run), same segment; duration = stop length."""
    se = df["qc_stop_event"].fillna(False).to_numpy().astype(bool)
    stat = df["qc_stationary"].fillna(False).to_numpy().astype(bool)
    seg = df["segment_id"].to_numpy()
    dur = pd.to_numeric(df["stop_duration_s"], errors="coerce").to_numpy()
    rows = [i for i in range(1, len(df)) if se[i - 1] and not stat[i] and seg[i] == seg[i - 1]]
    return pd.DataFrame(dict(row=rows, kind="stop", duration_s=[dur[i - 1] for i in rows]))


def deviation_bins(df: pd.DataFrame, rows, cadence_s: float, no_stop_in_window: bool) -> pd.DataFrame:
    """Binned D(t) = T(t) - median T over REF_WIN after each start row (same segment). Returns long table
    (event_i, bin_start, D). Events lacking >= 50% coverage of REF_WIN, or (if requested) with a significant stop
    inside (0, REF_WIN[1]], are dropped."""
    ts, T, seg = _seg_arrays(df)
    stop = df["qc_stop_event"].fillna(False).to_numpy().astype(bool) if no_stop_in_window else None
    need = 0.5 * (REF_WIN[1] - REF_WIN[0]) / max(cadence_s, 1e-6)
    out = []
    for k, i0 in enumerate(rows):
        j1 = np.searchsorted(ts, ts[i0] + REF_WIN[1], side="right")
        j = np.arange(i0, j1)
        j = j[seg[j] == seg[i0]]
        e = ts[j] - ts[i0]
        if stop is not None and stop[j[e > 0]].any():
            continue
        ref = (e >= REF_WIN[0]) & (e <= REF_WIN[1]) & np.isfinite(T[j])
        if ref.sum() < need:
            continue
        D = T[j] - np.median(T[j][ref])
        early = (e < CURVE_MAX_S) & np.isfinite(D)
        b = np.floor(e[early] / BIN_S) * BIN_S
        g = pd.DataFrame(dict(bin_start=b, D=D[early])).groupby("bin_start", as_index=False)["D"].mean()
        g["event_i"] = k
        g["row"] = i0
        out.append(g)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["bin_start", "D", "event_i", "row"])


def control_rows(df: pd.DataFrame, rng: np.random.Generator, n_max: int = 10) -> np.ndarray:
    """Pseudo-event rows: >= REF_WIN[1] s after segment start and after the end of any stop, not stationary."""
    ts, _, seg = _seg_arrays(df)
    seg_start = pd.Series(ts).groupby(seg).transform("min").to_numpy()
    stop = df["qc_stop_event"].fillna(False).to_numpy().astype(bool)
    last_stop = pd.Series(np.where(stop, ts, np.nan)).groupby(seg).ffill().to_numpy()
    stat = df["qc_stationary"].fillna(False).to_numpy().astype(bool)
    ok = (ts - seg_start >= REF_WIN[1]) & ~stat & ~((ts - last_stop) < REF_WIN[1])
    cand = np.where(ok)[0]
    if len(cand) == 0:
        return cand
    return np.sort(rng.choice(cand, size=min(n_max, len(cand)), replace=False))


def excess_curves(ev: pd.DataFrame, ct: pd.DataFrame, n_boot: int, rng: np.random.Generator) -> pd.DataFrame:
    """ev/ct: long tables with campaign, event_key, bin_start, D. Per bin: A = mean|D|_ev - mean|D|_ct,
    S = mean D_ev - mean D_ct, with campaign-cluster bootstrap 95% CI."""
    bins = np.arange(0, CURVE_MAX_S, BIN_S)
    camps = sorted(set(ev["campaign"]) | set(ct["campaign"]))
    ci = {c: i for i, c in enumerate(camps)}

    def agg(x):
        x = x.assign(ci=x["campaign"].map(ci), b=(x["bin_start"] // BIN_S).astype(int), aD=x["D"].abs())
        n = np.zeros((len(camps), len(bins)))
        sD = np.zeros_like(n)
        sA = np.zeros_like(n)
        np.add.at(n, (x.ci, x.b), 1)
        np.add.at(sD, (x.ci, x.b), x.D)
        np.add.at(sA, (x.ci, x.b), x.aD)
        return n, sD, sA

    ne, sDe, sAe = agg(ev)
    nc, sDc, sAc = agg(ct)

    def stat(w):
        with np.errstate(invalid="ignore", divide="ignore"):
            A = (w @ sAe) / (w @ ne) - (w @ sAc) / (w @ nc)
            S = (w @ sDe) / (w @ ne) - (w @ sDc) / (w @ nc)
        return A, S

    A0, S0 = stat(np.ones(len(camps)))
    W = rng.multinomial(len(camps), np.full(len(camps), 1 / len(camps)), size=n_boot).astype(float)
    AB, SB = stat(W)
    lo = lambda m: np.nanpercentile(m, 2.5, axis=0)  # noqa: E731
    hi = lambda m: np.nanpercentile(m, 97.5, axis=0)  # noqa: E731
    return pd.DataFrame(dict(bin_start=bins, n_events=ne.sum(0), n_controls=nc.sum(0), A=A0, A_lo=lo(AB), A_hi=hi(AB),
                             S=S0, S_lo=lo(SB), S_hi=hi(SB)))


def decide_recovery(curve: pd.DataFrame) -> dict:
    """Pre-registered R2/R3 rule: transient if, within EARLY_S, A or |S| > THERMAL_RES_C with CI excluding 0.
    Window W = first bin start after which no later bin is significant-and-above."""
    c = curve.dropna(subset=["A"])
    if c.empty or c.n_events.max() < 5:
        return dict(transient=None, window_s=None, reason="too few events (<5) -> v0.1 severity kept")
    sigA = (c.A > THERMAL_RES_C) & (c.A_lo > 0)
    sigS = (c.S.abs() > THERMAL_RES_C) & ((c.S_lo > 0) | (c.S_hi < 0))
    sig = (sigA | sigS).to_numpy()
    early = (c.bin_start < EARLY_S).to_numpy()
    transient = bool(sig[early].any())
    if not transient:
        return dict(transient=False, window_s=0.0, reason="no consequential transient in first 60 s")
    last = np.where(sig)[0].max()
    w = float(c.bin_start.iloc[last] + BIN_S)
    return dict(transient=True, window_s=min(w, CAP_WINDOW_S),
                reason=f"significant excess up to bin {c.bin_start.iloc[last]:.0f} s")


# ---------------------------------------------------------------------------------------------------------------
# R4 acceleration
# ---------------------------------------------------------------------------------------------------------------
def accel_table(df: pd.DataFrame) -> pd.DataFrame:
    dt = pd.to_numeric(df["dt_s"], errors="coerce")
    same = (df["segment_id"] == df["segment_id"].shift(1)) & (dt > 0)
    vd = pd.to_numeric(df["speed_device_kmh"], errors="coerce") / 3.6
    a_dop = (vd.diff() / dt.clip(lower=1.0)).where(same)
    d = pd.to_numeric(df["distance_from_previous_m"], errors="coerce")
    e_pos = (d - 0.5 * (vd + vd.shift(1)) * dt).abs().where(same)
    steady = (vd * 3.6 >= STEADY_MIN_KMH)
    calm = a_dop.abs() <= STEADY_MAX_ADOP
    steady &= calm & calm.shift(1, fill_value=False) & calm.shift(-1, fill_value=False)
    out = pd.DataFrame(dict(source_row=df["source_row"].to_numpy(), a_pos=pd.to_numeric(df["acceleration_gps_mps2"],
                       errors="coerce").to_numpy(), a_dop=a_dop.to_numpy(),
                       e_pos_max=np.fmax(e_pos.to_numpy(), e_pos.shift(1).to_numpy()), steady=steady.to_numpy(),
                       dt=dt.to_numpy(), dt_changed=(dt != dt.shift(1)).to_numpy(),
                       speed_kmh=(vd * 3.6).to_numpy()))
    out["cls"] = np.where(out.a_dop.isna(), "non_verificabile",
                          np.where(out.a_dop.abs() >= ACC_DOP_PLAUSIBLE, "dinamica_plausibile", "rumore_gps"))
    return out


def decide_accel(acc: pd.DataFrame, thr: float = 5.0) -> dict:
    f = acc[acc.a_pos.abs() > thr]
    if f.empty:
        return dict(noise_share=None, e_pos_p95=None, severity_recommended="exclude (v0.1)", n_flagged=0)
    noise = float((f.cls == "rumore_gps").mean())
    p95 = float(np.nanpercentile(f.e_pos_max, 95))
    ok = noise >= MAJORITY and p95 < POS_HALF_CELL_M
    return dict(n_flagged=int(len(f)), noise_share=noise, e_pos_p95=p95,
                severity_recommended="warn (EXCLUDE_RESTRICTIVE)" if ok else "exclude (EXCLUDE_RECOMMENDED)",
                rule_met=bool(ok))


# ---------------------------------------------------------------------------------------------------------------
# R5 gps freeze
# ---------------------------------------------------------------------------------------------------------------
def freeze_blocks(df: pd.DataFrame) -> pd.DataFrame:
    fz = df["qc_gps_freeze"].fillna(False).to_numpy().astype(bool)
    if not fz.any():
        return pd.DataFrame()
    ts, T, seg = _seg_arrays(df)
    lat = pd.to_numeric(df["Lat"], errors="coerce").to_numpy()
    lon = pd.to_numeric(df["Lon"], errors="coerce").to_numpy()
    vd = pd.to_numeric(df["speed_device_kmh"], errors="coerce").to_numpy() / 3.6
    varying = df["gps_freeze_meteo_still_varying"].fillna(False).to_numpy().astype(bool)
    run = np.r_[0, np.cumsum(fz[1:] != fz[:-1])]
    rows = []
    for r in np.unique(run[fz]):
        ii = np.where(run == r)[0]
        a, b = ii[0], ii[-1]
        rec = dict(start_row=int(df["source_row"].iloc[a]), n_points=len(ii), duration_s=float(ts[b] - ts[a]),
                   vdev_max_kmh=float(np.nanmax(vd[ii]) * 3.6) if np.isfinite(vd[ii]).any() else np.nan,
                   meteo_varying_share=float(varying[ii].mean()), D_rel_m=np.nan, dt_rel_s=np.nan, v_after_mps=np.nan)
        n = b + 1
        if n < len(df) and seg[n] == seg[b] and np.isfinite([lat[n], lon[n], lat[b], lon[b]]).all():
            _, _, dd = GEOD.inv(lon[b], lat[b], lon[n], lat[n])
            rec.update(D_rel_m=float(dd), dt_rel_s=float(ts[n] - ts[b]), v_after_mps=float(vd[n]))
        rows.append(rec)
    B = pd.DataFrame(rows)
    with np.errstate(invalid="ignore", divide="ignore"):
        rel_speed = B.D_rel_m / B.dt_rel_s.clip(lower=1.0)
    consistent = (rel_speed - B.v_after_mps).abs() <= FREEZE_CONSISTENT_MPS
    B["cls"] = np.where(B.D_rel_m.isna(), "non_verificabile",
                        np.where((B.D_rel_m <= POS_HALF_CELL_M) | consistent.fillna(False), "sosta_reale",
                                 "freeze_in_movimento"))
    return B


def decide_freeze(B: pd.DataFrame) -> dict:
    if B.empty:
        return dict(real_stop_point_share=None, severity="EXCLUDE_RECOMMENDED (v0.1)")
    share = float(B.loc[B.cls == "sosta_reale", "n_points"].sum() / B.n_points.sum())
    return dict(real_stop_point_share=share, n_blocks=int(len(B)), n_points=int(B.n_points.sum()),
                severity="EXCLUDE_RESTRICTIVE" if share > MAJORITY else "EXCLUDE_RECOMMENDED",
                rule_met=bool(share > MAJORITY))
