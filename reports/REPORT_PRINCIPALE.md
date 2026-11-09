# REPORT PRINCIPALE – MeteoTracker Bologna (documento vivo)

*Creato il 15/10/2026 alle 19:40 CEST. Da aggiornare a ogni nuovo risultato (vedi Changelog). I numeri provengono dagli output indicati; dove un'informazione non viene dagli output, la fonte è dichiarata.*

## Obiettivo
Caratterizzare la temperatura dell'aria (Tair) misurata con sensori mobili MeteoTracker a Bologna:
- controllo di qualità (QC) dei dati;
- individuazione dei percorsi ripetuti;
- anomalie termiche lungo i percorsi e loro ripetibilità;
- confronto descrittivo con il contesto urbano (LCZ) e con la LST satellitare downscaled.

Prodotti finali: poster e figure.

## Stato per componente
| Componente | IMPLEMENTED | TESTED | VALIDATED |
|---|---|---|---|
| Pipeline QC (profilo recommended, `outputs/recommended_20261015T0835`) | sì | sì (audit, test del repo) | no |
| Manifest campagne 20261015T0835 | sì | sì | n.a. |
| repeated_routes 20261015T0835 (matching ufficiale) | sì | sì | no |
| corridors_v2 (`corridor_passages_20261015`, sperimentale) | sì | sì (`validation.json`) | no |
| Anomalie su passaggi ripetuti (`pass_anomaly_20261015T1856`) | sì | sì | **no** |
| Anomalie Δt breve / andata-ritorno (`short_dt_anomaly_20261015T1927`) | sì | sì | **no** |
| Poster anomalie Tair (tutte le sessioni, centro) | sì | controllo visivo | n.a. (descrittivo) |
| Overlay LST v13 + tracce + stazioni (v1–v5) | sì | controllo visivo | **no** (LST operativa v13, non validata, non V19) |
| Manifest ufficiale E0 (55 canoniche / 60 righe) | sì | sì (SHA256) | n.a. |
| AOI + flag table E0 (e0/, flag_table.py) | sì | sì (19 test focused) | no |
| QC E0 + split day/route/spatial_block (outputs/e0_qc_split_20261105T1703) | sì | sì (55/55) | no |

## Risultati chiave
- **Manifest** `data/manifests/campaign_manifest_20261015T0835.csv`: 60 righe, **55 campagne canoniche non escluse**. Di queste, 53 hanno punti QC recommended.
- **Matching repeated_routes 20261015T0835**: **792 segmenti, 1616 passaggi**. Solo **23 segmenti (2,9%) hanno almeno 3 passaggi**.
- **corridors_v2**: **34 corridoi, 57,1 km, 416 passaggi** da 49 campagne (`corridor_passages_20261015/summary.json`, README).
- **Passaggi ripetuti** (`pass_anomaly_20261015T1856/summary.json`). R = quota di varianza del profilo ripetibile; IC 95% con bootstrap per campagna.
  - repeated_routes (23 segmenti): R grezzo **0,48 [−0,01; 0,72]**, detrended **0,33 [−0,19; 0,71]**.
  - corridors_v2 (31 corridoi): R grezzo **0,41 [0,24; 0,52]**, detrended **0,09 [−0,02; 0,23]**.
  - Gran parte della ripetibilità apparente è un gradiente su grande scala lungo il percorso.
  - Casi ripetibili anche dopo il detrend: **seg_0293** (6,2 km, 3 passaggi): R 0,86 [0,17; 0,91], detrended 0,80. **cv2_014** (8 campagne): R 0,79 [0,61; 0,95], detrended 0,72.
  - Esempio non ripetibile: seg_0305 (6 passaggi), R −0,25 [−0,82; 0,55].
