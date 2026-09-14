"""Small shared robust-statistics helpers (weighted median/MAD) used by both
assessability.py (descriptive session metrics) and trend_methods.py (Method
1 estimation) -- kept in one place to avoid duplicate implementations
drifting apart.
"""
from __future__ import annotations

import numpy as np


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    if len(values) == 0:
        return float("nan")
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w)
    if cum[-1] <= 0:
        return float("nan")
    cutoff = cum[-1] / 2.0
    idx = np.searchsorted(cum, cutoff)
    idx = min(idx, len(v) - 1)
    return float(v[idx])


def mad(values: np.ndarray) -> float:
    if len(values) == 0:
        return float("nan")
    med = np.median(values)
    return float(np.median(np.abs(values - med)))


def weighted_mad(values: np.ndarray, weights: np.ndarray) -> float:
    if len(values) == 0:
        return float("nan")
    med = weighted_median(values, weights)
    return weighted_median(np.abs(values - med), weights)
