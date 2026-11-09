"""Warm-up v0.3 pre-registration clarifications, Q2: the 300 s threshold calculation (no R).

  python e0/run_warmup_prereg_clarifications_q2.py <PREREG_DIR> <SUBDIR_NAME>

Writes <PREREG_DIR>/<SUBDIR_NAME>/q2_threshold_criterion.csv and q2_tq_median_robustness.json.
Time-constant bound: MeteoTracker+ App Manual rev.1, sec. 9.1 ("Measurement speed: >= 15 C variation detected over a
30 s interval at 20 km/h, under a stepped temperature change of 30 C"); under a FIRST-ORDER model ASSUMPTION
1 - exp(-30/tau) >= 0.5  ->  tau <= 30/ln 2 = 43.3 s. The manufacturer gives no tau value.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CANDS = (120, 180, 300, 600)


def main():
    pre = Path(sys.argv[1]); out = pre / sys.argv[2]; out.mkdir(parents=True, exist_ok=True)
    ev = pd.read_csv(pre / "evidence" / "start_metrics_real_vs_pseudo.csv")
    tq = np.sort(ev[(ev["var"] == "Temp[°C]") & (ev.kind == "real_start") & ev.transient].t_decay_below_0p1C_s.to_numpy(float))
    med = float(np.median(tq))
    rng = np.random.default_rng(20261109)
    bm = np.median(rng.choice(tq, (20000, len(tq))), axis=1)
    loo = [float(np.median(np.delete(tq, i))) for i in range(len(tq))]
    amt_mid = (2.2 + 6.3) / 2 * 60
    tau_committed = 10.0                       # bbc3121 value: NOT supported by the cited source (erratum)
    tau_bound = 30 / math.log(2)               # upper bound under first-order assumption
    rows = []
    for c in CANDS:
        rows.append(dict(candidate_s=c,
                         c1_ge_median_tq=c >= med, c2_ge_amt_midpoint=c >= amt_mid,
                         c3_committed_ge_10tau_100s=c >= 10 * tau_committed,
                         c3_corrected_ge_10tau_upper_bound_433s=c >= 10 * tau_bound,
                         c2bis_ge_amt_upper_378s=c >= 6.3 * 60,
                         n_transients_tq_le_c=int((tq <= c).sum()), n_transients=len(tq)))
    pd.DataFrame(rows).to_csv(out / "q2_threshold_criterion.csv", index=False)
    J = dict(tq_sorted_s=[round(x, 1) for x in tq], median_tq_s=round(med, 1),
             bootstrap_median_ci95_s=[round(float(x), 1) for x in np.percentile(bm, [2.5, 97.5])],
             bootstrap_share_median_le_300=round(float((bm <= 300).mean()), 3),
             bootstrap_share_median_le_255=round(float((bm <= 255).mean()), 3),
             leave_one_out_medians_s=[round(x, 1) for x in loo],
             amt_midpoint_s=amt_mid, amt_range_s=[2.2 * 60, 6.3 * 60],
             tau_committed_s=tau_committed, tau_upper_bound_first_order_s=round(tau_bound, 1),
             ten_tau_committed_s=10 * tau_committed, ten_tau_upper_bound_s=round(10 * tau_bound, 1),
             post_hoc_info_time_to_0p1C_for_step_dT_at_tau_bound_s={str(dT): round(tau_bound * math.log(dT / 0.1)) for dT in (3, 10, 20, 30)},
             seed=20261109, n_boot=20000)
    (out / "q2_tq_median_robustness.json").write_text(json.dumps(J, indent=2), encoding="utf-8")
    print(json.dumps(J, indent=1)); print(pd.DataFrame(rows).to_string())


if __name__ == "__main__":
    main()