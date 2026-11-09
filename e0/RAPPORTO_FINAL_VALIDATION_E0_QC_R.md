# E0-QC-R — Final validation (policy v0.2): rapporto tecnico

- Data: 9/11/2026, orari Europe/Rome. Autore: Grok Bot per Marco Ventura (autorizzazione di Marco 9/11 14:23, via coordinatore).
- Branch `feat/meteotracker-windows-app`, HEAD di partenza `67911c2`. Cartella: `outputs/e0R_final_validation_20261109T1430/` (locale, non in git).
- **Stato: nessuna maschera è dichiarata ufficiale.** Nessuna PR, nessun deploy. Nessuna severità e nessuna soglia modificate. Dati raw, config v0.1/v0.2 in `config/` e output storici intatti.

## 0. Sintesi
| Punto | Esito |
|---|---|
| 1. Campagna 27/05 13:08 (warm-up 91 → 1.395 punti) | **Effetto di segmentazione che espone un difetto preesistente del rilevatore di stabilizzazione.** Non è un problema di qualità del dato. Proposta P-0527 documentata, **non applicata** |
| 2. Test suite | Fallimento **preesistente** dal 15/10 (commit `0bbbb16`), non una regressione E0-QC-R. Correzione giustificata e applicata (import senza effetti collaterali). Suite completa: **624 passati, 1 saltato, 0 falliti**; il test saltato passa con `--real-data` |
| 3. Schema nelle risorse | Il path `../e0/` nelle 3 copie v0.2 in `resources/` è sostituito da una copia dello schema inclusa nel pacchetto, byte-identica al canonico (sha256 `11edae4f…`). v0.2 si carica senza errori dal repo e da un wheel installato, anche da una cwd estranea |
| 4. Validazione scientifica | Sulle popolazioni comuni la maschera non cambia R (\|ΔR\| ≤ 0,007, tutti gli IC includono 0). R route dipende da cv2_004. Il calo di R route v0.2 su popolazione propria (0,42 → 0,34) è un effetto di popolazione dovuto al warm-up esteso (punto 1) |
| **Raccomandazione** | **CHANGES REQUIRED**, limitato al rilevatore di warm-up (P-0527, da pre-registrare). Il resto della v0.2 è pronto per la revisione scientifica (§6) |

## 1. Campagna 27/05/2026 13:08 (AC4D162B317E, 15:08–16:00 ora locale)
Cartella `campaign_0527/`; script `e0/run_e0R_final_0527_investigation.py` e `e0/run_e0R_final_cv2_004_anomaly.py`, in sola lettura.

**1.1 Osservazioni raw e corrette.**
- Il file raw `data/raw/05-27/…13_08_42…csv` ha 2.053 righe.
- Lo standardized v0.1 e quello v0.2 hanno 2.053 righe nello stesso ordine.
- Temp, Lat, Lon, Speed, Hum e Time sono **identici** tra raw, v0.1 e v0.2: il QC aggiunge flag e non altera le osservazioni.
- Cadenza alternata 1 s e 2 s (dt mediano 2 s). Ci sono 5 righe con dt = 0 (righe 91, 170, 862, 883, 1385), nessuna copia esatta.
- Risoluzione della temperatura: 0,1 °C.

**1.2 Regola responsabile.**
- È `qc_sensor_stabilization` (EXCLUDE_RECOMMENDED sia in v0.1 sia in v0.2). Config warm-up e ventilazione identiche tra v0.1 e v0.2.
- **v0.1:**
  - le 5 righe con dt = 0 aprivano 6 segmenti falsi;
  - il primo segmento (91 righe, 117 s) non raggiungeva la stabilità, quindi tutte le sue 91 righe erano flaggate;
  - gli altri 5 segmenti producevano **929 righe di `qc_segment_restart_recovery`**, allora INFO_ONLY.
- **v0.2:**
  - c'è un solo segmento;
  - la stabilità è confermata solo a **2.093 s** (riga 1.395);
  - tutte le righe precedenti diventano warm-up.
- Il rilevatore v0.2 applicato ai segmenti v0.1 riproduce esattamente 91 + 929 righe. La traccia ricostruita riproduce il flag del pipeline riga per riga.
- **Gate attivo:** è quello della pendenza. Il gate della ventilazione è soddisfatto già a 20 s; togliendolo il risultato resta 1.395.
  - Con mediana mobile su 3 campioni e dt = 2 s, il più piccolo |slope| non nullo è 0,025 °C/s, già sopra la soglia di 0,02 °C/s.
  - Quindi "stabile" significa in pratica **nessuna variazione di un quanto (0,1 °C) della mediana per 60 s consecutivi**.
  - Prima del confine la serie stabile più lunga dura 59 s.
