# Analisi delle sessioni — Gate 2.1

Aprire la GUI e scegliere **Analizza sessioni** nella barra superiore. Si apre una
finestra dedicata alla stessa workspace: premere nuovamente il pulsante riporta in
primo piano la stessa istanza. La navigazione nella finestra principale resta indipendente.

## Selezione e mappa originale

La lista contiene le campagne canoniche del manifest, una riga per sessione: i
re-export esclusi e i CSV ancora nuovi non diventano ulteriori sessioni. Una cartella
può contenere più sessioni. Spuntare una o più righe, oppure usare **Seleziona visibili**.
Ricerca, date locali in formato `YYYY-MM-DD`, batch e stato filtrano l'elenco; una
selezione già spuntata resta tale anche se un filtro la nasconde. **Deseleziona tutto**
azzera anche le selezioni nascoste.

La mappa originale appare automaticamente prima del QC. Il caricamento avviene in
un worker; se cambia la selezione, i risultati precedenti vengono ignorati. Sono
visibili partenza, arrivo, direzione, punti sospetti e interruzioni preliminari. Le
linee non collegano sessioni differenti e non attraversano gap/salti rilevati dalla
visualizzazione preliminare. Questi indicatori non sostituiscono i flag del motore QC.

Ogni sessione mantiene colore e identità; la legenda permette di nascondere le
tracce. Zoom, pan e ripristino dell'estensione sono nella barra della mappa. Passare
sui punti o cliccarli mostra i dettagli: timestamp, coordinate, meteo, velocità e
indicatori. Il testo completo è anche nel tooltip. Il riepilogo della sessione è
nel tooltip della traccia. La decimazione riguarda soltanto il disegno: tutti i
punti originali restano disponibili per QC, statistiche ed export.

Lo sfondo è locale e funziona senza rete. Il CRS geografico e quello metrico sono
letti da `config/repeated_routes_recommended.yaml` (nella workspace attuale EPSG:4326
e EPSG:32632). Distanze e scala non vengono misurate in gradi. La freccia indica il
nord della griglia. Il confine locale convenzionale è
`data/external/boundaries/confine_comune_bologna.gpkg`; un percorso diverso, relativo
alla workspace, può essere indicato in `user_presets/map.json` come `boundary_path`.
Il confine deve avere CRS e geometria validi; l'assenza o un errore non blocca la mappa.

**Densità esplorativa** visualizza la distribuzione dei punti nelle celle; non è il
prodotto scientifico spatial density né un conteggio validato dei passaggi.
**Sovrapposizioni 50 m** evidenzia celle condivise da sessioni diverse, senza eseguire
route matching. Queste visualizzazioni sono esplicitamente esplorative.

Gli splitter regolano lo spazio. **Pannelli QC** permette di nascondere i pannelli
superiori ed espandere la mappa. I pannelli hanno barre di scorrimento quando lo
spazio è ridotto. Dimensione e posizione della finestra vengono ricordate.

## Profili e controlli

Recommended, Permissive e Restrictive usano gli YAML esistenti senza modificarli.
Le checkbox agiscono sui detector prima dell'applicazione delle policy; non
nascondono colonne prodotte dal QC. Disattivare un gruppo passa a **Personalizzato**.
Il profilo di origine è esplicito; i tooltip dei gruppi mostrano descrizione,
parametri correnti, unità e file di origine. Le regole del Session QC e della
suitability si consultano con **Soglie e regole Session QC / suitability**.

Schema, distanza e completezza sono prerequisiti/metriche obbligatori. Il controllo
autonomo coordinate non valide/AOI non esiste nel motore e viene dichiarato non
disponibile. Parsing temporale, segmentazione e geometrie rappresentabili restano
prerequisiti anche disattivando la relativa segnalazione. Il warm-up mantiene le
proprie dipendenze dalla velocità; disattivare ventilazione disattiva i suoi flag,
non il detector indipendente di stabilizzazione.