- **Δt breve** (`short_dt_anomaly_20261015T1927`):
  - 448 attraversamenti; a Δt ≤ 15 min ci sono **19 coppie** (16 in direzione opposta), 9 campagne, tutte coppie interne alla stessa campagna.
  - **R 0,64 [0,29; 0,67]**, |differenza| media 0,21 °C [0,13; 0,28].
  - Sensibilità: 10 min → 12 coppie, R 0,64; 20 min → 31 coppie, R 0,48.
  - **Ritardo del sensore compatibile con 0–4 s**, non identificato: mediana 1,6 s [−3,0; 3,8]; in 8 coppie su 16 il picco cade al limite della ricerca.
- **Figure poster e overlay LST**:
  - poster anomalie Tair di tutte le sessioni (53 sessioni, 04/07/2025–16/09/2026, anomalia detrended, ±1,6 °C) e zoom sul centro;
  - overlay LST 20/06/2026 (v13 operativa, 100 m), versioni v1–v5, con tracce MeteoTracker, 341 stazioni Netatmo e stazioni ARPAE dal file di metadati.

## Figure principali
- [Poster tutte le sessioni](figures/poster_all_20261015T1520/poster_anomalia_tutte_sessioni.png) · [Poster centro](figures/poster_all_20261015T1520/poster_anomalia_centro_bologna.png)
- [LST overlay v1 (2 pannelli)](figures/lst_overlay_20261015T1539/lst_overlay_20260620.png) · [centro v3](figures/lst_overlay_20261015T1539/lst_overlay_20260620_centro_v3.png) · [v5 comune intero](figures/lst_overlay_20261015T1539/lst_overlay_20260620_centro_v5.png) · [v5 trasparente](figures/lst_overlay_20261015T1539/lst_overlay_20260620_centro_transparent_v5.png)
- [Passaggi ripetuti: R grezzo vs detrended](../outputs/pass_anomaly_20261015T1856/report_sintesi/fig2_R_raw_vs_detrended.png) · [mappa R](../outputs/pass_anomaly_20261015T1856/report_sintesi/fig3_mappa_R.png) · [seg_0293 e cv2_014](../outputs/pass_anomaly_20261015T1856/report_sintesi/fig4_profili_ripetibili.png)
- [Δt breve: R vs soglia](../outputs/short_dt_anomaly_20261015T1927/fig3_R_vs_soglia.png) · [ritardo del sensore](../outputs/short_dt_anomaly_20261015T1927/fig4_ritardo_sensore.png)

## Limiti
- Pochi passaggi indipendenti per tratto: al massimo 3 per segmento nella maggior parte dei casi; a Δt breve, 9 campagne.
- I segmenti ufficiali si sovrappongono e condividono le stesse campagne.
- Confondimento con quota, velocità e ventilazione, sole e ombra, ora del giorno: le covariate sono solo descritte.
- Le classi LCZ vegetate (A, D) sono concentrate in collina: confuse con la quota.
- La LST è temperatura di superficie, non dell'aria. Il prodotto v13 è operativo, non validato e non V19. L'overlay non è una validazione.
- I punti di corridors_v2 non sono stati sottoposti a un nuovo QC.

## Fatti vs ipotesi
- **Fatti (dagli output):** i conteggi sopra; R e IC; il crollo di R in corridors_v2 dopo il detrend (0,41 → 0,09); il picco della cross-correlazione al limite in 8 coppie su 16.
- **Ipotesi (non verificate):**
  - la ripetibilità residua di seg_0293 e cv2_014 riflette il contesto locale piuttosto che la quota o la geometria del percorso;
  - il ritardo del sensore è dell'ordine di pochi secondi;
  - le differenze per LCZ hanno un'origine urbana.

## Decisioni di Marco
*Riportate come comunicate dal coordinatore del progetto il 15/10/2026; non ricavate dagli output.*
- I punti che non superano il QC vengono **marcati con un flag, non cancellati**.
- **(c) autorizzato il 15/10/2026.**
- Finestra temporale per il confronto LST–Tair: **±30 min**; sensibilità ±15 e ±60 min.
- Commit **0bbbb16** e successivi erano solo locali; **push autorizzato il 6/11/2026** (passi 5–6 E0) sul branch `feat/meteotracker-windows-app`.
- Le nuove analisi (pass_anomaly, short_dt) restano non tracciate da git: nessun commit.
- Regola dal 15/10/2026: un solo report principale vivo per filone di lavoro (questo file).

