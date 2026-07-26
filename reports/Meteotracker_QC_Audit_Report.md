# Meteotracker QC audit report

> **Note added 2026-07-25 (workspace cleanup).** This report was moved from the project root to `reports/Meteotracker_QC_Audit_Report.md` as part of a workspace reorganization. Every evidentiary section below — including "Final Closure Checks" and "Final Closure Checks (independent re-verification, 2026-07-25)" — is preserved **verbatim** and still refers to paths exactly as they existed at audit time (`meteotracker_qc/src/...`, `outputs_final_closure_*`, `outputs/`, `backup_pre_audit/`, `tests/test_qc.py`, etc.). None of those directories were deleted outright: they were archived to `Meteotracker_archive/Meteotracker_pre_cleanup_2026-07-25.zip` before removal from the active workspace. For the full old-path → new-path mapping, see [Workspace_Cleanup_Report.md](Workspace_Cleanup_Report.md). Only the "Files reviewed and updated" list just below (a live pointer section, not audit evidence) has been updated to the current paths; the rest of this document is untouched.

## Executive summary

The QC pipeline was audited end to end and the main technical risk was confirmed and corrected: time-based diagnostics and GPS-based diagnostics must remain attached to the same original row throughout the workflow. A separate sorting or processing of timestamps and coordinates would create silent misalignment, which is especially harmful for route reconstruction, spatial aggregation, and any downstream time–space analysis.

The current implementation now preserves row provenance through `source_row` and `source_file`, and the diagnostics are derived from the same DataFrame row rather than from independently sorted vectors. This change was verified on the real dataset and through a regression suite.

## Verified evidence

