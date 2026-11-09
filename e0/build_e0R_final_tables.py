"""E0-QC-R final validation, item 4: assemble the final comparison tables from EXISTING validated P1 outputs
(no P1 rerun: masks are unchanged by the final-validation fixes) plus the exploratory P-0527 sensitivity.

  python e0/build_e0R_final_tables.py <FINAL_DIR>
Reads only; writes <FINAL_DIR>/p1_comparison/*.csv and figures.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs"
P1_V01 = O / "p1_repeatability_E0_20261109T1041"
P1_V02 = O / "p1_repeatability_E0R_20261109T1243"
CP = P1_V02 / "common_population_20261109T1257"
AUD = O / "e0R_mask_audit_20261109T1238"
COLS = ["n_pairs", "n_campaigns", "n_locations", "R", "R_ci_lo", "R_ci_hi", "R_ci_includes_0"]


def kappa(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    po = (a == b).mean(); pa, pb = a.mean(), b.mean(); pe = pa * pb + (1 - pa) * (1 - pb)
    return float((po - pe) / (1 - pe)) if pe < 1 else np.nan


def main(final: Path):
    out = final / "p1_comparison"; out.mkdir(parents=True, exist_ok=True)
    # T1 own populations (pre-registered P1 method; each mask its own surviving pairs -> NOT comparable across masks)
    t = []
    for tag, d in (("v0.1", P1_V01), ("v0.2", P1_V02)):
        m = pd.read_csv(d / "pass_pairs_pooled_metrics.csv")
        m = m[m.pair_group == "diff_day"]
        t.append(m.assign(policy=tag)[["policy", "profile", "loc_type", "variant"] + COLS])
    T1 = pd.concat(t, ignore_index=True).sort_values(["loc_type", "variant", "profile", "policy"])
    T1.to_csv(out / "T1_P1_own_population_diff_day_v01_v02.csv", index=False)
    # T2/T3 common populations
    R = pd.read_csv(CP / "common_population_R.csv"); R = R[R.pair_group == "diff_day"]
    keep = ["pop", "loc_type", "variant", "tier", "mask", "n_pairs", "n_campaigns", "R", "R_ci_lo", "R_ci_hi",
            "dR_vs_ref", "dR_ci_lo", "dR_ci_hi", "dR_ci_includes_0"]
    R[R.tier.isin(["all_masks", "large_masks"])][keep].to_csv(out / "T2_common_population_PREREGISTERED.csv", index=False)
    R[R.tier == "broad_masks_exploratory"][keep].to_csv(out / "T3_common_population_EXPLORATORY_broad.csv", index=False)
    pd.read_csv(CP / "common_population_sizes.csv").to_csv(out / "T5_common_population_sizes_pairs_cv2_004.csv", index=False)
    S = pd.read_csv(CP / "pair_count_sensitivity.csv")
    S.to_csv(out / "T4_pair_count_sensitivity_all_tiers.csv", index=False)
    # T6 mask agreement incl. permissive vs restrictive
    p = pd.read_parquet(AUD / "points_masks_v01_v02.parquet")
    p["old_flagtable_keep"] = ~p["old_ft_exclude"].astype(bool)
    names = ["old_keep_recommended", "old_flagtable_keep", "v02_keep_permissive", "v02_keep_recommended", "v02_keep_restrictive"]
    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = p[a].astype(bool), p[b].astype(bool)
            rows.append(dict(mask_a=a, mask_b=b, n_keep_a=int(x.sum()), n_keep_b=int(y.sum()), agreement=float((x == y).mean()),
                             kappa=kappa(x, y), keep_a_only=int((x & ~y).sum()), keep_b_only=int((~x & y).sum())))
    pd.DataFrame(rows).to_csv(out / "T6_mask_agreement_points.csv", index=False)
    # T7 exploratory P-0527 sensitivity (copied view)
    X = pd.read_csv(out / "stabcap_sensitivity_exploratory" / "stabcap_sensitivity_R.csv")
    X.to_csv(out / "T7_P0527_stabcap_sensitivity_EXPLORATORY.csv", index=False)
    # headline table (diff-day): route/block x raw/detrended/alt x with/without cv2_004, own vs common
    H = []
    for pop in ("all", "excl_cv2_004"):
        for lt in ("route", "spatial_block"):
            for var in ("centered", "detrended", "detr_alt"):
                row = dict(pop=pop, loc_type=lt, variant=var)
                for tier, mk, lab in (("own_old_recommended", "old_recommended", "own_v01rec"),
                                      ("own_v02_recommended", "v02_recommended", "own_v02rec"),
                                      ("own_v02_rec_stabcap", "v02_rec_stabcap", "own_v02rec_capP0527"),
                                      ("common_3", "v02_recommended", "common_v02rec")):
                    r = X[(X["pop"] == pop) & (X.loc_type == lt) & (X.variant == var) & (X.tier == tier) & (X["mask"] == mk)]
                    if len(r):
                        r = r.iloc[0]
                        row[lab] = f"{r.R:.2f} [{r.R_ci_lo:.2f}; {r.R_ci_hi:.2f}] n={int(r.n_pairs)}"
                        if tier == "common_3":
                            row["common_dR_v02rec_vs_v01rec"] = f"{r.dR_vs_ref:+.3f} [{r.dR_ci_lo:+.3f}; {r.dR_ci_hi:+.3f}]"
                H.append(row)
    pd.DataFrame(H).to_csv(out / "T0_headline_diff_day.csv", index=False)
    # forest figure
    fig, axs = plt.subplots(1, 2, figsize=(13, 6), sharex=True)
    cols = {"own_old_recommended": "0.5", "own_v02_recommended": "C0", "own_v02_rec_stabcap": "C2", "common_3": "C3"}
    labs = {"own_old_recommended": "v0.1 rec (own pop.)", "own_v02_recommended": "v0.2 rec (own pop.)",
            "own_v02_rec_stabcap": "v0.2 rec + P-0527 cap (own, EXPLOR.)", "common_3": "v0.2 rec, common pop. (EXPLOR. tier)"}
    for ax, lt in zip(axs, ("route", "spatial_block")):
        y = 0; ticks = []
        for pop in ("all", "excl_cv2_004"):
            for var in ("centered", "detrended", "detr_alt"):
                for k, (tier, c) in enumerate(cols.items()):
                    mk = {"own_old_recommended": "old_recommended", "own_v02_recommended": "v02_recommended",
                          "own_v02_rec_stabcap": "v02_rec_stabcap", "common_3": "v02_recommended"}[tier]
                    r = X[(X["pop"] == pop) & (X.loc_type == lt) & (X.variant == var) & (X.tier == tier) & (X["mask"] == mk)]
                    if len(r):
                        r = r.iloc[0]; yy = y + k * 0.18
                        ax.errorbar(r.R, yy, xerr=[[r.R - r.R_ci_lo], [r.R_ci_hi - r.R]], fmt="o", color=c, ms=4,
                                    label=labs[tier] if (pop, var) == ("all", "centered") else None)
                ticks.append((y + 0.27, f"{'no cv2_004' if pop != 'all' else 'all'} | {var}")); y += 1
        ax.axvline(0, color="k", lw=.8); ax.set_yticks([t[0] for t in ticks]); ax.set_yticklabels([t[1] for t in ticks], fontsize=8)
        ax.invert_yaxis(); ax.set_title(f"P1 diff-day R [95% CI], {lt}"); ax.set_xlabel("R")
    fig.legend(*axs[0].get_legend_handles_labels(), fontsize=8, loc="lower center", ncol=4)
    fig.tight_layout(rect=(0, 0.06, 1, 1)); fig.savefig(out / "fig_final_P1_forest.png", dpi=130); plt.close(fig)
    print(pd.DataFrame(H).to_string()); print(pd.DataFrame(rows).round(3).to_string())


if __name__ == "__main__":
    main(Path(sys.argv[1]))

