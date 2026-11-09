# PROTOCOLLO DI MISURA — Costante di tempo e tempo di stabilità del MeteoTracker (warm-up) — v1

**Versione 1, 09/11/2026.** Redatto dopo la decisione di Marco delle 15:31 (`e0/DECISIONE_CAP_WARMUP_20261109.md`): il principio del cap è approvato, il valore numerico è aperto.
- **Scopo:** misurare in campo, con un termometro di riferimento indipendente:
  1. la costante di tempo τ del MeteoTracker (MT) ventilato;
  2. il tempo necessario perché l'errore dovuto al warm-up scenda sotto il requisito di accuratezza, nei tre stati di partenza (freddo, intermedio, già caldo).
- **Il valore del cap si decide solo sui dati strumentali di questo protocollo**, con la regola fissata in anticipo in `e0/PROPOSTA_VALIDAZIONE_TAU_v1.md`. R di P1 è escluso.
- **Esecuzione:** Marco, in campo. Analisi: `e0/tau_warmup_analysis.py` (scheletro già testato su dati sintetici).
- Nessun dato raw esistente viene toccato. I nuovi file vanno in una cartella separata (§9.3).

---

## 0. Definizioni
- **MT:** MeteoTracker sotto test (preferibilmente AC4D162B317E; B6CCF894 per almeno 5 partenze a freddo come controllo tra dispositivi).
- **REF:** termometro di riferimento indipendente (§3).
- **Gruppi di partenza** (gap = tempo dalla fine dell'ultima sessione o dallo spegnimento, con il MT dove viene normalmente riposto):
  - **COLD:** gap > 120 min;
  - **INTERMEDIATE:** gap 15–120 min;
  - **WARM:** gap ≤ 15 min, con il sensore rimasto montato o comunque non riposto al chiuso.
- **Istanti:**
  - `t_out`: il MT lascia il luogo di conservazione;
  - `t0`: avvio della sessione nell'app (o istante del gradino nel test STEP);
  - `t_move`: primo dato a ≥ 7 km/h.
- **Errore:** e(t) = T_MT(t) − T_REF(t), su asse UTC comune, in medie a blocchi di 10 s.
- **Offset finale:** e_∞ = mediana di e(t) nella finestra 900–1500 s dopo t0. È il bias stazionario del MT (AMT 2024: +0,3–0,5 °C), **non** fa parte del warm-up.
- **Tempo di stabilità:** t_s(ε) = inizio del primo blocco di 10 s dopo il quale ogni blocco fino a 900 s soddisfa |e − e_∞| ≤ ε.

## 1. Test A — gradino termico controllato (misura di τ)

**Obiettivo:** τ del MT ventilato a 20 km/h equivalenti (5,6 m/s), la condizione della specifica del produttore.

### 1.1 Setup
- **Ambiente A:** locale chiuso a temperatura stabile (riscaldamento acceso, porte chiuse), es. 20–22 °C.
- **Ambiente B:** esterno all'ombra (cortile o balcone esposto a nord, lontano da muri caldi e scarichi), con **|T_A − T_B| ≥ 5 °C (obiettivo ≥ 8 °C)**. In novembre–febbraio questo è normale.
- **Ventilatore in ciascun ambiente** (oppure lo stesso, spostato insieme al supporto): velocità dell'aria alla presa dei sensori **5,6 ± 0,6 m/s**, misurata con l'anemometro portatile prima di ogni test e annotata.
- **Supporto unico** (tavoletta o asta) che porta MT e presa del REF:
  - distanza tra le prese ≤ 10 cm, stessa altezza ±2 cm;
  - flusso del ventilatore frontale a entrambe;
  - nessuno dei due nella scia dell'altro.
- **App MT:**
  - "Static mode" **ON**, perché da fermo la Guard Time non acquisirebbe nulla;
  - intervallo di acquisizione al minimo consentito (1 s), distanza al minimo;
  - annotare nome e versione dell'app.
- **REF:** logging a 1 Hz, orologio sincronizzato a UTC (§3.4).

### 1.2 Procedura (una coppia = 2 test, discesa e risalita)
1. Accendere il REF, sincronizzare l'orologio e annotare l'offset. Avviare la sessione MT con il supporto nell'ambiente A e il ventilatore acceso.
2. **Equilibrio in A** per ≥ 30 min, finché sia il REF sia il MT hanno un'escursione ≤ 0,1 °C negli ultimi 5 min.
3. **Gradino A → B** (STEP_DOWN se B è più freddo):
   - spostare il supporto in ≤ 5 s davanti al ventilatore di B;
   - annotare l'ora UTC al secondo (`t0`), presa dall'app GPS/orologio del telefono.
4. Restare in B per **20 min** (≥ 25 volte il τ massimo documentato di 43 s).
5. **Gradino B → A** (STEP_UP): stessa procedura, 20 min in A.
6. Chiudere la sessione MT ed esportare il CSV. Scaricare il CSV del REF. Ricontrollare l'offset dell'orologio del REF (deriva).

### 1.3 Numero di ripetizioni
- **10 test a 5,6 m/s** (5 coppie: 5 discese e 5 risalite).
- **3 test di sensibilità a 2 m/s** (circa 7 km/h, la soglia di ventilazione del rilevatore).
- **Motivazione di n:**
  - si ipotizza un coefficiente di variazione di τ tra ripetizioni CV ≈ 20 %;
  - con n = 10, la semiampiezza dell'IC 95 % della media è t(0,975; 9)·0,20/√10 ≈ **±14 %** di τ;
  - il limite superiore unilaterale al 95 % è circa +12 %;
  - questa precisione basta per la decisione: anche con τ = 43 s il limite fisico τ_UCB·ln(ΔT/0,2) varia di meno di 30 s tra τ e τ_UCB per ΔT ≤ 20 °C.
- **Controllo intermedio pre-fissato:** se dopo i primi 5 test il CV osservato è > 30 %, portare n a 15.

### 1.4 Stima di τ e incertezza
- **Modello del primo ordine**, con il REF come ingresso (il REF è molto più veloce):
  - MT(t) = F_τ[REF(t − d)] + y0·e^(−t/τ) + b;
  - F_τ è il filtro del primo ordine, d il ritardo di sincronizzazione (0–5 s), b il bias.
- **Stima:** griglia su τ (1–200 s, passo 0,5 s) e su d; minimi quadrati lineari per y0 e b; si sceglie il minimo dell'errore quadratico (`fit_first_order`). Il modello usa l'andamento reale del REF, quindi non richiede che l'ambiente B sia perfettamente costante.
- **Incertezza del singolo test:** bootstrap a blocchi mobili dei residui (blocchi di 30 s, 200 repliche), IC 95 % percentile.
- **Incertezza tra test:**
  - media e IC 95 % t di Student;
  - τ_UCB95 = limite superiore unilaterale al 95 % della media;
  - si riportano anche il massimo, e discesa e risalita separate (asimmetria).
- **Correzione per il REF:** se REF ha costante τ_REF, il τ stimato vale circa τ_MT − τ_REF. Si riporta τ_MT = τ_fit + τ_REF, con τ_REF da scheda tecnica (§3.1) aggiunto all'incertezza.
- **Validità del singolo test:**
  - ΔT ≥ 5 °C;
  - aria 5,6 ± 0,6 m/s (o 2 ± 0,3 m/s per la sensibilità);
  - equilibrio iniziale raggiunto;
  - trasferimento ≤ 5 s;
  - RMSE del fit ≤ 0,10 °C;
  - |d| ≤ 5 s.
  
  Un test non valido viene registrato (`valid=N`, con il motivo), non cancellato, e va ripetuto.

## 2. Test B — partenze reali su strada (tempo di stabilità per l'uso previsto)

**Obiettivo:** la distribuzione di t_s(0,2 °C) nelle tre condizioni di partenza, nell'uso reale (MT magnetico sul tetto, auto in movimento). Il transitorio reale comprende anche la massa termica di custodia e supporto e l'ambiente di conservazione, non solo il τ dell'elemento sensibile. Per questo il Test A da solo non basta.

### 2.1 Setup
- **Percorso fisso "TAU-R1"**, scelto da Marco e da usare sempre uguale:
  - anello periurbano di ≥ 25 min a 30–50 km/h;
  - dislivello ≤ 30 m;
  - senza gallerie o sottopassi;
  - meno semafori possibile;
  - **i primi 15 min senza soste > 60 s.**
  
  Annotare il percorso con un identificativo (es. TAU-R1).
- **MT** sul tetto nella posizione abituale delle campagne.
- **Presa del REF** in schermo aspirato (§3.2), montata sul tetto:
  - a 10–20 cm di lato dal MT, stessa altezza ±5 cm;
  - ≥ 30 cm dal bordo anteriore del tetto;
  - nessuno dei due nella scia dell'altro (affiancati, perpendicolari al moto).
- **Logger di conservazione** (STO): piccolo logger (±0,2 °C, 1 campione/min) **sempre insieme al MT** dove viene riposto. Misura la temperatura di partenza del sensore, da cui ΔT0 = T_STO(t_out) − T_REF(t_out).
- **App:** "Static mode" **OFF** (uso normale), intervallo 1 s. Annotare se la Guard Time ritarda l'inizio dei dati (`t_move` rispetto al primo dato).

### 2.2 Procedura di una "tripla" (1 COLD + 1 WARM + 1 INTERMEDIATE, circa 3 h)
1. **Preparazione (−15 min):**
   - montare il REF sul tetto, accendere schermo aspirato e logger;
   - lasciarlo all'aria **≥ 10 min**, perché anche il REF deve essere in equilibrio;
   - sincronizzare l'orologio e annotare l'offset.
2. **COLD:** il MT è conservato da > 120 min (es. tutta la notte) nel luogo abituale.
   - Prendere il MT (`t_out`), montarlo e avviare la sessione (`t0`), partire entro 60 s.
   - Guidare TAU-R1 per **≥ 25 min**, 30–50 km/h.
   - Chiudere la sessione.
3. **WARM:** fermarsi 5–10 min con il MT **lasciato montato** (o in macchina, annotare dove), poi nuova sessione: altri 25 min su TAU-R1.
4. **INTERMEDIATE:** smontare il MT e riporlo nel luogo abituale (con il logger STO) per **30–90 min**, poi rimontarlo (`t_out`): terza sessione di 25 min.
5. Esportare i 3 CSV del MT e il CSV del REF (uno solo per tutta la mattina va bene). Scaricare il logger STO. Ricontrollare l'offset dell'orologio del REF.

Una **"singola"** è il solo passo 2 (COLD), circa 1 h compresa la preparazione.

### 2.3 Numero di partenze per gruppo
**Regola usata per giustificare n:** si stima la frazione p di partenze con t_s(0,2) > T (T = soglia candidata). Il criterio (PROPOSTA §3) richiede p̂ ≤ 10 % e limite superiore unilaterale al 95 % (Clopper–Pearson) ≤ 20 %.

| n | UCB95 con 0 superamenti | con 1 | con 2 | con 3 |
|---|---|---|---|---|
| 10 | 25,9 % | 39,4 % | — | — |
| 20 | 13,9 % | 21,6 % | 28,3 % | 34,4 % |
| 30 | 9,5 % | 14,9 % | 19,5 % | 23,9 % |

- **COLD, n = 20 (fase 1), estendibile a 30 (fase 2, una sola volta).**
  - È il caso fisicamente peggiore e quello che governa il cap.
  - Con 20 partenze si può accettare una soglia solo con 0 superamenti. Con 30 se ne tollerano fino a 2.
  - L'estensione si fa solo se la fase 1 è ambigua (PROPOSTA §4).
- **INTERMEDIATE n = 10, WARM n = 10.**
  - Servono a verificare che il cap scelto per COLD valga anche per loro (criterio C2: p̂ ≤ 20 %) e a fornire la stima descrittiva (con 0/10 l'UCB è 26 %).
  - n = 10 per WARM coincide con AT-E2 della pre-registrazione.
- **Totale fase 1:** 10 triple (10 COLD + 10 WARM + 10 INTERMEDIATE) + 10 singole COLD = **20 COLD, 10 WARM, 10 INTERMEDIATE**.
- **Controllo tra dispositivi:** almeno 5 delle 20 COLD con B6CCF894 se disponibile (descrittivo).

## 3. Termometro di riferimento indipendente — requisiti

### 3.1 Sensore e logger
- **Elemento:** Pt100/Pt1000 classe 1/10 DIN a film sottile, oppure termistore o termocoppia tipo T a filo sottile, con logger dedicato.
- **Accuratezza:** **±0,1 °C (k = 2) tra −10 e +40 °C** (sensore + logger).
- **Taratura:** certificato di taratura **riferibile** (centro LAT/ACCREDIA o ISO/IEC 17025) di non più di 12 mesi, con almeno 2 punti nel campo di lavoro (es. 0 °C e 20 °C).
  - Se manca il certificato: verifica propria a 0 °C (bagno ghiaccio-acqua distillata) e a temperatura ambiente contro un termometro tarato. In questo caso l'accuratezza da usare nel budget è ±0,15 °C.
- **Risoluzione:** ≤ 0,01 °C.
- **Tempo di risposta: τ_REF ≤ 5 s** in aria a ≥ 3 m/s (da scheda tecnica; altrimenti misurarlo con il Test A sul solo REF contro un secondo sensore più veloce). Deve essere almeno 5 volte più piccolo del τ atteso per il MT (≤ 43 s).
- **Logging:** **≥ 1 Hz** con timestamp memorizzato (non solo l'indice di campione).

### 3.2 Schermo dalla radiazione e ventilazione
- Schermo **aspirato** (ventola propria) con velocità dell'aria interna **≥ 3 m/s**, alimentato a batteria per almeno 4 h. Il REF non deve dipendere dalla velocità del veicolo.
- In alternativa per i soli test a veicolo fermo (Test A): sonda nuda all'ombra davanti al ventilatore del test.
- Sotto sole diretto, lo schermo aspirato deve mantenere l'errore radiativo ≤ 0,1 °C (dato del produttore dello schermo).

### 3.3 Montaggio accanto al MT
- **Su strada:** supporto magnetico o barre portatutto.
  - Presa del REF a 10–20 cm di lato dal MT, stessa altezza ±5 cm, nessuno dei due nella scia dell'altro.
  - Annotare separazione e dislivello (cm) sulla scheda.
- **Test A:** sullo stesso supporto, prese a ≤ 10 cm.
- Fotografare il montaggio a ogni giornata (`data/tau_tests/photos/`).

### 3.4 Sincronizzazione temporale
- Il MT riceve l'ora dallo smartphone; i CSV hanno l'ora con offset, convertita in UTC dallo script.
- Prima e dopo ogni giornata: sincronizzare l'orologio del REF con NTP o GPS, poi registrare **offset_pre** e **offset_post** = orologio del REF − UTC, confrontati con il riferimento a ±0,5 s (es. un'app di ora GPS).
- **Requisito:** incertezza di sincronizzazione ≤ 1 s. Lo script stima inoltre il ritardo residuo d dal fit (Test A) o dalla correlazione incrociata delle fluttuazioni nella fase stabile (Test B). Se |d| > 5 s il test non è valido.

## 4. Condizioni ambientali — matrice minima

Matrice minima fattibile per le **COLD di fase 1** (2 × 2, 5 partenze per cella):

| Cella | Cielo all'avvio | ΔT0 = T_conservazione − T_esterna |
|---|---|---|
| C1 | sole sul sensore (radiazione diretta) | |ΔT0| ≥ 5 °C |
| C2 | sole sul sensore | |ΔT0| < 5 °C |
| C3 | coperto, notte o ombra continua | |ΔT0| ≥ 5 °C |
| C4 | coperto, notte o ombra continua | |ΔT0| < 5 °C |

- **Velocità:** standard su TAU-R1 (30–50 km/h). In più, **4 partenze COLD facoltative su strada veloce (≥ 70 km/h)**, solo descrittive.
- **Vento:** annotato (calmo / moderato / forte), non controllato.
- **Pioggia:** **esclusa**. Il sensore bagnato invalida il test.
- **Stagioni:**
  - **inverno** (fase 1, novembre–febbraio): ΔT0 tipicamente positivo (sensore più caldo dell'esterno);
  - **estate** (blocco di conferma, giugno–luglio 2027): **10 COLD**, tra cui ≥ 5 con ΔT0 negativo (sensore conservato al fresco o con aria condizionata, esterno caldo) e ≥ 5 con sole.
  
  La decisione dopo l'inverno è **provvisoria**. Diventa definitiva dopo il blocco estivo (PROPOSTA §4.4).
- WARM e INTERMEDIATE non hanno vincolo di cella. Si registrano le condizioni.

## 5. Requisito di accuratezza e tempo di stabilità

- **Requisito primario: |e(t) − e_∞| ≤ ε = 0,2 °C.** Motivazione:
  1. 0,2 °C è l'accuratezza tipica dichiarata dal produttore per l'elemento sensibile ("+/- 0.2° C … (typ, sensors)", Device User Manual 2023-07-04). Un errore da warm-up entro ε non supera l'errore strumentale dichiarato.
  2. Sono 2 quanti di risoluzione (0,1 °C).
  3. È **maggiore dell'incertezza estesa del confronto** (U ≈ 0,11 °C, §6.1), quindi è misurabile in modo affidabile.
- **Requisito secondario (solo riportato): ε = 0,1 °C**, cioè un quanto. È confrontabile con U, quindi non è risolvibile in modo affidabile e non si usa per la decisione.
- **Riferimento a e_∞** (non a 0): il bias stazionario (+0,3–0,5 °C secondo AMT 2024) è una proprietà di calibrazione e radiazione, non del warm-up. Il cap riguarda solo il transitorio.
- **Grandezze riportate per ogni partenza:**
  - t_s(0,2), t_s(0,1);
  - ΔT0;
  - |e(t0+60 s) − e_∞|;
  - quota di tempo ventilato (≥ 7 km/h) nei primi 300 s.

## 6. Criteri di accettazione e incertezza di misura (fissati in anticipo)

### 6.1 Budget di incertezza su e(t) − e_∞ (incertezze tipo, blocchi di 10 s)

| Componente | Base | u (°C) |
|---|---|---|
| REF: ripetibilità e deriva in 25 min (l'offset costante si annulla con e_∞) | scheda/taratura | 0,02 |
| Quantizzazione MT (0,1 °C) | 0,1/√12 | 0,029 |
| Sincronizzazione (≤ 1 s) × velocità di variazione nel transitorio (≤ 0,03 °C/s, AMT: 0,5–1,7 °C/min) | 0,03·1/√3 | 0,017 |
| Separazione spaziale (10–20 cm, stessa altezza) | da verificare: dev. std di e nella finestra 900–1500 s | 0,03 (ipotesi) |
| Stima di e_∞ (mediana su 600 s) | | 0,02 |
| **Combinata u_c** | somma quadratica | **0,053** |
| **Estesa U (k = 2)** | | **≈ 0,11** |

- Se la deviazione standard osservata di e (blocchi di 10 s) nella finestra finale supera 0,10 °C, la separazione spaziale o il montaggio non sono adeguati e la partenza **non è valida**.
- Per il Test A, l'incertezza di τ è quella bootstrap e tra-test (§1.4), più τ_REF.

### 6.2 Validità di una partenza su strada (Test B)
- Dati completi di MT e REF da t0 a t0 + 1500 s.
- Velocità ≥ 20 km/h per ≥ 80 % dei primi 900 s, e nessuna sosta > 60 s nei primi 600 s.
- Niente pioggia.
- Gap e luogo di conservazione registrati; per COLD e INTERMEDIATE, logger STO presente.
- Offset dell'orologio del REF noto (pre e post) e ritardo residuo |d| ≤ 5 s.
- Dev. std di e nella finestra 900–1500 s ≤ 0,10 °C.

Le partenze non valide si **registrano e contano** (`valid=N` + motivo) e si ripetono. Non vengono cancellate.

### 6.3 Criteri di accettazione del protocollo nel suo complesso
- Test A: almeno 10 test validi a 5,6 m/s.
- Test B: almeno 20 COLD valide (≥ 5 per cella della §4), 10 WARM e 10 INTERMEDIATE.
- U ≤ 0,15 °C, verificata con i dati della finestra finale.
- Se uno di questi criteri non è soddisfatto, **non si decide** e si completano le misure.

## 7. Confronto 300 s / 600 s (solo evidenza strumentale)
Per ciascuna soglia candidata T ∈ {120, 180, 300, 600} s (300 e 600 sono quelle in discussione):
- frazione di partenze con t_s(0,2) > T, per gruppo, con IC Clopper–Pearson;
- per cella della matrice, la stessa frazione;
- **limite fisico:** τ_UCB95 · ln(ΔT0_p95 / 0,2), dove ΔT0_p95 è il 95° percentile di |ΔT0| nelle COLD;
- **errore residuo al tempo T:** distribuzione di |e(T) − e_∞|, mediana e massimo.

**Non sono criteri:** R di P1, il numero di punti persi nel dataset e ogni metrica di ripetibilità. Il numero di punti persi si può riportare come informazione accessoria, chiaramente separata.

## 8. Cosa NON fa questo protocollo
- Non tocca `data/raw`, i manifest, le config, il codice QC o le severità.
- Non implementa v0.3 e non dichiara nessuna QC ufficiale.
- Non valuta il bias stazionario del MT, che appartiene a un'altra analisi.

---

## 9. Parte pratica per Marco

### 9.1 Checklist attrezzatura
- [ ] MeteoTracker AC4D162B317E (+ B6CCF894 se disponibile), carichi; smartphone con app; annotare nome e versione dell'app.
- [ ] **Termometro di riferimento** con i requisiti della §3.1: sonda veloce, logger a 1 Hz, certificato di taratura.
- [ ] **Schermo aspirato** con ventola a batteria (≥ 3 m/s) + supporto magnetico o barre per il tetto.
- [ ] **Logger di conservazione** STO (±0,2 °C, 1/min).
- [ ] **Anemometro portatile** (a elica o a filo caldo, ±0,2 m/s o 3 %).
- [ ] **Ventilatore** regolabile (meglio 2, uno per ambiente) + supporto unico per MT e sonda REF (Test A).
- [ ] App di ora GPS/NTP sul telefono (orario al secondo); metro a nastro; fascette; nastro.
- [ ] Schede di campo stampate (§9.5) o il file `TAU_SHEETS.csv` sul telefono/portatile.

### 9.2 Quante sessioni e quanto tempo

| Blocco | Contenuto | Durata stimata |
|---|---|---|
| Preparazione | taratura o verifica del REF a 0 °C, prova di montaggio, scelta del percorso TAU-R1 | ~4 h (una tantum) |
| Test A (gradini) | 5 coppie a 5,6 m/s (10 test) + 3 test a 2 m/s; circa 80 min per coppia | **~9 h** (2 mezze giornate) |
| Test B fase 1 | 10 triple (~3 h l'una) + 10 singole COLD (~1 h l'una) | **~40 h** (circa 20 mattine; 1 COLD al giorno, dopo la conservazione notturna) |
| Fase 2 (solo se ambigua) | +10 singole COLD | ~10 h |
| Blocco estivo di conferma (giu–lug 2027) | 10 singole COLD (≥ 5 con ΔT0 negativo, ≥ 5 con sole) | ~10 h |
| **Totale** | | **circa 60 h** (+10 h se serve la fase 2), distribuite su 5–8 settimane in inverno + 2 settimane in estate |

- **Sessioni MT totali:** Test A 13 + fase 1 su strada 40 (20 COLD, 10 WARM, 10 INTERMEDIATE) + estate 10 = **63 sessioni**, più fino a 10 per la fase 2.

### 9.3 Dove mettere i file
- Cartella nuova: **`D:\projects\Meteotracker\data\tau_tests\`**, con sottocartelle `step\`, `field\`, `photos\` e il foglio `TAU_SHEETS.csv`.
- **NON in `data\raw\`:** quella cartella viene scansionata ricorsivamente da ingestione, inventario, pipeline e GUI (`ingestion.py`, `inventory.py`, `pipeline.py`, `application.py`), che tratterebbero i test come campagne.
- Non aggiungere i test a `data/manifests/campaign_manifest.csv`.
- **Git:** `data/tau_tests/` oggi **non** è in `.gitignore`. Non fare `git add` su quella cartella. Una riga di `.gitignore` si può aggiungere con un'autorizzazione separata.
- I CSV del MT si esportano dalla piattaforma come per le campagne e **non si modificano**, si rinominano soltanto.

### 9.4 Nomi dei file
`TAU_<TIPO>_<AAAAMMGG>T<HHMM>Z_<DEVICE>_<GRUPPO><NN>_<FONTE>.csv`
- **TIPO:** `STEP` | `FIELD`.
- **Ora:** UTC dell'avvio (`t0`), con la Z.
- **GRUPPO:**
  - Test A: `DOWN` / `UP` (`DOWN2` / `UP2` a 2 m/s);
  - Test B: `COLD` / `WARM` / `INTER`.
- **NN:** numero progressivo nel gruppo (01, 02, …).
- **FONTE:** `MT` (MeteoTracker) | `REF` (riferimento) | `STO` (logger di conservazione).

Esempi:
- `TAU_FIELD_20261112T0645Z_AC4D162B317E_COLD01_MT.csv`
- `TAU_FIELD_20261112T0645Z_AC4D162B317E_COLD01_REF.csv`
- `TAU_STEP_20261114T1000Z_AC4D162B317E_DOWN01_MT.csv`

Il CSV del REF deve avere le colonne `time_utc` (ISO 8601 con Z) e `temp_c`. Se il logger esporta in un altro formato, salvare l'originale accanto con suffisso `_orig`.

### 9.5 Scheda di campo (una riga per test; modello in `e0/TAU_SHEETS_TEMPLATE.csv`)

| Campo | Esempio | Note |
|---|---|---|
| test_id | FIELD-COLD-01 | univoco |
| test_type | FIELD / STEP | |
| date_local | 2026-11-12 | |
| operator | Marco Ventura | |
| device_id | AC4D162B317E | |
| app_name_version | MeteoTracker+ x.y.z | |
| mt_interval_s / static_mode | 1 / OFF | ON solo nel Test A |
| group / rep | COLD / 01 | DOWN, UP, COLD, WARM, INTER |
| last_session_end_local | 2026-11-11 18:40 | per calcolare il gap |
| gap_min | 725 | |
| storage_location | casa, ingresso | dove era riposto il MT |
| storage_temp_c | 19,8 | dal logger STO a t_out |
| t_out_utc / t0_utc / t_move_utc | 06:43:10Z / 06:45:02Z / 06:45:40Z | ora GPS al secondo |
| ref_id / ref_cal_cert | PT1000-01 / LAT-xxxx 2026 | |
| ref_clock_offset_pre_s / post_s | +0,3 / +0,8 | orologio REF − UTC |
| air_speed_ms (STEP) | 5,6 | anemometro |
| sky | SUN / PARTLY / OVERCAST / NIGHT | |
| sun_on_sensor | Y / N | all'avvio |
| precip | N | se Y: test non valido |
| wind | calmo / moderato / forte | |
| t_out_approx_c | 7 | lettura del REF |
| cell | C1–C4 | §4 (solo COLD) |
| route_id | TAU-R1 | |
| speed_mean_kmh_first900 / stops_gt60s_first600 | 38 / 0 | |
| mount_sep_cm / mount_dz_cm | 15 / 2 | |
| file_mt / file_ref / file_sto | nomi dei file | |
| valid / invalid_reason | Y / — | non cancellare mai una riga |
| notes | | eventi: semafori lunghi, ombra, ecc. |