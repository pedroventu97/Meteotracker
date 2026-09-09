# Repeated routes: modello many-to-many (schema 3)

La correzione conserva evidenze pairwise, corridoi geometrici, intervalli di
passaggio e osservazioni originali come elementi distinti. Non modifica le
soglie scientifiche del matching geometrico.

Revisione senior: [rapporto e controlli quantitativi](repeated_routes_many_to_many_high_review.md).
Lo schema 3 separa membership scientifiche uniche e supporti pairwise.

## Comportamento

Prima, `used_b` consumava una run reciproca; la union al 70% produceva componenti
transitive e `match_to_segment` conservava una sola destinazione. I punti originali
erano soltanto contati, senza una relazione interrogabile con i segmenti.

Ora ogni coppia di run reciprocamente valida può produrre un match. L'intervallo
su B è l'intersezione della run reciproca con l'estensione proiettata da A; non è
consumato e può ricomparire in altri match. Le evidenze con gli stessi track e
intervalli sono deduplicate prima del consolidamento e ricevono un
`supporting_match_id` deterministico. Anche lo scambio A/B viene normalizzato.
La scelta del rappresentante di evidenze duplicate ? indipendente dall?ordine
delle run. La soglia di overlap esistente ? verificata anche sugli intervalli
effettivi dopo il taglio della run reciproca.

Il consolidamento costruisce insiemi massimali di evidenze **tutte reciprocamente
compatibili**, non semplici componenti di overlap. La compatibilità verifica:

- estremi del passaggio comune entro la risoluzione di ricampionamento;
- estremi geometrici, in entrambi i versi, entro `matching_tolerance_m`;
- differenza di lunghezza entro due volte tale tolleranza (i due estremi);
- distanza di Hausdorff entro la tolleranza;
- coerenza dell'ordine delle posizioni proiettate con la soglia di correlazione
  direzionale già configurata, per distinguere ritorni e backtracking;
- connessione delle evidenze tramite track/passaggi comuni.

Le tolleranze esistenti descrivono la precisione geometrica: non trasformano un
contenimento lungo/corto in identità. Una catena A~B~C non fonde A con C se gli
estremi non sono compatibili. Un match può appartenere a più insiemi massimali.
Le componenti senza passaggi comuni rimangono distinte, anche se vicine.
`consolidation_same_track_overlap_fraction` rimane leggibile nei vecchi YAML,
ma è deprecato e non viene più utilizzato.

Ogni segmento conserva la geometria di riferimento e un `corridor_id`, impronta
della geometria metrica orientata canonicamente; il campo identifica quella
rappresentazione geometrica, non una strada cartografica. Gli ID sono
deterministici a input invariato, non garantiti invarianti aggiungendo campagne.
I passaggi conservano `track_start_m`, `track_end_m`, riferimento curvilineo,
`track_part_id` e `segment_passage_id` (alias compatibili dei precedenti track e
passage ID). Il supporto rimane esplicito nel layer `pairwise_matches` e nel CSV
`pairwise_match_segments.csv`.

## Assegnazione dei punti

Si usano `PartTrack.points`: osservazioni QC originali valide che hanno generato
la traccia, con il loro `source_row`, non i campioni interpolati. Restano valide
le esclusioni della pulizia preesistente (QC non valido, timestamp/coordinate
duplicati, spike isolati). Il `source_file` proviene dal manifest della campagna,
viene conservato nella preparazione della traccia e non è inventato in fase di
assegnazione; se manca, la costruzione delle membership segnala un errore.

Per ogni passaggio si selezionano i punti della parte e dell'intervallo
curvilineo corretti e si verifica la distanza dalla geometria del passaggio.
Ogni riga di provenienza richiede inoltre che il punto sia nell'intervallo del
match che la sostiene. La stessa osservazione può essere selezionata di nuovo
per un altro segmento. Un ritorno vicino alla stessa posizione, ma più avanti
sulla traccia, non soddisfa il vincolo curvilineo del primo passaggio.

## Schema `point_segment_memberships`

CSV `point_segment_memberships.csv` e layer Point omonimo nel GeoPackage.
Una riga rappresenta una membership scientifica unica, indipendentemente dal
numero di match che la sostengono. Le evidenze sono nella tabella separata
`point_segment_match_support`, senza liste serializzate.