## Prossimi passi
- Più passaggi indipendenti sugli stessi percorsi, con copertura completa di ciascun segmento.
- Un modello con covariate esplicite (quota, velocità, irraggiamento).
- Una prova controllata del ritardo del sensore.
- Una validazione con stazioni fisse (ARPAE, Netatmo) e con date tenute da parte.
- Il confronto LST–Tair con finestra ±30 min (sensibilità ±15 e ±60).
- Completare validazione scientifica del QC E0 / split (flag table, day/route/spatial_block) dopo il push.
- Allineare `README.md` al manifest attuale (vedi discrepanza sotto). **Fatto 09/11/2026.**
- Decidere quale QC E0 è ufficiale: `keep_recommended` della pipeline o le severity `exclude` di `flag_table_E0` (accordo per riga 48,6%; vedi entry 09/11).
  - Audit del 09/11 (`outputs/qc_mask_audit_E0_20261109T1113/`): proposta (non decisione) di una maschera armonizzata con unica fonte `config/flag_policy.csv`, con correzione preliminare dei cambi segmento da dt = 0. **Nessuna QC dichiarata ufficiale.**
  - E0-QC-R del 09/11: policy v0.2 con flag table e keep coerenti per costruzione; opzioni in `e0/RAPPORTO_E0_QC_R.md` ?7. **Decisione ancora di Marco.**
  - Final validation E0-QC-R del 09/11 (`e0/RAPPORTO_FINAL_VALIDATION_E0_QC_R.md`): raccomandazione **CHANGES REQUIRED**, limitata al rilevatore di warm-up (proposta P-0527, non applicata). **Nessuna QC ufficiale.**

## Discrepanze note
- `README.md` (modificato il 09/09/2026) **non contiene "34 campagne"**: la frase indicata non è stata trovata. Il README riporta invece dati superati:
  - riga 115: "Of the 49 raw CSVs under `data/raw/` (39 through the original audit, plus 10 more added 2026-08 …), 5 are redundant re-exports…";
  - riga 119: "By default, `run_qc.py` processes only the 44 canonical campaigns (`exclude_from_analysis == False` in the manifest)…".
  - Il manifest ufficiale campaign_manifest.csv è dal 5/11/2026 il contenuto E0 (60 righe / 55 canoniche; SHA256 81C903DE…C264); la copia datata resta campaign_manifest_20261015T0835.csv / campaign_manifest_E0_20261015T0835.csv. Archivio pre-E0 (44 canoniche): campaign_manifest_preE0_44canonical_20260731.csv.
  - Il README non è stato modificato.
  - **Risolto il 09/11/2026:** `README.md` riga 119 ora indica **55** canoniche nel manifest ufficiale E0; il 44 resta solo come storia (archivio `campaign_manifest_preE0_44canonical_20260731.csv`, albero legacy `outputs/recommended/` a 44). Anche `docs/GATE_2_1_STATUS.md` §2 allineato (55; «al momento del Gate 2.1 erano 44»). Gli altri report storici con 44 non sono stati toccati.
  - Il "34" corrisponde invece al numero di **corridoi** di corridors_v2.

