# Applicazione Windows — Gate 2

La GUI PySide6 chiama direttamente `ApplicationService`, lo stesso application layer
usato dalla CLI. Core scientifico, staging, soglie, analisi globali e rollback restano
nel servizio e nelle pipeline. I widget presentano risultati ed eventi strutturati.

**Portable e installer saranno realizzati nel Gate 3.** Questo Gate non produce
eseguibili autonomi, installer, workflow di build, release o firma digitale.

## Installazione di sviluppo

Da PowerShell, con Python 3.11–3.14 e una workspace esistente:

```powershell
cd D:\projects\Meteotracker
python -m venv .venv-gui
.\.venv-gui\Scripts\python.exe -m pip install -e ".[gui,test]"
.\.venv-gui\Scripts\meteotracker-gui.exe
```

L'extra `gui` installa PySide6; `test` aggiunge pytest e pytest-qt. Per riprodurre
l'ambiente scientifico Windows CPython 3.14 validato, aggiungere all'installazione
`-c constraints-scientific-win-py314.txt`. I raw non sono inclusi nel package.

Avvii equivalenti, anche da una directory diversa:

```powershell
meteotracker-gui --workspace "D:\progetti\Workspace città"
python -m meteotracker_qc.gui --workspace "D:\progetti\Workspace città"
meteotracker-gui --smoke-test
```

Lo smoke test importa Qt, crea l'applicazione e la finestra, verifica le quattro
schede e termina. Non avvia discovery, check o pipeline e non salva impostazioni.

## Workspace e panoramica

Al primo avvio selezionare una workspace esistente che contenga `data/raw`,
`data/manifests`, `config`, `outputs` e `logs`. Una selezione non valida mostra un
messaggio e conserva l'eventuale workspace precedente. `Scegli workspace` consente
di cambiare progetto quando nessuna operazione è in corso.

QSettings conserva soltanto ultima workspace, geometria e filtro grafico. Una
finestra salvata fuori dagli schermi disponibili viene riportata sullo schermo.
Percorsi con spazi e Unicode sono supportati e non vengono passati a una shell.

La Panoramica mostra doctor, campagne e CSV registrati, nuovi CSV, ultimo run,
lock, avvisi e pulsanti per aprire rapporto, output e log. `Aggiorna panoramica e
cronologia` rilegge il servizio senza elaborare o promuovere nuovi dati.

## Scansione e selezione

In **Nuove campagne**, `Scansiona data/raw` cerca ricorsivamente i nuovi CSV.
`Aggiungi cartella` accetta cartelle multiple; si possono anche trascinare più
cartelle nella finestra. Una cartella è un batch e può contenere più CSV, anche
annidati. Gli stessi CSV non vengono aggiunti due volte.

Selezionare i batch con Ctrl/Shift. Facoltativamente selezionare righe CSV per
controllare soltanto quelle. Il filtro cambia la visualizzazione, non la selezione
del batch. La tabella ha una riga per CSV, con stato testuale, batch, file,
campagna, righe, intervallo temporale, QC, suitability, route matching, problemi e
rapporto. Le intestazioni ordinano le righe; tooltip e doppio clic mostrano dettagli.

Le cartelle esterne vengono lette, senza importazione automatica. Per applicarle,
copiare esplicitamente gli input in `data/raw`, poi effettuare nuova scansione e check.

## Check e aggiornamento

`Controlla nuove campagne` chiama `ApplicationService.check()`. Il check non modifica
raw, manifest, configurazioni o output scientifici ufficiali. Il servizio usa staging
temporaneo sotto `logs`, lo rimuove al termine e salva i rapporti in `logs/check_reports`.
QC e suitability derivano dalle pipeline; il route matching è indicato come
pianificato, perché l'analisi globale viene eseguita nell'apply.

`Elabora e aggiorna il progetto` richiede un check riuscito della selezione corrente,
almeno un nuovo canonico, nessun ambiguo/invalido, input interni a `data/raw`, workspace
libera e nessun altro worker. Cambiare selezione o aggiungere cartelle invalida il
check. Il servizio ricontrolla la corrispondenza degli input prima della conferma,
sotto lock e prima della promozione: se gli input sono cambiati, occorre ripetere il check.

La conferma elenca batch, campagne, fasi, target, backup e artefatti stale. La scelta
predefinita è Annulla. Tutti i CSV selezionati costituiscono **un unico batch applicativo**:
Session QC, repeated routes, consolidamento many-to-many, spatial density e temporal
drift hanno ciascuno una sola pianificazione globale, oltre al QC dei punti.

I target aggiornati sono manifest, tre profili QC, Session QC, repeated routes,
spatial density, temporal drift e rapporto di ingestione. Il backup è temporaneo e
serve al rollback della transazione; non è un archivio permanente. Gli output e
rapporti storici non rigenerati vengono elencati come potenzialmente stale.

Per consultare un progetto con l'apply disabilitato:

```powershell
meteotracker-gui --workspace "D:\progetti\Workspace città" --read-only
```

In questa modalità il check usa comunque staging temporaneo locale, ma non salva
nuovi rapporti persistenti. Gli eventi e i risultati restano visibili nella GUI.
Nel Gate 2 l'apply viene testato esclusivamente su workspace sintetiche temporanee;
i batch ufficiali 8-1 e 9-8 non vengono applicati.

## Worker e cancellazione

Ogni operazione lunga usa un QThread. I risultati e gli eventi attraversano segnali
queued verso slot del thread GUI; il worker non modifica widget. È ammessa una sola
operazione per finestra. Errori e completamento rilasciano il worker e ripristinano i controlli.

`Annulla` richiede una cancellazione cooperativa: durante discovery vengono controllati
i confini dei file; durante QC e analisi si attende il successivo confine sicuro della
fase. Una fase scientifica può quindi terminare prima dell'annullamento.

La promozione non viene interrotta a metà. Una cancellazione ricevuta durante la
promozione viene verificata al termine di tutti i target, con rollback attraverso il
meccanismo esistente. Il messaggio della GUI segnala l'attesa del punto sicuro. Se la
richiesta arriva dopo l'ultimo punto cancellabile, l'aggiornamento è già completato.
La chiusura della finestra richiede cancellazione e attende cleanup e rilascio del
lock; non termina brutalmente il worker. Le transazioni annullate hanno stato
`cancelled` nel ledger.

## Cronologia, log e risultati

La Cronologia legge `logs/run_ledger.json`: run ID, data, comando, stato, durata,
campagne, rapporto e rollback. Il doppio clic apre il rapporto del run, se presente.
La scheda Log mostra progressivamente gli eventi strutturati del servizio.

L'apertura dei risultati passa dal servizio: verifica esistenza, percorso risolto
interno alla workspace (oppure radice esplicitamente autorizzata dall'application
layer) e tipo di file. URL, comandi, eseguibili e percorsi esterni non autorizzati
vengono rifiutati. Un file mancante produce un messaggio senza arrestare la GUI.

## Test

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:MPLBACKEND = "Agg"
python -m pytest tests/test_gui.py tests/test_application_gui_contract.py -W error -o cache_dir=.pytest_gui_cache
```

Le prove sono comportamentali e non dipendono da coordinate pixel. Comprendono
entry point, impostazioni, selezione, drag-and-drop, responsività, errori, conferma,
apply sintetico reale, cancellazione con rollback, many-to-many e assenza di doppio
conteggio. Un guard dei test vieta l'apply sulla workspace ufficiale.
