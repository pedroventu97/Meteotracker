"""Skeleton analysis for the warm-up time-constant field protocol (e0/PROTOCOLLO_TAU_WARMUP_v1.md).

NOT part of the QC package (nothing under src/meteotracker_qc). No data exist yet: this module fixes, BEFORE any
measurement, the computations and the decision rule of e0/PROPOSTA_VALIDAZIONE_TAU_v1.md.

  python e0/tau_warmup_analysis.py --sheet data/tau_tests/TAU_SHEETS.csv --data data/tau_tests --out outputs/tau_tests_<ts>

Main pieces
- read_mt_csv / read_ref_csv / align_to_ref : load a MeteoTracker CSV and the reference logger CSV on a common UTC axis.
- fit_first_order : MT(t) = filt_tau(REF(t - d)) + y0-transient + bias, grid over tau and delay d, linear LS for
                    the rest, moving-block bootstrap CI for tau.
- time_to_stability : first time after which |e(t) - e_inf| <= eps for every 10 s block up to the horizon.
- decide_cap : the pre-registered decision rule (candidates 120/180/300/600 s).
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

EPS_PRIMARY = 0.2          # deg C, accuracy requirement (protocol sec. 5)
EPS_SECONDARY = 0.1        # deg C, one quantum, reported only
CANDIDATES = (120, 180, 300, 600)
FINAL_WINDOW = (900.0, 1500.0)
HORIZON_S = 900.0
BLOCK_S = 10.0


# ------------------------------------------------------------------ I/O
def read_mt_csv(path: str | Path) -> pd.DataFrame:
    """MeteoTracker CSV -> DataFrame[time_utc, temp_c]. 'Time' carries its own UTC offset; '-' is missing."""
    raw = pd.read_csv(path, na_values=["-"], encoding="utf-8", encoding_errors="replace")
    tcol = next(c for c in raw.columns if c.startswith("Temp["))
    out = pd.DataFrame({"time_utc": pd.to_datetime(raw["Time"], utc=True), "temp_c": pd.to_numeric(raw[tcol], errors="coerce")})
    return out.dropna().sort_values("time_utc").reset_index(drop=True)


def read_ref_csv(path: str | Path, time_col: str = "time_utc", temp_col: str = "temp_c",
                 clock_offset_s: float = 0.0) -> pd.DataFrame:
    """Reference logger CSV (UTC ISO timestamps). clock_offset_s = logger clock minus UTC, from the field sheet."""
    raw = pd.read_csv(path)
    t = pd.to_datetime(raw[time_col], utc=True) - pd.to_timedelta(clock_offset_s, unit="s")
    return pd.DataFrame({"time_utc": t, "temp_c": pd.to_numeric(raw[temp_col], errors="coerce")}).dropna() \
        .sort_values("time_utc").reset_index(drop=True)


def align_to_ref(mt: pd.DataFrame, ref: pd.DataFrame, t0_utc) -> pd.DataFrame:
    """Reference interpolated on a 1 s grid; MT sample-and-hold on the same grid (MT values are quantized)."""
    t0 = pd.Timestamp(t0_utc)
    t0 = t0.tz_localize("UTC") if t0.tzinfo is None else t0.tz_convert("UTC")
    end = min(mt.time_utc.max(), ref.time_utc.max())
    grid = pd.date_range(t0, end, freq="1s")
    s = (grid - t0).total_seconds().to_numpy()
    r = np.interp(grid.astype("int64"), ref.time_utc.astype("int64"), ref.temp_c)
    m = pd.Series(mt.temp_c.to_numpy(), index=mt.time_utc).reindex(grid, method="ffill").to_numpy()
    return pd.DataFrame({"t_s": s, "mt": m, "ref": r}).dropna().reset_index(drop=True)


# ------------------------------------------------------------------ first-order fit
def _filt(x: np.ndarray, tau: float, dt: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Zero-initial-state first-order response to x, and the free-decay basis a**i."""
    a = math.exp(-dt / tau)
    y = np.empty_like(x, dtype=float); acc = 0.0
    for i, v in enumerate(x):
        acc = a * acc + (1 - a) * v
        y[i] = acc
    return y, a ** np.arange(len(x))


