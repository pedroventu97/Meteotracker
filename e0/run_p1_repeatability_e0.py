"""P1 repeatability on the E0 split (55 canonical campaigns).

Inputs (read-only): outputs/e0_qc_split_20261105T1703 (split_assignments_E0, flag_table_E0, per-campaign *_flagged.csv),
data/manifests/campaign_manifest.csv, 20261015 summaries for comparison.
Writes ONLY a new folder outputs/p1_repeatability_E0_<YYYYMMDDTHHMM Europe/Rome>/. No raw/historical overwrite, no git.

QC profiles are applied as masks from the per-row keep_permissive / keep_recommended / keep_restrictive columns that the
single E0 QC run (pipeline, config/qc_recommended.yaml run) already computes for all three profiles; flag_table_E0 encodes
the recommended profile and is cross-checked against keep_recommended. No QC rerun, no row deleted.
No LST / LCZ input is used (LCZ column of the split is not used), so the 2019-2022 training-year exclusion is not triggered.

Usage: python e0/run_p1_repeatability_e0.py [--n-boot 1000] [--quick]
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

from meteotracker_qc.p1_repeatability import (  # noqa: E402
    PROFILES, Params, bootstrap_pooled, build_passes, location_level, pair_stats_from_long, pooled, pass_pairs)
from meteotracker_qc.p1_repeatability.core import campaign_anomalies  # noqa: E402

ROME = ZoneInfo("Europe/Rome")
E0 = ROOT / "outputs" / "e0_qc_split_20261105T1703"
FORBIDDEN = ("recommended_20261015", "corridor_passages_20261015", "repeated_routes_20261015", "pass_anomaly_20261015",
             "short_dt_anomaly_20261015", "lst_campaigns_multiday_20261018", "e0_qc_split_")
LOC_TYPES = {"route": "route", "spatial_block": "spatial_block_id"}
PASS_VARIANTS = ("centered", "detrended")
LOC_VARIANTS = ("centered", "detrended", "detr_alt")
MAIN_LOC_VARIANT = "detrended"
# pipeline masks for the three QC profiles + literal flag-table mask as sensitivity
ALL_PROFILES = (*PROFILES, "flagtable_exclude")


def log(msg):
    print(f"[{datetime.now(ROME):%H:%M:%S}] {msg}", flush=True)


def git_head():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def load_points():
    from pyproj import Transformer
    split = pd.read_parquet(E0 / "split_assignments_E0.parquet")
    man = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    canon = man[(man.is_canonical.astype(str) == "True") & (man.exclude_from_analysis.astype(str) != "True")]
    ids = set(canon.canonical_campaign_id)
    cols = ["source_row", "canonical_temperature_c", "canonical_altitude_m", "speed_gps_kmh",
            "keep_permissive", "keep_recommended", "keep_restrictive"]
    parts = []
    for cid in sorted(ids):
        fs = sorted((E0 / "campaigns" / cid).glob("*_flagged.csv"))
        if len(fs) != 1:
            raise SystemExit(f"expected 1 flagged csv for {cid}, got {len(fs)}")
        f = pd.read_csv(fs[0], usecols=cols, low_memory=False)
        f["canonical_campaign_id"] = cid
        parts.append(f)
    fl = pd.concat(parts, ignore_index=True)
    d = split.merge(fl, on=["canonical_campaign_id", "source_row"], how="left", validate="one_to_one", indicator=True)
    chk = dict(n_manifest_canonical=len(ids), n_split_campaigns=int(split.canonical_campaign_id.nunique()),
               manifest_equals_split=set(split.canonical_campaign_id) == ids, n_obs=int(len(d)),
               n_obs_unmatched=int((d._merge != "both").sum()))
    for p in PROFILES:
        d[f"keep_{p}"] = d[f"keep_{p}"].astype(str) == "True"
        chk[f"n_keep_{p}"] = int(d[f"keep_{p}"].sum())
    # flag table cross-check (recommended profile, exclude severity)
    ft = pd.read_parquet(E0 / "flag_table_E0.parquet", columns=["canonical_campaign_id", "source_row", "severity", "qc_profile"])
    ex = ft[ft.severity == "exclude"].drop_duplicates(["canonical_campaign_id", "source_row"])
    ex["flag_exclude"] = True
    d = d.merge(ex[["canonical_campaign_id", "source_row", "flag_exclude"]], how="left",
                on=["canonical_campaign_id", "source_row"])
    d["flag_exclude"] = d["flag_exclude"].fillna(False).astype(bool)
    # 4th mask: literal flag-table interpretation (mask every row carrying any exclude-severity flag of flag_table_E0)
    d["keep_flagtable_exclude"] = ~d["flag_exclude"]
    chk["n_keep_flagtable_exclude"] = int(d["keep_flagtable_exclude"].sum())
    chk["flag_table_rows"] = int(len(ft))
    chk["flag_table_profiles"] = sorted(ft.qc_profile.astype(str).unique().tolist())
    chk["n_obs_with_exclude_flag"] = int(d.flag_exclude.sum())
    chk["agreement_keep_recommended_vs_no_exclude_flag"] = float((d.keep_recommended == ~d.flag_exclude).mean())
    tr = Transformer.from_crs(4326, 32632, always_xy=True)
    d["x"], d["y"] = tr.transform(d.lon.to_numpy(), d.lat.to_numpy())
    blk = np.floor(d.x / 500).astype(int).astype(str) + "_" + np.floor(d.y / 500).astype(int).astype(str)
    chk["spatial_block_recomputed_agreement"] = float((blk == d.spatial_block_id.astype(str)).mean())
    d = d.rename(columns={"canonical_campaign_id": "campaign", "canonical_temperature_c": "T", "canonical_altitude_m": "alt"})
    d["t"] = pd.to_datetime(d.time_utc, utc=True)
    d["route"] = d["route"].where(d["route"].notna() & (d["route"].astype(str) != ""), None)
    chk["n_obs_T_missing"] = int(d["T"].isna().sum())
    return d, chk


def ci_str(v, ci):
    return f"{v:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]" if ci and np.all(np.isfinite(ci)) else f"{v:.2f} [n/a]"


def loo_pass(P, L, loc_type):
    """Leave-one-* on diff_day pass pairs. Campaign/day/location drops remove pairs (exact); the cross unit
    (spatial_block for routes, route for blocks) removes the cells of that unit and recomputes pair statistics."""
    D = P[P.pair_type == "diff_day"]
    if len(D) == 0:
        return pd.DataFrame()
    rows = []

    def rec(ut, u, sub):
        o = pooled(sub)
        rows.append(dict(unit_type=ut, unit=u, n_pairs=o.get("n_pairs", 0), R=o.get("R", np.nan),
                         fisher_r=o.get("fisher_r", np.nan), rmsd_c=o.get("rmsd_c", np.nan)))

    for c in sorted(set(D.ca) | set(D.cb)):
        rec("campaign", c, D[(D.ca != c) & (D.cb != c)])
    for dd in sorted(set(D.day_a) | set(D.day_b)):
        rec("day", dd, D[(D.day_a != dd) & (D.day_b != dd)])
    for loc in sorted(D["loc"].unique()):
        rec(loc_type, loc, D[D["loc"] != loc])
    cross, ccol = ("spatial_block", "block") if loc_type == "route" else ("route", "route")
    LD = L[L.pair_id.isin(D.pair_id)]
    base = D.drop(columns=["n", "cov", "sd2", "r", "msd", "offset"])
    for u in sorted(LD[ccol].dropna().unique()):
        hit = LD.loc[LD[ccol] == u, "pair_id"].unique()
        if len(hit) == 0:
            continue
        Lh = LD[LD.pair_id.isin(hit) & (LD[ccol] != u)]
        S = pair_stats_from_long(Lh, min_common=4) if len(Lh) else pd.DataFrame(columns=["pair_id"])
        sub = pd.concat([D[~D.pair_id.isin(hit)], base[base.pair_id.isin(S.pair_id)].merge(S, on="pair_id")])
        rec(cross, u, sub)
    return pd.DataFrame(rows)


def loo_summary(df, full):
    out = []
    for ut, g in df.groupby("unit_type"):
        g = g.dropna(subset=["R"])
        if g.empty:
            continue
        out.append(dict(unit_type=ut, n_units=len(g), R_full=full, R_min=g.R.min(), R_max=g.R.max(), R_median=g.R.median(),
                        unit_at_min=g.loc[g.R.idxmin(), "unit"], unit_at_max=g.loc[g.R.idxmax(), "unit"],
                        max_abs_shift=float(np.max(np.abs(g.R - full))), any_R_le_0=bool((g.R <= 0).any())))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--quick", action="store_true", help="recommended only, 200 boot, no LOO (smoke test)")
    a = ap.parse_args()
    t0 = time.time()
    now = datetime.now(ROME)
    out = ROOT / "outputs" / f"p1_repeatability_E0_{now:%Y%m%dT%H%M}{'_quick' if a.quick else ''}"
    if any(out.name.startswith(f) for f in FORBIDDEN) or out.exists():
        raise SystemExit(f"refusing to write {out}")
    (out / "figures").mkdir(parents=True)
    prm = Params(n_boot=200 if a.quick else a.n_boot)
    rng = np.random.default_rng(prm.seed)
    log(f"output {out}")
    d, chk = load_points()
    json.dump(chk, open(out / "inputs_check.json", "w"), indent=1, default=str)
    log(f"inputs {chk}")
    profiles = ("recommended",) if a.quick else ALL_PROFILES

    pooled_rows, loc_rows, loo_rows, loo_sum, ll_rows, ll_loo, power_rows, all_pairs = [], [], [], [], [], [], [], []
    for prof in profiles:
        pts = d[d[f"keep_{prof}"] & d["T"].notna()].copy()
        log(f"[{prof}] kept points {len(pts)}")
        for lt, lcol in LOC_TYPES.items():
            passes = build_passes(pts, lcol, prm)
            pc = passes.groupby(lcol).agg(n_campaigns=("campaign", "nunique"), n_days=("day", "nunique"),
                                          n_passes=("pass_id", "nunique"), n_points=("T", "size")).reset_index()
            elig = set(pc.loc[pc.n_campaigns >= prm.min_campaigns_loc, lcol])
            for var in PASS_VARIANTS:
                P, L = pass_pairs(passes, lcol, var, prm, eligible_locs=elig)
                if len(P) == 0:
                    continue
                all_pairs.append(P.assign(profile=prof, loc_type=lt, variant=var))
                share_same = float((P.pair_type == "same_campaign").mean())
                groups = {"diff_day": P.pair_type == "diff_day",
                          "same_day_diff_campaign": P.pair_type == "same_day_diff_campaign",
                          "inter_campaign_all": P.pair_type != "same_campaign",
                          "same_campaign": P.pair_type == "same_campaign",
                          "all": P.pair_type.notna()}
                for gname, msk in groups.items():
                    sub = P[msk]
                    o = pooled(sub)
                    if len(sub) >= 2:
                        o.update(bootstrap_pooled(sub, prm.n_boot, rng))
                    o.update(profile=prof, loc_type=lt, variant=var, pair_group=gname, share_same_campaign_all=share_same,
                             n_eligible_locations=len(elig))
                    pooled_rows.append(o)
                log(f"[{prof}|{lt}|{var}] pairs {len(P)} share_same {share_same:.2f}")
                # per-location (diff_day)
                for loc, g in P[P.pair_type == "diff_day"].groupby("loc"):
                    o = pooled(g)
                    o.update(bootstrap_pooled(g, prm.n_boot, rng) if len(g) >= 2 else {})
                    o.update(profile=prof, loc_type=lt, variant=var, loc=loc)
                    loc_rows.append(o)
                if not a.quick:
                    lo = loo_pass(P, L, lt)
                    full = pooled(P[P.pair_type == "diff_day"]).get("R", np.nan)
                    loo_rows.append(lo.assign(profile=prof, loc_type=lt, variant=var))
                    loo_sum += [dict(profile=prof, loc_type=lt, variant=var, **r) for r in loo_summary(lo, full)]
            # power table
            pc = pc.rename(columns={lcol: "loc"}).assign(profile=prof, loc_type=lt,
                                                          eligible_ge3_campaigns=lambda x: x.n_campaigns >= prm.min_campaigns_loc)
            power_rows.append(pc)
        # location-level
        anom = campaign_anomalies(pts)
        for lt, lcol in LOC_TYPES.items():
            for var in LOC_VARIANTS:
                res, cells, CP = location_level(anom, lcol, var, prm, rng=rng, n_boot=prm.n_boot)
                res.update(profile=prof, loc_type=lt, variant=var)
                ll_rows.append(res)
                log(f"[{prof}|{lt}|loc-level {var}] ICC {res.get('icc_between_location')} R_dd {res.get('campaign_pairs_diff_day', {}).get('R')}")
                if var == MAIN_LOC_VARIANT and not a.quick:
                    cross_col = "spatial_block_id" if lt == "route" else "route"
                    units = [("campaign", "campaign", sorted(cells.campaign.unique())),
                             ("day", "day", sorted(cells.day.unique())),
                             (lt, lcol, sorted(cells["loc"].unique()))]
                    cu = anom[anom[lcol].isin(cells["loc"].unique())][cross_col].dropna().value_counts()
                    units.append(("spatial_block" if lt == "route" else "route", cross_col, sorted(cu[cu >= prm.min_pts_loc_cell].index)))
                    for ut, col, vals in units:
                        for u in vals:
                            r2, _, _ = location_level(anom[anom[col] != u], lcol, var, prm)
                            ll_loo.append(dict(profile=prof, loc_type=lt, variant=var, unit_type=ut, unit=u,
                                               icc=r2.get("icc_between_location", np.nan),
                                               R_diff_day=r2.get("campaign_pairs_diff_day", {}).get("R", np.nan),
                                               n_locations=r2.get("n_locations")))

    # ---------------- write tables ----------------
    PT = pd.DataFrame(pooled_rows)
    for k in ("R_ci", "fisher_r_ci", "rmsd_ci"):
        if k in PT:
            PT[k + "_lo"] = PT[k].map(lambda v: v[0] if isinstance(v, list) else np.nan)
            PT[k + "_hi"] = PT[k].map(lambda v: v[1] if isinstance(v, list) else np.nan)
    PT = PT.drop(columns=[c for c in ("R_ci", "fisher_r_ci", "rmsd_ci") if c in PT])
    front = ["profile", "loc_type", "variant", "pair_group", "n_pairs", "n_campaigns", "n_days", "n_locations", "R", "R_ci_lo",
             "R_ci_hi", "R_ci_includes_0", "fisher_r", "fisher_r_ci_lo", "fisher_r_ci_hi", "fisher_r_ci_includes_0",
             "rmsd_c", "rmsd_ci_lo", "rmsd_ci_hi", "median_r", "median_dt_min", "share_same_campaign_all", "n_eligible_locations"]
    PT = PT[[c for c in front if c in PT] + [c for c in PT if c not in front]]
    PT.to_csv(out / "pass_pairs_pooled_metrics.csv", index=False)
    pd.concat(all_pairs).to_csv(out / "pass_pairs.csv", index=False)
    LM = pd.DataFrame(loc_rows)
    for k in ("R_ci", "fisher_r_ci", "rmsd_ci"):
        if k in LM:
            LM[k + "_lo"] = LM[k].map(lambda v: v[0] if isinstance(v, list) else np.nan)
            LM[k + "_hi"] = LM[k].map(lambda v: v[1] if isinstance(v, list) else np.nan)
            LM = LM.drop(columns=k)
    LM.to_csv(out / "pass_location_metrics_diff_day.csv", index=False)
    PW = pd.concat(power_rows)
    PW.to_csv(out / "power_locations.csv", index=False)
    if loo_rows:
        pd.concat(loo_rows).to_csv(out / "loo_pass_diff_day.csv", index=False)
        pd.DataFrame(loo_sum).to_csv(out / "loo_pass_summary.csv", index=False)
    LL = pd.json_normalize(ll_rows, sep=".")
    LL.to_csv(out / "location_level_metrics.csv", index=False)
    if ll_loo:
        LLO = pd.DataFrame(ll_loo)
        LLO.to_csv(out / "loo_location_level.csv", index=False)
    else:
        LLO = pd.DataFrame()

    # ---------------- summary ----------------
    def get(prof, lt, var, grp):
        r = PT[(PT.profile == prof) & (PT.loc_type == lt) & (PT.variant == var) & (PT.pair_group == grp)]
        return r.iloc[0].to_dict() if len(r) else {}

    prev = {}
    for name, f in [("pass_anomaly_20261015T1856", "pass_anomaly_20261015T1856/summary.json"),
                    ("short_dt_anomaly_20261015T1927", "short_dt_anomaly_20261015T1927/summary.json")]:
        try:
            prev[name] = json.load(open(ROOT / "outputs" / f))
        except Exception as e:  # noqa: BLE001
            prev[name] = f"unreadable: {e}"
    S = dict(built_at_europe_rome=now.isoformat(timespec="seconds"), output_root=str(out), code_commit=git_head(),
             params=prm.as_dict(), inputs_check=chk, profiles=list(profiles), elapsed_s=None,
             headline={}, location_level={}, loo={}, power={}, previous_20261015={
                 "pass_anomaly_official_23seg_anom_mean_R": [0.48, [-0.01, 0.72]],
                 "pass_anomaly_cv2_anom_mean_R": [0.41, [0.24, 0.52]],
                 "pass_anomaly_cv2_anom_detr_R": [0.09, [-0.02, 0.23]],
                 "short_dt_15min_R": [0.64, [0.29, 0.67]], "short_dt_15min_share_same_campaign": 1.0})
    for prof in profiles:
        for lt in LOC_TYPES:
            for var in PASS_VARIANTS:
                key = f"{prof}|{lt}|{var}"
                S["headline"][key] = {g: {k: get(prof, lt, var, g).get(k) for k in
                                          ("n_pairs", "n_campaigns", "n_days", "n_locations", "R", "R_ci_lo", "R_ci_hi",
                                           "R_ci_includes_0", "fisher_r", "fisher_r_ci_lo", "fisher_r_ci_hi",
                                           "fisher_r_ci_includes_0", "rmsd_c", "rmsd_ci_lo", "rmsd_ci_hi", "median_dt_min")}
                                      for g in ("diff_day", "same_day_diff_campaign", "same_campaign")}
                S["headline"][key]["share_same_campaign_all_pairs"] = get(prof, lt, var, "all").get("share_same_campaign_all")
                S["headline"][key]["n_eligible_locations_ge3_campaigns"] = get(prof, lt, var, "all").get("n_eligible_locations")
            pw = PW[(PW.profile == prof) & (PW.loc_type == lt)]
            S["power"][f"{prof}|{lt}"] = dict(n_locations_with_passes=int(len(pw)),
                                              n_ge3_campaigns=int(pw.eligible_ge3_campaigns.sum()),
                                              n_lt3_campaigns=int((~pw.eligible_ge3_campaigns).sum()),
                                              n_ge5_campaigns=int((pw.n_campaigns >= 5).sum()))
            sub = LM[(LM.profile == prof) & (LM.loc_type == lt)] if len(LM) else LM
            if len(sub):
                S["power"][f"{prof}|{lt}"]["per_location_diff_day"] = {
                    var: dict(n_locations_with_diff_day_pairs=int((sub.variant == var).sum()),
                              n_ci_excluding_0=int(((sub.variant == var) & (sub.R_ci_lo > 0)).sum()),
                              n_ci_includes_0_or_na=int(((sub.variant == var) & ~(sub.R_ci_lo > 0)).sum()))
                    for var in PASS_VARIANTS}
    for r in ll_rows:
        S["location_level"][f"{r['profile']}|{r['loc_type']}|{r['variant']}"] = r
    if loo_sum:
        S["loo"]["pass_diff_day"] = loo_sum
    if len(LLO):
        S["loo"]["location_level_detrended"] = [
            dict(profile=k[0], loc_type=k[1], unit_type=k[2], n_units=len(g), icc_min=g.icc.min(), icc_max=g.icc.max(),
                 R_diff_day_min=g.R_diff_day.min(), R_diff_day_max=g.R_diff_day.max())
            for k, g in LLO.groupby(["profile", "loc_type", "unit_type"])]
    S["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(S, open(out / "summary.json", "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))

    # ---------------- figures ----------------
    try:
        make_figures(out, PT, LM, pd.DataFrame(loo_sum), LL, profiles)
    except Exception as e:  # noqa: BLE001
        log(f"figure error: {e}")
    log(f"done in {time.time() - t0:.0f}s -> {out}")
    print(out)


def make_figures(out, PT, LM, LS, LL, profiles):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = {"permissive": "tab:green", "recommended": "tab:blue", "restrictive": "tab:red", "flagtable_exclude": "tab:purple"}
    # Fig 1: R with CI by pair group x profile, panels = loc_type x variant
    fig, axs = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    groups = ["diff_day", "same_day_diff_campaign", "same_campaign"]
    for i, lt in enumerate(LOC_TYPES):
        for j, var in enumerate(PASS_VARIANTS):
            ax = axs[i, j]
            for k, prof in enumerate(profiles):
                for gi, g in enumerate(groups):
                    r = PT[(PT.profile == prof) & (PT.loc_type == lt) & (PT.variant == var) & (PT.pair_group == g)]
                    if r.empty or not np.isfinite(r.R.iloc[0]):
                        continue
                    y = gi + (k - 1.5) * 0.18
                    lo, hi = r.R_ci_lo.iloc[0], r.R_ci_hi.iloc[0]
                    v0 = r.R.iloc[0]
                    ax.errorbar(v0, y, xerr=[[max(v0 - lo, 0)], [max(hi - v0, 0)]] if np.isfinite(lo) else None,
                                fmt="o", color=cols[prof], ms=5, label=prof if gi == 0 else None)
                    ax.text(1.02, y, f"n={int(r.n_pairs.iloc[0])}", fontsize=7, va="center", transform=ax.get_yaxis_transform())
            ax.axvline(0, color="k", lw=0.8)
            ax.set_yticks(range(3))
            ax.set_yticklabels(["giorni diversi", "stesso giorno,\ncampagne diverse", "stessa campagna\n(passaggi ripetuti)"], fontsize=8)
            ax.set_title(f"{lt} - {var}", fontsize=10)
            ax.set_xlim(-1, 1)
    axs[0, 0].legend(fontsize=8, loc="lower left")
    for ax in axs[1]:
        ax.set_xlabel("R (quota di varianza del profilo ripetibile), IC 95% bootstrap per campagna")
    fig.suptitle("P1 E0 - ripetibilita' dei profili di anomalia Tair tra coppie di passaggi")
    fig.tight_layout()
    fig.savefig(out / "figures" / "fig1_R_by_pairtype_profile.png", dpi=140)
    plt.close(fig)
    # Fig 2: per-location R (recommended, diff_day), sorted
    for lt in LOC_TYPES:
        sub = LM[(LM.profile == "recommended") & (LM.loc_type == lt) & (LM.variant == "centered")].sort_values("R") if len(LM) else LM
        if len(sub) == 0:
            continue
        fig, ax = plt.subplots(figsize=(8, max(4, 0.22 * len(sub))))
        y = np.arange(len(sub))
        lo = (sub.R - sub.R_ci_lo).clip(lower=0).fillna(0)
        hi = (sub.R_ci_hi - sub.R).clip(lower=0).fillna(0)
        ax.errorbar(sub.R, y, xerr=[lo, hi], fmt="o", ms=3, lw=0.8)
        ax.axvline(0, color="k", lw=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels([f"{a} (camp={int(b)}, coppie={int(c)})" for a, b, c in zip(sub["loc"], sub.n_campaigns, sub.n_pairs)], fontsize=6)
        ax.set_xlabel("R coppie di giorni diversi, IC 95% bootstrap per campagna (recommended, centered)")
        ax.set_xlim(-1.05, 1.05)
        fig.tight_layout()
        fig.savefig(out / "figures" / f"fig2_R_per_{lt}_recommended.png", dpi=140)
        plt.close(fig)
    # Fig 3: LOO ranges
    if len(LS):
        sub = LS[LS.variant == "centered"]
        fig, ax = plt.subplots(figsize=(10, 5))
        labs = []
        for i, (_, r) in enumerate(sub.iterrows()):
            ax.plot([r.R_min, r.R_max], [i, i], color=cols.get(r.profile, "k"), lw=3, alpha=0.7)
            ax.plot(r.R_full, i, "k|", ms=10)
            labs.append(f"{r.profile[:4]} {r.loc_type} - leave-one-{r.unit_type} ({r.n_units})")
        ax.set_yticks(range(len(labs)))
        ax.set_yticklabels(labs, fontsize=7)
        ax.axvline(0, color="k", lw=0.8)
        ax.set_xlabel("R coppie di giorni diversi: intervallo leave-one-* (| = stima completa), variante centered")
        fig.tight_layout()
        fig.savefig(out / "figures" / "fig3_loo_ranges.png", dpi=140)
        plt.close(fig)
    # Fig 4: location-level ICC
    if "icc_between_location" in LL:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        labs = []
        for i, (_, r) in enumerate(LL.iterrows()):
            v = r.get("icc_between_location")
            ci = r.get("icc_ci")
            ax.errorbar(v, i, xerr=[[max(v - ci[0], 0)], [max(ci[1] - v, 0)]] if isinstance(ci, list) else None, fmt="o",
                        color=cols.get(r.profile, "k"), ms=4)
            labs.append(f"{r.profile[:4]} {r.loc_type} {r.variant}")
        ax.set_yticks(range(len(labs)))
        ax.set_yticklabels(labs, fontsize=7)
        ax.axvline(0, color="k", lw=0.8)
        ax.set_xlabel("ICC tra localita' (anomalia media localita' x campagna), IC 95% jackknife leave-one-campaign")
        fig.tight_layout()
        fig.savefig(out / "figures" / "fig4_icc_location_level.png", dpi=140)
        plt.close(fig)


if __name__ == "__main__":
    main()
