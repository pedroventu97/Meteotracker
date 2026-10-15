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
- Commit **0bbbb16** solo in locale ("feat: corridors_v2, manifest refresh (55 canonical), session GUI updates"); **nessun push**. Il push è ancora in sospeso.
- Le nuove analisi (pass_anomaly, short_dt) restano non tracciate da git: nessun commit.
- Regola dal 15/10/2026: un solo report principale vivo per filone di lavoro (questo file).

## Prossimi passi
- Più passaggi indipendenti sugli stessi percorsi, con copertura completa di ciascun segmento.
- Un modello con covariate esplicite (quota, velocità, irraggiamento).
- Una prova controllata del ritardo del sensore.
- Una validazione con stazioni fisse (ARPAE, Netatmo) e con date tenute da parte.
- Il confronto LST–Tair con finestra ±30 min (sensibilità ±15 e ±60).
- Decidere il push del commit 0bbbb16.
- Allineare `README.md` al manifest attuale (vedi discrepanza sotto).

## Discrepanze note
- `README.md` (modificato il 09/09/2026) **non contiene "34 campagne"**: la frase indicata non è stata trovata. Il README riporta invece dati superati:
  - riga 115: "Of the 49 raw CSVs under `data/raw/` (39 through the original audit, plus 10 more added 2026-08 …), 5 are redundant re-exports…";
  - riga 119: "By default, `run_qc.py` processes only the 44 canonical campaigns (`exclude_from_analysis == False` in the manifest)…".
  - Il manifest attuale 20261015T0835 ha 60 righe e 55 campagne canoniche non escluse.
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

## Changelog
- **15/10/2026 19:40** – Creazione del report principale. Nessun equivalente esistente: in `reports/` ci sono solo l'audit QC del 25/07, il report di sessione del 31/07 e quello di pulizia del 25/07; in `docs/` ci sono `GATE_2_1_STATUS.md` e simili, che sono specifici di un singolo gate. Risultati inseriti fino a `short_dt_anomaly_20261015T1927`.
- 2026-10-15 19:50: README aggiornato (righe 115 e 119) con 60 CSV grezzi e 55 canoniche dal manifest 20261015T0835, con rimando a questo report; backup in reports/README_backup_20261015.md. Autorizzato da Marco 15/10 19:44.