### 1. Regression suite

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_qc.py
```

Result:
- 29 passed
- 0 warnings
- 0 failures

### 2. Full batch run on the real dataset

Command:

```powershell
.\.venv\Scripts\python.exe run_qc.py --input runs --output outputs_closure_baseline --config meteotracker_qc/config/qc_config.yaml
```

Result:
- Exit code: 0
- The run completed successfully and generated outputs under the timestamped output folder.

### 3. Batch-level inventory summary

The generated inventory reported 39 input CSVs and the batch produced the expected per-campaign artifacts. The aggregate output metrics showed:
- Total rows across processed campaigns: 55,092
- Strict-keep rows: 51,330
- Relaxed-keep rows: 51,330

The generated standardized outputs included the expected provenance fields and had no missing parquet artifacts in the inspected campaign directories.

### 4. Sensitivity analysis

The same batch was executed with three threshold profiles:
- permissive
- recommended
- restrictive

Aggregate keep counts were:
- permissive: 55,092 total rows, 50,671 satellite-eligible rows
- recommended: 55,092 total rows, 50,621 satellite-eligible rows
- restrictive: 55,092 total rows, 50,603 satellite-eligible rows

This shows the pipeline is stable and that the profile choice changes the filtering behavior in a predictable way without breaking the run.

## What was fixed

### Time QC

The temporal logic now derives row-level features directly from the same source frame:
- `dt_s` is calculated row-wise from parsed UTC timestamps.
- `qc_time_gap`, `qc_time_duplicate`, `qc_time_order`, and `qc_new_segment` are computed from the same row sequence.
- Timestamp parsing and timezone handling are explicit and do not silently assume that naive timestamps are local.

### GPS QC

The GPS logic was revised so that repeated coordinates are no longer over-interpreted as confirmed freeze events.
- Repeated coordinates are tracked separately.
- Confirmed freeze is treated as a stronger condition than repeated coordinates alone.
- GPS jumps are detected using stepwise distance and time information.

### Provenance and pipeline integrity

The pipeline now preserves the original row identity from ingestion through all QC stages:
- `source_file`
- `source_row`

This prevents time–coordinate desynchronization from creeping into later stages.

## Scientific interpretation

The most important invariant for this workflow is that each observation must keep its own time, coordinate, meteorological, and QC attributes together. The original failure mode was not merely a coding typo, but a data-modeling risk. Once rows are preserved and all flags are computed from the same row sequence, the outputs are much more trustworthy for route analysis, spatial statistics, and QC-based filtering.

## Files reviewed and updated

Current locations (post 2026-07-25 cleanup; see note at the top of this document):

- [src/meteotracker_qc/time_qc.py](../src/meteotracker_qc/time_qc.py)
- [src/meteotracker_qc/gps_qc.py](../src/meteotracker_qc/gps_qc.py)
- [src/meteotracker_qc/pipeline.py](../src/meteotracker_qc/pipeline.py)
- [tests/test_time_qc.py](../tests/test_time_qc.py), [tests/test_gps_qc.py](../tests/test_gps_qc.py), [tests/test_meteo_qc.py](../tests/test_meteo_qc.py), [tests/test_stabilization.py](../tests/test_stabilization.py), [tests/test_pipeline_integrity.py](../tests/test_pipeline_integrity.py) (formerly one `tests/test_qc.py`, split by module during cleanup; same 29 tests, unchanged assertions)
- `meteotracker_qc/config/qc_config.yaml` — retired during cleanup. After the Section 3b threshold fix it was behaviorally equivalent to [config/qc_recommended.yaml](../config/qc_recommended.yaml) (identical `physical_limits`, `filtering`, and `warmup`; its extra `operational_limits` block and `gps.min_speed_kmh`/`gps.freeze_repeat_seconds`/`filtering.missing_fraction_warning` keys were confirmed unused by the current code before retiring the file). Preserved in the pre-cleanup archive.
- [pytest.ini](../pytest.ini)

A backup of the pre-audit state was preserved in `backup_pre_audit/` at audit time. As of the 2026-07-25 cleanup it is archived (not deleted) in `Meteotracker_archive/Meteotracker_pre_cleanup_2026-07-25.zip`.

## Bottom line

The pipeline is now technically sounder, the regression suite is passing, and the real batch run completed successfully. The audit confirms that the row-preservation fix is working and that the QC workflow can be used on the provided Meteotracker runs with a verified, reproducible execution path.

## Final Closure Checks

> **This section supersedes the "Final Closure Checks" originally written above.** That version declared `READY FOR SCIENTIFIC ANALYSIS` without demonstrating it end to end. A closure re-audit was run against fresh, from-scratch pipeline executions (`outputs_final_closure_{baseline,permissive,recommended,restrictive}`, generated 2026-07-23) plus exhaustive pairwise checks on the 39 raw input CSVs. Two real, previously undetected issues were found and are documented below along with a corrected verdict.

### 1. Input-to-output bijection

**Directory-level collision (39 CSV / 38 directories): confirmed root cause, confirmed fixed.**
`_campaign_output_dir()` in [meteotracker_qc/src/pipeline.py](meteotracker_qc/src/pipeline.py) derives the output folder name from the *relative* input path (parent folder + filename) plus a 10-hex-digit SHA1 suffix, not from the filename stem alone. The one real collision under the old stem-only naming was:

- `runs/02-28/20260304T08_41_51_..._Bologna-Bologna (1).csv`
- `runs/03-04/20260304T08_41_51_..._Bologna-Bologna (1).csv`

— identical stems, so the old naming scheme mapped both to one directory (38 = 39 − 1), silently overwriting whichever file `rglob` visited second. Under the current naming, the two get distinct hashed directories. Verified on the fresh rerun: 39 input CSVs → 39 distinct `campaign_id` values → 39 distinct output directories, 0 collisions, 0 overwrites, 39/39 `source_file` values represented in the outputs. Regression test: `test_campaign_output_dir_is_unique_for_same_stem_in_different_folders`.

**New finding — this is not a directory-naming bug, it is a raw-data duplication problem.** The two files above are not just same-named, they are **byte-identical** (`md5 4462fb9274f12b5d953c4986942fc5ca`, 313,030 bytes, 2,101 rows each). Fixing the directory collision did not fix this — it converted a silent *overwrite* into a silent *duplication*: both copies are now processed as separate "campaigns" and both are counted in every downstream total.

Going further than the checklist asked for, every one of the 741 possible pairs among the 39 CSVs was compared on row count and on `Time`/`Lat`/`Lon` values (not just filename or full-file hash, since a full-file hash misses cases where the same trip was exported with a different column subset). This surfaced **4 additional duplicate pairs** that a filename or md5 check alone would miss, because in each case one copy is a reduced 5-column export (`Time, Lat, Lon, Alt[m], Temp[°C]`) of the same trip that also exists as a fuller 42/43-column export elsewhere:

| # | File A (kept candidate) | File B (redundant copy) | Rows | Evidence |
|---|---|---|---|---|
| 1 | `03-04/20260304T08_41_51_..._Bologna-Bologna (1).csv` | `02-28/20260304T08_41_51_..._Bologna-Bologna (1).csv` | 2101 | byte-identical, md5 match |
| 2 | `04-27/20260427T08_00_36_..._Bologna-Bologna (1).csv` (43 col) | `04-27 moto/20260427T08_00_36_..._Bologna-Bologna.csv` (5 col) | 1142 | Time/Lat/Lon/Temp identical row-by-row |
| 3 | `04-27/20260427T08_38_02_private_..._Bologna-Bologna.csv` (43 col) | `04-27 moto/20260427T08_38_02_private_..._UNKNOWN-UNKNOWN.csv` (5 col) | 772 | Time/Lat/Lon/Temp identical row-by-row |
| 4 | `05-19/20260519T08_17_35_..._Bologna-Bologna (1).csv` (43 col) | `05-19/20260519T08_17_35_..._Bologna-Bologna.csv` (5 col, same folder) | 1849 | Time/Lat/Lon/Temp identical row-by-row |
| 5 | `07-04 2025 moto/..._Bologna-Bologna (2).csv` (42 col) | `07-04 2025 moto/..._Bologna-Bologna (3).csv` (5 col, same folder) | 1055 | Time/Lat/Lon/Temp identical row-by-row |

Net effect: **of the 39 nominal input files, only 34 represent physically distinct transects.** 5 files are redundant re-exports of a trip already present elsewhere. This was not caught by the original closure check because that check only verified filename/directory uniqueness, not measurement-content uniqueness.

Full per-file table (fresh `outputs_final_closure_baseline` run):

| source_file | campaign_id | raw_rows | flagged_rows | status | note |
|---|---|---|---|---|---|
| 02-13/20260213T09_06_57_..._Bologna-Bologna.csv | 02-13__...__353b44f890 | 2167 | 2167 | OK | |
| 02-13/20260213T13_23_47_..._Bologna-Bologna.csv | 02-13__...__c098f040ec | 2829 | 2829 | OK | |
| 02-20/20260220T09_05_04_..._Bologna-Bologna.csv | 02-20__...__c2b73a152d | 536 | 536 | OK | |
| 02-20/20260220T12_54_36_..._Bologna-Bologna (1).csv | 02-20__..._(1)__d8c7858580 | 2437 | 2437 | OK | |
| 02-21/20260221T09_17_23_..._Bologna-Bologna.csv | 02-21__...__a2bd5f18d1 | 2310 | 2310 | OK | |
| 02-21/20260221T12_52_42_..._Bologna-Bologna.csv | 02-21__...__cf996bfb18 | 2452 | 2452 | OK | |
| 02-28/20260228T09_08_22_..._Bologna-Bologna.csv | 02-28__...__fb99845f64 | 1084 | 1084 | OK | |
| 02-28/20260228T14_01_31_..._Bologna-Bologna.csv | 02-28__...__fd7d5426a2 | 1907 | 1907 | OK | |
| 02-28/20260228T19_09_37_..._Bologna-Bologna.csv | 02-28__...__75c3c3918e | 468 | 468 | OK | |
| **02-28/20260304T08_41_51_..._Bologna-Bologna (1).csv** | 02-28__..._(1)__928fb5381e | 2101 | 2101 | **DUPLICATE (redundant)** | byte-identical to the 03-04 copy |
| 03-04/20260304T08_41_51_..._Bologna-Bologna (1).csv | 03-04__..._(1)__4d0e0fdcdc | 2101 | 2101 | OK (kept copy) | |
| 03-04/20260304T13_53_03_..._Bologna-Bologna (1).csv | 03-04__..._(1)__93e6367072 | 1993 | 1993 | OK | |
| 03-04/20260304T21_12_40_..._Bologna-Bologna (1).csv | 03-04__..._(1)__de6e341cef | 1424 | 1424 | OK | |
| 04-27/20260427T07_28_18_..._Bologna-Bologna.csv | 04-27__...__a768d6fc15 | 21 | 21 | OK | |
| 04-27/20260427T08_00_36_..._Bologna-Bologna (1).csv | 04-27__..._(1)__1cbe131095 | 1142 | 1142 | OK (kept copy, fuller export) | |
| 04-27/20260427T08_38_02_private_..._Bologna-Bologna.csv | 04-27__...__71d77a7bf2 | 772 | 772 | OK (kept copy, fuller export) | |
| **04-27 moto/20260427T08_00_36_..._Bologna-Bologna.csv** | 04-27_moto__...__4eb8225b1f | 1142 | 1142 | **DUPLICATE (redundant)** | same trip as 04-27/…08_00_36…(1), 5-col export |
| **04-27 moto/20260427T08_38_02_private_..._UNKNOWN-UNKNOWN.csv** | 04-27_moto__...__14572d7868 | 772 | 772 | **DUPLICATE (redundant)** | same trip as 04-27/…08_38_02…, 5-col export |
| 05-19/20260519T08_17_35_..._Bologna-Bologna (1).csv | 05-19__..._(1)__4a76f14cb8 | 1849 | 1849 | OK (kept copy, fuller export) | |
| **05-19/20260519T08_17_35_..._Bologna-Bologna.csv** | 05-19__...__011248cb28 | 1849 | 1849 | **DUPLICATE (redundant)** | same trip as the "(1)" file in the same folder, 5-col export |
| 05-27/20260527T08_09_11_..._Bologna-Sasso Marconi.csv | 05-27__...__cf22ca7363 | 1161 | 1161 | OK | |
| 05-27/20260527T08_50_27_..._Sasso Marconi-Bologna.csv | 05-27__...__70501cac2d | 1133 | 1133 | OK | |
| 05-27/20260527T12_58_39_..._Bologna-Bologna.csv | 05-27__...__d3116f69d4 | 234 | 234 | OK | |
| 05-27/20260527T13_08_42_..._Bologna-Bologna.csv | 05-27__...__99cbc5b816 | 2053 | 2053 | OK | |
| 05-27/20260527T18_39_53_..._Bologna-Bologna.csv | 05-27__...__02ca0ca22a | 942 | 942 | OK | |
| 06-04/20260604T08_17_52_..._Bologna-Carpi.csv | 06-04__...__003a500552 | 2418 | 2418 | OK | |
| 06-04/20260604T10_49_10_..._Carpi-Bologna.csv | 06-04__...__9a1ec501bf | 2245 | 2245 | OK | |
| 06-04/20260604T11_40_32_..._Bologna-Ravenna.csv | 06-04__...__5bd4095200 | 631 | 631 | OK | |
| 06-04/20260604T14_34_10_..._Ravenna-Imola.csv | 06-04__...__d0602de380 | 1002 | 1002 | OK | |
| 06-20/20260620T07_44_41_..._Bologna-Sasso Marconi.csv | 06-20__...__0545f6d7aa | 1146 | 1146 | OK | |
| 06-20/20260620T08_29_06_..._Bologna-Bologna.csv | 06-20__...__ac09a3459a | 1415 | 1415 | OK | |
| 06-20/20260620T12_48_24_..._Bologna-Bologna.csv | 06-20__...__64bad4dfc4 | 2834 | 2834 | OK | |
| 06-20/20260620T17_20_43_..._Bologna-Bologna.csv | 06-20__...__ec56e23b3a | 1160 | 1160 | OK | |
| 06-20/20260620T20_53_29_..._Bologna-Bologna.csv | 06-20__...__cbd2f455f2 | 1231 | 1231 | OK | |
| 07-04 2025 moto/..._Bologna-Bologna (2).csv | 07-04_2025_moto__..._(2)__0d9a293803 | 1055 | 1055 | OK (kept copy, fuller export) | |
| **07-04 2025 moto/..._Bologna-Bologna (3).csv** | 07-04_2025_moto__..._(3)__103527c9de | 1055 | 1055 | **DUPLICATE (redundant)** | same trip as the "(2)" file in the same folder, 5-col export |
| 07-04 2025 moto/20250704T09_31_26_..._Bologna-Bologna.csv | 07-04_2025_moto__...__e9e4deafbf | 91 | 91 | OK | |
| 07-04 2025 moto/20250704T10_15_51_..._Bologna-Bologna.csv | 07-04_2025_moto__...__5f01006ac6 | 933 | 933 | OK | |
| 07-04 2025 moto/20250704T14_37_10_..._Bologna-Bologna.csv | 07-04_2025_moto__...__5e89a632f1 | 997 | 997 | OK | |

Answering the checklist directly:
- Two files with the same `campaign_id`? No — 39 distinct `campaign_id` values, 0 collisions, after the hash-suffix fix.
- A directory overwritten? No, not in the current code. It *would* have happened under the pre-fix naming (see above) — that is the historical bug, now closed.
- Two CSVs intentionally merged? No merging happens anywhere in the pipeline; each CSV produces exactly one campaign directory.
- A CSV producing no artefacts? No — 39/39 produced complete artefact sets (see Section 4).
- Different file names normalizing to the same directory name? No — checked exhaustively, 39/39 unique.
- All 39 files represented via `source_file`? Yes, 39/39 — but 5 of those 39 `source_file` values are redundant re-exports of a trip already represented under a different `source_file`, so **only 34 are informationally distinct.**

**Action recommended, not yet taken:** deleting/archiving raw files under `runs/` is a destructive, irreversible edit to your original dataset, so it has not been done automatically. Recommended keep/drop pairs are in the table above (bold rows are the redundant copies). Once you confirm, dropping those 5 files and rerunning `run_qc.py` would make the nominal file count and the physically-distinct campaign count equal (34 = 34).

### 2. Warning analysis

Warning text (as it appeared before the fix, reproduced verbatim from the original audit):

```text
Could not infer format, so each element will be parsed individually, falling back to `dateutil`. To ensure parsing is consistent and as-expected, please specify a format.
```

- **File/line:** [meteotracker_qc/src/time_qc.py:9](meteotracker_qc/src/time_qc.py) — `_parse_timestamp_series()`, the shared helper used by `normalize_timestamp_series()`, `classify_timezone()`, and `detect_time_issues()`.
- **Test context:** `test_non_interpretable_timestamp_is_flagged` (mixed valid/invalid timestamp strings in one series triggered pandas' format-inference path).
- **Cause:** `pd.to_datetime(..., errors="coerce", utc=True)` without an explicit `format=` argument makes pandas try to auto-detect a format per element when the series isn't uniformly parseable, which is what emits the `UserWarning`.
- **Effect on results:** none on parsed values in the case tested — but it is exactly the kind of implicit, unverified assumption this audit exists to catch, and it failed the `-W error` bar.
- **Decision: corrected**, not just accepted. The fix passes `format="mixed"` explicitly to every `pd.to_datetime()` call in this module (line 9), which tells pandas to parse each element independently without emitting the inference warning.

**Verification performed for this closure (not just re-stated):**
1. `./.venv/Scripts/python.exe -m pytest -vv -W error` → **29 passed, 0 warnings, 0 failures.**
2. Beyond the test suite: the full 39-file production batch was also re-run through `run_qc.run_qc()` directly under `warnings.simplefilter("error")` (i.e. *any* warning anywhere in the real batch path — including matplotlib figure rendering, parquet/CSV writers, and yaml serialization — would raise). Result: **completed with no warnings raised.** This confirms the fix holds outside the synthetic test fixtures too, on the actual dataset.

### 3. Row integrity

Per-file PASS/FAIL (fresh `outputs_final_closure_baseline` run; checks: `raw_rows == standardized_rows == flagged_rows`; `source_row` present and unique within the file; the set of `source_row` values equals `range(raw_rows)`; `keep_strict ⊆ keep_relaxed ⊆ flagged`):

All **39/39 files: PASS** on every one of those six checks. (Full per-file table available; every row reads `PASS` — omitted here for length since there is no FAIL to show, in contrast with Section 1's table which does need the full listing to show *where* the duplicate problem lives.)

**Global `source_file + source_row` uniqueness across the complete assembled dataset: FAIL.**
This is the check that formally exposes the Section 1 finding. Across all 39 campaign outputs there are 52,991 `(source_file, source_row)` pairs; **2,101 of them are duplicated** — every single row of `20260304T08_41_51_..._Bologna-Bologna (1).csv` appears twice, once under the `02-28` campaign directory and once under `03-04`, because `source_file` is only the basename (`input_path.name` in [pipeline.py:75](meteotracker_qc/src/pipeline.py)), and this basename is not unique across folders. Note this key-level check only *directly* catches duplicate pair #1 from Section 1 (the byte-identical one, which also shares a filename): the other 4 duplicate pairs have different `source_file` names, so they pass this literal-key check while still double-counting the same physical measurements in every aggregate statistic. In other words: **passing `source_file + source_row` uniqueness is necessary but not sufficient for "no duplicated observations."**

Aggregate counts, fresh baseline run (`outputs_final_closure_baseline`, all 4 sensitivity configs use the same input set):
- Total rows, 39 nominal campaigns (includes the byte-identical duplicate counted twice): **55,092**
- Total rows, 34 physically distinct campaigns (5 redundant files excluded): **48,173** (deduplication removes 6,919 rows across the 5 redundant files, 2,101 of which come from the byte-identical pair and the remainder from the 4 reduced-column re-exports)
- Timezone classes: `explicit_offset` 39/39, `ambiguous` 0, `invalid` 0

### 3b. Default-config threshold bug found and fixed (not in the original scope, found during this closure)

While reproducing the strict/relaxed keep counts, `meteotracker_qc/config/qc_config.yaml`'s `filtering` section had `strict_keep_threshold: 0.9` and `relaxed_keep_threshold: 0.7`. [pipeline.py](meteotracker_qc/src/pipeline.py) casts both with `int(...)` before comparing against the integer-valued `qc_severity` (a 0–4 flag count) — `int(0.9)` and `int(0.7)` both truncate to `0`, so **`keep_strict` and `keep_relaxed` were silently identical** for any run using the default config (this is why the original closure report showed both at 51,330 rows — that equality was the bug, not evidence of a stable pipeline). This predates the audit; it is present unchanged in `backup_pre_audit/meteotracker_qc/config/qc_config.yaml` too, so it was not introduced by the earlier fix pass and was never caught.

**Fixed:** `qc_config.yaml` filtering thresholds changed to integers (`strict_keep_threshold: 0`, `relaxed_keep_threshold: 1`), matching `qc_recommended.yaml`, with a comment explaining why they must stay integers. Verified: after the fix, baseline and `qc_recommended.yaml` now produce identical `keep_strict`/`keep_relaxed` counts (53,430 / 55,085 of 55,092, as expected since they now share both filtering thresholds and physical/GPS/warmup parameters), and `keep_strict` (53,430) is now meaningfully smaller than `keep_relaxed` (55,085) as the two-tier design intends.

### 4. Output completeness

Checked for all 39×4 = 156 (campaign × config) combinations across `outputs_final_closure_{baseline,permissive,recommended,restrictive}`: standardized parquet, flagged CSV, strict CSV, relaxed CSV, report markdown, metrics JSON, diagnostic plot PNG, route map PNG, `config_used.yaml` — checked for existence *and* non-zero file size (an empty file would otherwise pass an existence-only check).

**Result: 156/156 complete. 0 missing or empty artefacts.** No campaign directory was empty or partial in any of the 4 fresh runs.

### 5. Sensitivity analysis

Real per-campaign figures were computed on each profile's own `keep_relaxed`-filtered subset (not on the unfiltered standardized frame, which would trivially show 0 change across profiles since GPS/warmup/temperature values themselves don't change — only which rows get flagged does).

**Totals across all 39 nominal campaigns:**

| Configuration | rows kept (relaxed) | % kept | rows kept (strict) | % strict | satellite-usable | % satellite | segments (sum) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Permissive | 55,086 | 100.0% | 53,480 | 97.1% | 50,671 | 92.0% | 486 |
| Recommended | 55,085 | 100.0% | 53,430 | 97.0% | 50,621 | 91.9% | 486 |
| Restrictive | 53,412 | 97.0% | 53,412 | 97.0% | 50,603 | 91.9% | 486 |

**Same totals, deduplicated to the 34 physically distinct campaigns** (excludes the 5 redundant files from Section 1 — this is the number that should be used for anything scientific):

| Configuration | total rows | rows kept (relaxed) | % kept | satellite-usable | % satellite |
|---|---:|---:|---:|---:|---:|
| Permissive | 48,173 | 48,167 | 100.0% | 44,417 | 92.2% |
| Recommended | 48,173 | 48,166 | 100.0% | 44,371 | 92.1% |
| Restrictive | 48,173 | 46,784 | 97.1% | 44,354 | 92.1% |

Segment counts are **identical across all three profiles for every campaign** (verified: 0/39 campaigns differ) — this is expected, not a coincidence: `qc_time_gap`/`qc_new_segment` in [time_qc.py:60](meteotracker_qc/src/time_qc.py) uses a hardcoded `2.0`-second threshold that is not read from the sensitivity config at all. Only GPS-jump/acceleration and warm-up thresholds actually vary across `qc_permissive.yaml` / `qc_recommended.yaml` / `qc_restrictive.yaml`.

**Per-campaign permissive → restrictive comparison** (computed on each profile's own kept subset, 39 campaigns):

| metric | max | median | mean |
|---|---:|---:|---:|
| row-count loss (percentage points) | 10.3 | 4.0 | 3.6 |
| temperature range loss (°C) | 0.2 | 0.0 | 0.01 |
| latitude-span loss (%) | 0.11 | 0.0 | — |
| longitude-span loss (%) | 2.67 | 0.0 | — |
| satellite-usable share loss (percentage points) | 0.64 | 0.09 | — |

Full per-campaign table (all 39, permissive vs. recommended vs. restrictive kept-share, satellite-share, temperature range, segment count) is preserved in `sensitivity_proper_{permissive,recommended,restrictive}.csv` alongside the closure outputs. The worst single case is `05-27__20260527T08_50_27_..._Sasso_Marconi-Bologna` (100.0% → 89.7% kept, a 10.3-point drop) and `05-27__20260527T08_09_11_..._Bologna-Sasso_Marconi` (99.7% → 90.6%, 9.1 points) — both GPS-jump-driven losses on the Sasso Marconi commute, not geographic-coverage loss (their lat/lon span barely moves) and not thermal-signal loss (temperature range unchanged to 0.0–0.1°C).

**Assessment:** no campaign shows destructive urban-signal loss between permissive and restrictive. The largest row-count impact (10.3 points) is concentrated in one commute route and does not truncate its geographic extent or compress its temperature range. This finding is unchanged whether measured on the 39-nominal or 34-deduplicated campaign set.

### 6. Timezone and satellite comparison

Campaign counts by timezone class, fresh baseline rerun, verified from real per-file parsed data (not assumed): `classify_timezone()` in [time_qc.py:19-27](meteotracker_qc/src/time_qc.py) only ever returns `explicit_offset`, `ambiguous`, or `invalid` — `explicit_utc`, `inferred_utc_high_confidence`, and `inferred_local_high_confidence` are not reachable outcomes of the current implementation (dead classes in the enum, not bugs, just unused paths).

- `explicit_utc`: 0 (unreachable by the current classifier)
- `explicit_offset`: **39 / 39**
- `inferred_utc_high_confidence`: 0 (unreachable)
- `inferred_local_high_confidence`: 0 (unreachable)
- `ambiguous`: 0
- `invalid`: 0

Verified this isn't a first-row artifact: every one of the 39 raw CSVs has an explicit `±HH:MM` offset suffix (e.g. `+01:00`, `+02:00`) on **100% of its `Time` values**, not just a majority — so the per-file `explicit_offset` classification is robust for this dataset, not a borderline call.

**Gating check, in code and in data:**
[pipeline.py:112-118](meteotracker_qc/src/pipeline.py) computes `timezone_safe = classification.isin({explicit_utc, explicit_offset, inferred_utc_high_confidence, inferred_local_high_confidence})` and ANDs it into `use_for_satellite_comparison` alongside `use_for_raw_timeseries`, `gps_valid`, and `~qc_sensor_stabilization`. Regression test `test_ambiguous_timezone_campaign_is_not_satellite_eligible` monkeypatches `classify_timezone` to force `"ambiguous"` and asserts zero satellite-eligible rows — passes. On the real dataset: scanned every standardized frame for rows where `timezone_classification` is *not* in the safe set AND `use_for_satellite_comparison` is `True` — **0 such rows found across all 39 campaigns.** (Moot for this dataset since 0 campaigns are ambiguous/invalid, but the gate is confirmed structurally sound for when one is.)

### 7. Final judgment

**READY FOR EXPLORATORY ANALYSIS** (downgraded from the superseded section's `READY FOR SCIENTIFIC ANALYSIS`)

What passes:
- Directory-level bijection is resolved: 39 CSVs → 39 distinct directories, 0 overwrites, 0 name-collisions, verified on a fresh rerun.
- The warning is corrected (not just filtered) and verified with `-W error` on both the test suite (29/29 passed, 0 warnings) and a full real-data batch run.
- A second real bug — the default config's fractional filtering thresholds silently collapsing `strict`≡`relaxed` — was found during this closure and fixed.
- Per-file row integrity (raw=standardized=flagged, `source_row` unique, strict⊆relaxed⊆flagged) is PASS for all 39/39 files.
- Output completeness is 156/156 across all 4 sensitivity runs.
- Timezone-ambiguous/invalid campaigns are structurally prevented from being satellite-eligible, confirmed in code, by test, and against real data (0 campaigns currently ambiguous/invalid).
- The sensitivity analysis shows no destructive loss of urban thermal or geographic signal between permissive and restrictive.

What blocks `READY FOR SCIENTIFIC ANALYSIS`:
- **The global `source_file + source_row` uniqueness check FAILS** (2,101 duplicated pairs from one byte-identical file pair), which is one of this checklist's explicit gating conditions.
- **5 of the 39 raw input files are redundant re-exports of trips already present under a different filename** (1 byte-identical pair + 4 same-content-different-column-subset pairs found via exhaustive pairwise comparison, not by the original md5-only check). Every aggregate figure computed over "all 39 campaigns" — including the ones in the superseded section above — over-counts by these 5 files unless explicitly deduplicated.
- Deduplication has not been applied to `runs/` because deleting/moving raw input files is an irreversible edit to your original dataset and needs your confirmation on which copy to keep (recommendations are in the Section 1 table).

Path to `READY FOR SCIENTIFIC ANALYSIS`: confirm and apply the 5 keep/drop decisions in Section 1, remove (or move aside) the redundant copies from `runs/`, rerun `run_qc.py` for all 4 configs, and re-verify that 39 input files now equal 34 distinct campaigns with no remaining duplicate `(source_file, source_row)` pairs. Nothing else in this audit needs further work to reach that bar — the pipeline logic itself, once past this raw-data hygiene step, checks out.

## Final Closure Checks (independent re-verification, 2026-07-25)

This section is a from-scratch, adversarial re-check of the 2026-07-23 "Final Closure Checks" section above: every number below was recomputed today directly from the persisted artifacts (not copied from the earlier text), using a standalone verification script run against `outputs_final_closure_{baseline,permissive,recommended,restrictive}` and the raw files in `runs/`. Code file mtimes (`pipeline.py`, `time_qc.py`, `qc_*.yaml` — all last modified 2026-07-23 17:11–22:39) predate the output directories (all generated 2026-07-23 22:40–22:42), so these outputs are current with respect to the code and did not need to be regenerated to be re-checked.

**Bottom line of this re-check: every substantive claim in the 2026-07-23 section holds up.** One inaccuracy was found and is corrected below (Section 5).

### 1. Input-to-output bijection — re-verified

Recomputed independently (not re-stated): 39 CSVs under `runs/` → `_campaign_output_dir()` in [pipeline.py:23-27](meteotracker_qc/src/pipeline.py) produces 39 distinct hashed directory names, all 39 exist under `outputs_final_closure_baseline`, 0 missing, 0 unexpected, 0 collisions. The pre-fix collision is reproduced by inspection of the still-present, never-deleted `outputs/` directory (stem-only naming, no hash): it contains exactly **38** campaign folders for the same 39 source CSVs — confirmed by direct listing, not inference — because `20260304T08_41_51_..._Bologna-Bologna (1).csv` exists under both `runs/02-28/` and `runs/03-04/` and the old naming scheme silently overwrote one with the other. This is the historical bug the hash-suffix fix closes; it is left in place under `outputs/` only as a fossil for comparison, not as an active code path.

Full per-file table, `source_file` → `campaign_id` (= output directory name) → row counts, fresh read of `outputs_final_closure_baseline` today:

| source_file | campaign_id / output_directory | righe raw | righe flagged | stato | nota |
|---|---|---:|---:|---|---|
| 20260213T09_06_57_..._Bologna-Bologna.csv | 02-13__..._353b44f890 | 2167 | 2167 | OK | |
| 20260213T13_23_47_..._Bologna-Bologna.csv | 02-13__..._c098f040ec | 2829 | 2829 | OK | |
| 20260220T09_05_04_..._Bologna-Bologna.csv | 02-20__..._c2b73a152d | 536 | 536 | OK | |
| 20260220T12_54_36_..._Bologna-Bologna (1).csv | 02-20__..._(1)_d8c7858580 | 2437 | 2437 | OK | |
| 20260221T09_17_23_..._Bologna-Bologna.csv | 02-21__..._a2bd5f18d1 | 2310 | 2310 | OK | |
| 20260221T12_52_42_..._Bologna-Bologna.csv | 02-21__..._cf996bfb18 | 2452 | 2452 | OK | |
| 20260228T09_08_22_..._Bologna-Bologna.csv | 02-28__..._fb99845f64 | 1084 | 1084 | OK | |
| 20260228T14_01_31_..._Bologna-Bologna.csv | 02-28__..._fd7d5426a2 | 1907 | 1907 | OK | |
| 20260228T19_09_37_..._Bologna-Bologna.csv | 02-28__..._75c3c3918e | 468 | 468 | OK | |
| **20260304T08_41_51_..._Bologna-Bologna (1).csv** (copy under `02-28/`) | 02-28__..._(1)_928fb5381e | 2101 | 2101 | OK (output) / DUPLICATE (raw content) | md5 `4462fb92…` identical to the row below |
| **20260304T08_41_51_..._Bologna-Bologna (1).csv** (copy under `03-04/`) | 03-04__..._(1)_4d0e0fdcdc | 2101 | 2101 | OK (output) / DUPLICATE (raw content, kept candidate) | byte-identical to row above, confirmed by md5 today |
| 20260304T13_53_03_..._Bologna-Bologna (1).csv | 03-04__..._(1)_93e6367072 | 1993 | 1993 | OK | |
| 20260304T21_12_40_..._Bologna-Bologna (1).csv | 03-04__..._(1)_de6e341cef | 1424 | 1424 | OK | |
| 20260427T07_28_18_..._Bologna-Bologna.csv | 04-27__..._a768d6fc15 | 21 | 21 | OK | |
| 20260427T08_00_36_..._Bologna-Bologna (1).csv (43 col) | 04-27__..._(1)_1cbe131095 | 1142 | 1142 | OK (kept candidate) | Time/Lat/Lon/Temp verified identical to next row |
| **20260427T08_00_36_..._Bologna-Bologna.csv** (5 col, `04-27 moto/`) | 04-27_moto__..._4eb8225b1f | 1142 | 1142 | OK (output) / DUPLICATE (raw content) | confirmed row-by-row identical Time/Lat/Lon/Temp |
| 20260427T08_38_02_private_..._Bologna-Bologna.csv (43 col) | 04-27__..._71d77a7bf2 | 772 | 772 | OK (kept candidate) | Time/Lat/Lon/Temp verified identical to next row |
| **20260427T08_38_02_private_..._UNKNOWN-UNKNOWN.csv** (5 col, `04-27 moto/`) | 04-27_moto__..._14572d7868 | 772 | 772 | OK (output) / DUPLICATE (raw content) | confirmed row-by-row identical Time/Lat/Lon/Temp |
| 20260519T08_17_35_..._Bologna-Bologna (1).csv (43 col) | 05-19__..._(1)_4a76f14cb8 | 1849 | 1849 | OK (kept candidate) | Time/Lat/Lon/Temp verified identical to next row |
| **20260519T08_17_35_..._Bologna-Bologna.csv** (5 col, same folder) | 05-19__..._011248cb28 | 1849 | 1849 | OK (output) / DUPLICATE (raw content) | confirmed row-by-row identical Time/Lat/Lon/Temp |
| 20260527T08_09_11_..._Bologna-Sasso Marconi.csv | 05-27__..._cf22ca7363 | 1161 | 1161 | OK | |
| 20260527T08_50_27_..._Sasso Marconi-Bologna.csv | 05-27__..._70501cac2d | 1133 | 1133 | OK | |
| 20260527T12_58_39_..._Bologna-Bologna.csv | 05-27__..._d3116f69d4 | 234 | 234 | OK | |
| 20260527T13_08_42_..._Bologna-Bologna.csv | 05-27__..._99cbc5b816 | 2053 | 2053 | OK | |
| 20260527T18_39_53_..._Bologna-Bologna.csv | 05-27__..._02ca0ca22a | 942 | 942 | OK | |
| 20260604T08_17_52_..._Bologna-Carpi.csv | 06-04__..._003a500552 | 2418 | 2418 | OK | |
| 20260604T10_49_10_..._Carpi-Bologna.csv | 06-04__..._9a1ec501bf | 2245 | 2245 | OK | |
| 20260604T11_40_32_..._Bologna-Ravenna.csv | 06-04__..._5bd4095200 | 631 | 631 | OK | |
| 20260604T14_34_10_..._Ravenna-Imola.csv | 06-04__..._d0602de380 | 1002 | 1002 | OK | |
| 20260620T07_44_41_..._Bologna-Sasso Marconi.csv | 06-20__..._0545f6d7aa | 1146 | 1146 | OK | |
| 20260620T08_29_06_..._Bologna-Bologna.csv | 06-20__..._ac09a3459a | 1415 | 1415 | OK | |
| 20260620T12_48_24_..._Bologna-Bologna.csv | 06-20__..._64bad4dfc4 | 2834 | 2834 | OK | |
| 20260620T17_20_43_..._Bologna-Bologna.csv | 06-20__..._ec56e23b3a | 1160 | 1160 | OK | |
| 20260620T20_53_29_..._Bologna-Bologna.csv | 06-20__..._cbd2f455f2 | 1231 | 1231 | OK | |
| 20250704T07_55_49_..._Bologna-Bologna (2).csv (42 col) | 07-04_2025_moto__..._(2)_0d9a293803 | 1055 | 1055 | OK (kept candidate) | Time/Lat/Lon/Temp verified identical to next row |
| **20250704T07_55_49_..._Bologna-Bologna (3).csv** (5 col, same folder) | 07-04_2025_moto__..._(3)_103527c9de | 1055 | 1055 | OK (output) / DUPLICATE (raw content) | confirmed row-by-row identical Time/Lat/Lon/Temp |
| 20250704T09_31_26_..._Bologna-Bologna.csv | 07-04_2025_moto__..._e9e4deafbf | 91 | 91 | OK | |
| 20250704T10_15_51_..._Bologna-Bologna.csv | 07-04_2025_moto__..._5f01006ac6 | 933 | 933 | OK | |
| 20250704T14_37_10_..._Bologna-Bologna.csv | 07-04_2025_moto__..._5e89a632f1 | 997 | 997 | OK | |

Totals: 39/39 rows read back match between raw CSV and standardized/flagged output (Σ raw = Σ flagged = 55,092). All 5 bolded rows are genuine, independently re-confirmed raw-data duplicates (1 md5-identical pair + 4 content-identical-different-column-export pairs); they are not an output-pipeline defect — each still gets its own complete, correctly-named, non-overwritten output directory.

Checklist, answered directly, from today's data:
- Two files with the same `campaign_id`? No, 39/39 distinct.
- A directory overwritten (in the current code)? No. (It *would* under the old stem-only naming — reproduced above as the historical 38-directory fossil.)
- Two CSVs intentionally merged? No, the pipeline never merges; verified `run_qc()` writes exactly one directory per input CSV.
- A CSV producing no artefacts? No, 39/39 produced full artefact sets in baseline (and in all 3 sensitivity configs — see Section 4).
- Different filenames normalizing to the same directory? No, checked all 39 pairwise dirname collisions — none.
- All 39 represented via `source_file`? Yes, 39/39 — with the caveat, reconfirmed today, that 5 of those `source_file` values are redundant re-exports of a trip already present under a different `source_file` (evidence in the table above).

### 2. Warning — re-verified today

- Warning text (historical, pre-fix): `Could not infer format, so each element will be parsed individually, falling back to \`dateutil\`. To ensure parsing is consistent and as-expected, please specify a format.`
- Source: `pd.to_datetime(..., errors="coerce", utc=True)` without an explicit `format=`, in `_parse_timestamp_series()`.
- Location today: [time_qc.py:9](meteotracker_qc/src/time_qc.py) — confirmed the call now reads `pd.to_datetime(values, errors="coerce", utc=utc, format="mixed")`, i.e. the fix is present in the file as of this check, not just described in prose.
- Triggering test: `test_non_interpretable_timestamp_is_flagged` (mixed valid/invalid timestamps in one series).
- Cause: pandas auto-detecting a per-element format when a series isn't uniformly parseable.
- Effect on results: none on parsed values; the risk was an unverified implicit assumption, not incorrect output.
- Decision: **corrected** (explicit `format="mixed"` eliminates the inference path that emits the warning), not filtered or suppressed.

