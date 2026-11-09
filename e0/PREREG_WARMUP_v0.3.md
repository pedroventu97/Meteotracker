# PRE-REGISTRAZIONE — Regola di warm-up `qc_sensor_stabilization` v0.3

**Stato:** pre-registrazione scientifica, sola analisi. **v0.3 NON implementata**. Nessuna modifica a `src/meteotracker_qc/` (qc), config, severità o policy v0.1/v0.2. Nessuna QC dichiarata ufficiale.
**Autorizzazione:** Marco Ventura, 09/11/2026 14:53 (via chief of project Bologna). HEAD di partenza `5886085`.
**Cartella output (locale, non in git):** `outputs/warmup_prereg_20261109T1455/` (`evidence/`, `rules/`, poi `r_sensitivity_descriptive/`).
**Copia versionata:** `e0/PREREG_WARMUP_v0.3.md`.

**Ordine temporale (garanzia di pre-registrazione).**
- Fase A: evidenza termica, criterio di selezione, regola, test di accettazione. In questa fase non è stato calcolato **alcun R** (nessuna esecuzione di P1 o del modulo di ripetibilità).
- Le sezioni §1–§6 e §8 sono state committate e pushate **prima** di qualunque calcolo di R (commit di fase A, vedi changelog in `reports/REPORT_PRINCIPALE.md`).
- Fase B: analisi di R puramente descrittiva (§7.3), aggiunta con un commit successivo. Non modifica la scelta.
- **Trasparenza:** la definizione del test di transitorio (test D, §2.4) e il criterio di soglia (§4) sono stati fissati **dopo** aver ispezionato la tabella termica di fase A, ma **prima** di qualunque R.
  - Una prima versione del criterio di transitorio (ampiezza |b| di un modello esponenziale con trend lineare) è stata scartata perché non discriminava: il p95 di |b| sugli pseudo-start era 4,26 °C, perché le soluzioni con τ = 600 s imitano un trend lineare.
  - Questo è un grado di libertà del ricercatore e va dichiarato. Per questo l'eccezione E1 resta condizionata a un test **prospettico** (§6, AT-E1).

---

## 1. Ipotesi

Il rilevatore attuale: mediana mobile su 3 righe (dt 2 s); |pendenza| < 0,02 °C/s sostenuta per 60 s; gate di ventilazione di 20 s sopra 7 km/h. Il cap `max_window_s = 300 s` vale **solo** se la stabilità non viene mai raggiunta. Una conferma tardiva (> 300 s) marca invece tutto fino alla conferma (asimmetria documentata nella final validation, P-0527).

