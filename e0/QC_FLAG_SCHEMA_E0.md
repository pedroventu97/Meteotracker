# Schema flag QC E0 – v0.1 DRAFT (5/11/2026)
Stato: **IMPLEMENTED (step 3) + applicato in QC E0 step 4 (5/11/2026)**. Modulo `src/meteotracker_qc/flag_table.py` + AOI `data/aoi/bologna_e0_aoi_v0.1.geojson`. Run QC E0 + split in `outputs/e0_qc_split_20261105T1703/` (locale). Commit/push: passi 5–6 (6/11/2026).
## Policy (DESIGN)
- I flag **non cancellano mai** nulla: i dati raw restano intatti (`keep_raw=true`, VERIFIED: è true in tutte le 60 righe del manifest E0).
- Ogni esclusione ha `rule_id`, `threshold`, `value_observed`, `config_fingerprint` e `code_commit`, quindi si può ricalcolare e verificare.
- `reversible=true` sempre. Ogni flag ha una `severity` tra info, warn ed exclude. L'analisi filtra sui flag, non elimina righe.
## Campi
flag_id, canonical_campaign_id, source_file, source_row, observation_id (=sha256[:12]:row), flag_code, reason, rule_id, qc_profile, threshold, value_observed, severity, reversible, applied_by, applied_at (Europe/Rome), code_commit (placeholder TBD), config_fingerprint.
## Codici flag
Si riusano i nomi `qc_*` già presenti in `src/meteotracker_qc/*.py` (VERIFIED, grep). Si aggiungono 2 codici a livello file per i duplicati: DUP_BYTE_IDENTICAL e DUP_REDUCED_REEXPORT. Le soglie riportate sono quelle del profilo recommended (VERIFIED, `config/qc_recommended.yaml`). I profili reali si chiamano permissive, recommended e **restrictive**: nel repo non esiste un profilo "strict" (VERIFIED).
- **AOI (RISOLTO step 3):** `qc_coord_outside_aoi` usa `data/aoi/bologna_e0_aoi_v0.1.geojson` (True/False; NA solo se lat/lon missing). Severity **warn** (recommended). Conta step 4: 6566 True.
Elenco completo: `qc_flag_schema_E0_v0.1.yaml`.


**AOI (step 3):** qc_coord_outside_aoi usa data/aoi/bologna_e0_aoi_v0.1.geojson (confine Comune di Bologna, da data/external/boundaries/confine_comune_bologna.gpkg). Severity **warn** (recommended). NA solo se lat/lon missing. Vedi data/aoi/README_AOI_E0.md.
