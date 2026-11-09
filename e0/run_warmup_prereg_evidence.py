"""Warm-up pre-registration (v0.3 proposal, NOT implemented), phase A: THERMAL EVIDENCE ONLY (no P1 / no R).

  python e0/run_warmup_prereg_evidence.py <OUT_DIR>

Read-only on data/raw and every existing output. Inputs: v0.2 recommended standardized frames
(outputs/e0R_qc_split_20261109T1240) and v0.1 ones (e0_qc_split_20261105T1703) for the affected-campaign list.
Per campaign, first segment only (the scope of qc_sensor_stabilization). Real session starts are compared with
PSEUDO-STARTS (same metrics on windows starting mid-trip), which give the null distribution produced by spatial and
meteorological variability alone. Nothing here looks at repeatability.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
V02 = ROOT / "outputs" / "e0R_qc_split_20261109T1240" / "recommended" / "campaigns"
V01 = ROOT / "outputs" / "e0_qc_split_20261105T1703" / "campaigns"
T, RH, DP = "Temp[°C]", "Hum[%]", "DP[°C]"
CAP_NOW = 300.0
# A-priori constants (documented in the pre-registration; not tuned on these data):
WARM_GAP_MIN = 15.0      # AMT 2024: stationary MT needs 10-15 min to equilibrate -> < 15 min off = sensor still warm
COLD_GAP_MIN = 120.0
BLOCK_S = 10.0           # block means to limit autocorrelation in model comparison
FIT_S = 900.0            # transient model fitted on [t0, t0+900 s]
LATER = (600.0, 1200.0)  # "later phase" reference window relative to the (pseudo) start
WINDOWS = [(0, 60), (60, 120), (120, 180), (180, 300), (300, 600)]
TAUS = [15, 30, 60, 120, 180, 300, 600]
PSEUDO_STEP_S = 300.0    # pseudo-starts every 300 s from 600 s after ANY segment start (correlated; inference by campaign bootstrap)
QUANTUM = 0.1


def frames():
    for d in sorted(V02.iterdir()):
        if not d.is_dir():
            continue
        s = pd.read_parquet(next(d.glob("*_standardized.parquet")),
                            columns=["time_utc", T, RH, DP, "speed_device_kmh", "segment_id", "device_id",
                                     "qc_sensor_stabilization", "stabilization_seconds_from_segment_start",
                                     "stabilization_window_end_reason"])
        yield d.name, s


def v01_stab(cid):
    try:
        s = pd.read_parquet(next((V01 / cid).glob("*_standardized.parquet")), columns=["qc_sensor_stabilization"])
        return int(s.qc_sensor_stabilization.sum())
    except StopIteration:
        return np.nan


def blocks(t, y):
    b = np.floor(t / BLOCK_S)
    g = pd.DataFrame({"b": b, "t": t, "y": y}).dropna().groupby("b").mean()
    return g.t.to_numpy(), g.y.to_numpy()


def fit_transient(t, y):
    """Block-mean series; models: linear a+c t vs exponential a+b exp(-t/tau) (tau on a grid, +1 parameter)."""
    tb, yb = blocks(t, y)
    n = len(tb)
    if n < 20:
        return None
    X_lin = np.column_stack([np.ones(n), tb])
    sse_lin = float(np.sum((yb - X_lin @ np.linalg.lstsq(X_lin, yb, rcond=None)[0]) ** 2))
    best = None
    for tau in TAUS:
        X = np.column_stack([np.ones(n), np.exp(-tb / tau)])
        coef = np.linalg.lstsq(X, yb, rcond=None)[0]
        sse = float(np.sum((yb - X @ coef) ** 2))
        if best is None or sse < best[0]:
            best = (sse, tau, coef)
    sse_exp, tau, coef = best
    bic = lambda sse, k: n * np.log(max(sse, 1e-12) / n) + k * np.log(n)  # noqa: E731
    b = float(coef[1])
    t_star = float(tau * np.log(abs(b) / (QUANTUM / 2))) if abs(b) > QUANTUM / 2 else 0.0
    return dict(n_blocks=n, tau_s=float(tau), amp_b=b, dBIC=float(bic(sse_lin, 2) - bic(sse_exp, 3)),
                t_below_half_quantum_s=t_star)


def acf(y, lag):
    y = y - np.nanmean(y)
    if len(y) <= lag + 5:
        return np.nan
    return float(np.corrcoef(y[:-lag], y[lag:])[0, 1])


def window_metrics(t, s, t0, var):
    y = pd.to_numeric(s[var], errors="coerce").to_numpy()
    rel = t - t0
    later = (rel >= LATER[0]) & (rel < LATER[1])
    if later.sum() < 30 or (rel >= 0).sum() == 0:
        return None
    ref = np.nanmean(y[later])
    out = {}
    for a, b in WINDOWS:
        m = (rel >= a) & (rel < b)
        out[f"off_{a}_{b}"] = float(np.nanmean(y[m]) - ref) if m.sum() >= 5 else np.nan
    for a, b in ((0, 300), (300, 600)):
        m = (rel >= a) & (rel < b)
        out[f"slope_{a}_{b}_c_per_min"] = float(np.polyfit(rel[m], y[m], 1)[0] * 60) if m.sum() >= 10 else np.nan
    m = (rel >= 0) & (rel < FIT_S)
    f = fit_transient(rel[m], y[m])
    if f:
        out.update({k: v for k, v in f.items()})
    # autocorrelation of the 10 s block-mean series, first 300 s (linear detrend)
    m3 = (rel >= 0) & (rel < 300)
    tb, yb = blocks(rel[m3], y[m3])
    if len(tb) > 12:
        yb = yb - np.polyval(np.polyfit(tb, yb, 1), tb)
        out["acf_lag1_10s"] = acf(yb, 1); out["acf_lag3_30s"] = acf(yb, 3)
    sp = pd.to_numeric(s["speed_device_kmh"], errors="coerce").to_numpy()
    out["ventilated_share_0_300"] = float(np.nanmean(sp[m3] > 7.0)) if m3.sum() else np.nan
    return out


def main(out: Path):
    out.mkdir(parents=True, exist_ok=False)
    meta, rows, traces = [], [], {}
    for cid, s in frames():
        s = s[s.segment_id == s.segment_id.min()].reset_index(drop=True)
        t = s["stabilization_seconds_from_segment_start"].to_numpy(dtype=float)
        stab = s.qc_sensor_stabilization.to_numpy()
        reason = str(s.stabilization_window_end_reason.iloc[0])
        conf_s = float(t[np.argmin(stab)]) if (~stab).any() and reason == "slope_confirmed_stable" else np.nan
        meta.append(dict(campaign=cid, device=str(s.device_id.iloc[0]), start=s.time_utc.iloc[0], end=s.time_utc.iloc[-1],
                         first_segment_s=float(t.max()), end_reason=reason, confirm_s=conf_s,
                         stab_rows_v02=int(stab.sum()), stab_s_v02=float(t[stab].max()) if stab.any() else 0.0,
                         stab_rows_v01=v01_stab(cid)))
        traces[cid] = (t, s)
    M = pd.DataFrame(meta).sort_values(["device", "start"])
    # previous recorded session of the same device (any segment); full-session end needed -> use 'end' of first segment
    # is not enough, so re-read full end times
    ends = {}
    for cid, s in frames():
        ends[cid] = s.time_utc.iloc[-1]
    M["full_end"] = M.campaign.map(ends)
    M["gap_prev_session_min"] = (M.start - M.groupby("device").full_end.shift()).dt.total_seconds() / 60
    M.loc[M.device.isin(["UNKNOWN"]), "gap_prev_session_min"] = np.nan  # device identity not established
    M["start_class"] = np.where(M.gap_prev_session_min <= WARM_GAP_MIN, "warm",
                                np.where(M.gap_prev_session_min > COLD_GAP_MIN, "cold",
                                         np.where(M.gap_prev_session_min.isna(), "unknown", "intermediate")))
    M.loc[M.gap_prev_session_min.isna() & (M.device != "UNKNOWN"), "start_class"] = "cold"  # first record of device
    inc = M.stab_rows_v02 - M.stab_rows_v01
    # AFFECTED_v02 = warm-up >= 14 min in v0.2 that grew vs v0.1 (the cases named in the final validation);
    # CAP_GREW_v02 = grew vs v0.1 only up to the 300 s cap; LONG_CONFIRM_preexisting = confirmation > 300 s already in v0.1.
    M["group"] = np.where((inc > 150) & (M.confirm_s > 600), "AFFECTED_v02",
                          np.where(inc > 150, "CAP_GREW_v02",
                                   np.where(M.confirm_s > CAP_NOW, "LONG_CONFIRM_preexisting", "reference")))
    # cross-device simultaneity check (other sensors at the same time)
    ov = []
    for i, a in M.iterrows():
        for j, b in M.iterrows():
            if i < j and a.device != b.device and a.start < b.full_end and b.start < a.full_end:
                ov.append((a.campaign, b.campaign))
    # metrics: real starts and pseudo-starts, for T, RH, DP
    for cid, (t, s) in traces.items():
        for var in (T, RH, DP):
            r = window_metrics(t, s, 0.0, var)
            if r:
                rows.append(dict(campaign=cid, var=var, kind="real_start", t0=0.0, **r))
    for cid, full in frames():
        for seg, sg in full.groupby("segment_id"):
            sg = sg.reset_index(drop=True)
            ts = (sg.time_utc - sg.time_utc.iloc[0]).dt.total_seconds().to_numpy()
            t0 = 600.0
            while ts.max() >= t0 + LATER[1]:
                for var in (T, RH, DP):
                    r = window_metrics(ts, sg, t0, var)
                    if r:
                        rows.append(dict(campaign=cid, var=var, kind="pseudo_start", t0=t0, segment=int(seg), **r))
                t0 += PSEUDO_STEP_S
    X = pd.DataFrame(rows).merge(M[["campaign", "group", "start_class", "gap_prev_session_min"]], on="campaign")
    M.to_csv(out / "campaigns_warmup_meta.csv", index=False)
    X.to_csv(out / "start_metrics_real_vs_pseudo.csv", index=False)
    # Transient test D (specified after inspecting the phase-A real-start table, BEFORE any repeatability):
    # a decaying session-start transient = exponential preferred over linear (dBIC >= 10 on 10 s blocks), tau <= 300 s,
    # amplitude >= 3 quanta (0.3 C), same sign as the first-minute offset, and the offset decays (|off 300-600| <=
    # 0.5 |off 0-60|). Its false-positive rate is measured on the pseudo-starts (mid-trip windows).
    XT = X[X["var"] == T].copy()
    XT["transient"] = ((XT.tau_s <= 300) & (XT.dBIC >= 10) & (XT.amp_b.abs() >= 3 * QUANTUM)
                       & (np.sign(XT.off_0_60) == np.sign(XT.amp_b)) & (XT.off_300_600.abs() <= 0.5 * XT.off_0_60.abs()))
    XT["t_decay_below_0p1C_s"] = np.where(XT.amp_b.abs() > QUANTUM, XT.tau_s * np.log(XT.amp_b.abs().clip(lower=QUANTUM) / QUANTUM), 0.0)
    X.loc[XT.index, "transient"] = XT.transient; X.loc[XT.index, "t_decay_below_0p1C_s"] = XT.t_decay_below_0p1C_s
    X.to_csv(out / "start_metrics_real_vs_pseudo.csv", index=False)
    ps = XT[XT.kind == "pseudo_start"]
    b95, dbic95 = float(np.nanpercentile(ps.amp_b.abs(), 95)), float(np.nanpercentile(ps.dBIC, 95))
    rs = XT[XT.kind == "real_start"]
    summ = dict(n_campaigns=len(M), groups=M.group.value_counts().to_dict(), start_class=M.start_class.value_counts().to_dict(),
                affected=M[M.group == "AFFECTED_v02"][["campaign", "confirm_s", "stab_rows_v01", "stab_rows_v02", "gap_prev_session_min", "start_class"]].to_dict("records"),
                cap_grew=M[M.group == "CAP_GREW_v02"][["campaign", "confirm_s", "stab_rows_v01", "stab_rows_v02", "gap_prev_session_min", "start_class"]].to_dict("records"),
                long_confirm_preexisting=M[M.group == "LONG_CONFIRM_preexisting"][["campaign", "confirm_s", "stab_rows_v01", "stab_rows_v02", "gap_prev_session_min", "start_class"]].to_dict("records"),
                cross_device_simultaneous_sessions=ov,
                n_pseudo_starts=int(len(ps)), n_real_starts=int(len(rs)),
                pseudo_abs_b_p95=b95, pseudo_dBIC_p95=dbic95,
                transient_real_starts=int(rs.transient.sum()), transient_pseudo_starts=int(ps.transient.sum()),
                transient_rate_real=float(rs.transient.mean()), transient_rate_pseudo=float(ps.transient.mean()),
                transient_rate_real_by_class={k: [int(v.sum()), int(len(v))] for k, v in rs.groupby("start_class").transient},
                fisher_real_vs_pseudo_p=float(stats.fisher_exact([[int(rs.transient.sum()), int((~rs.transient).sum())],
                                                                   [int(ps.transient.sum()), int((~ps.transient).sum())]], alternative="greater")[1]),
                transient_campaigns=rs[rs.transient][["campaign", "amp_b", "tau_s", "dBIC", "off_0_60", "off_300_600",
                                                      "t_decay_below_0p1C_s", "start_class", "group", "gap_prev_session_min"]].to_dict("records"),
                transient_pseudo=ps[ps.transient][["campaign", "t0", "amp_b", "tau_s", "dBIC", "t_decay_below_0p1C_s"]].to_dict("records"))
    # group comparisons of |offset| (real vs pseudo) for T, RH, DP
    comp = []
    for var in (T, RH, DP):
        V = X[X["var"] == var]
        p = V[V.kind == "pseudo_start"]
        for a, b in WINDOWS:
            col = f"off_{a}_{b}"
            for cls in ("all", "warm", "intermediate", "cold"):
                r = V[(V.kind == "real_start") & ((V.start_class == cls) | (cls == "all"))]
                x, y = r[col].abs().dropna(), p[col].abs().dropna()
                if len(x) >= 3 and len(y) >= 3:
                    u = stats.mannwhitneyu(x, y, alternative="greater")
                    comp.append(dict(var=var, window=col, start_class=cls, n_real=len(x), n_pseudo=len(y),
                                     median_abs_real=float(x.median()), median_abs_pseudo=float(y.median()),
                                     p90_abs_real=float(x.quantile(.9)), p90_abs_pseudo=float(y.quantile(.9)),
                                     median_signed_real=float(r[col].median()), mw_p_greater=float(u.pvalue)))
        for col in ("slope_0_300_c_per_min", "acf_lag3_30s", "amp_b"):
            for cls in ("all", "warm", "cold"):
                r = V[(V.kind == "real_start") & ((V.start_class == cls) | (cls == "all"))]
                x, y = (r[col].abs() if col != "acf_lag3_30s" else r[col]).dropna(), (p[col].abs() if col != "acf_lag3_30s" else p[col]).dropna()
                if len(x) >= 3 and len(y) >= 3:
                    comp.append(dict(var=var, window=col, start_class=cls, n_real=len(x), n_pseudo=len(y),
                                     median_abs_real=float(x.median()), median_abs_pseudo=float(y.median()),
                                     p90_abs_real=float(x.quantile(.9)), p90_abs_pseudo=float(y.quantile(.9)),
                                     mw_p_greater=float(stats.mannwhitneyu(x, y, alternative="greater").pvalue)))
    C = pd.DataFrame(comp); C.to_csv(out / "real_vs_pseudo_comparison.csv", index=False)
    # campaign-bootstrap CI of the median |offset| excess (real starts of a class minus pseudo-starts), T only
    rng = np.random.default_rng(20261109); bx = []
    pT = XT[XT.kind == "pseudo_start"]
    for cls in ("cold", "warm", "intermediate", "all"):
        rT = XT[(XT.kind == "real_start") & ((XT.start_class == cls) | (cls == "all"))]
        for a, b in WINDOWS:
            col = f"off_{a}_{b}"
            x = rT[["campaign", col]].dropna(); y = pT[["campaign", col]].dropna()
            if len(x) < 3:
                continue
            px = y.groupby("campaign")[col].apply(lambda v: v.abs().to_numpy())
            reps = []
            for _ in range(2000):
                xs = x[col].abs().to_numpy()[rng.integers(0, len(x), len(x))]
                ks = rng.integers(0, len(px), len(px)); ys = np.concatenate([px.iloc[k] for k in ks])
                reps.append(np.median(xs) - np.median(ys))
            bx.append(dict(start_class=cls, window=col, n_real=len(x), n_pseudo=len(y), n_pseudo_campaigns=len(px),
                           median_excess_c=float(x[col].abs().median() - y[col].abs().median()),
                           ci_lo=float(np.percentile(reps, 2.5)), ci_hi=float(np.percentile(reps, 97.5))))
    B = pd.DataFrame(bx); B.to_csv(out / "median_abs_offset_excess_bootstrap_T.csv", index=False)
    summ["median_abs_offset_excess_T"] = B.to_dict("records")
    summ["ventilated_share_0_300_real_starts"] = dict(median=float(rs.ventilated_share_0_300.median()),
                                                      p10=float(rs.ventilated_share_0_300.quantile(.1)))
    print(B.round(3).to_string())
    # offset profile per window (T): affected vs reference vs pseudo
    prof = []
    for a, b in WINDOWS:
        col = f"off_{a}_{b}"
        for lab, sel in (("AFFECTED_v02", (XT.kind == "real_start") & (XT.group == "AFFECTED_v02")),
                         ("CAP_GREW_v02", (XT.kind == "real_start") & (XT.group == "CAP_GREW_v02")),
                         ("LONG_CONFIRM_preexisting", (XT.kind == "real_start") & (XT.group == "LONG_CONFIRM_preexisting")),
                         ("reference_real", (XT.kind == "real_start") & (XT.group == "reference")),
                         ("cold_real", (XT.kind == "real_start") & (XT.start_class == "cold")),
                         ("warm_real", (XT.kind == "real_start") & (XT.start_class == "warm")),
                         ("pseudo", XT.kind == "pseudo_start")):
            v = XT.loc[sel, col].dropna()
            prof.append(dict(window=col, set=lab, n=len(v), median_abs=float(v.abs().median()) if len(v) else np.nan,
                             p75_abs=float(v.abs().quantile(.75)) if len(v) else np.nan,
                             p90_abs=float(v.abs().quantile(.9)) if len(v) else np.nan, median_signed=float(v.median()) if len(v) else np.nan))
    P = pd.DataFrame(prof); P.to_csv(out / "offset_profile_T.csv", index=False)
    summ["offset_profile_T"] = P.to_dict("records")
    (out / "evidence_summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    # figures
    sel = M[M.group != "reference"].campaign.tolist()
    fig, axs = plt.subplots(len(sel), 1, figsize=(11, 2.1 * len(sel)), sharex=True)
    for ax, cid in zip(np.atleast_1d(axs), sel):
        t, s = traces[cid]; m = t <= 2400
        ax.plot(t[m] / 60, s[T].to_numpy()[m], lw=.7, color="C0")
        ax2 = ax.twinx(); ax2.plot(t[m] / 60, s[RH].to_numpy()[m], lw=.6, color="C1", alpha=.7); ax2.set_ylabel("RH %", fontsize=7, color="C1")
        r = M[M.campaign == cid].iloc[0]
        ax.axvspan(0, r.stab_s_v02 / 60, color="orange", alpha=.15); ax.axvline(5, color="k", ls="--", lw=.8)
        ax.set_title(f"{cid[:40]}  [{r.group}, start {r.start_class}, gap {r.gap_prev_session_min:.1f} min]", fontsize=8)
        ax.set_ylabel("T °C", fontsize=7)
    np.atleast_1d(axs)[-1].set_xlabel("minutes from session start (orange = v0.2 warm-up flag; dashed = 5 min)")
    fig.tight_layout(); fig.savefig(out / "fig_affected_traces.png", dpi=120); plt.close(fig)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    for lab, c in (("pseudo", "0.6"), ("warm_real", "C2"), ("cold_real", "C3"), ("AFFECTED_v02", "C1")):
        q = P[P.set == lab]
        ax[0].plot(range(len(q)), q.median_abs, "o-", color=c, label=f"{lab} (median)")
        ax[0].plot(range(len(q)), q.p90_abs, ":", color=c)
    ax[0].set_xticks(range(len(WINDOWS))); ax[0].set_xticklabels([f"{a}-{b}s" for a, b in WINDOWS])
    ax[0].set_ylabel("|T(window) - T(600-1200 s)| °C"); ax[0].legend(fontsize=7); ax[0].set_title("Offset vs later phase (dotted = p90)")
    ax[1].scatter(ps.tau_s + np.random.default_rng(0).normal(0, 4, len(ps)), ps.amp_b.abs(), s=10, color="0.6", label="pseudo-starts")
    for cls, c in (("warm", "C2"), ("intermediate", "C0"), ("cold", "C3"), ("unknown", "k")):
        q = rs[rs.start_class == cls]
        ax[1].scatter(q.tau_s, q.amp_b.abs(), s=22, color=c, label=f"real start: {cls}")
    ax[1].axhline(b95, color="k", ls="--", lw=.8); ax[1].set_xscale("log"); ax[1].set_xlabel("best tau [s]"); ax[1].set_ylabel("|b| exp amplitude °C")
    ax[1].legend(fontsize=7); ax[1].set_title("Transient fit (0-900 s): real vs pseudo starts")
    fig.tight_layout(); fig.savefig(out / "fig_offset_and_transient.png", dpi=120); plt.close(fig)
    print(json.dumps({k: v for k, v in summ.items() if k != "offset_profile_T"}, indent=1, default=str))
    print(P.round(3).to_string()); print(C.round(3).to_string())


if __name__ == "__main__":
    main(Path(sys.argv[1]))