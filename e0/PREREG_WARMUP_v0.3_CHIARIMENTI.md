# PRE-REGISTRAZIONE WARM-UP v0.3 — CHIARIMENTI (appendice datata 09/11/2026)

**Stato:** documento **aggiuntivo**. Non modifica la pre-registrazione committata in `bbc3121` (`e0/PREREG_WARMUP_v0.3.md`, §1–§6, §8) né la §7.3 aggiunta in `db013eb`.
- Richiesta: Marco Ventura, 09/11/2026 15:19 (via chief). Marco **non ha ancora approvato** la pre-registrazione e **non ha autorizzato v0.3**.
- Solo analisi: nessuna modifica a codice, config o severità. v0.3 NON implementata. Nessuna QC ufficiale.
- **Obiettivo dichiarato:** una regola di qualità **strumentale**, non il miglioramento di P1. R non è usato in nessuna risposta.
- Tabelle di supporto (locali, non in git): `outputs/warmup_prereg_20261109T1455/chiarimenti_20261109T1530/`.
- Script:
  - `e0/run_warmup_prereg_clarifications.py`: Q1, Q3, Q4 e harness empirico;
  - `e0/run_warmup_prereg_clarifications_q2.py`: Q2.

**Erratum (importante, vedi §2.2).** La §3.6 di `bbc3121` attribuisce al manuale un τ "dell'ordine di 10 s". Questo valore **non è sostenuto dalla fonte**: era un'assunzione non dichiarata. La correzione è in §2.2. Il testo committato non è stato riscritto.

---

## 1. Quattro campagne anomale contro otto campagne modificate

Regola responsabile in tutti gli 8 casi: `qc_sensor_stabilization` (EXCLUDE_RECOMMENDED), primo segmento. Il gate di pendenza conferma la stabilità **dopo 300 s**: oggi v0.2 marca 0…t_conferma, con il cap a 300 s marcherebbe 0…300 s. Nessun'altra regola è coinvolta.
- "Punti liberati" = righe che escono dal warm-up.
- "Recuperati" = righe che tornano in `keep_recommended`.
- "Ancora esclusi" = righe escluse da un'altra regola (§4).

### 1.1 Le 4 campagne con warm-up anomalo
Criterio di `bbc3121`: aumento v0.1 → v0.2 superiore a 150 righe **e** conferma oltre 600 s.

| Campagna | Dispositivo | Classe di avvio (gap) | Conferma | Righe v0.1 → v0.2 → cap300 | Liberati | Recuperati | Ancora esclusi | Durata interessata |
|---|---|---|---|---|---|---|---|---|
| 05-27 13:08 | AC4D | warm (1,2 min) | 2093 s | 91 → 1.395 → 225 | 1.170 | 1.169 | 1 (`qc_spatial_jump`) | 301–2091 s (≈ 30 min) |
| 02-20 12:54 | B6CC | cold (183 min) | 845 s | 297 → 802 → 297 | 505 | 505 | 0 | 301–844 s (≈ 9 min) |
| 7-22 09:17 | AC4D | warm (9,1 min) | 901 s | 189 → 700 → 242 | 458 | 458 | 0 | 301–899 s (≈ 10 min) |
| 06-20 08:29 | AC4D | warm (7,2 min) | 869 s | 210 → 634 → 210 | 424 | 374 | 50 (49 `qc_duplicate_record`, 1 `qc_temp_isolated_spike`) | 301–867 s (≈ 9,5 min) |

**Perché sono anomale.**
- In v0.2 il fix dt = 0 ha unito segmenti spuri. Il primo segmento è diventato lungo e il gate di pendenza ha confermato solo dopo 14–35 min: la mediana a 3 righe non resta ferma per 60 s, perché la temperatura del percorso varia a passi di 0,1 °C.
- In 3 casi su 4 la partenza è a sensore caldo, senza transitorio (test D negativo). Nella 02-20 il transitorio c'è, ma si esaurisce in 143 s.

### 1.2 Le altre 4 campagne che cambiano

| Campagna | Dispositivo | Classe di avvio (gap) | Conferma | Righe v0.1 = v0.2 → cap300 | Liberati | Recuperati | Ancora esclusi | Durata interessata |
|---|---|---|---|---|---|---|---|---|
| 9-16 11:29 | AC4D | intermedio (85 min) | 580 s | 429 → 222 | 207 | 206 | 1 (`qc_temp_isolated_spike`) | 301–579 s (≈ 4,6 min) |
| 05-27 18:39 | AC4D | cold (279 min) | 498 s | 387 → 237 | 150 | 150 | 0 | 301–497 s (≈ 3,3 min) |
| 7-30 07:42 | AC4D | cold (189 h) | 449 s | 323 → 218 | 105 | 105 | 0 | 302–447 s (≈ 2,4 min) |
| 07-04 10:15 (moto) | 6D17 | intermedio (42 min) | 321 s | 240 → 225 | 15 | 15 | 0 | 301–319 s (≈ 18 s) |

