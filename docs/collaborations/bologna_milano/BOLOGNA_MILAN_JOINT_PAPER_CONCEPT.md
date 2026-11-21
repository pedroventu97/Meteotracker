# BOLOGNA_MILAN_JOINT_PAPER_CONCEPT — Nota di fattibilità scientifica

- **Data:** bozza 18/11/2026, versione verificata sul repo 21/11/2026 (Europe/Rome)
- **Stato:** NOTA ESPLORATIVA. Nessun accordo con Milano. Nessuna decisione operativa.
- **Percorso:** `docs/collaborations/bologna_milano/BOLOGNA_MILAN_JOINT_PAPER_CONCEPT.md`. Cartella nuova e separata: `docs/` del repo è piatta e non conteneva sottocartelle di collaborazione.
- **Origine:** messaggio di Marco del 18/11/2026 (t71u), «Aggiornamento contesto scientifico — collaborazione Bologna–Milano».
- **Perimetro:** linea di ricerca **separata**. **Non** modifica:
  - gli obiettivi approvati di Space It Up!;
  - la roadmap P0–P5 (piano operativo adottato il 05/11/2026) e le decisioni vigenti;
  - dataset, `data/raw`, pipeline, codice QC, config, severità e warm-up.
  - Non implementa v0.3 e non dichiara ufficiale alcun QC.
- **Stato del repo letto il 21/11/2026:**
  - `D:\projects\Meteotracker`, branch `feat/meteotracker-windows-app`, HEAD `e1524b1`, allineato a `origin`;
  - unici file non tracciati: DTM, `licenza/`, `metadati/`, `outputs/…`, `reports/experiments/` (non toccati).

## Legenda delle etichette

| Etichetta | Significato |
|---|---|
| **[VERIFICATO — fonte]** | Letto o ricalcolato in sola lettura il 18–21/11/2026 da un file citato (repo DICAM, altri repo in `D:\projects`, Drive BOLOGNA_URBAN_CLIMATE_INTEGRATION). |
| **[DICHIARATO DA MARCO]** | Riportato da Marco in t71u e non verificato da noi. Vale per **tutto** ciò che riguarda Milano e Alberto Vavassori. |
| **[IPOTESI / DA CONCORDARE]** | Proposta di lavoro, non concordata con Milano. |

---

## 1. Contesto della collaborazione

1. Il 18/11/2026 è iniziata una discussione con **Alberto Vavassori** (DICA, Politecnico di Milano) per una collaborazione tra gruppi che lavorano su misura e modellazione della temperatura urbana. **[DICHIARATO DA MARCO]**
2. Ipotesi condivisa: unire i dataset di misure mobili di Tair di Bologna e Milano (diurne e notturne), armonizzare acquisizione, correzione e trattamento, svolgere analisi comparative e modellazione condivisa e preparare un articolo congiunto. **[DICHIARATO DA MARCO]**
3. La fase è **esplorativa**. Protocollo definitivo, struttura del paper, ruoli degli autori e calendario **non** sono concordati. **[DICHIARATO DA MARCO]**
4. Titolo di lavoro: *"Daytime and nighttime urban air temperature mapping: a comparative data-driven approach across Bologna and Milan"*. **[DICHIARATO DA MARCO; IPOTESI / DA CONCORDARE]**
5. **Separazione dalle attività in corso.**
   - Obiettivo del progetto Bologna: «determinare quanta parte del campo termico urbano di Bologna sia realmente ricostruibile da campagne mobili discontinue (Meteotracker), con quale incertezza e grazie a quali informazioni ambientali».
   - Priorità P1 Meteotracker, satelliti in P4. V18 resta la baseline congelata ma non è il filo conduttore.
   - **[VERIFICATO — Drive `00_PROJECT_CONTROL/OPERATIONAL_PLAN_2026-11-05.md`; DEC-OPERATIONAL-PLAN-ADOPTED-2026-11-05]**
   - Questa collaborazione **non** cambia quelle priorità e riusa i prodotti esistenti solo in lettura.
   - Gli obiettivi formali di Space It Up! non sono descritti nei documenti di controllo del progetto. In `D:\projects` esiste solo una presentazione `SIU! Summer Forum_Presentation.pptx`, non letta. La relazione con questa linea va confermata da Marco. **[DA CONCORDARE]**

## 2. Stato delle informazioni disponibili

### 2.1 Bologna — stato dei componenti

