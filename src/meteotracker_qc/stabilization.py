from __future__ import annotations

import numpy as np
import pandas as pd


def detect_sensor_stabilization(temperatures: pd.Series, window: int = 5, min_stable_seconds: int = 60, config: dict | None = None) -> pd.DataFrame:
    """A simple warm-up detector that flags the initial period until the slope stabilizes."""
    cfg = config or {}
    warmup_cfg = cfg.get("warmup", {})
    window = int(warmup_cfg.get("window_size", window))
    slope_threshold = float(warmup_cfg.get("slope_threshold_c_per_s", 0.02))
    min_stable_seconds = int(warmup_cfg.get("min_stable_seconds", min_stable_seconds))

    s = pd.to_numeric(temperatures, errors="coerce")
    med = s.rolling(window, center=True, min_periods=1).median()
    slope = med.diff().fillna(0) / 1.0
    stabilized = np.abs(slope.rolling(window, min_periods=1).median()) < slope_threshold
    out = pd.DataFrame(index=s.index)
    out["qc_sensor_stabilization"] = (~stabilized).fillna(False)
    return out
