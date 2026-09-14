# Chiusura scientifica — Gate 1.5

La pipeline scientifica richiede l'insieme di file elencato in
`docs/scientific-closure-files.json`. Il commit di partenza
`8e9e6d81313be58f00dc9b36c60aa523ff057b3b` da solo non lo contiene:
il suo point QC produceva solo `keep_strict` e `keep_relaxed`, mentre Session
QC dipende dalla revisione multi-profilo presente nella workspace di sviluppo.
Il perimetro comprende quella revisione coerente, le dipendenze scientifiche,
le policy, i test portabili e il contratto di distribuzione delle risorse.
Non comprende GUI, build Windows, installer, acquisizioni o output scientifici.

## Catena e sorgenti autorevoli

```text
raw + manifest + config esplicita
  -> schema -> tempo/segmenti -> GPS -> ventilazione/soste
  -> meteo/derivate/stabilizzazione -> flag policy -> tre alberi point QC
  -> Session QC / suitability
  -> repeated routes -> consolidamento many-to-many
  -> spatial density -> temporal drift
  -> validazione staging -> promozione transazionale
```

`MeteotrackerQC.process_file()` esegue i controlli con le soglie del proprio
YAML. `policy.apply_flag_policy()` traduce i flag in severità, motivazioni e
maschere. Nessuna soglia o azione delle configurazioni preesistenti è cambiata
durante la chiusura; gli YAML scientifici modificati prima del Gate sono parte
del perimetro, con i loro valori originari.

| Colonna | Contratto |
|---|---|
| `keep_permissive` | Nessun flag attivo con azione `EXCLUDE_ALL_SCIENTIFIC`. |
| `keep_recommended` | Nessun flag attivo con azione precedente o `EXCLUDE_RECOMMENDED`. |
| `keep_restrictive` | Nessun flag attivo con una delle precedenti azioni o `EXCLUDE_RESTRICTIVE`. |
| `qc_severity_<profilo>` | Numero di flag escludenti attivi nella proiezione di policy del profilo. |
| `qc_severity`, `qc_reason_count`, `qc_exclusion_reasons` | Valori del profilo della singola esecuzione. |
| `qc_bitmask` | Nome storico: contiene il conteggio della severità, non un insieme di bit. |
| `keep_strict`, `keep_relaxed` | Confronto della severità del proprio run con i rispettivi budget `filtering.*` dello YAML. Non sono alias dei nuovi profili. |
| `keep_<profilo>_true` | In Session QC: maschera letta dall'albero prodotto effettivamente con lo YAML di quel profilo. |

Le tre maschere presenti in un singolo parquet applicano policy diverse agli
stessi flag. I flag stessi dipendono dalle soglie del run: per confrontare i
profili completi sono autorevoli i tre alberi separati
`outputs/{permissive,recommended,restrictive}`. Session QC conserva la
segmentazione recommended e allinea per riga le maschere autorevoli degli
altri due alberi. Verifica lunghezza, unicità e ordine di `source_row`, identità
di sorgente/tempo quando presenti e valori booleani non nulli. Uno schema
legacy incompleto è rifiutato esplicitamente; occorre ricalcolare i tre alberi
in staging. I vecchi output non vengono reinterpretati o aggiornati in lettura.

Temporal drift conserva la propria sensibilità alle proiezioni di policy sui
flag recommended; questa misura è distinta dal confronto Session QC tra tre
esecuzioni. Repeated routes seleziona geometria tramite `use_for_route_mapping`
e coordinate valide, senza sostituire questa maschera con il keep termico.

## Identità, appartenenze e transazione

Il manifest seleziona le campagne canoniche: cartelle residue negli output non
aggiungono campagne. Gli ID Session QC sono quelli canonici del manifest;
gli ID route storici sono il nome file senza estensione. Per nomi uguali in
cartelle diverse, le route usano l'ID deterministico derivato dal percorso,
evitando sovrascritture. Il collegamento tra i due domini avviene per
`source_file`, non per uguaglianza dei nomi degli ID.

La chiave delle membership è
`(repeated_segment_id, segment_passage_id, source_file, source_row)`.
Un punto può appartenere a più segmenti e passaggi, anche in direzioni opposte;
i sotto-tratti condivisi non formano una partizione disgiunta.
`point_segment_match_support` conserva le prove di matching per membership.
Si verificano unicità semantica e referenziale, supporto completo e conteggi
senza duplicazione delle osservazioni raw. La cache conserva chiavi e regole
di invalidazione scientifiche preesistenti; il consolidamento resta globale.

