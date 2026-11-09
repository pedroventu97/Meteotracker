# Meteotracker QC pipeline

A deterministic, reversible QC workflow for mobile Meteotracker CSV transects: raw preservation, temporal standardization, GPS anomaly marking, meteorological plausibility flags, sensor warm-up marking, derived-variable recalculation, and analytical eligibility classification. It never removes observations — filtering is expressed as columns (`keep_strict`, `keep_relaxed`) that downstream analysis can select on.

See [reports/QC_Methodology.md](reports/QC_Methodology.md) for how the QC method works and [reports/Meteotracker_QC_Audit_Report.md](reports/Meteotracker_QC_Audit_Report.md) for the full audit trail.

## Integrazione Bologna Urban Climate

Per il passaggio dai CSV raw agli output QC `recommended` e quindi all'integrazione,
vedere [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md).

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

This processes the canonical campaigns recorded by the manifest (see "Gestione duplicati" below). Each campaign gets its own output folder under `outputs/recommended/` containing the standardized parquet, the flagged/strict/relaxed CSVs, `metrics.json`, `report.md`, `config_used.yaml`, and two diagnostic PNGs. A raw-file inventory is written to `outputs/recommended/inventory.csv`.

## Applicazione Windows

Per usare il progetto senza VS Code, installare il package con `python -m pip install -e ".[gui]"` oppure usare la build Windows descritta in [docs/BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md). Le istruzioni della GUI e della CLI condivisa sono in [docs/USO_SENZA_VSCODE.md](docs/USO_SENZA_VSCODE.md).

## Core CLI e workspace portabile

Il core applicativo e i comandi `meteotracker` sono descritti in [docs/CORE_CLI_GATE.md](docs/CORE_CLI_GATE.md). La workspace puo essere indicata con `--workspace`, con `METEOTRACKER_WORKSPACE` oppure rilevata dalla directory corrente. `check` e non distruttivo; `apply` usa staging, lock, rollback e ledger.

## Aggiungere una nuova acquisizione

1. Copiare l'esportazione, senza rinominarla o modificarla, in
   `data/raw/<cartella_acquisizione>/`.
2. Eseguire il controllo non distruttivo:

   ```powershell
   python ingest_acquisition.py --campaign <cartella_acquisizione> --check
   ```

   Il comando valida struttura, timestamp, coordinate e duplicati, confronta gli
   hash con il manifest ed esegue i tre profili QC in un'area temporanea. `pass`
   indica che l'acquisizione è applicabile; `ambiguous` o `fail` richiedono una
   decisione/correzione prima di proseguire. Il risultato elenca anche i target
   ufficiali interessati.
3. Applicare soltanto dopo un check riuscito:

   ```powershell
   python ingest_acquisition.py --campaign <cartella_acquisizione> --apply
   ```

   L'apply ripete il check, prepara tutto in staging, quindi aggiorna manifest,
   inventari, i tre profili QC, Session QC/suitability, repeated routes, densità
   spaziale e temporal drift. La promozione conserva copie di rollback fino al
   completamento e non lascia intenzionalmente uno stato parziale.

   Repeated-routes usa per default una cache incrementale deterministica: conserva
   le coppie old-old valide e calcola soltanto new-old/new-new, poi ricostruisce
   sempre il consolidamento globale. Spatial density e temporal drift restano
   prudenzialmente globali. Sensitivity e figure repeated-routes non vengono
   rigenerate dall'apply ordinario e sono marcate in `stale_artifacts.json`.

   Per un backfill completo, compresi sensitivity e figure:

   ```powershell
   python ingest_acquisition.py --campaign <cartella_acquisizione> --apply --full-rebuild
   ```

   Il comando standalone equivalente per repeated-routes e':

   ```powershell
   python -m meteotracker_qc.repeated_routes --skip-qc-refresh --full-rebuild
   ```
4. Verificare `outputs/ingestion/<cartella>_ingestion_report.json`, rieseguire
   `--check` (deve rispondere `already_registered`) e lanciare i test.

`data/raw` è immutabile: il workflow legge e confronta gli SHA-256, ma non scrive,
sposta o elimina raw. Un duplicato con destinazione canonica univoca è registrato
come ridondante; una corrispondenza ambigua blocca l'apply. In caso di errore prima
della promozione gli output ufficiali restano invariati; in caso di errore durante
la promozione vengono ripristinati dai backup di staging.