## Indice output datati
- [data/manifests/campaign_manifest_20261015T0835.csv](../data/manifests/campaign_manifest_20261015T0835.csv)
- [outputs/recommended_20261015T0835/](../outputs/recommended_20261015T0835/)
- [outputs/repeated_routes_20261015T0835/](../outputs/repeated_routes_20261015T0835/)
- [outputs/corridor_passages_20261015/README.md](../outputs/corridor_passages_20261015/README.md)
- [outputs/pass_anomaly_20261015T1856/README.md](../outputs/pass_anomaly_20261015T1856/README.md) · [report_sintesi/REPORT_SINTESI.pdf](../outputs/pass_anomaly_20261015T1856/report_sintesi/REPORT_SINTESI.pdf)
- [outputs/short_dt_anomaly_20261015T1927/README.md](../outputs/short_dt_anomaly_20261015T1927/README.md)
- [reports/figures/poster_all_20261015T1520/README.md](figures/poster_all_20261015T1520/README.md)
- [reports/figures/lst_overlay_20261015T1539/README.md](figures/lst_overlay_20261015T1539/README.md)
- [reports/figures/poster_20261015T1514/README.md](figures/poster_20261015T1514/README.md) · [reports/figures/poster_20261015T1520/README.md](figures/poster_20261015T1520/README.md)

- [data/manifests/campaign_manifest.csv](../data/manifests/campaign_manifest.csv) (ufficiale E0 dal 5/11/2026)
- [data/aoi/bologna_e0_aoi_v0.1.geojson](../data/aoi/bologna_e0_aoi_v0.1.geojson)
- [outputs/e0_qc_split_20261105T1703/](../outputs/e0_qc_split_20261105T1703/) (locale; non in git, ~458 MB)
- [outputs/lst_campaigns_multiday_20261018T2218/](../outputs/lst_campaigns_multiday_20261018T2218/)
- [outputs/p1_repeatability_E0_20261109T1041/summary.md](../outputs/p1_repeatability_E0_20261109T1041/summary.md) (locale; non in git) · metodo [e0/P1_REPEATABILITY_E0.md](../e0/P1_REPEATABILITY_E0.md)
- [outputs/qc_mask_audit_E0_20261109T1113/summary.md](../outputs/qc_mask_audit_E0_20261109T1113/summary.md) (locale; non in git) · metodo [e0/QC_MASK_AUDIT_E0.md](../e0/QC_MASK_AUDIT_E0.md)

## Changelog
- **15/10/2026 19:40** – Creazione del report principale. Nessun equivalente esistente: in `reports/` ci sono solo l'audit QC del 25/07, il report di sessione del 31/07 e quello di pulizia del 25/07; in `docs/` ci sono `GATE_2_1_STATUS.md` e simili, che sono specifici di un singolo gate. Risultati inseriti fino a `short_dt_anomaly_20261015T1927`.
- 2026-10-15 19:50: README aggiornato (righe 115 e 119) con 60 CSV grezzi e 55 canoniche dal manifest 20261015T0835, con rimando a questo report; backup in reports/README_backup_20261015.md. Autorizzato da Marco 15/10 19:44.
- **18/10/2026 22:25** – Nuovo output `outputs/lst_campaigns_multiday_20261018T2218/` ([README](../outputs/lst_campaigns_multiday_20261018T2218/README.md) · [REPORT_SINTESI.pdf](../outputs/lst_campaigns_multiday_20261018T2218/report_sintesi/REPORT_SINTESI.pdf)). Confronto tra le anomalie spaziali di Tair MeteoTracker e le anomalie LST V18 per 24 campagne in 5 giorni: 04/06 COLD, 20/06 HOT e 22/07 COLD (AOI 90%) canonici; 30/07 HOT e 08/09 MILD backfill. Manifest `campaign_manifest_20261015T0835.csv` (55 canoniche; quello ufficiale ne conta 44). Livello: IMPLEMENTATO / TESTATO / NON VALIDATO. Risultati chiave (FATTO, dagli output):
    - ±30 min attorno alle 12:00 ora di Roma (riferimento; ora di acquisizione nominale 10:00 UTC, assunta): dati solo per 22/07, 30/07 e 08/09 (4 passaggi, 339 pixel); 04/06 e 20/06 senza dati. ρ di Spearman per giorno: 22/07 −0,14; 30/07 0,74; 08/09 0,95 (10 pixel). Pool ρ 0,43, IC per campagna [−0,22; 0,74], detrend 0,45 [−0,26; 0,76]: nessuna evidenza robusta.
    - Sensibilità: ±15 min pool ρ 0,44 (detrend 0,07); ±60 min pool ρ 0,48 [−0,19; 0,65] (detrend 0,31).
    - Giornata intera (descrittivo): pool ρ 0,56 [0,38; 0,68], detrend 0,43 [0,20; 0,60] (22 passaggi, 21 campagne, 2381 pixel). Per giorno: 04/06 −0,09; 20/06 0,71; 22/07 0,41; 30/07 0,63; 08/09 −0,03. Escludendo i pixel sopra 100 m: 0,34 [0,18; 0,45], detrend 0,21 [0,03; 0,35]. Buona parte del segnale viene dal contrasto collina/pianura (quota).
    - Valori assoluti (solo descrittivi, offset V18 −8/−9 K): differenza media LST − Tair per passaggio da −2,24 a +7,49 °C.
    - Limiti: V18 rende circa metà del contrasto inter-classe di Landsat, quindi ampiezze e pendenze delle anomalie non sono fisiche (RICORDO B058, commit 672cb30 non trovato); `qc_coord_outside_aoi` è NA in gps_qc.py:87 (FATTO); detrend solo lineare; LCZ solo descrittive (A/D confuse con la quota).

