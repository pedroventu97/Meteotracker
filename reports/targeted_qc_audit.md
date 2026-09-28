# Audit tecnico-scientifico mirato della pipeline QC MeteoTracker

Data audit: 2026-07-30
Branch: `main` (working tree con `README.md` modificato e `INTEGRATION_GUIDE.md` non tracciato, preesistenti all'audit — vedi nota in fondo)
Ambito: **solo audit**. Nessuna regola di esclusione è stata implementata, nessun CSV raw è stato modificato, nessun commit è stato creato.

Output prodotti da questo audit:
- `outputs/audit/csv_schema_inventory.csv` (1517 righe: 39 file × colonne realmente presenti in ciascuno)
- `outputs/audit/campaign_sampling_inventory.csv` (39 righe: una per CSV raw, incluse le 5 copie ridondanti già note)
- `outputs/audit/current_flag_inventory.csv` (28 righe: ogni flag/colonna QC oggi calcolata dal codice)
- `outputs/audit/threshold_candidates.csv` (13 righe: ogni soglia candidata, classificata per origine dell'evidenza)

---

## Baseline eseguita

| Verifica | Comando | Risultato |
|---|---|---|
| Suite di test | `.venv\Scripts\python.exe -m pytest -q -W error` | **29 passed, 0 warning, 0 failure** |
| CSV raw presenti | `data/raw/**/*.csv` | **39 file**, invariato rispetto al manifest esistente |
| Campagne canoniche | `data/manifests/campaign_manifest.csv` | **34 canoniche + 5 ridondanti** (1 byte-identica, 4 re-export a colonne ridotte) — coerente con `reports/Meteotracker_QC_Audit_Report.md` |
| Output `recommended` già presenti | `outputs/recommended/` | 34 cartelle campagna + `inventory.csv`, generate dall'ultima run registrata in `logs/latest_qc_run.log` (2026-07-25, 48.173 righe totali, 99.99% keep relaxed, 92.11% satellite-usable) |
| Sensitivity già presente | `outputs/sensitivity/` | 3 CSV per-profilo + 1 comparativo, già esistenti e non ricalcolati in questo audit |

Non è stata rieseguita `run_qc.py`: l'audit ha letto **solo i CSV raw** e il codice sorgente, per evitare qualunque dipendenza dagli output già scritti (che riflettono la logica attuale, non necessariamente corretta — vedi sezione C).

---

## A. Architettura corrente

Pipeline in `src/meteotracker_qc/`, orchestrata da `pipeline.py::MeteotrackerQC.process_file()` e da `run_qc()`:

1. **Ingresso raw** (`pipeline.py:74-78`): `pd.read_csv` diretto sul CSV originale, senza normalizzazione dei separatori decimali/mancanti a monte — la conversione `"-"` → mancante avviene colonna per colonna, più a valle, tramite `pd.to_numeric(..., errors="coerce")` in ciascun modulo QC. Vengono aggiunte `source_file`, `source_row`, `device_id` (euristico da nome file), `campaign_id` (stem del file).
2. **QC temporale** (`time_qc.py::detect_time_issues`): parsing esplicito (`format="mixed"`), classificazione timezone, `dt_s`, `qc_time_gap` (soglia 2.0s **hardcoded**), `qc_new_segment`/`segment_id`.
3. **QC GPS** (`gps_qc.py::detect_gps_issues`): distanza geodetica passo-passo (pyproj `Geod.inv`, WGS84), velocità e accelerazione ricalcolate, `qc_gps_jump` (config-driven), `qc_coord_repeated`, `qc_possible_gps_freeze`/`qc_gps_freeze` (soglia velocità 0.5 km/h **hardcoded**, non in YAML).
4. **QC meteorologico** (`meteo_qc.py::detect_meteo_issues`): limiti fisici assoluti (config-driven ma identici sui 3 profili) e test di spike isolato via mediana/MAD mobile (finestra/molteplicatore/floor **hardcoded**).
5. **Stabilizzazione sensore** (`stabilization.py::detect_sensor_stabilization`): test di pendenza su mediana mobile della temperatura.
6. **Variabili derivate** (`derived_variables.py`): dew point (Magnus) e temperatura potenziale ricalcolati, confrontati con i valori esportati dal device.
7. **Classificazione di eleggibilità** (`pipeline.py:86-118`): `qc_severity` (somma di **solo 4** flag), `keep_strict`/`keep_relaxed` (mai distruttivo — scrive sempre `_flagged.csv` completo più `_strict.csv`/`_relaxed.csv` come sottoinsiemi), più i flag composti `gps_valid`, `use_for_route_mapping`, `use_for_spatial_aggregation`, `use_for_satellite_comparison`.
8. **Output**: parquet standardizzato, 3 CSV (flagged/strict/relaxed), `config_used.yaml`, `metrics.json`, `report.md`, 2 PNG diagnostici, per ogni campagna sotto una cartella con hash univoco (`_campaign_output_dir`, SHA1 del path relativo — risolve la collisione di cartelle documentata nell'audit storico).

Tre profili in `config/qc_{permissive,recommended,restrictive}.yaml`: differiscono nominalmente su `gps.*`, `warmup.*`, `filtering.*`; **in pratica** (vedi C) solo `gps.gps_jump_distance_m/dt_s` e `warmup.slope_threshold_c_per_s` incidono davvero sull'output, perché sono gli unici due parametri configurabili che alimentano `qc_severity`.

Gestione duplicati: `run_qc.py` esclude di default i 5 file marcati `exclude_from_analysis=True` nel manifest (34 campagne canoniche); `--include-all-files` riprocessa tutti e 39. **Nessun file raw viene mai cancellato.**

---

## B. Comportamento reale dei CSV

Verificato leggendo tutti i 39 file raw (non assunto dalla documentazione).

### Schema — 4 varianti di colonne, non 1

| Varianti | N. file | Colonne | Note |
|---|---|---|---|
| 42 colonne | 17 | set base | file di Feb-Mar + 07-04 moto |
| 43 colonne | 9 | base + `level[m]` | file 04-27/05-19/05-27 |
| 44 colonne | 9 | base + `Twat[°C]` + `level[m]` | file 06-04/06-20 |
| 5 colonne | 4 | `Time,Lat,Lon,Alt[m],Temp[°C]` | **tutti e 4 sono le copie ridondanti già note dal manifest** (re-export a colonne ridotte) |

`level[m]` e `Twat[°C]` sono presenti come intestazione ma **sempre vuote** (0/18 e 0/9 file con dati) — canali per sensori acqua mai installati su rilievi terrestri.

### Colonne mappate sulla lista richiesta (attività 4)

| Richiesto | Colonna reale | Copertura |
|---|---|---|
| timestamp | `Time` (ISO8601 con offset esplicito) | 39/39, 100% popolata |
| lat/lon | `Lat`, `Lon` | 39/39, 100% popolata |
| temperatura | `Temp[°C]` | 39/39, 100% popolata |
| umidità | `Hum[%]` | 35/39 (assente solo nei 4 export a 5 colonne) |
| pressione | `Press[mbar]` | 35/39 |
| quota | `Alt[m]` | 39/39 |
| velocità | `Speed[km/h]` | 35/39 (assente nei 5-colonne) |
| distanza | **non esportata** — nessuna colonna distanza cumulata o step | va sempre ricalcolata da lat/lon |
| temperatura corretta/non corretta | **non esistono due campi distinti** — `Temp[°C]` è l'unico campo aria; `Tir[°C]`/`Tsur[°C]` esistono come intestazione ma sono **100% vuoti in tutti i 35 file che li hanno** (0/35) | nessuna correzione RECS è esportata dal device |
| stato RECS | **non esiste alcuna colonna di stato RECS/ventilazione** | confermato: nessuna colonna nel dataset codifica "sotto soglia ventilazione" o "correzione applicata" |
| indicatore radiazione solare | `Radiation[]` (adimensionale, nessuna unità dichiarata nell'header) | presente in 35/39 file ma popolata solo nel **52.4%** delle righe in media (range 0%-97.4% per file); nei file di febbraio è quasi sempre `-`, nei file di giugno è popolata >90% delle righe — comportamento non uniforme nel tempo, non un semplice "device non equipaggiato" |
| campi qualità/stato dispositivo | `BT[dBm]` (RSSI Bluetooth, 100% popolato quando presente, mediana tra -40 e -61 dBm secondo file), `ext voltage[mV]`/`batt voltage[mV]` (sempre vuoti, 0/35) | nessun campo booleano/enum di "qualità dato" o "verde/stabilizzato" |
| sensori aggiuntivi mai popolati | `CO2[ppm]`, `EAQ[]`, `FAQ[]`, `O3[ppb]`, `CO[ppm]`, `SO2[ppb]`, `NO2[ppb]`, `AQI[]`, tutti i canali PM | popolati in **2 soli file su 39** (`04-27/…08_00_36…`, `04-27/…08_38_02…`), e anche lì solo per 6 righe su >700 — rumore residuo, non un vero payload aria-qualità |

### Velocità: origine e comportamento

- `Speed[km/h]` è un campo **esportato dal device**, non ricalcolabile in modo affidabile solo dal nome colonna: è stato messo a confronto con una velocità ricalcolata indipendentemente da lat/lon/tempo (geodetica pyproj, solo su coppie con `dt≤2s`).
- La correlazione tra velocità dichiarata e velocità ricalcolata **varia enormemente tra campagne**: da **-0.056** (02-13 mattina) a **0.96** (02-28 mattina), mediana intorno a 0.75-0.80. Le 3 campagne con correlazione negativa o quasi nulla sono tutte rilievi urbani a bassa velocità del device di febbraio (B6CCF894…), con alta incidenza di coordinate ripetute (12-16% delle righe) — compatibile con rumore GPS (multipath urbano) che decorrela una velocità istantanea a 1Hz da una velocità probabilmente filtrata/smussata internamente dal device. **Conclusione operativa: `Speed[km/h]` non va trattato come intercambiabile con la velocità ricalcolata da GPS — sono due segnali con comportamento diverso a seconda della qualità del fix, e nessuno dei due è uniformemente più affidabile.**
- I punti sotto 7 km/h **sono presenti e non marcati**: mediana 22.6% delle righe per campagna (range 2.3%-100%), nessuna colonna indica se il device li corregge, li esclude dalle medie o li lascia tali e quali. Il campo derivato del device `HDX[°C]` non mostra alcuna discontinuità sistematica attorno a 7 km/h che suggerisca una correzione già applicata (verifica qualitativa, non quantificata in questo audit).
- Il campo device `delta Temp[°C/sec]` correla fortemente (0.78-0.996, tranne un file da 21 righe) con la derivata ricalcolata indipendentemente — **conferma che è una derivata grezza per-campione, non già corretta per RECS.**

### Frequenza di campionamento: non uniformemente 1 Hz

- 32/39 file hanno `dt` mediano = 1.0s; **7/39 hanno `dt` mediano = 2.0s** (04-27 due file + relative copie in "04-27 moto", 05-27 due file, 06-20 un file).
- Il gruppo a 2s non è isolabile per device o tipo di veicolo: appartiene allo stesso device (`AC4D162B317E`) di molte campagne a 1s, e include sia rilievi in moto sia in auto/bici.
- Verificato empiricamente che la soglia hardcoded `dt_s > 2.0` **non** genera falsi gap sistematici sulle campagne a cadenza 2s (0% dei passi nativi cade nell'intervallo (2.0, 2.5]) — il valore è sempre esattamente 2.0, non 2.0+jitter.
- **Non è possibile, dal solo CSV esportato, distinguere una cadenza nativa a 2s (impostazione "minimal distance" o simile) da un dimezzamento silenzioso del data rate per perdita pacchetti Bluetooth**: non esiste un numero di sequenza o un contatore di pacchetti nel CSV.

### Interruzioni Bluetooth: visibili solo come gap temporali

- `BT[dBm]` è popolato al 100% nelle righe effettivamente scritte — **non scende mai a mancante prima di un gap**, perché durante l'interruzione semplicemente non viene scritta alcuna riga. Il segnale RSSI da solo non permette quindi di **prevedere** un'interruzione imminente in questo dataset (nessuna riga con RSSI anomalo appena prima di un gap è stata osservata nei casi controllati manualmente).
- Le interruzioni sono però ben visibili come gap: la campagna `06-04/20260604T11_40_32_..._Bologna-Ravenna.csv` ha un singolo gap di **2469 secondi (41 minuti)** dentro una sessione di 4597s nominali — **l'84% della durata nominale della sessione è "buco"**. Altri casi rilevanti: `02-20/…09_05_04…` (78.9% perso, gap massimo 591s), `05-19` (entrambe le copie, 45.5% perso, gap massimo 1237s), `02-28/…09_08_22…` (53.7% perso).
- Questi sono con ogni probabilità gli stessi casi descritti qualitativamente nella tesi come "sessioni quasi completamente perse per problemi Bluetooth" — ma **oggi non esiste alcuna regola di codice che li isoli a livello di sessione** (vedi E).

---

## C. Limiti della pipeline attuale (verificati nel codice, non presunti)

Il fatto più rilevante di questo audit: **la maggior parte dei flag QC calcolati non influisce sull'output filtrato.** Solo 4 flag su ~20 alimentano `qc_severity` (quindi `keep_strict`/`keep_relaxed`): `qc_time_gap`, `qc_gps_jump`, `qc_temp_spike`, `qc_sensor_stabilization`. Dettaglio completo in `outputs/audit/current_flag_inventory.csv`; punti salienti:

1. **`qc_gps_freeze` non entra in `qc_severity`.** Entra in `gps_valid` (quindi esclude da route-mapping/spatial-aggregation/satellite-comparison) ma **non** da `keep_strict.csv`/`keep_relaxed.csv`, i due output documentati come uso generale. Sui dati reali, il freeze confermato tocca una mediana del 3.8% e fino al 20.9% delle righe per campagna — non è un caso limite.
2. **`qc_temp_impossible`/`qc_humidity_impossible`/`qc_pressure_impossible` sono calcolati e mai usati.** Un valore fisicamente impossibile (es. -100°C) verrebbe flaggato ma **non escluso da nulla**. Questo è il gap più semplice da chiudere: i limiti fisici sono già configurati, manca solo di collegare i tre flag a `qc_severity`.
3. **`qc_speed_disagreement` e `qc_impossible_acceleration` sono completamente morti**, nonostante i relativi parametri (`max_speed_kmh_absolute`, `acceleration_ms2_abs`) varino nominalmente nei 3 profili YAML — cambiare quei valori oggi non ha **alcun effetto misurabile** su nessun output.
4. **Bug confermato in `stabilization.py`:** `warmup.min_stable_seconds` viene letto dal config (riga 13) e mai più referenziato. È documentato in `reports/QC_Methodology.md` come parametro che varia per profilo (30/60/120s) ma **non fa nulla**.
5. **`qc_sensor_stabilization` non è un rilevatore di "avvio sessione".** Verificato su 3 campagne reali: su una campagna da 2834 righe, 130 punti sono flaggati e 127 di questi (98%) cadono **dopo** la riga 120 — il rilevatore di pendenza (mediana mobile centrata) si riattiva ovunque nel percorso ci sia una variazione locale di temperatura sufficientemente rapida (es. sole/ombra, sottopassi), non solo all'avvio. Questo non corrisponde al requisito della tesi ("esclusione di tratti iniziali").
6. **Soglia gap/segmento (2.0s) hardcoded**, non in YAML, identica sui 3 profili — conferma ed estende un finding già presente nell'audit storico (`reports/Meteotracker_QC_Audit_Report.md`, sezione Final Closure Checks) che aveva verificato solo il conteggio segmenti; qui si aggiunge la controprova diretta sulle campagne a cadenza 2s.
7. **Soglia spike di temperatura (finestra 5, moltiplicatore 3×MAD, floor 0.2°C) hardcoded**, non in YAML — di fatto solo 2 dei 4 componenti di `qc_severity` (`qc_gps_jump`, `qc_sensor_stabilization`) variano realmente tra permissive/recommended/restrictive.
8. **`qc_coord_missing` non esclude nulla**: righe con lat/lon mancanti possono risultare `gps_valid=True` perché il ciclo che calcola `qc_gps_freeze`/`qc_gps_jump` le salta semplicemente (restano `False` di default).
9. **`qc_coord_outside_aoi` è un segnaposto**: dichiarato, sempre `False`, nessuna logica di area-di-interesse implementata — coerente con l'indicazione di non usare OSM come verità assoluta, ma oggi significa che **non esiste alcun controllo di plausibilità geografica**, nemmeno approssimativo (es. bounding box regionale).
10. **`permissive` e `recommended` condividono le stesse soglie di filtro** (`strict_keep_threshold=0`, `relaxed_keep_threshold=1`): l'unica differenza reale tra questi due profili nominati è `gps_jump_distance_m/dt_s` e `warmup.slope_threshold_c_per_s`.

---

## D. Problemi già coperti (e verificati funzionanti)

- Preservazione della riga sorgente (`source_row`/`source_file`) attraverso l'intera pipeline — verificato da test dedicati (`test_pipeline_integrity.py`) e confermato dall'audit storico su tutte le 39 campagne.
- Parsing timestamp esplicito, senza inferenza silenziosa di formato (`format="mixed"`), con classificazione timezone (`explicit_offset` su tutte le 39 campagne, verificato in questo audit sul 100% delle righe `Time`).
- Rilevamento salti GPS (`qc_gps_jump`) e freeze GPS (`qc_gps_freeze`/`qc_possible_gps_freeze`) — logica distinta tra "ripetizione di coordinate" e "freeze confermato" (richiede anche velocità bassa), coperta da test mirati.
- Spike isolati di temperatura distinti da trend persistenti (test dedicato che verifica che un trend di 1°C/campione su 5 campioni **non** generi uno spike).
- Nessuna cancellazione distruttiva: ogni run scrive sempre il file `_flagged.csv` completo prima di derivare `_strict.csv`/`_relaxed.csv`.
- Gestione duplicati a livello di analisi (manifest), senza mai toccare i file raw.
- Collisione di cartelle di output (bug storico, 39 file → 38 cartelle) risolta con hashing del path relativo.

---

## E. Problemi non ancora coperti

1. **Nessun gate di qualità a livello di sessione.** La tesi esclude sessioni "quasi completamente perse"; il codice attuale non ha alcun concetto di campagna-livello, solo flag riga-per-riga. Le 4 campagne peggiori per `gap_ratio` (84%, 79%, 54%, 46%×2) non vengono segnalate diversamente da una campagna pulita nell'output attuale.
2. **Nessuna gestione esplicita della soglia 7 km/h / RECS.** Non è chiaro se debba diventare un flag di esclusione, un peso, o un input per una correzione radiativa a valle — la tesi la tratta come input di correzione, non come criterio di rimozione, e il codice oggi non fa nessuna delle due cose.
3. **Il rilevatore di stabilizzazione non è limitato all'avvio del tragitto** (vedi C.5) — va ridisegnato prima di essere ritarato.
4. **Flag meteorologici "impossibili" non collegati alla severità** — la correzione più semplice e a minor rischio di falsi positivi disponibile in questo audit (limiti fisici assoluti, non soglie soft).
5. **Nessun controllo di plausibilità geografica**, nemmeno un bounding box largo (Bologna + area metropolitana) come rete di sicurezza minima contro errori GNSS grossolani — coerente con l'indicazione di non usare OSM come verità assoluta, ma un controllo più debole (bbox, non rete stradale) non è stato scartato per una buona ragione tecnica, semplicemente non esiste.
6. **Ripetizione di coordinate testata per uguaglianza esatta in floating point**, non per prossimità entro una tolleranza — comportamento non discusso né in tesi né nella documentazione.
7. **Nessuna verifica di continuità del device/BT** oltre al gap temporale — `BT[dBm]` è presente e potenzialmente informativo (qualità del segnale) ma non è correlato oggi a nessun flag.
8. **Colonne morte non rimosse né documentate come tali** (`qc_temp_suspect`/`qc_humidity_suspect`/`qc_pressure_suspect` sempre `False`, `qc_coord_outside_aoi` sempre `False`) — rischio concreto che un futuro utilizzatore le scambi per segnali reali leggendo `_flagged.csv`.

---

## F. Soglie supportate da evidenze

| Soglia | Evidenza | Fonte |
|---|---|---|
| Timezone esplicito nei timestamp | 39/39 file, 100% delle righe con offset `±HH:MM` | verifica diretta su tutti i raw |
| Soglia gap 2.0s non genera falsi positivi sulle campagne a cadenza nativa 2s | 0% dei passi nativi in (2.0, 2.5] su 3 campagne campione | verifica diretta |
| Limiti fisici assoluti (-40/60°C, 0-100%, 850-1100 mbar) | valori standard di plausibilità meteorologica, coerenti con l'ordine di grandezza osservato in tutte le campagne (min/max reali ben dentro questi limiti) | `csv_schema_inventory.csv` |
| Correlazione device `delta Temp[°C/sec]` vs derivata ricalcolata | 0.78-0.996 su 33/35 campagne con la colonna disponibile | `campaign_sampling_inventory.csv` |
| Velocità massime reali fino a 151 km/h su rilievi in moto | `speed_reported_max_kmh` | `campaign_sampling_inventory.csv` — rilevante per non impostare un cutoff troppo aggressivo se `qc_speed_disagreement` verrà riattivato |

---

## G. Soglie ancora da decidere (richiedono sensitivity analysis o una decisione esplicita)

Elenco completo con evidenza dati in `outputs/audit/threshold_candidates.csv`. Le più rilevanti:

- **Soglia salto GPS** (distanza/tempo): oggi arbitraria, nessun supporto numerico né in tesi né nei dati diversamente da "sembra funzionare sui test".
- **Soglia velocità di freeze** (0.5 km/h, hardcoded): mai esposta a sensitivity analysis nonostante tocchi una quota rilevante di righe (fino al 21%).
- **Soglia 7 km/h**: politica da decidere (escludere / correggere / pesare), non solo un numero.
- **Finestra e pendenza di stabilizzazione**: da ridefinire come rilevatore "solo avvio" prima ancora di poter essere tarato.
- **Gate di completezza sessione**: nessun precedente in codice; `gap_ratio` mostra una distribuzione a coda pesante (mediana 1.4%, ma alcuni casi 45-84%) che si presta a un taglio, ma il valore esatto è una decisione, non un fatto.
- **Tolleranza di uguaglianza coordinate ripetute**: passare da uguaglianza esatta a una tolleranza in metri è ragionevole ma il valore va scelto con sensitivity analysis.

---

## H. Proposta di implementazione ordinata per priorità

**Non implementata in questa fase — solo elenco ordinato per la prossima.**

1. **(Correzione, rischio minimo)** Collegare `qc_temp_impossible`/`qc_humidity_impossible`/`qc_pressure_impossible` a `qc_severity`. Sono limiti fisici assoluti già configurati e testati; non richiedono una nuova decisione di soglia.
2. **(Correzione, rischio minimo)** Correggere il bug di `min_stable_seconds` non utilizzato in `stabilization.py`, oppure rimuovere il parametro se si decide di ridisegnare il rilevatore (punto 4).
3. **(Decisione + implementazione)** Decidere se e come `qc_gps_freeze` deve incidere su `keep_strict`/`keep_relaxed`, non solo su `gps_valid`.
4. **(Ridisegno)** Riprogettare `qc_sensor_stabilization` come rilevatore a finestra iniziale (solo le prime N righe/secondi dall'inizio segmento), coerente con la tesi, prima di ritarare la soglia di pendenza.
5. **(Nuova funzionalità)** Introdurre un gate di completezza a livello di sessione (`gap_ratio` o equivalente), con soglia da definire via sensitivity analysis, per intercettare le sessioni "quasi perse" descritte nella tesi.
6. **(Decisione di policy)** Definire esplicitamente il trattamento della soglia 7 km/h (esclusione vs correzione vs peso) prima di scrivere qualunque codice — è una decisione scientifica, non solo tecnica.
7. **(Esposizione a config)** Portare in YAML le soglie oggi hardcoded (gap/segmento 2.0s, spike finestra/moltiplicatore/floor, freeze 0.5 km/h) così da poterle davvero sottoporre a sensitivity analysis sui 3 profili.
8. **(Rete di sicurezza geografica)** Valutare un bounding box largo (non rete stradale OSM) come controllo minimo di plausibilità geografica, mantenendo la cautela richiesta su parchi/piazze/percorsi non mappati.
9. **(Pulizia)** Rimuovere o documentare esplicitamente come "non implementato" i flag segnaposto sempre `False` (`qc_coord_outside_aoi`, `qc_*_suspect`) per evitare interpretazioni errate.

---

## I. Rischi di falsi positivi e falsi negativi

**Falsi negativi (dati problematici che oggi passano `keep_strict`/`keep_relaxed`):**
- Righe con `qc_gps_freeze=True` (fino al 20.9% di una campagna) non vengono escluse da nessuno dei due CSV filtrati.
- Valori meteorologici fisicamente impossibili non vengono esclusi da nulla.
- Sessioni quasi completamente perse per gap Bluetooth (fino all'84% di durata persa) non ricevono alcun segnale di bassa qualità a livello di sessione — solo ispezionando `campaign_sampling_inventory.csv` o i gap individuali ci si accorge del problema.
- Righe con coordinate mancanti possono risultare `gps_valid=True`.

**Falsi positivi (rischi se le soglie venissero strette senza validazione):**
- Restringere `max_speed_kmh_absolute` (profilo restrictive: 120 km/h) senza verificarlo contro i dati reali flaggerebbe erroneamente segmenti autentici in moto (osservati fino a 151 km/h).
- Ritarare la soglia di pendenza di `qc_sensor_stabilization` senza prima limitarla a una finestra iniziale continuerebbe a flaggare transizioni termiche legittime a metà percorso (sole/ombra, sottopassi), indipendentemente dal valore scelto.
- Restringere la soglia di salto GPS senza tener conto della velocità reale del segmento rischia di penalizzare sistematicamente le campagne in moto, che hanno passi-distanza naturalmente più lunghi a parità di tempo.
- Introdurre una tolleranza di distanza troppo larga per "coordinate ripetute" rischia di confondere soste brevi e legittime (semafori, incroci) con veri freeze GNSS — la distribuzione osservata (mediana 10, massimo 29 righe consecutive ripetute) mostra che i due casi si sovrappongono nella durata e vanno distinti con un criterio di velocità aggiuntivo, non di sola posizione.
- Un gate di completezza a livello di sessione troppo aggressivo rischia di scartare campagne brevi ma pulite (es. `04-27/…07_28_18…`, 21 righe / 29 secondi — probabile test/interruzione volontaria, non necessariamente un problema di qualità del segnale).

---

## Nota su stato Git e file di contesto

- Branch: `main`. Nessun push/pull/reset/clean eseguito.
- `README.md` risultava già modificato (working tree) e `INTEGRATION_GUIDE.md` già presente come non tracciato **prima dell'inizio di questo audit** — nessuna di queste modifiche è stata toccata o generata da questo audit.
- Unici file scritti da questo audit: i 4 CSV in `outputs/audit/` e questo report in `reports/targeted_qc_audit.md`. Nessun file sotto `data/raw/` è stato letto in modalità scrittura né modificato.
- Nessun commit creato.
