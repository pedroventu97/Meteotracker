import numpy as np
import pandas as pd

from meteotracker_qc import qc_r_evidence as ev


def test_decide_recovery_rule():
    bins = np.arange(0, 240, 10.0)
    base = dict(bin_start=bins, n_events=20, n_controls=50, S=0.0, S_lo=-.1, S_hi=.1)
    flat = pd.DataFrame(dict(base, A=0.02, A_lo=-0.1, A_hi=0.12))
    assert ev.decide_recovery(flat)["transient"] is False
    A = np.where(bins < 80, 0.3, 0.02)
    lo = np.where(bins < 80, 0.15, -0.1)
    tr = pd.DataFrame(dict(base, A=A, A_lo=lo, A_hi=A + 0.1))
    d = ev.decide_recovery(tr)
    assert d["transient"] is True and d["window_s"] == 80.0
    few = flat.assign(n_events=3)
    assert ev.decide_recovery(few)["transient"] is None


def test_decide_freeze_and_accel_rules():
    B = pd.DataFrame(dict(n_points=[10, 2], cls=["sosta_reale", "freeze_in_movimento"]))
    assert ev.decide_freeze(B)["severity"] == "EXCLUDE_RESTRICTIVE"
    B2 = pd.DataFrame(dict(n_points=[2, 10], cls=["sosta_reale", "freeze_in_movimento"]))
    assert ev.decide_freeze(B2)["severity"] == "EXCLUDE_RECOMMENDED"
    acc = pd.DataFrame(dict(a_pos=[6, 7, 8, 1], a_dop=[0.5, 0.2, 3.0, 0.1], e_pos_max=[5, 6, 7, 1],
                            cls=["rumore_gps", "rumore_gps", "dinamica_plausibile", "rumore_gps"]))
    assert ev.decide_accel(acc)["rule_met"] is True
