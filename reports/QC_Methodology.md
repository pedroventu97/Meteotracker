# QC methodology (operational summary)

This document describes the current QC method in plain terms. For the full audit trail, findings, and verification evidence, see [Meteotracker_QC_Audit_Report.md](Meteotracker_QC_Audit_Report.md) (first-generation audit) and [targeted_qc_audit.md](targeted_qc_audit.md) + [targeted_qc_implementation.md](targeted_qc_implementation.md) (second-generation audit and implementation, "Prompt 2"). This page is intentionally short and does not repeat that evidence.

## 1. Raw preservation

Every raw CSV under `data/raw/` is read but never modified in place. Each output row carries `source_file` (the raw filename) and `source_row` (its 0-based row index in that file) so any QC-flagged or derived value can be traced back to the exact original observation. Raw files are never deleted by the pipeline, regardless of whether they are used in an analysis run — see "Duplicate handling" below.

## 2. Temporal standardization

`time_qc.py` parses the `Time` column explicitly (`format="mixed"`, no silent format inference), classifies each file's timezone handling (`explicit_offset`, `ambiguous`, or `invalid`), and derives `time_utc`, `time_local` (Europe/Rome), `dt_s` (row-to-row delta). The expected sampling cadence (`sampling_interval_expected_seconds`) is estimated per campaign from the campaign's own data (median of clean, non-gap `dt_s` values, `time.*` config) rather than assumed to be 1 Hz — 32/39 raw files are natively ~1 Hz, 7/39 are natively ~2 Hz. Gaps are split into `qc_sampling_gap_short` (warning only) and `qc_sampling_gap_long` (closes the segment: `qc_segment_break`/`segment_id`, with `segment_start_reason`/`segment_end_reason`). A gap never invalidates the valid points on either side of it. Out-of-order and duplicate timestamps are flagged (`qc_nonmonotonic_timestamp`/`qc_time_order`, `qc_duplicate_timestamp`/`qc_time_duplicate`) without dropping rows. `qc_time_gap`/`qc_new_segment` remain as legacy-compatible aliases.

## 3. GPS QC

`gps_qc.py` computes step distance/speed/acceleration/bearing from consecutive valid fixes within the same segment (geodesic via `pyproj`, never across a segment boundary), and tracks two speeds side by side — `speed_device_kmh` (device-reported) and `speed_gps_kmh` (recalculated) — never merging them, since the audit found their correlation ranges from -0.056 to 0.96 across campaigns. `speed_evidence_class` records which source(s) were available and whether they agree (`qc_speed_disagreement`). GPS jumps (`qc_gps_jump`) and isolated 3-point position outliers (`qc_isolated_position_outlier`, a detour-vs-direct-distance test that distinguishes a snapback error from a real, sustained route deviation) are combined into `qc_spatial_jump`. Repeated coordinates use a geodesic distance tolerance (not bit-exact equality) and are tracked separately from confirmed freeze: `qc_gps_freeze` requires a repeated-coordinate block *and* both available speeds confirming near-zero motion; `qc_possible_gps_freeze` is the more permissive companion signal. `qc_unrealistic_speed`/`qc_unrealistic_acceleration` (correct m/s² units; the pre-existing formula was silently computing (km/h)/s) round out the GNSS checks.

## 4. Low speed / ventilation and stops

`ventilation_qc.py` treats the thesis's ~7 km/h reference as ventilation-adequacy evidence, not an automatic thermal-error rule: `qc_low_speed_device`/`qc_low_speed_gps` are raw signals, `ventilation_evidence_class` records which source(s) confirm low speed, and `qc_low_ventilation_possible` is a risk flag (never excludes under permissive/recommended). `local_hour_bucket` (day/night, civil time) and `radiation_context` (campaign-relative, since `Radiation[]` has no declared unit and wildly varying population) add optional context. Stops (`qc_stationary`, computed in gps_qc.py) are grouped into `qc_stop_event` (real elapsed time ≥ `stops.min_significant_stop_s`) and followed by `qc_post_stop_recovery` until speed has stayed above the ventilation threshold continuously for `stops.recovery_min_duration_s` — all time-based, so it works the same at 1 Hz and 2 Hz cadence.

## 5. Meteorological QC

`meteo_qc.py` flags physically impossible temperature/humidity/pressure values against configurable limits (now wired into severity — previously computed but ignored), detects isolated temperature spikes via a rolling median/MAD test (`qc_temp_isolated_spike`, config-driven window/multiplier/floor), a segment-gated rate-of-change anomaly (`qc_temp_rate_anomaly`, de-escalated when the elevated rate persists ≥ `thermal.rate_anomaly_persistence_s` — a real sustained urban-microclimate transition is not an error), and a plateau signal (`qc_sensor_plateau_possible`, informational only — no independent channel exists to ever confirm a stuck sensor).