- **Discontinuità della regola:**
  - se la stabilità non viene mai confermata, il flag si ferma a `max_window_s` = 300 s;
  - se la conferma arriva tardi, il flag copre tutto fino alla conferma.
  - Ne segue un comportamento non monotono: `min_stable_seconds` = 120 (più severo) dà 225 righe, 60 ne dà 1.395, 30 ne dà 419.
  - Soglia di pendenza 0,01–0,05 → 1.395; 0,1 → 461. `window_size_s` ≥ 21 → 390–501.

**1.3 Distribuzione temporale e spaziale.**
- Il flag copre in modo contiguo i primi 35 minuti (fasce di 5 min tutte al 100% fino a 30–35 min, poi 0).
- Tocca 31 route (1.314 punti su route) e 34 dei 36 blocchi da 500 m.
- Copre **l'intero passaggio della campagna su cv2_004 (376 punti)**, cv2_003 (271) e 346 dei 507 punti di cv2_001.
- In recommended v0.2: 1.162 punti esclusi in più, tutti per la sola stabilizzazione; 89 punti tenuti in più (gps_freeze).

**1.4 È un problema reale del dato? No, per quattro prove.**
1. **Sensore già acceso:** la sessione precedente dello stesso dispositivo (12:58) finisce alle 13:07:28 UTC, 74 s prima. T media negli ultimi 60 s 34,8 °C, nei primi 60 s di questa sessione 34,4 °C: nessun avvio a freddo.
2. **Nessun transitorio:** la pendenza OLS su 300 s ha mediana |·| 0,16 °C/min prima del confine e 0,11 dopo, contro una soglia equivalente di 1,2 °C/min.
3. **Il segnale flaggato è spaziale:** il calo a 31–32 °C tra 20 e 28 min avviene su cv2_003 a una quota media di 207 m (media della campagna 87 m), cioè in collina, a 40–80 km/h.
4. **cv2_004 nella norma:** la sua anomalia termica in questa campagna (−0,13 °C rispetto alla media della campagna) rientra nella distribuzione delle altre 14 campagne (mediana −0,30).

**1.5 Contesto su tutte le 55 campagne.**
- v0.2 flagga 13.148 righe di stabilizzazione, v0.1 9.560. 12 campagne aumentano, nessuna diminuisce.
- Esito del rilevatore sul primo segmento: 36 STABILIZATION_NOT_REACHED (cap a 300 s), 14 confermate, 5 segmenti troppo corti.
- Conferma oltre 300 s in 8 campagne. Gli aumenti grandi sono 4:
  - 05-27 13:08: 2.093 s, +1.304 righe;
  - 7-22 09:17: 901 s, +511;
  - 06-20 08:29: 869 s, +424;
  - 02-20 12:54: 845 s, +505.

**Verdetto:**
- Il fix dt = 0 è corretto: non tocca il rilevatore e lo applica al segmento reale.
- Ha però **esposto un difetto preesistente** del rilevatore, che in v0.1 era nascosto come restart_recovery INFO. Le cause sono due:
  - un gate di pendenza limitato dalla quantizzazione;
  - un'asimmetria con `max_window_s`.
- Effetto non voluto: viene escluso segnale spaziale reale (cv2_003/cv2_004) senza alcuna evidenza di warm-up.
- **La severità non va cambiata.** Il problema è il rilevatore, non l'azione della policy.

**Proposta P-0527, NON applicata:**
- il warm-up iniziale non si estende mai oltre `max_window_s` (300 s), anche quando la conferma arriva più tardi, come già avviene quando la conferma non arriva;
- alternativa: rendere il test di pendenza consapevole della risoluzione (OLS su ≥ 30–60 s).
- Va pre-registrata (i criteri di `ffac604` dichiarano la stabilizzazione «non toccata») e approvata da Marco.
- Effetto stimato della variante con cap: 2.982 punti tornano tenuti, di cui 1.169 nella 05-27 13:08 (1.395 → 225 righe flaggate).

