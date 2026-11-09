"""Warm-up v0.3 pre-registration, PHASE B: DESCRIPTIVE impact of the warm-up time threshold on P1 R.

Run ONLY after the phase-A commit (criterion fixed). R is NOT a selection criterion (PREREG AT-8): nothing here can
confirm, change or reject the pre-registered rule. Masks = keep_recommended(v0.2) with the warm-up flag replaced by each
in-memory variant from e0/run_warmup_prereg_rules.py (cap120/180/300/600, nocap_v02 = status quo, cap300_E1cond).

  python e0/run_warmup_prereg_threshold_sensitivity.py --e0r-root outputs/e0R_qc_split_20261109T1240 --prereg <PREREG_DIR>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from meteotracker_qc.p1_repeatability import Params  # noqa: E402
from meteotracker_qc.p1_repeatability import common as cp  # noqa: E402

LOC_TYPES = {"route": "route", "spatial_block": "spatial_block_id"}
VARIANTS = ("nocap_v02", "cap120", "cap180", "cap300", "cap600", "cap300_E1cond")


def _mod(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "e0" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--e0r-root", required=True); ap.add_argument("--prereg", required=True)
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args(); t0 = time.time()
    out = Path(a.prereg) / "r_sensitivity_descriptive"; out.mkdir(parents=True, exist_ok=False)
    cpop = _mod("run_p1_common_population_e0R")
    d, chk = cpop.load(Path(a.e0r_root))
    V = pd.read_parquet(Path(a.prereg) / "rules" / "warmup_rule_variants_points.parquet",
                        columns=["campaign", "source_row"] + [f"keep_{v}" for v in VARIANTS])
    d = d.merge(V, on=["campaign", "source_row"], how="left", validate="one_to_one")
    miss = int(d["keep_nocap_v02"].isna().sum())
    for v in VARIANTS:
        d[f"mk_{v}"] = d[f"keep_{v}"].fillna(False).astype(bool)
    mism = int((d["mk_nocap_v02"] != d["mk_v02_recommended"]).sum())
    chk.update(rows_without_variant=miss, mismatch_nocap_vs_v02_recommended=mism,
               n_keep={v: int(d[f"mk_{v}"].sum()) for v in VARIANTS})
    print(chk, flush=True)
    assert mism == 0, "status-quo variant must reproduce v0.2 keep_recommended"
    tiers = {"common_all": VARIANTS, **{f"own_{v}": (v,) for v in VARIANTS}}
    prm = Params(n_boot=a.n_boot); rows = []
    for pop in ("all", "excl_cv2_004"):
        dp = d if pop == "all" else d[d["route"].astype(str) != "cv2_004"]
        masks = {k: dp[f"mk_{k}"] for k in VARIANTS}
        for lt, lcol in LOC_TYPES.items():
            passes = cp.prepare_passes(dp, lcol, prm)
            for var in cp.VARIANTS:
                cv = cp.cell_values(passes, masks, var, prm)
                for tier, names in tiers.items():
                    P, L = cp.common_pairs(passes, lcol, cv, names, prm)
                    if len(P) == 0:
                        continue
                    st = {k: v[v.pair_type == "diff_day"].reset_index(drop=True)
                          for k, v in cp.per_mask_stats(P, L, names).items()}
                    ref = names[0]
                    if len(st[ref]) < 2:
                        continue
                    C = cp.compare_masks(st, ref, a.n_boot, prm.seed)
                    rows.append(C.assign(pop=pop, loc_type=lt, variant=var, tier=tier, pair_group="diff_day",
                                         n_diff_day=int((P.pair_type == "diff_day").sum())))
                    print(f"[{pop}|{lt}|{var}|{tier}] diff_day {(P.pair_type == 'diff_day').sum()}", flush=True)
    R = pd.concat(rows, ignore_index=True)
    front = ["pop", "loc_type", "variant", "tier", "pair_group", "mask", "n_diff_day"]
    R = R[front + [c for c in R.columns if c not in front]]
    R.to_csv(out / "warmup_threshold_R_descriptive.csv", index=False)
    (out / "summary.json").write_text(json.dumps(dict(
        label="DESCRIPTIVE ONLY - computed after the phase-A pre-registration commit; NOT a selection criterion (AT-8)",
        inputs_check=chk, n_boot=a.n_boot, seed=prm.seed, elapsed_s=round(time.time() - t0, 1)), indent=2, default=str),
        encoding="utf-8")
    print("done", round(time.time() - t0, 1), flush=True)


if __name__ == "__main__":
    main()