"""E0-QC-R step G: P1 on COMMON POPULATIONS across masks (pre-registered in e0/QC_R_CRITERIA_E0.md).

Masks: old_recommended (v0.1 keep_recommended), old_flagtable (no v0.1 flag-table exclude), consensus (both),
v02_permissive / v02_recommended / v02_restrictive (real runs, policy v0.2).
Tiers: 'all_masks' (all six) and 'large_masks' (old_recommended + the three v0.2 masks).
Populations: all points, and without route cv2_004. Location types: route, 500 m block.
Variants: centered (raw), detrended (within-pass time), detr_alt (T ~ time + altitude per campaign).
Pair-count sensitivity: random subsets of 100/200/400 diff-day pairs (+ all), the same subsets for every mask.

Read-only inputs: outputs/e0_qc_split_20261105T1703 (v0.1 masks, split) and an outputs/e0R_qc_split_* root.
Writes ONLY <p1_repeatability_E0R_*>/common_population/ (refuses to overwrite).

Usage: python e0/run_p1_common_population_e0R.py --e0r-root <e0R_qc_split_*> --p1-out <p1_repeatability_E0R_*>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meteotracker_qc.p1_repeatability import Params  # noqa: E402
from meteotracker_qc.p1_repeatability import common as cp  # noqa: E402

ROME = ZoneInfo("Europe/Rome")
LOC_TYPES = {"route": "route", "spatial_block": "spatial_block_id"}
MASKS = ("old_recommended", "old_flagtable", "consensus", "v02_permissive", "v02_recommended", "v02_restrictive")
TIERS = {"all_masks": MASKS, "large_masks": ("old_recommended", "v02_permissive", "v02_recommended", "v02_restrictive"),
         # NOT pre-registered (added after seeing that tiers a/b leave < 100 diff-day pairs, before looking at its R):
         # lets the 100/200/400 pair-count sensitivity run at all. Reported as exploratory.
         "broad_masks_exploratory": ("old_recommended", "v02_permissive", "v02_recommended")}
SIZES = (100, 200, 400, "all")
EXCL_ROUTE = "cv2_004"


def log(m):
    print(f"[{datetime.now(ROME):%H:%M:%S}] {m}", flush=True)


def _p1_module():
    spec = importlib.util.spec_from_file_location("p1run", ROOT / "e0" / "run_p1_repeatability_e0.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load(e0r_root: Path):
    p1 = _p1_module()
    d, chk = p1.load_points()  # v0.1 masks + split (read-only)
    n, _ = p1.load_points_e0r(e0r_root)
    keep_cols = ["campaign", "source_row", "T", "route", "spatial_block_id", "day", "time_utc",
                 "keep_permissive", "keep_recommended", "keep_restrictive"]
    m = d.merge(n[keep_cols], on=["campaign", "source_row"], suffixes=("", "_v02"), how="inner", validate="one_to_one")
    chk2 = dict(n_v01=len(d), n_v02=len(n), n_joined=len(m),
                T_identical=bool(((m["T"] == m["T_v02"]) | (m["T"].isna() & m["T_v02"].isna())).all()),
                split_identical={c: _same_na_aware(m[c], m[c + "_v02"])
                                 for c in ("route", "spatial_block_id", "day", "time_utc")})
    masks = {"old_recommended": m["keep_recommended"], "old_flagtable": m["keep_flagtable_exclude"],
             "consensus": m["keep_recommended"] & m["keep_flagtable_exclude"],
             "v02_permissive": m["keep_permissive_v02"], "v02_recommended": m["keep_recommended_v02"],
             "v02_restrictive": m["keep_restrictive_v02"]}
    for k in masks:
        m[f"mk_{k}"] = masks[k].astype(bool)
        chk2[f"n_keep_{k}"] = int(m[f"mk_{k}"].sum())
    return m, chk2


def _same_na_aware(a, b) -> float:
    na_a, na_b = a.isna(), b.isna()
    return float(((na_a & na_b) | (~na_a & ~na_b & (a.astype(str) == b.astype(str)))).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--e0r-root", required=True)
    ap.add_argument("--p1-out", required=True)
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--n-sub", type=int, default=200)
    ap.add_argument("--n-boot-sub", type=int, default=200)
    ap.add_argument("--out-name", default="common_population")
    a = ap.parse_args()
    t0 = time.time()
    p1_out = Path(a.p1_out)
    if not p1_out.name.startswith("p1_repeatability_E0R_"):
        raise SystemExit("--p1-out must be an outputs/p1_repeatability_E0R_* folder")
    out = p1_out / a.out_name
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    (out / "figures").mkdir(parents=True)
    prm = Params(n_boot=a.n_boot)
    d, chk = load(Path(a.e0r_root))
    log(f"inputs {chk}")
    R_rows, S_rows, size_rows = [], [], []
    for pop in ("all", "excl_cv2_004"):
        dp = d if pop == "all" else d[d["route"].astype(str) != EXCL_ROUTE]
        masks = {k: dp[f"mk_{k}"] for k in MASKS}
        for lt, lcol in LOC_TYPES.items():
            passes = cp.prepare_passes(dp, lcol, prm)
            for var in cp.VARIANTS:
                cv = cp.cell_values(passes, masks, var, prm)
                for tier, names in TIERS.items():
                    P, L = cp.common_pairs(passes, lcol, cv, names, prm)
                    if len(P) == 0:
                        size_rows.append(dict(pop=pop, loc_type=lt, variant=var, tier=tier, n_pairs_all=0))
                        continue
                    stats = cp.per_mask_stats(P, L, names)
                    for pt in ("diff_day", "inter_campaign"):
                        sel = (lambda S: S[S.pair_type == "diff_day"]) if pt == "diff_day" else \
                            (lambda S: S[S.pair_type != "same_campaign"])
                        st = {k: sel(v).reset_index(drop=True) for k, v in stats.items()}
                        if len(st["old_recommended"]) < 2:
                            continue
                        C = cp.compare_masks(st, "old_recommended", a.n_boot, prm.seed)
                        R_rows.append(C.assign(pop=pop, loc_type=lt, variant=var, tier=tier, pair_group=pt))
                        if pt == "diff_day":
                            sens = cp.pair_count_sensitivity(st, SIZES, a.n_sub, a.n_boot_sub, prm.seed)
                            S_rows.append(sens.assign(pop=pop, loc_type=lt, variant=var, tier=tier))
                    on4 = L.groupby("pair_id")["route"].apply(lambda r: (r.astype(str) == EXCL_ROUTE).any())
                    size_rows.append(dict(pop=pop, loc_type=lt, variant=var, tier=tier, n_pairs_all=len(P),
                                          n_pairs_touching_cv2_004=int(on4.sum()),
                                          n_diff_day_touching_cv2_004=int(on4.reindex(
                                              P.loc[P.pair_type == "diff_day", "pair_id"]).fillna(False).sum()),
                                          n_diff_day=int((P.pair_type == "diff_day").sum()),
                                          n_locations=int(P["loc"].nunique()), n_common_cells=int(L.shape[0])))
                    log(f"[{pop}|{lt}|{var}|{tier}] pairs {len(P)} diff_day {(P.pair_type == 'diff_day').sum()}")
    R = pd.concat(R_rows, ignore_index=True)
    front = ["pop", "loc_type", "variant", "tier", "pair_group", "mask"]
    R = R[front + [c for c in R.columns if c not in front]]
    R.to_csv(out / "common_population_R.csv", index=False)
    SS = pd.concat(S_rows, ignore_index=True)
    SS.to_csv(out / "pair_count_sensitivity.csv", index=False)
    pd.DataFrame(size_rows).to_csv(out / "common_population_sizes.csv", index=False)
    S = dict(built_at_europe_rome=datetime.now(ROME).isoformat(timespec="seconds"), e0r_root=a.e0r_root,
             params=prm.as_dict(), n_sub=a.n_sub, n_boot_sub=a.n_boot_sub, inputs_check=chk, masks=list(MASKS),
             tiers={k: list(v) for k, v in TIERS.items()}, sizes=[str(s) for s in SIZES], excluded_route=EXCL_ROUTE,
             elapsed_s=round(time.time() - t0, 1))
    head = R[(R.pair_group == "diff_day")]
    S["headline_diff_day"] = head[["pop", "loc_type", "variant", "tier", "mask", "n_pairs", "R", "R_ci_lo", "R_ci_hi",
                                   "dR_vs_ref", "dR_ci_lo", "dR_ci_hi"]].round(4).to_dict(orient="records")
    json.dump(S, open(out / "summary.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))
    try:
        figures(out, R, SS)
    except Exception as e:  # noqa: BLE001
        log(f"figure error {e}")
    log(f"done in {time.time() - t0:.0f}s -> {out}")


def figures(out, R, SS):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = {"old_recommended": "#525252", "old_flagtable": "#a3a3a3", "consensus": "#7c3aed",
            "v02_permissive": "#16a34a", "v02_recommended": "#0369a1", "v02_restrictive": "#b91c1c"}
    for tier in TIERS:
        fig, axs = plt.subplots(2, 3, figsize=(15, 8), sharex=True)
        for i, lt in enumerate(("route", "spatial_block")):
            for j, var in enumerate(("centered", "detrended", "detr_alt")):
                ax = axs[i, j]
                sub = R[(R.tier == tier) & (R.loc_type == lt) & (R.variant == var) & (R.pair_group == "diff_day")]
                y = 0
                labels, ypos = [], []
                for pop, mk in (("all", "o"), ("excl_cv2_004", "s")):
                    for m in TIERS[tier]:
                        r = sub[(sub["pop"] == pop) & (sub["mask"] == m)]
                        if len(r):
                            r = r.iloc[0]
                            ax.errorbar(r.R, y, xerr=[[max(r.R - r.R_ci_lo, 0)], [max(r.R_ci_hi - r.R, 0)]], fmt=mk,
                                        color=cols[m], capsize=2)
                        labels.append(f"{m} | {pop}")
                        ypos.append(y)
                        y += 1
                    y += 0.5
                ax.axvline(0, color="k", lw=.6)
                ax.set_yticks(ypos)
                ax.set_yticklabels(labels if j == 0 else [], fontsize=6)
                ax.invert_yaxis()
                n = sub["n_pairs"].iloc[0] if len(sub) else 0
                ax.set_title(f"{lt} | {var} | coppie diff-day={n}", fontsize=9)
                if i == 1:
                    ax.set_xlabel("R (IC 95% bootstrap per campagna)")
        handles = [plt.Line2D([], [], color=cols[m], marker="o", ls="") for m in TIERS[tier]]
        handles += [plt.Line2D([], [], color="k", marker="o", ls=""), plt.Line2D([], [], color="k", marker="s", ls="")]
        fig.legend(handles, list(TIERS[tier]) + ["tutti i punti", "senza cv2_004"], loc="lower center", ncol=8, fontsize=8)
        fig.suptitle(f"P1 su popolazione comune ({tier}): stesse coppie e celle per tutte le maschere")
        fig.tight_layout(rect=(0, 0.05, 1, 0.96))
        fig.savefig(out / "figures" / f"common_population_R_{tier}.png", dpi=130)
        plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, lt in zip(axs, ("route", "spatial_block")):
        sub = SS[(SS.tier == "broad_masks_exploratory") & (SS.loc_type == lt) & (SS.variant == "centered")
                 & (SS["pop"] == "all")]
        for m in TIERS["broad_masks_exploratory"]:
            s = sub[sub["mask"] == m].sort_values("n_pairs")
            ax.plot(s.n_pairs, s.R_median, marker="o", color=cols[m], label=m)
            ax.fill_between(s.n_pairs, s.R_p2_5, s.R_p97_5, color=cols[m], alpha=.08)
        ax.set_xscale("log")
        ax.axhline(0, color="k", lw=.6)
        ax.set_xlabel("coppie diff-day nel sottocampione")
        ax.set_title(f"{lt}: R mediano e 2,5–97,5% tra sottocampioni")
    axs[0].set_ylabel("R")
    axs[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "figures" / "pair_count_sensitivity.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