## Sensitivity analysis

Three threshold profiles are provided in `config/`. To reproduce a full sensitivity run for a profile:

```powershell
python run_qc.py --input data/raw --output <tmp_dir> --config config/qc_permissive.yaml
python run_qc.py --input data/raw --output <tmp_dir> --config config/qc_recommended.yaml
python run_qc.py --input data/raw --output <tmp_dir> --config config/qc_restrictive.yaml
```

Rather than keeping four full copies of every artifact on disk, `outputs/sensitivity/` holds the per-campaign summaries already extracted from these runs:

- `sensitivity_proper_permissive.csv`, `sensitivity_proper_recommended.csv`, `sensitivity_proper_restrictive.csv` — one row per campaign (all 39 nominal files, with a `redundant` column; predates the 2026-07 manifest extension to 49 files -- not regenerated by Fase 4B, out of its scope)
- `sensitivity_comparison.csv` — the same three merged side by side, with permissive→restrictive deltas

## Gestione duplicati

Of the raw CSVs under `data/raw/` (60 as of the 2026-10-15 manifest `data/manifests/campaign_manifest_20261015T0835.csv`; originally 49 under `data/raw/`: 39 through the original audit, plus 10 more added 2026-08 for the 2026-07-22/07-30 campaigns), 5 are redundant re-exports of a trip already present under a different filename (see `reports/Meteotracker_QC_Audit_Report.md` for the evidence and `data/manifests/campaign_manifest.csv` / `duplicate_groups.csv` for the machine-readable mapping). **No raw data is ever deleted or modified** — all raw files stay in `data/raw/` permanently.

Duplication is handled at the analysis layer instead:

- By default, `run_qc.py` processes only the canonical campaigns (`exclude_from_analysis == False` in the manifest): **55** in the official `data/manifests/campaign_manifest.csv`, which since 2026-11-05 holds the E0 catalog (60 rows / 55 canonical / 5 excluded; same content as the dated copies `campaign_manifest_20261015T0835.csv` and `campaign_manifest_E0_20261015T0835.csv`; see `reports/REPORT_PRINCIPALE.md`). History: the previous official manifest had 44 canonical campaigns and is archived, not deleted, as `data/manifests/campaign_manifest_preE0_44canonical_20260731.csv`. The legacy tree `outputs/recommended/` was built from that earlier 44-campaign set; the 55-campaign QC runs are `outputs/recommended_20261015T0835/` and `outputs/e0_qc_split_20261105T1703/` (the `outputs/sensitivity/` summaries still reflect the original 39-file set -- see note above).
- Pass `--include-all-files` to process all 49 files, including the 5 known-redundant ones (e.g. to reproduce the full historical audit, which was run and verified against the original 39).
- `inventory.csv` (written by every run) always lists all files found under `--input`, regardless of this flag — it's a raw-data inventory, not a filtered analysis set.

## Version control and data policy

This repository tracks code, configurations, tests, documentation, manifests, and result summaries — not bulk data. Concretely:

- Git versions: `src/`, `config/`, `tests/`, `reports/`, `data/manifests/`, `outputs/sensitivity/`, and project files (`README.md`, `requirements.txt`, `pytest.ini`, `run_qc.py`, the two `workspace_inventory_*.csv` snapshots).
- The original Meteotracker data stays local in `data/raw/` — all 49 raw exports are preserved on disk but are `.gitignore`d, not committed.
- Full per-campaign outputs (`outputs/recommended/*/`: parquet, flagged/strict/relaxed CSVs, diagnostic PNGs, per-campaign reports) are regenerable from `data/raw/` via `run_qc.py` and are not versioned; only the aggregate summaries in `outputs/sensitivity/` and `outputs/recommended/inventory.csv` are.
- Default analyses use the canonical campaigns defined in `data/manifests/campaign_manifest.csv`. `--include-all-files` exists only to reproduce the historical processing of all raw exports, including known-redundant ones.
- The pre-cleanup backup (`Meteotracker_pre_cleanup_2026-07-25.zip`) is kept outside this repository, in `D:\projects\Meteotracker_archive\`, and is not part of version control.
