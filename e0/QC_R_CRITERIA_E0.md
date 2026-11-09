# E0-QC-R: criteri pre-registrati (09/11/2026)

**Stato:** PRE-REGISTRAZIONE. Questo documento è stato committato **prima** di:
- calcolare qualsiasi R di P1 sulle nuove maschere;
- fissare le severità della policy v0.2.

Autorizzazione: Marco, 9/11 alle 12:01 (via coordinatore). **Nessuna QC è dichiarata ufficiale.**

Fatti già noti prima di questo documento, dall'audit `outputs/qc_mask_audit_E0_20261109T1113`:
- 372 eventi dt = 0 aprono 372 dei 482 cambi segmento;
- `qc_unrealistic_acceleration` flagga il 25,7% dei punti;
- le severità della flag table e della policy divergono.

Nessun dato di P1 sulle nuove maschere è stato visto.

## 0. Principi generali (validi per tutte le regole)
1. **La severità si decide solo con evidenza sulla misura.** Le basi ammesse sono:
   - fisica del sensore: tempo di risposta e stabilizzazione;
   - entità dell'errore GNSS rispetto alla scala di analisi;
   - integrità dei timestamp.

   **Mai in base all'effetto su P1.** P1 non viene calcolato finché la policy v0.2 non è committata e l'audit delle maschere (passo E) non è superato. Il commit della policy usata è registrato nel summary di P1.
2. **Scala di analisi.**
   - Spaziale: celle di 50 m in P1 e blocchi di 500 m. Un errore di posizione < 25 m (mezza cella) è considerato **non influente** sull'assegnazione spaziale.
   - Termica: il dato grezzo ha risoluzione 0,1 °C. Un transitorio < 0,1 °C è considerato **non influente**.
3. **Incertezza.** Le curve empiriche e le quote hanno IC 95% con bootstrap per campagna (unità = `canonical_campaign_id`, 1000 repliche, seed 20261109).
4. **Archivi.** Restano intatti, e la nuova policy si seleziona con un parametro di config, non sovrascrivendo:
   - `config/flag_policy.csv`;
   - `config/qc_*.yaml`;
   - `e0/qc_flag_schema_E0_v0.1.yaml`;
   - gli output esistenti.
5. **Soglie delle regole decisionali.** Le soglie qui sotto (0,1 °C, 25 m, 50%, 2 m/s²) sono fissate ora. Se un dato le rende inapplicabili (per esempio troppi pochi eventi), il rapporto lo dichiara e la severità resta quella della policy v0.1. Le soglie non vengono riadattate a posteriori.

## R1. dt = 0 (timestamp duplicati) e segmentazione
- **Criterio fisico/logico (decide il codice).** Un nuovo segmento rappresenta un'interruzione reale dell'acquisizione:
  - `dt > soglia long gap` (5 × cadenza, ≥ 1 s);
  - oppure un salto all'indietro dell'orologio, `dt < 0`.

  Con dt = 0 non passa tempo in cui il sensore possa trovarsi in un ambiente diverso, quindi un «restart» è fisicamente impossibile. **dt = 0 non apre più un segmento.**
- **Gestione.**
  - `qc_duplicate_timestamp` (alias legacy `qc_time_duplicate`) resta il flag di entrambe le righe con lo stesso istante.
  - Nuovo `qc_duplicate_record`: riga con contenuto identico alla precedente (Lat, Lon, Temp, Hum, Alt, Press, Speed) **e** dt = 0. È una copia senza informazione nuova; si flagga solo la seconda copia e le successive.
  - Velocità e accelerazione da posizione non sono calcolabili a dt ≤ 0 e diventano NaN (niente divisione per zero).
- **Evidenza da riportare.**
  - Classi: copia esatta vs contenuto distinto (jitter di quantizzazione).
  - Pattern dei dt adiacenti, per esempio 2-0-2.
  - Continuità alla riga duplicata, confrontata con la distribuzione dei passi di 1 s: distanza e |ΔT|.
- **Severità (regola).**
  - `qc_duplicate_timestamp`: azione invariata, EXCLUDE_RESTRICTIVE. È ambiguo per l'uso come serie temporale; ma se i dati mostrano contenuto distinto e continuo, è un campione valido con incertezza di timing ≤ 1 s, irrilevante per celle di 50 m.
  - `qc_duplicate_record`: EXCLUDE_RECOMMENDED (doppio conteggio).
  - `qc_time_nonpositive_dt`: resta NOT_APPLICABLE (segnale interno).