## 6. Sensor stabilization

`stabilization.py` searches, from the start of each segment, for the first continuous window of `warmup.min_stable_seconds` real seconds where the rolling-median thermal slope stays under `warmup.slope_threshold_c_per_s` (and, when speed context is available, where ventilation has been adequate for at least `warmup.min_ventilated_duration_s` seconds somewhere in that window). Once found, the flag drops to `False` and never reactivates later in the same segment — a later thermal transition is `qc_temp_rate_anomaly`'s job, not this detector's. Only the first segment of a file gets `qc_sensor_stabilization` (true session-start warm-up); every later segment (after a gap) gets `qc_segment_restart_recovery` instead, from the same underlying search. If stability is never confirmed, the leading stretch is capped at `warmup.max_window_s` and marked `STABILIZATION_NOT_REACHED` rather than flagging the whole segment or failing the pipeline. `warmup.min_stable_seconds` was previously read from config and never used anywhere (dead code) — it is now load-bearing.

## 7. Derived variables

`derived_variables.py` recomputes dew point (Magnus approximation) and potential temperature from temperature/humidity/pressure, and reports the difference against the device's own reported values (`dewpoint_difference_c`, `theta_difference_k`) as an independent cross-check.

## 8. Flag policy and severity

Every `qc_*` flag has a documented action in `config/flag_policy.csv`: `INFO_ONLY` / `WARNING_ONLY` / `EXCLUDE_RECOMMENDED` / `EXCLUDE_RESTRICTIVE` / `EXCLUDE_ALL_SCIENTIFIC` / `SEGMENT_BREAK` / `NOT_APPLICABLE`. `policy.py::apply_flag_policy()` reads this table to build, per row, `qc_severity`/`qc_exclusion_reasons` (for the profile the current run actually uses) plus a same-flags-held-fixed *policy projection* of what severity would be under all three profiles (`qc_severity_{permissive,recommended,restrictive}`, `keep_{permissive,recommended,restrictive}`) — this projection does not re-derive the underlying flags from each profile's own thresholds, only re-applies the action tier, so it is not a substitute for the three separate `outputs/{permissive,recommended,restrictive}` runs, which remain authoritative. `keep_strict`/`keep_relaxed` remain as legacy-compatible severity-budget columns (`filtering.strict_keep_threshold`/`relaxed_keep_threshold`), never a destructive filter — both `_strict.csv` and `_relaxed.csv` are written alongside the full `_flagged.csv`. `use_for_satellite_comparison` additionally requires GPS validity (now also excluding missing coordinates), no sensor-stabilization flag, and a timezone-safe classification.

Three configuration profiles tune GPS/warm-up/thermal/stop/gap thresholds; see `config/threshold_provenance.csv` for every threshold's value, unit, and evidence source (`thesis_documented`, `device_documentation`, `audit_observed`, `data_distribution`, `engineering_default`, or `sensitivity_selected`).

## 9. Duplicate handling

Of the 39 raw CSVs under `data/raw/`, 5 are redundant re-exports of a trip already present under a different filename (1 byte-identical pair, 4 reduced-column re-exports — see `data/manifests/campaign_manifest.csv` and `duplicate_groups.csv` for the full evidence, hashes, and reasoning). **All 39 raw files are kept, untouched, forever** — duplication is handled at the analysis layer, not by deleting raw data:

- `run_qc.py` defaults to processing only the 34 canonical campaigns (`exclude_from_analysis == False` in the manifest).
- Pass `--include-all-files` to process all 39, including the 5 redundant ones, e.g. to reproduce the full historical audit trail.

## 10. Output

`outputs/{permissive,recommended,restrictive}/` are the canonical, deduplicated (34-campaign) runs of the three configs — each is a real, independent pipeline execution, not a projection. Per campaign: standardized parquet, flagged/strict/relaxed CSVs, `{stem}_schema_report.csv` (which raw columns were present for this file's schema variant), `{stem}_segments.csv` (per-segment summary), `config_used.yaml`, `{stem}_metrics.json`, `{stem}_report.md`, and two diagnostic PNGs. `outputs/sensitivity/` holds cross-profile and single-parameter sensitivity summaries (see `scripts/run_sensitivity.py`). `outputs/qc_v2/qc_policy_matrix.csv` and `outputs/qc_v2/campaign_qc_impact.csv` are compiled views of the flag policy and its real per-campaign impact.
