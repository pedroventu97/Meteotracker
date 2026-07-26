# Workspace Cleanup Report — 2026-07-25

Full reorganization of `D:\projects\Meteotracker` from an audit-era working tree (13 overlapping output trees, a backup snapshot, and a nested `src/` package) into the canonical structure below. Full file-level detail is in `workspace_inventory_before.csv` and `workspace_inventory_after.csv` (project root).

## 1. Initial structure (summary)

```
Meteotracker/
├── Meteotracker_QC_Audit_Report.md
├── README.md, requirements.txt, pytest.ini, run_qc.py
├── Transect_MeteoTracker.zip          (original delivery archive, zipped copy of runs/)
├── sensitivity_proper_{permissive,recommended,restrictive}.csv
├── .venv/, __pycache__/, .pytest_cache/
├── backup_pre_audit/                  (24 files: pre-audit code snapshot)
├── meteotracker_qc/
│   ├── __init__.py
│   ├── src/*.py                       (7 modules + __init__.py + __pycache__)
│   ├── config/qc_{config,recommended,permissive,restrictive}.yaml
│   └── tests/                         (empty, undocumented)
├── tests/test_qc.py                   (29 tests, all in one file)
├── runs/                              (39 raw CSVs across 12 date subfolders, 7.7 MiB)
├── outputs/                                        (fossil: 38 dirs, pre hash-suffix fix, 33.6 MiB)
├── outputs_closure_{baseline,permissive,recommended,restrictive}/     (4 × ~137 MiB)
├── outputs_final_closure_{baseline,permissive,recommended,restrictive}/ (4 × ~137 MiB)
├── outputs_run_20260723_171408/, outputs_run_20260723_171935/         (2 × ~127 MiB)
├── outputs_run_final_check/                                            (136 MiB)
└── outputs_run_{permissive,recommended,restrictive}/                   (3 × ~128 MiB)
```

15 output-like directories total, most of them near-duplicate re-runs of the same 34–39 campaigns under different config/naming iterations. See `workspace_inventory_before.csv` for the full 5,134-row, per-file listing (path, type, size, mtime, sha256 for code/config/test/report/raw files, category, proposed action).