**Perché cambiano anche se non sono "problematiche".**
- In queste 4 la conferma arriva tra 300 e 600 s, già in v0.1 e identica in v0.2. Non sono una regressione introdotta da v0.2, quindi non rientrano tra le 4 anomale.
- Il cap a 300 s però è una regola **generale**: si applica a *ogni* conferma oltre 300 s, non solo ai casi anomali. Il meccanismo è lo stesso, quindi anche queste vengono accorciate.
- Questo rende coerente la regola con il caso "stabilità mai raggiunta", che v0.2 già limita a 300 s (36 campagne su 55).
- **Caso da segnalare:** la 9-16 11:29 ha un transitorio D vero (t_q = 332 s). Il cap a 300 s libera i punti tra 300 e 332 s, dove l'offset residuo stimato è appena sopra 0,1 °C. È un rischio residuo noto (AT-7 della pre-registrazione).
- Nelle altre tre (05-27 18:39, 7-30 07:42, 07-04 10:15) il test D non trova transitori.

**Totale 8 campagne:** liberati 3.034, recuperati 2.982, ancora esclusi 52. Le altre 47 campagne sono identiche a v0.2.

## 2. La soglia di 300 s

### 2.1 Testo pre-registrato in `bbc3121` (citazione letterale, §4)
> **C-cap.** T_cap è la **più piccola** soglia candidata in {120, 180, 300, 600 s} che soddisfa **tutte** le condizioni seguenti:
> 1. T_cap ≥ mediana di t_q dei transitori confermati dal test D nei real start (**250 s**);
> 2. T_cap ≥ punto medio del tempo di adattamento operativo da letteratura (**255 s**, AMT 2024);
> 3. T_cap ≥ 10 τ intrinseco del sensore ventilato (≈ **100 s**);
> 4. l'eccesso di |offset| nei 300–600 s degli avvii cold rispetto agli pseudo-start non è sistematico: IC che include 0 e punto ≤ 1 quanto (0,1 °C).
>
> | 300 s | soddisfa 1, 2 e 3; condizione 4 verificata (+0,10 °C, IC [−0,18; 0,32]) |
>
> **→ T_cap = 300 s.**

E in §3.6 (riga 179):
> **Manuale MeteoTracker:** una variazione di 15 °C è rilevata entro 30 s a 20 km/h, quindi τ intrinseco ventilato dell'ordine di 10 s.

### 2.2 Calcolo completo e fonti

**Condizione 1: dati propri.**
- t_q è il tempo per scendere sotto 0,1 °C nei 7 transitori D: t_q = τ·ln(|b|/0,1).
- Valori ordinati: 90, 143, 147, **250**, 332, 644, 995 s. **Mediana 249,9 s.**
- Robustezza (`q2_tq_median_robustness.json`):
  - IC 95 % bootstrap della mediana: [143; 644] s;
  - la mediana resta ≤ 300 s solo nel **65 %** dei campioni bootstrap;
  - leave-one-out: mediana da 198 a 291 s, sempre ≤ 300.
- → La condizione 1 è soddisfatta, ma **fragile**: con n = 7, in circa un terzo dei bootstrap selezionerebbe 600 s.

