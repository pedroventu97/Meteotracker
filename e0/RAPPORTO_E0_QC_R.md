# Rapporto E0-QC-R: revisione del QC E0 (policy v0.2), prove empiriche e P1 su popolazioni comuni

- Data: 9/11/2026 (orari Europe/Rome). Autore: Grok Bot per Marco Ventura.
- Branch: `feat/meteotracker-windows-app` (repo `pedroventu97/Meteotracker`).
- **Stato: proposta per decisione. Nessun QC viene dichiarato ufficiale.** La policy v0.1 (`config/flag_policy.csv`, YAML v0.1) e tutti gli archivi restano intatti.

## 0. Sintesi per la decisione
1. **Bug dt=0 corretto.** I 372 timestamp duplicati (dt=0) aprivano un nuovo segmento: 537 segmenti, ora 165.
   - Solo dt<0 o un gap lungo interrompono un segmento.
   - Le copie esatte di una riga (84) sono un nuovo flag, `qc_duplicate_record` (EXCLUDE_RECOMMENDED).
   - Effetti collaterali corretti: velocità, accelerazione e rateo termico non dividono più per zero; la stabilizzazione eredita lo stato.
2. **Severità decise dalle regole pre-registrate** (commit `ffac604`, prima di ogni P1), mai in base all'effetto su P1:
   - `qc_gps_freeze`: EXCLUDE_RECOMMENDED → **EXCLUDE_RESTRICTIVE**. Il 93,5% dei punti sono soste reali.
   - `qc_unrealistic_acceleration`: **invariato** (EXCLUDE_RESTRICTIVE, warn in recommended). L'87% dei flag è rumore GPS.
   - `qc_segment_restart_recovery` e `qc_post_stop_recovery`: INFO_ONLY → **WARNING_ONLY**. Nessun transitorio rilevabile, ma il test ha bassa potenza.
   - Nessuna soglia numerica è cambiata.
3. **Flag table e maschere keep coincidono per costruzione** in tutti e tre i profili: 0 discordanze su 72.505 punti, nessun codice legacy emesso. La discordanza v0.1 (flag table 26.342 vs keep 55.618) è eliminata.
4. **P1 sulla stessa popolazione:** le maschere **non cambiano R** in modo apprezzabile, tutte le differenze sono |ΔR| ≤ 0,02 con IC di ΔR che include 0.
   - Le differenze di R viste in P1 tra profili derivano dalla **popolazione** di coppie che sopravvive, non dalla qualità dei punti.
   - Il fattore che conta è **cv2_004**: senza, R route grezzo scende da 0,35 [0,09; 0,51] a 0,12 [−0,07; 0,31].
   - Servono ≥400 coppie diff-day perché l'IC escluda 0 nella maggior parte dei sottocampioni.

## 1. Pre-registrazione
- `e0/QC_R_CRITERIA_E0.md`, commit **ffac604afc18147e80af1254f503e5c318daa8b3** (9/11 12:08:35).
  - Regole R1–R6 con soglie fissate a priori.
  - Analisi P1 pre-registrate.
- Cronologia, tutta successiva al commit dei criteri:
  1. prove C (12:36, commit 37666b6);
  2. audit E (12:38, commit 2740f1a);
  3. run QC F (12:40);
  4. P1 (avvio 12:43:58, commit a8f9a8b);
  5. popolazioni comuni (12:55 e 12:57).

## 2. Correzioni e prove (passi B–C)
Cartella prove: `outputs/e0R_qc_evidence_20261109T1236/`. Codice 37666b6, bootstrap per campagna con 1000 repliche, seed 20261109.

