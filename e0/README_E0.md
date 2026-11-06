# README E0 - dataset QC analitico (5/11/2026, aggiornato 6/11/2026)

## Manifest base
- La base E0 è `data/manifests/campaign_manifest_E0_20261015T0835.csv`, una copia byte-identica di `campaign_manifest_20261015T0835.csv` (SHA256 `81C903DE6240E2DEE448CB3DB89122FD2531C97C624B110F34B1E7CEDB16C264`). Ha 60 righe, **55 canoniche** e 5 escluse. VERIFIED.
- Il manifest ufficiale `data/manifests/campaign_manifest.csv` è stato **promosso** (passo 1, 5/11/2026) allo stesso contenuto E0 (stesso SHA256). VERIFIED.
- Archivio senza delete del precedente ufficiale a 44 canoniche: `data/manifests/campaign_manifest_preE0_44canonical_20260731.csv`.
- Le 5 esclusioni sono dupgrp_01-05 e il loro file_sha256 coincide con l'hash calcolato sui file raw (5/5 True). Hanno tutte keep_raw=True. VERIFIED.

## Documenti
- Schema flag: `QC_FLAG_SCHEMA_E0.md` + `qc_flag_schema_E0_v0.1.yaml` (**IMPLEMENTED** step 3)
- Split: `SPLIT_DESIGN_E0.md` (design) + applicazione in `outputs/e0_qc_split_20261105T1703/` (**IMPLEMENTED** step 4, locale, non in git)

## Stato passi (autorizzati da Marco)
1. **FATTO (5/11):** promozione puntatore ufficiale al manifest E0 + archivio pre-E0.
2. **SALTATO:** inventory/recommended già allineati a `recommended_20261015T0835`.
3. **FATTO (5/11):** tabella flag + poligono AOI (vedi sotto).
4. **FATTO (5/11 ~17:03):** QC E0 55/55 + split day/route/spatial_block in `outputs/e0_qc_split_20261105T1703/`.
5. **FATTO (6/11):** commit del lavoro E0 + push branch `feat/meteotracker-windows-app` (include i commit locali precedenti).
6. **FATTO (6/11):** changelog `reports/REPORT_PRINCIPALE.md`.

## Step 3 (2026-11-05, locale) - IMPLEMENTATO
- Flag table writer: `src/meteotracker_qc/flag_table.py` (contratto `qc_flag_schema_E0_v0.1.yaml`); integrazione leggera `MeteotrackerQC.emit_flag_table`.
- AOI: `data/aoi/bologna_e0_aoi_v0.1.geojson` + `data/aoi/README_AOI_E0.md`; `gps.aoi_geojson` nei profili QC; `qc_coord_outside_aoi` non è più sempre NA.
- 19 test focused passati (`tests/test_e0_flag_table_aoi.py` e correlati).

## Step 4 (2026-11-05) - IMPLEMENTATO (output locale)
- 55/55 campagne OK; `flag_table_E0.csv` 165735 righe (warn 105846 / exclude 59857 / info 32); `qc_coord_outside_aoi` 6566.
- Split: n_obs 72505; n_days 17; n_routes non-null 604; n_spatial_blocks 570.
- LCZ WARNING: asset usato fuori repo `D:\projects\LCZ\LCZ_PRISMA.shp` (coverage 0.9148).
- Helper: `e0/run_e0_step4_qc_split.py`, `e0/build_split_assignments_e0.py`.
- Albero output **non** versionato in git (~458 MB). Nessun overwrite 20261015/18; raw intatto.