## 2. Test suite
- **Test che falliva:** `tests/test_package_resources.py::test_runtime_import_closure_is_in_the_installed_package`.
  - Il test assume che ogni modulo del pacchetto (GUI esclusa) sia importabile senza effetti collaterali e che le sue dipendenze interne siano nel pacchetto.
  - `corridors_v2/validate.py` era uno script a livello di modulo: all'import leggeva `sys.argv[1]/corridors.gpkg`.
  - Sotto pytest quel path è `tests\test_package_resources.py\corridors.gpkg`. Senza argomenti avrebbe potuto **sovrascrivere** `outputs/corridor_passages_20261015/validation*.json|csv|png`. Verificato: quei file non sono stati toccati, mtime 15/10.
- **Storia, verificata con worktree temporanei e `PYTHONPATH` sul worktree** (log in `tests/history_worktrees/`):

  | Commit | Data | Esito |
  |---|---|---|
  | `611b290` | 28/09 | PASSA |
  | `0bbbb16` | 15/10, introduce `validate.py` | FALLISCE |
  | `48f4d6a` | 9/11, prima di E0-QC-R | FALLISCE |

  **È preesistente, non una regressione E0-QC-R.**
- **Correzione (giustificata):** il corpo di `validate.py` è spostato in `main(argv)` con `if __name__ == "__main__"`; la logica è invariata.
  - Rieseguito su una copia di `corridor_passages_20261015`: `validation.json` e `validation_ns_axis.csv` sono **byte-identici** a quelli del 15/10.
- **Nuovi test sullo schema:**
  - copia nel pacchetto byte-identica al canonico;
  - i 3 preset v0.2 risolvono policy e schema sia da `config/` sia da `resources/`, con cwd estranea.
  - Il test sull'uguaglianza tra config e risorse ammette come unica differenza la riga `flag_schema`.
- **Suite completa** (`tests/pytest_full.txt`, JUnit in `tests/pytest_full_junit.xml`): 625 test, **624 passati, 1 saltato, 0 falliti**, 412 s. Il test saltato, `test_real_data_regression_stabilization_no_longer_scattered_mid_trip`, **passa** con `--real-data` (`tests/pytest_stabilization_real_data.txt`).

## 3. Integrazione dello schema
- **Modifiche:**
  - `src/meteotracker_qc/resources/qc_E0R_{permissive,recommended,restrictive}_v0.2.yaml`: `flag_schema: qc_flag_schema_E0_v0.2.yaml`;
  - nuovo `src/meteotracker_qc/resources/qc_flag_schema_E0_v0.2.yaml`, copia byte-identica di `e0/qc_flag_schema_E0_v0.2.yaml` (sha256 `11edae4f4230a2c49b1e638657fbe4a51c0ec0a84e1359029d44cd4956cb63a7`);
  - policy v0.2 identica nelle due sedi (sha256 `7619dbc4…`).
- **Non modificati**, così i fingerprint del run 12:40 restano validi:
  - `config/qc_E0R_*_v0.2.yaml`, che dal repo risolvono già `../e0/`;
  - lo schema canonico;
  - la policy;
  - gli output storici.
- **Verifica con wheel non editable:** costruito con `pip wheel`, estratto in una cartella temporanea e importato da una cwd estranea (`schema_integration/package_check_unrelated_cwd.json`).
  - Il vecchio riferimento `../e0/` non si risolve dal pacchetto (confermato).
  - Il nuovo riferimento si risolve per tutti e 3 i profili.
  - Un run end-to-end sulla 05-27 13:08 con i preset del pacchetto dà keep identici al run archiviato (2.053 / 656 / 281).

## 4. Validazione scientifica
Tabelle in `p1_comparison/`. **Nessuna nuova P1 pre-registrata è stata rieseguita:** i fix 2–3 non cambiano maschere né valori (keep identici verificati), quindi i risultati validati delle 12:43 e 12:57 restano validi. L'unico calcolo nuovo è la sensibilità **esplorativa** P-0527 (`stabcap_sensitivity_exploratory/`, 111 s).

**4.1 Maschere** (`T6_mask_agreement_points.csv`, 72.505 punti):

| Confronto | Accordo | κ | Note |
|---|---|---|---|
| v0.1 rec vs v0.2 rec | 86,0% | 0,58 | 6.876 punti tenuti solo da v0.2 (freeze di soste reali); 3.285 tenuti solo da v0.1 (3.267 di stabilizzazione) |
| v0.2 permissive vs v0.2 restrictive | 27,3% | 0 | 72.505 contro 19.768 punti tenuti |
| v0.2 rec vs v0.2 restrictive | 44,7% | 0,14 | 326 punti tenuti da restrictive ma non da recommended (non annidamento, soglie v0.1) |