- **05/11/2026** – Passi E0 1–4 (locale DICAM; autorizzati da Marco). FATTI verificati:
    - **Passo 1:** puntatore ufficiale data/manifests/campaign_manifest.csv promosso al contenuto E0 SHA256 81C903DE6240E2DEE448CB3DB89122FD2531C97C624B110F34B1E7CEDB16C264 (60 righe / **55 canoniche** / 5 esclude). Archivio senza delete: campaign_manifest_preE0_44canonical_20260731.csv (precedente ufficiale a 44 canoniche). Copia datata campaign_manifest_E0_20261015T0835.csv. Analisi 20261015/18 intatte.
    - **Passo 2:** saltato — outputs/recommended_20261015T0835 già allineato.
    - **Passo 3:** AOI = confine Comune di Bologna da data/external/boundaries/confine_comune_bologna.gpkg → data/aoi/bologna_e0_aoi_v0.1.geojson (WGS84, buffer 0 m). gps_qc.py imposta qc_coord_outside_aoi True/False (NA solo se coordinate mancanti). src/meteotracker_qc/flag_table.py emette flag long-form da e0/qc_flag_schema_E0_v0.1.yaml (hook emit_flag_table). 19 test focused passati. Tocca anche pipeline/config/resources/e0 docs/tests.
    - **Passo 4 (~17:03 Europe/Rome):** output nuovo outputs/e0_qc_split_20261105T1703/ — **55/55** campagne OK, 0 failed. lag_table_E0.csv **165735** righe (warn 105846 / exclude 59857 / info 32). Top flag: qc_segment_restart_recovery 27253; qc_speed_disagreement 27040; qc_low_ventilation_possible 20066; qc_low_speed_device 18852; qc_unrealistic_acceleration 18663; qc_coord_repeated 15254; qc_sensor_stabilization 9560; qc_stationary 8549; qc_gps_freeze 8299; **qc_coord_outside_aoi 6566**. Split: n_obs 72505; n_days 17; n_routes non-null 604 (obs: cv2 36731 / seg 15262 / NA 20512); n_spatial_blocks 570; routes ≥3 campagne 40. **LCZ WARNING:** nessun asset sotto data/; usato D:\projects\LCZ\LCZ_PRISMA.shp (coverage 0,9148). Helper: e0/run_e0_step4_qc_split.py, e0/build_split_assignments_e0.py. Nessun overwrite 20261015/18; raw intatto. Albero QC **non** committato (~458 MB): citato qui.
    - Note scientifiche: i flag QC non cancellano mai; tenere separati temporale vs spaziale; catalogo ufficiale = manifest E0 a **55** canoniche (non più 44). V18 resta baseline congelata / non filone guida (vedi entry 18/10).
