# Implementazione QC v2 — controlli puntuali e segmentazione ("Prompt 2")

Data implementazione: 2026-07-30
Base: `reports/targeted_qc_audit.md` (audit mirato, stessa sessione) + specifica completa "Prompt 2 aggiornato" (sezioni A-P) fornita dall'utente.
Ambito: correzione e ampliamento del QC puntuale e della segmentazione. **Non implementati in questa fase** (come richiesto): stato sessione PASS/PARTIAL/REJECT, correzione deriva termica, integrazione Netatmo, map-matching OSM obbligatorio. Nessun file in `data/raw/` è stato letto in modalità scrittura. Nessun commit creato.

---

## A. Stato iniziale e baseline

Riconfermato prima di ogni modifica (milestone M0):
- `pytest -q -W error`: **29 passed, 0 warning** (identico all'audit).
- 39 CSV raw, 34 campagne canoniche, 5 file ridondanti noti, 4 schemi di colonne (42/43/44/5).
- `git status`: working tree con le sole modifiche pre-esistenti (`README.md`, `INTEGRATION_GUIDE.md`) più, scoperto durante la riverifica, un modulo `src/meteotracker_qc/repeated_routes/` e `requirements.txt` (aggiunta `geopandas`/`shapely`/`pyogrio`) **non creati da questa sessione** — lavoro concorrente di un'altra sessione (concettualmente il "Prompt 4" del piano originale dell'utente). Non toccato, nessuna sovrapposizione di file.
- File reali confermati: gap Bologna–Ravenna (06-04, ~2469s/41min su 4597s nominali) usato come fixture di regressione esplicita; campagna 06-20 12:48:24 (2834 righe) usata come fixture per il fix della stabilizzazione (127/130 flag oltre la riga 120 nella versione precedente).

## B. Bug corretti

1. **`warmup.min_stable_seconds` era morto**: letto dal config in `stabilization.py` e mai più referenziato. Ora è realmente usato per determinare la durata minima della finestra stabile continua.
2. **`qc_sensor_stabilization` non era limitato all'avvio**: rilevatore a slope sull'intero file, non finestra iniziale. Verificato su dati reali: prima del fix, 127/130 flag (98%) cadevano dopo la riga 120 su una campagna da 2834 righe. Dopo il fix, il flag è una finestra contigua dall'inizio del segmento (verificato: `first=0`, mai riattivato — test di regressione dedicato).
3. **Unità sbagliate in `acceleration_gps_ms2`**: la formula originale calcolava `(km/h delta) / dt_s`, cioè (km/h)/s, non m/s² nonostante il nome e la soglia di configurazione (`acceleration_ms2_abs`) lasciassero intendere m/s². Corretto in `acceleration_gps_mps2` con conversione esplicita a m/s prima della derivata. Nessun impatto sui risultati storici (il flag era comunque morto, mai consumato a valle), ma cambia il comportamento ora che `qc_unrealistic_acceleration` è agganciato alla policy.
4. **Soglia gap/segmento duplicata in due moduli** (`time_qc.py` e `gps_qc.py`, entrambe hardcoded `2.0`): unificata in `time_qc.py` come unica fonte di verità; `gps_qc.py` non ha più una propria soglia, si affida esclusivamente alla continuità di `segment_id`.
5. **`gps_valid` non considerava `qc_coord_missing`**: righe senza fix GPS potevano risultare `gps_valid=True`. Corretto: `gps_valid = ~(qc_gps_freeze | qc_spatial_jump | qc_coord_missing)`.
6. **`qc_gps_freeze`, `qc_temp_impossible/humidity_impossible/pressure_impossible` erano calcolati e mai usati**: ora agganciati alla policy (vedi sezione L).
7. **Parametro morto `speed_mode` in `detect_gps_issues`**: mai referenziato nel corpo della funzione, rimosso (nessun chiamante lo passava).

## C. Normalizzazione dei quattro schemi