Flag table e keep coincidono per costruzione: 0 discordanze in tutti e 3 i profili.

**4.2 PRE-REGISTRATO** (`e0/QC_R_CRITERIA_E0.md`, `ffac604`, 9/11 12:08:35).
- Endpoint primario: R route su coppie di giorni diversi, variante grezza. Su popolazione propria (`T1`):

  | Maschera | v0.1 | v0.2 |
  |---|---|---|
  | recommended | 0,42 [0,19; 0,54], n = 781 | 0,34 [0,09; 0,51], n = 664 |
  | permissive | 0,38 [0,20; 0,48], n = 999 | 0,38 [0,20; 0,48], n = 999 |
  | restrictive | 0,12 [−0,30; 0,48], n = 128 | −0,09 [−0,45; 0,44], n = 65 |

- Blocco 500 m, recommended: v0.1 0,23 [0,10; 0,39], v0.2 0,25 [0,06; 0,43]. Detrend nel tempo: route 0,22 / 0,20, blocco 0,04 / 0,04.
- **I valori su popolazione propria non sono confrontabili tra maschere.**
- Popolazioni comuni pre-registrate (`T2`; livelli a = 6 maschere, b = 4 maschere):
  - solo 16 / 61 coppie route diff-day e 13 / 47 di blocco;
  - R ≈ 0 o negativo, con IC ampi;
  - tutti gli IC di ΔR rispetto a v0.1 rec includono 0;
  - nessuna coppia tocca cv2_004.
  - **Conclusione pre-registrata:** con restrictive e la vecchia flag table in gioco la domanda «la maschera cambia R?» non ha potenza.

**4.3 ESPLORATIVO** (non pre-registrato). Livello c = v0.1 rec + v0.2 perm + v0.2 rec, più la sensibilità P-0527. Coppie diff-day (`T0_headline_diff_day.csv`, figura `fig_final_P1_forest.png`):

| Popolazione | Località | Variante | v0.1 rec (propria) | v0.2 rec (propria) | v0.2 rec + cap P-0527 (propria) | ΔR v0.2 − v0.1, pop. comune |
|---|---|---|---|---|---|---|
| tutte | route | grezzo | 0,42 [0,21; 0,55] n = 781 | 0,34 [0,09; 0,50] n = 664 | 0,43 [0,19; 0,56] n = 789 | −0,001 [−0,003; +0,001] |
| tutte | route | detrend tempo | 0,22 [0,00; 0,34] | 0,20 [−0,00; 0,34] | 0,19 [0,01; 0,33] | +0,007 [−0,003; +0,015] |
| tutte | route | detrend quota | 0,32 [0,14; 0,43] | 0,27 [0,07; 0,41] | 0,32 [0,14; 0,44] | −0,006 [−0,031; +0,009] |
| tutte | blocco | grezzo | 0,23 [0,08; 0,39] n = 2285 | 0,25 [0,05; 0,44] n = 1783 | 0,22 [0,07; 0,39] | +0,001 |
| tutte | blocco | detrend tempo | 0,04 [−0,03; 0,12] | 0,04 [−0,05; 0,13] | 0,04 | +0,002 |
| tutte | blocco | detrend quota | 0,16 [0,01; 0,30] | 0,18 [0,01; 0,36] | 0,14 [−0,01; 0,30] | −0,000 |
| senza cv2_004 | route | grezzo | 0,17 [−0,04; 0,34] n = 658 | 0,12 [−0,07; 0,31] n = 594 | 0,15 [−0,05; 0,33] | −0,001 |
| senza cv2_004 | route | detrend quota | 0,15 [−0,00; 0,28] | 0,10 [−0,06; 0,25] | 0,13 [−0,01; 0,27] | −0,003 |
| senza cv2_004 | blocco | grezzo | 0,23 [0,02; 0,44] | 0,24 [0,01; 0,47] | 0,21 [0,00; 0,43] | +0,001 |
| senza cv2_004 | blocco | detrend tempo | 0,03 [−0,03; 0,10] | 0,02 [−0,05; 0,11] | 0,03 | +0,002 |