## R2. qc_segment_restart_recovery dopo gap reali
- **Gap reale:** `dt > soglia long gap` dopo il fix R1. dt = 0 e jitter non sono gap.
- **Eventi:** inizio dei segmenti k > 0 con `segment_start_reason = long_gap`.
- **Curva di deviazione:**
  - D(t) = T(t) − T_ref, con T_ref = mediana di T in [240, 360] s dall'evento;
  - eventi con ≥ 50% di copertura in quella finestra, nello stesso segmento;
  - bin di 10 s da 0 a 240 s.
- **Controllo:** pseudo-eventi a tempi casuali (seed 20261109) interni a segmenti continui, ≥ 360 s da inizio segmento, gap o fine sosta; fino a 10 per campagna; stessa D(t).
- **Eccesso:**
  - A(t) = media|D_evento| − media|D_controllo|;
  - S(t) = media D_evento − media D_controllo (con segno);
  - IC con bootstrap per campagna.
- **Stratificazione:** durata del gap < 60 s vs ≥ 60 s.
- **Regola.**
  - Transitorio presente in uno strato se nei primi 60 s A(t) o |S(t)| > 0,1 °C con IC che esclude 0.
  - Finestra W = primo t oltre il quale, per tutti i bin successivi, |eccesso| < 0,1 °C oppure IC che include 0.
  - Se presente: EXCLUDE_RECOMMENDED nello strato, con finestra temporale W (limite massimo 300 s).
  - Se assente: WARNING_ONLY (flag mantenuto per trasparenza).
  - Per confronto, si riporta la durata flaggata dal detector a pendenza attuale.

## R3. qc_post_stop_recovery
- **Eventi:** fine di una sosta significativa (≥ 10 s stazionario, `stops.min_significant_stop_s`) seguita da movimento; t = secondi dalla ripresa del moto.
- **Metodo:** stessa D(t), stesso controllo, stessi bin, stessa soglia di 0,1 °C e stesso bootstrap di R2. T_ref = mediana in [240, 360] s dalla ripresa, senza nuove soste nel frattempo.
- **Strati:** sosta < 60 s vs ≥ 60 s.
- **Regola.**
  - Transitorio presente: EXCLUDE_RECOMMENDED nella finestra W, che sostituisce `stops.recovery_min_duration_s` come durata dopo la ripresa, arrotondata ai 10 s superiori.
  - Transitorio assente: WARNING_ONLY.
  - Nota di conflitto: la spec dice «non escludere automaticamente tutti i punti di recupero». Un'esclusione limitata alla finestra empirica non equivale a «tutti».

## R4. qc_unrealistic_acceleration (THR-GPS-006, 5 m/s²)
- **Grandezze.**
  - a_pos: accelerazione da velocità posizionale, come nel codice.
  - a_dop: Δ(`Speed[km/h]`/3,6)/dt sullo stesso intervallo, con la velocità del dispositivo. Si presume che sia GNSS Doppler del telefono; non è verificato e lo si dichiara come ipotesi.
- **Rumore di fondo.** Punti in «crociera stabile»: velocità del dispositivo ≥ 15 km/h e |a_dop| ≤ 0,3 m/s² nel punto e nei due adiacenti. Si riportano la distribuzione di |a_pos| (p50/p95/p99) e la quota sopra soglia.
- **Classificazione dei punti flaggati.**
  - «rumore GPS»: |a_dop| < 2 m/s²;
  - «dinamica plausibile»: |a_dop| ≥ 2 m/s²;
  - «non verificabile»: a_dop mancante.

  Errore implicito di posizione: e_pos = |d_pos − v̄_dop·dt|.
- **Sensibilità della soglia:** 3, 4, 5, 6, 8, 10 m/s², quota flaggata per classe.
- **Regola.**
  - Se ≥ 50% dei flag sono «rumore GPS» **e** il p95 di e_pos < 25 m, il flag segnala rumore di velocità senza conseguenze spaziali alla scala di analisi. Allora vale **warn a permissive/recommended**: azione di policy EXCLUDE_RESTRICTIVE, invariata.
  - Altrimenti: EXCLUDE_RECOMMENDED.
  - La soglia di 5 m/s² resta invariata (si riporta solo la sensibilità).

## R5. qc_gps_freeze (verifica di falsi positivi chiesta dalla sua nota di policy)
- **Blocchi:** run consecutivi di `qc_gps_freeze`.
- **Grandezze per blocco:**
  - durata;
  - salto al rilascio D_rel = distanza tra l'ultima posizione congelata e la prima successiva;
  - dt_rel;
  - velocità del dispositivo dopo il rilascio v_after;
  - velocità del dispositivo durante il blocco;
  - variazione di temperatura durante il blocco (`gps_freeze_meteo_still_varying`).
- **Classi.**
  - «sosta reale»: D_rel ≤ 25 m, oppure |D_rel/dt_rel − v_after| ≤ 3 m/s (il rilascio è coerente con la velocità).
  - «freeze in movimento»: D_rel > 25 m e incoerente (salto).
  - «non verificabile»: nessun punto dopo il blocco nello stesso segmento.