@dataclass
class TauFit:
    tau_s: float
    delay_s: int
    bias_c: float
    rmse_c: float
    tau_ci95_s: tuple = field(default=(float("nan"), float("nan")))
    n_boot: int = 0


def _best(mt, ref, taus, delays):
    best = None
    for d in delays:
        x = np.concatenate([np.full(d, ref[0]), ref[: len(ref) - d]]) if d else ref
        for tau in taus:
            y, dec = _filt(x, tau)
            A = np.column_stack([y, dec, np.ones_like(y)])       # gain on filtered ref fixed to 1 below
            rhs = mt - y
            coef, *_ = np.linalg.lstsq(A[:, 1:], rhs, rcond=None)
            res = rhs - A[:, 1:] @ coef
            sse = float(res @ res)
            if best is None or sse < best[0]:
                best = (sse, tau, d, float(coef[1]), res, y + A[:, 1:] @ coef)
    return best


def fit_first_order(mt: np.ndarray, ref: np.ndarray, taus=None, delays=range(0, 6), n_boot: int = 200,
                    block: int = 30, seed: int = 20261109) -> TauFit:
    """Fit MT = first-order(ref delayed by d) + initial transient + bias on 1 s data. tau grid default 1..200 s."""
    mt = np.asarray(mt, float); ref = np.asarray(ref, float)
    taus = np.arange(1.0, 200.5, 0.5) if taus is None else np.asarray(taus, float)
    sse, tau, d, bias, res, fitted = _best(mt, ref, taus, list(delays))
    out = TauFit(tau_s=tau, delay_s=d, bias_c=bias, rmse_c=math.sqrt(sse / len(mt)))
    if n_boot:
        rng = np.random.default_rng(seed); n = len(res); bt = []
        local = taus[(taus >= tau / 3) & (taus <= tau * 3)]
        for _ in range(n_boot):
            idx = np.concatenate([np.arange(s, s + block) for s in rng.integers(0, max(n - block, 1), n // block + 1)])[:n] % n
            bt.append(_best(fitted + res[idx], ref, local, [d])[1])
        out.tau_ci95_s = tuple(float(x) for x in np.percentile(bt, [2.5, 97.5])); out.n_boot = n_boot
    return out


# ------------------------------------------------------------------ time to stability
def time_to_stability(t_s: np.ndarray, err: np.ndarray, eps: float = EPS_PRIMARY, final_window=FINAL_WINDOW,
                      horizon_s: float = HORIZON_S, block_s: float = BLOCK_S) -> float:
    """err = MT - REF. e_inf = median err in final_window. Returns the start of the first 10 s block after which every
    block mean up to horizon_s satisfies |block - e_inf| <= eps (0.0 if from the start; inf if never)."""
    t_s = np.asarray(t_s, float); err = np.asarray(err, float)
    fw = (t_s >= final_window[0]) & (t_s < final_window[1])
    if fw.sum() < 0.5 * (final_window[1] - final_window[0]):
        raise ValueError("final window not covered: session too short for the protocol")
    e_inf = float(np.median(err[fw]))
    edges = np.arange(0.0, horizon_s + block_s, block_s)
    dev = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (t_s >= a) & (t_s < b)
        dev.append(abs(float(np.mean(err[m])) - e_inf) if m.any() else np.nan)
    dev = np.array(dev)
    bad = np.where(~(dev <= eps))[0]              # NaN blocks count as not stable
    if len(bad) == 0:
        return 0.0
    if bad[-1] == len(dev) - 1:
        return float("inf")
    return float(edges[bad[-1] + 1])


# ------------------------------------------------------------------ decision rule
def ucb95_one_sided(k: int, n: int) -> float:
    return float(binomtest(k, n).proportion_ci(confidence_level=0.90, method="exact").high)


def decide_cap(ts_cold, ts_intermediate, ts_warm, tau_ucb95_s: float, dT0_p95_c: float, cells_cold: dict | None = None,
               phase: int = 1, candidates=CANDIDATES, eps: float = EPS_PRIMARY,
               n_cold_min: int = 20, n_other_min: int = 10) -> dict:
    """Pre-registered rule (PROPOSTA_VALIDAZIONE_TAU_v1 sec. 3). Returns status and the per-candidate checks."""
    ts_cold = np.asarray(ts_cold, float); ts_i = np.asarray(ts_intermediate, float); ts_w = np.asarray(ts_warm, float)
    if len(ts_cold) < n_cold_min or len(ts_i) < n_other_min or len(ts_w) < n_other_min:
        return dict(status="INSUFFICIENT_DATA", n=(len(ts_cold), len(ts_i), len(ts_w)))
    phys = tau_ucb95_s * math.log(max(dT0_p95_c, eps) / eps)
    checks = []
    for T in candidates:
        k = int((ts_cold > T).sum()); n = len(ts_cold)
        c1_point = k / n <= 0.10; c1_ucb = ucb95_one_sided(k, n) <= 0.20
        c2 = all((g > T).mean() <= 0.20 for g in (ts_i, ts_w))
        c3 = all((np.asarray(v, float) > T).mean() <= 0.20 for v in (cells_cold or {}).values() if len(v) >= 5)
        c4 = phys <= T
        checks.append(dict(T=T, k_cold=k, n_cold=n, p_cold=round(k / n, 3), ucb95_cold=round(ucb95_one_sided(k, n), 3),
                           C1_point=c1_point, C1_ucb=c1_ucb, C2_other_groups=c2, C3_cells=c3,
                           C4_physics=c4, physics_bound_s=round(phys, 1), passes=c1_point and c1_ucb and c2 and c3 and c4))
    passing = [c["T"] for c in checks if c["passes"]]
    first_fail_only_ucb = next((c for c in checks if not c["passes"] and c["C1_point"] and not c["C1_ucb"]
                                and c["C2_other_groups"] and c["C3_cells"] and c["C4_physics"]), None)
    if first_fail_only_ucb is not None and (not passing or first_fail_only_ucb["T"] < passing[0]):
        if phase == 1:
            return dict(status="EXTEND_TO_PHASE_2", candidate=first_fail_only_ucb["T"], checks=checks)
        if passing:
            return dict(status="PROVISIONAL_CONSERVATIVE", selected_s=passing[0], checks=checks)
        return dict(status="NONE_PASSES", checks=checks)
    if passing:
        return dict(status="SELECTED", selected_s=passing[0], checks=checks)
    return dict(status="NONE_PASSES", checks=checks)


# ------------------------------------------------------------------ CLI (to be completed when data exist)
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", required=True); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    sheet = pd.read_csv(a.sheet)
    rows = []
    for r in sheet.itertuples():
        if str(getattr(r, "valid", "Y")).upper() != "Y":
            continue
        mt = read_mt_csv(Path(a.data) / r.file_mt); ref = read_ref_csv(Path(a.data) / r.file_ref, clock_offset_s=float(r.ref_clock_offset_s))
        df = align_to_ref(mt, ref, r.t0_utc)
        row = dict(test_id=r.test_id, test_type=r.test_type, group=r.group)
        if r.test_type == "STEP":
            f = fit_first_order(df.mt.to_numpy(), df.ref.to_numpy()); row.update(asdict(f))
        else:
            e = (df.mt - df.ref).to_numpy()
            row.update(t_s_02=time_to_stability(df.t_s, e, EPS_PRIMARY), t_s_01=time_to_stability(df.t_s, e, EPS_SECONDARY))
        rows.append(row)
    pd.DataFrame(rows).to_csv(out / "tau_tests_results.csv", index=False)
    (out / "README.json").write_text(json.dumps(dict(sheet=a.sheet, n_tests=len(rows)), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()