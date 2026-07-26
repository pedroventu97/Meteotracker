# QC methodology (operational summary)

This document describes the current QC method in plain terms. For the full audit trail, findings, and verification evidence, see [Meteotracker_QC_Audit_Report.md](Meteotracker_QC_Audit_Report.md). This page is intentionally short and does not repeat that evidence.

## 1. Raw preservation

Every raw CSV under `data/raw/` is read but never modified in place. Each output row carries `source_file` (the raw filename) and `source_row` (its 0-based row index in that file) so any QC-flagged or derived value can be traced back to the exact original observation. Raw files are never deleted by the pipeline, regardless of whether they are used in an analysis run — see "Duplicate handling" below.

## 2. Temporal standardization

`time_qc.py` parses the `Time` column explicitly (`format="mixed"`, no silent format inference), classifies each file's timezone handling (`explicit_offset`, `ambiguous`, or `invalid`), and derives `time_utc`, `time_local` (Europe/Rome), `dt_s` (row-to-row delta), and segment boundaries (`qc_new_segment`/`segment_id`) from a gap threshold. Out-of-order and duplicate timestamps are flagged (`qc_time_order`, `qc_time_duplicate`) without dropping rows.

## 3. GPS QC

`gps_qc.py` computes step distance/speed/acceleration from consecutive valid fixes (geodesic distance via `pyproj`), and flags GPS jumps (`qc_gps_jump`), impossible acceleration (`qc_impossible_acceleration`), and speed disagreement against the reported speed column. Repeated coordinates are tracked separately from confirmed freeze: a freeze (`qc_gps_freeze`) requires both repeated coordinates *and* near-zero GPS-derived and reported speed; repeated coordinates alone are only `qc_possible_gps_freeze`.

## 4. Meteorological QC

`meteo_qc.py` flags physically impossible temperature/humidity/pressure values against configurable limits, and detects isolated temperature spikes via a rolling median/MAD test (persistent trends are not flagged as spikes).

## 5. Sensor stabilization

`stabilization.py` flags the sensor warm-up period at the start of a transect using a rolling-median slope test against a configurable threshold and minimum stabilization window.

## 6. Derived variables

`derived_variables.py` recomputes dew point (Magnus approximation) and potential temperature from temperature/humidity/pressure, and reports the difference against the device's own reported values (`dewpoint_difference_c`, `theta_difference_k`) as an independent cross-check.

## 7. Strict / relaxed classification

Each row gets `qc_severity` (count of `qc_time_gap`, `qc_gps_jump`, `qc_temp_spike`, `qc_sensor_stabilization`). `keep_strict` and `keep_relaxed` are boolean columns from two configurable severity budgets (`filtering.strict_keep_threshold` / `relaxed_keep_threshold`), never a destructive filter — both `_strict.csv` and `_relaxed.csv` are written alongside the full `_flagged.csv`. `use_for_satellite_comparison` additionally requires GPS validity, no sensor-stabilization flag, and a timezone-safe classification.

Three configuration profiles tune the GPS/warm-up thresholds (segment boundaries use a fixed 2.0 s gap and do not vary by profile):

| Profile | GPS jump distance/dt | Warm-up slope / min stable |
|---|---|---|
| `config/qc_permissive.yaml` | 120 m / 3.0 s | 0.03 °C/s / 30 s |
| `config/qc_recommended.yaml` | 80 m / 2.0 s | 0.02 °C/s / 60 s |
| `config/qc_restrictive.yaml` | 60 m / 1.0 s | 0.01 °C/s / 120 s |

## 8. Duplicate handling

Of the 39 raw CSVs under `data/raw/`, 5 are redundant re-exports of a trip already present under a different filename (1 byte-identical pair, 4 reduced-column re-exports — see `data/manifests/campaign_manifest.csv` and `duplicate_groups.csv` for the full evidence, hashes, and reasoning). **All 39 raw files are kept, untouched, forever** — duplication is handled at the analysis layer, not by deleting raw data:

- `run_qc.py` defaults to processing only the 34 canonical campaigns (`exclude_from_analysis == False` in the manifest).
- Pass `--include-all-files` to process all 39, including the 5 redundant ones, e.g. to reproduce the full historical audit trail.

## 9. Recommended output

`outputs/recommended/` is the canonical, deduplicated (34-campaign) run of `config/qc_recommended.yaml`. `outputs/sensitivity/` holds per-campaign summaries (not full output trees) for all three profiles plus a merged `sensitivity_comparison.csv`, so permissive/recommended/restrictive can be compared without keeping four full copies of every artifact on disk.