| Regola | Evidenza principale | Decisione (regola pre-registrata) |
|---|---|---|
| R1 dt=0 | 372 dt=0 in 35 campagne. 84 copie esatte (82 nella campagna 06-20 08:29), 288 con contenuto distinto. Pattern 2-0-2 (159), 2-0-1 (68), 1-0-2 (60): jitter di quantizzazione al secondo. Il passo spaziale delle righe distinte ha mediana 14,2 m (passo a 1 s: 5,1 m). Segmenti 537→165, restart_recovery 27.253→15.487 punti | Il dt=0 non apre segmenti. `qc_duplicate_timestamp` resta EXCLUDE_RESTRICTIVE. Nuovo `qc_duplicate_record` EXCLUDE_RECOMMENDED |
| R2 restart dopo gap reale | 40 eventi in 24 campagne contro 199 controlli. Eccesso nei primi 60 s S≈+0,19 °C, IC ±0,32. Nessun transitorio consequenziale | WARNING_ONLY |
| R3 ripresa dopo sosta | 43 eventi in 33 campagne contro 93 controlli. S≈+0,22 °C, IC ±0,52. Nessun transitorio. Strato ≥60 s: 1 solo evento | WARNING_ONLY |
| Controllo positivo | Inizio sessione (35 eventi): S≈+0,30 °C ma IC che include 0. **Anche il controllo positivo non è rilevato**, quindi il metodo ha bassa potenza (MDE ≈0,3–0,5 °C) | Limite dichiarato (§6) |
| R4 accelerazione | In crociera stabile \|a_pos\| ha p50 0,31 e p95 14,4 m/s²: il rumore da differenze finite domina. Dei 18.663 flag a 5 m/s², l'87,4% ha \|a_doppler\|<2 e solo l'1,1% ha \|a_doppler\|>5. Errore di posizione implicito p95 23,8 m (<25 m, mezza cella). Quota flaggata con soglie 3/4/5/6/8/10: 33,7/29,3/26,1/23,6/19,6/16,4% | Invariato: EXCLUDE_RESTRICTIVE, warn in recommended |
| R5 gps_freeze | 8.299 punti in 2.236 blocchi: 93,5% soste reali (7.762 punti, velocità del dispositivo ≈0, D_rel mediana 0,57 m), 352 freeze in movimento, 185 non verificabili | EXCLUDE_RECOMMENDED → **EXCLUDE_RESTRICTIVE** |
| R6 alias legacy | `qc_time_duplicate`, `qc_time_order` e `qc_time_nonpositive_dt` diventano NOT_APPLICABLE (non emessi) | Mappati nello schema v0.2 |

Figure in `figures/`: `R1_dt0.png`, `R2R3_recovery_curves.png` (con controllo positivo), `R4_acceleration.png`, `R5_gps_freeze.png`.

Il run su DICAM ha riprodotto esattamente i numeri della prova di sviluppo citati nelle rationale della policy.

## 3. Maschere versionate (passi D–E)
- **Policy:** `config/flag_policy_E0R_v0.2.csv` (44 righe), più la copia in `src/meteotracker_qc/resources/`.
- **Schema:** `e0/qc_flag_schema_E0_v0.2.yaml`.
  - `severity_source: policy` (severità derivate per profilo);
  - alias legacy;
  - `code_commit` compilato.
- **Profili:** YAML reali `config/qc_E0R_{permissive,recommended,restrictive}_v0.2.yaml`, con soglie identiche alla v0.1. La policy si seleziona via `policy_file`/`flag_schema`.
- **Audit** `outputs/e0R_mask_audit_20261109T1238/` (commit 2740f1a):
  - accordo per costruzione: **0 discordanze** in permissive, recommended e restrictive;
  - keep: permissive 72.505, recommended 59.209, restrictive 19.768.
- **Run QC** `outputs/e0R_qc_split_20261109T1240/`:
  - code_commit 2740f1a, 55/55 campagne per profilo, 0 errori;
  - keep identici all'audit;
  - split identico alla v0.1 su route, blocco, LCZ, giorno e tempo (100%; vedi `SPLIT_CHECK_NA_AWARE.json`). Il 71,7% per route scritto nel meta era un artefatto NaN vs `<NA>`, corretto.
  - Le 5 righe "exclude" in permissive sono codici a livello file (DUP_*), che non escludono punti.
- **Discordanza residua v0.2 recommended vs v0.1 recommended:** accordo 86,0%.
  - 6.876 punti tornano tenuti: freeze (soste reali).
  - 3.285 punti diventano esclusi:
    - 3.267 `qc_sensor_stabilization`;
    - 65 `qc_duplicate_record`;
    - 2 `qc_spatial_jump`.
- **Perché la stabilizzazione cresce senza cambio di severità:** il flag copre solo il primo segmento. In v0.1 i falsi break dt=0 troncavano il primo segmento e il riscaldamento iniziale finiva in restart_recovery (INFO). Ora viene valutato per intero.
  - 12 campagne aumentano, nessuna diminuisce.
  - Il caso maggiore è 05-27 13:08 (91→1.395 punti): **da ispezionare**, il rilevatore potrebbe non confermare mai la stabilità.
- **Annidamento:** 326 punti sono tenuti da restrictive ma esclusi da recommended. Dipende dalle soglie v0.1 diverse per profilo (gap 4× vs 5×, finestre di stabilizzazione), non dalla policy.

## 4. P1 sulle maschere v0.2 (passo F)
`outputs/p1_repeatability_E0R_20261109T1243/` (commit a8f9a8b, metodo P1 invariato). Coppie di giorni diversi, R [IC 95%]:

| Maschera (popolazione propria) | route grezzo | route detrend | blocco grezzo | blocco detrend |
|---|---|---|---|---|
| v0.2 permissive | 0,38 [0,20; 0,48], n=999 | 0,22 [0,06; 0,34] | 0,25 [0,11; 0,41], n=2960 | 0,05 [−0,02; 0,12] |
| v0.2 recommended (= flag table) | 0,34 [0,09; 0,51], n=664 | 0,20 [−0,01; 0,33] | 0,25 [0,06; 0,43], n=1783 | 0,04 [−0,06; 0,13] |
| v0.2 restrictive | −0,09 [−0,45; 0,44], n=65 | 0,04 [−0,28; 0,43] | −0,49 [−0,81; 0,20], n=49 | −0,02 [−0,41; 0,54] |
| *v0.1 recommended (rif. 10:41)* | *0,42 [0,19; …], n=781* | *0,22* | *0,23, n=2285* | *0,04* |

Su popolazioni proprie i numeri **non sono confrontabili tra loro**, perché cambiano coppie e campagne. Per questo esiste il passo G.

## 5. Popolazioni comuni (passo G)
Cartella `outputs/p1_repeatability_E0R_20261109T1243/common_population_20261109T1257/` (commit b4c58cd). Il primo run, `common_population/`, è completo ma superato e marcato `SUPERSEDED.txt`.

**Validazione:** con una sola maschera la stessa procedura riproduce esattamente P1 (v0.1 recommended route 781 coppie, R 0,423; permissive 999 coppie, R 0,379).

**Livelli pre-registrati (a: tutte le 6 maschere; b: v0.1 rec + v0.2 perm/rec/restr):**
- Popolazione minuscola, perché restrictive e vecchia flag table tengono il 27–36% dei punti:
  - route: 16 (a) / 61 (b) coppie diff-day;
  - blocco: 13 / 47.
- R è negativo o ≈0 con IC larghissimi (es. b, route grezzo, da −0,11 a −0,16, IC circa [−0,45; +0,42]).
- **Tutti i ΔR rispetto a v0.1 recommended hanno IC che include 0.**
- Nessuna coppia di questi livelli tocca cv2_004, quindi la sensibilità a cv2_004 è vuota.
- Conclusione: con restrictive in gioco la domanda "le maschere cambiano R?" non ha potenza. L'unico segnale è che le coppie sopravvissute sono quelle meno ripetibili.

**Livello esplorativo c, NON pre-registrato** (v0.1 rec + v0.2 perm + v0.2 rec). È stato aggiunto dopo aver visto che a e b hanno meno di 100 coppie, prima di vederne R. Coppie diff-day, R [IC], ΔR rispetto a v0.1 rec:

| | route grezzo | route detrend tempo | route detrend quota (T~t+alt) | blocco grezzo | blocco detrend | blocco detr. quota |
|---|---|---|---|---|---|---|
| tutte, v0.1 rec | 0,35 [0,09; 0,51] | 0,19 [−0,01; 0,33] | 0,27 [0,09; 0,41] | 0,25 [0,05; 0,44] | 0,03 [−0,05; 0,13] | 0,18 [0,01; 0,36] |
| tutte, v0.2 perm | 0,34 (Δ −0,001) | 0,20 (Δ +0,010 [0,000; 0,018]) | 0,29 (Δ +0,021, IC incl. 0) | 0,25 (Δ +0,001) | 0,04 | 0,19 (Δ +0,009) |
| tutte, v0.2 rec | 0,34 (Δ −0,001) | 0,20 (Δ +0,007) | 0,27 (Δ −0,006) | 0,25 (Δ +0,001) | 0,04 | 0,18 (Δ 0,000) |
| senza cv2_004, v0.1 rec | **0,12 [−0,07; 0,31]** | 0,18 [−0,04; 0,33] | **0,11 [−0,06; 0,25]** | 0,24 [0,01; 0,47] | 0,02 | 0,19 [0,00; 0,38] |
| senza cv2_004, v0.2 rec | 0,12 (Δ −0,001) | 0,18 | 0,10 | 0,25 | 0,02 | 0,18 |
| n coppie (tutte / senza cv2_004) | 664 / 594 | 659 / 589 | 664 / 594 | 1778 / 1605 | 1413 / 1295 | 1778 / 1605 |

Letture:
- (i) Sulla stessa popolazione la scelta della maschera sposta R di ≤0,02.
- (ii) **cv2_004 (70 coppie diff-day) porta quasi tutto R route grezzo e detrend quota.** Senza, l'IC include 0. Il detrend nel tempo e il blocco da 500 m sono robusti a cv2_004.
- (iii) Il detrend altimetrico riduce R route da 0,35 a 0,27. Il gradiente con la quota spiega una parte della "ripetibilità" grezza.