- **06/11/2026** – Passi E0 5–6: aggiornamento di questo changelog; commit del lavoro E0 locale + push del branch `feat/meteotracker-windows-app` (inclusi i commit locali precedenti non ancora su origin). Niente force-push; niente delete raw; output storici 20261015/18 non toccati.
- **09/11/2026 ~10:55** - P1 ripetibilità sullo split E0 (autorizzato da Marco il 9/11, via coordinatore). Nuovo output `outputs/p1_repeatability_E0_20261109T1041/` ([summary.md](../outputs/p1_repeatability_E0_20261109T1041/summary.md); locale, non in git). Codice: `src/meteotracker_qc/p1_repeatability/`, `e0/run_p1_repeatability_e0.py`, test `tests/test_p1_repeatability.py`, metodo `e0/P1_REPEATABILITY_E0.md`. Livello: IMPLEMENTATO / TESTATO / NON VALIDATO. Metodo 20261015 riusato: R = Σcov/Σ√(var·var), r di Fisher, bootstrap per campagna, celle 50 m. Novità: località E0 (route, spatial_block 500 m), maschere QC permissive/recommended/restrictive + flag-table, coppie separate same_campaign / stesso giorno / giorni diversi, leave-one-campaign/day/route/block, ICC per località. FATTI (dagli output):
    - **Coppie di giorni diversi, recommended:**
        - route centered R 0,42 [0,19; 0,54] (781 coppie, 46 campagne, 24 route); detrended 0,22 [0,01; 0,35];
        - blocchi centered 0,23 [0,10; 0,39] (2285 coppie, 83 blocchi); **blocchi detrended 0,04 [−0,03; 0,11], IC include 0**;
        - permissive simile (route 0,38 / 0,22; blocchi 0,25 / 0,05).
    - **Restrictive e flag-table: tutti gli IC includono 0** (route centered 0,12 [−0,30; 0,48] e −0,01 [−0,27; 0,30]), con 128 e 127 coppie e 14 e 15 route.
    - **Leave-one-* (recommended):** nessuna esclusione porta R ≤ 0, ma R route centered passa da 0,42 a 0,17 senza cv2_004 (la salita). Intervalli: campaign 0,37–0,44; day 0,30–0,46; route 0,17–0,46; block 0,25–0,44.
    - **Temporale vs spaziale:** coppie same-campaign (Δt mediano 21 min) solo 15 su 928 sulle route, cioè **quota 1,6%** (blocchi 1,9%). R same-campaign 0,51 [0,29; 0,64] e stesso giorno 0,42 [0,02; 0,61]: la ripetibilità a breve Δt resta non separabile dal contesto del giro (come short_dt 20261015, share 1,0).
    - **Livello località (recommended):**
        - ICC tra località: route 0,34 [0,21; 0,47], blocchi 0,35 [0,20; 0,49] (IC jackknife per campagna);
        - dopo la quota (lineare) l'ICC scende a 0,26 [0,07; 0,45] e 0,17 [0,04; 0,30].
    - **Potenza (recommended):**
        - località con almeno 3 campagne dopo QC: 25 route su 195 e 93 blocchi su 408 (lo split dichiarava 40 route su tutte le osservazioni pre-QC);
        - IC per località sopra 0 solo per 2 route su 24 e 9 blocchi su 83.
    - **Verdetto:** ripetibilità inter-giorno modesta, diversa da 0 con recommended/permissive, in larga parte gradiente a grande scala o quota. Non supportate: strutture sotto i 500 m, affermazioni per singola località, conclusioni con le maschere restrictive o flag-table, separazione temporale/spaziale a breve Δt, effetto urbano.
    - **Discrepanza (blocker dati):** le severity `exclude` di `flag_table_E0` sono etichette statiche per codice e non coincidono con `keep_recommended`: accordo per riga 48,6%, 46 163 righe con flag exclude contro 16 887 escluse da recommended. Il P1 usa `keep_<profilo>` come principale e la flag-table letterale come sensibilità. Serve una decisione di Marco.
    - Nessun input LST/LCZ (regola 2019–2022 non applicabile); V18 non toccato. Nessun overwrite di 20261015/18 o e0_qc_split; raw intatto. Le cartelle `..._20261109T1029_quick` e `..._20261109T1030` sono superate (marcate SUPERSEDED.txt, non cancellate).