| Colonna | Tipo / significato |
| --- | --- |
| membership_id | stringa, ID SHA-256 deterministico della chiave semantica |
| repeated_segment_id | stringa, segmento |
| segment_passage_id | stringa, passaggio nel segmento |
| campaign_id | stringa, campagna |
| track_part_id | stringa, ID globale `campaign::partN` |
| source_file | stringa, percorso relativo del CSV originale |
| source_row | intero, identificativo originale senza rinumerazione |
| timestamp | stringa ISO 8601 con fuso, timestamp originale UTC |
| longitude, latitude | float, coordinate originali |
| track_position_m | float, ascissa metrica nella parte |
| segment_position_m | float, proiezione sul riferimento orientato canonicamente |
| distance_to_passage_m | float, distanza dalla geometria metrica del passaggio |
| passage_direction | same_direction / opposite_direction / direction_uncertain rispetto all'orientamento canonico |
| membership_basis | `original_qc_point_track_interval_and_passage_distance` |
| geographic_crs | stringa EPSG; 4326 nella configurazione recommended |
| metric_crs | stringa EPSG; 32632 nella configurazione recommended |
| geometry | Point alle coordinate originali, solo nel GeoPackage |

Chiave unica della membership: `(repeated_segment_id, segment_passage_id,
source_file, source_row)`. Anche `membership_id` è unico. La tabella di supporto
contiene coppie uniche `(membership_id, supporting_match_id)`. Non esiste un
vincolo di unicità sul solo punto originale: può appartenere a segmenti diversi.

`membership_summary.json` distingue righe di evidenza, membership uniche, punti
originali e punti appartenenti a più segmenti. La provenance CLI contiene schema,
modello, CRS, configurazione, checksum e le medesime metriche.

Esempio di interrogazione SQLite del GeoPackage:

```sql
SELECT campaign_id, source_file, source_row,
       COUNT(DISTINCT repeated_segment_id) AS n_segments
FROM point_segment_memberships
GROUP BY campaign_id, source_file, source_row
HAVING COUNT(DISTINCT repeated_segment_id) > 1;
```

## Compatibilità e limiti

Tutti i precedenti nomi di file/layer sono conservati. Migrazione schema 2?3:
`supporting_match_id` si sposta dalla tabella scientifica a
`point_segment_match_support`; `membership_id` collega le due tabelle.
Le vecchie CSV dello schema 2 non sono sicure per medie dirette senza deduplicare.
`build_point_segment_memberships` restituisce solo la tabella scientifica unica;
`build_point_segment_tables` restituisce la coppia membership/supporti.
Il ritorno di `consolidate_segments` rimane una terna. Nel layer
`pairwise_matches`, un `supporting_match_id` può ora comparire per segmenti
differenti: usare DISTINCT sull'ID per contare match; la tabella scientifica
contiene gi? una sola riga per membership. L'istogramma dei match applica
questa distinzione.

`direction_class` dei passaggi esprime il verso rispetto al riferimento,
`normalized_direction` e `passage_direction` il verso rispetto all'orientamento
canonico; una proiezione ambigua resta `direction_uncertain`. Le direzioni
pairwise originali sono conservate nel layer dei match.

Le versioni degli algoritmi di cache delle tracce e delle coppie sono aggiornate:
i vecchi risultati non vengono riutilizzati. Il nuovo consolidamento può cambiare
numero, ID e lunghezza dei segmenti. Gli insiemi massimali hanno complessità
potenzialmente elevata per grafi di compatibilità molto densi; nessun limite
arbitrario elimina evidenze per contenere il tempo di calcolo.

La rigenerazione globale ufficiale resta un passo successivo da autorizzare.
Dopo avere risolto separatamente l'allineamento degli input QC, il comando
seguente rigenererebbe segmenti, passaggi, membership, cache, provenance e report:

```powershell
$env:PYTHONPATH = 'src'
.venv\Scripts\python.exe -m meteotracker_qc.repeated_routes --config recommended --skip-qc-refresh --full-rebuild --output-dir outputs/repeated_routes
```

Non è stato eseguito sugli output ufficiali; non è stato eseguito alcun `--apply`.

## Rapporto di validazione — 2026-09-09

`METEOTRACKER_MANY_TO_MANY_FIX_STATUS: PASS_WITH_WARNINGS`

Il warning riguarda un test preesistente saltato condizionalmente sui dati reali:
`test_direction_dependent_campaign_identified_dynamically_if_any`, perché nessuna
campagna presenta il disaccordo direzionale necessario in questa esecuzione.
I test espliciti same/opposite-direction della correzione sono passati.