**Explicitly identified during the Fase 1 audit** (all confirmed before any deletion):
- **Duplicate code copies:** `meteotracker_qc/src/*.py` (active) vs `backup_pre_audit/meteotracker_qc/src/*.py` (frozen pre-audit snapshot, kept as historical record, now archived).
- **Unimported Python files:** none. All 7 modules under `meteotracker_qc/src/` are imported by `pipeline.py` or exercised directly by tests.
- **Duplicate configuration:** `meteotracker_qc/config/qc_config.yaml` (the original "baseline" config) became behaviorally equivalent to `qc_recommended.yaml` after the report's Section 3b threshold fix — same `physical_limits`/`filtering`/`warmup`; its extra `operational_limits` block and 3 extra keys were confirmed **unused by the code** (verified by reading `meteo_qc.py` and `gps_qc.py`) before retiring it.
- **Old outputs:** all 15 directories listed above except the two freshly-generated `outputs/recommended` and `outputs/sensitivity`.
- **Empty directories:** `meteotracker_qc/tests/` and `backup_pre_audit/meteotracker_qc/tests/` (both stray, undocumented, zero files).
- **Cache:** `.pytest_cache/`, root `__pycache__/`, plus `__pycache__/` under `meteotracker_qc/`, `meteotracker_qc/src/`, `tests/`, and inside `backup_pre_audit/` (8 cache directories total).
- **Complete backup:** `backup_pre_audit/` (24 files — pre-audit code, README, run_qc.py, one test file, one inventory.csv).
- **Reproducible intermediate results:** all 15 output directories — reproducibility was later verified empirically (Section 4 below), not assumed.
- **Files cited in the report but missing:** none at inventory time — `sensitivity_proper_*.csv` had already been created (the report's own Section 5 records that they were missing as of 2026-07-23 and fixed by 2026-07-25).
- **Files present but undocumented:** `Transect_MeteoTracker.zip` (a zipped copy of the original `runs/` delivery, not mentioned in README or the audit report) and the two empty `tests/` directories above.

## 2. Final structure

```
Meteotracker/
├── README.md, requirements.txt, pytest.ini, run_qc.py
├── workspace_inventory_before.csv, workspace_inventory_after.csv
├── config/
│   ├── qc_recommended.yaml
│   ├── qc_permissive.yaml
│   └── qc_restrictive.yaml
├── src/meteotracker_qc/
│   ├── __init__.py, pipeline.py, inventory.py, time_qc.py,
│   │   gps_qc.py, meteo_qc.py, stabilization.py, derived_variables.py
├── tests/
│   ├── test_time_qc.py, test_gps_qc.py, test_meteo_qc.py,
│   │   test_stabilization.py, test_pipeline_integrity.py   (29 tests total)
├── data/
│   ├── raw/            (39 CSVs, 12 original date subfolders preserved, 7.7 MiB)
│   │   └── original_delivery/Transect_MeteoTracker.zip
│   └── manifests/
│       ├── campaign_manifest.csv      (39 rows: 34 canonical + 5 redundant, full hash evidence)
│       ├── duplicate_groups.csv       (5 groups, canonical/redundant pairing)
│       └── raw_file_inventory.csv     (39 rows: n_rows/n_cols/sha256/core_content_hash)
├── outputs/
│   ├── recommended/     (34 canonical campaign dirs, config/qc_recommended.yaml, 306 files)
│   └── sensitivity/
│       ├── sensitivity_proper_permissive.csv
│       ├── sensitivity_proper_recommended.csv
│       ├── sensitivity_proper_restrictive.csv
│       └── sensitivity_comparison.csv (new: per-campaign, 3 profiles merged + deltas)
├── reports/
│   ├── Meteotracker_QC_Audit_Report.md   (moved; evidence sections verbatim, see below)
│   ├── QC_Methodology.md                 (new: short operational method summary)
│   └── Workspace_Cleanup_Report.md       (this file)
└── logs/
    └── latest_qc_run.log
```

`reports/figures/` was **not created**: the audit report embeds no images, and the per-campaign diagnostic PNGs (`diagnostic_plot.png`, `route_map.png`) are QC artifacts that belong with their campaign, not report illustrations — they remain in `outputs/recommended/<campaign>/`. No standalone report-level figure existed to move, and an empty folder was not created just to match the template.

`schema.py`, `aggregation.py`, and `reporting.py` were **not created** under `src/meteotracker_qc/` — no such logic existed in the original code and none was needed for this reorganization.

## 3. Files moved

| From | To |
|---|---|
| `meteotracker_qc/src/*.py` (7 modules) | `src/meteotracker_qc/*.py` |
| `meteotracker_qc/__init__.py` + `meteotracker_qc/src/__init__.py` | merged into `src/meteotracker_qc/__init__.py` |
| `meteotracker_qc/config/qc_{recommended,permissive,restrictive}.yaml` | `config/*.yaml` |
| `runs/**/*.csv` (39 files, 12 subfolders) | `data/raw/**/*.csv` (relative paths preserved) |
| `Transect_MeteoTracker.zip` | `data/raw/original_delivery/Transect_MeteoTracker.zip` |
| `sensitivity_proper_{permissive,recommended,restrictive}.csv` | `outputs/sensitivity/*.csv` (unchanged, reused as-is — see Section 6) |
| `Meteotracker_QC_Audit_Report.md` | `reports/Meteotracker_QC_Audit_Report.md` |

## 4. Files renamed / restructured

- `tests/test_qc.py` (29 tests, 1 file) → split into `tests/test_time_qc.py` (10), `test_gps_qc.py` (8), `test_meteo_qc.py` (3), `test_stabilization.py` (2), `test_pipeline_integrity.py` (6) — same 29 assertions, grouped by which module they exercise; import paths updated from `meteotracker_qc.src.X` to `meteotracker_qc.X`.
- `run_qc.py` — import path updated, added a `sys.path` shim for the new `src/` layout, default `--config` changed from `meteotracker_qc/config/qc_config.yaml` to `config/qc_recommended.yaml`, and added `--manifest` / `--include-all-files` for manifest-driven canonical-campaign filtering (new, see Section 6).
- `pytest.ini` — added `pythonpath = src`; removed the now-obsolete `backup_pre_audit` ignore rules.

## 5. Folders archived (then removed from the active tree)

All 15 archived into `D:\projects\Meteotracker_archive\Meteotracker_pre_cleanup_2026-07-25.zip` (built and integrity-verified — see Section 8 — *before* any deletion):

`outputs/` (fossil), `outputs_closure_{baseline,permissive,recommended,restrictive}/`, `outputs_final_closure_{baseline,permissive,recommended,restrictive}/`, `outputs_run_20260723_171408/`, `outputs_run_20260723_171935/`, `outputs_run_final_check/`, `outputs_run_{permissive,recommended,restrictive}/`, `backup_pre_audit/`.

The archive also contains, at the time it was built: the then-current code/config/tests, both root-level inventories existing at that point, `data/raw` (post-move, already relocated when the archive ran), and `Transect_MeteoTracker.zip`. Excluded from the archive (rebuildable, per the allowed exclusion list): `.venv/`, `__pycache__/` (all copies), `.pytest_cache/`.

## 6. Folders deleted from the active workspace

Same 15 directories as Section 5, plus: the old `meteotracker_qc/` tree (emptied of active content — everything in it had already been moved or was a confirmed-dead config/empty dir), root `__pycache__/`, `.pytest_cache/`, and the `__pycache__/` directories nested under `meteotracker_qc/`, `meteotracker_qc/src/`, `tests/`, and `backup_pre_audit/`. Nothing was deleted that isn't also sitting in the ZIP archive, except pure caches (which are excluded from the archive by design, per Fase 2, since they're trivially rebuildable).

