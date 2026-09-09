"""Local-time (Europe/Rome) fields and a configurable, preliminary time-of-day bin.

Section 12 of the Phase 1 spec: no sunrise/sunset, no solar position, no weather
classification here -- just calendar/clock fields derived from time_utc, correctly
converted to Europe/Rome local time (DST-aware via pandas/tzdata).
"""
from __future__ import annotations

import pandas as pd

from .config import RepeatedRoutesConfig

TZ = "Europe/Rome"


def to_local(ts_utc: pd.Timestamp) -> pd.Timestamp:
    if ts_utc.tzinfo is None:
        ts_utc = ts_utc.tz_localize("UTC")
    return ts_utc.tz_convert(TZ)


def hour_decimal(ts_local: pd.Timestamp) -> float:
    return ts_local.hour + ts_local.minute / 60.0 + ts_local.second / 3600.0


def classify_time_bin(hour_dec: float, cfg: RepeatedRoutesConfig) -> str:
    boundaries = cfg.time_bin_boundaries
    ordered = sorted(boundaries.items(), key=lambda kv: kv[1])
    label = ordered[-1][0]
    for name, start_hour in ordered:
        if hour_dec >= start_hour:
            label = name
        else:
            break
    return label


def describe_timestamp(ts_utc: pd.Timestamp, cfg: RepeatedRoutesConfig) -> dict:
    local = to_local(pd.Timestamp(ts_utc))
    hour_dec = hour_decimal(local)
    return {
        "local_date": local.date().isoformat(),
        "local_time": local.strftime("%H:%M:%S"),
        "local_hour_decimal": hour_dec,
        "month": local.month,
        "day_of_week": local.day_name(),
        "time_bin": classify_time_bin(hour_dec, cfg),
    }
