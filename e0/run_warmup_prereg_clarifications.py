"""Warm-up v0.3 pre-registration - CLARIFICATIONS requested by Marco (9/11 15:19). Analysis only, NOT v0.3.

  python e0/run_warmup_prereg_clarifications.py <PREREG_DIR> <SUBDIR_NAME>

Q1  per-campaign table of the campaigns whose keep_recommended changes under the cap-300 variant;
Q3  the 30 real starts by start class, transient counts with Wilson and Clopper-Pearson 95% CIs;
Q4  independent recomputation of keep_recommended (59,209 -> 62,191) from the archived v0.2 parquets, the
    still-excluded points with their other reasons, and an EMPIRICAL check that no other QC flag changes:
    the real pipeline (MeteotrackerQC.compute_frame, in memory, config qc_E0R_recommended_v0.2.yaml unchanged) is
    run twice on every canonical campaign - as is, and with the warm-up output post-processed by the cap-300 rule
    through a wrapper defined HERE (verification harness; no file under src/ or config/ is modified, nothing is
    written to any QC tree) - and every column is diffed.
Reads data/raw read-only. Writes only <PREREG_DIR>/<SUBDIR_NAME>/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest, fisher_exact

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import meteotracker_qc.pipeline as pl  # noqa: E402

V02 = ROOT / "outputs" / "e0R_qc_split_20261109T1240" / "recommended" / "campaigns"
CFG = ROOT / "config" / "qc_E0R_recommended_v0.2.yaml"
CAP = 300.0


def ci(k, n):
    b = binomtest(k, n)
    w = b.proportion_ci(method="wilson"); c = b.proportion_ci(method="exact")
    return dict(k=k, n=n, p=round(k / n, 3), wilson_lo=round(w.low, 3), wilson_hi=round(w.high, 3),
                cp_lo=round(c.low, 3), cp_hi=round(c.high, 3))


def cap_rows(s: pd.DataFrame) -> np.ndarray:
    """cap-300 warm-up flag from an archived/standardized frame (first segment only, late confirmation capped)."""
    first = (s.segment_id == s.segment_id.min()).to_numpy()
    stab = s.qc_sensor_stabilization.to_numpy(bool)
    t = s.stabilization_seconds_from_segment_start.to_numpy(float)
    reason = str(s.loc[first, "stabilization_window_end_reason"].iloc[0])
    if reason != "slope_confirmed_stable":
        return stab.copy()
    return stab & ~(first & (t > CAP))


def q1_q4_archived(out: Path, meta: pd.DataFrame):
    rows, still = [], []
    tot = dict(n_points=0, keep_v02=0, keep_cap300=0, stab_v02=0, stab_cap300=0)
    for d in sorted(V02.iterdir()):
        if not d.is_dir():
            continue
        s = pd.read_parquet(next(d.glob("*_standardized.parquet")))
        stab = s.qc_sensor_stabilization.to_numpy(bool)
        new = cap_rows(s)
        reasons = s.qc_exclusion_reasons_recommended.fillna("").astype(str)
        other = reasons.str.split(";").apply(lambda L: ";".join(x for x in L if x and x != "qc_sensor_stabilization"))
        keep = s.keep_recommended.to_numpy(bool)
        keep_new = keep | (stab & ~new & (other.to_numpy() == ""))
        released = stab & ~new
        t = s.stabilization_seconds_from_segment_start.to_numpy(float)
        tot["n_points"] += len(s); tot["keep_v02"] += int(keep.sum()); tot["keep_cap300"] += int(keep_new.sum())
        tot["stab_v02"] += int(stab.sum()); tot["stab_cap300"] += int(new.sum())
        if released.any():
            m = meta.set_index("campaign").loc[d.name]
            rec = released & keep_new
            st = released & ~keep_new
            for r in other[st].value_counts().items():
                still.append(dict(campaign=d.name, other_exclusion_reasons=r[0], n_points=int(r[1])))
            rows.append(dict(
                campaign=d.name, device=str(m.device)[:12], start_class=m.start_class, gap_prev_session_min=m.gap_prev_session_min,
                group_prereg=m.group, end_reason=m.end_reason, t_confirm_s=m.confirm_s,
                stab_rows_v01=int(m.stab_rows_v01), stab_rows_v02=int(stab.sum()), stab_rows_cap300=int(new.sum()),
                released_rows=int(released.sum()), recovered_to_keep=int(rec.sum()), still_excluded_other_rule=int(st.sum()),
                flagged_window_v02_s=f"0-{t[stab].max():.0f}", flagged_window_cap300_s=f"0-{t[new].max():.0f}",
                released_span_s=f"{t[released].min():.0f}-{t[released].max():.0f}",
                released_duration_s=round(float(t[released].max() - t[released].min()), 0),
                responsible_rule="qc_sensor_stabilization (EXCLUDE_RECOMMENDED): slope gate confirmed after 300 s -> "
                                 "v0.2 flags 0..t_confirm; cap-300 flags 0..300 s"))
    Q1 = pd.DataFrame(rows).sort_values("released_rows", ascending=False)
    Q1.to_csv(out / "q1_campaigns_mask_changes_cap300.csv", index=False)
    S = pd.DataFrame(still); S.to_csv(out / "q4_still_excluded_by_other_rules.csv", index=False)
    return Q1, S, tot


def harness(out: Path):
    """Empirical: run the real pipeline twice in memory and diff every column."""
    orig = pl.detect_sensor_stabilization

    def wrapped(temp, *, config, time_utc=None, segment_id=None, speed_kmh=None):
        w = orig(temp, config=config, time_utc=time_utc, segment_id=segment_id, speed_kmh=speed_kmh)
        seg = pd.Series(segment_id).reset_index(drop=True)
        first = (seg == seg.min()).to_numpy()
        reason = str(w["stabilization_window_end_reason"].to_numpy()[first][0]) if first.any() else ""
        if reason == "slope_confirmed_stable":
            t = w["stabilization_seconds_from_segment_start"].to_numpy(float)
            w = w.copy()
            w["qc_sensor_stabilization"] = w["qc_sensor_stabilization"].to_numpy(bool) & ~(first & (t > CAP))
        return w

    qc = pl.MeteotrackerQC(CFG)
    man = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    man = man[(man.is_canonical.astype(str) == "True") & (man.exclude_from_analysis.astype(str) != "True")]
    diffs, repro = [], []
    for k, (sf, cid) in enumerate(zip(man.source_file, man.canonical_campaign_id), 1):
        pl.detect_sensor_stabilization = orig
        a, _ = qc.compute_frame(ROOT / "data" / "raw" / sf)
        pl.detect_sensor_stabilization = wrapped
        b, _ = qc.compute_frame(ROOT / "data" / "raw" / sf)
        pl.detect_sensor_stabilization = orig
        arch = pd.read_parquet(next((V02 / cid).glob("*_standardized.parquet")), columns=["source_row", "keep_recommended", "qc_sensor_stabilization"])
        repro.append(dict(campaign=cid, baseline_equals_archived_keep=bool((a.keep_recommended.to_numpy(bool) == arch.keep_recommended.to_numpy(bool)).all()),
                          baseline_equals_archived_stab=bool((a.qc_sensor_stabilization.to_numpy(bool) == arch.qc_sensor_stabilization.to_numpy(bool)).all())))
        for c in a.columns:
            x, y = a[c], b[c]
            neq = ~((x == y) | (x.isna() & y.isna()))
            n = int(neq.sum())
            if n:
                diffs.append(dict(campaign=cid, column=c, n_rows_changed=n))
        print(f"[{k}/{len(man)}] {cid[:45]}", flush=True)
    D = pd.DataFrame(diffs, columns=["campaign", "column", "n_rows_changed"])
    D.to_csv(out / "q4_harness_column_diffs_by_campaign.csv", index=False)
    R = pd.DataFrame(repro); R.to_csv(out / "q4_harness_baseline_reproduces_archive.csv", index=False)
    return D, R


def q3(out: Path, meta: pd.DataFrame):
    ev = pd.read_csv(Path(sys.argv[1]) / "evidence" / "start_metrics_real_vs_pseudo.csv")
    ev = ev[ev["var"] == "Temp[°C]"]
    real = ev[ev.kind == "real_start"].copy(); pseudo = ev[ev.kind != "real_start"]
    rows = []
    for cls in ["cold", "intermediate", "warm", "unknown"]:
        r = real[real.start_class == cls]
        rows.append(dict(group=cls, **ci(int(r.transient.sum()), len(r)) if len(r) else dict(n=0)))
    for name, r in [("NOT warm (cold+intermediate+unknown)", real[real.start_class != "warm"]),
                    ("warm (gap <= 15 min)", real[real.start_class == "warm"]),
                    ("ALL real starts", real), ("pseudo-starts (null)", pseudo)]:
        rows.append(dict(group=name, **ci(int(r.transient.sum()), len(r))))
    T = pd.DataFrame(rows); T.to_csv(out / "q3_transients_by_start_class_ci.csv", index=False)
    f_all = fisher_exact([[int(real.transient.sum()), len(real) - int(real.transient.sum())],
                          [int(pseudo.transient.sum()), len(pseudo) - int(pseudo.transient.sum())]], alternative="greater")
    cold = real[real.start_class == "cold"]
    f_cold = fisher_exact([[int(cold.transient.sum()), len(cold) - int(cold.transient.sum())],
                           [int(pseudo.transient.sum()), len(pseudo) - int(pseudo.transient.sum())]], alternative="greater")
    L = real[["campaign", "start_class", "gap_prev_session_min", "group", "off_0_60", "off_300_600", "tau_s", "amp_b", "dBIC",
              "transient", "t_decay_below_0p1C_s"]].sort_values(["start_class", "campaign"])
    L.to_csv(out / "q3_real_starts_list.csv", index=False)
    return T, dict(fisher_one_sided_all_p=round(f_all.pvalue, 3), fisher_one_sided_cold_p=round(f_cold.pvalue, 3)), L


def main():
    pre = Path(sys.argv[1]); out = pre / sys.argv[2]; out.mkdir(parents=True, exist_ok=False)
    meta = pd.read_csv(pre / "evidence" / "campaigns_warmup_meta.csv")
    Q1, S, tot = q1_q4_archived(out, meta)
    T, fis, L = q3(out, meta)
    D, R = harness(out)
    rules = pd.read_parquet(pre / "rules" / "warmup_rule_variants_points.parquet", columns=["campaign", "source_row", "keep_cap300"])
    summ = dict(
        recompute_from_archived_parquets=tot,
        recovered_points=tot["keep_cap300"] - tot["keep_v02"],
        released_from_warmup=tot["stab_v02"] - tot["stab_cap300"],
        cross_check_rules_script_keep_cap300=int(rules.keep_cap300.sum()),
        n_campaigns_changed=int(len(Q1)),
        still_excluded_total=int(S.n_points.sum()) if len(S) else 0,
        transients_fisher=fis,
        harness=dict(n_campaigns=int(len(R)), baseline_reproduces_archive_keep=bool(R.baseline_equals_archived_keep.all()),
                     baseline_reproduces_archive_stab=bool(R.baseline_equals_archived_stab.all()),
                     columns_changed=sorted(D.column.unique().tolist()),
                     campaigns_changed=sorted(D.campaign.unique().tolist()),
                     rows_changed_by_column=D.groupby("column").n_rows_changed.sum().to_dict(),
                     other_qc_flag_columns_changed=sorted(c for c in D.column.unique() if c.startswith("qc_")
                                                          and c not in ("qc_sensor_stabilization",)
                                                          and not c.startswith(("qc_severity", "qc_exclusion_reasons", "qc_reason", "qc_primary", "qc_bitmask", "qc_warning")))),
        note="Analysis only. The harness wrapper lives in this script; src/, config/, severities and v0.1/v0.2 untouched.")
    (out / "clarifications_summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    pd.set_option("display.width", 250)
    print(json.dumps(summ, indent=1, default=str)); print(Q1.drop(columns=["responsible_rule"]).to_string()); print(S.to_string()); print(T.to_string())


if __name__ == "__main__":
    main()