| Componente | Stato | Fonte | Etichetta |
|---|---|---|---|
| Progetto nel complesso | **PARTIAL**, nessuna voce VALIDATED | Drive `PROJECT_MASTER_STATUS.md` (09/11) | VERIFICATO |
| MeteoTracker | Pipeline QC implementata e testata, **non validata**: nessuna validazione indipendente della Tair mobile (issue MT-NOT-VALIDATED) | `reports/REPORT_PRINCIPALE.md`, «Stato per componente»; Drive `OPEN_ISSUES_AND_BLOCKERS.md` | VERIFICATO |
| E0 (manifest, QC, split) | Manifest ufficiale `data/manifests/campaign_manifest.csv`: 60 righe / **55 canoniche** / 5 escluse. QC 55/55. Split: 17 giorni, 604 route, 570 blocchi da 500 m, 72 505 osservazioni | `REPORT_PRINCIPALE.md`; `e0/README_E0.md`; `e0/SPLIT_DESIGN_E0.md` | VERIFICATO |
| QC E0-QC-R, policy v0.2 | Final validation del 09/11: **CHANGES REQUIRED**, limitato al rilevatore di warm-up. **Nessun QC ufficiale** | `e0/RAPPORTO_FINAL_VALIDATION_E0_QC_R.md`; `REPORT_PRINCIPALE.md`, «Prossimi passi» | VERIFICATO |
| Warm-up | Principio del cap approvato; valore 300/600 s **APERTO** fino alla misura di τ in campo. Pre-registrazione v0.3 **non approvata, non implementata**. Protocollo τ nel commit `321ea73` | `e0/PREREG_WARMUP_v0.3*.md`; `e0/DECISIONE_CAP_WARMUP_20261109.md`; `e0/PROTOCOLLO_TAU_WARMUP_v1.md`; changelog del 09/11 | VERIFICATO |
| Netatmo | OPERATIONAL / **VALIDATION_ABSENT**. ARPAE non è ground truth; D8 aperto; Dext3r in attesa di file | Drive `03_NETATMO/00_OVERVIEW/README.md`; `OPEN_ISSUES_AND_BLOCKERS.md` | VERIFICATO |
| Downscaling LST (MODIS → 100 m) | V18 `v18_training_only_no_gamma`: baseline **congelata**, validazione parziale del pattern (non della temperatura assoluta). Circa metà del contrasto spaziale; offset estivo di circa −5 K non spiegato. V19 bloccata | Drive `01_DOWNSCALING_LST/00_OVERVIEW/*`; DEC-V18-HALF-CONTRAST | VERIFICATO |
| LCZ | `D:\projects\LCZ\LCZ_SENTINEL.tif`: EPSG:32632, **15 m**, OA 0,834 su 44 poligoni, validazione parziale; inferenza LCZ-V18 bloccata; vietato modificare le LCZ per migliorare le correlazioni. E0 usa `LCZ_PRISMA.shp` esterno al repo (copertura 0,9148) | Drive `04_LCZ/00_OVERVIEW/README.md`; `e0/README_E0.md`; DEC-LCZ-NO-TUNING | VERIFICATO |

### 2.2 Bologna — risultati Meteotracker già ottenuti (contesto, non risultati del paper congiunto)

- **Ripetibilità P1 tra coppie di giorni diversi**, profilo recommended, bootstrap per campagna:
  - route centered: **0,42 [0,19; 0,54]** (v0.1, n = 781) e **0,34 [0,09; 0,51]** (v0.2, n = 664);
  - route detrended nel tempo: 0,22 / 0,20;
  - blocco 500 m centered: **0,23 [0,10; 0,39]** (v0.1) e 0,25 [0,06; 0,43] (v0.2);
  - blocco detrended: **0,04** (IC che include 0);
  - R route dipende dal corridoio cv2_004.
  - **[VERIFICATO — `e0/RAPPORTO_FINAL_VALIDATION_E0_QC_R.md` §4; `e0/P1_REPEATABILITY_E0.md`]**
- Storico del 15/10: corridors_v2 R grezzo 0,41 → detrended 0,09. Gran parte della ripetibilità apparente è un gradiente su grande scala lungo il percorso. **[VERIFICATO — `REPORT_PRINCIPALE.md`, «Risultati chiave»]**
- **Ritardo del sensore** a Δt breve compatibile con 0–4 s ma non identificato (mediana 1,6 s). **[VERIFICATO — `REPORT_PRINCIPALE.md`]**
- **Regola vigente:** l'R di P1 **non** è mai un criterio per scegliere soglie o severità del QC. **[VERIFICATO — regola di Marco]**
- Paper Meteotracker: PROTOCOL_READY, **SUBMISSION_NOT_READY**. **[VERIFICATO — Drive `15_PAPER_READINESS/SCIENTIFIC_STATE.md`]**

### 2.3 Correzione temporale a un istante unico: NON implementata