Nuovo modulo `src/meteotracker_qc/schema.py` (non previsto esplicitamente nel piano approvato inizialmente, aggiunto per onorare la sezione B della specifica completa arrivata durante la pianificazione). `normalize_columns(df)` produce colonne `canonical_*` (timestamp, latitude, longitude, temperature_c, humidity_pct, pressure_mbar, altitude_m, speed_device_kmh_raw, radiation_raw, bluetooth_rssi_dbm, dewpoint_device_c, theta_device_k, device_delta_temp_c_per_s) affiancate — mai in sostituzione — alle colonne originali, più un `schema_report` con presenza/conversione/percentuale non-mancante per colonna. Verificato che i 4 schemi reali (42/43/44/5 colonne) usano **la stessa spelling** per i campi condivisi — non serve un mapping nome-per-nome, solo rilevamento di presenza/assenza (i file a 5 colonne hanno solo `timestamp_raw, latitude, longitude, altitude_m, temperature_c` presenti; tutto il resto è NA, mai un valore inventato). `pd.read_csv(..., na_values=["-"])` sostituisce la conversione manuale sparsa nei singoli moduli. Testato con un file reale per ciascuno dei 4 schemi (`tests/test_schema.py`). `missing_required_fields()` è il punto di estensione per `MISSING_REQUIRED_FIELD`; in pratica, la degradazione "campo mancante → non valutabile" è già ottenuta in modo capillare da `speed_evidence_class` (`DEVICE_ONLY`/`GPS_ONLY`/`NEITHER_AVAILABLE`) e `ventilation_evidence_class` (`NOT_ASSESSABLE`), non da un meccanismo generico separato.

`{stem}_schema_report.csv` è ora scritto per ogni campagna in output.

## D. Nuova gestione della cadenza

`time_qc.py::estimate_expected_sampling_interval_s()`: mediana dei `dt_s` positivi e finiti, poi ricalcolata escludendo valori oltre `time.outlier_multiplier` (default 8×) la prima mediana — esclude i gap prima di stimare la cadenza "normale". Fallback a `time.fallback_expected_dt_s` (1.0s) sotto `time.min_samples_for_cadence_estimate` (20) campioni puliti — riproduce esattamente la soglia storica 2.0s sui fixture sintetici esistenti (verificato).

Verificato sui dati reali: 32/39 file hanno cadenza mediana nativa 1.0s, 7/39 hanno cadenza mediana 2.0s — la pipeline ora si adatta correttamente a entrambe (test dedicati a 1s e 2s per `time_qc`, `stabilization`, `ventilation_qc`).

## E. Segmentazione e gap

`qc_sampling_gap_short` (avviso, non esclude) e `qc_sampling_gap_long` (chiude il segmento) derivano dalla cadenza stimata (`time.gap_short_multiplier`/`gap_long_multiplier`, pavimento assoluto `time.gap_absolute_floor_s`). `qc_segment_break`/`segment_id` invariati nel meccanismo (cumsum), ora adattivi. `segment_start_reason`/`segment_end_reason` (vocabolario: `campaign_start`, `long_gap`, `nonpositive_dt`, `campaign_end`) registrati per ogni riga.

**Regola verificata**: un gap non invalida i punti validi ai due lati; nessuna interpolazione; nessun collegamento spaziale artificiale attraverso il gap (i calcoli cinematici in `gps_qc.py` sono gated esclusivamente su `segment_id[i] == segment_id[i-1]`).

**Caso di regressione esplicito** (`tests/test_regression_real_data.py::test_bologna_ravenna_long_gap_regression`, dati reali, non sintetici): la campagna 06-04 Bologna–Ravenna produce **≥2 segmenti**, il gap (>2000s) viene riconosciuto, i punti validi sono conservati su entrambi i lati, e la durata osservata (somma delle durate per-segmento) resta distinta dalla durata nominale start-end per più di 2000 secondi — verificato via assert diretti sui dati reali, non su un fixture sintetico.

