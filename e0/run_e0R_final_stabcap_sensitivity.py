"""E0-QC-R final validation: EXPLORATORY (not pre-registered) P1 sensitivity to proposal P-0527 (NOT applied).

P-0527 = the warm-up flag (qc_sensor_stabilization) would never extend beyond warmup.max_window_s (300 s), also when
the slope gate confirms stability later (today only the never-confirmed case is capped). The mask
`v02_rec_stabcap` = keep_recommended(v0.2) OR (point excluded ONLY by qc_sensor_stabilization AND > 300 s from the
segment start). This is a what-if to size the effect of the 05-27 13:08 finding on P1; it changes no policy,
severity, threshold or official output.

  python e0/run_e0R_final_stabcap_sensitivity.py --e0r-root outputs/e0R_qc_split_20261109T1240 --out <DIR>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from meteotracker_qc.p1_repeatability import Params  # noqa: E402
from meteotracker_qc.p1_repeatability import common as cp  # noqa: E402

LOC_TYPES = {"route": "route", "spatial_block": "spatial_block_id"}
CAMP_0527 = "05-27__20260527T13_08_42_mtdicambo_AC4D162B317E_Bologna-Bologna__99cbc5b816"


def _mod(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "e0" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def stabcap_restore(e0r_root: Path) -> pd.DataFrame:
    parts = []
    for d in sorted((e0r_root / "recommended" / "campaigns").iterdir()):
        if not d.is_dir():
            continue
        s = pd.read_parquet(next(d.glob("*_standardized.parquet")),
                            columns=["source_row", "segment_id", "qc_sensor_stabilization",
                                     "stabilization_seconds_from_segment_start", "qc_exclusion_reasons_recommended"])
        cap = float(yaml.safe_load((d / "config_used.yaml").read_text(encoding="utf-8"))["warmup"]["max_window_s"])
        s["restore"] = (s.qc_sensor_stabilization & (s.stabilization_seconds_from_segment_start > cap)
                        & (s.qc_exclusion_reasons_recommended.astype(str) == "qc_sensor_stabilization"))
        parts.append(s[["source_row", "restore"]].assign(campaign=d.name))
    return pd.concat(parts, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--e0r-root", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args(); t0 = time.time()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    cpop = _mod("run_p1_common_population_e0R")
    d, chk = cpop.load(Path(a.e0r_root))
    r = stabcap_restore(Path(a.e0r_root))
    d = d.merge(r, on=["campaign", "source_row"], how="left", validate="one_to_one")
    d["restore"] = d["restore"].fillna(False).astype(bool)
    d["mk_v02_rec_stabcap"] = d["mk_v02_recommended"] | d["restore"]
    chk.update(n_restored=int((d.restore & ~d.mk_v02_recommended).sum()),
               n_restored_0527_1308=int((d.restore & ~d.mk_v02_recommended & (d.campaign == CAMP_0527)).sum()),
               n_keep_v02_rec_stabcap=int(d.mk_v02_rec_stabcap.sum()))
    print(chk, flush=True)
    names_all = ("old_recommended", "v02_recommended", "v02_rec_stabcap")
    tiers = {"common_3": names_all, "own_v02_recommended": ("v02_recommended",), "own_v02_rec_stabcap": ("v02_rec_stabcap",),
             "own_old_recommended": ("old_recommended",)}
    prm = Params(n_boot=a.n_boot); rows, sizes = [], []
    for pop in ("all", "excl_cv2_004"):
        dp = d if pop == "all" else d[d["route"].astype(str) != "cv2_004"]
        masks = {k: dp[f"mk_{k}"] for k in names_all}
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
                    ref = "old_recommended" if "old_recommended" in names else names[0]
                    if len(st[ref]) < 2:
                        continue
                    C = cp.compare_masks(st, ref, a.n_boot, prm.seed)
                    rows.append(C.assign(pop=pop, loc_type=lt, variant=var, tier=tier, pair_group="diff_day",
                                         n_diff_day=int((P.pair_type == "diff_day").sum())))
                    print(f"[{pop}|{lt}|{var}|{tier}] diff_day {(P.pair_type == 'diff_day').sum()}", flush=True)
    R = pd.concat(rows, ignore_index=True)
    front = ["pop", "loc_type", "variant", "tier", "pair_group", "mask", "n_diff_day"]
    R = R[front + [c for c in R.columns if c not in front]]
    R.to_csv(out / "stabcap_sensitivity_R.csv", index=False)
    (out / "summary.json").write_text(json.dumps(dict(label="EXPLORATORY, NOT PRE-REGISTERED; proposal P-0527 NOT applied",
                                                      inputs_check=chk, n_boot=a.n_boot, seed=prm.seed,
                                                      elapsed_s=round(time.time() - t0, 1)), indent=2, default=str),
                                     encoding="utf-8")
    print("done", round(time.time() - t0, 1), flush=True)


if __name__ == "__main__":
    main()
