# QC di sessione — valutazione trasparente di segmento, sessione e idoneità analitica ("Prompt 3")

Data implementazione: 2026-07-31
Base: `reports/targeted_qc_audit.md` (audit) + `reports/targeted_qc_implementation.md` (QC puntuale/segmentazione, "Prompt 2") + specifica completa "Session QC" (sezioni A-U) fornita dall'utente.
Ambito: aggregazione punto→segmento→sessione, valutazione multi-dimensionale (mai un punteggio unico opaco), idoneità per tipo di analisi, sensitivity a 3 configurazioni. **Non implementati in questa fase** (come richiesto): correzione/diagnosi della deriva termica, detrending, integrazione Netatmo, confronto con stazioni esterne, riconoscimento repeated routes (nessuna modifica né import da `src/meteotracker_qc/repeated_routes/`), classificazione meteorologica dei giorni, map-matching OSM obbligatorio, confronto satellitare. Nessun file in `data/raw/` modificato. Nessun commit creato.

> **Aggiornamento 2026-07-31 (Fase 4B)**: Session QC è stato rieseguito sulle 44 campagne canoniche (le 34 di questo report + 10 nuove campagne di luglio 2026), dopo aver completato anche gli alberi `outputs/permissive/` e `outputs/restrictive/` per le 10 nuove (mancanti fino a questo punto). Le 34 campagne originali e tutti i numeri di questo report **restano il baseline storico**, non alterati. Le 10 nuove campagne sono in linea con la distribuzione qui documentata (nessuna anomalia, nessun `REJECT`, stesse famiglie di flag dominanti). Dettaglio completo del confronto 10-nuove-vs-34 in `reports/temporal_drift_diagnostics.md`, sezione AH. `outputs/session_qc/session_qc_inventory.csv` ora contiene 44 righe, non più 34.

---

## A. Stato iniziale e baseline

Riconfermato prima di ogni modifica (milestone M0):
- `pytest -q -W error`: **99 passed, 0 warning** (QC puntuale + segmentazione, "Prompt 2" completo).
- 34 campagne canoniche nell'albero `outputs/recommended/` (più 5 file ridondanti noti, esclusi da ogni conteggio statistico di questa fase, per principio B.5).
- Pipeline a 3 profili realmente indipendenti (`outputs/{permissive,recommended,restrictive}/`), non una proiezione a singola run.
- `git status`: working tree coerente con la sessione precedente, nessuna sovrapposizione con lavoro concorrente su `repeated_routes/`.

Verifica dati reale eseguita **prima** di scrivere qualunque soglia (disciplina "percentili prima delle soglie", sezione J): `qc_gps_freeze` per sessione varia 1.47%–34.83% (media 12.38%) sull'albero `recommended`; campagna con `keep_recommended` più basso tra le non brevissime: `02-20 09:05:04` (33.2%, 18 segmenti). Percentili di durata/distanza di segmento misurati su tutte le 427 righe di segmento reali prima di fissare qualunque soglia minima (sezione J).

## B. Architettura

Nuovo package `src/meteotracker_qc/session_qc/` (9 moduli) + orchestratore sibling `src/meteotracker_qc/session_qc_pipeline.py`, analogo a `pipeline.py`/`policy.py` del livello puntuale:

| File | Ruolo |
|---|---|
| `metrics.py` | calcolo puro punto→segmento→sessione, **nessuna classificazione** |
| `rules_engine.py` | motore generico di regole dichiarative (`evaluate_dimension`), first-match-wins per priorità, aggregazione reason code |
| `segment_status.py` | 6 dimensioni di segmento + `segment_qc_status` |
| `session_status.py` | 7 dimensioni di sessione + `session_qc_status` + `temporal_drift_assessability` (mai una diagnosi, sezione U) |
| `suitability.py` | 6 categorie `usable_for_*` |
| `outputs.py` | costruzione dei 7 CSV + JSON per campagna |
| `diagnostics.py` | PNG diagnostici multi-pannello per le campagne problematiche |
| `sensitivity.py` | sweep a 3 configurazioni di aggregazione (sezione K) |
| `__init__.py` | minimale |

Principi architetturali onorati esplicitamente:
- **B.1 qualità tecnica ≠ idoneità scientifica**: `segment_qc_status`/`session_qc_status` (qualità tecnica, sezioni F/G) sono calcolati e scritti in output separatamente da `usable_for_*` (idoneità, sezione H) — nessuna colonna deriva l'una dall'altra per semplice rinominazione.
- **B.2 `recommended` come profilo operativo primario**: `MAIN_PROFILE = "recommended_session"` è l'unico profilo scritto negli output principali; `permissive_session`/`conservative_session` esistono solo come contesto di sensitivity (sezione K), mai negli inventari primari.
- **B.3 `keep_recommended==0` non implica REJECT**: REJECT è riservato ad assenza dati genuina (`gps_valid_fraction`/`temp_valid_fraction` sotto un pavimento), verificato esplicitamente sulle due campagne brevi reali (sezione N) e su un caso sintetico (sezione R).
- **B.4 i flag si sovrappongono**: ogni frazione di "problema" a livello di segmento/sessione è un'**unione** di flag booleani (`FAMILY_FLAG_UNIONS` in `metrics.py`), mai una somma di percentuali per-flag; `session_reason_count` conta codici distinti, non occorrenze.
- **B.5 nessun doppio conteggio**: tutti gli output referenziano solo le 34 campagne canoniche, scoperte enumerando le sottocartelle di `outputs/recommended/` (unica fonte di verità sull'elenco canonico, coerente con l'audit).