**Condizione 2: letteratura.** Barbano F. et al. (2024), *Performance evaluation of MeteoTracker mobile sensor for outdoor applications*, Atmos. Meas. Tech., 17, 3255 (https://amt.copernicus.org/articles/17/3255/2024/), §4.1. Citazione letterale:
> "Overall, the cooling or heating rate of an MT under operational use ranges between 0.5 to 1.7 °C min−1, accounting for an adjustment time of 2.2–6.3 min according to this test."

E per il sensore fermo:
> "a stationary MT takes 15 min (on average) to achieve thermal equilibrium in a partially controlled room from an initial temperature discrepancy of 2 °C. When exposed to outdoor conditions, the stationary MT takes 10 min (on average) to drop its temperature of 2 °C."

- Punto medio: (2,2 + 6,3)/2 = 4,25 min = **255 s** → 300 ≥ 255, soddisfatta.
- **Limite:** l'estremo superiore è 6,3 min = 378 s > 300. Il criterio usa il punto medio, scelta dichiarata in `bbc3121`.
- Il "tempo di adattamento" di AMT è definito con un metodo IQR di rimozione degli outlier: non è una costante di tempo.

**Condizione 3: costante di tempo. Erratum.**
- **Il produttore non fornisce un valore di τ.** Le fonti verificate oggi (scaricate dal sito meteotracker.com) dicono:
  - *MeteoTracker Device User Manual EN 2023-07-04*, specifiche: "measurement speed: 15° C variation over a 30 seconds time interval at 20 km/h". Non indica l'ampiezza del gradino, quindi da questa sola frase τ non è calcolabile.
  - *MeteoTracker+ App Manual rev.1* (2026), §9.1: "Measurement speed: ≥ 15 °C variation detected over a 30 s interval at 20 km/h, under a stepped temperature change of 30 °C."
- **Derivazione (ASSUNZIONE: risposta del primo ordine).** Almeno il 50 % di un gradino di 30 °C in 30 s implica 1 − e^(−30/τ) ≥ 0,5, quindi **τ ≤ 30/ln 2 = 43,3 s**. È solo un **limite superiore**, non un valore.
  - Il "≈ 10 s" di `bbc3121` equivaleva a supporre il 95 % del gradino in 30 s. Questo **non è scritto nella fonte**.
- **Conseguenze:**
  - con il valore committato (10τ ≈ 100 s) la condizione 3 è soddisfatta da 300 s;
  - con la fonte corretta, 10τ ≤ 433 s e la condizione è **indeterminata**: 300 s la soddisfa solo se τ ≤ 30 s, cioè almeno il 63 % del gradino entro 30 s;
  - nel caso peggiore ammesso dalla fonte (τ = 43,3 s) il criterio selezionerebbe **600 s**.
- **Informazione post hoc, NON parte del criterio pre-registrato:** il multiplo "10τ" è arbitrario. Il tempo fisico per portare un gradino ΔT sotto 0,1 °C è τ·ln(ΔT/0,1). Con τ = 43,3 s vale 147 / 199 / 229 / 247 s per ΔT = 3 / 10 / 20 / 30 °C, sempre < 300 s. Lo riporto solo come elemento per la decisione: sostituirlo ora al criterio sarebbe una modifica a posteriori.

**Condizione 4:** +0,096 °C, IC [−0,18; 0,32] → soddisfatta (al limite di 1 quanto).

**Tabella meccanica** (`q2_threshold_criterion.csv`):

| Soglia | Cond. 1 (≥ 250) | Cond. 2 (≥ 255) | Cond. 3 committata (≥ 100) | Cond. 3 corretta (≥ 433, caso peggiore) | Copre l'estremo AMT (≥ 378) | Transitori con t_q ≤ soglia |
|---|---|---|---|---|---|---|
| 120 | no | no | sì | no | no | 1/7 |
| 180 | no | no | sì | no | no | 3/7 |
| **300** | sì | sì | sì | **no** | no | 4/7 |
| 600 | sì | sì | sì | sì | sì | 5/7 |

**Coerenza con `bbc3121`:**
- 300 s è **coerente con il criterio così come è stato committato**, valore di τ incluso.
- Quel valore di τ era però un'assunzione non dichiarata. Con la fonte letterale, la condizione 3 non permette di escludere 600 s.
- **La selezione di 300 s non è quindi robusta alla correzione dell'erratum.** Lo dichiaro esplicitamente invece di ritoccare il criterio.

## 3. Le 30 partenze

**Classi** (in base al gap dalla fine della sessione precedente dello stesso dispositivo; primo segmento ≥ 1200 s):

| Gruppo | n | Transitori D | Quota | IC 95 % Wilson | IC 95 % Clopper–Pearson |
|---|---|---|---|---|---|
| **Partenze a freddo** (gap > 120 min o prima sessione) | **20** | 5 | 25 % | 11–47 % | 9–49 % |
| Intermedie (15–120 min) | 5 | 2 | 40 % | 12–77 % | 5–85 % |
| **Riprese a sensore caldo** (gap ≤ 15 min) | **4** | 0 | 0 % | 0–49 % | 0–60 % |
| Dispositivo sconosciuto | 1 | 0 | — | 0–79 % | 0–97 % |
| Tutte le non-warm | 26 | 7 | 27 % | 14–46 % | 12–48 % |
| **Tutte** | **30** | 7 | 23 % | 12–41 % | 10–42 % |
| Pseudo-start (nullo, 11 campagne) | 29 | 3 | 10 % | 4–26 % | 2–27 % |

- **Fisher unilaterale, real > pseudo:** tutte p = 0,16; solo cold p = 0,17. **Non significativo.**
- **Le 4 riprese a sensore caldo:** 04-27 08:38 (3,6 min), 05-27 13:08 (1,2), 06-20 08:29 (7,2), 7-22 09:17 (9,1). Tre di queste sono campagne anomale, quindi c'è bias di selezione.
- Elenco completo: `q3_real_starts_list.csv`.

**Come sono stati identificati i transitori (test D, fissato prima di R):**
- **Dati:** medie su blocchi di 10 s della temperatura nei primi 900 s del primo segmento.
- **Modelli:**
  - esponenziale a + b·e^(−t/τ), con τ su una griglia da 15 a 600 s;
  - lineare a + c·t.
- **Positivo se valgono tutte:**
  1. ΔBIC (lineare − esponenziale) ≥ 10;
  2. τ ≤ 300 s;
  3. |b| ≥ 0,3 °C (3 quanti);
  4. segno(offset 0–60 s) = segno(b);
  5. |offset 300–600 s| ≤ 0,5·|offset 0–60 s|.
- **Offset:** mediana della finestra meno mediana della fase 600–1200 s.
- **Controllo:** lo stesso test sui 29 pseudo-start, cioè finestre a metà viaggio da 600 s dopo l'inizio di un segmento, ogni 300 s, con almeno 1200 s di dati. Dà il tasso di falsi positivi: 3/29.

**Offset** (bootstrap per campagna, 2000 repliche, seed 20261109; da `evidence/median_abs_offset_excess_bootstrap_T.csv`):
- **Cold:**
  - eccesso di |offset| sugli pseudo-start a 0–60 s: +0,28 °C [−0,20; 0,51];
  - a 300–600 s: +0,10 °C [−0,18; 0,32].
- **Warm** (60–120 s): +0,83 °C [0,10; 2,01]. Gli offset non decadono e il gruppo ha bias di selezione.

**Limiti statistici:**
- campioni piccoli, con IC larghi (warm: 0/4, IC fino al 60 %);
- nessuna differenza significativa tra partenze reali e pseudo-start;
- la soglia del 10 % di falsi positivi è superata (10,3 %);
- partenza e uscita da garage o città non sono separabili senza un riferimento fisso;
- il gap tra sessioni è solo un'approssimazione dell'accensione.

## 4. Impatto sulla maschera

**Ricalcolo indipendente** dai parquet archiviati v0.2 (`e0R_qc_split_20261109T1240/recommended`):
- punti totali 72.505;
- `keep_recommended` v0.2 = **59.209** (ricalcolato) → con cap 300 = **62.191** (ricalcolato);
- concorda con lo script delle varianti di `bbc3121` (62.191).

**Composizione:**
- Righe che escono dal warm-up: **3.034** (13.148 → 10.114).
- **Recuperati** in `keep_recommended`: **2.982**.
- **Ancora esclusi da altre regole: 52** (`q4_still_excluded_by_other_rules.csv`):
  - `qc_duplicate_record`: 49 (06-20);
  - `qc_temp_isolated_spike`: 2 (06-20, 9-16 11:29);
  - `qc_spatial_jump`: 1 (05-27 13:08).
- Campagne interessate: le 8 della §1. Le altre 47 non cambiano.

**Verifica empirica che nessun'altra regola QC cambi** (`q4_harness_*`):
- Ho eseguito la pipeline reale (`MeteotrackerQC.compute_frame`, config `qc_E0R_recommended_v0.2.yaml` non modificata, in memoria) due volte su tutte le 55 campagne canoniche:
  - una volta così com'è;
  - una volta con l'uscita del rilevatore di warm-up post-processata dal cap a 300 s, tramite un wrapper definito *nello script di analisi*. Nessun file in `src/` o `config/` è stato toccato e nessun albero QC è stato scritto.
- **Riproducibilità:** la prima esecuzione riproduce l'archivio v0.2 in tutte le 55 campagne (`keep_recommended` e `qc_sensor_stabilization` identici).
- **Diff colonna per colonna:** cambiano solo 8 campagne.
  - **Unica flag di rilevatore che cambia:** `qc_sensor_stabilization` (3.034 righe).
  - **Flag di altri rilevatori cambiate: 0.** Tra queste `qc_segment_restart_recovery`, `qc_post_stop_recovery`, `qc_temp_*`, `qc_gps_*`, `qc_time_*`, `qc_duplicate_record`, `qc_spatial_jump` e tutte le altre.
  - Le altre colonne che cambiano sono **aggregati derivati** dalla stessa flag:
    - `qc_severity*`, `qc_exclusion_reasons*`, `qc_reasons`, `qc_reason_count` e `qc_bitmask`: 3.034 righe;
    - `qc_primary_reason`: 2.985 righe;
    - `keep_recommended` e `keep_strict`: 2.982 righe;
    - `keep_restrictive`: 689 righe; `keep_relaxed`: 52 righe;
    - `use_for_spatial_aggregation`: 2.649 righe; `use_for_satellite_comparison`: 2.571 righe.
  - Le colonne `keep_restrictive` e `keep_relaxed` sono quelle calcolate dentro la run recommended. Le run permissive e restrictive non sono state rieseguite qui.
- **Nel codice** (`pipeline.py`): il rilevatore di warm-up gira dopo tutti gli altri rilevatori. La sua uscita è letta solo dalla policy, che calcola severità e keep, e dalle colonne `use_for_*`. Nessun altro rilevatore la usa in ingresso, coerentemente con il diff.

## 5. Raccomandazione finale sulla solidità scientifica della regola

**Giudizio: il principio è solido; la soglia di 300 s è difendibile ma NON dimostrata. Non approvabile "così com'è" senza una decisione esplicita di Marco sull'erratum.**

1. **Principio, solido.** Una regola di warm-up strumentale deve coprire il tempo di risposta del sensore e dell'alloggiamento, non la variabilità ambientale.
   - Nelle 4 campagne anomale il warm-up di 14–35 min non corrisponde a nessun transitorio del sensore: 3 su 4 sono riprese a sensore caldo con test D negativo; nella quarta il transitorio dura 143 s.
   - Limitare la conferma tardiva a un tempo massimo fisso è quindi corretto dal punto di vista strumentale, ed è coerente con il cap già applicato quando la stabilità non viene mai raggiunta.
   - La modifica è chirurgica: un'unica flag e 8 campagne, nessun'altra regola cambia (verificato).
2. **Valore di 300 s, debole.**
   - Poggia sulla mediana di 7 transitori (IC [143; 644] s; solo il 65 % dei bootstrap ≤ 300).
   - Poggia sul punto medio di un intervallo di letteratura il cui estremo superiore (378 s) supera 300.
   - Con la correzione della costante di tempo, la condizione 3 non esclude 600 s.
   - 3 transitori su 7 superano 300 s (332, 644, 995 s).
3. **Opzioni per Marco** (nessuna usa R):
   - **(a)** 300 s come valore *provvisorio ingegneristico-empirico*, dichiarato tale, con l'erratum annotato. Pro: coerente con il cap già in uso per la stabilità mai raggiunta; perde meno dati. Contro: copre 4 transitori su 7.
   - **(b)** 600 s come scelta conservativa coerente con il caso peggiore del τ e con l'intervallo AMT completo. Contro: circa +6.200 righe escluse, e per coerenza andrebbe portato a 600 s anche il cap della stabilità mai raggiunta, cambiando 31 campagne in tutto (23 con stabilità mai raggiunta e 8 con conferma tardiva, +6.175 righe).
   - **(c)** Rinviare il valore e approvare solo il principio, finché non c'è una **prova controllata della costante di tempo**: gradino termico noto, sensore ventilato a 20 km/h, e misura di τ e del tempo sotto 0,1 °C. La prova è già nei "Prossimi passi" del rapporto principale.
4. **Mia raccomandazione: (c) + (a).**
   - Approvare il principio del cap anche sulla conferma tardiva.
   - Usare 300 s come valore provvisorio esplicitamente non dimostrato, se serve subito una v0.3.
   - Fissare il valore definitivo solo dopo la prova controllata di τ e la replica prospettica (AT-E1 e AT-E2).
   - Il miglioramento di R osservato in fase B **non** è un argomento a favore e non va usato.

## 6. Limiti aggiuntivi emersi
- La costante di tempo non è pubblicata dal produttore. Il limite τ ≤ 43,3 s richiede l'ipotesi del primo ordine e si basa sulla specifica dell'app MeteoTracker+ rev.1 (2026), forse relativa a una generazione di dispositivo diversa da quelli usati nel 2025–2026.
- Il manuale dell'app MeteoTracker+ descrive una "Guard Time": i dati vengono acquisiti solo dopo almeno 10 punti a 7 km/h o più. Non sappiamo quale versione dell'app abbia prodotto i nostri CSV. Una parte del warm-up potrebbe quindi essere già scartata a monte.
- Il "tempo di adattamento" di AMT 2024 è definito con un metodo statistico (IQR), in prove invernali in bici e cargo-bike: non è direttamente una costante di tempo.