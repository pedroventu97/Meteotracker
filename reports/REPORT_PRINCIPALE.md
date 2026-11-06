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
- Allineare `README.md` al manifest attuale (vedi discrepanza sotto).

## Discrepanze note
- `README.md` (modificato il 09/09/2026) **non contiene "34 campagne"**: la frase indicata non è stata trovata. Il README riporta invece dati superati:
  - riga 115: "Of the 49 raw CSVs under `data/raw/` (39 through the original audit, plus 10 more added 2026-08 …), 5 are redundant re-exports…";
  - riga 119: "By default, `run_qc.py` processes only the 44 canonical campaigns (`exclude_from_analysis == False` in the manifest)…".
  - Il manifest ufficiale campaign_manifest.csv è dal 5/11/2026 il contenuto E0 (60 righe / 55 canoniche; SHA256 81C903DE…C264); la copia datata resta campaign_manifest_20261015T0835.csv / campaign_manifest_E0_20261015T0835.csv. Archivio pre-E0 (44 canoniche): campaign_manifest_preE0_44canonical_20260731.csv.
  - Il README non è stato modificato.
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