**Sensibilità al numero di coppie** (livello c, route grezzo; 200 sottocampioni per n, seed 20261109):
- R mediano stabile (≈0,34–0,35);
- quota di sottocampioni con IC per campagna che esclude 0: 100 coppie → 10%, 200 → 41%, 400 → 78–79%, tutte (664) → IC [0,08; 0,51];
- blocco grezzo: 7% / 19% / 32% a 100/200/400 coppie.

Con meno di circa 400 coppie diff-day l'IC per campagna di regola include 0, indipendentemente dalla maschera. Figura chiave: `figures/pair_count_sensitivity.png`.

## 6. Limiti onesti
- **Potenza dei test di recovery bassa:** anche il controllo positivo (inizio sessione) non è rilevato. WARNING_ONLY significa "non dimostrato dannoso", non "dimostrato innocuo".
- **R4:** l'errore di posizione implicito (p95 23,8 m) è vicino alla soglia di 25 m. Si assume che `Speed[km/h]` sia velocità Doppler GNSS, cosa non verificata sul firmware.
- **Restrictive** rimane molto severo (27% dei punti tenuti): speed_disagreement, accelerazione, low_ventilation. Tra i profili non c'è annidamento stretto (326 punti).
- **Permissive** per costruzione non esclude alcun punto.
- **Stabilizzazione:** l'aumento di 3.267 punti esclusi è un effetto corretto del fix, ma il caso 05-27 13:08 (1.395 s di "riscaldamento") va ispezionato.
- **Schema nelle risorse:** il path `flag_schema: ../e0/...` negli YAML v0.2 copiati in `resources/` non è risolvibile dal pacchetto installato. I runner E0R usano `config/`. Da sistemare prima di un'eventuale adozione nell'app.
- **Test:** l'intera suite passa (619), tranne il test preesistente `test_runtime_import_closure_is_in_the_installed_package`. Fallisce perché `corridors_v2/validate.py` legge un gpkg all'import; il file non è toccato da E0-QC-R.
- **Livelli a e b:** non permettono di confrontare le maschere con potenza; il livello c è esplorativo.
- **LCZ:** usato l'asset esterno documentato (`D:\projects\LCZ\LCZ_PRISMA.shp`), come nella v0.1.

## 7. Opzioni per Marco (nessuna è dichiarata ufficiale)
1. **Adottare v0.2 recommended come maschera di lavoro E0 (non ufficiale).**
   - Pro: flag table e keep coerenti per costruzione; bug dt=0 corretto; freeze delle soste reali non più escluso; R invariato sulla stessa popolazione; ~3.600 punti in più tenuti.
   - Contro: recovery declassate a warning con test a bassa potenza; restano aperti la stabilizzazione 05-27 e il path dello schema nelle risorse.
2. **v0.2 recommended più sensibilità obbligatoria senza cv2_004 in ogni risultato P1.**
   - Pro: rende esplicito che R route dipende da una sola route.
   - Contro: con ~590 coppie l'IC route grezzo include 0; serve più campionamento (≥400 coppie per route senza cv2_004) prima di dichiarare la ripetibilità.
3. **Tenere la v0.1 recommended per ora e usare v0.2 solo come analisi di sensibilità.**
   - Pro: nessun cambiamento ai risultati già comunicati.
   - Contro: resta la discordanza tra flag table e keep v0.1; resta il bug dt=0 (segmentazione e divisioni per zero); il freeze delle soste resta escluso senza evidenza.
4. **Rimandare la scelta e prima rafforzare le prove.** Si possono:
   - ispezionare 05-27 13:08;
   - verificare la natura Doppler di `Speed` sul firmware;
   - raccogliere eventi di sosta lunga (≥60 s) per la potenza di R3;
   - ripetere G con nuove campagne.
   - Pro: decisione più solida. Contro: tempi.

## 8. Tracciabilità
Commit:
- ffac604: criteri;
- 37666b6: fix B + strumenti prove;
- 2740f1a: policy/schema/YAML v0.2 + runner audit/split;
- a8f9a8b: runner P1/G;
- b4c58cd: livello esplorativo G e conteggi cv2_004;
- commit del rapporto (vedi git log).

Output (non versionati):
- `outputs/e0R_qc_evidence_20261109T1236`;
- `outputs/e0R_mask_audit_20261109T1238`;
- `outputs/e0R_qc_split_20261109T1240`;
- `outputs/p1_repeatability_E0R_20261109T1243` (+ `common_population_20261109T1257`);
- `outputs/e0R_qc_report_20261109T1300`.

Archivi non modificati: `e0_qc_split_20261105T1703`, `p1_repeatability_E0_20261109T1041`, `qc_mask_audit_E0_20261109T1113`, alberi 20261015/18, `data/raw`, config v0.1.
