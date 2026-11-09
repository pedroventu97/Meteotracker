"""P1 repeatability of Meteotracker Tair anomalies on the E0 split.

Reuses the 2026-10-15 methodology (pass_anomaly / short_dt_anomaly: R = sum cov / sum sqrt(var_a var_b),
Fisher-mean r, campaign-cluster bootstrap) and extends it to the E0 split (route / spatial_block / day),
three QC profiles, explicit pair types (same campaign / same day / different day) and leave-one-* sensitivity.
QC is applied as masks (keep_<profile>); no data are deleted.
"""
from .core import (  # noqa: F401
    PAIR_TYPES,
    PROFILES,
    Params,
    bootstrap_pooled,
    build_passes,
    icc_oneway,
    location_level,
    pair_stats_from_long,
    pass_pairs,
    pooled,
)
