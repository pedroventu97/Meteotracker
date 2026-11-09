"""Warm-up pre-registration, phase A2: rule variants as in-memory flags (NO P1/R here).

  python e0/run_warmup_prereg_rules.py <PREREG_DIR>

Builds, per point of the 55 campaigns, the warm-up flag under each candidate rule and the resulting
keep_recommended (all other flags/severities of the v0.2 recommended run unchanged):
  cap120/cap180/cap300/cap600 : flag = first segment, t <= min(t_confirm, cap) (t <= cap if never confirmed);
  nocap_v02                   : status quo v0.2 (late confirmation fully flagged; never confirmed -> 300 s);
  cap300_E1cond                  : cap300 + CONDITIONAL exception E1 (test D positive -> flag until ceil30(t_decay<0.1 C), <= 900 s).
segment_too_short segments stay fully flagged in every variant.
Proposed v0.3 rule (pre-registration) = cap300; E1 is NOT active until its prospective activation test passes. Read-only on all inputs; writes <PREREG_DIR>/rules/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V02 = ROOT / "outputs" / "e0R_qc_split_20261109T1240" / "recommended" / "campaigns"
CAPS = (120.0, 180.0, 300.0, 600.0)
E1_MAX = 900.0


def main(pre: Path):
    out = pre / "rules"; out.mkdir(parents=True, exist_ok=False)
    ev = pd.read_csv(pre / "evidence" / "start_metrics_real_vs_pseudo.csv")
    ev = ev[(ev["var"] == "Temp[°C]") & (ev.kind == "real_start")]
    e1 = {r.campaign: float(min(np.ceil(r.t_decay_below_0p1C_s / 30.0) * 30.0, E1_MAX))
          for r in ev.itertuples() if bool(r.transient)}
    parts, cnt = [], []
    for d in sorted(V02.iterdir()):
        if not d.is_dir():
            continue
        s = pd.read_parquet(next(d.glob("*_standardized.parquet")),
                            columns=["source_row", "segment_id", "qc_sensor_stabilization", "keep_recommended",
                                     "stabilization_seconds_from_segment_start", "stabilization_window_end_reason",
                                     "qc_exclusion_reasons_recommended"])
        first = (s.segment_id == s.segment_id.min()).to_numpy()
        t = s.stabilization_seconds_from_segment_start.to_numpy(dtype=float)
        stab = s.qc_sensor_stabilization.to_numpy(bool)
        reason = str(s.loc[first, "stabilization_window_end_reason"].iloc[0])
        if reason == "slope_confirmed_stable":
            t_conf = float(t[first][np.argmin(stab[first])]) if (~stab[first]).any() else np.inf
        else:
            t_conf = np.inf
        v = {"nocap_v02": stab.copy()}
        for c in CAPS:
            if reason == "segment_too_short":
                f = stab.copy()
            else:
                f = first & (t < t_conf) & (t <= c)   # t_conf = inf when never confirmed
            v[f"cap{int(c)}"] = f
        w = v["cap300"].copy()
        if d.name in e1 and reason != "segment_too_short":
            w = w | (first & (t <= e1[d.name]))
        v["cap300_E1cond"] = w
        if reason != "slope_confirmed_stable" or t_conf <= 300.0:   # cap300 must reproduce v0.2 exactly here
            assert (v["cap300"] == stab).all(), d.name
        only_stab = (~s.keep_recommended.to_numpy(bool)) & stab & (s.qc_exclusion_reasons_recommended.astype(str).to_numpy() == "qc_sensor_stabilization")
        base_keep = s.keep_recommended.to_numpy(bool) | only_stab   # keep if the warm-up flag were absent
        row = {"campaign": d.name, "end_reason": reason, "t_confirm_s": t_conf if np.isfinite(t_conf) else np.nan,
               "E1_s": e1.get(d.name, np.nan)}
        frame = pd.DataFrame({"campaign": d.name, "source_row": s.source_row.to_numpy()})
        for k, f in v.items():
            frame[f"stab_{k}"] = f
            frame[f"keep_{k}"] = base_keep & ~f
            row[f"stab_rows_{k}"] = int(f.sum()); row[f"keep_rec_{k}"] = int((base_keep & ~f).sum())
        # consistency: nocap_v02 keep must equal the archived keep_recommended
        assert (frame["keep_nocap_v02"].to_numpy() == s.keep_recommended.to_numpy(bool)).all(), d.name
        parts.append(frame); cnt.append(row)
    F = pd.concat(parts, ignore_index=True); F.to_parquet(out / "warmup_rule_variants_points.parquet", index=False)
    C = pd.DataFrame(cnt); C.to_csv(out / "warmup_rule_variants_by_campaign.csv", index=False)
    tot = {k: dict(stab_rows=int(C[f"stab_rows_{k}"].sum()), keep_recommended=int(C[f"keep_rec_{k}"].sum()))
           for k in ["nocap_v02", "cap120", "cap180", "cap300", "cap600", "cap300_E1cond"]}
    tot["E1_campaigns"] = e1
    tot["note"] = "In-memory rule variants; no code, config or severity changed. Base = v0.2 recommended run 20261109T1240."
    (out / "warmup_rule_variants_totals.json").write_text(json.dumps(tot, indent=2), encoding="utf-8")
    print(json.dumps(tot, indent=1))
    print(C[C.campaign.str.contains("13_08_42|09_17_03|08_29_06|12_54_36")][["campaign", "t_confirm_s", "E1_s"] + [c for c in C.columns if c.startswith("stab_rows")]].to_string())


if __name__ == "__main__":
    main(Path(sys.argv[1]))