| Verifica | Risultato |
| --- | --- |
| Prima implementazione, regressioni iniziali | 6 fallimenti attesi: membership assenti, riuso run perso, duplicati influenzano risultati |
| Regressioni finali many-to-many | 11 passati |
| Tutti i test repeated_routes, incluse regressioni/cache | 31 passati |
| Ingestione, pipeline integrity e Session QC | 100 passati |
| Suite completa | 472 passati, 1 skip condizionale, 0 fallimenti |
| CLI end-to-end con refresh QC e figure, 4 campagne reali copiate | exit 0; 4 segmenti; 1.514 righe di membership; 49 punti in più segmenti; 7 layer; 13 figure |
| Protezione SHA-256 | 4.055 file raw/manifest/output invariati, nessun file aggiunto o rimosso in tali directory |

I test usano `-p no:cacheprovider` e `--basetemp .tmp_many_to_many/...`:
il default temporaneo di Windows non era accessibile; il cambio della directory
ha risolto gli errori di setup senza modificare i test esistenti.

Prova concreta nella fixture di contenimento:

| campaign_id | source_file | source_row | repeated_segment_id | supporting_match_id |
| --- | --- | --- | --- | --- |
| a | a.csv | 100 | seg_0001 | match_afb86aa51f6f3dd189e4 |
| a | a.csv | 100 | seg_0002 | match_46d560d599f9e4053408 |

La fixture produce 130 osservazioni originali appartenenti a più segmenti.
La prova geometrica di riuso, senza mock di `find_runs`, rileva **2 run di A e
1 run di B**: entrambi i match persistono, con intervalli A disgiunti e lo stesso
intervallo B. Un'altra regressione verifica una stessa evidenza pairwise collegata
a due segmenti distinti senza fusioni transitive.

### File della correzione

Tutti i moduli elencati qui sono in `src/meteotracker_qc/repeated_routes/`.

| File | Modifica e motivazione |
| --- | --- |
| matching.py | Riuso di tutte le run reciproche valide, intersezione dell'intervallo B, deduplicazione |
| corridors.py (nuovo) | Evidenze canoniche, ID stabili, compatibilità completa, gruppi non transitivi |
| segments.py | Gruppi di corridoio, relazione match?segmenti plurale, intervalli e direzioni dei passaggi, corridor_id |
| memberships.py (nuovo) | Assegnazione di punti originali, provenienza normalizzata e metriche senza doppi conteggi |
| tracks.py | Conservazione di source_file nei punti originali |
| dataload.py | Provenienza source_file esplicita dal manifest |
| pipeline.py | Costruzione membership e scrittura CSV, relazione match/segmento e riepilogo |
| geopackage.py | Layer Point aggiuntivo, CRS esplicito, scrittura corretta anche senza risultati |
| provenance.py | Versione dello schema e descrizione del modello |
| __main__.py | Metriche delle membership nella provenance CLI |
| cache.py | Invalidation delle cache precedenti delle tracce e dei match |
| config.py | Campo legacy overlap conservato ma documentato come inattivo; nessuna soglia cambiata |
| viz.py | Istogramma dei match deduplicato per supporting_match_id |
| tests/test_repeated_routes_memberships.py (nuovo, nella directory tests) | 11 regressioni e verifiche di round-trip/output |
| reports/repeated_routes_many_to_many.md (questo documento) | Schema, invarianti, compatibilità e rapporto di validazione |

Branch iniziale: `main`; HEAD iniziale:
`89ca196d641da7282ffa6614ead5b0bf4b3bed29`.
Il worktree era già dirty; non sono stati ripristinati file e non sono stati
creati commit o push. Nessun processo Python risultava attivo al controllo
iniziale; l'ispezione CIM dettagliata non era consentita da Windows.

Artefatti locali di verifica in `.tmp_many_to_many/`:
`before.json`, `status_before.txt`, `protection_check.json`, `routes.xml`,
`linked.xml`, `full.xml`, `multiple_membership_example.csv`, `changed_files.json`
e `implementation.diff`. Il diff è costruito rispetto alla copia dei moduli
all'inizio di questa attività, perché l'intero pacchetto repeated_routes era già
non tracciato: un semplice diff contro HEAD non isolerebbe la correzione.
La prova reale e i suoi output sono in `.tmp_many_to_many/e2e_real/`.
Il rebuild finale con QC temporaneo riutilizzato e figure ? in
`.tmp_many_to_many/e2e_real/result_review/` (exit 0, stesse metriche).
