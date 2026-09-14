from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Geod

from .time_qc import estimate_expected_sampling_interval_s

GEOD = Geod(ellps="WGS84")


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def detect_off_network_possible(df: pd.DataFrame, network_geometry=None) -> pd.Series:
    """Optional, informational-only signal: distance from a supplied local
    network geometry (roads/paths/etc). No network is fetched or bundled with
    this repository, and OSM is deliberately not treated as ground truth in
    this phase -- returns all-NA (nullable boolean) unless a caller explicitly
    supplies `network_geometry`, a documented but unimplemented extension
    point for a future local network dataset.
    """
    if network_geometry is None:
        return pd.Series(pd.NA, index=df.index, dtype="boolean")
    raise NotImplementedError(
        "network_geometry-based off-network detection is not implemented in this pass; "
        "qc_off_network_possible stays informational-only and NA until a local network "
        "dataset is supplied."
    )


def detect_gps_issues(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    out = df.copy()
    cfg = config or {}
    gps_cfg = cfg.get("gps", {})
    jump_distance_m = float(gps_cfg.get("gps_jump_distance_m", 80.0))
    jump_dt_s = float(gps_cfg.get("gps_jump_dt_s", 2.0))
    acceleration_abs = float(gps_cfg.get("acceleration_ms2_abs", 5.0))
    max_speed_kmh_absolute = float(gps_cfg.get("max_speed_kmh_absolute", 150.0))
    freeze_speed_kmh = float(gps_cfg.get("freeze_speed_threshold_kmh", 0.5))
    coord_repeated_tolerance_m = float(gps_cfg.get("coord_repeated_tolerance_m", 2.0))
    isolated_outlier_excess_m = float(gps_cfg.get("isolated_outlier_excess_m", 40.0))
    speed_disagreement_abs_kmh = float(gps_cfg.get("speed_disagreement_abs_kmh", 8.0))
    speed_disagreement_rel_fraction = float(gps_cfg.get("speed_disagreement_rel_fraction", 0.35))

    if "time_utc" not in out.columns:
        out["time_utc"] = pd.to_datetime(out.get("Time"), errors="coerce", utc=True)
    if "dt_s" not in out.columns:
        out["dt_s"] = pd.Series(np.nan, index=out.index, dtype=float)
        valid_time = out["time_utc"].notna()
        if valid_time.any():
            out.loc[valid_time, "dt_s"] = out.loc[valid_time, "time_utc"].diff().dt.total_seconds()
    if "segment_id" not in out.columns:
        # Standalone/ungated call (no detect_time_issues upstream): derive a
        # minimal but real segmentation from this file's own cadence instead
        # of a trivial constant, so speed/distance are never silently
        # computed across a large real gap just because no segment_id was
        # supplied. Reuses time_qc.py's own estimator -- single source of
        # truth for what counts as a gap, whether reached via the pipeline
        # or called directly.
        time_cfg = cfg.get("time", {})
        expected_dt_s = estimate_expected_sampling_interval_s(
            out["dt_s"],
            min_samples_for_estimate=int(time_cfg.get("min_samples_for_cadence_estimate", 20)),
            fallback_dt_s=float(time_cfg.get("fallback_expected_dt_s", 1.0)),
            outlier_multiplier=float(time_cfg.get("outlier_multiplier", 8.0)),
        )
        long_threshold = max(
            float(time_cfg.get("gap_long_multiplier", 5.0)) * expected_dt_s,
            float(time_cfg.get("gap_absolute_floor_s", 1.0)),
        )
        nonpositive = out["dt_s"] <= 0
        long_gap = out["dt_s"] > long_threshold
        out["segment_id"] = (long_gap | nonpositive).cumsum()

    lat = _to_numeric(out.get("Lat", pd.Series(index=out.index, dtype=float)))
    lon = _to_numeric(out.get("Lon", pd.Series(index=out.index, dtype=float)))
    dt_s = pd.to_numeric(out["dt_s"], errors="coerce")
    segment_id = out["segment_id"]
    speed_device_kmh = pd.to_numeric(out.get("Speed[km/h]", pd.Series(index=out.index, dtype=float)), errors="coerce")
    temp_c = pd.to_numeric(out.get("Temp[°C]", pd.Series(index=out.index, dtype=float)), errors="coerce")

    n = len(out)
    out["qc_coord_missing"] = lat.isna() | lon.isna()
    out["qc_coord_outside_aoi"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out["qc_off_network_possible"] = detect_off_network_possible(out)
    out["speed_device_kmh"] = speed_device_kmh
    out["speed_device_valid"] = speed_device_kmh.notna()

    empty_f = pd.Series(np.nan, index=out.index, dtype=float)
    out["distance_from_previous_m"] = empty_f.copy()
    out["speed_gps_kmh"] = empty_f.copy()
    out["acceleration_gps_mps2"] = empty_f.copy()
    out["bearing_deg"] = empty_f.copy()
    out["bearing_change_deg"] = empty_f.copy()

    coord_valid = lat.notna() & lon.notna()
    if n >= 2:
        coord_valid_prev = coord_valid.shift(1, fill_value=False)
        same_segment_prev = segment_id == segment_id.shift(1)
        pair_valid = coord_valid & coord_valid_prev & same_segment_prev

        lat_prev = lat.shift(1)
        lon_prev = lon.shift(1)
        idx = out.index[pair_valid]
        if len(idx) > 0:
            az12, _, dist = GEOD.inv(
                lon_prev.loc[idx].to_numpy(),
                lat_prev.loc[idx].to_numpy(),
                lon.loc[idx].to_numpy(),
                lat.loc[idx].to_numpy(),
            )
            out.loc[idx, "distance_from_previous_m"] = dist
            out.loc[idx, "bearing_deg"] = (np.asarray(az12) + 360.0) % 360.0
            out.loc[idx, "speed_gps_kmh"] = out.loc[idx, "distance_from_previous_m"] / dt_s.loc[idx] * 3.6

        bearing_diff = out["bearing_deg"].diff()
        out["bearing_change_deg"] = ((bearing_diff + 180.0) % 360.0) - 180.0

        speed_mps = out["speed_gps_kmh"] / 3.6
        accel_denom = dt_s.clip(lower=1.0)
        out["acceleration_gps_mps2"] = speed_mps.diff() / accel_denom
    else:
        pair_valid = pd.Series(False, index=out.index)

    out["cumulative_distance_segment_m"] = out.groupby(segment_id)["distance_from_previous_m"].cumsum()
    out["cumulative_distance_session_m"] = out["distance_from_previous_m"].cumsum()

    out["speed_gps_valid"] = out["speed_gps_kmh"].notna()
    speed_difference = out["speed_device_kmh"] - out["speed_gps_kmh"]
    out["speed_difference_kmh"] = speed_difference
    gps_speed_meaningful = out["speed_gps_kmh"].abs() > 1.0
    out["speed_ratio"] = (out["speed_device_kmh"] / out["speed_gps_kmh"]).where(gps_speed_meaningful)

    segment_boundary = segment_id != segment_id.shift(1)
    disagreement = (
        speed_difference.abs() > speed_disagreement_abs_kmh
    ) | ((out["speed_ratio"] - 1.0).abs() > speed_disagreement_rel_fraction)
    disagreement = disagreement.fillna(False)

    device_ok = out["speed_device_valid"]
    gps_ok = out["speed_gps_valid"]
    conditions = [
        device_ok & gps_ok & disagreement,
        device_ok & gps_ok & ~disagreement,
        device_ok & ~gps_ok & segment_boundary,
        device_ok & ~gps_ok & ~segment_boundary,
        ~device_ok & gps_ok,
        ~device_ok & ~gps_ok & segment_boundary,
    ]
    choices = [
        "BOTH_AVAILABLE_DISAGREE",
        "BOTH_AVAILABLE_CONSISTENT",
        "NOT_EVALUABLE_AFTER_GAP",
        "DEVICE_ONLY",
        "GPS_ONLY",
        "NOT_EVALUABLE_AFTER_GAP",
    ]
    out["speed_evidence_class"] = np.select(conditions, choices, default="NEITHER_AVAILABLE")
    out["qc_speed_disagreement"] = out["speed_evidence_class"] == "BOTH_AVAILABLE_DISAGREE"

    # Coordinate repetition: geodesic tolerance instead of bit-exact float
    # equality, and evaluated independently of segment continuity (a device
    # can genuinely stay in the same spot across a reconnection).
    coord_valid_prev_any = coord_valid.shift(1, fill_value=False)
    repeat_pair_valid = coord_valid & coord_valid_prev_any
    distance_for_repeat_m = pd.Series(np.nan, index=out.index)
    idx2 = out.index[repeat_pair_valid]
    if len(idx2) > 0:
        _, _, dist2 = GEOD.inv(
            lon.shift(1).loc[idx2].to_numpy(),
            lat.shift(1).loc[idx2].to_numpy(),
            lon.loc[idx2].to_numpy(),
            lat.loc[idx2].to_numpy(),
        )
        distance_for_repeat_m.loc[idx2] = dist2
    out["distance_from_previous_repeat_check_m"] = distance_for_repeat_m
    qc_coord_repeated = (distance_for_repeat_m <= coord_repeated_tolerance_m).fillna(False)
    out["qc_coord_repeated"] = qc_coord_repeated

    repeated_block = qc_coord_repeated & (
        qc_coord_repeated.shift(1, fill_value=False) | qc_coord_repeated.shift(-1, fill_value=False)
    )

    device_confirmed_low = out["speed_device_kmh"] <= freeze_speed_kmh
    gps_confirmed_low = out["speed_gps_kmh"] <= freeze_speed_kmh
    device_ok_for_freeze = out["speed_device_kmh"].isna() | device_confirmed_low
    gps_ok_for_freeze = out["speed_gps_kmh"].isna() | gps_confirmed_low
    any_speed_confirmed_low = device_confirmed_low.fillna(False) | gps_confirmed_low.fillna(False)
    speed_evidence_for_freeze = device_ok_for_freeze & gps_ok_for_freeze & any_speed_confirmed_low

    # Optional corroborating signal (diagnostic only, does not gate the
    # boolean flags): if temperature keeps changing while position is
    # repeated, the sensor/device is more likely alive and this is a real
    # stop rather than a GNSS-chip-only freeze.
    temp_diff_abs = temp_c.diff().abs()
    out["gps_freeze_meteo_still_varying"] = (
        temp_diff_abs.rolling(3, min_periods=1, center=True).max() > 0.05
    ).fillna(False)

    out["qc_possible_gps_freeze"] = repeated_block & ~device_confirmed_low.fillna(False)
    out["qc_gps_freeze"] = repeated_block & speed_evidence_for_freeze
    out["qc_stationary"] = qc_coord_repeated & device_confirmed_low.fillna(False) & gps_confirmed_low.fillna(False)

    # Isolated 3-point outlier: prev -> current -> next detour distance in
    # excess of prev -> next direct distance, restricted to same-segment
    # triplets so it is never evaluated across a gap or session boundary.
    lat_next = lat.shift(-1)
    lon_next = lon.shift(-1)
    next_valid = lat_next.notna() & lon_next.notna()
    same_segment_next = segment_id == segment_id.shift(-1)
    triplet_valid = pair_valid & next_valid & same_segment_next

    dist_to_next = pd.Series(np.nan, index=out.index)
    dist_direct = pd.Series(np.nan, index=out.index)
    idx3 = out.index[triplet_valid]
    if len(idx3) > 0:
        _, _, d_next = GEOD.inv(
            lon.loc[idx3].to_numpy(), lat.loc[idx3].to_numpy(),
            lon_next.loc[idx3].to_numpy(), lat_next.loc[idx3].to_numpy(),
        )
        dist_to_next.loc[idx3] = d_next
        _, _, d_direct = GEOD.inv(
            lon_prev.loc[idx3].to_numpy(), lat_prev.loc[idx3].to_numpy(),
            lon_next.loc[idx3].to_numpy(), lat_next.loc[idx3].to_numpy(),
        )
        dist_direct.loc[idx3] = d_direct

    excess_m = out["distance_from_previous_m"] + dist_to_next - dist_direct
    out["position_outlier_excess_m"] = excess_m
    out["qc_isolated_position_outlier"] = (excess_m > isolated_outlier_excess_m).fillna(False)

    out["qc_gps_jump"] = (out["distance_from_previous_m"] > jump_distance_m) & (dt_s <= jump_dt_s)
    out["qc_gps_jump"] = out["qc_gps_jump"].fillna(False)
    out["qc_spatial_jump"] = out["qc_gps_jump"] | out["qc_isolated_position_outlier"]

    out["qc_unrealistic_speed"] = (out["speed_gps_kmh"] > max_speed_kmh_absolute).fillna(False)
    out["qc_unrealistic_acceleration"] = (out["acceleration_gps_mps2"].abs() > acceleration_abs).fillna(False)
    # Deprecated legacy-compatibility aliases (formulas unchanged in meaning,
    # renamed for clarity): kept because referenced by name in existing tests.
    out["qc_impossible_acceleration"] = out["qc_unrealistic_acceleration"]

    return out