- **09/11/2026** - README: allineate le occorrenze del conteggio canonico corrente da 44 a **55** (`README.md` riga 119; `docs/GATE_2_1_STATUS.md` §2). I riferimenti storici a 44 sono mantenuti come storia. Solo documentazione.
- **09/11/2026 ~11:30** - Audit del disaccordo tra severity `exclude` di `flag_table_E0` e `keep_*` della pipeline (autorizzato da Marco il 9/11 alle 11:08, via coordinatore). **Nessuna QC è dichiarata ufficiale; nessuna config modificata.** Output `outputs/qc_mask_audit_E0_20261109T1113/` ([summary.md](../outputs/qc_mask_audit_E0_20261109T1113/summary.md); locale, non in git). Codice: `src/meteotracker_qc/qc_mask_audit.py`, `e0/run_qc_mask_audit_e0.py`, test `tests/test_qc_mask_audit.py`, metodo `e0/QC_MASK_AUDIT_E0.md`. Livello: IMPLEMENTATO / TESTATO / NON VALIDATO. FATTI (dagli output):
    - 72 505 punti. Stato FT: exclude 46 163, warn-only 15 514, ok 10 828.
    - Recommended: accordo 48,6% (κ 0,10). FT exclude ma pipeline tiene: 33 288. Pipeline scarta senza FT exclude: 4 012. Restrictive: accordo 70,4% (κ 0,35). Permissive: 36,3% (κ 0). L'accordo per campagna va dal 9% al 100%.
    - Codici principali: qc_segment_restart_recovery 24 003 (schema exclude r. 50 vs policy INFO_ONLY r. 30); qc_unrealistic_acceleration 15 508 (exclude vs EXCLUDE_RESTRICTIVE); qc_gps_freeze 4 012 (schema warn vs EXCLUDE_RECOMMENDED); qc_post_stop_recovery 2 540 (exclude vs INFO_ONLY); qc_time_duplicate 572 (nessuna riga di policy).
    - Meccanismo: la FT usa la severità fissa per codice dello schema E0 (`flag_table.py:106-119`); `keep_<p>` usa le azioni per profilo di `flag_policy.csv` (`policy.py:9-16`).
    - 372 timestamp duplicati (dt = 0) generano 372 dei 482 cambi segmento (`time_qc.py:119`). Ne derivano circa 15 500 punti restart_recovery spuri (`stabilization.py:191`).
    - Permissive non esclude nulla per scelta di progetto, non per bug: esclude solo EXCLUDE_ALL_SCIENTIFIC (`flag_policy.csv` r. 2, 31-33), che in E0 conta 0 punti. Le colonne `keep_*` di E0 sono proiezioni con le soglie di recommended (`policy.py:38-49`).
    - P1 route, coppie di giorni diversi: recommended 0,42 [0,21; 0,55]; union 0,42 [0,21; 0,55]; consensus (rec ∧ nessun FT exclude) 0,01 [−0,26; 0,32], con 126 coppie invece di 781. Il segnale P1 dipende dalla maschera.
    - Raccomandazione (solo proposta): unica fonte `flag_policy.csv`, con severità della FT derivata per profilo; correggere i cambi segmento da dt = 0; allineare unrealistic_acceleration, post_stop e restart_recovery, gps_freeze e gli alias; per i profili ufficiali permissive/restrictive rieseguire con le YAML proprie. Read-only: nessun overwrite di e0_qc_split, p1_repeatability, 20261015/18; raw intatto.