## F. Confronto tra velocità device e GPS

Colonne parallele mai fuse: `speed_device_kmh`, `speed_gps_kmh`, `speed_device_valid`, `speed_gps_valid`, `speed_difference_kmh`, `speed_ratio` (solo quando `speed_gps_kmh` > 1 km/h), `speed_evidence_class` (6 valori: `BOTH_AVAILABLE_CONSISTENT`, `BOTH_AVAILABLE_DISAGREE`, `DEVICE_ONLY`, `GPS_ONLY`, `NEITHER_AVAILABLE`, `NOT_EVALUABLE_AFTER_GAP`), `qc_speed_disagreement` (ridefinito su questo confronto — la vecchia formula, che confrontava la sola velocità GPS con `max_speed_kmh_absolute`, è migrata sotto il nuovo nome `qc_unrealistic_speed`). Soglie di disaccordo configurabili (`gps.speed_disagreement_abs_kmh`/`rel_fraction`), `engineering_default` — non ancora sottoposte a sensitivity analysis dedicata (l'audit aveva trovato correlazione tra le due velocità da -0.056 a 0.96 tra campagne, quindi nessun valore singolo è ovviamente giustificato).

## G. Gestione della soglia di 7 km/h

`ventilation_qc.py::detect_low_speed_and_ventilation()`. `ventilation.low_speed_threshold_kmh = 7.0` è l'**unica soglia di questa implementazione esplicitamente supportata dal testo della tesi** (`config/threshold_provenance.csv`, `evidence_source=thesis_documented`). Trattata come evidenza di rischio ventilazione/RECS, non come regola di esclusione termica automatica: `qc_low_speed_device`/`qc_low_speed_gps` sono segnali grezzi (`INFO_ONLY`), `qc_low_ventilation_possible` è un flag di rischio (`EXCLUDE_RESTRICTIVE` — mai esclusivo per permissive/recommended). `ventilation_evidence_class` distingue esplicitamente i 7 casi richiesti (incluse le discordanze device/GPS). `local_hour_bucket` (giorno/notte, ora civile 7:00–20:00, esplicitamente **non** alba/tramonto solare) e `radiation_context` (split mediano relativo alla singola campagna, mai soglia assoluta — l'audit non ha trovato un'unità dichiarata per `Radiation[]` né una popolazione uniforme) forniscono contesto opzionale, mai obbligatorio per i flag principali.

## H. Nuova stabilizzazione iniziale

Vedi anche sezione B.2. Ricerca a finestra iniziale per segmento: cerca la prima finestra continua di `warmup.min_stable_seconds` secondi reali sotto `warmup.slope_threshold_c_per_s`, con un gate di ventilazione opzionale (quando `speed_kmh` è fornito) soddisfatto da **una qualunque** finestra di `warmup.min_ventilated_duration_s` secondi in precedenza nel segmento — non richiesto di coincidere riga per riga con la finestra di stabilità termica (correzione fatta durante l'implementazione: la prima versione richiedeva coincidenza riga-per-riga, che su percorsi urbani con soste frequenti impediva quasi sempre la convergenza; vedi sezione P).

Una volta raggiunta la stabilità, il flag diventa `False` e **non si riattiva più** in quel segmento. Solo il primo segmento del file riceve `qc_sensor_stabilization`; ogni segmento successivo (dopo un gap) riceve invece `qc_segment_restart_recovery`, dallo stesso algoritmo. Se la stabilità non viene mai confermata, la finestra è tagliata a `warmup.max_window_s` (300s) e marcata `STABILIZATION_NOT_REACHED`; se il segmento è troppo corto per essere valutato, `segment_too_short` — mai un fallimento della pipeline.

**Verifica su dati reali** (campagna 06-20 12:48:24, 2834 righe): dopo il fix, `qc_sensor_stabilization` è flaggato su righe 0–230, contiguo, mai riattivato. `stabilization_window_end_reason`: 843 righe `slope_confirmed_stable`, 1985 `STABILIZATION_NOT_REACHED`, 6 `segment_too_short` — la campagna con più soste non converge sempre entro il tetto di sicurezza (vedi sezione P, rischio residuo).

## I. Gestione di soste e recovery

`ventilation_qc.py::detect_stop_events()`. `qc_stationary` (calcolato in `gps_qc.py`, riutilizzato qui) raggruppato in episodi; `qc_stop_event` quando la durata reale dell'episodio ≥ `stops.min_significant_stop_s`; `stop_event_id`, `stop_duration_s` (tempo reale, mai conteggio righe). `qc_post_stop_recovery` inizia subito dopo un episodio significativo e termina quando la velocità (affidabile) è rimasta continuamente sopra `ventilation.low_speed_threshold_kmh` per `stops.recovery_min_duration_s`, senza nuova sosta né gap nel mezzo — verificato funzionante sia a cadenza 1s sia 2s (`tests/test_ventilation_qc.py`).

**Sensitivity sul tempo di recupero** (`outputs/sensitivity/sensitivity_recovery_duration_sweep.csv`, 15/30/60s come esplicitamente suggerito nel Prompt 2 originale, mappato 1:1 sui 3 profili): quota media di righe in recovery cresce da 2.25% (15s) a 3.82% (30s) a 6.02% (60s); caso peggiore da 11.4% a 33.5%. Nessuna configurazione scelta automaticamente come "migliore" — restano i 3 valori per profilo.

## J. Freeze e salti GNSS

`qc_coord_repeated`: da uguaglianza esatta in floating point a tolleranza geodetica (`gps.coord_repeated_tolerance_m`, 1–3m secondo profilo). `qc_possible_gps_freeze` resta permissivo (blocco ripetuto + velocità device non chiaramente bassa). `qc_gps_freeze` richiede evidenza più forte: blocco ripetuto **e** entrambe le velocità disponibili sotto soglia (`gps.freeze_speed_threshold_kmh=0.5`, ora esposta in YAML, prima hardcoded). Segnale di supporto diagnostico (non vincolante) `gps_freeze_meteo_still_varying`: se la temperatura continua a variare durante il blocco, è più probabile un vero stop con sensore vivo che un freeze del solo chip GNSS — esposto come colonna separata, non piega il flag booleano (test dedicato che dimostra lo stesso `qc_gps_freeze` con temperatura statica vs variabile, e il segnale diagnostico che li distingue correttamente).

`qc_isolated_position_outlier` (nuovo): test a 3 punti, eccesso di distanza andata+ritorno (`dist(i-1,i)+dist(i,i+1)-dist(i-1,i+1)`) oltre `gps.isolated_outlier_excess_m`, ristretto a triplette nello stesso segmento. `qc_spatial_jump = qc_gps_jump | qc_isolated_position_outlier` è l'unico flag che porta severità (evita il doppio conteggio dello stesso evento sotto due nomi). Verificato: un salto isolato con rientro immediato viene rilevato anche quando la soglia di distanza/tempo grezza (`qc_gps_jump`) da sola non lo catturerebbe; un vero angolo di strada a 90° (nessun rientro, il percorso continua nella nuova direzione) non viene confuso con un salto quando la soglia è impostata sopra l'eccesso geometrico intrinseco del solo angolo (~74m nel caso di test, contro ~1037m di un vero rientro di ampiezza comparabile) — la distinzione è quindi una questione di soglia, non di algoritmo perfetto (limite riconosciuto, sezione P).

## K. Anomalie termoigrometriche

`qc_temp_isolated_spike` (mediana mobile/MAD, finestra/moltiplicatore/floor ora config-driven in secondi — default che riproducono esattamente i numeri storici hardcoded: finestra 5, 3×MAD, floor 0.2°C, verificato sui test esistenti). `qc_temp_rate_anomaly`: soglia di rate (`thermal.rate_anomaly_threshold_c_per_s`, valori 0.15/0.25/0.35 per profilo, informati dalla distribuzione reale trovata nell'audit: p99 per-campagna 0.09–0.40°C/s, mediana 0.20), **de-escalato automaticamente** quando il rate elevato persiste ≥ `thermal.rate_anomaly_persistence_s` (20s) — un gradiente reale sostenuto (attraversamento di un microclima urbano diverso) non è più marcato come errore, per l'intera durata del run, non solo il suo inizio. `qc_sensor_plateau_possible`: nuovo, `WARNING_ONLY` sempre, perché non esiste nello schema raw un secondo canale di temperatura indipendente per confermarlo.

## L. Nuova matrice flag × keep

`config/flag_policy.csv` (39 flag, azione esatta dal vocabolario della specifica: `INFO_ONLY | WARNING_ONLY | EXCLUDE_RECOMMENDED | EXCLUDE_RESTRICTIVE | EXCLUDE_ALL_SCIENTIFIC | SEGMENT_BREAK | NOT_APPLICABLE`). Semantica ordinale: `EXCLUDE_RECOMMENDED` esclude da recommended e restrictive; `EXCLUDE_RESTRICTIVE` solo da restrictive; `EXCLUDE_ALL_SCIENTIFIC` sempre. Principi applicati: valori fisicamente impossibili → `EXCLUDE_ALL_SCIENTIFIC`; gap lungo → `SEGMENT_BREAK` (non esclude i punti circostanti); bassa velocità → `INFO_ONLY`; ventilazione bassa possibile → `EXCLUDE_RESTRICTIVE` (mai automatica su recommended); freeze confermato → `EXCLUDE_RECOMMENDED` (dopo verifica quantitativa sui dati reali, sezione N); stabilizzazione iniziale → `EXCLUDE_RECOMMENDED` solo nella finestra corretta; spike isolato confermato → `EXCLUDE_RECOMMENDED`; plateau → `WARNING_ONLY`.

`src/meteotracker_qc/policy.py::apply_flag_policy()` costruisce, per ogni riga: `qc_severity`/`qc_exclusion_reasons`/`qc_primary_reason`/`qc_reason_count` (sul profilo effettivamente in esecuzione — vedi limite architetturale sotto), più una **proiezione** a flag-values-fissi per tutti e 3 i profili (`qc_severity_{permissive,recommended,restrictive}`, `qc_exclusion_reasons_{...}`, `keep_{...}`). `qc_warning_count`/`qc_warning_reasons` per i flag attivi ma non esclusivi nel profilo corrente. `keep_strict`/`keep_relaxed` restano come alias legacy (stesso meccanismo a budget di severità, ora alimentato dalla severità più ricca).

**Limite architetturale importante, verificato empiricamente** (sezione N): `qc_severity_<profilo>`/`keep_<profilo>` sono una *proiezione solo-policy* — permissive/recommended/restrictive differiscono in questo codice in due modi: (1) quali flag sono `True`, perché le soglie sottostanti (es. `gps.gps_jump_distance_m`) variano per YAML di profilo, e (2) quale azione un flag `True` innesca (questa tabella, condivisa dai 3 YAML). La proiezione ricalcola solo la dimensione (2) sui flag già calcolati da QUESTA run; non può retroattivamente tenere conto della (1). Confermato sui dati reali: la proiezione "restrictive" su una run recommended stima 43.8% di righe tenute; la run restrictive VERA (soglie proprie) ne tiene solo 37.6% — la differenza è interamente dovuta alla dimensione (1), non catturata dalla proiezione. Le tre cartelle `outputs/{permissive,recommended,restrictive}/` (run reali indipendenti) restano l'unica fonte autorevole per un confronto tra profili corretto.

## M. Risultati della sensitivity analysis

`scripts/run_sensitivity.py`, due parti:

1. **Confronto tra profili** (run reali, non proiezioni) — `outputs/sensitivity/sensitivity_profile_comparison_v2.csv`, 34 campagne. Totali sulle 34 campagne canoniche (48.173 righe):

| Profilo | Righe tenute | % |
|---|---:|---:|
| permissive | 48.173 | 100.0% |
| recommended | 38.126 | 79.1% |
| restrictive | 18.121 | 37.6% |

2. **Sweep isolato `stops.recovery_min_duration_s`** (15/30/60s, altri parametri fissi a recommended) — vedi sezione I.

Nessuna soglia è stata selezionata automaticamente in base a quanti dati elimina, come richiesto.

## N. Impatto sulle 34 campagne canoniche

Run reale completo (recommended), confrontato con il comportamento intenzionale della nuova policy:

- **keep_relaxed**: 47.592/48.173 (98.79%) — leggermente inferiore al valore storico (99.99%, con la severità a 4 flag). **Non è una regressione**: `qc_gps_freeze` ora contribuisce alla severità (prima veniva calcolato e ignorato), quindi righe di freeze reale ora vengono correttamente segnalate dove prima passavano inosservate.
- **keep_strict = keep_recommended** (severità recommended ≤ 0): 79.14%. I due flag che guidano la maggior parte delle esclusioni: `qc_gps_freeze` (10.05% delle righe) e `qc_sensor_stabilization` (11.83% delle righe).
- **Campagne più colpite** (per `keep_recommended` più basso): due campagne molto brevi (`04-27 07:28:18`, 21 righe/29s; `07-04 2025 moto 09:31:26`, 91 righe/122s) risultano **0% keep_recommended** — l'intera campagna è troppo corta per confermare la stabilizzazione (`segment_too_short`, marcata interamente instabile). La campagna `02-20 09:05:04` (536 righe, **18 segmenti** — frammentazione già segnalata nell'audit come possibile perdita Bluetooth) ha keep_recommended 33.2%, con il 50.6% delle righe in `qc_segment_restart_recovery`.
- **Nessuna perdita/duplicazione di righe**: somma `n_raw` su tutte le 34 campagne = 48.173, identico al totale storico.

## O. Test eseguiti

`pytest -q -W error`: **99 passed, 0 warning, 0 failure** (partiti da 29; escludendo i 14 test del modulo concorrente `repeated_routes` non toccato da questa sessione, il conteggio proprio di questa implementazione è 29→85 nuovi/modificati). Nuovi file di test: `test_schema.py` (5), `test_config_provenance.py` (7), `test_regression_real_data.py` (1, dati reali), `test_ventilation_qc.py` (7); estesi: `test_time_qc.py` (+11), `test_gps_qc.py` (+10), `test_meteo_qc.py` (+7), `test_stabilization.py` (+8). Gate ripetuto ad ogni milestone (M1–M8), sempre verde.

## P. Rischi residui

1. **`warmup.max_window_s` (300s) troppo generoso per campagne brevi**: le due campagne < 130s vengono interamente flaggate come "mai stabilizzate", risultando 0% keep_recommended. Sono probabilmente sessioni di test/interruzione (già segnalate come tali nell'audit), ma il comportamento andrebbe rivisto con un cap relativo alla durata della campagna, non un valore assoluto fisso.
2. **Nessuna soglia di questa implementazione (eccetto i 7 km/h) è stata sottoposta a una vera sensitivity analysis multi-valore sui dati reali** — la maggior parte resta `engineering_default`, con valori scelti per riprodurre il comportamento storico dove esisteva un precedente, o stimati in modo grossolano dove non esisteva. `config/threshold_provenance.csv` documenta esplicitamente quali (colonna `sensitivity_values = "not yet swept"`).
3. **Il test di outlier isolato a 3 punti non distingue perfettamente un angolo di strada reale da un errore**, per costruzione geometrica (entrambi producono un eccesso di distanza diverso da zero) — la distinzione dipende dalla soglia configurata, non da un algoritmo che guarda "oltre" la tripletta immediata.
4. **`qc_gps_freeze` a `EXCLUDE_RECOMMENDED`** tocca il 10.05% delle righe in aggregato (fino al 20.9% nella campagna peggiore, già noto dall'audit) — non ridotto a `EXCLUDE_RESTRICTIVE` in questa fase perché la percentuale aggregata non è apparsa eccessiva, ma resta una decisione rivedibile.
5. **`qc_sensor_plateau_possible` non ha modo di essere confermato**: nessun secondo canale di temperatura esiste nello schema raw per distinguere un plateau reale (microclima stabile) da un sensore bloccato.
6. **La proiezione `qc_severity_<profilo>`/`keep_<profilo>` in una singola run non equivale a una run reale con quel profilo** (sezione L) — rischio di uso improprio se un consumatore a valle scambia la proiezione per il vero output multi-profilo.
7. **Il gate di ventilazione nella ricerca di stabilizzazione richiede "una qualunque finestra precedente" di ventilazione adeguata, non l'ultima**: in teoria una finestra di ventilazione molto precoce e poi mai più ripetuta potrebbe soddisfare il gate anche se la ventilazione è peggiorata da allora. Comportamento accettato come ragionevole compromesso (vedi correzione in sezione H) ma non validato oltre gli scenari di test.
8. **`inventory.py`** (soglia gap `>2` hardcoded indipendente, loop di distanza non vettorizzato) non è stato toccato in questa fase — resta un'inconsistenza residua rispetto al resto della pipeline, segnalata ma non nello scope di questo prompt.

## Q. Decisioni rinviate alla fase di session QC

- Classificazione finale di sessione (PASS/PASS_WITH_WARNINGS/PARTIAL/REJECT) — esplicitamente esclusa da questa fase.
- Correzione della deriva termica (detrending, confronto ripassaggi) — esplicitamente esclusa.
- Integrazione Netatmo — esplicitamente esclusa.
- Map-matching OSM obbligatorio — `qc_off_network_possible` resta uno stub informativo (`pd.NA` sempre), nessuna chiamata di rete.
- Se e come rivedere `warmup.max_window_s` per le campagne brevi (rischio residuo 1).
- Se e quando eseguire la sensitivity analysis multi-valore completa sulle soglie ancora `not yet swept` (rischio residuo 2).

---

## Riepilogo file

**Modificati**: `.gitignore`, `config/qc_{permissive,recommended,restrictive}.yaml`, `reports/QC_Methodology.md`, `src/meteotracker_qc/{gps_qc,meteo_qc,pipeline,stabilization,time_qc}.py`, `tests/test_{gps_qc,meteo_qc,stabilization,time_qc}.py`.

**Nuovi**: `config/{flag_policy,threshold_provenance}.csv`, `scripts/run_sensitivity.py`, `src/meteotracker_qc/{policy,schema,ventilation_qc}.py`, `tests/test_{config_provenance,regression_real_data,schema,ventilation_qc}.py`, `outputs/{permissive,restrictive}/` (nuovi alberi output), `outputs/recommended/` (rigenerato), `outputs/qc_v2/{qc_policy_matrix,campaign_qc_impact}.csv`, `outputs/sensitivity/sensitivity_{profile_comparison_v2,recovery_duration_sweep}.csv`, questo report.

**Non toccati** (lavoro concorrente di un'altra sessione, verificato non sovrapposto): `src/meteotracker_qc/repeated_routes/`, `config/repeated_routes_recommended.yaml`, `reports/repeated_routes_phase1.md`, `tests/test_repeated_routes.py`, `requirements.txt` (già modificato da quella sessione prima dell'inizio di questa).

Nessun commit creato. Nessuna modifica a `data/raw/`.