**Limite architetturale dichiarato** (analogo al caveat già esistente in `policy.py` per la proiezione a 3 profili): `segment_id` differisce leggermente tra i 3 alberi reali (le soglie di gap dipendono dal profilo, `THR-TIME-002/003`). L'inventario di segmento usa **la segmentazione di `recommended` come riferimento unico**; le colonne `keep_permissive`/`keep_restrictive` si uniscono per posizione di riga (`source_row`), con un'asserzione a runtime che le sequenze di `source_row` combacino nei 3 alberi (mai vero per costruzione: nessun profilo elimina righe, solo le marca).

## C. Definizione di durata e distanza

**Regola di attribuzione, unica e testata**: un intervallo `(i-1, i]` conta come valido per il profilo P se e solo se `keep_P[i-1] AND keep_P[i] AND segment_id[i]==segment_id[i-1]`. Per la sola distanza si aggiunge un pavimento invariante-per-profilo, `gps_valid[i-1] AND gps_valid[i]` — necessario perché `qc_spatial_jump`/`qc_gps_freeze` hanno azione `EXCLUDE_RECOMMENDED`: sotto `permissive` (che tiene quasi il 100% delle righe) `keep_permissive` da solo non li escluderebbe, e una distanza calcolata attraverso un salto GNSS confermato sarebbe falsa indipendentemente dal profilo.

Implementazione: `metrics.valid_interval_mask(df, keep_column, segment_column="segment_id", require_gps_valid=False)`, una singola funzione riusata identica a livello di segmento e di sessione, per tutti e 3 i profili.

Definizioni derivate, identiche a quelle già testate nel livello puntuale:
- `nominal_time_span_s` = max−min `time_utc` (include i gap).
- `observed_sampling_duration_s` = somma, per segmento, di max−min `time_utc` (esclude solo i gap che chiudono un segmento — `qc_segment_break` — non i gap brevi interni, che restano dentro la finestra osservata).
- `missing_gap_duration_s` = `nominal_time_span_s − observed_sampling_duration_s`.
- `observed_distance_km` non attraversa mai `qc_segment_break`, anche se a monte i dati fossero incoerenti (guardia esplicita, "difesa in profondità": un test avversariale inietta un valore di distanza spurio proprio sulla riga di rottura e verifica che venga scartato).
- `longest_valid_contiguous_duration_s`/`distance_km`: run-length encoding della maschera di validità per segmento, somma per run, massimo tra i run (stesso idioma già usato in `ventilation_qc.py`/`stabilization.py`).

A livello di segmento, `nominal_time_span_s ≡ observed_sampling_duration_s` sempre — un gap lungo non può esistere dentro un segmento per costruzione (chiude il segmento). Le due colonne sono comunque mantenute a entrambe le granularità per uniformità di schema; l'invariante è verificato da un test dedicato (`tests/test_session_metrics.py`).

## D. Metriche di segmento

