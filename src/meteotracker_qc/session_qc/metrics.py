"""Pure point -> segment -> session metric computation. No status/classification
here (see segment_status.py / session_status.py) -- this module only computes
numbers, deterministically, from already-QC-flagged point-level frames.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROFILES = ["permissive", "recommended", "restrictive"]

# Boolean flags unioned into each family for session-level "problem fraction"
# metrics (Section G). A row can trigger more than one flag in a family --
# these are unions, never sums, per principle B.4.
FAMILY_FLAG_UNIONS = {
    "temporal_problem_fraction": [
        "qc_nonmonotonic_timestamp", "qc_duplicate_timestamp",
        "qc_sampling_gap_short", "qc_sampling_gap_long",
    ],
    "gps_problem_fraction": [
        "qc_coord_missing", "qc_gps_freeze", "qc_possible_gps_freeze",
        "qc_spatial_jump", "qc_unrealistic_speed", "qc_unrealistic_acceleration",
    ],
    "stabilization_problem_fraction": ["qc_sensor_stabilization", "qc_segment_restart_recovery"],
    "ventilation_risk_fraction": ["qc_low_ventilation_possible"],
    "thermal_problem_fraction": ["qc_temp_isolated_spike", "qc_temp_rate_anomaly", "qc_sensor_plateau_possible"],
    "impossible_value_fraction": ["qc_temp_impossible", "qc_humidity_impossible", "qc_pressure_impossible"],
}


def _bool(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].fillna(False).astype(bool)


def _union(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    out = pd.Series(False, index=df.index)
    for c in cols:
        out = out | _bool(df, c)
    return out


def load_campaign_frames(campaign_id: str, profile_roots: dict[str, Path]) -> dict[str, pd.DataFrame]:
    """Read the 3 real per-profile parquet files for one campaign. Each
    profile's own tree is the only correct source for that profile's own
    `keep_<profile>` (see policy.py's documented single-run-projection
    caveat -- a projection from one tree cannot substitute for the others).
    """
    frames = {}
    for profile, root in profile_roots.items():
        campaign_dir = root / campaign_id
        parquet_files = sorted(campaign_dir.glob("*_standardized.parquet"))
        if len(parquet_files) != 1:
            raise ValueError(f"Expected one standardized parquet under {campaign_dir}; found {len(parquet_files)}")
        frames[profile] = pd.read_parquet(parquet_files[0])
    return frames


def build_reference_frame(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """recommended's own segmentation/flags as the single cross-profile
    reference (documented architectural choice), with each profile's own
    TRUE keep_<profile> attached by row position (row count/order verified
    identical across the 3 trees -- no profile ever drops rows).
    """
    ref = frames["recommended"].reset_index(drop=True).copy()
    perm = frames["permissive"].reset_index(drop=True)
    rest = frames["restrictive"].reset_index(drop=True)
    for profile, frame in frames.items():
        required = {"source_row", f"keep_{profile}"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Incompatible {profile} point-QC schema; missing {sorted(missing)}. Regenerate that profile with the scientific closure.")
        if len(frame) != len(ref) or not frame["source_row"].is_unique:
            raise ValueError(f"{profile} tree must contain each source row exactly once")
        if frame[f"keep_{profile}"].isna().any() or not pd.api.types.is_bool_dtype(frame[f"keep_{profile}"]):
            raise ValueError(f"{profile} keep column must contain non-null booleans")
        for key in ("source_file", "time_utc"):
            if key in ref and (key not in frame or not ref[key].equals(frame[key].reset_index(drop=True))):
                raise ValueError(f"{profile} tree {key} does not match recommended tree")
    if not (ref["source_row"].to_numpy() == perm["source_row"].to_numpy()).all():
        raise ValueError("permissive tree row order does not match recommended tree")
    if not (ref["source_row"].to_numpy() == rest["source_row"].to_numpy()).all():
        raise ValueError("restrictive tree row order does not match recommended tree")
    ref["keep_permissive_true"] = perm["keep_permissive"].to_numpy()
    ref["keep_recommended_true"] = ref["keep_recommended"]
    ref["keep_restrictive_true"] = rest["keep_restrictive"].to_numpy()
    return ref


def valid_interval_mask(
    df: pd.DataFrame,
    keep_column: str,
    *,
    segment_column: str = "segment_id",
    require_gps_valid: bool = False,
) -> pd.Series:
    """True at row i iff the interval (i-1, i] counts as valid for
    `keep_column`: both endpoints keep_column==True, same segment, and (if
    require_gps_valid) both endpoints gps_valid==True. Row 0 of the frame
    and the first row of every segment are always False (no interval to
    form). See reports/session_qc_report.md section C for the rationale.
    """
    keep = df[keep_column].fillna(False).astype(bool)
    same_segment = df[segment_column] == df[segment_column].shift(1)
    mask = keep & keep.shift(1, fill_value=False) & same_segment
    if require_gps_valid:
        gps_valid = _bool(df, "gps_valid")
        mask = mask & gps_valid & gps_valid.shift(1, fill_value=False)
    return mask.fillna(False)


def _sum_and_longest_run(values: pd.Series, mask: pd.Series) -> tuple[float, float]:
    masked = values.where(mask, 0.0).fillna(0.0)
    total = float(masked.sum())
    if not mask.any():
        return total, 0.0
    run_id = mask.ne(mask.shift(1)).cumsum()
    run_sums = masked.groupby(run_id).sum()
    run_is_true = mask.groupby(run_id).first()
    true_sums = run_sums[run_is_true]
    longest = float(true_sums.max()) if len(true_sums) else 0.0
    return total, longest


def _mode_or_none(series: pd.Series):
    non_null = series.dropna()
    non_null = non_null[non_null != ""]
    if non_null.empty:
        return None
    counts = non_null.value_counts()
    top = counts[counts == counts.max()].index.tolist()
    return sorted(top)[0]  # alphabetical tie-break


def _reason_family_lookup(flag_policy: pd.DataFrame) -> dict[str, str]:
    return dict(zip(flag_policy["flag_name"], flag_policy["reason_family"]))


def _secondary_reasons(exclusion_reason_strings: pd.Series, primary: str | None) -> str:
    flags = set()
    for s in exclusion_reason_strings.dropna():
        if not s:
            continue
        flags.update(s.split(";"))
    flags.discard(primary)
    return ";".join(sorted(flags))


def _one_group_metrics(g: pd.DataFrame, family_lookup: dict[str, str], profile_suffix: str = "") -> dict:
    """Metrics shared by segment- and session-level aggregation (everything
    in Section E except identification columns, which the caller adds)."""
    n_raw = len(g)
    time_valid = g["time_utc"].notna()
    time_series = g.loc[time_valid, "time_utc"]
    nominal_time_span_s = float((time_series.max() - time_series.min()).total_seconds()) if len(time_series) >= 2 else 0.0

    dt_s = pd.to_numeric(g["dt_s"], errors="coerce")
    positive_dt = dt_s[dt_s > 0]
    not_break = ~_bool(g, "qc_segment_break")
    observed_sampling_duration_s = float(dt_s.where((dt_s > 0) & not_break, 0.0).fillna(0.0).sum())
    missing_gap_duration_s = float(dt_s.where(_bool(g, "qc_sampling_gap_long"), 0.0).fillna(0.0).sum())

    distance = pd.to_numeric(g.get("distance_from_previous_m", pd.Series(index=g.index, dtype=float)), errors="coerce")
    # Defense in depth: gps_qc.py already guarantees NaN distance at a
    # segment boundary, but this layer re-asserts it explicitly rather than
    # trusting an upstream invariant silently.
    distance_safe = distance.where(~_bool(g, "qc_segment_break"), np.nan)
    observed_distance_km = float(distance_safe.fillna(0.0).sum()) / 1000.0

    out = {
        "n_raw": n_raw,
        "n_permissive": int(_bool(g, "keep_permissive_true").sum()),
        "n_recommended": int(_bool(g, "keep_recommended_true").sum()),
        "n_restrictive": int(_bool(g, "keep_restrictive_true").sum()),
        "nominal_time_span_s": nominal_time_span_s,
        "observed_sampling_duration_s": observed_sampling_duration_s,
        "missing_gap_duration_s": missing_gap_duration_s,
        "observed_distance_km": observed_distance_km,
        "sampling_interval_expected_s": float(g["sampling_interval_expected_seconds"].iloc[0]) if "sampling_interval_expected_seconds" in g.columns and n_raw else np.nan,
        "sampling_interval_median_s": float(positive_dt.median()) if len(positive_dt) else np.nan,
        "sampling_interval_p95_s": float(positive_dt.quantile(0.95)) if len(positive_dt) else np.nan,
        "n_short_gaps": int(_bool(g, "qc_sampling_gap_short").sum()),
        "n_long_gaps": int(_bool(g, "qc_sampling_gap_long").sum()),
        "max_internal_gap_s": float(dt_s.max()) if dt_s.notna().any() else 0.0,
        "gps_valid_fraction": float(_bool(g, "gps_valid").mean()) if n_raw else np.nan,
        "gps_freeze_fraction": float(_bool(g, "qc_gps_freeze").mean()) if n_raw else np.nan,
        "possible_gps_freeze_fraction": float(_bool(g, "qc_possible_gps_freeze").mean()) if n_raw else np.nan,
        "spatial_jump_fraction": float(_bool(g, "qc_spatial_jump").mean()) if n_raw else np.nan,
        "isolated_position_outlier_fraction": float(_bool(g, "qc_isolated_position_outlier").mean()) if n_raw else np.nan,
        "unrealistic_speed_fraction": float(_bool(g, "qc_unrealistic_speed").mean()) if n_raw else np.nan,
        "unrealistic_acceleration_fraction": float(_bool(g, "qc_unrealistic_acceleration").mean()) if n_raw else np.nan,
        "low_speed_device_fraction": float(_bool(g, "qc_low_speed_device").mean()) if n_raw else np.nan,
        "low_speed_gps_fraction": float(_bool(g, "qc_low_speed_gps").mean()) if n_raw else np.nan,
        "low_ventilation_possible_fraction": float(_bool(g, "qc_low_ventilation_possible").mean()) if n_raw else np.nan,
        "stationary_fraction": float(_bool(g, "qc_stationary").mean()) if n_raw else np.nan,
        "stop_fraction": float(_bool(g, "qc_stop_event").mean()) if n_raw else np.nan,
        "post_stop_recovery_fraction": float(_bool(g, "qc_post_stop_recovery").mean()) if n_raw else np.nan,
        "temp_valid_fraction": float(g["canonical_temperature_c"].notna().mean()) if "canonical_temperature_c" in g.columns and n_raw else np.nan,
        "temp_spike_fraction": float(_bool(g, "qc_temp_isolated_spike").mean()) if n_raw else np.nan,
        "temp_rate_anomaly_fraction": float(_bool(g, "qc_temp_rate_anomaly").mean()) if n_raw else np.nan,
        "sensor_plateau_fraction": float(_bool(g, "qc_sensor_plateau_possible").mean()) if n_raw else np.nan,
        "impossible_value_fraction": float(_union(g, FAMILY_FLAG_UNIONS["impossible_value_fraction"]).mean()) if n_raw else np.nan,
    }

    stab_col = _union(g, ["qc_sensor_stabilization", "qc_segment_restart_recovery"])
    out["stabilization_fraction"] = float(stab_col.mean()) if n_raw else np.nan
    reached = bool((g.get("stabilization_window_end_reason") == "slope_confirmed_stable").any())
    out["stabilization_reached"] = reached
    if reached and "stabilization_seconds_from_segment_start" in g.columns:
        stable_rows = g.loc[~stab_col, "stabilization_seconds_from_segment_start"]
        out["stabilization_reached_after_s"] = float(stable_rows.min()) if len(stable_rows) else np.nan
    else:
        out["stabilization_reached_after_s"] = np.nan
    out["stabilization_reason_code"] = g["stabilization_window_end_reason"].iloc[0] if "stabilization_window_end_reason" in g.columns and n_raw else None

    excluded = g.loc[~_bool(g, "keep_recommended_true")]
    out["excluded_recommended_fraction"] = float(len(excluded) / n_raw) if n_raw else np.nan
    primary = _mode_or_none(excluded.get("qc_primary_reason", pd.Series(dtype=object)))
    out["primary_exclusion_reason"] = primary
    out["primary_exclusion_family"] = family_lookup.get(primary) if primary else None
    out["secondary_exclusion_reasons"] = _secondary_reasons(excluded.get("qc_exclusion_reasons_recommended", pd.Series(dtype=object)), primary)
    reason_count = pd.to_numeric(g.get("qc_reason_count", pd.Series(index=g.index, dtype=float)), errors="coerce")
    out["exclusion_reason_count"] = float(reason_count.loc[excluded.index].mean()) if len(excluded) else 0.0
    out["multi_flagged_fraction"] = float((reason_count > 1).mean()) if n_raw else np.nan

    for profile in PROFILES:
        keep_col = f"keep_{profile}_true"
        duration_mask = valid_interval_mask(g, keep_col)
        distance_mask = valid_interval_mask(g, keep_col, require_gps_valid=True)
        duration_total, duration_longest = _sum_and_longest_run(dt_s, duration_mask)
        distance_total, distance_longest = _sum_and_longest_run(distance, distance_mask)
        out[f"valid_duration_{profile}_s"] = duration_total
        out[f"valid_distance_{profile}_km"] = distance_total / 1000.0
        out[f"longest_valid_contiguous_duration_{profile}_s"] = duration_longest
        out[f"longest_valid_contiguous_distance_{profile}_km"] = distance_longest / 1000.0

    return out


def compute_segment_metrics(ref: pd.DataFrame, campaign_id: str, source_file: str, family_lookup: dict[str, str]) -> pd.DataFrame:
    rows = []
    for segment_id, g in ref.groupby("segment_id", sort=True):
        g = g.reset_index(drop=True)
        time_valid = g["time_utc"].notna()
        row = {
            "canonical_campaign_id": campaign_id,
            "source_file": source_file,
            "segment_id": int(segment_id),
            "segment_start_timestamp": g.loc[time_valid, "time_utc"].min() if time_valid.any() else pd.NaT,
            "segment_end_timestamp": g.loc[time_valid, "time_utc"].max() if time_valid.any() else pd.NaT,
            "segment_start_reason": g["segment_start_reason"].iloc[0],
            "segment_end_reason": g["segment_end_reason"].iloc[0],
        }
        row.update(_one_group_metrics(g, family_lookup))
        row["valid_duration_recommended_s"] = row["valid_duration_recommended_s"]  # explicit per spec naming (already present)
        row["valid_distance_recommended_km"] = row["valid_distance_recommended_km"]
        rows.append(row)
    return pd.DataFrame(rows)


def compute_session_metrics(ref: pd.DataFrame, segment_metrics: pd.DataFrame, campaign_id: str, source_file: str, family_lookup: dict[str, str]) -> dict:
    time_valid = ref["time_utc"].notna()
    session = _one_group_metrics(ref, family_lookup)
    session.update({
        "canonical_campaign_id": campaign_id,
        "source_file": source_file,
        "campaign_start_timestamp": ref.loc[time_valid, "time_utc"].min() if time_valid.any() else pd.NaT,
        "campaign_end_timestamp": ref.loc[time_valid, "time_utc"].max() if time_valid.any() else pd.NaT,
        "n_segments": int(ref["segment_id"].nunique()),
    })
    n_raw = session["n_raw"]
    for profile in PROFILES:
        session[f"keep_fraction_{profile}"] = session[f"n_{profile}"] / n_raw if n_raw else np.nan

    session["observed_to_nominal_time_ratio"] = (
        session["observed_sampling_duration_s"] / session["nominal_time_span_s"] if session["nominal_time_span_s"] else np.nan
    )
    session["recommended_to_observed_time_ratio"] = (
        session["valid_duration_recommended_s"] / session["observed_sampling_duration_s"] if session["observed_sampling_duration_s"] else np.nan
    )
    session["recommended_to_observed_distance_ratio"] = (
        session["valid_distance_recommended_km"] / session["observed_distance_km"] if session["observed_distance_km"] else np.nan
    )
    session["longest_valid_segment_duration_s"] = float(segment_metrics["valid_duration_recommended_s"].max()) if len(segment_metrics) else 0.0
    session["longest_valid_segment_distance_km"] = float(segment_metrics["valid_distance_recommended_km"].max()) if len(segment_metrics) else 0.0

    session["total_gap_duration_s"] = session["missing_gap_duration_s"]
    session["gap_fraction_of_nominal_span"] = (
        session["missing_gap_duration_s"] / session["nominal_time_span_s"] if session["nominal_time_span_s"] else np.nan
    )
    session["max_gap_s"] = session["max_internal_gap_s"]

    for family_metric, cols in FAMILY_FLAG_UNIONS.items():
        session[family_metric] = float(_union(ref, cols).mean()) if n_raw else np.nan

    excluded = ref.loc[~_bool(ref, "keep_recommended_true")]
    reason_count = pd.to_numeric(ref.get("qc_reason_count", pd.Series(index=ref.index, dtype=float)), errors="coerce")
    excluded_reason_count = reason_count.loc[excluded.index]
    session["recommended_primary_reason_mode"] = session["primary_exclusion_reason"]
    session["fraction_excluded_by_exactly_one_reason"] = float((excluded_reason_count == 1).mean()) if len(excluded) else np.nan
    session["fraction_excluded_by_multiple_reasons"] = float((excluded_reason_count > 1).mean()) if len(excluded) else np.nan

    canonical_cols = [c for c in ref.columns if c.startswith("canonical_")]
    present_cols = [c for c in canonical_cols if ref[c].notna().any()]
    session["n_canonical_fields_total"] = len(canonical_cols)
    session["n_canonical_fields_present"] = len(present_cols)
    session["canonical_fields_present_fraction"] = (
        len(present_cols) / len(canonical_cols) if canonical_cols else np.nan
    )
    is_reduced_schema = len(present_cols) <= 5  # matches the 5-column raw export variant
    session["is_reduced_schema"] = bool(is_reduced_schema)

    return session