Solo i parametri dichiarati modificabili possono essere cambiati; tipi, intervalli,
unità e relazioni minimo/massimo sono validati. Il pannello differenze mostra ogni
variazione. **Ripristina** torna al profilo di origine. I preset sono JSON separati in
`user_presets/`: nome, descrizione, data, origine, controlli, override, versione schema
e fingerprint. Un preset con schema o configurazioni di origine differenti viene
rifiutato e deve essere ricreato.

## Esecuzione e risultati

**Anteprima QC** lavora in una directory temporanea. Non aggiorna raw, manifest,
output o cache ufficiali. Le tre configurazioni ufficiali vengono rieseguite
indipendentemente: il confronto `keep_by_profile` non deriva dalle sole proiezioni
di policy di un singolo frame. Una configurazione personalizzata produce una
quarta esecuzione, con conteggio mantenuto separato.

Il Session QC standard mantiene il riferimento recommended e le tre maschere
reali del motore esistente. Per il risultato personalizzato, le metriche di
Session QC usano coerentemente la maschera runtime nei tre slot delle metriche;
il confronto con i tre profili standard è riportato separatamente. La policy
di classificazione resta `recommended_session`; questa scelta è registrata nel
rapporto. I controlli disattivati sono identificati come **Disattivato**, non come
valutati con esito positivo.

Il riepilogo espone osservazioni, keep, flag, metriche meteo/temporali/spaziali,
warm-up, Session QC, suitability ed eligibility. Quest'ultima usa la preparazione
tracce e l'inventario esistenti; non lancia il matching e non ne modifica la cache.
I conteggi per famiglia sono unioni di righe, non somme di flag sovrapposti.

Scegliere una sessione nella tendina dei risultati per consultarne riepilogo,
flag e serie temporali. Cliccare un flag o una famiglia apre le righe interessate
(prime 500 nella vista, tutte nel CSV) e le evidenzia sulla mappa. Dopo il QC si
possono visualizzare tutti i punti, mantenuti, flaggati, famiglia e prima/dopo.
I punti esclusi restano disponibili. Il confronto tabellare non fonde osservazioni
di sessioni diverse.

**Annulla** richiede una cancellazione cooperativa al successivo confine di fase.
Chiudere durante un'operazione richiede conferma e attende la pulizia; una chiusura
normale elimina il risultato temporaneo. **Principale** permette di tornare al
progetto mantenendo aperta l'analisi. **Elimina anteprima temporanea** elimina
soltanto gli artefatti temporanei.

## Export e log

Gli export creano sempre una nuova directory `outputs/custom_analyses/<id>/`.
Sono disponibili CSV flagged/strict/relaxed, CSV mantenuti dei tre profili realmente
eseguiti, Parquet, GeoPackage, GeoJSON, Markdown, JSON, configurazioni e PNG.
Ogni export include provenienza; non promuove il risultato a ufficiale e non
sovrascrive una precedente analisi. La selezione cartografica può essere esportata
anche prima del QC, con configurazione, colori/legenda e CRS separati.

Il log mostra ora, livello, fase, sessione, messaggio e avanzamento. Sono disponibili
filtri, copia messaggio e salvataggio JSON, con **Dettagli tecnici** espandibili.

## CLI equivalente

```powershell
meteotracker sessions list --workspace "D:\projects\Meteotracker" --json
meteotracker sessions inspect <campaign_id> --workspace "D:\projects\Meteotracker" --json
meteotracker sessions qc <id1> <id2> --profile recommended --workspace "D:\projects\Meteotracker" --json
meteotracker sessions compare <id1> <id2> --workspace "D:\projects\Meteotracker" --json
```

`list` supporta `--search`, `--batch`, `--status`, `--date-from`, `--date-to`.
`qc`/`compare` supportano `--disable <group_id>`, `--preset <json>` e `--export`.
Senza export, la CLI restituisce il rapporto e rimuove la directory temporanea.
GUI e CLI condividono le stesse operazioni dell'application layer.

Questo Gate non include basemap online, GIS generale, cambi alle soglie scientifiche,
matching personalizzato, executable o installer.
