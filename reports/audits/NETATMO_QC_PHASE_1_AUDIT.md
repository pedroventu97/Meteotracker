# Netatmo QC Phase 1 — audit preliminare

Data: 2026-09-28. Stato: AUDIT_ONLY / IMPLEMENTATION_PENDING_WORKSPACE_SELECTION.
Questo documento non attesta il completamento della pipeline o la validazione dei dati.

## Repository e fonti lette

La workspace di questa sessione è `D:/projects/Meteotracker`; la richiesta riguarda
`D:/projects/bologna_urban_climate_integration`, distinto repository accessibile in
lettura ma fuori dalle radici di scrittura della sessione. Il collector e la dashboard
Netatmo sono in `D:/projects/netatmo`.

Documentazione consultata: README e INTEGRATION_GUIDE Meteotracker; specifica
`MASTER_SCIENTIFIC_SPECIFICATION_v2.2.md` nell'integrazione; registri P0,
`docs/known_limitations.md`, `docs/scientific_integration_contract.md`; manifest
Netatmo e codice di snapshot, copertura giornaliera e normalizzazione upstream.

## Input e conteggi già documentati

Il manifest dell'integrazione seleziona lo snapshot `netatmo_20260916T132430Z`:

| Indicatore | Valore registrato |
|---|---:|
| Osservazioni long | 3.663.370 |
| Device | 341 |
| Moduli | 683 |
| Moduli temperatura/umidità | 342 |
| Record temperatura/umidità | 1.831.667 |
| Moduli pressione | 341 |
| Record pressione | 1.831.703 |

Periodo UTC registrato: 2026-06-25T10:26:13+00:00 — 2026-09-16T13:22:02+00:00.
Hash SHA-256 registrato dello snapshot:
`23c7f824b387a293dcc5830da402e0ba627959d2e73e3d0f4a1051307c3780d9`.
Questi valori provengono dai manifest/censimenti esistenti: non sono una nuova
verifica di cardinalità o checksum eseguita in questa sessione.

Il database live è presente in `D:/projects/netatmo/data/netatmo_bologna.sqlite`.
Non è stato aperto né modificato. Esistono snapshot SQLite e derivati Parquet
partizionati per anno/mese/giorno locale nell'integrazione. Le campagne MeteoTracker
sono disponibili nel catalogo ufficiale `outputs/campaign_catalog.csv` upstream.

## Componenti riutilizzabili

- `netatmo_analytical_snapshot.py`: esportazione long, provenienza verso chiave
  originale `(station_id, module_id, timestamp_utc)` e snapshot.
- `netatmo_daily_coverage.py`: `local_day_utc_bounds`, già compatibile con DST;
  diagnostica di rete distinta dalla copertura per device.
- `netatmo_known_gaps.py` e manifest gap: interruzione documentata del 15–16 luglio.
- Catalogo MeteoTracker: ID canonici, inizio/fine UTC, provenienza e percorsi QC.
- Upstream `netatmo_qc/station_normalization.py`: matching T/RH–pressione con
  timestamp distinti, tracciabilità delle righe, gestione delle ambiguità e
  ricostruzione sperimentale di episodi spaziali.
- Upstream `netatmo_qc/completeness.py`, dashboard Streamlit e test esistenti.

## Identità e conflitti da risolvere esplicitamente

La normalizzazione upstream definisce `canonical_station_id` come identità del
device principale, non come sito fisico. `deployment_id` è un episodio spaziale
ricostruito con soglia configurabile di 50 m. Non equivale a un deployment validato.
La specifica v2.2 richiede identità fisiche basate su evidenze e lascia ignote quelle
non dimostrate. Non si possono dichiarare 341 stazioni fisiche normalizzate.

Il rapporto upstream del 14 settembre documenta un device con due moduli termici
e cinque gruppi di coordinate condivise tra device. Sono casi da riesaminare nello
snapshot selezionato, non prove sufficienti per unificare o separare siti fisici.

La tabella `scientific_v1` conserva physical_station_id e deployment_id NULL:
non va aggiornata retroattivamente con identità inferite.

Metà circa delle osservazioni riguarda pressione senza temperatura: questa
mancanza è strutturale e non costituisce automaticamente un errore termico.
Una tabella wide accoppiata non conserva la cardinalità della tabella long;
la normalizzazione osservazionale richiesta deve mantenere ogni riga sorgente.

## QC e assunzioni esistenti

Il QC della dashboard è calcolato in memoria sulla selezione corrente:
range termico [-20, 50] °C, scarto dalla mediana della finestra >6 °C,
salto >4 °C con 0 < delta-t <=30 minuti. Non è QC scientifico persistente.
Il controllo rispetto alla mediana della selezione non deve diventare un criterio
automatico di esclusione delle anomalie locali.

Lo snapshot usa limiti strutturali [-40, 60] °C, non soglie scientifiche di esclusione.
La frequenza nominale esistente è 10 minuti; la copertura di rete e quella sullo
span attivo non equivalgono alla completezza termica dell'intero giorno.
Le soglie QC scientifiche e di copertura restano decisioni aperte della Master.

Il parser storico dello snapshot attribuisce UTC ai timestamp naive; il contratto
scientific_v1 li rifiuta. La nuova normalizzazione deve renderli espliciti tramite
flag/provenienza, evitando assunzioni silenziose.

## Mancanze rispetto alla richiesta

Non sono ancora stati implementati in questa sessione: mapping fisico documentato,
tabella normalizzata con QC persistente, station inventory fisico, station-day,
station-daytime configurabile, spike/persistence/oscillation QC, station-day QC,
station summary, campaign windows, diagnostica integrata e interfaccia ARPAE.
I sette output richiesti non sono stati generati.

## Verifiche e limiti

Sono state eseguite esclusivamente ispezioni in lettura di directory, manifest,
documenti e codice. Nessun codice sorgente o RAW è stato modificato. Questo report
è l'unico nuovo file prodotto. Nessuna pipeline, test sintetico o suite di
regressione è stata eseguita; nessuna distribuzione QC nuova è disponibile.
Non è stato introdotto alcun modello temporale, Kriging, fusione o confronto LST/ARPAE.

## Passo successivo

Confermare il repository destinatario e lavorare nella relativa workspace.
Poi implementare e verificare la fase Netatmo QC riusando i componenti elencati,
tenendo separati device, identità fisica verificata e deployment inferito;
aggiornare questo audit con conteggi ricalcolati, hash prima/dopo, soglie esplicite,
risultati dei test e limitazioni residue. L'assenza di identità fisiche dimostrate
deve restare un limite esplicito del criterio di completamento.