- **Regola, dalla nota di policy («downgrade to EXCLUDE_RESTRICTIVE if impact excessive on legitimate stops»).** «Eccessivo» = > 50% dei punti flaggati in blocchi «sosta reale».
  - Se eccessivo: EXCLUDE_RESTRICTIVE. La posizione è corretta; il problema residuo è la ventilazione, coperta da `qc_low_ventilation_possible` e `qc_stationary`.
  - Altrimenti: EXCLUDE_RECOMMENDED, invariato.

## R6. Nomi legacy e unica fonte di verità
- **Fonte unica:** `config/flag_policy_E0R_v0.2.csv`. Le severità della flag table sono **derivate per profilo** dall'azione:
  - **exclude** se l'azione esclude a quel profilo;
  - **warn** se WARNING_ONLY, oppure EXCLUDE_* che non esclude a quel profilo;
  - **info** se INFO_ONLY o SEGMENT_BREAK.

  I codici NOT_APPLICABLE non sono emessi (alias interni).
- **Schema `e0/qc_flag_schema_E0_v0.2.yaml`:** elenca i nomi canonici della policy e la mappa legacy → canonico. Le identità sono verificate nell'audit 9/11 (`alias_check.csv`, colonne booleane identiche):
  - `qc_time_duplicate` → `qc_duplicate_timestamp`;
  - `qc_time_order` → `qc_nonmonotonic_timestamp`;
  - `qc_temp_spike` → `qc_temp_isolated_spike`;
  - `qc_impossible_acceleration` → `qc_unrealistic_acceleration`;
  - `qc_gps_jump` e `qc_isolated_position_outlier` → sotto-segnali INFO dell'ombrello `qc_spatial_jump`;
  - `qc_time_nonpositive_dt` → interno (dopo R1: dt = 0 → `qc_duplicate_timestamp`, dt < 0 → `qc_nonmonotonic_timestamp`).
- **Garanzia per costruzione:** test unitario «FT exclude ⇔ keep_<p> = False» per ogni profilo.
- `code_commit` = git HEAD al momento della run (con suffisso `-dirty` se l'albero non è pulito).
- **Profili:** permissive, recommended e restrictive sono **run reali** con le rispettive YAML v0.2 (soglie v0.1 di ciascun profilo, più `policy_file`). Non sono proiezioni.

Regole non toccate, con azione v0.1 invariata: sensor_stabilization, spatial_jump, temp_isolated_spike, low_ventilation, speed_disagreement, unrealistic_speed, temp_rate_anomaly, plateau, limiti fisici.

## Analisi P1 pre-registrate (dopo E)
- **Metodo P1 invariato:**
  - celle di 50 m;
  - pass separati a 120 s;
  - ≥ 4 celle comuni;
  - località con ≥ 3 campagne;
  - R = Σcov/Σ√(var_a var_b);
  - bootstrap per campagna, seed 20261109.
- **Endpoint primario:** R route, coppie di giorni diversi, variante grezza (centrata per coppia).
- **Endpoint secondari:**
  - detrend lineare intra-pass nel tempo (variante «detrended» di P1);
  - **detrend altimetrico**: residuo di T ~ tempo + quota per campagna, stimato sui punti tenuti dalla maschera;
  - blocco di 500 m.
- **Popolazione comune.**
  - I pass sono definiti una sola volta sull'unione dei punti con T valida.
  - Una coppia (pass, cella) entra solo se **tutte** le maschere confrontate tengono ≥ 2 punti in quella cella per entrambi i pass.
  - Una coppia di pass entra solo con ≥ 4 celle comuni di questo tipo.

  Così insieme di coppie e celle è identico tra le maschere e cambiano solo i valori. Due livelli:
  - (a) tutte le maschere, incluse consensus e la vecchia flag-table;
  - (b) solo le maschere «larghe» (vecchia recommended e v0.2 permissive/recommended/restrictive).
- **Maschere confrontate:**
  - vecchia recommended;
  - vecchia flag-table (nessun exclude);
  - consensus (vecchia recommended ∧ nessun exclude);
  - v0.2 permissive, recommended, restrictive.
- **Sensibilità:**
  - con e senza cv2_004;
  - numerosità delle coppie: sottocampioni casuali di 100, 200, 400 coppie e tutte, 200 sottocampioni per n, seed 20261109. Si riportano mediana e percentili 2,5–97,5 di R tra sottocampioni e la mediana dell'IC bootstrap per campagna.
- **Interpretazione:** nessuna maschera viene scelta in base al valore di R. Il rapporto presenta le opzioni a Marco.
