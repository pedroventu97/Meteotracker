"""E0-QC-R final validation, item 1: campaign 2026-05-27 13:08 (AC4D162B317E), warm-up flag 91 -> 1,395 points.

  python e0/run_e0R_final_0527_investigation.py <OUT_DIR>

Read-only on data/raw and on every existing output (v0.1 tree e0_qc_split_20261105T1703, v0.2 tree
e0R_qc_split_20261109T1240). Re-runs only the stabilization detector in memory (same function, same config values)
to attribute the flag to its exact gate and to run counterfactuals. Changes no severity, no threshold, no config.
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
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from meteotracker_qc.stabilization import detect_sensor_stabilization  # noqa: E402

V01 = ROOT / "outputs" / "e0_qc_split_20261105T1703" / "campaigns"
V02 = ROOT / "outputs" / "e0R_qc_split_20261109T1240" / "recommended" / "campaigns"
SPLIT = ROOT / "outputs" / "e0R_qc_split_20261109T1240" / "split_assignments_E0R.parquet"
CAMP = "05-27__20260527T13_08_42_mtdicambo_AC4D162B317E_Bologna-Bologna__99cbc5b816"
PREV = "05-27__20260527T12_58_39_mtdicambo_AC4D162B317E_Bologna-Bologna__d3116f69d4"
RAW = ROOT / "data" / "raw" / "05-27" / "20260527T13_08_42_mtdicambo_AC4D162B317E_Bologna-Bologna.csv"
T = "Temp[°C]"


def std(tree: Path, camp: str) -> pd.DataFrame:
    return pd.read_parquet(next((tree / camp).glob("*_standardized.parquet")))


def cfg(tree: Path, camp: str) -> dict:
    return yaml.safe_load(next((tree / camp).glob("config_used.yaml")).read_text(encoding="utf-8"))


def detector_trace(s: pd.DataFrame, c: dict) -> pd.DataFrame:
    """Row-level gates of stabilization._analyze_segment for a single-segment frame (same formulas)."""
    w, v = c["warmup"], c["ventilation"]
    temps = pd.to_numeric(s[T], errors="coerce")
    dt = s["time_utc"].diff().dt.total_seconds()
    pos = dt[(dt > 0) & np.isfinite(dt)]
    exp_dt = float(pos.median()) if len(pos) >= 3 else 1.0
    dte = dt.fillna(exp_dt)
    el = dte.copy(); el.iloc[0] = 0.0
    sl_dt = dte.copy(); sl_dt.iloc[0] = np.nan
    rows = max(3, int(round(float(w["window_size_s"]) / max(exp_dt, 1e-6))))
    rows += rows % 2 == 0
    med = temps.rolling(rows, center=True, min_periods=1).median()
    nonpos = (sl_dt <= 0).fillna(False)
    slope = med.diff() / sl_dt.where(~nonpos)
    st = slope.abs() < float(w["slope_threshold_c_per_s"])
    if nonpos.any():
        st = st.astype("boolean").mask(nonpos).ffill().fillna(False).astype(bool)
    rid = st.ne(st.shift(1)).cumsum()
    run_el = el.groupby(rid).cumsum()
    conf = st & (run_el >= float(w["min_stable_seconds"]))
    vent = (pd.to_numeric(s["speed_device_kmh"], errors="coerce") > float(v["low_speed_threshold_kmh"])).fillna(False)
    vid = vent.ne(vent.shift(1)).cumsum()
    vsat = (vent & (el.groupby(vid).cumsum() >= float(w["min_ventilated_duration_s"]))).cummax()
    return pd.DataFrame({"elapsed_s": el.cumsum(), "temp_c": temps, "median_c": med, "slope_c_per_s": slope,
                         "row_stable": st, "stable_run_id": rid, "stable_run_elapsed_s": run_el,
                         "slope_confirmed": conf, "ventilated": vent, "ventilation_satisfied": vsat,
                         "qualifying": conf & vsat, "expected_dt_s": exp_dt, "window_rows": rows})


def run_det(s, c, seg=None, speed=True, **over):
    c = json.loads(json.dumps(c)); c["warmup"].update(over)
    r = detect_sensor_stabilization(s[T], config=c, time_utc=s["time_utc"],
                                    segment_id=s["segment_id"] if seg is None else seg,
                                    speed_kmh=s["speed_device_kmh"] if speed else None)
    return int(r.qc_sensor_stabilization.sum()), int(r.qc_segment_restart_recovery.sum())


def campaign_context() -> pd.DataFrame:
    out = []
    for d in sorted(V02.iterdir()):
        if not d.is_dir():
            continue
        s2 = std(V02, d.name)
        try:
            s1 = std(V01, d.name)
        except StopIteration:
            s1 = None
        first = s2[s2.segment_id == s2.segment_id.min()]
        el = first["stabilization_seconds_from_segment_start"]
        stab = first["qc_sensor_stabilization"].to_numpy()
        conf_s = float(el.iloc[int(np.argmin(stab))]) if (~stab).any() else np.nan
        out.append({"canonical_campaign_id": d.name, "rows": len(s2), "segments_v02": int(s2.segment_id.nunique()),
                    "stab_rows_v02": int(s2.qc_sensor_stabilization.sum()),
                    "restart_rows_v02": int(s2.qc_segment_restart_recovery.sum()),
                    "end_reason_first_seg_v02": first["stabilization_window_end_reason"].iloc[0],
                    "confirm_s_from_start_v02": conf_s,
                    "first_segment_duration_s_v02": float(el.max()),
                    "segments_v01": int(s1.segment_id.nunique()) if s1 is not None else np.nan,
                    "stab_rows_v01": int(s1.qc_sensor_stabilization.sum()) if s1 is not None else np.nan,
                    "restart_rows_v01": int(s1.qc_segment_restart_recovery.sum()) if s1 is not None else np.nan,
                    "first_segment_duration_s_v01": float(s1.loc[s1.segment_id == s1.segment_id.min(),
                                                                "stabilization_seconds_from_segment_start"].max())
                    if s1 is not None else np.nan})
    return pd.DataFrame(out)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    res: dict = {"campaign": CAMP}
    s1, s2 = std(V01, CAMP), std(V02, CAMP)
    c2, c1 = cfg(V02, CAMP), cfg(V01, CAMP)
    res["warmup_config_identical_v01_v02"] = c1["warmup"] == c2["warmup"] and c1["ventilation"] == c2["ventilation"]
    res["time_local_first_last"] = [str(s2.time_local.iloc[0]), str(s2.time_local.iloc[-1])]

    # A. raw vs corrected observations
    raw = pd.read_csv(RAW)  # read-only
    a = {"raw_rows": len(raw), "v01_rows": len(s1), "v02_rows": len(s2),
         "rows_identical_order_source_row": bool((s1.source_row.to_numpy() == s2.source_row.to_numpy()).all())}
    for col in [T, "Lat", "Lon", "Speed[km/h]", "Hum[%]"]:
        r = pd.to_numeric(raw[col], errors="coerce").to_numpy()
        a[f"{col}_raw_eq_v02"] = bool(np.allclose(r, pd.to_numeric(s2[col], errors="coerce").to_numpy(), equal_nan=True))
        a[f"{col}_v01_eq_v02"] = bool(np.allclose(pd.to_numeric(s1[col], errors="coerce").to_numpy(),
                                                  pd.to_numeric(s2[col], errors="coerce").to_numpy(), equal_nan=True))
    a["time_raw_eq_v02"] = bool((raw["Time"].astype(str).to_numpy() == s2["time_raw"].astype(str).to_numpy()).all())
    dt = s2.time_utc.diff().dt.total_seconds()
    a["dt_counts"] = {str(k): int(v) for k, v in dt.value_counts().sort_index().items()}
    a["dt0_rows"] = s2.loc[dt == 0, "source_row"].astype(int).tolist()
    a["dt0_exact_duplicates"] = int(s2.qc_duplicate_record.sum())
    a["temp_resolution_c"] = float(np.min(np.diff(np.sort(s2[T].dropna().unique()))))
    res["A_raw_vs_corrected"] = a

    # B. segmentation and flags v0.1 vs v0.2
    b = {"segments_v01": int(s1.segment_id.nunique()), "segments_v02": int(s2.segment_id.nunique()),
         "v01_segment_starts_source_row": s1.groupby("segment_id").source_row.min().astype(int).tolist(),
         "v01_stab": int(s1.qc_sensor_stabilization.sum()), "v01_restart": int(s1.qc_segment_restart_recovery.sum()),
         "v02_stab": int(s2.qc_sensor_stabilization.sum()), "v02_restart": int(s2.qc_segment_restart_recovery.sum())}
    f1 = (s1.qc_sensor_stabilization | s1.qc_segment_restart_recovery).to_numpy()
    f2 = s2.qc_sensor_stabilization.to_numpy()
    b["v02_stab_and_v01_any_warm"] = int((f1 & f2).sum())
    b["v02_stab_only"] = int((f2 & ~f1).sum())
    b["v01_any_warm_only"] = int((f1 & ~f2).sum())
    b["keep_recommended_v01"] = int(s1.keep_recommended.sum()); b["keep_recommended_v02"] = int(s2.keep_recommended.sum())
    k1, k2 = s1.keep_recommended.to_numpy(), s2.keep_recommended.to_numpy()
    b["newly_excluded_recommended"] = int((k1 & ~k2).sum()); b["newly_kept_recommended"] = int((~k1 & k2).sum())
    ne = s2.loc[k1 & ~k2, "qc_exclusion_reasons_recommended"].astype(str).value_counts().head(8)
    b["newly_excluded_reasons_v02"] = {k: int(v) for k, v in ne.items()}
    b["stab_rows_excluded_only_by_stab_v02"] = int((s2.qc_sensor_stabilization & ~s2.keep_recommended &
                                                   (s2.qc_exclusion_reasons_recommended.astype(str) ==
                                                    "qc_sensor_stabilization")).sum())
    res["B_segmentation_flags"] = b

    # C. exact gate attribution on v0.2 (single segment)
    tr = detector_trace(s2, c2)
    q = tr.qualifying.to_numpy()
    bpos = int(np.argmax(q))
    repro = np.zeros(len(tr), bool); repro[:bpos] = True
    c = {"expected_dt_s": float(tr.expected_dt_s.iloc[0]), "window_rows": int(tr.window_rows.iloc[0]),
         "trace_reproduces_pipeline_flag": bool((repro == f2).all()), "boundary_row": bpos,
         "boundary_elapsed_s": float(tr.elapsed_s.iloc[bpos]),
         "first_ventilation_satisfied_s": float(tr.elapsed_s[tr.ventilation_satisfied].iloc[0]),
         "first_slope_confirmed_s": float(tr.elapsed_s[tr.slope_confirmed].iloc[0]),
         "share_rows_unstable_before_boundary": float(1 - tr.row_stable.iloc[:bpos].mean()),
         "share_rows_unstable_after_boundary": float(1 - tr.row_stable.iloc[bpos:].mean())}
    runs = tr[tr.row_stable].groupby("stable_run_id").stable_run_elapsed_s.max()
    pre = tr.iloc[:bpos]; pre_runs = pre[pre.row_stable].groupby("stable_run_id").stable_run_elapsed_s.max()
    c["longest_stable_run_before_boundary_s"] = float(pre_runs.max()) if len(pre_runs) else 0.0
    c["n_stable_runs_ge_30s_before_boundary"] = int((pre_runs >= 30).sum())
    c["n_stable_runs_ge_60s_whole_campaign"] = int((runs >= 60).sum())
    nz = tr.slope_c_per_s.abs()[tr.slope_c_per_s.abs() > 0]
    c["nonzero_slope_min_abs_c_per_s"] = float(nz.min())
    c["nonzero_slope_share_above_threshold"] = float((nz >= c2["warmup"]["slope_threshold_c_per_s"]).mean())
    # physical trend: 60 s and 300 s rolling OLS slope of raw temperature, degC/min
    ts = tr.elapsed_s.to_numpy(); tt = tr.temp_c.to_numpy()
    def roll_slope(win):
        o = np.full(len(ts), np.nan)
        for i in range(len(ts)):
            m = (ts >= ts[i] - win / 2) & (ts <= ts[i] + win / 2)
            if m.sum() >= 5:
                o[i] = np.polyfit(ts[m], tt[m], 1)[0] * 60
        return o
    tr["ols60_c_per_min"] = roll_slope(60); tr["ols300_c_per_min"] = roll_slope(300)
    c["ols300_abs_median_before_boundary_c_per_min"] = float(np.nanmedian(np.abs(tr.ols300_c_per_min[:bpos])))
    c["ols300_abs_median_after_boundary_c_per_min"] = float(np.nanmedian(np.abs(tr.ols300_c_per_min[bpos:])))
    c["detector_threshold_c_per_min"] = float(c2["warmup"]["slope_threshold_c_per_s"]) * 60
    c["temp_first_5min_mean"] = float(tr.temp_c[tr.elapsed_s <= 300].mean())
    c["temp_before_boundary_mean"] = float(tr.temp_c[:bpos].mean()); c["temp_after_boundary_mean"] = float(tr.temp_c[bpos:].mean())
    # sensor continuity with the preceding session of the same device (12:58, ends 13:07:28 UTC)
    sp = std(V02, PREV)
    c["prev_session_end_utc"] = str(sp.time_utc.iloc[-1]); c["this_start_utc"] = str(s2.time_utc.iloc[0])
    c["gap_from_prev_session_s"] = float((s2.time_utc.iloc[0] - sp.time_utc.iloc[-1]).total_seconds())
    c["prev_last_60s_temp_mean"] = float(sp.loc[sp.time_utc >= sp.time_utc.iloc[-1] - pd.Timedelta(seconds=60), T].mean())
    c["this_first_60s_temp_mean"] = float(s2.loc[s2.time_utc <= s2.time_utc.iloc[0] + pd.Timedelta(seconds=60), T].mean())
    c["prev_session_stab_rows"] = int(sp.qc_sensor_stabilization.sum())
    res["C_gate_attribution"] = c
    tr.to_csv(out / "detector_trace_0527_1308.csv", index_label="row")

    # D. counterfactuals (diagnostic only, nothing applied)
    d = {"v02_as_run": run_det(s2, c2), "v02_detector_with_v01_segments": run_det(s2, c2, seg=s1.segment_id),
         "v02_no_ventilation_gate": run_det(s2, c2, speed=False)}
    for thr in (0.01, 0.02, 0.03, 0.05, 0.1):
        d[f"slope_threshold_{thr}"] = run_det(s2, c2, slope_threshold_c_per_s=thr)
    for wsz in (5.0, 11.0, 21.0, 31.0, 61.0):
        d[f"window_size_s_{wsz:g}"] = run_det(s2, c2, window_size_s=wsz)
    for mst in (30, 60, 120):
        d[f"min_stable_seconds_{mst}"] = run_det(s2, c2, min_stable_seconds=mst)
    # cap at max_window_s also when confirmation comes late (proposal P-0527, NOT applied)
    cap = float(c2["warmup"]["max_window_s"])
    d["proposal_cap_max_window_s"] = [int((f2 & (tr.elapsed_s.to_numpy() <= cap)).sum()), 0]
    res["D_counterfactuals_[stab_rows,restart_rows]"] = d

    # E. temporal / spatial distribution
    sa = pd.read_parquet(SPLIT, columns=["canonical_campaign_id", "source_row", "route", "spatial_block_id"])
    sa = sa[sa.canonical_campaign_id == CAMP]
    m = s2[["source_row", "time_local", "Lat", "Lon", "qc_sensor_stabilization", "keep_recommended"]].merge(
        sa, on="source_row", how="left")
    m["min_from_start"] = tr.elapsed_s.to_numpy() / 60
    tb = m.groupby(pd.cut(m.min_from_start, np.arange(0, 60, 5)), observed=False).agg(
        rows=("source_row", "size"), stab=("qc_sensor_stabilization", "sum"))
    tb.to_csv(out / "temporal_distribution_5min.csv")
    rt = m.groupby(m.route.fillna("(none)")).agg(rows=("source_row", "size"), stab=("qc_sensor_stabilization", "sum"),
                                                keep_rec=("keep_recommended", "sum")).sort_values("stab", ascending=False)
    rt.to_csv(out / "route_distribution.csv")
    blk = m.groupby("spatial_block_id").agg(rows=("source_row", "size"), stab=("qc_sensor_stabilization", "sum"))
    res["E_distribution"] = {"routes_touched_by_stab": int((rt.stab > 0).sum() - int("(none)" in rt.index and rt.loc["(none)", "stab"] > 0)),
                             "stab_rows_on_routes": int(rt.drop(index="(none)", errors="ignore").stab.sum()),
                             "blocks_touched_by_stab": int((blk.stab > 0).sum()), "blocks_total": int(len(blk)),
                             "blocks_fully_stab": int(((blk.stab == blk.rows) & (blk.rows > 0)).sum())}

    # F. all campaigns context
    ctx = campaign_context(); ctx.to_csv(out / "stabilization_all_campaigns_v01_v02.csv", index=False)
    res["F_all_campaigns"] = {
        "n": int(len(ctx)),
        "confirm_s_v02_quantiles": {str(p): float(ctx.confirm_s_from_start_v02.quantile(p)) for p in (0.25, 0.5, 0.75, 0.9)},
        "n_confirm_after_max_window_s": int((ctx.confirm_s_from_start_v02 > cap).sum()),
        "campaigns_confirm_after_max_window_s": ctx.loc[ctx.confirm_s_from_start_v02 > cap,
                                                        ["canonical_campaign_id", "confirm_s_from_start_v02", "stab_rows_v02", "stab_rows_v01"]].to_dict("records"),
        "end_reason_counts_v02": ctx.end_reason_first_seg_v02.value_counts().to_dict(),
        "stab_rows_total_v01": int(ctx.stab_rows_v01.sum()), "stab_rows_total_v02": int(ctx.stab_rows_v02.sum()),
        "rank_of_0527_by_stab_rows_v02": int(ctx.stab_rows_v02.rank(ascending=False)[ctx.canonical_campaign_id == CAMP].iloc[0])}

    # figures
    fig, ax = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    x = tr.elapsed_s / 60
    ax[0].plot(x, tr.temp_c, lw=.7, color="0.4", label="Temp raw (0.1 °C)")
    ax[0].plot(x, tr.median_c, lw=1, color="C0", label=f"rolling median {int(tr.window_rows.iloc[0])} rows")
    ax[0].axvspan(0, x.iloc[bpos], color="orange", alpha=.2, label="qc_sensor_stabilization v0.2")
    for st0 in s1.groupby("segment_id").source_row.min().iloc[1:]:
        ax[0].axvline(x[s2.source_row.to_numpy() == st0].iloc[0], color="r", ls=":", lw=1)
    ax[0].axvline(cap / 60, color="k", ls="--", lw=1, label="max_window_s (300 s)")
    ax[0].set_ylabel("°C"); ax[0].legend(fontsize=7, loc="lower left")
    ax[0].set_title("05-27 13:08: warm-up flag v0.2 (orange); red dotted = v0.1 false dt=0 segment breaks")
    ax[1].plot(x, tr.stable_run_elapsed_s.where(tr.row_stable, 0), lw=.8, color="C2")
    ax[1].axhline(c2["warmup"]["min_stable_seconds"], color="k", ls="--", lw=1)
    ax[1].set_ylabel("stable run [s]")
    ax2 = ax[1].twinx(); ax2.plot(x, tr.ols300_c_per_min, color="C3", lw=1); ax2.set_ylabel("OLS 300 s [°C/min]", color="C3")
    ax[2].plot(x, s2.speed_device_kmh, lw=.6, color="C1"); ax[2].axhline(c2["ventilation"]["low_speed_threshold_kmh"], color="k", ls="--", lw=1)
    ax[2].set_ylabel("speed [km/h]"); ax[2].set_xlabel("minutes from start")
    fig.tight_layout(); fig.savefig(out / "fig_0527_1308_detector_trace.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(m.Lon, m.Lat, s=3, c=np.where(m.qc_sensor_stabilization, "orange", "C0"))
    ax.set_title("05-27 13:08: orange = qc_sensor_stabilization v0.2"); ax.set_aspect(1.4)
    fig.savefig(out / "fig_0527_1308_map.png", dpi=130, bbox_inches="tight"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.scatter(ctx.stab_rows_v01, ctx.stab_rows_v02, s=12)
    ax.plot([0, ctx.stab_rows_v02.max()], [0, ctx.stab_rows_v02.max()], "k:", lw=1)
    for _, r in ctx[ctx.stab_rows_v02 - ctx.stab_rows_v01 > 150].iterrows():
        ax.annotate(r.canonical_campaign_id[:5] + " " + r.canonical_campaign_id[16:21], (r.stab_rows_v01, r.stab_rows_v02), fontsize=7)
    ax.set_xlabel("stabilization rows v0.1"); ax.set_ylabel("stabilization rows v0.2"); ax.set_title("All 55 campaigns")
    fig.tight_layout(); fig.savefig(out / "fig_stabilization_v01_v02_all.png", dpi=130); plt.close(fig)

    (out / "investigation_0527_1308.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