**[VERIFICATO]**
- **Non esiste** nel codice una catena operativa di «correzione temporale a un istante di riferimento + Ordinary Kriging dei coefficienti».
  - `git grep` in `Meteotracker`, `bologna_urban_climate_integration`, `netatmo`, `Downscaling` e `LCZ` non trova `OrdinaryKriging`/PyKrige né un istante di riferimento 11:17/09:17. Le sole occorrenze di «11:17» sono orari di inizio/fine campagna, ad esempio la fine della campagna 30/07 07:42 UTC alle 11:17:24 locali.
  - Il master report di integrazione (§15, `MASTER_REPORT_BOLOGNA_URBAN_CLIMATE_2026-10-17.md`) dice: catena kriging «NOT VERIFIED/non trovata, non validata»; filone F7 «NON AVVIATO».
  - `D:\projects\kriging\` contiene solo un PDF di riferimento.
- **Esiste invece** in Meteotracker un detrending **sperimentale intra-sessione**, `src/meteotracker_qc/temporal_drift/`:
  - usa la pendenza lineare stimata dai ripassaggi nella stessa sessione;
  - il candidato quadratico non è applicato (warning `NONLINEAR_DETREND_NOT_IMPLEMENTED_USING_LINEAR_APPROXIMATION`);
  - scrive solo colonne separate e non tocca la temperatura ufficiale (`reports/temporal_drift_diagnostics.md`).
- La memoria di progetto del 09/10 parla di un metodo con riferimento 11:17 CEST applicato a due itinerari. Nel codice dei repo **non c'è traccia** di quel metodo: se esiste, è in notebook o archivi non versionati. **[VERIFICATO assenza nei repo; esistenza altrove = DA CHIARIRE con Marco]**
- La specifica `MASTER_SCIENTIFIC_SPECIFICATION_v2.1.md` del repo di integrazione definisce le convenzioni di una normalizzazione a un istante di riferimento, ma **solo come specifica**. **[VERIFICATO]**

### 2.4 Bologna — inventario campagne: fuso, durata, giorno/notte, stagione

**Fuso orario — conclusione [VERIFICATO]:**
- **L'orario nel nome dei file raw è UTC.**
- La colonna `Time` dei raw porta l'**ora locale con offset esplicito** (`+01:00` d'inverno, `+02:00` d'estate).
- Su tutte le 55 campagne canoniche il primo timestamp coincide con l'orario del nome file convertito in UTC: 0 discrepanze oltre 120 s; offset +01:00 per 12 campagne, +02:00 per 43.
  - Esempio: `20260730T21_47_28_…csv` inizia a `2026-07-30T23:47:28+02:00`.
- Il codice converte correttamente in UTC (`pd.to_datetime(..., utc=True)` in `gps_qc.py`, `ingestion.py`, `inventory.py`) e in Europe/Rome per il giorno (`campaign_catalog.py`, `flag_table.py`).
- Metodo: script in sola lettura sui raw del manifest ufficiale (`.venv` del repo, output solo a schermo).
- Giorno/notte con alba e tramonto NOAA (Bologna 44,49 N; 11,34 E; elevazione solare −0,833°):
  - «notte» = sole sotto l'orizzonte;
  - «serale» = entro 1 h prima del tramonto.

**Discrepanza 16 vs 17 date — risolta [VERIFICATO]:** le date di inizio sono 16. La campagna del 30/07 23:47 locale termina il **31/07 alle 00:16**. Lo split E0 assegna il giorno Europe/Rome **per osservazione**, quindi conta anche il 31/07: **17 giorni** in tutto.

**Catalogo ufficiale [VERIFICATO]:**

| Fonte | Righe | Note |
|---|---|---|
| `data/manifests/campaign_manifest.csv` (ufficiale E0) | 60 / **55 canoniche** / 5 escluse | — |
| `outputs/campaign_catalog.csv` (non tracciato, 16/09/2026) | **44** campagne | Generazione pre-E0 (`timezone_interpretation = explicit_offset`); non va usato per conteggi correnti |
| `data/raw` | 61 file, 17 cartelle | — |

**Conteggi finali sulle 55 campagne canoniche [VERIFICATO]:**

| Ripartizione | Valore |
|---|---|
| Osservazioni | 72 505 (55 618 recommended v0.1) |
| Durata totale | circa **33,3 h** (1 998 min); durata tipica 20–95 min; alcune campagne sono frammenti (0,5–9 min) |
| Anno | 2025: **4** (una sola data, 04/07/2025, moto privata); 2026: **51** |
| Stagione (campagne / date di inizio) | JJA 2025: 4/1 · DJF 2026: 9/4 · MAM 2026: 12/4 · JJA 2026: 20/5 · SON 2026: 10/2 |
| Copertura | 04/07/2025 → 16/09/2026, con un vuoto luglio 2025 → febbraio 2026 |
| **Giorno / serale / notte** (punto medio della campagna) | **47 / 1 / 7** |
| Giorno / serale / notte (inizio della campagna) | 47 / 2 / 6 |
| Durata notturna totale | circa **2,4 h** (144 min) su 33,3 h, cioè il 7% del tempo |
| Dispositivi (ID nel nome file) | `AC4D162B317E`: 37 · `B6CCF894…`: 12 · `6D17FE6E…` (privato, moto): 4 · `UNKNOWN`: 2 |

**Le 7 campagne notturne** (ora locale; durata):

| Data | Orario locale | Durata |
|---|---|---|
| 28/02/2026 | 20:09–20:17 | 8 min, frammento |
| 04/03/2026 | 22:12–22:36 | 24 min |
| 27/05/2026 | 20:39–21:00 | 20 min; 68% dopo il tramonto, in parte crepuscolo |
| 20/06/2026 | 22:53–23:20 | 27 min |
| 30/07/2026 | 23:47–00:16 | 29 min |
| 08/09/2026 | 20:50–21:11 | 21 min |
| 16/09/2026 | 20:36–20:51 | 15 min |

- Più una campagna **serale**: 16/09/2026, 18:58–19:44, 32% dopo il tramonto.
- Tutte le notturne cadono **entro circa 3–4 h dal tramonto**: non c'è nessuna misura a notte fonda o prima dell'alba, quando l'isola di calore notturna è di solito massima.
- **Percorsi:** molte campagne sono trasferimenti extraurbani (Bologna–Modena, Carpi, Ravenna–Imola, Sasso Marconi, Bentivoglio, Anzola, Castelfranco). Il flag `qc_coord_outside_aoi` riguarda 6 566 righe. Il campione «urbano» è quindi minore del totale. **[VERIFICATO — nomi file raw; flag table E0]**

**Sovrapposizione con Milano:** Bologna ha campagne il **22/07/2026** (4, diurne) e il **30/07/2026** (6: 5 diurne e 1 notturna, 23:47–00:16). Milano ha presentato campagne del **23/07** e del **30/07/2026**. **[VERIFICATO per Bologna; DICHIARATO DA MARCO per Milano]**
- Il **30/07/2026 è una data comune**.
- Se il 30/07 sia un giorno di ondata di calore anche a Bologna **non è verificabile** con i file locali: la serie ERA5-Land di `D:\projects\HW` si ferma al 26/05/2026. **[DA VERIFICARE]**

### 2.5 Milano — cosa sappiamo

Tutto **[DICHIARATO DA MARCO]**; **nulla è verificato** da noi:
- misure mobili Meteotracker;
- predittori da rilievi aerei ad alta risoluzione: altezza edifici, aspect ratio, Sky View Factor, altezza alberi, indici spettrali;
- temperatura superficiale da termico aereo;
- regressione multivariata con ottimizzazione del buffer spaziale in cross-validation;
- validazione con centraline indipendenti;
- due campagne presentate, **23/07/2026** (senza ondata di calore) e **30/07/2026** (con ondata di calore).

**Non noti, e da non dedurre:** numero di campagne, esistenza di misure **notturne**, sensori e firmware, montaggio, correzioni, formati, licenze.

## 3. Dataset potenzialmente integrabili

### 3.1 Disponibilità dei predittori (verificata sul disco di DICAM il 21/11/2026)

| Predittore / dato | Bologna: stato reale | Milano | Comparabilità |
|---|---|---|---|
| Tair mobile Meteotracker | **Presente**: 55 campagne, QC E0 a flag [VERIFICATO] | Presente, almeno 2 campagne [DICHIARATO] | Alta solo con stesso sensore/firmware e QC armonizzato [DA CONCORDARE] |
| Stazioni fisse | Netatmo (crowdsourcing, non validato); ARPAE (non ground truth) [VERIFICATO] | Centraline indipendenti [DICHIARATO] | Natura diversa [DA CONCORDARE] |
| MODIS LST 1 km | **Presente** (MOD11A1 v061 Terra) [VERIFICATO] | Non dichiarata | Disponibile ovunque [IPOTESI] |
| **LST downscalata 100 m (V18) sulle date MT** | **Presente parzialmente**: 13 date coperte. 10 `DOWNSCALED_OPERATIONAL`; 3 `NO_VALID_MODIS` (20/02, 28/02, 04/03); **30/07 `STACK_BUILD_FAILED`**; 01/08, 08/09 e 16/09 non coperte [VERIFICATO — `D:\projects\Downscaling\results\geotiff\v13_100m_v18_training_only_no_gamma_meteotracker_dates\manifests\meteotracker_campaign_downscaled_lst_manifest.csv`] | No | Solo Bologna; contrasto circa dimezzato |
| **Landsat 8/9 LST sulle date MT** | **Scene a catalogo, non scaricate come prodotti autonomi**: 8 date con scena lo stesso giorno, con copertura nuvolosa di scena 20/02 71%, 28/02 63%, 19/05 30%, 27/05 14%, 04/06 30%, 20/06 **0,7%**, 22/07 14%, 30/07 **1,0%**. Stato `NOT_DOWNLOADED`; alcune LST Landsat incorporate parzialmente negli stack di downscaling (es. 22/07: 29% della griglia) [VERIFICATO — `D:\projects\Downscaling\manifests\landsat_catalog_v19_candidates.csv`, `landsat_local_inventory.csv`] | Non dichiarata | Fattibile per entrambe, solo diurna (~10:00 UTC) [IPOTESI] |
| LST da termico aereo | **Assente** [VERIFICATO: nessun file] | Presente [DICHIARATO] | **Non comparabile**: solo Milano |
| LCZ | **Presente**: `LCZ_SENTINEL.tif` 15 m, `S2_map.tif`, `LCZ_PRISMA.shp` [VERIFICATO — `D:\projects\LCZ`, `bologna_urban_climate_integration\data\reference\lcz`] | Non dichiarata | Per Milano servirebbe una LCZ esterna comparabile [IPOTESI] |
| **DTM / quota** | **Presente con limiti**: `DTM5x5_ed2025_NE_7791.tif`, 5 m, regionale, EPSG:7791, tile NE, non tracciato da git, con `licenza/` e `metadati/`. Audit D1 (21/10): copertura **PARZIALE** (18/20 corridoi), datum verticale **non verificato**, adatto solo a stratificazione relativa [VERIFICATO — `reports/experiments/D1_dtm_validation_20261021/`] | Non dichiarato | Bologna collinare, Milano pianeggiante |
| **Altezza edifici / DSM / LiDAR** | **Assente**: nessun raster o vettore trovato; acquisizione prevista in P2 [VERIFICATO — ricerca file in `D:\projects`] | Presente [DICHIARATO] | Da produrre a Bologna |
| **Aspect ratio H/W, SVF** | **Assenti** (dipendono da DSM/edifici) [VERIFICATO] | Presenti [DICHIARATO] | Da produrre con lo stesso algoritmo |
| **Altezza alberi** | **Assente** [VERIFICATO] | Presente [DICHIARATO] | Da produrre |
| **Sentinel-2 / indici spettrali** | **Parziale**: composito estivo `D:\projects\LCZ\s2_estate.tif` (input LCZ) e probe S2 ARPAE nel repo di integrazione; NDVI 100 m dentro gli stack di downscaling. **Nessun S2 per data di campagna** (acquisizione mirata prevista in P4) [VERIFICATO] | Indici spettrali, fonte non nota [DICHIARATO] | S2 comune possibile [IPOTESI] |
| Urban Atlas | **Assente** [VERIFICATO] | Non dichiarato | Disponibile per entrambe le FUA [IPOTESI] |
| Contesto meteo (ERA5-Land) | Serie giornaliera e ondate di calore per il Comune di Bologna fino al **26/05/2026** (`D:\projects\HW`) [VERIFICATO] | Non dichiarato | Va estesa ai giorni di campagna 2026 |

**Conseguenza:** i predittori morfologici 3D che caratterizzano il lavoro milanese (altezza edifici, H/W, SVF, altezza alberi, termico aereo) **oggi non esistono a Bologna**. Il set comune immediato si riduce a:
- Tair mobile;
- LCZ (con mappatura comparabile a Milano);
- quota relativa;
- indici spettrali da Sentinel-2/Landsat (da acquisire sulle date);
- LST satellitare.

Il paper deve partire da questo **set minimo comune**. I predittori esclusivi vanno trattati come **analisi di sensibilità per città**, a meno che Bologna non produca la morfologia 3D in P2. **[IPOTESI / DA CONCORDARE]**

### 3.2 Dataset di Bologna utilizzabili subito (in lettura, senza nuove pipeline)

**[VERIFICATO]**
- Manifest E0 e output QC/split E0.
- Maschere permissive / recommended / restrictive (policy v0.2, QC **non ufficiale**).
- Risultati P1.
- LCZ.
- DTM 5 m (con limiti).
- LST V18 per 10 date di campagna.

Tutto il resto richiede attività P2/P4 non avviate.

## 4. Obiettivi scientifici

**[IPOTESI / DA CONCORDARE]**, coerenti con la domanda proposta:

> *Quanto cambiano i controlli morfologici e superficiali sulla distribuzione spaziale della temperatura dell'aria tra giorno e notte, e quanto sono trasferibili tra contesti urbani differenti?* **[DICHIARATO DA MARCO]**

- **O1.** Costruire un **protocollo armonizzato** di acquisizione, QC e correzione per Tair mobile Meteotracker, valido per due città.
- **O2.** Stimare per ogni città l'**importanza relativa** dei predittori morfologici, vegetazionali e superficiali sull'anomalia spaziale di Tair, separatamente per giorno e notte dove i dati lo permettono.
- **O3.** Valutare la **trasferibilità** dei modelli tra Bologna e Milano (cross-city) e tra condizioni meteo diverse.
- **O4.** Quantificare la relazione **LST–Tair** come relazione tra **due grandezze distinte**: LST ≠ Tair.
- **O5.** Dichiarare in modo esplicito i **limiti di ripetibilità e rappresentatività** delle campagne mobili (eredità di P1).

## 5. Ipotesi di ricerca

Tutte **[IPOTESI / DA CONCORDARE]**; vanno fissate prima di guardare i dati congiunti:

- **H1.** Di giorno la copertura (vegetazione, impermeabile, ombra) spiega più varianza spaziale della Tair rispetto alla geometria 3D. Di notte prevale la geometria (SVF, H/W, densità edificata).
- **H2.** Il buffer spaziale ottimale differisce tra giorno e notte e tra città.
- **H3.** Un modello allenato su una città perde accuratezza sull'altra. La perdita è minore con il solo set comune che con i predittori esclusivi.
- **H4.** La correlazione LST–Tair è più debole di notte e in condizioni ventilate.
- **H5.** In ondata di calore i contrasti intra-urbani di Tair aumentano. L'ipotesi è testabile solo con campagne comparabili in giorni con e senza ondata in entrambe le città.

## 6. Analisi proposte

Tutte **[IPOTESI / DA CONCORDARE]**:

1. **Pattern diurni e notturni.** Anomalie di Tair per città e fascia, definita con ora ed elevazione solare. Con i dati attuali di Bologna l'analisi notturna è **descrittiva** (7 campagne brevi, circa 2,4 h).
2. **Confronto Bologna–Milano.** Distribuzioni di anomalia per LCZ e per classi morfologiche comuni; LCZ solo come stratificazione (DEC-LCZ-NO-TUNING).
3. **Importanza dei predittori.** Regressione multivariata (approccio milanese) affiancata a GAM e modelli ad albero; importanza per permutazione **fuori campione**; blocchi di predittori aggiunti in modo incrementale (schema E3 del piano operativo).
4. **LST–Tair.**
   - Valore assoluto e anomalia analizzati separatamente (DEC-ABS-ANOM-SEPARATE).
   - Contrasto dimezzato di V18 dichiarato (DEC-V18-HALF-CONTRAST); V18 non va «corretto».
   - **Anni di training 2019–2022 esclusi** da ogni analisi con prodotti V18 (DEC-TRAIN-YEARS-EXCLUDED). Le campagne MT 2025–2026 non cadono in quegli anni.
5. **Trasferibilità.** Training su Bologna con test su Milano e viceversa, con il solo set comune.
6. **Generalizzazione meteorologica.** Leave-one-day-out; train su giorni «normali» e test su ondata di calore, se esistono dati in entrambe le città.
7. **Validazione.**
   - CV a **blocchi spaziali**, leave-one-campaign, leave-one-day, leave-one-route (piano operativo §5); split casuale dei punti escluso.
   - Stazioni indipendenti: centraline milanesi; a Bologna ARPAE e Netatmo **solo** come riferimenti imperfetti.

## 7. Requisiti di armonizzazione

### 7.1 Protocollo di pulizia di Bologna (base comune proposta)

- **Il QC segnala, non cancella.** `data/raw` resta immutabile. Ogni osservazione riceve flag con codice, motivo, severità e versione della procedura. **[VERIFICATO — `e0/QC_FLAG_SCHEMA_E0.md`; `REPORT_PRINCIPALE.md`, «Decisioni di Marco»]**
- **Tre maschere** derivate dagli stessi flag: **permissive / recommended / restrictive**. Chi analizza sceglie e dichiara il livello. Con la policy v0.2 la tabella flag e le maschere sono coerenti per costruzione.
  - Restrictive tiene circa il 27% dei punti e non è annidata in recommended. **[VERIFICATO — `e0/RAPPORTO_E0_QC_R.md`; `e0/RAPPORTO_FINAL_VALIDATION_E0_QC_R.md`]**
- **Controlli coperti:** warm-up del sensore, GPS congelato o soste, velocità e accelerazioni non realistiche, discordanza di velocità GPS/dispositivo, ventilazione insufficiente a bassa velocità, ripartenze dopo una sosta, duplicati temporali, punti fuori AOI. **[VERIFICATO — schema e flag table E0]**
- **Regole versionate e pre-registrate.** Policy v0.1 → v0.2. Regola del warm-up v0.3 **pre-registrata** (commit `bbc3121`, pushato prima di calcolare qualsiasi R) ma **non approvata**. **[VERIFICATO]**
- **R mai usato per scegliere soglie o severità.** **[VERIFICATO — regola di Marco]**
- **Warm-up.** Principio del cap approvato; valore **300 o 600 s APERTO**. Il produttore non fornisce τ; dal manuale si ricava solo τ ≤ 43 s nell'ipotesi del primo ordine. **[VERIFICATO — `e0/PREREG_WARMUP_v0.3_CHIARIMENTI.md` §2.2]**
- **Protocollo τ** (`e0/PROTOCOLLO_TAU_WARMUP_v1.md`, `e0/PROPOSTA_VALIDAZIONE_TAU_v1.md`, commit `321ea73`): prove a gradino e avvii a freddo in campo. Regola fissata prima delle prove: errore entro 0,2 °C e al massimo il 10% degli avvii a freddo ancora instabili; R escluso. Dati in `data/tau_tests/`, ignorata da git. **[VERIFICATO]**
  - **Se Milano usa lo stesso sensore**, il protocollo τ può diventare un **lavoro metodologico congiunto**: stesse prove sui dispositivi delle due città, così inerzia e warm-up si stimano una volta per entrambi i dataset. **[IPOTESI / DA CONCORDARE]**
- **Separazione degli effetti:** temporali vs spaziali; quota a parte; LST ≠ Tair. **[VERIFICATO — regole di progetto]**

### 7.2 Cosa va armonizzato con Milano

**[IPOTESI / DA CONCORDARE]**

| Tema | Requisito minimo |
|---|---|
| Sensore | Stesso modello e firmware, oppure intercalibrazione affiancata |
| Montaggio e mezzo | Altezza, schermatura, ventilazione, mezzo e velocità documentati. A Bologna ci sono almeno 2 giornate con moto privata (04/07/2025, 27/04/2026) |
| Tempo | Raw con offset locale esplicito e nome file in UTC (convenzione verificata a Bologna, da verificare a Milano); UTC + Europe/Rome; giorno/notte con elevazione solare |
| QC | Stesso schema di flag e stesse tre maschere, applicati dal codice di Bologna in sola lettura ai raw milanesi |
| Inerzia termica | Stesso modello di risposta (τ) per dispositivo, dalle prove τ |
| Correzione temporale | A Bologna **non esiste** una correzione a istante unico implementata. Proposta: analisi in **anomalia per campagna** come base comune; una correzione a istante unico va progettata e validata insieme |
| Griglia | CRS metrico comune: EPSG:32632 copre entrambe; il DTM regionale è in EPSG:7791 e va riproiettato una sola volta, con nearest per le classi. Risoluzione comune 50–100 m, analisi multiscala 10–500 m |
| Predittori | Algoritmi identici (SVF, H/W, buffer) su fonti analoghe; set comune come base |
| Validazione | Stessi schemi di CV e stesse metriche (MAE, RMSE, bias, copertura degli intervalli) |
| Provenienza | Manifest con checksum, licenza e versione per ogni dataset |

## 8. Rischi metodologici

| Rischio | Effetto | Mitigazione | Etichetta |
|---|---|---|---|
| Ripetibilità tra giorni debole a Bologna (blocco detrended R ≈ 0,04) | Mappe e importanza dei predittori instabili | Lavorare in anomalia, bootstrap per campagna, limiti dichiarati | VERIFICATO |
| **Notte a Bologna molto scarsa**: 7 campagne, 2,4 h, tutte nelle prime ore dopo il tramonto | Giorno/notte non inferenziale con i soli dati esistenti | Nuove campagne notturne (anche a notte fonda), possibilmente in date comuni con Milano | VERIFICATO |
| Molte campagne extraurbane | Campione urbano più piccolo del totale | Analisi limitata all'AOI urbana, dichiarata | VERIFICATO |
| Morfologia 3D assente a Bologna | Confronto dei predittori asimmetrico | Set comune; produzione di DSM/SVF/H/W in P2 se autorizzata | VERIFICATO |
| Notturne di Milano ignote; 2 campagne dichiarate | Trasferibilità non stimabile; overfitting | Checklist §10; più campagne | DICHIARATO |
| Sensori e montaggi diversi | Differenze strumentali scambiate per urbane | Intercalibrazione; protocollo τ congiunto | IPOTESI |
| Warm-up non deciso | Maschera recommended non definitiva | Usare v0.2 dichiarandolo, con sensibilità al cap; niente v0.3 senza ok di Marco | VERIFICATO |
| Correzione temporale non implementata | Bias residuo tempo ↔ spazio | Anomalia per campagna; correzione congiunta da validare | VERIFICATO |
| LST 30/07 non disponibile (stack fallito) | Niente LST downscalata nella data comune con Milano | Landsat 30/07 (nuvolosità di scena 1%) da acquisire, se autorizzato | VERIFICATO |
| DTM: datum verticale non verificato, copertura parziale | Niente correzioni di quota assolute | Solo stratificazione relativa; tile sud se serve | VERIFICATO |
| LST usata come proxy della Tair; V18 corretto a posteriori | Errori concettuali | LST ≠ Tair; V18 congelato; 2019–2022 esclusi | VERIFICATO (regole) |
| Autocorrelazione spaziale | CV ottimistica | CV a blocchi e per campagna | VERIFICATO (piano) |
| Sovrapposizione con P1/P2/P4 | Deriva delle priorità operative | Riuso in sola lettura; nessun cambio di roadmap | IPOTESI |
| Condivisione dati e authorship non definite | Blocco tardivo | Accordo scritto prima di scambiare dati | DA CONCORDARE |

## 9. Piano preliminare di lavoro

Tutto **[IPOTESI / DA CONCORDARE]**; nessuna data è concordata.

| Fase | Contenuto | Uscita | Go / no-go |
|---|---|---|---|
| **F0 — Allineamento** | Incontro con Alberto; checklist §10; accordo dati e authorship | Verbale, inventario Milano | Notturne e numero di campagne milanesi noti |
| **F1 — Armonizzazione strumentale** | Confronto sensori/firmware; eventuale protocollo τ congiunto; intercalibrazione | Nota metodologica τ comune | Stesso sensore, o intercalibrazione possibile |
| **F2 — Dataset armonizzato** | QC con schema comune sui dati milanesi (copia, sola lettura); maschere; griglia; set minimo di predittori | Dataset congiunto v1 con manifest | N minimo di campagne per città e fascia, fissato prima |
| **F3 — Integrazione dei dati mancanti** (separata da P2/P4 operativi, su autorizzazione) | Bologna: S2/Landsat sulle date, eventuale DSM/SVF/H/W. Entrambe: nuove campagne notturne e in date comuni | Predittori comuni | Autorizzazione di Marco |
| **F4 — Analisi per città** | Modelli e importanza per giorno/notte, CV a blocchi | Risultati per città | Migliori della baseline fuori campione |
| **F5 — Cross-city e meteo** | Train Bologna / test Milano e viceversa; con/senza ondata di calore | Curve di trasferibilità | — |
| **F6 — Scrittura** | Struttura, ruoli, figure | Bozza del manoscritto | — |

## 10. Informazioni mancanti da richiedere ad Alberto Vavassori

**[DA CONCORDARE — checklist proposta]**

**Strumento e acquisizione**
- [ ] Modello Meteotracker, numero di dispositivi, ID/numeri di serie, **firmware**
- [ ] Montaggio: altezza, posizione sul mezzo, schermatura, ventilazione
- [ ] Mezzo (bici, auto, moto, a piedi), velocità tipica e minima
- [ ] Frequenza di campionamento ed export (app, cloud, CSV grezzi)
- [ ] Timestamp: formato, **fuso** (UTC/locale/offset), ora legale, convenzione dei nomi file
- [ ] Procedura di accensione e attesa iniziale (warm-up)

**Campagne**
- [ ] Numero totale, date, orari di inizio e fine, percorsi
- [ ] Quante **notturne** e a che ora dopo il tramonto; ripetizioni sullo stesso percorso
- [ ] Meteo per campagna; criterio con cui il 30/07/2026 è «ondata di calore»
- [ ] Disponibilità a nuove campagne notturne o in date comuni con Bologna

**Trattamento dati**
- [ ] QC: regole, soglie, cancellazione o segnalazione
- [ ] Correzione dell'**inerzia termica** (metodo, τ)
- [ ] Correzione delle **variazioni temporali** (metodo, istante di riferimento)
- [ ] Aggregazione spaziale (griglia, buffer, tratti)

**Predittori**
- [ ] Elenco con **risoluzione, CRS, data, fonte, licenza**
- [ ] Altezza edifici, H/W, SVF, altezza alberi: algoritmi e software, per poterli riprodurre a Bologna
- [ ] Indici spettrali: sensore, data, correzioni
- [ ] Buffer ottimale e procedura di CV

**Termico aereo**
- [ ] Data e ora del volo, sensore, risoluzione, correzione atmosferica ed emissività, calibrazione

**Validazione**
- [ ] Centraline: rete, numero, posizione, schermatura, frequenza, accesso
- [ ] Metriche e schema di CV

**Condizioni**
- [ ] Termini di **condivisione dei dati** (licenza, embargo, riuso, archiviazione)
- [ ] Aspettative di **authorship**, ruoli, rivista target, calendario
- [ ] Vincoli di progetto o finanziamento lato Milano

---

## Riepilogo di fattibilità

**[VALUTAZIONE — IPOTESI, basata su fatti VERIFICATI]**

- **Verificato a Bologna:**
  - 55 campagne Meteotracker; QC a flag con tre maschere e regole pre-registrate; split formalizzati.
  - Nomi file in UTC e raw in ora locale con offset.
  - Ripetibilità tra giorni debole.
  - Il dato è **quasi solo diurno**: 47 campagne diurne, 1 serale, 7 notturne brevi (circa 2,4 h su 33 h), tutte nelle prime ore dopo il tramonto.
  - Nessuna correzione temporale a istante unico implementata.
  - **Nessun predittore morfologico 3D** (edifici, SVF, H/W, alberi) e nessun termico aereo; presenti LCZ, DTM 5 m con limiti, LST V18 su 10 date di campagna, scene Landsat a catalogo.
  - Data comune con Milano: **30/07/2026**, con una campagna notturna a Bologna.
- **Da concordare:** quasi tutto il lato milanese, il protocollo comune, la struttura del paper, ruoli e calendario.
- **Verdetto:** la collaborazione è **fattibile e utile come paper metodologico-comparativo** sulla Tair mobile: protocollo QC e τ comune, ripetibilità, set minimo di predittori comune.
  - L'obiettivo **giorno/notte e la trasferibilità dei controlli morfologici** oggi **non** è sostenibile con i soli dati esistenti. La notte di Bologna è troppo scarsa e la morfologia 3D manca.
  - Diventa realistico solo con nuove campagne notturne, idealmente in date comuni, e con predittori 3D comuni.

## Changelog del documento

- **18/11/2026:** prima bozza sulla box (DICAM offline), da Drive in sola lettura e copie sulla box.
- **21/11/2026:** verifica sul repo (DICAM, HEAD `e1524b1`).
  - Fuso dei nomi file risolto (UTC); conteggi finali giorno/serale/notte con durate; discrepanza 16/17 date spiegata; catalogo ufficiale.
  - Correzione temporale verificata come non implementata.
  - Inventario reale dei predittori.
  - Tutte le voci «VERIFICATO-BOX» e «DA VERIFICARE SUL REPO» chiuse.
  - Nessun dato, pipeline, QC, config, severità o warm-up modificato.