- **Sulla stessa popolazione la maschera non cambia R** (\|ΔR\| ≤ 0,007; tutti gli IC includono 0).
- La differenza su popolazione propria tra v0.1 e v0.2 rec (0,42 contro 0,34) **sparisce con il cap P-0527** (0,43): è un effetto di popolazione, causato dalle coppie perse con il warm-up esteso (cv2_004 della 05-27 13:08 e simili).
- La proposta P-0527 è motivata dalle prove fisiche del §1.4, ottenute prima e in modo indipendente da questo calcolo. R non è un obiettivo.
- **R route è guidato da cv2_004:** senza, l'IC include 0 in tutte le maschere.
- **Blocchi 500 m:** R grezzo ≈ 0,23–0,25 indipendente da cv2_004; detrendato nel tempo ≈ 0; con detrend altimetrico ≈ 0,16–0,18. Gran parte della ripetibilità dei blocchi è un gradiente temporale o altimetrico condiviso.
- **Numerosità** (`T4`, livello c, grezzo, 200 sottocampioni): R mediano stabile; quota di sottocampioni con IC per campagna che esclude 0:

  | | 100 coppie | 200 | 400 | tutte |
  |---|---|---|---|---|
  | route | 10% | 40–42% | 78–79% | 664 coppie: [0,09; 0,50] |
  | route senza cv2_004 | 0% | 0% | 0% | 0% |
  | blocco | 6–7% | 18–20% | 32–34% | — |

  Servono ≥ 400 coppie diff-day per route, e senza cv2_004 nemmeno quelle bastano con l'R attuale (≈ 0,12).

## 5. Limiti e questioni aperte
1. **P-0527** (rilevatore di warm-up) non è applicata: richiede pre-registrazione, approvazione di Marco, rerun dello split QC e rerun di P1. Fino ad allora v0.2 recommended esclude 2.982 punti flaggati oltre i 300 s. Per essi non c'è evidenza di warm-up; la verifica in dettaglio è stata fatta solo sulla 05-27 13:08.
2. Test di recovery a bassa potenza (R2/R3, già noto); R4 assume `Speed` = Doppler GNSS, non verificato sul firmware.
3. Restrictive tiene solo il 27% dei punti e non è annidato in recommended (326 punti).
4. Il path AOI (`data/aoi/…`) in un'installazione fuori dal repo si risolve tramite le radici candidate di `gps_qc.py`; non verificato come risorsa del pacchetto. Non riguarda la v0.2.
5. La sensibilità P-0527 e il livello c sono esplorativi.

## 6. Raccomandazione finale: **CHANGES REQUIRED**
**Motivi:**
- La maschera candidata v0.2 recommended contiene un artefatto documentato (§1): in 4 campagne il warm-up dura 14–35 min; nella 05-27 13:08 il sensore era già acceso. L'artefatto:
  - esclude segnale spaziale reale (cv2_003/cv2_004);
  - determina la differenza di R su popolazione propria rispetto a v0.1.
- Portare in revisione scientifica una maschera con un difetto noto e quantificato non è appropriato.

**Modifiche richieste** (tutte da autorizzare):
1. Pre-registrare P-0527 (cap a `max_window_s`, oppure pendenza consapevole della risoluzione), senza cambiare severità.
2. Implementarla come v0.3 candidata con test, poi rieseguire lo split QC e P1/G.
3. Ripetere questa validazione.

**Già pronto per la revisione:**
- severità v0.2 e prove R1–R6;
- coerenza per costruzione tra flag table e keep;
- fix dt = 0;
- test, tutti verdi;
- integrazione dello schema;
- conclusioni sulle popolazioni comuni (la maschera non cambia R; cv2_004 e la numerosità dominano).

## 7. Contenuto della cartella
- `RAPPORTO_FINAL_VALIDATION_E0_QC_R.md` (questo file, copia in `e0/`) e `REPRODUCIBILITY.md`;
- `qc_policy_v0.2/`: policy, 3 YAML, schema, criteri pre-registrati, più `package_resources/` (copie nel pacchetto);
- `masks/`: flag table v0.2 per profilo (parquet), campaign summary, split, meta del run, `points_masks_v01_v02.parquet` e audit (copie da `e0R_qc_split_20261109T1240` e `e0R_mask_audit_20261109T1238`);
- `tests/`: suite completa, JUnit, test delle risorse, test real-data, log storici dei worktree;
- `campaign_0527/`: JSON, traccia del rilevatore, distribuzioni, contesto delle 55 campagne, anomalia cv2_004, figure;
- `schema_integration/`: controllo del wheel;
- `p1_comparison/`: T0–T7, figure, sensibilità esplorativa P-0527;
- `MANIFEST_sha256.csv`.