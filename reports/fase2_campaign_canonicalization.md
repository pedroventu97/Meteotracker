# Fase 2 — Canonicalizzazione Meteotracker

Gate: **PASS_WITH_WARNINGS**

Generato: 2026-09-16T20:55:32Z  
HEAD: `f404ae3587033835285be87b5a633dd821938e47`  
Branch: `feat/meteotracker-windows-app`  
Nessun commit, push o merge eseguito.

## A. Executive summary

È stato reso ufficiale il contratto di consumo Meteotracker senza modificare soglie QC, flag policy, keep_recommended, session QC o geometria/matching.

Implementato:

- catalogo ufficiale `outputs/campaign_catalog.csv` (44 campagne canoniche, chiave `canonical_campaign_id`);
- fingerprint QC `settings_fingerprint()` scritto in Session QC e nel catalogo (`session_qc_v1`);
- timestamp originali / UTC / locali nel catalogo, con offset esplicito preservato;
- prodotto ufficiale repeated-segment rigenerato dalla pipeline `python -m meteotracker_qc.repeated_routes`, non copiato da `outputs/audit/`;
- membership many-to-many invariata (26 106 punti originali in più segmenti);
- 2026-07-22 e 2026-07-30 incluse nel rebuild ufficiale;
- 2026-08-01 e 2026-09-08 verificate e lasciate **PENDING** (ingest ufficiale le accetterebbe, nessuna promozione automatica).

## B. Architecture

```text
RAW
 ↓
MANIFEST (canonical_campaign_id)
 ↓
POINT QC  (outputs/{permissive,recommended,restrictive})
 ↓
RECOMMENDED parquet + config_used.yaml
 ↓
SESSION QC  (session_qc_v1 + qc_config_fingerprint)
 ↓
CAMPAIGN CATALOG  (outputs/campaign_catalog.csv)
 ↓
REPEATED SEGMENTS  (outputs/repeated_routes/)  OFFICIAL
          │
          │ READ ONLY
          ▼
bologna_urban_climate_integration
```

`outputs/audit/` resta ambiente di verifica. Non è una sorgente ufficiale.

Definizione di campagna canonica (derivata dal manifest esistente, non da un nuovo ID):

> `exclude_from_analysis = false` e `canonical_campaign_id` non vuoto e unico in `data/manifests/campaign_manifest.csv`.

## C. Campaign catalog

- Path: `outputs/campaign_catalog.csv`
- Provenance: `outputs/campaign_catalog_provenance.json`
- Righe: **44** (una per `canonical_campaign_id`, zero duplicati)
- Date locali: 2025-07-04, 2026-02-13, 2026-02-20, 2026-02-21, 2026-02-28, 2026-03-04, 2026-04-27, 2026-05-19, 2026-05-27, 2026-06-04, 2026-06-20, **2026-07-22**, **2026-07-30**
- Session QC: PASS_WITH_WARNINGS 28, PARTIAL 13, PASS 2, NOT_ASSESSABLE 1
- Pending raw non in catalogo: 6 file (8-1 + 9-8)

## D. QC provenance

Catena ricostruibile:

```text
campaign → raw (source_file, source_sha256)
        → config/qc_*.yaml + flag_policy.csv + session_*_policy.csv
        → qc_config_fingerprint = settings_fingerprint(config/)
        → qc_version = session_qc_v1
        → outputs/session_qc/session_qc_inventory.csv
        → recommended parquet (recommended_product + sha256)
```

Fingerprint di questo run:

`0e06b2ee5397030ba4592eeaa1e86857cc5a32cfe127821946be60875641ebc4`

Il calcolo di `settings_fingerprint()` non è stato cambiato.

## E. Repeated-segment status

| Prodotto | Stato |
|---|---|
| `outputs/repeated_routes/` | **OFFICIAL** (rebuild 2026-09-16T20:55:30Z, 44 campagne) |
| `outputs/audit/incremental_validation_20260909/reference44/` | **AUDIT / DERIVED_NOT_YET_CANONICAL** (non usato) |
| Prodotto ufficiale precedente (commit `cec4ca28…`, 2026-07-30) | sostituito dal rebuild; non più la fonte |

Conteggi ufficiali:

- campagne: 44 (43 usable, 1 excluded dal matching: 2026-04-27 short/sparse)
- segmenti: 537
- passages: 1096
- memberships: 155435
- supporting matches: 157877
- matching_algorithm_version: `repeated_routes_schema_version_3` (identificatore già esistente; nessuna semver inventata)
- matching_config_fingerprint: `a757e66cd0b075e9074ff0492d9ab10eb941d3f0659a9ec60dd99189e1117c51`

File ufficiali: `repeated_segments.csv`, `segment_passages.csv`, `point_segment_memberships.csv`, `point_segment_match_support.csv`, `repeated_routes.gpkg`, `provenance.json`.

## F. 22/07 status

Quattro campagne già nel manifest (modifica preesistente). Non ricalcolati gli status QC.

| Rotta | Session QC | spatial_mapping | route_comparison | keep_frac | in matching |
|---|---|---|---|---|---|
| Bologna → Sasso Marconi | PASS_WITH_WARNINGS | YES | YES | 0.743 | sì |
| Sasso Marconi → Bologna | PASS_WITH_WARNINGS | YES | YES | 0.759 | sì |
| Bologna → Bologna | PASS_WITH_WARNINGS | YES | YES | 0.693 | sì |
| Modena → Modena | PASS_WITH_WARNINGS | YES | YES | 0.710 | no membership (nessun segmento ripetuto) |