Verification run today:
```
./.venv/Scripts/python.exe -m pytest -vv -W error
```
Result: **29 passed in 4.00s, 0 warnings.** (Full pass-by-pass output captured; every one of the 29 tests, including `test_campaign_output_dir_is_unique_for_same_stem_in_different_folders` and `test_ambiguous_timezone_campaign_is_not_satellite_eligible`, passed individually.)

### 3. Row integrity — re-verified, all 39/39 PASS

Per-file checks recomputed today (raw = standardized = flagged; `source_row` present, unique, and equal to `range(n)`; `strict.csv`/`relaxed.csv` row counts match `keep_strict`/`keep_relaxed` sums; `keep_strict` rows ⊆ `keep_relaxed` rows):

| Check | Result |
|---|---|
| raw_rows == standardized_rows == flagged_rows, all 39 files | **PASS 39/39** |
| `source_row` present and unique per file, all 39 files | **PASS 39/39** |
| `source_row` set == `range(raw_rows)`, all 39 files | **PASS 39/39** |
| `strict.csv` row count == `keep_strict` sum, all 39 files | **PASS 39/39** |
| `relaxed.csv` row count == `keep_relaxed` sum, all 39 files | **PASS 39/39** |
| `keep_strict` rows ⊆ `keep_relaxed` rows, all 39 files | **PASS 39/39** |