Un record per `segment_id`, 83 colonne in output (`outputs/session_qc/segment_qc_inventory.csv`, 427 righe = tutti i segmenti delle 34 campagne canoniche sull'albero `recommended`). Blocchi, per la lista di colonne esatta richiesta dalla specifica:

- **Identificazione**: `canonical_campaign_id, source_file, segment_id, segment_start_timestamp, segment_end_timestamp, segment_start_reason, segment_end_reason`.
- **Dimensione**: `n_raw, n_permissive, n_recommended, n_restrictive, nominal_time_span_s, observed_sampling_duration_s, observed_distance_km`, più `valid_duration_{permissive,recommended,restrictive}_s` e `valid_distance_{permissive,recommended,restrictive}_km` (estesi ai 3 profili anche a livello di segmento, coerente con la sezione D della specifica che li richiede per ogni profilo) e i corrispondenti `longest_valid_contiguous_*`.
- **Campionamento**: `sampling_interval_expected_s, sampling_interval_median_s, sampling_interval_p95_s, n_short_gaps, n_long_gaps, max_internal_gap_s`.
- **GNSS**: `gps_valid_fraction, gps_freeze_fraction, possible_gps_freeze_fraction, spatial_jump_fraction, isolated_position_outlier_fraction, unrealistic_speed_fraction, unrealistic_acceleration_fraction`.
- **Ventilazione/movimento**: `low_speed_device_fraction, low_speed_gps_fraction, low_ventilation_possible_fraction, stationary_fraction, stop_fraction, post_stop_recovery_fraction`.
- **Segnale meteo**: `temp_valid_fraction, temp_spike_fraction, temp_rate_anomaly_fraction, sensor_plateau_fraction, impossible_value_fraction`.
- **Stabilizzazione**: `stabilization_fraction, stabilization_reached, stabilization_reached_after_s, stabilization_reason_code`.
- **Esclusioni**: `excluded_recommended_fraction, primary_exclusion_reason, primary_exclusion_family, secondary_exclusion_reasons, exclusion_reason_count, multi_flagged_fraction`.

Distribuzione reale della durata di segmento (427 segmenti): mediana 11s, p75 52.5s, p90 460.8s, p95 897.6s, p99 1333.4s, max 2606s — **65.6% dei segmenti dura meno di 30s**, frammentazione reale confermata dall'audit puntuale, non un artefatto di questa fase.

## E. Metriche di sessione

Un record per campagna canonica (34 righe, 117 colonne, `outputs/session_qc/session_qc_inventory.csv`), stessa logica aggregata sui segmenti della campagna: `n_segments, keep_fraction_{permissive,recommended,restrictive}, observed_to_nominal_time_ratio, recommended_to_observed_time_ratio, recommended_to_observed_distance_ratio, longest_valid_segment_duration_s/distance_km, total_gap_duration_s, gap_fraction_of_nominal_span, max_gap_s`, più tutte le frazioni `FAMILY_FLAG_UNIONS` (unione di flag, mai somma), `recommended_primary_reason_mode`, `fraction_excluded_by_exactly_one_reason`/`fraction_excluded_by_multiple_reasons`, `n_canonical_fields_total/present/canonical_fields_present_fraction/is_reduced_schema` (verificato: tutte le 34 campagne canoniche hanno schema completo, `is_reduced_schema=False` su tutte — i 4 schemi ridotti individuati dall'audit riguardano solo file esclusi dal canonico).

Enfasi esplicita sul principio B.4: la frequenza grezza per-flag resta disponibile (`segment_reason_codes.csv`/`session_reason_codes.csv`, formato lungo) separata dalla frazione unione-per-famiglia (colonne `*_fraction` in metrics), dal reason primario (una moda deterministica) e dalla frazione multi-flag (`multi_flagged_fraction`) — **mai** sommati come se indipendenti.

## F. Status dimensionali

Vocabolario unico: `OK|WARNING|POOR|NOT_ASSESSABLE`. Nessun modello nascosto, nessuna media pesata: ogni stato è l'esito della prima regola verificata (per priorità crescente) in `config/session_qc_policy.csv`, con `reason_code`, valore osservato (dalla riga stessa), soglia (`threshold`), origine (`evidence_source`) e motivazione (`rationale`) tutti leggibili nella stessa riga di configurazione.

**6 dimensioni di segmento** (`segment_status.py`): `sampling_integrity, gps_quality, thermal_quality, ventilation_risk, stabilization, spatial_continuity`.
**7 dimensioni di sessione** (`session_status.py`): `sampling_integrity, gps_quality, thermal_signal, ventilation_risk, stabilization_quality, spatial_continuity, schema_completeness`.

Distribuzione reale delle 7 dimensioni di sessione (34 campagne): `sampling_integrity` OK=19/WARNING=6/POOR=8/NOT_ASSESSABLE=1; `gps_quality` OK=19/WARNING=12/POOR=3; `thermal_signal` OK=16/WARNING=12/POOR=6; `ventilation_risk` OK=21/WARNING=13/**POOR=0**; `stabilization_quality` OK=17/WARNING=12/POOR=4/NOT_ASSESSABLE=1; `spatial_continuity` OK=7/WARNING=13/POOR=14; `schema_completeness` OK=34/34. `ventilation_risk` non raggiunge mai `POOR` per costruzione (nessuna regola nella configurazione lo permette, verificato da `tests/test_session_qc_config.py`), attuazione diretta del principio B che tratta la ventilazione come segnale di rischio, non come giudizio di qualità del dato termico.

## G. Regole di stato complessivo (rollup)

Stesso motore generico, seconda passata: il `metric` referenzia una colonna di stato dimensionale già calcolata (regole categoriali `==`/`in`), non una metrica grezza. Vocabolario: `PASS|PASS_WITH_WARNINGS|PARTIAL|REJECT|NOT_ASSESSABLE`. Ordine di verifica (priorità crescenti, **il peggiore/il meno noto prima**, non "worst status wins" a posteriori):

1. **`NOT_ASSESSABLE`** (priorità 0): `sampling_integrity_status==NOT_ASSESSABLE` o `stabilization_status==NOT_ASSESSABLE` — durata insufficiente per un giudizio, non un giudizio negativo.
2. **`REJECT`** (priorità 10): `gps_valid_fraction < pavimento` **oppure** `temp_valid_fraction < pavimento` — assenza dati genuina, deliberatamente **non** basata su `excluded_recommended_fraction`/`keep_fraction_recommended` (principio B.3).
3. **`PARTIAL`** (priorità 20): `excluded_recommended_fraction` oltre soglia, oppure `gap_fraction_of_nominal_span` oltre soglia POOR, oppure `n_segments` oltre soglia POOR (frammentazione eccessiva).
4. **`PASS_WITH_WARNINGS`** (priorità 30/31): una riga per dimensione con reason code specifico (`LONG_GAP`, `HIGH_GPS_FREEZE`, `TEMP_RATE_ANOMALIES`, `LOW_VALID_DISTANCE_COVERAGE`, `MISSING_REQUIRED_FIELD`, `HIGH_LOW_SPEED_FRACTION`, `STABILIZATION_NOT_REACHED`, `MANY_SEGMENTS`) — qualunque dimensione `POOR`/`WARNING`.
5. **`PASS`** (priorità 99, fallback `always` obbligatorio, verificato da `tests/test_session_qc_config.py` per ogni combinazione `(level,dimension,profile)`).

Verificato esplicitamente: `NOT_ASSESSABLE` non è trattato come "peggiore" di `POOR` con una gerarchia di gravità nascosta — è verificato **per primo** perché è epistemicamente diverso ("non lo so" vs "lo so ed è cattivo"), non perché sia più grave. Stessa logica, identica a livello di segmento (`segment_status.py`).

## H. Idoneità per tipo di analisi

`suitability.py`, vocabolario `YES|YES_WITH_LIMITATIONS|PARTIAL|NO|NOT_ASSESSABLE`, 6 `analysis_type`: `spatial_mapping, route_comparison, temporal_drift_analysis, satellite_coincidence, environment_class_analysis, full_route_statistics`. Formato lungo (`outputs/session_qc/session_suitability_inventory.csv`, 34×6=204 righe), con `qualifying_segments` (segmenti con `segment_qc_status ∈ {PASS, PASS_WITH_WARNINGS}`, lista a lunghezza variabile — motivo del formato lungo invece che largo) e `limiting_dimensions`.

Distribuzione reale:

| analysis_type | YES | YES_WITH_LIMITATIONS | PARTIAL | NO | NOT_ASSESSABLE(_EXTERNAL_DATA_REQUIRED) |
|---|---:|---:|---:|---:|---:|
| spatial_mapping | 30 | 2 | – | 2 | – |
| route_comparison | 26 | 3 | – | 2 | 3 |
| temporal_drift_analysis | – | 5 | 26 | 2 | 1 |
| satellite_coincidence | – | – | – | – | 34 |
| environment_class_analysis | 30 | 2 | – | 2 | – |
| full_route_statistics | 16 | – | 7 | 11 | – |

`satellite_coincidence` è **sempre e solo** `NOT_ASSESSABLE_EXTERNAL_DATA_REQUIRED` (1 sola regola in `config/session_suitability_policy.csv`, verificato) perché nessun metadato satellitare esiste nel repository — non un giudizio di qualità dei dati MeteoTracker. `route_comparison` non importa mai `repeated_routes/` (verificato via parsing AST degli import, non un semplice controllo di sottostringa — un primo tentativo naïve falliva sul docstring del modulo stesso, che menziona legittimamente "repeated_routes/" per documentare il vincolo).

**Bug di design corretto durante l'implementazione**: la regola `YES` di `spatial_mapping` (`recommended_to_observed_distance_ratio >= 0.7`) aveva originariamente priorità 20, verificata **dopo** la regola più debole `YES_WITH_LIMITATIONS` (priorità 10) — una sessione che qualificava per entrambe otteneva l'esito più debole per first-match-wins. Corretto scambiando le priorità (10=YES, 20=YES_WITH_LIMITATIONS). Nota di asimmetria per futura manutenzione: le regole di rollup (sezione G) verificano il **peggiore** per primo (REJECT prima di PASS-fallback); le regole di idoneità qui verificano il **migliore** per primo — la direzione dipende da quale esito è il fallback generico, non da una convenzione fissa del motore.

## I. Reason codes

Tassonomia centralizzata per famiglia: `TEMPORAL, GPS, STABILIZATION, THERMAL, VENTILATION, SPATIAL, SCHEMA`. Colonna `reason_family` aggiunta a `config/flag_policy.csv` (unica fonte di verità, non un file di mapping separato) per i 39 flag puntuali non vuoti; `SPATIAL` e `SCHEMA` non hanno flag puntuali sorgente — i loro reason code provengono direttamente dalle regole di `config/session_qc_policy.csv` che scattano a livello di aggregazione.

`session_primary_reason` = reason code della **stessa regola di rollup** che ha determinato `session_qc_status` (deterministico per costruzione, mai una moda separata soggetta a pareggi impliciti). `session_secondary_reasons`/`session_reason_count`/`session_reason_families` derivano da tutte le **altre** dimensioni che hanno prodotto un reason code non-OK — `session_reason_count` conta **codici distinti**, mai una somma di percentuali per-flag (implementazione diretta del principio B.4).

Distribuzione reale di `session_primary_reason` sulle 34 campagne (profilo `recommended_session`): `LONG_GAP`=9, `LOW_VALID_DISTANCE_COVERAGE`=6, `VALID_LOCAL_SEGMENTS_ONLY`=4, `HIGH_GPS_FREEZE`=4, `TEMP_RATE_ANOMALIES`=4, `MANY_SEGMENTS`=3, `STABILIZATION_NOT_REACHED`=1, `TOO_SHORT_FOR_INTEGRITY_ASSESSMENT`=1, nessuno (PASS pulito)=2.

**Bug corretto durante l'implementazione** (trovato solo sulla run reale, non nei test sintetici): la maggior parte dei `PASS_WITH_WARNINGS` mostrava inizialmente il codice generico e non informativo `QUALITY_DIMENSION_NOT_ASSESSABLE` per **ogni** dimensione, perché lo script di generazione della policy riusava un unico placeholder per tutte le regole `PWW-{dim}-POOR/WARN`. Corretto mappando ogni dimensione al proprio reason code specifico (elenco sopra); rigenerata la policy, rieseguita la pipeline: la distribuzione di `session_qc_status` è rimasta **identica** (conferma che il fix era di sola chiarezza, non di comportamento).

## J. Soglie e provenienza

`config/session_qc_policy.csv` (306 righe: 141 a livello segmento, 165 a livello sessione — include le 3 configurazioni di sensitivity) e `config/session_suitability_policy.csv` (23 righe), schema analogo a `config/threshold_provenance.csv` del livello puntuale: `rule_id, level, dimension, profile, metric, operator, threshold, unit, resulting_status, reason_code, priority, evidence_source, rationale, sensitivity_values, enabled`.

Distribuzione `evidence_source` (306 righe): `engineering_default`=201, `data_distribution`=99, `thesis_documented`=6 (le sole 6 righe che ereditano `low_speed_threshold_kmh=7.0` dalla tesi, già documentata nel livello puntuale). Nessuna soglia è stata scelta per ottenere una distribuzione desiderata di PASS/REJECT — le soglie `data_distribution` sono ancorate ai percentili reali misurati **prima** di scrivere la policy (sezione A/M0), non scelte a ritroso guardando l'esito. Esempio verificabile: la soglia POOR di `gap_fraction_of_nominal_span` è impostata così che Bologna-Ravenna (gap reale ≈84.1% dello span nominale) la superi in **tutte e tre** le configurazioni di sensitivity — verificato da un test di configurazione dedicato (`tests/test_session_qc_config.py`), non da un'ispezione manuale.

## K. Sensitivity analysis

`sensitivity.py`, 3 configurazioni di **solo aggregazione** (`permissive_session/recommended_session/conservative_session` — varia soglie come durata minima segmento, `keep_recommended` minimo, `gap_fraction` POOR, `n_segments` POOR, ecc.; **non** riderivazione dei flag puntuali, che restano quelli del profilo `recommended` calcolati a monte). `run_session_sensitivity()` applica `compute_session_status()` alle stesse metriche già calcolate, una volta per profilo; `run_segment_sensitivity()` fa lo stesso a livello di segmento. Output: `outputs/session_qc/session_qc_sensitivity.csv` (102 righe = 34 campagne × 3 profili).

Distribuzione reale (`session_qc_status` per profilo, 34 campagne ciascuno):

| profilo | PASS | PASS_WITH_WARNINGS | PARTIAL | NOT_ASSESSABLE | REJECT |
|---|---:|---:|---:|---:|---:|
| permissive_session | 8 | 19 | 7 | 0 | 0 |
| recommended_session | 2 | 20 | 11 | 1 | 0 |
| conservative_session | 0 | 18 | 15 | 1 | 0 |

**17 delle 34 campagne (50%) cambiano classe** tra almeno due configurazioni, sempre in direzione monotona (mai una campagna classificata peggio sotto `permissive_session` che sotto `conservative_session` — verificato da `tests/test_session_sensitivity.py::test_permissive_never_stricter_than_conservative_per_campaign`). Esempio notevole: la campagna breve a 21 righe passa da `PARTIAL` (`permissive_session`) a `NOT_ASSESSABLE` (`recommended_session`/`conservative_session`) — la sua durata (29s) supera la soglia minima permissiva (15s) ma non quella raccomandata/conservativa (30s/60s). Bologna-Ravenna resta `PARTIAL` in tutte e tre le configurazioni per costruzione (vedi sezione J).

**Nessuna configurazione è scelta automaticamente**: `sensitivity.py` non produce alcun campo "profilo migliore"/"best_profile" (verificato da un test dedicato). La scelta di `recommended_session` come profilo operativo primario è una decisione dichiarata qui, non un artefatto del codice:
- **Rischio di falso PASS** (rilevante per `permissive_session`): 8 campagne PASS pure, 0 REJECT/NOT_ASSESSABLE — rischio di trattare come solide sessioni con `keep_recommended` anche sotto il 30% se altre dimensioni non intercettano il problema.
- **Rischio di falso REJECT/PARTIAL** (rilevante per `conservative_session`): 0 PASS puri, 15 PARTIAL — rischio di scartare per uso scientifico segmenti in realtà utilizzabili localmente, specialmente le campagne fortemente frammentate (molti segmenti brevi ma individualmente validi).
- `recommended_session` è il compromesso dichiarato: nessuna campagna raggiunge REJECT (nessuna delle 34 ha un'assenza dati genuina), ma la frammentazione e i gap lunghi restano visibili come PARTIAL invece di essere nascosti sotto PASS.

## L. Risultati sulle 34 campagne

Pipeline eseguita end-to-end sull'intero albero `recommended`: 427 segmenti, 34 sessioni, 204 righe di idoneità, 16 PNG diagnostici, 34 JSON per-campagna. Tutti gli output referenziano esclusivamente le 34 campagne canoniche (verificato: `n_raw.sum()` coincide esattamente tra `segment_qc_inventory.csv` e `session_qc_inventory.csv`, nessun conteggio duplicato dai 5 file ridondanti).

`segment_qc_status` (427 segmenti): NOT_ASSESSABLE=324 (75.9%, quasi tutti per durata sotto soglia — mediana delle durate NOT_ASSESSABLE: 6s, massimo 59s), PASS_WITH_WARNINGS=77, PARTIAL=15, PASS=11, **REJECT=0**. L'alta quota di `NOT_ASSESSABLE` a livello di segmento è la conseguenza diretta e attesa della frammentazione reale già documentata dall'audit puntuale (65.6% dei segmenti sotto i 30s) — non un difetto della classificazione: un segmento di 6 secondi non offre abbastanza dato per giudicare stabilizzazione o continuità campionamento, e dirlo esplicitamente (`NOT_ASSESSABLE`) è più corretto che forzare un giudizio (principio B.3 esteso al livello di segmento).

## M. Distribuzione PASS/PASS_WITH_WARNINGS/PARTIAL/REJECT/NOT_ASSESSABLE

`session_qc_status` sulle 34 campagne canoniche (profilo `recommended_session`, l'unico scritto negli output primari):

| Stato | N | % |
|---|---:|---:|
| PASS_WITH_WARNINGS | 20 | 58.8% |
| PARTIAL | 11 | 32.4% |
| PASS | 2 | 5.9% |
| NOT_ASSESSABLE | 1 | 2.9% |
| REJECT | 0 | 0.0% |

**Nessuna campagna raggiunge REJECT** — coerente con l'audit, che non aveva trovato alcuna campagna con assenza dati genuina (`gps_valid_fraction`/`temp_valid_fraction` sistematicamente vicini a zero) tra le 34 canoniche. Il caso REJECT è comunque implementato e testato (sezione R, caso sintetico) per campagne future che dovessero presentarlo.

## N. Analisi delle due campagne brevi

- **`04-27 07:28:18`** (21 righe, 29s, 1 segmento): `session_qc_status=NOT_ASSESSABLE`, `session_primary_reason=TOO_SHORT_FOR_INTEGRITY_ASSESSMENT`. La durata (29s) è sotto la soglia minima di `recommended_session` (30s) per `sampling_integrity`/`stabilization` — un giudizio di "non abbastanza dato", non un giudizio negativo. Sotto `permissive_session` (soglia 15s) diventa `PARTIAL` (sezione K) — la sensitivity conferma che è un caso di confine reale, non un artefatto di una singola soglia arbitraria.
- **`07-04 09:31:26`** (91 righe, 122s, 1 segmento, `keep_recommended=0%`): `session_qc_status=PARTIAL`, `session_primary_reason=VALID_LOCAL_SEGMENTS_ONLY`, **mai REJECT** nonostante `keep_fraction_recommended` esattamente zero — perché `gps_valid_fraction`/`temp_valid_fraction` restano ben sopra il pavimento REJECT (i dati grezzi sono presenti e validi, solo interamente esclusi dalla policy puntuale `recommended` per altri motivi, es. freeze/stabilizzazione mai raggiunta). Verificato stabile in tutte e 3 le configurazioni di sensitivity (sezione K).

Entrambe le campagne confermano il principio B.3: `keep_recommended==0` non è mai stato trattato come equivalente a dati scientificamente corrotti.

## O. Analisi Bologna-Ravenna

`06-04 11:40:32` (631 righe, 4597s nominali, gap ≈2469s ≈53.7%* dello span nominale — *la cifra `gap_fraction_of_nominal_span` effettiva nella metrica è 84.1%, perché include anche i gap brevi interni oltre al gap principale; il gap singolo più lungo resta ≈2469s/53.7%, riportato separatamente in `max_gap_s`, 5 segmenti, `keep_recommended=87.0%`): `session_qc_status=PARTIAL`, `session_primary_reason=LONG_GAP`, in **tutte e 3** le configurazioni di sensitivity (per costruzione, sezione J).

Verificato sui dati reali (`tests/test_session_regression_real_data.py::test_bologna_ravenna_lands_partial_with_valid_segments_intact`):
- `n_segments >= 2` (il gap produce effettivamente una rottura di segmentazione, non viene assorbito).
- Almeno un segmento resta `PASS`/`PASS_WITH_WARNINGS` a livello di segmento — **il gap non invalida i segmenti puliti lontani da esso**.
- `nominal_time_span_s > observed_sampling_duration_s` (durata nominale e osservata restano esplicitamente distinte, mai confuse in output).
- `spatial_continuity_status=POOR` (il gap riduce la copertura spaziale continua) e `stabilization_quality_status=WARNING` (i 4 segmenti post-gap passano una parte della propria durata in `qc_segment_restart_recovery`), ma la sessione **non** collassa a REJECT.

Questo era il caso-oracolo più a rischio di regola sbagliata durante la pianificazione (una prima formulazione ipotetica avrebbe potuto sommare la frazione di gap a `excluded_recommended_fraction`, portando a REJECT anche con segmenti validi) — verificato che l'implementazione finale non lo fa: REJECT dipende solo da `gps_valid_fraction`/`temp_valid_fraction`, mai da `gap_fraction_of_nominal_span`.

## P. Campagne più problematiche

Le 11 campagne `PARTIAL` (oltre a Bologna-Ravenna e alle due campagne brevi, già discusse):

| Campagna | Motivo primario | Nota |
|---|---|---|
| `02-13 09:06:57` (1Hz) | MANY_SEGMENTS | 63 segmenti, `keep_recommended=83.8%` — frammentazione, non scarsa qualità puntuale |
| `02-13 13:23:47` | MANY_SEGMENTS | 122 segmenti — la campagna più frammentata dell'intero dataset |
| `02-20 09:05:04` | VALID_LOCAL_SEGMENTS_ONLY | `keep_recommended=33.2%`, 18 segmenti — caso-oracolo di sezione R, confermato PARTIAL non REJECT |
| `02-28 09:08:22` | LONG_GAP | `gap_fraction=53.7%` |
| `05-19 08:17:35` | LONG_GAP | `gap_fraction=44.9%` |
| `05-27 12:58:39` | LONG_GAP | campagna corta (529s), gap ≈41% |
| `05-27 18:39:53` | VALID_LOCAL_SEGMENTS_ONLY | `keep_recommended=44.5%` |
| `06-20 08:29:06` | MANY_SEGMENTS | 84 segmenti |
| `07-04 10:15:51` (max freeze, molte soste) | VALID_LOCAL_SEGMENTS_ONLY | vedi sezione R, `gps_quality=POOR` ma non REJECT |

Nessuna di queste 9 campagne è stata gestita con una regola speciale caso-per-caso: tutte derivano dalle stesse regole generali di sezione G, verificate una a una in sezione R.

## Q. Campagne di qualità migliore

Solo 2 campagne raggiungono `PASS` puro (nessuna dimensione sopra `OK`):
- **`02-28 14:01:31`** (1907 righe, 1931s, 1 segmento, `keep_recommended=83.1%`, `gps_freeze=1.5%`) — la campagna con il freeze GNSS più basso tra le 34.
- **`05-27 08:09:11`** (1161 righe, 1741s, 1 segmento, `keep_recommended=71.7%`, `gps_freeze=8.5%`).

Entrambe: 1 solo segmento (nessuna rottura), nessun gap lungo, `gps_freeze_fraction` tra le più basse osservate. Il fatto che solo 2/34 campagne raggiungano `PASS` puro (contro 20 `PASS_WITH_WARNINGS`) non è una soglia troppo severa: riflette che quasi ogni campagna reale ha *almeno* una dimensione con qualche warning (tipicamente `spatial_continuity` o `thermal_signal`), il che è esattamente l'informazione che il principio B.1/B.4 vuole rendere visibile invece di nasconderla dietro un unico giudizio binario.

## R. Risultati dei test

`pytest -q -W error`: **99 → 213 passed, 0 warning** (114 nuovi test in questa fase, nessuna regressione). Suddivisione:

| File | Test | Oggetto |
|---|---:|---|
| `test_session_metrics.py` | 11 | durata/distanza, attribuzione, non doppio conteggio |
| `test_session_rules_engine.py` | 17 | motore generico, first-match-wins, operatori |
| `test_session_qc_config.py` | 10 | configurazione reale (vocabolari, fallback, evidence_source) |
| `test_segment_status.py` | 12 | 6 dimensioni di segmento, keep=0 ≠ REJECT |
| `test_session_status.py` | 10 | 7 dimensioni di sessione, Bologna-Ravenna sintetico |
| `test_drift_assessability.py` | 5 | `temporal_drift_assessability`, mai una diagnosi |
| `test_suitability.py` | 8 | 6 categorie, satellite sempre NOT_ASSESSABLE, no import repeated_routes |
| `test_session_outputs.py` | 14 | 7 CSV + JSON reali, coerenza, solo 34 campagne |
| `test_diagnostics.py` | 3 | selezione e generazione PNG reali |
| `test_session_regression_real_data.py` | 14 | i 9 casi reali della sezione R + 1 sintetico + hash raw + no-import |
| `test_session_sensitivity.py` | 10 | sweep 3 profili, nessuna auto-selezione, monotonia |
| **Totale nuovo** | **114** | |

**I 9 casi reali richiesti** (`test_session_regression_real_data.py`), tutti verificati sui dati veri, non su fixture sintetiche:
1. Bologna-Ravenna → PARTIAL, segmenti validi intatti.
2. Campagna 21 righe → NOT_ASSESSABLE, mai REJECT.
3. Campagna 91 righe → PARTIAL nonostante `keep_recommended=0`, mai REJECT.
4. Campagna a freeze massimo (34.8%) → `gps_quality=POOR` ma non REJECT.
5. Campagna `02-20` (keep più basso tra le non brevi) → PARTIAL, non REJECT.
6. Campagna quasi perfetta (`02-28 14:01:31`) → PASS/PASS_WITH_WARNINGS.
7. Campagna reale a 1Hz → cadenza mediana confermata 1.0s, classificazione coerente.
8. Campagna reale a 2Hz → cadenza mediana confermata 2.0s, `sampling_integrity` mai POOR per la sola cadenza nativa.
9. Campagna a più soste (coincide con il caso 4 sui dati reali, non forzata a essere distinta) → `ventilation_risk` mai POOR.
10. Campagna a massimo disaccordo device/GPS (identificata dinamicamente, non hardcoded) → non forza REJECT a meno di assenza GPS genuina.

Più: 1 caso sintetico (freeze estremo + `gps_valid_fraction≈0`) → REJECT, l'unico scenario REJECT del progetto (non presente tra le 34 reali); verifica hash SHA-256 di un campione di file raw (nessuna modifica); verifica AST che nessun modulo del package `session_qc` importi `repeated_routes`.

## S. Rischi di falsi positivi e falsi negativi

- **Falso PASS (rischio maggiore sotto `permissive_session`)**: una sessione con `keep_recommended` moderato ma senza gap lunghi né frammentazione eccessiva può ottenere PASS pur avendo una quota non trascurabile di righe escluse per motivi puntuali (es. freeze, spike termici sparsi) che non superano singolarmente le soglie di sessione. Mitigazione: `recommended_session` (profilo primario) ha soglie più severe di `permissive_session` su `keep_fraction`/`gap_fraction`/`n_segments`, e ogni dimensione resta visibile separatamente in output anche quando il rollup è PASS_WITH_WARNINGS.
- **Falso REJECT/PARTIAL (rischio maggiore sotto `conservative_session`)**: campagne fortemente frammentate ma con singoli segmenti individualmente validi (es. `02-13 13:23:47`, 122 segmenti) rischiano di essere scartate a livello di sessione anche quando una parte sostanziale dei dati è scientificamente utilizzabile localmente — motivo per cui `usable_for_*` (sezione H) referenzia `qualifying_segments` invece di un giudizio di sessione unico: un ricercatore interessato a un sottoinsieme di percorso può ancora identificare i segmenti utilizzabili anche quando `session_qc_status=PARTIAL`.
- **Rischio non testabile sui dati attuali**: nessuna delle 34 campagne reali raggiunge REJECT, quindi il comportamento REJECT è verificato solo su un caso sintetico — un vero campione REJECT (sensore spento a metà campagna, GPS assente per l'intera sessione) non è disponibile per validare la soglia empiricamente; la soglia resta `engineering_default`, non `data_distribution`, per questo motivo (dichiarato in `config/session_qc_policy.csv`).
- **`spatial_continuity` è la dimensione più severa** (14/34 POOR, 13/34 WARNING, solo 7/34 OK) — riflette la frammentazione strutturale del dataset più che un difetto della soglia; un utente che leggesse solo `session_qc_status` senza le dimensioni sottostanti rischierebbe di sottostimare quante campagne hanno comunque una buona `gps_quality`/`thermal_signal` nonostante `spatial_continuity` bassa — motivo esplicito per cui la specifica vieta un punteggio unico (principio B.1).

## T. Limiti residui

- Il riferimento di segmentazione cross-profilo (sezione B, `recommended` come unico riferimento) è un compromesso dichiarato, non un limite nascosto: `keep_permissive`/`keep_restrictive` a livello di segmento ereditano i confini di segmento di `recommended`, che possono differire leggermente (gap borderline) da quelli che i profili `permissive`/`restrictive` userebbero se segmentati autonomamente.
- Le soglie `engineering_default` (201/306 righe di policy) non sono ancora sottoposte a una sensitivity analysis granulare soglia-per-soglia (solo alle 3 configurazioni aggregate) — un lavoro futuro naturale sarebbe una sensitivity a una soglia alla volta, analoga a quella già fatta nel livello puntuale per `warmup.min_stable_seconds`.
- `full_route_statistics` è `NO` per 11/34 campagne — la soglia (`recommended_to_observed_distance_ratio` minimo) non è stata tarata con una sensitivity dedicata separata da quella di `spatial_mapping`, che condivide la stessa metrica; un'analisi più fine potrebbe differenziarle.
- I PNG diagnostici (16/34 campagne, quelle problematiche) usano marcatori `axvline`/testo invece di annotazioni per-punto ruotate, per un bug di rendering di questo ambiente matplotlib/freetype documentato e aggirato (non un limite dei dati, ma vale la pena ricordarlo per chi debba estendere `diagnostics.py`: `ax.axis("off")` sull'ultimo asse di una figura `sharex=True` con asse x datetime, combinato con qualunque `ax.text()`, causa un errore di overflow nel transform di freetype — evitato nascondendo tick/spine manualmente).

## U. Decisioni rinviate alla diagnosi della deriva temporale

Per esplicita richiesta della specifica (sezione I), questa fase **non diagnostica** la deriva termica. `temporal_drift_assessability ∈ {ASSESSABLE, PARTIALLY_ASSESSABLE, NOT_ASSESSABLE}` (mai `TEMPORALLY_STABLE`/`SENSOR_DRIFT`/`BACKGROUND_CHANGE` — vocabolario verificato assente da `tests/test_drift_assessability.py`) indica solo se esistono abbastanza dati comparabili per un **futuro** tentativo di diagnosi: durata minima per profilo (`DRIFT_MIN_DURATION_S`), posizioni di inizio/fine sufficientemente vicine (`start_end_locations_comparable`, soglia 300m via `pyproj.Geod`, geodesica reale non euclidea), frammentazione limitata (`n_segments <= 2`) e copertura dati sufficiente (`keep_fraction_recommended`).

I campi `start_temperature_c`, `end_temperature_c`, `raw_start_end_temperature_difference_c`, `raw_start_end_time_difference_s` sono **puramente descrittivi**: calcolati e scritti in output, ma mai usati per classificare `thermal_signal`/`thermal_quality` né qualunque altra dimensione — verificato che nessuna regola in `config/session_qc_policy.csv` referenzia queste colonne come `metric`. `start_end_comparison_warning` avverte esplicitamente contro l'interpretazione ("locations_close_enough_to_compare_but_this_is_not_a_drift_diagnosis" / "start_and_end_locations_are_far_apart_do_not_interpret_the_difference_as_drift") per impedire che un consumatore a valle legga una differenza di temperatura grezza come se fosse già una diagnosi di deriva.

Decisioni esplicitamente rinviate a una fase futura, che dovrà avere il proprio prompt/specifica: soglia di rilevamento deriva (quale `raw_start_end_temperature_difference_c` costituisce una deriva reale vs rumore/microclima locale), correzione/detrending, confronto con Netatmo o stazioni esterne per validare la deriva osservata, e se `temporal_drift_analysis` (idoneità, sezione H) debba diventare `usable_for_temporal_drift_analysis=YES` solo dopo che una vera diagnosi esista (oggi è `PARTIAL`/`YES_WITH_LIMITATIONS` per 31/34 campagne, riflettendo l'assessabilità, non l'assenza di deriva).