- **09/11/2026 ~13:00** - E0-QC-R: revisione QC E0 con policy versionata v0.2 (autorizzata da Marco il 9/11 alle 12:01, via coordinatore). **Nessuna QC dichiarata ufficiale; config e archivi v0.1 intatti.** Criteri pre-registrati `e0/QC_R_CRITERIA_E0.md` (commit ffac604, prima di ogni P1). Rapporto: [e0/RAPPORTO_E0_QC_R.md](../e0/RAPPORTO_E0_QC_R.md) (copia in `outputs/e0R_qc_report_20261109T1300/`). Livello: IMPLEMENTATO / TESTATO / NON VALIDATO. FATTI (dagli output): fix dt=0 (segmenti 537?165; nuovo `qc_duplicate_record`, 84 righe); `qc_gps_freeze` ? EXCLUDE_RESTRICTIVE (93,5% soste reali); `qc_unrealistic_acceleration` invariato (87% rumore GPS); recovery restart/post-stop ? WARNING_ONLY (nessun transitorio, test a bassa potenza); flag table e keep coincidono per costruzione (0 discordanze, 3 profili); keep v0.2: permissive 72.505, recommended 59.209, restrictive 19.768. P1 su popolazione comune: le maschere cambiano R di ?0,02 (IC di ?R include 0); R route grezzo 0,35 [0,09; 0,51] ? 0,12 [?0,07; 0,31] senza cv2_004; servono ?400 coppie diff-day perch? l'IC escluda 0. Output: `outputs/e0R_qc_evidence_20261109T1236/`, `e0R_mask_audit_20261109T1238/`, `e0R_qc_split_20261109T1240/`, `p1_repeatability_E0R_20261109T1243/` (locali, non in git). Opzioni per la decisione nel rapporto ?7.
- **09/11/2026 ~15:00** - E0-QC-R final validation (autorizzata da Marco il 9/11 alle 14:23, via coordinatore). **Nessuna QC dichiarata ufficiale; nessuna severità o soglia modificata; config, raw e output storici intatti.** Rapporto: [e0/RAPPORTO_FINAL_VALIDATION_E0_QC_R.md](../e0/RAPPORTO_FINAL_VALIDATION_E0_QC_R.md) (copia in `outputs/e0R_final_validation_20261109T1430/`, locale, non in git). FATTI:
  - Campagna 05-27 13:08: warm-up da 91 a 1.395 punti. Causa: il fix dt=0 (6 segmenti diventano 1) espone un difetto preesistente di `qc_sensor_stabilization`. Il gate di pendenza è limitato dalla quantizzazione a 0,1 °C (nessuna variazione della mediana per 60 s) e c'è un'asimmetria con `max_window_s`. In v0.1 lo stesso effetto c'era già, come 929 righe di restart_recovery INFO. Nessun warm-up reale: sensore acceso 74 s prima, nessun transitorio. Escluso segnale spaziale reale (collina cv2_003, cv2_004 intera). Proposta P-0527 (cap a 300 s) documentata, NON applicata.
  - Test: `test_runtime_import_closure_is_in_the_installed_package` falliva dal 15/10 (`0bbbb16`), quindi non è una regressione. Fix: `corridors_v2/validate.py` ora ha `main()`, con output byte-identici. Suite completa 624 passati, 1 saltato (passa con --real-data), 0 falliti.
  - Schema: le copie v0.2 in `resources/` puntano allo schema incluso nel pacchetto, byte-identico al canonico (sha256 11edae4f…). Verificato da un wheel installato con cwd estranea.
  - P1 (riuso degli output validati, più una sensibilità esplorativa P-0527): sulla popolazione comune |ΔR| ≤ 0,007. R route su popolazione propria: v0.1 0,42, v0.2 0,34, v0.2+cap 0,43 (effetto di popolazione del warm-up). Senza cv2_004 l'IC include 0. Servono ≥ 400 coppie diff-day.