Discovery riconosce anche duplicati interni al batch con un manifest temporaneo
in memoria. Apply registra le copie ridondanti senza ricalcolarle come campagne.
Il lock precede la scrittura del ledger; su Windows la verifica PID usa API
di lettura dello stato del processo. Lo staging di apply risiede nel volume
della workspace per consentire la promozione con rename e rollback. Il ledger
registra le fasi completate e il report contiene i conteggi delle analisi.
Check calcola point QC e Session QC in temporanea e scrive solo rapporti di
controllo sotto `logs/check_reports`; apply esegue ciascuna analisi globale una
volta per batch prima della promozione.

## Risorse e installazione

`config/` è la sorgente autorevole delle configurazioni scientifiche.
`src/meteotracker_qc/resources/` contiene copie identiche distribuite nella wheel;
un test confronta ogni byte. Una modifica futura deve aggiornare entrambi.
I caricamenti senza workspace esplicita usano `importlib.resources`; quelli con
workspace/config esplicita richiedono quei file e non ripiegano sul bundle.
Point QC richiede una policy valida accanto allo YAML. Session QC e temporal
drift usano la directory corrente se `root` non viene fornito; per elaborazioni
applicative si passa sempre una workspace esplicita.

Installazione portabile, da una copia contenente soltanto i file del perimetro:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -c constraints-scientific-win-py314.txt '.[test]'
& .\.venv\Scripts\python.exe -m pip check
& .\.venv\Scripts\python.exe -m pytest -vv -W error
& .\.venv\Scripts\meteotracker.exe --help
```

La combinazione verificata dal Gate è Windows / CPython 3.14.5. Il file
constraints registra le versioni esatte della prova; non è un lock universale
per tutti i sistemi. I vincoli nel pyproject escludono le combinazioni
pandas 2 / NumPy 2.5 e PyArrow 19 / Python 3.14 che bloccavano la baseline.
Il supporto dichiarato ad altre versioni Python non implica che siano state
eseguite in questa verifica. La wheel scientifica esclude esplicitamente la GUI.

## Verifiche portabili e casi storici

La suite predefinita genera acquisizioni, manifest e tutti gli output in
workspace temporanee, anche con spazi e Unicode. Gli schemi CSV 42/43/44/5
colonne hanno gli header osservati e valori interamente sintetici. Le prove
coprono il contratto keep, policy/schema, controlli puntuali, Session QC,
many-to-many, densità, deriva, cache, application layer, lock, promozione reale
e rollback dopo una promozione parziale. Un secondo calcolo confronta gli
output scientifici e osserva gli hit della cache; spy sui veri entry point
contano le esecuzioni senza sostituire gli algoritmi.

I tre moduli storici `test_regression_real_data.py`,
`test_session_regression_real_data.py`, `test_temporal_real_data.py` e il caso
`test_real_data_regression_stabilization_no_longer_scattered_mid_trip` richiedono
acquisizioni/output locali e sono esclusi dal checkpoint scientifico. Nessun
modulo runtime li importa. Restano preservati come lavoro locale separato;
non sono necessari all'installazione o alla validazione della pipeline.
La suite del checkpoint comprende tutti i 488 test portabili, senza skip.
Il perimetro del Gate 1.5 aveva 151 file; quello committabile ne ha 148 dopo
l'esclusione dei tre moduli. Il caso storico è escluso selettivamente dal file
di stabilizzazione, conservando tutte le sue prove sintetiche.
Il conftest supporta `--real-data` soltanto per studi locali opzionali;
le verifiche sugli output del checkpoint usano dati sintetici realmente elaborati.

Per verificare una wheel installata: usare una venv nuova, copiare solo test,
configurazioni e documentazione in una directory senza `src`, eseguire pytest
con `-o pythonpath=` e impostare `METEOTRACKER_EXPECT_PACKAGE_ROOT` al package
in `site-packages`. Il test degli import visita tutti i moduli scientifici e
verifica che la loro origine sia il package installato. Entrambi gli help
(`meteotracker` e `python -m meteotracker_qc`) devono funzionare da una directory
esterna al checkout.