- **H1 (transitorio reale all'accensione).** Nei primi minuti di una sessione esiste un transitorio termico del sensore/alloggiamento: un offset rispetto alla fase stabile successiva che decade nel tempo e che supera la variabilità spaziale/temporale attesa a parità di durata. Atteso soprattutto con **avvio freddo** (sensore conservato in ambiente diverso, es. indoor).
- **H2 (warm start).** Se la sessione precedente dello stesso dispositivo si è chiusa da ≤ 15 min (sensore già in equilibrio), il transitorio è assente o più breve.
- **H3 (campagne colpite).** Nelle 4 campagne in cui v0.2 estende il warm-up oltre 600 s (conferma a 845–2093 s), la conferma tardiva non dipende da un transitorio del sensore. Dipende dalla variabilità ambientale lungo il percorso, combinata con la quantizzazione a 0,1 °C: il gate di pendenza richiede in pratica "nessuna variazione di 0,1 °C della mediana per 60 s".
- **H0.** I primi 300 s non differiscono dagli altri tratti della sessione (pseudo-start).

## 2. Dati e metodi (fase A, nessun R)

Script: `e0/run_warmup_prereg_evidence.py`, eseguito su `outputs/e0R_qc_split_20261109T1240/recommended/` (sola lettura). Log in `evidence_run.log`.

### 2.1 Campagne e classi di avvio
- **55 campagne.** Anni di training 2019–2022 esclusi, come da vincolo.
- **Classe di avvio**, in base al gap dalla fine della sessione precedente dello stesso dispositivo:
  - warm: ≤ 15 min;
  - cold: > 120 min, oppure prima sessione;
  - intermedio: tra 15 e 120 min;
  - unknown: dispositivo UNKNOWN.
- **Conteggio:** cold 35, intermedio 11, warm 7, unknown 2.
- **Proxy dell'accensione.** Non esiste un log di accensione del dispositivo, quindi il gap tra sessioni è l'unica approssimazione disponibile.

### 2.2 Popolazioni a confronto
- **Real start:** primo segmento di ciascuna campagna, con durata ≥ 1200 s. **n = 30.**
- **Pseudo-start:** finestre a metà viaggio, con t0 ogni 300 s a partire da 600 s dall'inizio di un segmento e almeno 1200 s di dati dopo t0. **n = 29**, da 11 campagne.
  - Sono la distribuzione nulla di quanto varia la temperatura in 10–20 min per sola variabilità spaziale/temporale, a sensore già stabile.
- **Gruppi:**
  - AFFECTED_v02: aumento di oltre 150 righe e conferma oltre 600 s;
  - CAP_GREW_v02: crescita solo fino al cap;
  - LONG_CONFIRM_preexisting: conferma tra 300 e 600 s, già presente in v0.1;
  - reference: tutte le altre.

### 2.3 Metriche (Temp, Hum, DP)
- **Offset** = mediana nella finestra [0–60, 60–120, 120–180, 180–300, 300–600 s] meno mediana della fase stabile di riferimento [600–1200 s].
- **Pendenza** 0–300 s, per regressione lineare, in °C/min.
- **Autocorrelazione** a lag 30 s (lag 3 su blocchi di 10 s).
- **Quota ventilata** 0–300 s (velocità > 7 km/h).
- **Test statistici:**
  - Mann–Whitney unilaterale, real > pseudo;
  - bootstrap per campagna (2000 repliche, seed 20261109) dell'eccesso di mediana |offset| real − pseudo.

### 2.4 Test di transitorio "D" (fissato prima di R)
Fit su blocchi di 10 s nei primi 900 s. Modello esponenziale `a + b·exp(−t/τ)`, con τ su una griglia da 15 a 600 s, contro un modello lineare. Il test è **positivo** se valgono tutte le condizioni:

1. ΔBIC (lineare − esponenziale) ≥ 10;
2. τ ≤ 300 s;
3. |b| ≥ 0,3 °C (3 quanti);
4. segno(offset 0–60) = segno(b);
5. |offset 300–600| ≤ 0,5·|offset 0–60| (il transitorio decade).

**Tempo di decadimento sotto un quanto:** t_q = τ·ln(|b|/0,1).

### 2.5 Cosa esiste e cosa no (non inventato)
- **Canali disponibili:**
  - Temp (risoluzione 0,1 °C);
  - Hum[%] (intero, 1 %);
  - DP;
  - Press;
  - Radiation (solo in parte).
- **Assenti o vuoti in tutte le campagne:**
  - Tir e Tsur;
  - tensione della batteria e tensione esterna;
  - temperatura interna del dispositivo;
  - log di accensione.
- **Altri dispositivi:**
  - nessuna sessione simultanea di dispositivi diversi, nello stesso giorno o sullo stesso percorso;
  - i dispositivi sono AC4D162B317E, B6CCF894, 6D17FE6E e UNKNOWN;
  - **non è quindi possibile un confronto tra dispositivi.**

## 3. Evidenza (fase A)

### 3.1 Lista delle campagne colpite (verificata)
Sono **esattamente 4**. La 05-27 13:08 è **una delle 4**, non una quinta.

| Campagna | Conferma (s) | Righe warm-up v0.1 → v0.2 | Gap dalla sessione precedente | Classe | Test D |
|---|---|---|---|---|---|
| 05-27 13:08 (AC4D) | 2093 | 91 → 1395 | 1,2 min | warm | negativo |
| 06-20 08:29 (AC4D) | 869 | 210 → 634 | 7,2 min | warm | negativo |
| 7-22 09:17 (AC4D) | 901 | 189 → 700 | 9,1 min | warm | negativo |
| 02-20 12:54 (B6CC) | 845 | 297 → 802 | 183 min | cold | **positivo**: τ = 60 s, b = +1,08 °C, t_q = 143 s |

- **CAP_GREW_v02** (crescita solo fino al cap di 300 s):
  - 02-28 09:08: 9 → 183 righe;
  - 02-28 19:09: 7 → 288 righe.
- **LONG_CONFIRM_preexisting** (invariate rispetto a v0.1):
  - 07-04 10:15: conferma a 321 s;
  - 05-27 18:39: 498 s;
  - 7-30 07:42: 449 s;
  - 9-16 11:29: 580 s.

**Lettura.**
- Tre delle quattro campagne colpite sono avvii **warm**, a 1–9 min dalla sessione precedente. Il sensore era già in equilibrio e **nessuna** mostra un decadimento.
- I loro offset iniziali sono **negativi**: −0,2/−0,6/−1,5 °C a 0–60 s, e −0,6/−2,5/−1,6 °C a 60–120 s. La temperatura sale nel corso del viaggio, in mattinate o nelle ore centrali.
  - Un sensore "caldo" residuo leggerebbe invece **più alto** all'inizio.
  - Il segno è quindi coerente con variabilità ambientale e di percorso, non con un artefatto del sensore (**H3 supportata**).
- La quarta (02-20, cold) ha un transitorio vero, ma breve: t_q = 143 s, ben dentro i 300 s. La conferma a 845 s è dovuta alla variabilità successiva, non al transitorio.

### 3.2 Primi 300 s vs periodi successivi (Temp)
Mediana |offset| rispetto alla fase 600–1200 s. Eccesso = mediana real − mediana pseudo, con IC al 95 % da bootstrap per campagna.

| Classe | 0–60 s | 60–120 s | 120–180 s | 180–300 s | 300–600 s |
|---|---|---|---|---|---|
| tutte (n=30) | +0,28 [−0,18; 0,51] | +0,10 [−0,06; 0,56] | +0,02 [−0,28; 0,41] | +0,04 [−0,33; 0,24] | +0,10 [−0,12; 0,30] |
| cold (n=20) | +0,28 [−0,20; 0,51] | +0,04 [−0,15; 0,53] | −0,02 [−0,38; 0,35] | −0,06 [−0,40; 0,24] | +0,10 [−0,18; 0,32] |
| intermedio (n=5) | +0,14 | +0,15 | +0,01 | −0,09 | −0,05 |
| warm (n=4) | +0,39 [−0,30; 1,12] | **+0,83 [0,10; 2,01]** | +0,71 | +0,38 | +0,45 [−0,09; 0,91] |

- **Pseudo-start (riferimento assoluto):** mediana |offset| 0,38 / 0,46 / 0,49 / 0,35 / 0,28 °C.
- **Avvii cold:** l'eccesso è concentrato nel **primo minuto** (+0,28 °C, IC che include 0). Da 120 s in poi è ≈ 0, entro un quanto. Non c'è eccesso sistematico oltre 300 s: +0,10 °C, IC [−0,18; 0,32].
- **Avvii warm:** l'eccesso è maggiore e persistente, ma **non decade** (0,8 → 0,7 → 0,4 → 0,45 °C).
  - n = 4, e 3 di queste sono state selezionate *proprio* perché la temperatura variava: forte **bias di selezione**.
  - Il pattern non è compatibile con un transitorio del sensore.

### 3.3 Pendenza e autocorrelazione (Temp)
**Mediana |pendenza 0–300 s|:**

| Classe | Real (°C/min) | Pseudo (°C/min) | MW p |
|---|---|---|---|
| tutte | 0,116 | 0,069 | 0,036 |
| cold | 0,110 | 0,069 | 0,20 |
| warm | 0,168 | 0,069 | 0,013 (bias di selezione) |

**ACF a 30 s:** real 0,28 contro pseudo 0,32 (p = 0,76). L'inizio sessione non è più "persistente" di un tratto qualunque.

### 3.4 Transitori (test D)
- **Frequenza:**
  - real start: 7/30 = 23 % (IC Wilson 12–41 %);
  - pseudo-start: 3/29 = 10,3 % (IC 3,6–26 %);
  - Fisher p = 0,16.
- **Per classe:** cold 5/20, intermedio 2/5, **warm 0/4**.

| Campagna | Classe | τ (s) | b (°C) | t_q (s) |
|---|---|---|---|---|
| 02-21 09:17 | cold | 30 | +2,02 | 90 |
| 02-20 12:54 | cold | 60 | +1,08 | 143 |
| 07-04 14:37 | cold | 60 | −1,16 | 147 |
| 9-16 18:36 | intermedio | 120 | −0,80 | 250 |
| 9-16 11:29 | intermedio | 120 | +1,60 | 332 |
| 03-04 21:12 | cold | 180 | +3,59 | 644 |
| 06-04 08:17 (Bologna–Carpi) | cold | 300 | −2,76 | 995 |

- **Distribuzione di t_q:** mediana 250 s, p75 ≈ 490 s, max 995 s.
- **Falsi positivi sugli pseudo-start (3):**
  - 02-13 13:23, t_q 386 s;
  - 02-21 a t0 = 600 s, t_q 118 s;
  - 05-27 13:08 a t0 = 1500 s, t_q 677 s.
- **Segno (qualitativo, n = 7):** b > 0 in inverno (febbraio–marzo: sensore più caldo dell'esterno, che si raffredda) e b < 0 in estate (giugno–luglio). Il pattern è coerente con un equilibrio indoor → outdoor. Non è stato testato formalmente.
- Il caso con t_q più lungo (06-04, τ = 300 s, percorso extraurbano Bologna–Carpi) è indistinguibile da un gradiente di percorso.

### 3.5 Altri sensori
- **Hum:**
  - offset 0–60 s: real 2,4 % contro pseudo 1,6 % (p = 0,05; warm 4,6 %, p = 0,03, con bias di selezione);
  - nessun eccesso da 60 s in poi;
  - ACF a 30 s più alta nei real start: 0,23 contro 0,05 (p = 0,06).
- **DP:** nessun eccesso significativo in nessuna finestra (p ≥ 0,07).
- **Interpretazione:** l'umidità relativa mostra un piccolo segnale nel primo minuto, coerente con un leggero effetto termico, perché RH dipende dalla T del sensore. Il dew point, conservativo, non lo mostra. Gli altri canali non indicano transitori oltre il primo minuto.
- Temperatura interna, Tir/Tsur, tensioni e altri dispositivi: **non disponibili** (§2.5).

### 3.6 Ventilazione e costante di tempo
- **Quota ventilata 0–300 s nei real start:** mediana 0,82, p10 0,59.
- **Manuale MeteoTracker:** una variazione di 15 °C è rilevata entro 30 s a 20 km/h, quindi τ intrinseco ventilato dell'ordine di 10 s. Accuratezza tipica ±0,1–0,2 °C.
- **AMT 2024** (*Performance evaluation of MeteoTracker mobile sensor*, AMT 17, 3255):
  - tempo di adattamento in uso operativo, in movimento: **2,2–6,3 min** (punto medio 4,25 min ≈ 255 s);
  - sensore fermo: 10–15 min.
- **Conclusione fisica:** l'elemento sensibile si equilibra in decine di secondi. I transitori di minuti dipendono dalla massa termica dell'alloggiamento, dal supporto e dall'ambiente di conservazione, e sono dell'ordine di grandezza osservato qui (t_q mediano 250 s).

## 4. Criterio di selezione della soglia (fissato prima di R)

**C-cap.** T_cap è la **più piccola** soglia candidata in {120, 180, 300, 600 s} che soddisfa **tutte** le condizioni seguenti:
1. T_cap ≥ mediana di t_q dei transitori confermati dal test D nei real start (**250 s**);
2. T_cap ≥ punto medio del tempo di adattamento operativo da letteratura (**255 s**, AMT 2024);
3. T_cap ≥ 10 τ intrinseco del sensore ventilato (≈ **100 s**);
4. l'eccesso di |offset| nei 300–600 s degli avvii cold rispetto agli pseudo-start non è sistematico: IC che include 0 e punto ≤ 1 quanto (0,1 °C).

**Motivazione della scelta della mediana (non del p90).**
- I transitori lunghi sono individualmente rilevabili e vanno gestiti con un'eccezione (E1), non imponendo a tutte le sessioni una finestra lunga. Il 77 % dei real start (23/30) non ha alcun transitorio.
- Usare il p90 (~800–1000 s) toglierebbe 10–15 min a ogni sessione per proteggersi da 1–2 casi, di cui uno ambiguo (06-04).

**Applicazione meccanica:**

| Soglia | Esito |
|---|---|
| 120 s | fallisce le condizioni 1 e 2 |
| 180 s | fallisce le condizioni 1 e 2 |
| **300 s** | soddisfa 1, 2 e 3; condizione 4 verificata (+0,10 °C, IC [−0,18; 0,32]) |

**→ T_cap = 300 s.**

**C-E1 (attivazione dell'eccezione "transitorio confermato").**
- Condizioni: tasso di falsi positivi del test D sugli pseudo-start **≤ 10 %** e tasso nei real start maggiore di quello negli pseudo-start.
- Esito attuale: **3/29 = 10,3 %**. La condizione non è soddisfatta in senso stretto, e la differenza real/pseudo non è significativa (p = 0,16).
- **→ E1 NON attiva in v0.3.** È pre-registrata come eccezione condizionata a un test prospettico (AT-E1).

**C-E2 (eccezione "warm start").**
- Per accorciare la finestra servono 0 transitori su ≥ 10 warm start e un eccesso di offset ≤ 0,1 °C.
- Esito attuale: n = 4, eccesso non nullo (con bias di selezione).
- **→ E2 NON adottata.** Ipotesi da testare (AT-E2).
- Allungare la finestra per i warm start non ha base fisica (0/4 transitori), quindi è escluso.

## 5. Regola proposta (v0.3, da implementare solo dopo approvazione)

```
primo segmento della sessione (segmenti successivi: invariato, qc_segment_restart_recovery WARNING_ONLY)
if segment_too_short:              flag tutto il segmento                 (invariato)
elif stabilità confermata a t_c:   flag t < min(t_c, 300 s)               (NUOVO: cap anche per conferma tardiva)
else (STABILIZATION_NOT_REACHED):  flag t ≤ 300 s                         (invariato)
[E1, condizionata, NON attiva]: se test D positivo → flag t ≤ min(ceil30(t_q), 900 s)
[E2, non adottata]:             warm start (gap ≤ 15 min) → nessuna modifica
[E3, solo sensibilità]:         cap misurato su tempo ventilato           → non adottata
```

- **Parametri invariati:** pendenza 0,02 °C/s, min_stable 60 s, ventilazione 7 km/h / 20 s. La severità resta EXCLUDE_RECOMMENDED.
- **Unica modifica:** il cap di 300 s si applica anche alla conferma tardiva. È la stessa logica di P-0527, qui motivata fisicamente.

**Conteggi attesi** (in-memory, `e0/run_warmup_prereg_rules.py`, non R):

| Variante | Righe warm-up | keep_recommended |
|---|---|---|
| v0.2 attuale (nessun cap sulla conferma) | 13.148 | 59.209 |
| cap 120 | 4.834 | 67.465 |
| cap 180 | 6.807 | 65.498 |
| **cap 300 (proposta)** | **10.114** | **62.191** |
| cap 600 | 16.289 | 56.072 |
| cap 300 + E1 (condizionata) | 11.099 | 61.208 |

- **Campagne che cambiano con la proposta (8; le altre 47 sono identiche bit per bit a v0.2):**

  | Campagna | v0.2 → cap 300 (righe) |
  |---|---|
  | 02-20 12:54 | 802 → 297 |
  | 05-27 13:08 | 1.395 → **225** |
  | 06-20 08:29 | 634 → 210 |
  | 7-22 09:17 | 700 → 242 |
  | 05-27 18:39 | 387 → 237 |
  | 07-04 10:15 | 240 → 225 |
  | 7-30 07:42 | 323 → 218 |
  | 9-16 11:29 | 429 → 222 |

- La variante "cap 300" riproduce esattamente v0.2 in tutte le campagne con conferma ≤ 300 s o mai raggiunta. È verificato da un'asserzione nello script.

## 6. Test di accettazione e metriche (definiti in anticipo)

**Implementazione (bloccanti, prima di ogni uso):**
- **AT-1 Equivalenza.**
  - 47 campagne con flag warm-up identici a v0.2 bit per bit.
  - Le 8 campagne della §5 con esattamente i conteggi attesi.
  - Totale: 10.114 righe warm-up, keep_recommended 62.191.
  - 0 discordanze riga per riga con `rules/warmup_rule_variants_points.parquet`, colonna `stab_cap300`.
- **AT-2 Limite.** Nessuna riga di `qc_sensor_stabilization` con t > 300 s dall'inizio del primo segmento, salvo `segment_too_short`.
- **AT-3 Caso 05-27 13:08.** 225 righe di warm-up (t < 300 s). Nessuna altra flag di questa campagna cambia.
- **AT-4 Non-regressione.**
  - Nessuna altra flag, severità o segmentazione cambia (diff di tutte le colonne diverse da warm-up e keep = 0).
  - Flag table e keep coincidono per costruzione (0 discordanze, 3 profili).
  - Suite completa verde.
  - Copie dello schema byte-identiche.
- **AT-5 Unit test della regola**, su serie sintetiche:
  - conferma a 100 s → flag fino a 100 s;
  - conferma a 900 s → 300 s;
  - mai confermata → 300 s;
  - segment_too_short → intero segmento;
  - il gate di ventilazione resta invariato;
  - E1 disattivata di default (nessun effetto anche con un transitorio sintetico).

**Metriche di validazione fisica (riportate, soglie fissate ora):**
- **AT-6 Residuo dopo il warm-up.** Sugli avvii cold, l'eccesso di |offset| 300–600 s rispetto agli pseudo-start deve avere un punto ≤ 0,1 °C e un IC 95 % che include 0. Valore attuale: +0,10 [−0,18; 0,32] → **superato** (al limite).
- **AT-7 Copertura dei transitori.** Quota dei transitori D confermati con t_q ≤ 300 s ≥ 50 %. Valore attuale: 4/7 = 57 % → superato.
  - I tre casi oltre 300 s (9-16 11:29 a 332 s, 03-04 a 644 s, 06-04 a 995 s) vanno elencati come rischio residuo noto.

**Prospettici (su campagne nuove, dopo il 09/11/2026; non usano R):**
- **AT-E1 (attivazione di E1).** Servono ≥ 20 nuovi real start con primo segmento ≥ 1200 s e i relativi pseudo-start. E1 entra in una versione successiva solo se valgono **entrambe** le condizioni:
  - falsi positivi pseudo ≤ 10 %;
  - real > pseudo, Fisher unilaterale p < 0,05.
- **AT-E2 (warm start).** Servono ≥ 10 nuovi warm start (gap ≤ 15 min). Si valuta un cap ridotto a 120 s per i warm start solo se valgono entrambe le condizioni:
  - 0 transitori D;
  - eccesso 0–300 s ≤ 0,1 °C.
- **AT-8 (R non è criterio).** Dopo l'implementazione, P1 va rieseguito e ΔR riportato, **ma nessun esito su R può confermare, modificare o respingere la regola.** Una decisione motivata da R invalida questa pre-registrazione.

## 7. Analisi di sensibilità

### 7.1 Termica (fase A)
- **Soglie 120/180/300/600 s e nessun cap:** vedi conteggi in §5 e profilo degli offset in §3.2.
  - Con 120–180 s resterebbe non marcato il transitorio 9-16 18:36 (t_q 250 s), coperto da 300 s.
  - 600 s aggiunge ~6.200 righe (+61 %) per coprire 1 solo transitorio in più (9-16 11:29, 332 s); 03-04 (644 s) e 06-04 (995 s) resterebbero comunque scoperti.
- **Soglie del test D (nota):** il p95 di |b| sugli pseudo-start con il modello originale era 4,26 °C. Con il criterio di decadimento (condizione 5) i falsi positivi scendono a 3/29.

### 7.2 Varianti non adottate
- **E3**, cap su tempo ventilato: con una quota ventilata mediana di 0,82 equivale a ~365 s di tempo totale, quindi un effetto piccolo. Resta solo sensibilità.
- **E1 condizionata:** +985 righe su 4 campagne (03-04 +352, 06-04 +590, 9-16 11:29 +43; 02-20, 02-21, 07-04 14:37 e 9-16 18:36 già coperte).

### 7.3 Impatto su R (fase B, puramente descrittivo)
**Calcolato dopo il commit di fase A `bbc3121`. Non usato per la scelta (AT-8).**
- Script: `e0/run_warmup_prereg_threshold_sensitivity.py`.
- Output: `r_sensitivity_descriptive/warmup_threshold_R_descriptive.csv`.
- Metodo: P1 diff-day, 1000 bootstrap, varianti centered/detrended/detr_alt, popolazione completa e senza cv2_004.
- La variante "nessun cap" riproduce `keep_recommended` v0.2 con 0 discordanze.

**Popolazione comune** (stesse celle per tutte le 6 varianti): |ΔR| ≤ 0,012 rispetto a v0.2 in tutte le combinazioni. L'IC di ΔR include 0 in tutte tranne una: cap 600, route, detr_alt, senza cv2_004, ΔR −0,012 [−0,041; −0,001].
→ La soglia di warm-up **non cambia** la ripetibilità a parità di celle.

**Popolazione propria, R route centered (diff-day):**

| Variante | tutte: R [IC 95 %] | senza cv2_004: R [IC 95 %] |
|---|---|---|
| v0.2 (nessun cap sulla conferma) | 0,34 [0,09; 0,50] | 0,12 [−0,07; 0,31] |
| cap 120 | 0,39 [0,19; 0,50] | 0,17 [−0,02; 0,33] |
| cap 180 | 0,42 [0,22; 0,53] | 0,19 [0,00; 0,35] |
| **cap 300 (proposta)** | **0,43 [0,19; 0,56]** | **0,16 [−0,05; 0,34]** |
| cap 600 | 0,40 [0,08; 0,56] | 0,12 [−0,12; 0,31] |
| cap 300 + E1 | 0,43 [0,22; 0,56] | 0,16 [−0,04; 0,34] |

- **Spatial block centered:** 0,22–0,27 per tutte le varianti; senza cv2_004, 0,21–0,25.
- Le differenze tra popolazioni proprie dipendono dal numero di coppie (593–908 su route) e non dalla soglia.
- Tutti gli IC si sovrappongono ampiamente. Senza cv2_004 l'IC di route include 0 per quasi tutte le varianti.
- **Nessuna conclusione su R** è tratta o usabile per la scelta della soglia.

## 8. Limiti scientifici
1. **Campione piccolo:** 30 real start ≥ 1200 s, 29 pseudo-start da 11 campagne, 7 transitori. Le differenze real/pseudo non sono significative (Fisher p = 0,16; IC degli eccessi che includono 0 salvo warm 60–120 s).
2. **Confondimento:** inizio sessione = spesso uscita da garage/città. La variabilità di percorso nei primi minuti non è separabile da un transitorio strumentale senza un riferimento fisso o un secondo sensore co-locato, che non è disponibile.
3. **Bias di selezione:** il gruppo warm (n = 4) contiene 3 campagne scelte *perché* colpite. I suoi eccessi non sono stimatori di un effetto warm.
4. **Proxy dell'accensione:** il gap tra sessioni non equivale al tempo dall'accensione. Mancano log di accensione, temperatura interna, Tir/Tsur e tensioni.
5. **Quantizzazione a 0,1 °C:** limita la risoluzione delle pendenze (minimo non nullo 0,025 °C/s sulla mediana a 3 righe) e di t_q (definito su 1 quanto).
6. **Gradi di libertà del ricercatore:** il test D e il criterio C-cap sono stati fissati dopo aver visto la tabella termica, ma prima di R. E1 è condizionata a un test prospettico proprio per questo.
7. **Riferimento 600–1200 s:** non è "verità": include variabilità ambientale. Gli pseudo-start la stimano solo in media.
8. **Dispositivi e stagioni sbilanciati:** prevalgono AC4D162B317E e B6CCF894. Nessun confronto tra dispositivi.
9. **Letteratura:** un solo studio indipendente (AMT 2024) e il manuale del produttore. La costante di tempo non è stata misurata da noi (resta nei "Prossimi passi": prova controllata del ritardo del sensore).
10. **LST ≠ Tair:** nessuna inferenza su LST da questi dati.

## 9. Riproducibilità
- `e0/run_warmup_prereg_evidence.py <OUT>`: evidenza termica (`evidence/`). Seed bootstrap 20261109, 2000 repliche.
- `e0/run_warmup_prereg_rules.py <OUT>`: varianti di regola in memoria (`rules/`), con asserzioni di equivalenza a v0.2.
- Input in sola lettura: `outputs/e0R_qc_split_20261109T1240/recommended/` (policy v0.2 recommended). Nessun file in `data/raw` toccato; nessun output storico sovrascritto.
- Figure:
  - `evidence/fig_affected_traces.png`: tracce delle 4 campagne colpite e dei riferimenti;
  - `evidence/fig_offset_and_transient.png`: profilo degli offset e transitori D.