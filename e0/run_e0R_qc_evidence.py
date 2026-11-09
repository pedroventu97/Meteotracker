"""E0-QC-R step C: empirical checks pre-registered in e0/QC_R_CRITERIA_E0.md (R1-R5).

Read-only on data/raw and on every existing output. Runs the (dt=0-fixed) detectors in memory with the
recommended v0.1 thresholds (config/qc_recommended.yaml; the policy file does not affect detector flags) and, for
the before/after comparison, the same config with time.legacy_nonpositive_dt_segment_break=true.
Writes ONLY a new folder outputs/e0R_qc_evidence_<YYYYMMDDTHHMM Europe/Rome>/. No P1 is computed here.

Usage: python e0/run_e0R_qc_evidence.py [--n-boot 1000]
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meteotracker_qc import qc_r_evidence as ev  # noqa: E402
from meteotracker_qc.pipeline import MeteotrackerQC  # noqa: E402

ROME = ZoneInfo("Europe/Rome")
SEED = 20261109


def log(m):
    print(f"[{datetime.now(ROME):%H:%M:%S}] {m}", flush=True)


def git_head():
    try:
        h = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                        text=True).strip()
        return h + ("-dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def canonical_manifest():
    m = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    return m[(m.is_canonical.astype(str) == "True") & (m.exclude_from_analysis.astype(str) != "True")]


def legacy_qc(tmpdir: Path) -> MeteotrackerQC:
    cfg = yaml.safe_load((ROOT / "config" / "qc_recommended.yaml").read_text(encoding="utf-8"))
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("time", {})["legacy_nonpositive_dt_segment_break"] = True
    p = tmpdir / "qc_recommended_legacy_dt0.yaml"
    p.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (tmpdir / "flag_policy.csv").write_bytes((ROOT / "config" / "flag_policy.csv").read_bytes())
    return MeteotrackerQC(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--limit", type=int, default=0, help="first N campaigns only (smoke test)")
    a = ap.parse_args()
    now = datetime.now(ROME)
    out = ROOT / "outputs" / f"e0R_qc_evidence_{now:%Y%m%dT%H%M}{'_smoke' if a.limit else ''}"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    (out / "figures").mkdir(parents=True)
    rng = np.random.default_rng(SEED)
    qc = MeteotrackerQC(ROOT / "config" / "qc_recommended.yaml")
    tmp = Path(tempfile.mkdtemp(prefix="e0R_legacy_"))
    qc_old = legacy_qc(tmp)
    man = canonical_manifest().sort_values("canonical_campaign_id")
    if a.limit:
        man = man.head(a.limit)
    R1, STEP, EVB, CTB, ACC, FRZ, SEGCMP, CURDUR = [], [], [], [], [], [], [], []
    for k, (sf, cid) in enumerate(zip(man.source_file, man.canonical_campaign_id), 1):
        raw = ROOT / "data" / "raw" / sf
        df, _ = qc.compute_frame(raw)
        old, _ = qc_old.compute_frame(raw)
        cad = float(df["sampling_interval_expected_seconds"].iloc[0])
        SEGCMP.append(dict(campaign=cid, n_rows=len(df), n_segments_fixed=int(df.segment_id.nunique()),
                           n_segments_legacy=int(old.segment_id.nunique()),
                           restart_recovery_fixed=int(df.qc_segment_restart_recovery.sum()),
                           restart_recovery_legacy=int(old.qc_segment_restart_recovery.sum()),
                           sensor_stab_fixed=int(df.qc_sensor_stabilization.sum()),
                           sensor_stab_legacy=int(old.qc_sensor_stabilization.sum()),
                           accel_fixed=int(df.qc_unrealistic_acceleration.sum()),
                           accel_legacy=int(old.qc_unrealistic_acceleration.sum()),
                           temp_rate_fixed=int(df.qc_temp_rate_anomaly.sum()),
                           temp_rate_legacy=int(old.qc_temp_rate_anomaly.sum()),
                           dup_ts=int(df.qc_duplicate_timestamp.sum()), dup_record=int(df.qc_duplicate_record.sum()),
                           backward_dt=int(df.qc_time_backward_dt.sum()), cadence_s=cad))
        r1 = ev.dt0_rows(df)
        if len(r1):
            R1.append(r1.assign(campaign=cid))
        STEP.append(ev.one_second_steps(df).assign(campaign=cid))
        # R2/R3 events
        ge, se = ev.gap_events(df), ev.stop_events(df)
        for E, kind, nostop in ((ge, "gap", False), (se, "stop", True)):
            if len(E):
                b = ev.deviation_bins(df, E.row.to_numpy(), cad, no_stop_in_window=nostop)
                if len(b):
                    b = b.merge(E.reset_index(drop=True).reset_index().rename(columns={"index": "event_i"})[
                        ["event_i", "duration_s"]], on="event_i")
                    EVB.append(b.assign(campaign=cid, kind=kind))
        # positive control (validation of the method, NOT a decision input): session-start warm-up
        b = ev.deviation_bins(df, np.array([0]), cad, no_stop_in_window=False)
        if len(b):
            EVB.append(b.assign(duration_s=np.nan, campaign=cid, kind="start"))
        cr = ev.control_rows(df, rng)
        for nostop in (False, True):
            b = ev.deviation_bins(df, cr, cad, no_stop_in_window=nostop)
            if len(b):
                CTB.append(b.assign(campaign=cid, kind="ctrl_nostop" if nostop else "ctrl_any"))
        # current detector durations (for comparison with W)
        seg_first = df.segment_id.min()
        rr = df[df.qc_segment_restart_recovery & (df.segment_id != seg_first)]
        for s, g in rr.groupby("segment_id"):
            CURDUR.append(dict(campaign=cid, kind="restart_recovery_slope_detector", segment_id=int(s),
                               flagged_s=float(g.stabilization_seconds_from_segment_start.max()),
                               start_reason=str(g.segment_start_reason.iloc[0])))
        ps = df[df.qc_post_stop_recovery]
        if len(ps):
            run = (~df.qc_post_stop_recovery).cumsum()[df.qc_post_stop_recovery]
            for _, g in ps.groupby(run):
                t = pd.to_datetime(g.time_utc, utc=True)
                CURDUR.append(dict(campaign=cid, kind="post_stop_recovery_detector", segment_id=int(g.segment_id.iloc[0]),
                                   flagged_s=float((t.max() - t.min()).total_seconds()), start_reason="stop"))
        ACC.append(ev.accel_table(df).assign(campaign=cid))
        fb = ev.freeze_blocks(df)
        if len(fb):
            FRZ.append(fb.assign(campaign=cid))
        log(f"[{k}/{len(man)}] {cid[:40]} rows={len(df)} seg {old.segment_id.nunique()}->{df.segment_id.nunique()}")

    S = dict(built_at_europe_rome=now.isoformat(timespec="seconds"), code_commit=git_head(),
             criteria_doc="e0/QC_R_CRITERIA_E0.md", config="config/qc_recommended.yaml (v0.1 thresholds)",
             n_campaigns=int(len(man)), n_boot=a.n_boot, seed=SEED)
    SEG = pd.DataFrame(SEGCMP)
    SEG.to_csv(out / "R1_segments_before_after_by_campaign.csv", index=False)
    S["R1_totals"] = {c: int(SEG[c].sum()) for c in SEG.columns if c not in ("campaign", "cadence_s")}

    # ---- R1
    D0 = pd.concat(R1, ignore_index=True) if R1 else pd.DataFrame()
    ST = pd.concat(STEP, ignore_index=True)
    D0.to_csv(out / "R1_dt0_rows.csv", index=False)
    if len(D0):
        S["R1"] = dict(n_dt0=int(len(D0)), n_exact_copy=int(D0.exact_copy.sum()),
                       n_distinct_content=int((~D0.exact_copy).sum()),
                       patterns_top=D0.pattern.value_counts().head(8).to_dict(),
                       distinct_step_m_median=float(D0.loc[~D0.exact_copy, "step_m"].median()),
                       distinct_dT_abs_median=float(D0.loc[~D0.exact_copy, "dT_abs"].median()),
                       one_s_step_m_median=float(ST.step_m.median()), one_s_dT_abs_median=float(ST.dT_abs.median()),
                       distinct_step_m_p90=float(D0.loc[~D0.exact_copy, "step_m"].quantile(.9)),
                       one_s_step_m_p90=float(ST.step_m.quantile(.9)),
                       campaigns_with_dt0=int(D0.campaign.nunique()))

    # ---- R2 / R3
    EV = pd.concat(EVB, ignore_index=True) if EVB else pd.DataFrame(columns=["campaign", "kind"])
    CT = pd.concat(CTB, ignore_index=True) if CTB else pd.DataFrame(columns=["campaign", "kind"])
    EV["event_key"] = EV.campaign + "|" + EV.kind + "|" + EV.event_i.astype(str)
    CT["event_key"] = CT.campaign + "|" + CT.kind + "|" + CT.event_i.astype(str)
    EV.to_csv(out / "R2R3_event_bins.csv", index=False)
    CT.to_csv(out / "R2R3_control_bins.csv", index=False)
    curves, decisions = [], {}
    for kind, ctrl, rule in (("gap", "ctrl_any", "R2"), ("stop", "ctrl_nostop", "R3"),
                             ("start", "ctrl_any", "positive_control_session_start")):
        e = EV[EV.kind == kind]
        c = CT[CT.kind == ctrl]
        strata = {"all": e, "lt60s": e[e.duration_s < 60], "ge60s": e[e.duration_s >= 60]} if kind != "start" \
            else {"all": e}
        decisions[rule] = {}
        for sname, es in strata.items():
            cur = ev.excess_curves(es, c, a.n_boot, np.random.default_rng(SEED))
            cur = cur.assign(rule=rule, stratum=sname, n_event_units=int(es.event_key.nunique()),
                             n_control_units=int(c.event_key.nunique()))
            curves.append(cur)
            d = ev.decide_recovery(cur)
            early = cur[cur.bin_start < ev.EARLY_S]
            d["ci_halfwidth_first60s_A"] = float(((early.A_hi - early.A_lo) / 2).mean())
            d["ci_halfwidth_first60s_S"] = float(((early.S_hi - early.S_lo) / 2).mean())
            d["S_mean_first60s"] = float(early.S.mean())
            d.update(n_events=int(es.event_key.nunique()), n_campaigns=int(es.campaign.nunique()),
                     n_controls=int(c.event_key.nunique()))
            decisions[rule][sname] = d
    CU = pd.concat(curves, ignore_index=True)
    CU.to_csv(out / "R2R3_excess_curves.csv", index=False)
    CD = pd.DataFrame(CURDUR)
    CD.to_csv(out / "R2R3_current_detector_durations.csv", index=False)
    if len(CD):
        S["current_detector_flagged_s"] = {k: dict(n=int(len(g)), median=float(g.flagged_s.median()),
                                                   p90=float(g.flagged_s.quantile(.9)))
                                           for k, g in CD.groupby("kind")}
    # event counts before the coverage filter
    S["R2R3_decisions"] = decisions

    # ---- R4
    AC = pd.concat(ACC, ignore_index=True)
    AC.to_parquet(out / "R4_acceleration_points.parquet", index=False)
    stdy = AC[AC.steady & AC.a_pos.notna()]
    S["R4_noise_floor_steady_cruise"] = dict(n=int(len(stdy)), p50=float(stdy.a_pos.abs().median()),
                                             p95=float(stdy.a_pos.abs().quantile(.95)),
                                             p99=float(stdy.a_pos.abs().quantile(.99)),
                                             share_gt5=float((stdy.a_pos.abs() > 5).mean()))
    S["R4_all_points"] = dict(n=int(AC.a_pos.notna().sum()), a_pos_p95=float(AC.a_pos.abs().quantile(.95)),
                              a_dop_p95=float(AC.a_dop.abs().quantile(.95)),
                              a_dop_p99=float(AC.a_dop.abs().quantile(.99)))
    sens = []
    for thr in (3, 4, 5, 6, 8, 10):
        f = AC[AC.a_pos.abs() > thr]
        row = dict(threshold_ms2=thr, n_flagged=int(len(f)), share_points=float(len(f) / max(AC.a_pos.notna().sum(), 1)),
                   share_dop_exceeds_thr=float((f.a_dop.abs() > thr).mean()) if len(f) else np.nan,
                   e_pos_p50=float(f.e_pos_max.median()) if len(f) else np.nan,
                   e_pos_p95=float(f.e_pos_max.quantile(.95)) if len(f) else np.nan,
                   share_dt_changed=float(f.dt_changed.mean()) if len(f) else np.nan)
        for cls in ("rumore_gps", "dinamica_plausibile", "non_verificabile"):
            row[f"share_{cls}"] = float((f.cls == cls).mean()) if len(f) else np.nan
        sens.append(row)
    SE = pd.DataFrame(sens)
    SE.to_csv(out / "R4_threshold_sensitivity.csv", index=False)
    S["R4_share_dt_changed_all_points"] = float(AC.loc[AC.a_pos.notna(), "dt_changed"].mean())
    S["R4_decision"] = ev.decide_accel(AC, 5.0)
    pc = AC.groupby("campaign").apply(lambda g: pd.Series(dict(n=g.a_pos.notna().sum(),
                                                                share_flag=(g.a_pos.abs() > 5).mean())),
                                      include_groups=False).reset_index()
    pc.to_csv(out / "R4_flag_share_by_campaign.csv", index=False)

    # ---- R5
    FB = pd.concat(FRZ, ignore_index=True) if FRZ else pd.DataFrame()
    FB.to_csv(out / "R5_freeze_blocks.csv", index=False)
    if len(FB):
        S["R5"] = dict(classes_points=FB.groupby("cls").n_points.sum().to_dict(),
                       classes_blocks=FB.cls.value_counts().to_dict(),
                       D_rel_m_median=float(FB.D_rel_m.median()), D_rel_m_p95=float(FB.D_rel_m.quantile(.95)),
                       duration_s_median=float(FB.duration_s.median()),
                       meteo_varying_share_mean=float(FB.meteo_varying_share.mean()),
                       vdev_max_kmh_max=float(FB.vdev_max_kmh.max()))
    S["R5_decision"] = ev.decide_freeze(FB)

    json.dump(S, open(out / "summary.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))
    try:
        figures(out, D0, ST, CU, AC, SE, FB)
    except Exception as e:  # noqa: BLE001
        log(f"figure error {e}")
    log(f"done -> {out}")
    print(out)


def figures(out, D0, ST, CU, AC, SE, FB):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    f = out / "figures"
    # R1
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    if len(D0):
        D0.pattern.value_counts().head(10)[::-1].plot.barh(ax=ax[0], color="#64748b")
        ax[0].set_title(f"R1: pattern dt (prec-0-succ), n={len(D0)}; copie esatte={int(D0.exact_copy.sum())}")
        bins = np.linspace(0, 40, 41)
        ax[1].hist(ST.step_m.clip(upper=40), bins=bins, density=True, alpha=.5, label="passi dt=1 s")
        ax[1].hist(D0.loc[~D0.exact_copy, "step_m"].clip(upper=40), bins=bins, density=True, alpha=.6,
                   label="riga dt=0, contenuto distinto")
        ax[1].set_xlabel("distanza dalla riga precedente [m]")
        ax[1].legend()
        ax[1].set_title("R1: continuità spaziale")
    fig.tight_layout()
    fig.savefig(f / "R1_dt0.png", dpi=130)
    plt.close(fig)
    # R2/R3
    fig, axs = plt.subplots(3, 3, figsize=(14, 10), sharex=True)
    names = {"R2": "gap", "R3": "sosta", "positive_control_session_start": "CONTROLLO POSITIVO avvio sessione"}
    for r, rule in enumerate(("R2", "R3", "positive_control_session_start")):
        for c, st in enumerate(("all", "lt60s", "ge60s")):
            ax = axs[r, c]
            cu = CU[(CU.rule == rule) & (CU.stratum == st)]
            if cu.empty:
                ax.set_axis_off()
                continue
            x = cu.bin_start + 5
            ax.fill_between(x, cu.A_lo, cu.A_hi, alpha=.25, color="#b91c1c")
            ax.plot(x, cu.A, color="#b91c1c", label="A(t)=|D|ev−|D|ctrl")
            ax.fill_between(x, cu.S_lo, cu.S_hi, alpha=.2, color="#1d4ed8")
            ax.plot(x, cu.S, color="#1d4ed8", label="S(t) con segno")
            for y in (-0.1, 0.1):
                ax.axhline(y, color="k", ls=":", lw=.8)
            ax.axhline(0, color="k", lw=.5)
            n = int(cu.n_event_units.iloc[0]) if len(cu) else 0
            ax.set_title(f"{rule if rule != 'positive_control_session_start' else ''} {names[rule]} {st} (eventi={n})",
                         fontsize=9)
            if r == 2 or (r == 1 and c > 0):
                ax.set_xlabel("s dall'evento")
            if c == 0:
                ax.set_ylabel("eccesso [°C]")
    axs[0, 0].legend(fontsize=7)
    fig.suptitle("Transitorio termico dopo gap reale (R2), dopo sosta (R3) e avvio sessione (controllo positivo) "
                 "vs controllo; IC 95% bootstrap per campagna")
    fig.tight_layout()
    fig.savefig(f / "R2R3_recovery_curves.png", dpi=130)
    plt.close(fig)
    # R4
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    b = np.linspace(0, 15, 61)
    ax[0].hist(AC.a_pos.abs().clip(upper=15).dropna(), bins=b, density=True, alpha=.5, label="|a_pos| tutti")
    st = AC[AC.steady]
    ax[0].hist(st.a_pos.abs().clip(upper=15).dropna(), bins=b, density=True, alpha=.5, label="|a_pos| crociera stabile")
    ax[0].hist(AC.a_dop.abs().clip(upper=15).dropna(), bins=b, density=True, histtype="step", color="k",
               label="|a_dop| tutti")
    ax[0].axvline(5, color="r", ls="--")
    ax[0].set_yscale("log")
    ax[0].legend(fontsize=7)
    ax[0].set_xlabel("m/s²")
    ax[0].set_title("R4: distribuzioni accelerazione")
    for cls, col in (("share_rumore_gps", "#b91c1c"), ("share_dinamica_plausibile", "#15803d"),
                     ("share_non_verificabile", "#a3a3a3")):
        ax[1].plot(SE.threshold_ms2, SE[cls], marker="o", label=cls.replace("share_", ""), color=col)
    ax[1].set_xlabel("soglia m/s²")
    ax[1].set_ylabel("quota dei flag")
    ax[1].legend(fontsize=7)
    ax[1].set_title("R4: classe dei punti flaggati vs soglia")
    ax[2].plot(SE.threshold_ms2, SE.share_points * 100, marker="o")
    ax[2].set_xlabel("soglia m/s²")
    ax[2].set_ylabel("% punti flaggati")
    ax[2].set_title("R4: sensibilità alla soglia")
    fig.tight_layout()
    fig.savefig(f / "R4_acceleration.png", dpi=130)
    plt.close(fig)
    # R5
    if len(FB):
        fig, ax = plt.subplots(1, 2, figsize=(11, 4))
        ax[0].hist(FB.D_rel_m.dropna().clip(upper=200), bins=40, color="#64748b")
        ax[0].axvline(25, color="r", ls="--")
        ax[0].set_xlabel("salto al rilascio D_rel [m]")
        ax[0].set_title("R5: salto al rilascio dei blocchi gps_freeze")
        FB.groupby("cls").n_points.sum().plot.bar(ax=ax[1], color="#0f766e")
        ax[1].set_title("R5: punti per classe")
        fig.tight_layout()
        fig.savefig(f / "R5_gps_freeze.png", dpi=130)
        plt.close(fig)


if __name__ == "__main__":
    main()
