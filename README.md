# Meteotracker QC pipeline

A deterministic, reversible QC workflow for mobile Meteotracker CSV transects: raw preservation, temporal standardization, GPS anomaly marking, meteorological plausibility flags, sensor warm-up marking, derived-variable recalculation, and analytical eligibility classification. It never removes observations — filtering is expressed as columns (`keep_strict`, `keep_relaxed`) that downstream analysis can select on.

See [reports/QC_Methodology.md](reports/QC_Methodology.md) for how the QC method works and [reports/Meteotracker_QC_Audit_Report.md](reports/Meteotracker_QC_Audit_Report.md) for the full audit trail.

## Installazione

```powershell
cd D:\projects\Meteotracker
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Test

```powershell
python -m pytest -vv -W error
```

## Esecuzione raccomandata

```powershell
python run_qc.py `
  --input data/raw `
  --output outputs/recommended `
  --config config/qc_recommended.yaml
```

This processes only the 34 canonical campaigns (see "Gestione duplicati" below). Each campaign gets its own output folder under `outputs/recommended/` containing the standardized parquet, the flagged/strict/relaxed CSVs, `metrics.json`, `report.md`, `config_used.yaml`, and two diagnostic PNGs. A raw-file inventory is written to `outputs/recommended/inventory.csv`.

## Sensitivity analysis

Three threshold profiles are provided in `config/`. To reproduce a full sensitivity run for a profile:

```powershell
python run_qc.py --input data/raw --output <tmp_dir> --config config/qc_permissive.yaml
python run_qc.py --input data/raw --output <tmp_dir> --config config/qc_recommended.yaml
python run_qc.py --input data/raw --output <tmp_dir> --config config/qc_restrictive.yaml
```

Rather than keeping four full copies of every artifact on disk, `outputs/sensitivity/` holds the per-campaign summaries already extracted from these runs:

- `sensitivity_proper_permissive.csv`, `sensitivity_proper_recommended.csv`, `sensitivity_proper_restrictive.csv` — one row per campaign (all 39 nominal files, with a `redundant` column)
- `sensitivity_comparison.csv` — the same three merged side by side, with permissive→restrictive deltas

## Gestione duplicati

Of the 39 raw CSVs under `data/raw/`, 5 are redundant re-exports of a trip already present under a different filename (see `reports/Meteotracker_QC_Audit_Report.md` for the evidence and `data/manifests/campaign_manifest.csv` / `duplicate_groups.csv` for the machine-readable mapping). **No raw data is ever deleted or modified** — all 39 files stay in `data/raw/` permanently.

Duplication is handled at the analysis layer instead:

- By default, `run_qc.py` processes only the 34 canonical campaigns (`exclude_from_analysis == False` in the manifest). This is what `outputs/recommended/` and the sensitivity summaries are built from.
- Pass `--include-all-files` to process all 39 files, including the 5 known-redundant ones (e.g. to reproduce the full historical audit, which was run and verified against all 39).
- `inventory.csv` (written by every run) always lists all files found under `--input`, regardless of this flag — it's a raw-data inventory, not a filtered analysis set.

## Version control and data policy

This repository tracks code, configurations, tests, documentation, manifests, and result summaries — not bulk data. Concretely:

- Git versions: `src/`, `config/`, `tests/`, `reports/`, `data/manifests/`, `outputs/sensitivity/`, and project files (`README.md`, `requirements.txt`, `pytest.ini`, `run_qc.py`, the two `workspace_inventory_*.csv` snapshots).
- The original Meteotracker data stays local in `data/raw/` — all 39 raw exports are preserved on disk but are `.gitignore`d, not committed.
- Full per-campaign outputs (`outputs/recommended/*/`: parquet, flagged/strict/relaxed CSVs, diagnostic PNGs, per-campaign reports) are regenerable from `data/raw/` via `run_qc.py` and are not versioned; only the aggregate summaries in `outputs/sensitivity/` and `outputs/recommended/inventory.csv` are.
- Default analyses use the 34 canonical campaigns defined in `data/manifests/campaign_manifest.csv`. `--include-all-files` exists only to reproduce the historical processing of all 39 raw exports (including the 5 known-redundant ones).
- The pre-cleanup backup (`Meteotracker_pre_cleanup_2026-07-25.zip`) is kept outside this repository, in `D:\projects\Meteotracker_archive\`, and is not part of version control.