Verifica timezone sul primo punto Bologna→Sasso Marconi:

`2026-07-22T10:42:34+02:00` = `2026-07-22T08:42:34Z`

Raw non modificato.

## G. 30/07 status

Sei campagne già nel manifest. Pipeline Meteotracker in grado di produrre QC, session QC, recommended e matching. Incluse nel rebuild ufficiale.

| Rotta | Session QC | spatial / route | in matching |
|---|---|---|---|
| Bologna→Bologna 07:42 | PASS_WITH_WARNINGS | YES / YES | sì |
| Bologna→Modena | PARTIAL | YES / YES | sì |
| Castelfranco Emilia→San Giovanni in Persiceto | PARTIAL | YES / YES | no membership |
| Bologna→Bologna 13:12 | PASS_WITH_WARNINGS | YES / YES | sì |
| Bologna→Bentivoglio | PASS_WITH_WARNINGS | YES / YES | sì |
| Bologna→Bologna 21:47 | PASS_WITH_WARNINGS | YES / YES | sì |

Downscaling non è in scope.

## H. 8-1 / 9-8 status

**PENDING_RAW_NOT_IN_MANIFEST** — non promosse.

L’ingest ufficiale (`validate_file`) classifica tutti e 6 i file come `canonical`, `ok=True`, schema 45 colonne, offset `+02:00` esplicito, non duplicati del manifest. Apply sarebbe permesso.

Non è stato eseguito `apply` / non è stato modificato `campaign_manifest.csv` in questa fase: la promozione richiede una decisione esplicita sull’ingest ufficiale, come richiesto.

## I. Many-to-many verification

Chiave membership invariata: `(repeated_segment_id, segment_passage_id, source_file, source_row)`.

Da `membership_summary.json`:

- `n_duplicate_semantic_memberships`: 0
- `n_original_points_in_multiple_segments`: **26106**
- max segmenti per `(source_file, source_row)`: **16**

Il modello one-to-one non è stato introdotto.

## J. Files changed

### Introdotti da questa fase

- `src/meteotracker_qc/campaign_catalog.py` (nuovo)
- `tests/test_campaign_catalog.py` (nuovo)
- `src/meteotracker_qc/inventory.py` (timezone_original / UTC / local; non cambia i flag QC)
- `src/meteotracker_qc/session_qc_pipeline.py` (colonne fingerprint/version)
- `src/meteotracker_qc/session_qc/outputs.py` (fingerprint nel JSON campagna)
- `src/meteotracker_qc/repeated_routes/pipeline.py` (restore `REPO_ROOT`; export CSV segmenti/passaggi)
- `src/meteotracker_qc/repeated_routes/provenance.py` (fingerprint matching + product_status OFFICIAL)
- `src/meteotracker_qc/repeated_routes/__main__.py` (conteggi + catalogo ufficiale)
- `reports/fase2_campaign_canonicalization.md` (questo file)
- `reports/integration_handoff_fase2.md`

### Preesistenti (non sovrascritti nella sostanza)

`.gitignore`, `README.md`, `data/manifests/campaign_manifest.csv` (+7-22/+7-30 già presenti), `outputs/recommended/inventory.csv`, `reports/QC_Methodology.md`, `requirements.txt`, `application.py`, `cli.py`, `gps_qc.py`, `gui/window.py`, `meteo_qc.py`, `pipeline.py`, `stabilization.py`, `time_qc.py`, `ventilation_qc.py`, `tests/test_stabilization.py`.

`tests/test_application.py`: 1 riga allinea il test CLI al comando `sessions` già presente nel working tree.

### Generati / ignorati da git

Catalogo, provenance, Session QC, `outputs/repeated_routes/*` (gpkg, membership, figure, cache). Molti output restano untracked/gitignored. Raw CSV gitignored e non toccati.

## K. Source/raw changes

**NESSUN RAW MODIFICATO**

## L. Git status

Vedi sezione finale della risposta e i comandi `git status` / `git diff --stat` / `git diff --name-only`. Branch invariato. Nessun commit.

## M. Integration handoff

Contratto: `reports/integration_handoff_fase2.md`. Integration resta consumatore read-only. Non è stato modificato `bologna_urban_climate_integration`.

## N. Remaining gaps

- **IMPLEMENTED_AND_VERIFIED**: catalogo, fingerprint QC, timezone nel catalogo/QC, rebuild repeated-routes ufficiale, many-to-many, 22/07 e 30/07 nel prodotto ufficiale, test infrastrutturali, separazione official/audit.
- **IMPLEMENTED_NOT_VALIDATED**: `outputs/recommended/inventory.csv` ha ancora `timezone_original=unknown` perché point QC inventory non è stato rigenerato; il codice `inventory.py` è corretto e i test lo coprono. Il catalogo ufficiale non usa quel campo.
- **PARTIAL_OR_STALE**: 8-1/9-8 pending; Modena-Modena 22/07 e Castelfranco 30/07 canoniche ma senza membership (esito matching, non un bug di canonicalizzazione).
- **PROPOSED_ONLY**: includere il catalogo nei target di `apply` (evitato: `application.py` era già dirty).
- **BLOCKED_BY_MISSING_DATA**: nessuno per questa fase.

## O. Final gate

**PASS_WITH_WARNINGS**

Warnings: campagne 8-1/9-8 lasciate pending; inventory.csv recommended non ancora riallineato sul timezone; working tree già dirty con modifiche GUI/CLI preesistenti.