**Mid-cleanup correction (transparency note):** the first attempt at creating `outputs/recommended` and `outputs/sensitivity` landed *inside* the still-present fossil `outputs/` directory (since `outputs/` already existed, `mkdir -p outputs/recommended` nested into it rather than replacing it). This was caught before any deletion, by inspecting `outputs/`'s contents. The new subfolders were moved out, the fossil `outputs/` (already safely captured in the ZIP, built before this happened) was removed, and `outputs/` was rebuilt clean with only `recommended/` and `sensitivity/`. No data was lost; this is recorded here for transparency, not because it affected the final result.

**Raw data, manifests, reports, configuration, tests, active code, canonical `outputs/recommended`, and the sensitivity summaries were never deleted.** The external ZIP archive was also never deleted.

## 7. Duplicate raw-file handling

5 of the 39 raw CSVs are redundant re-exports of a trip already present under a different filename — independently re-verified in this cleanup by hashing (`file_sha256` for exact-byte matches, plus a `core_content_hash` over just `Time`/`Lat`/`Lon`/`Temp[°C]` to catch reduced-column re-exports that don't hash-match on the full file). The recomputed redundant-file set matched the audit report's Section 1 findings **exactly**, with no manual reconciliation needed:

| Group | Type | Canonical (kept) | Redundant (kept as raw, excluded from analysis) |
|---|---|---|---|
| dupgrp_01 | byte-identical | `03-04/20260304T08_41_51_..._(1).csv` | `02-28/20260304T08_41_51_..._(1).csv` |
| dupgrp_02 | reduced-column re-export | `04-27/20260427T08_00_36_..._(1).csv` (43 col) | `04-27 moto/20260427T08_00_36_....csv` (5 col) |
| dupgrp_03 | reduced-column re-export | `04-27/20260427T08_38_02_private_....csv` (43 col) | `04-27 moto/20260427T08_38_02_private_..._UNKNOWN-UNKNOWN.csv` (5 col) |
| dupgrp_04 | reduced-column re-export | `05-19/20260519T08_17_35_..._(1).csv` (43 col) | `05-19/20260519T08_17_35_....csv` (5 col) |
| dupgrp_05 | reduced-column re-export | `07-04 2025 moto/..._(2).csv` (42 col) | `07-04 2025 moto/..._(3).csv` (5 col) |

All 39 files remain in `data/raw/` with `keep_raw = True`. `run_qc.py` now defaults to the 34 canonical campaigns; `--include-all-files` reproduces the full 39-campaign historical run.

## 8. Backup archive verification

`D:\projects\Meteotracker_archive\Meteotracker_pre_cleanup_2026-07-25.zip` — built with `zipfile`/`ZIP_DEFLATED`, verified before any deletion:
- `ZipFile.testzip()` → no corrupt entries (`None`)
- 4,506 entries, matching the pre-cleanup file count
- Spot-checked a raw CSV read back from inside the archive against the live file: byte-identical
- Confirmed presence of the audit report, `backup_pre_audit/run_qc.py`, all 352 files of `outputs_final_closure_recommended/`, the sensitivity CSVs, and `workspace_inventory_before.csv`

## 9. Size

| | Size (excl. `.venv`) | Files (excl. dirs) |
|---|---:|---:|
| Before | 1,911.9 MiB | 4,506 |
| After | 132.5 MiB | 379 |
| **Freed from the active workspace** | **≈ 1,779.4 MiB (−93%)** | |
| Safety archive (compressed, external) | 277.7 MiB | 4,506 |

`.venv/` (Python environment, ~unchanged, excluded from all of the above) was left untouched throughout.

## 10. Final tests

```
python -m pytest -vv -W error
```
**29 passed, 0 warnings, 0 failed** — run twice: once immediately after the code move (import-path sanity check) and once as the formal Fase 10 closure run. Both identical.

## 11. Pipeline result

`python run_qc.py --input data/raw --output outputs/recommended --config config/qc_recommended.yaml` → **exit code 0.**

Re-run from scratch into a temporary directory after the cleanup (input untouched, output isolated, deleted afterward) and checked against both the manifest and the committed `outputs/recommended`:

| Check | Result |
|---|---|
| Exactly 34 canonical campaign directories produced | PASS |
| Campaign-id set matches the manifest's 34 canonical entries exactly | PASS |
| None of the 5 excluded files' campaign-ids appear as output dirs | PASS |
| No two canonical source files map to the same output directory (no collisions) | PASS |
| No missing artifacts (9 expected files × 34 campaigns) | PASS |
| No zero-byte artifacts | PASS |
| Row integrity (raw=standardized=flagged rows, `source_row` unique = `range(n)`, strict⊆relaxed) for all 34 | PASS |
| Timezone gating (0 unsafe-timezone rows marked satellite-usable) | PASS |
| Aggregate total rows = 48,173 | PASS — matches the audited "34 physically distinct campaigns" figure exactly |
| Aggregate satellite-usable rows = 44,371 (92.11%) | PASS — matches the audited figure exactly |
| Temp-directory run reproduces the committed `outputs/recommended` metrics exactly, per campaign | PASS |

15/15 checks passed. Temporary directory deleted after verification.

`sensitivity_comparison.csv`'s recomputed aggregate totals (both the 39-nominal and 34-canonical breakdowns, for all three profiles) were cross-checked against the report's Section 5 (2026-07-25) tables and **matched exactly** to the reported row counts and percentages.

## 12. Open items / judgment calls

- **`Transect_MeteoTracker.zip`** was not mentioned in the original README or audit report. It is a zipped copy of the original `runs/` delivery (same 39 files). Kept, relocated to `data/raw/original_delivery/` as provenance rather than deleted, since it's part of what was originally received even though its content is redundant with `data/raw/`.
- **`meteotracker_qc/config/qc_config.yaml`** ("baseline" config) was retired rather than carried into `config/`. It is behaviorally identical to `qc_recommended.yaml` post-fix (verified against the source, not assumed) and the target structure only calls for 3 profiles. It is preserved in the ZIP archive for anyone who wants to inspect the pre-fix history.
- **`reports/figures/`** was intentionally not created — see Section 2.
- Per-campaign diagnostic PNGs are not byte-reproducible run-to-run (matplotlib/font-rendering nondeterminism is normal); reproducibility was verified at the data level (row counts, flags, metrics — see Section 11), not by pixel-hashing the PNGs. This is expected and does not affect any scientific figure.
- No test failures, no missing files, no open data-integrity issues remain.

## 13. Final tree (depth-limited)

```
Meteotracker/
├── README.md
├── requirements.txt
├── pytest.ini
├── run_qc.py
├── workspace_inventory_before.csv
├── workspace_inventory_after.csv
├── config/
│   ├── qc_recommended.yaml
│   ├── qc_permissive.yaml
│   └── qc_restrictive.yaml
├── src/
│   └── meteotracker_qc/
│       ├── __init__.py
│       ├── pipeline.py
│       ├── inventory.py
│       ├── time_qc.py
│       ├── gps_qc.py
│       ├── meteo_qc.py
│       ├── stabilization.py
│       └── derived_variables.py
├── tests/
│   ├── test_time_qc.py
│   ├── test_gps_qc.py
│   ├── test_meteo_qc.py
│   ├── test_stabilization.py
│   └── test_pipeline_integrity.py
├── data/
│   ├── raw/
│   │   ├── 02-13/  (2 csv)            ├── 05-19/  (2 csv)
│   │   ├── 02-20/  (2 csv)            ├── 05-27/  (5 csv)
│   │   ├── 02-21/  (2 csv)            ├── 06-04/  (4 csv)
│   │   ├── 02-28/  (4 csv)            ├── 06-20/  (5 csv)
│   │   ├── 03-04/  (3 csv)            ├── "07-04 2025 moto"/  (5 csv)
│   │   ├── 04-27/  (3 csv)            └── original_delivery/Transect_MeteoTracker.zip
│   │   └── "04-27 moto"/  (2 csv)         (39 raw CSVs total, 12 subfolders)
│   └── manifests/
│       ├── campaign_manifest.csv      (39 rows)
│       ├── duplicate_groups.csv       (5 rows)
│       └── raw_file_inventory.csv     (39 rows)
├── outputs/
│   ├── recommended/                   (34 campaign dirs x 9 files = 306 files, + inventory.csv)
│   │   ├── 02-13__..._353b44f890/
│   │   │   ├── ..._flagged.csv, ..._strict.csv, ..._relaxed.csv
│   │   │   ├── ..._standardized.parquet, ..._metrics.json, ..._report.md
│   │   │   └── config_used.yaml, diagnostic_plot.png, route_map.png
│   │   ├── 02-13__..._c098f040ec/  (same 9-file shape)
│   │   └── ... (32 more campaign directories, same 9-file shape each)
│   └── sensitivity/
│       ├── sensitivity_proper_permissive.csv
│       ├── sensitivity_proper_recommended.csv
│       ├── sensitivity_proper_restrictive.csv
│       └── sensitivity_comparison.csv
├── reports/
│   ├── Meteotracker_QC_Audit_Report.md
│   ├── QC_Methodology.md
│   └── Workspace_Cleanup_Report.md
└── logs/
    └── latest_qc_run.log
```

(`.venv/` omitted — Python virtual environment, untouched by this cleanup.)