No FAIL rows in any of the 6 checks × 39 files = 234 individual checks. (Not printed file-by-file since every one reads PASS — the one place where per-file detail matters, the raw/flagged row counts, is already in the Section 1 table above.)

**Global `(source_file, source_row)` uniqueness across the assembled 39-campaign dataset: FAIL, reproduced exactly.** 52,991 pairs total, **2,101 duplicated** — all belonging to `20260304T08_41_51_..._Bologna-Bologna (1).csv`, whose basename is shared by the `02-28/` and `03-04/` copies (`source_file` is `input_path.name`, [pipeline.py:75](meteotracker_qc/src/pipeline.py), so it isn't unique across input subfolders). This check formally catches only the byte-identical pair; the other 4 redundant pairs have distinct `source_file` values so they pass this specific key check while still double-counting the same measurements in any pooled statistic — confirmed independently today by recomputing row-by-row Time/Lat/Lon/Temp equality for all 4 pairs (not re-stated from the earlier section): all 4 came back identical on every compared field.

No duplicated rows were found that are *not* explained by these 5 known files, and no rows are missing (raw = standardized = flagged for all 39, per above).

### 4. Output completeness — re-verified, 156/156

Checked today, for existence **and non-zero size**, across all 39 campaigns × 4 configs (`outputs_final_closure_{baseline,permissive,recommended,restrictive}`) = 156 campaign-config combinations: standardized parquet, flagged CSV, strict CSV, relaxed CSV, report markdown, metrics JSON, diagnostic plot PNG, route map PNG, `config_used.yaml`. (No separate "map" artifact exists in this pipeline beyond `route_map.png`, which is the geographic diagnostic; there is no other mapping output to check.)

**Result: 156/156 complete, 0 missing, 0 zero-byte files, 0 partial campaign directories**, in any of the 4 configs.

### 5. Sensitivity analysis — re-verified, and one inaccuracy corrected

**Correction to the 2026-07-23 section:** it stated the full per-campaign sensitivity table was "preserved in `sensitivity_proper_{permissive,recommended,restrictive}.csv` alongside the closure outputs." Those files **did not exist anywhere on disk** — checked today across the entire project tree, including every `outputs*` folder and `backup_pre_audit`. The aggregate *numbers* quoted in that section were independently recomputed from the persisted flagged CSVs today and matched (see below), so the analysis itself was real and correct; only the specific claim that a reusable per-campaign artifact had been saved was false. **Fixed as part of this closure**: `sensitivity_proper_permissive.csv`, `sensitivity_proper_recommended.csv`, and `sensitivity_proper_restrictive.csv` now exist for real at the project root, each with one row per campaign and columns `campaign_dir, redundant, rows_total, rows_kept_relaxed, pct_kept, rows_kept_strict, valid_length, temp_range_c, temp_sd_c, temp_mad_c, segments, sat_usable_rows, pct_sat_usable`.

**Totals across all 39 nominal campaigns** (recomputed today directly from `outputs_final_closure_{permissive,recommended,restrictive}`):

| Configurazione | righe conservate (relaxed) | percentuale | righe strict | segmenti (somma) | satellite-usable | % satellite |
|---|---:|---:|---:|---:|---:|---:|
| Permissive | 55,086 | 99.99% | 53,480 | 486 | 50,671 | 91.98% |
| Recommended | 55,085 | 99.99% | 53,430 | 486 | 50,621 | 91.88% |
| Restrictive | 53,412 | 96.95% | 53,412 | 486 | 50,603 | 91.85% |

**Same totals, deduplicated to the 34 physically distinct campaigns** (excludes the 5 redundant files identified in Section 1 — this is the number to use for anything scientific):

| Configurazione | righe totali | righe conservate (relaxed) | percentuale | satellite-usable | % satellite |
|---|---:|---:|---:|---:|---:|
| Permissive | 48,173 | 48,167 | 99.99% | 44,417 | 92.20% |
| Recommended | 48,173 | 48,166 | 99.99% | 44,371 | 92.11% |
| Restrictive | 48,173 | 46,784 | 97.12% | 44,354 | 92.07% |

Segment counts are identical across all 3 profiles for every campaign (verified again today: 0/39 differ) because `qc_time_gap`/`qc_new_segment` in [time_qc.py:60](meteotracker_qc/src/time_qc.py) uses a hardcoded 2.0-second threshold not wired to the sensitivity config — only GPS-jump/acceleration and warm-up thresholds vary across profiles.

**Per-campaign permissive → restrictive deltas, worst 10 by kept-row-percentage loss** (recomputed today from each profile's own kept subset):

| campaign_dir | % kept loss (pp) | temp range loss (°C) | satellite-share loss (pp) |
|---|---:|---:|---:|
| 05-27__..._Sasso_Marconi-Bologna__70501cac2d | 10.33 | 0.10 | 0.00 |
| 05-27__..._Bologna-Sasso_Marconi__cf22ca7363 | 9.13 | 0.00 | 0.17 |
| 06-04__..._Bologna-Ravenna__5bd4095200 | 6.97 | 0.00 | 0.31 |
| 06-20__..._Bologna-Bologna__ac09a3459a | 6.86 | 0.00 | 0.00 |
| 05-19__..._Bologna-Bologna_(1)__4a76f14cb8 | 6.54 | 0.00 | 0.06 |
| 05-19__..._Bologna-Bologna__011248cb28 | 6.54 | 0.00 | 0.05 |
| 05-27__..._Bologna-Bologna__d3116f69d4 | 6.41 | 0.20 | 0.00 |
| 05-27__..._Bologna-Bologna__99cbc5b816 | 6.38 | 0.10 | 0.15 |
| 04-27__..._Bologna-Bologna__71d77a7bf2 | 6.22 | 0.00 | 0.13 |
| 04-27_moto__..._UNKNOWN-UNKNOWN__14572d7868 | 6.22 | 0.00 | 0.13 |

**Geographic extent check (new for this re-verification, not in the 2026-07-23 section):** computed lat/lon span of the `keep_relaxed` subset, permissive vs. restrictive, for all 39 campaigns. Worst case is a **2.85% loss in longitude span** (campaign `02-20__..._c2b73a152d`); every other campaign loses ≤0.13% of its lat or lon span between permissive and restrictive. No campaign loses a geographically meaningful segment of its route.

**Assessment, re-confirmed:** no campaign shows destructive urban-signal loss between permissive and restrictive. The largest row-count impact (10.33 pp, one Sasso Marconi commute) does not truncate geographic extent (≤0.02% span change on that campaign) or compress temperature range (0.10 °C). This holds on both the 39-nominal and 34-deduplicated campaign sets.

### 6. Timezone and satellite comparison — re-verified

Recomputed today directly from the standardized/flagged data in `outputs_final_closure_baseline` (not assumed from the classifier's possible enum values):

- `explicit_utc`: 0 (unreachable — [time_qc.py:19-27](meteotracker_qc/src/time_qc.py) `classify_timezone()` only ever returns `explicit_offset`, `ambiguous`, or `invalid`)
- `explicit_offset`: **39 / 39**
- `inferred_utc_high_confidence`: 0 (unreachable)
- `inferred_local_high_confidence`: 0 (unreachable)
- `ambiguous`: 0
- `invalid`: 0

**Gating check, re-run against real data today:** scanned every one of the 39 standardized frames for rows where `timezone_classification` is outside the safe set (`explicit_utc`, `explicit_offset`, `inferred_utc_high_confidence`, `inferred_local_high_confidence`) **and** `use_for_satellite_comparison` is `True`. **0 such rows found**, confirming [pipeline.py:112-118](meteotracker_qc/src/pipeline.py)'s `timezone_safe` gate holds on the full real dataset, not just in the synthetic regression test (`test_ambiguous_timezone_campaign_is_not_satellite_eligible`, re-run today, still passes). This dataset currently has 0 ambiguous/invalid campaigns, so the gate is structurally verified but not exercised by real ambiguous data; the code path is nonetheless confirmed correct by the monkeypatch-based test.

### 7. Final judgment (independent re-check, 2026-07-25)

**READY FOR EXPLORATORY ANALYSIS — unchanged from the 2026-07-23 judgment, now independently reconfirmed with fresh evidence rather than restated.**

Gate-by-gate, against the explicit criteria for `READY FOR SCIENTIFIC ANALYSIS`:

| Gate | Status |
|---|---|
| Tutti i 39 CSV possiedono output completi e univoci | **Complete: yes (156/156).** Procedurally univoci: yes, 39 distinct directories, 0 overwrites. Physically/scientifically univoci: **no** — 5 of the 39 are confirmed redundant re-exports of trips already present under another `source_file` |
| Discrepanza 39 file / 38 cartelle risolta | **PASS** — hash-suffixed naming verified fixed and regression-tested |
| Nessuna sovrascrittura | **PASS** in current code; historical fossil (`outputs/`, 38 dirs) reproduced for evidence only |
| Warning corretto o motivato | **PASS** — corrected via explicit `format="mixed"`, not filtered |
| Tutti i test passano anche con `-W error` | **PASS** — 29/29, 0 warnings, re-run today |
| Integrità delle righe PASS per ogni file | **PASS 39/39** on all 6 per-file checks |
| Campagne con timezone ambigua escluse dal confronto satellitare | **PASS** — 0 ambiguous/invalid in current data, gate structurally verified in code and by test |
| Sensitivity analysis senza distruzione ingiustificata del segnale urbano | **PASS** — max 10.33 pp row loss, ≤0.20 °C range loss, ≤2.85% geographic span loss, worst-case on one commute route |

Everything in the explicit gate list passes except the physical-uniqueness qualifier on the first gate, which is a direct consequence of the still-open, previously-documented raw-data duplication (Section 1/3): **5 of the 39 nominal campaigns are redundant re-exports of a trip already counted elsewhere**, so any statistic pooled over "all 39 campaigns" over-counts those trips unless explicitly deduplicated to the 34 physically distinct campaigns (tables for both are provided in Section 5). This has not changed since 2026-07-23 because fixing it means deleting or moving raw files under `runs/` — an irreversible edit to your original dataset that requires your explicit confirmation of which of each pair to keep (recommendations are in the Section 1 table; kept candidates are marked "OK (kept candidate)").

**Nothing else blocks `READY FOR SCIENTIFIC ANALYSIS`.** Path forward, unchanged: confirm the 5 keep/drop decisions, remove the redundant copies from `runs/`, rerun `run_qc.py` for all 4 configs, and re-verify 39 inputs now equal 34 distinct campaigns with 0 duplicate `(source_file, source_row)` pairs.
