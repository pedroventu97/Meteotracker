"""QC mask audit E0: flag_table_E0 'exclude' severities vs pipeline keep_<profile> (read-only).

Writes ONLY a new folder outputs/qc_mask_audit_E0_<YYYYMMDDTHHMM Europe/Rome>/. Reads e0_qc_split_20261105T1703,
config/flag_policy.csv, e0/qc_flag_schema_E0_v0.1.yaml. Declares no QC official; changes no config.
Usage: python e0/run_qc_mask_audit_e0.py [--n-boot 1000]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meteotracker_qc.p1_repeatability import Params, bootstrap_pooled, build_passes, pass_pairs, pooled  # noqa: E402
from meteotracker_qc.qc_mask_audit import (  # noqa: E402
    agreement_summary, attach_state, confusion, is_flag_column, mapping_table, per_code_disagreement,
    point_flag_state, rates_by, read_policy_lines, read_schema_lines)

ROME = ZoneInfo("Europe/Rome")
E0 = ROOT / "outputs" / "e0_qc_split_20261105T1703"
SCHEMA = ROOT / "e0" / "qc_flag_schema_E0_v0.1.yaml"
POLICY = ROOT / "config" / "flag_policy.csv"
KEEPS = ("keep_permissive", "keep_recommended", "keep_restrictive")
EXTRA = ["source_row", "canonical_temperature_c", "canonical_altitude_m", "speed_gps_kmh", "segment_id",
         "segment_start_reason", "stabilization_seconds_from_segment_start", "recovery_seconds_elapsed",
         "stabilization_window_end_reason", "dt_s", *KEEPS, "qc_exclusion_reasons_permissive",
         "qc_exclusion_reasons_recommended", "qc_exclusion_reasons_restrictive"]
ALT_BINS = [-1e9, 50, 75, 100, 150, 250, 1e9]
ALT_LABELS = ["<50", "50-75", "75-100", "100-150", "150-250", ">250"]


def log(m):
    print(f"[{datetime.now(ROME):%H:%M:%S}] {m}", flush=True)


def tobool(s):
    return s.astype(str).str.strip().str.lower().eq("true")


def load():
    from pyproj import Transformer
    split = pd.read_parquet(E0 / "split_assignments_E0.parquet")
    parts = []
    for cid in sorted(split.canonical_campaign_id.unique()):
        f = sorted((E0 / "campaigns" / cid).glob("*_flagged.csv"))
        assert len(f) == 1, cid
        x = pd.read_csv(f[0], usecols=lambda c: c in EXTRA or is_flag_column(c), low_memory=False)
        x["canonical_campaign_id"] = cid
        parts.append(x)
    fl = pd.concat(parts, ignore_index=True)
    flag_cols = [c for c in fl.columns if is_flag_column(c)]
    for c in flag_cols + list(KEEPS):
        fl[c] = tobool(fl[c])
    d = split.merge(fl, on=["canonical_campaign_id", "source_row"], how="left", validate="one_to_one")
    ft = pd.read_parquet(E0 / "flag_table_E0.parquet")
    d = attach_state(d, point_flag_state(ft))
    tr = Transformer.from_crs(4326, 32632, always_xy=True)
    d["x"], d["y"] = tr.transform(d.lon.to_numpy(), d.lat.to_numpy())
    d["hour_rome"] = d.time_local.astype(str).str[11:13].astype(int)
    d["alt_band"] = pd.cut(d.canonical_altitude_m, ALT_BINS, labels=ALT_LABELS).astype(str)
    d["route"] = d["route"].where(d["route"].notna() & (d["route"].astype(str) != ""), None)
    d["route_f"] = d["route"].fillna("NA")
    return d, ft, flag_cols


def disagreement_cat(d, keep="keep_recommended"):
    k = d[keep]
    return np.select([k & ~d.ft_exclude, ~k & d.ft_exclude, k & d.ft_exclude], ["agree_keep", "agree_drop", "ft_only_drop"],
                     "pipeline_only_drop")


def figures(out, d, codes, rb):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fd = out / "figures"
    # fig1: per-code bar
    t = codes[codes["mask"] == "keep_recommended"].copy()
    a = t[t.direction == "ft_exclude_but_pipeline_keeps"].head(8)
    b = t[t.direction == "pipeline_drops_but_no_ft_exclude"].head(6)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    lab = [f"{c}  (sole {s})" for c, s in zip(a.code, a.n_sole)] + [f"{c}  (sole {s})" for c, s in zip(b.code, b.n_sole)]
    val = list(a.n_points) + list(-b.n_points)
    col = ["tab:purple"] * len(a) + ["tab:orange"] * len(b)
    ax.barh(range(len(val)), val, color=col)
    ax.set_yticks(range(len(val)))
    ax.set_yticklabels(lab, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="k", lw=.8)
    ax.set_xlabel("punti  (viola >0: flag table exclude ma recommended tiene;  arancio <0: recommended scarta senza exclude)")
    ax.set_title("flag_table_E0 vs keep_recommended: disaccordo per codice\n(punti; un punto con piu' codici conta per ciascuno; sole = unico codice)", fontsize=10)
    fig.tight_layout(); fig.savefig(fd / "fig1_disagreement_by_code.png", dpi=140); plt.close(fig)
    # fig2: map of 500 m blocks
    try:
        import geopandas as gpd
        aoi = gpd.read_file(ROOT / "data" / "aoi" / "bologna_e0_aoi_v0.1.geojson").to_crs(32632)
    except Exception:  # noqa: BLE001
        aoi = None
    bb = rb.copy()
    ij = bb.spatial_block_id.astype(str).str.split("_", expand=True).astype(int)
    bb["x0"], bb["y0"] = ij[0] * 500, ij[1] * 500
    from matplotlib.collections import PatchCollection
    from matplotlib.patches import Rectangle
    fig, axs = plt.subplots(1, 2, figsize=(14, 7.5), sharex=True, sharey=True)
    for ax, c, ttl, cm in [(axs[0], "ft_only_rate", "flag table exclude, recommended tiene", "Purples"),
                           (axs[1], "pipe_only_rate", "recommended scarta, nessun exclude", "Oranges")]:
        pcl = PatchCollection([Rectangle((x, y), 500, 500) for x, y in zip(bb.x0, bb.y0)], cmap=cm, edgecolor="k", linewidth=.2)
        pcl.set_array(bb[c].to_numpy()); pcl.set_clim(0, 1)
        ax.add_collection(pcl)
        if aoi is not None:
            aoi.boundary.plot(ax=ax, color="k", lw=.8)
        ax.set_title(f"Quota per blocco 500 m: {ttl}", fontsize=10)
        ax.set_aspect("equal"); fig.colorbar(pcl, ax=ax, shrink=.7)
    if aoi is not None:
        x0, y0, x1, y1 = aoi.total_bounds
    else:
        x0, y0, x1, y1 = bb.x0.min(), bb.y0.min(), bb.x0.max() + 500, bb.y0.max() + 500
    axs[0].set_xlim(x0 - 1500, x1 + 1500); axs[0].set_ylim(y0 - 1500, y1 + 1500)
    fig.suptitle("Disaccordo per blocco 500 m (n>=50 punti; EPSG:32632; contorno = AOI Comune di Bologna; blocchi fuori AOI non mostrati)")
    fig.tight_layout(); fig.savefig(fd / "fig2_map_blocks_disagreement.png", dpi=130); plt.close(fig)
    # fig3: hour + altitude band
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, by, order in [(axs[0], "hour_rome", sorted(d.hour_rome.unique())), (axs[1], "alt_band", ALT_LABELS)]:
        r = rates_by(d, by).set_index(by).reindex(order)
        x = np.arange(len(r))
        ax.bar(x, r.ft_only_rate, color="tab:purple", label="flag table exclude, recommended tiene")
        ax.bar(x, r.pipe_only_rate, bottom=r.ft_only_rate, color="tab:orange", label="recommended scarta, nessun exclude")
        ax.set_xticks(x); ax.set_xticklabels([f"{v}\n(n={int(n)})" for v, n in zip(r.index, r.n)], fontsize=7)
        ax.set_ylabel("quota di punti in disaccordo"); ax.set_ylim(0, 1)
        ax.set_title({"hour_rome": "per ora locale (Europe/Rome)", "alt_band": "per fascia di quota (m)"}[by])
    axs[0].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(fd / "fig3_hour_altitude.png", dpi=140); plt.close(fig)
    # fig4: per campaign
    r = rates_by(d, "canonical_campaign_id").sort_values("disagree_rate")
    fig, ax = plt.subplots(figsize=(9, 10))
    y = np.arange(len(r))
    ax.barh(y, r.ft_only_rate, color="tab:purple"); ax.barh(y, r.pipe_only_rate, left=r.ft_only_rate, color="tab:orange")
    ax.set_yticks(y); ax.set_yticklabels([c[:22] for c in r.canonical_campaign_id], fontsize=6)
    ax.set_xlabel("quota di punti in disaccordo (viola: FT-only exclude; arancio: pipeline-only drop)"); ax.set_xlim(0, 1)
    fig.tight_layout(); fig.savefig(fd / "fig4_campaign_disagreement.png", dpi=140); plt.close(fig)


def examples(d):
    ex = []
    k = d.keep_recommended

    def pick(mask, label):
        g = d[mask]
        if g.empty:
            return
        cid = g.canonical_campaign_id.value_counts().index[0]
        g = g[g.canonical_campaign_id == cid].sort_values("source_row")
        r = g.iloc[len(g) // 2]
        cols = ["canonical_campaign_id", "source_row", "time_local", "lat", "lon", "route", "spatial_block_id",
                "canonical_altitude_m", "speed_gps_kmh", "canonical_temperature_c", "ft_exclude_codes", "ft_warn_codes",
                "qc_exclusion_reasons_recommended", "qc_exclusion_reasons_restrictive", "keep_permissive", "keep_recommended",
                "keep_restrictive", "segment_id", "segment_start_reason", "stabilization_seconds_from_segment_start",
                "recovery_seconds_elapsed"]
        row = {c: (r[c].item() if hasattr(r[c], "item") else r[c]) for c in cols if c in r.index}
        row["example"] = label
        row["n_points_same_category_in_campaign"] = int(len(g))
        ex.append(row)

    codes = d.ft_exclude_codes.fillna("")
    pick(k & (codes == "qc_segment_restart_recovery"), "A. segment_restart_recovery unico exclude FT, recommended tiene")
    pick(k & (codes == "qc_unrealistic_acceleration"), "B. unrealistic_acceleration unico exclude FT, recommended tiene (solo restrictive scarta)")
    pick(k & (codes == "qc_post_stop_recovery"), "C. post_stop_recovery unico exclude FT, recommended tiene (policy INFO_ONLY)")
    pick(~k & ~d.ft_exclude & d.qc_exclusion_reasons_recommended.fillna("").eq("qc_gps_freeze"), "D. gps_freeze: recommended scarta, FT solo warn")
    pick(~k & d.ft_exclude & codes.str.contains("qc_sensor_stabilization"), "E. sensor_stabilization: accordo (entrambi scartano)")
    return pd.DataFrame(ex)


def p1_impact(d, n_boot):
    prm = Params(n_boot=n_boot)
    pts = d.rename(columns={"canonical_campaign_id": "campaign", "canonical_temperature_c": "T", "canonical_altitude_m": "alt"})
    pts["t"] = pd.to_datetime(pts.time_utc, utc=True)
    masks = {"recommended": pts.keep_recommended,
             "consensus_rec_and_no_ft_exclude": pts.keep_recommended & ~pts.ft_exclude,
             "union_rec_or_no_ft_exclude": pts.keep_recommended | ~pts.ft_exclude,
             "flagtable_exclude": ~pts.ft_exclude}
    rows = []
    for mname, m in masks.items():
        p = pts[m & pts["T"].notna()]
        for lt, lcol in (("route", "route"), ("spatial_block", "spatial_block_id")):
            passes = build_passes(p, lcol, prm)
            pc = passes.groupby(lcol).campaign.nunique()
            elig = set(pc[pc >= prm.min_campaigns_loc].index)
            for var in ("centered", "detrended"):
                P, _ = pass_pairs(passes, lcol, var, prm, eligible_locs=elig)
                D = P[P.pair_type == "diff_day"] if len(P) else P
                o = pooled(D)
                o.update(bootstrap_pooled(D, prm.n_boot, np.random.default_rng(prm.seed)) if len(D) >= 2 else {})
                o.update(mask=mname, n_points_kept=int(len(p)), loc_type=lt, variant=var, n_eligible_locations=len(elig),
                         share_same_campaign_all=float((P.pair_type == "same_campaign").mean()) if len(P) else np.nan)
                rows.append(o)
                log(f"P1 {mname}|{lt}|{var}: R={o.get('R')} ci={o.get('R_ci')} n={o.get('n_pairs')}")
    T = pd.DataFrame(rows)
    for k in ("R_ci", "fisher_r_ci", "rmsd_ci"):
        T[k + "_lo"] = T[k].map(lambda v: v[0] if isinstance(v, list) else np.nan)
        T[k + "_hi"] = T[k].map(lambda v: v[1] if isinstance(v, list) else np.nan)
        T = T.drop(columns=k)
    front = ["mask", "n_points_kept", "loc_type", "variant", "n_pairs", "n_campaigns", "n_locations", "n_eligible_locations",
             "R", "R_ci_lo", "R_ci_hi", "R_ci_includes_0", "fisher_r", "fisher_r_ci_lo", "fisher_r_ci_hi", "rmsd_c"]
    return T[[c for c in front if c in T] + [c for c in T if c not in front]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--figures-only", type=str, default=None, help="regenerate figures inside an existing audit folder")
    a = ap.parse_args()
    if a.figures_only:
        out = Path(a.figures_only)
        if not out.name.startswith("qc_mask_audit_E0_"):
            raise SystemExit("figures-only works only on a qc_mask_audit_E0_* folder")
        d, _, _ = load()
        figures(out, d, pd.read_csv(out / "disagreement_by_code.csv"), pd.read_csv(out / "rates_by_block.csv"))
        log("figures regenerated")
        return
    t0 = time.time()
    now = datetime.now(ROME)
    out = ROOT / "outputs" / f"qc_mask_audit_E0_{now:%Y%m%dT%H%M}"
    if out.exists():
        raise SystemExit(f"exists: {out}")
    (out / "figures").mkdir(parents=True)
    log(f"output {out}")
    d, ft, flag_cols = load()
    log(f"points {len(d)}; ft rows {len(ft)}; flag cols {len(flag_cols)}")
    # 1. confusion
    conf = pd.concat([confusion(d, k) for k in KEEPS]); conf.to_csv(out / "confusion_global.csv", index=False)
    confc = pd.concat([confusion(d, k, by="canonical_campaign_id") for k in KEEPS]); confc.to_csv(out / "confusion_by_campaign.csv", index=False)
    agr = pd.DataFrame([agreement_summary(d, k) for k in KEEPS]); agr.to_csv(out / "agreement_summary.csv", index=False)
    agc = pd.DataFrame([dict(canonical_campaign_id=c, **agreement_summary(g, "keep_recommended"))
                        for c, g in d.groupby("canonical_campaign_id")]); agc.to_csv(out / "agreement_by_campaign_recommended.csv", index=False)
    # 2. per code + mapping
    codes = pd.concat([per_code_disagreement(d, k, f"qc_exclusion_reasons_{k.split('_')[1]}") for k in KEEPS])
    codes.to_csv(out / "disagreement_by_code.csv", index=False)
    f = ft[ft.source_row >= 0]
    ft_counts = f.drop_duplicates(["canonical_campaign_id", "source_row", "flag_code"]).flag_code.value_counts().to_dict()
    flag_counts = {c: int(d[c].sum()) for c in flag_cols}
    MT = mapping_table(read_schema_lines(SCHEMA), read_policy_lines(POLICY), flag_counts, ft_counts)
    MT.to_csv(out / "severity_mapping_schema_vs_policy.csv", index=False)
    alias = []
    for a1, a2 in [("qc_time_duplicate", "qc_duplicate_timestamp"), ("qc_temp_spike", "qc_temp_isolated_spike"),
                   ("qc_unrealistic_acceleration", "qc_impossible_acceleration"), ("qc_time_order", "qc_nonmonotonic_timestamp")]:
        if a1 in d and a2 in d:
            alias.append(dict(a=a1, b=a2, n_a=int(d[a1].sum()), n_b=int(d[a2].sum()), n_both=int((d[a1] & d[a2]).sum()),
                              identical=bool((d[a1] == d[a2]).all())))
    if {"qc_spatial_jump", "qc_gps_jump", "qc_isolated_position_outlier"} <= set(d.columns):
        u = d.qc_gps_jump | d.qc_isolated_position_outlier
        alias.append(dict(a="qc_gps_jump|qc_isolated_position_outlier", b="qc_spatial_jump", n_a=int(u.sum()),
                          n_b=int(d.qc_spatial_jump.sum()), n_both=int((u & d.qc_spatial_jump).sum()),
                          identical=bool((u == d.qc_spatial_jump).all())))
    pd.DataFrame(alias).to_csv(out / "alias_check.csv", index=False)
    # 3. distributions
    d["cat_recommended"] = disagreement_cat(d)
    rr = rates_by(d, "route_f", min_n=200); rr.to_csv(out / "rates_by_route.csv", index=False)
    rb = rates_by(d, "spatial_block_id", min_n=50); rb.to_csv(out / "rates_by_block.csv", index=False)
    for by in ("alt_band", "hour_rome", "canonical_campaign_id", "day"):
        rates_by(d, by).to_csv(out / f"rates_by_{by}.csv", index=False)
    EX = examples(d); EX.to_csv(out / "examples.csv", index=False)
    # restart-recovery context: duration of the flagged windows
    srr = d[d.qc_segment_restart_recovery] if "qc_segment_restart_recovery" in d else d.iloc[:0]
    ctx = dict(n_points=int(len(srr)), share_of_all_points=float(len(srr) / len(d)),
               stabilization_seconds_quantiles=srr.stabilization_seconds_from_segment_start.quantile([.1, .5, .9]).round(1).tolist()
               if "stabilization_seconds_from_segment_start" in srr and len(srr) else None,
               segment_start_reason_counts=srr.segment_start_reason.value_counts().head(8).to_dict() if "segment_start_reason" in srr else None,
               share_campaign_points_flagged_median=float(d.groupby("canonical_campaign_id").qc_segment_restart_recovery.mean().median())
               if "qc_segment_restart_recovery" in d else None)
    # 4. permissive trace
    allsci = MT[MT.policy_action == "EXCLUDE_ALL_SCIENTIFIC"][["code", "policy_line", "n_points_flag_true"]].to_dict("records")
    perm = dict(n_keep_permissive_false=int((~d.keep_permissive).sum()),
                exclude_all_scientific_flags=allsci,
                exclude_recommended_flags=MT[MT.policy_action == "EXCLUDE_RECOMMENDED"].code.tolist(),
                exclude_restrictive_flags=MT[MT.policy_action == "EXCLUDE_RESTRICTIVE"].code.tolist())
    # 5. P1 impact
    P1 = p1_impact(d, a.n_boot); P1.to_csv(out / "p1_impact_masks.csv", index=False)
    # 6. summary json
    top = codes[codes["mask"] == "keep_recommended"].sort_values("n_points", ascending=False)
    S = dict(built_at_europe_rome=now.isoformat(timespec="seconds"), output_root=str(out),
             code_commit=subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
             n_points=int(len(d)), n_flag_rows=int(len(ft)), n_file_level_flag_rows=int((ft.source_row < 0).sum()),
             ft_state_counts=d.ft_state.value_counts().to_dict(),
             agreement=agr.to_dict("records"), confusion_global=conf.to_dict("records"),
             top_codes_recommended=top.head(12).to_dict("records"),
             mapping_mismatches=MT[MT.status.str.startswith(("MISMATCH", "schema_only", "policy_only_not"))].to_dict("records"),
             alias_check=alias, segment_restart_recovery_context=ctx, permissive_trace=perm,
             p1_impact=P1.to_dict("records"),
             campaign_agreement_range=[float(agc.agreement.min()), float(agc.agreement.max())],
             elapsed_s=round(time.time() - t0, 1))
    json.dump(S, open(out / "summary.json", "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    try:
        figures(out, d, codes, rb)
    except Exception as e:  # noqa: BLE001
        log(f"figure error {e}")
    log(f"done {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
