# Revisione senior many-to-many

`METEOTRACKER_MANY_TO_MANY_HIGH_REVIEW_STATUS: PASS_WITH_FIXES`

Data: 2026-09-09. Revisione dello stato già implementato; nessuna riscrittura del
consolidamento, ottimizzazione o modifica delle soglie scientifiche.

## Problemi reali e correzioni

1. **Doppio conteggio scientifico.** La tabella schema 2 ripeteva la chiave
   `(repeated_segment_id, segment_passage_id, source_file, source_row)` per
   ogni `supporting_match_id`. Le metriche riepilogative deduplicavano, ma una
   media diretta sul CSV avrebbe dato più peso alle osservazioni con più match.
   Ora la tabella scientifica ha una sola riga per chiave e la provenance è
   nella tabella separata `point_segment_match_support`.
2. **Dipendenza dall'ordine delle run duplicate.** `setdefault` sceglieva la
   prima evidenza con gli stessi intervalli: invertendo run duplicate con
   diagnostiche differenti cambiavano distanze e statistiche. Il rappresentante
   viene ora scelto con ordinamento deterministico, analogamente al
   consolidamento già esistente; la relazione semantica rimane una sola.
3. **Overlap non corrispondente agli intervalli emessi.** La frazione veniva
   calcolata prima del taglio reciproco. Un test produceva A=1.000 m e B=300 m
   con overlap dichiarato 1,0. Ora si ricalcola la frazione effettiva e si
   applica la stessa soglia configurata: 0,30 non supera 0,70. Nessuna soglia
   è stata cambiata. La versione dell'algoritmo pair-cache è stata incrementata.

I tre test di regressione sono stati eseguiti e sono falliti prima delle
correzioni; gli XML sono in `.tmp_many_to_many_high_review/red.xml`.

## Controllo sul doppio conteggio

Fixture con stesso punto `a.csv`, riga 100, stesso passaggio
`seg_0001__a::part1`, stesso segmento `seg_0001`:

- una sola membership scientifica;
- due relazioni di provenance, ai match `match_afb86aa51f6f3dd189e4` e
  `match_b6b7d53813e01b3fc364`;
- 201 osservazioni scientifiche e 400 righe di supporto nel passaggio;
- temperature sintetiche 10/30 °C: media scientifica **29,800995024875622 °C**;
  la media errata sulle righe di supporto sarebbe **29,9 °C**.

Il test effettua il join con le osservazioni originali con validazione
`one_to_one`, calcola la media e dimostra esplicitamente che espandere i match
altererebbe il risultato. Il many-to-many tra punti e segmenti differenti è
preservato nei test di overlap/contenimento e nelle 49 osservazioni reali.

## Schema finale 3

`point_segment_memberships.csv` e layer Point omonimo nel GeoPackage:

- `membership_id`: identificatore deterministico SHA-256 della chiave semantica;
- `repeated_segment_id`, `segment_passage_id`, `campaign_id`, `track_part_id`;
- `source_file`, `source_row`, `timestamp` originale UTC;
- `longitude`, `latitude`, `track_position_m`, `segment_position_m`;
- `distance_to_passage_m`, `passage_direction`, `membership_basis`;
- `geographic_crs`, `metric_crs`;
- `geometry` Point, solo nel GeoPackage.

Unicità scientifica: `(repeated_segment_id, segment_passage_id, source_file,
source_row)`. Anche `membership_id` è unico. Entrambi i vincoli sono imposti
con indici unici nel GeoPackage, oltre alla deduplicazione in costruzione.

`point_segment_match_support.csv` e tabella attributi non spaziale omonima nel
GeoPackage: `membership_id`, `supporting_match_id`, con chiave composta unica.
`membership_id` è FK alla membership; il match si risolve nel layer
`pairwise_matches` insieme al segmento della membership. La verifica reale
controlla anche appartenenza al track e intervallo di ciascun match di supporto.

Migrazione: `supporting_match_id` si sposta dalla tabella scientifica alla
provenance; non si conserva una colonna singola che nasconderebbe altri supporti.
I nomi degli output preesistenti sono conservati. Per le medie meteorologiche
usare la tabella scientifica unita ai punti QC, senza espandere prima le righe
con un join uno-a-molti sui supporti. Nessuna lista serializzata.

`build_point_segment_memberships` restituisce solo le membership uniche;
`build_point_segment_tables` restituisce membership e supporti insieme.
Schema 3 dichiarato nella provenance; nuove metriche per supporti, duplicati e
membership prive di supporto. Le cache persistono tracce/coppie, non le tabelle
finali: non possono ripristinare accidentalmente membership dello schema 2.
La cache delle coppie usa `pair-v3-emitted-overlap-deterministic`; un test
verifica che risultati `pair-v2-reusable-runs` non vengano riutilizzati.

## Controllo quantitativo sulle stesse quattro campagne

Verificata l'identità SHA-256 con le quattro copie della prova precedente.
Raw copiati nella nuova directory temporanea; QC temporaneo già prodotto
riutilizzato in sola lettura. CLI completa repeated_routes con cache nuova,
output e figure in `.tmp_many_to_many_high_review/e2e/result/`.
Nessuna rigenerazione delle campagne ufficiali.

| Metrica | Valore |
| --- | ---: |
| Repeated segment | 4 |
| Segment passages | 8 |
| Match semantici unici | 4 |
| Membership scientifiche uniche | 1.514 |
| Relazioni di provenance | 1.514 |
| Osservazioni in più segmenti | 49 |
| Duplicati sulla chiave semantica | 0 |
| Membership prive di provenance | 0 |
| Membership fuori dall'intervallo del passaggio | 0 |
| Distanza massima dalla geometria associata | 7,8772297735 m |

CSV e GeoPackage confrontati su **tutte le colonne**, non soltanto sul numero
riga. Distanze ricalcolate dalle geometrie persistite, accordo entro 1e-6 m.
Geometrie e coordinate originali in EPSG:4326; distanze/ascisse in EPSG:32632.
Verificati tutti i 1.514 riferimenti ai punti QC originali: file/riga, timestamp,
coordinate e `use_for_route_mapping`; nessun punto escluso è entrato.
Verificati gli intervalli dei match e le FK SQLite. Il GeoPackage contiene i
precedenti 7 layer più la nuova tabella attributi; prodotte 13 figure.

### Campioni controllati

- Membership singola: campagna 13 febbraio ore 09:06:57, riga 168,
  `seg_0001`, ascissa 712,319624 m, distanza 0,694227 m.
- Due segmenti: campagna 13 febbraio ore 13:23:47, riga 95,
  `seg_0001` e `seg_0004`, stessa ascissa 162,407130 m e stessa posizione
  originale, membership ID distinti e provenienza presente per entrambe.
- Verso opposto: `seg_0002`, campagna pomeridiana, riga 871. Il suo
  `direction_class=opposite_direction` è relativo al riferimento; il riferimento
  ha orientamento canonico opposto, quindi `passage_direction=same_direction`.
  Non è una contraddizione: le due direzioni usano riferimenti differenti,
  esplicitamente documentati. I due passaggi hanno direzioni normalizzate opposte.
- Contenimento: non presente nel campione reale di quattro campagne. Controllata
  la fixture: sul track A restano distinti `[0, 1000]` e `[390, 710]` m,
  con membership multiple nella parte comune.
- Più match di supporto: non presente nel campione reale (tutte le membership
  reali hanno un supporto). Controllata la fixture descritta sopra, con una
  membership e due supporti e dimostrazione della media senza doppio peso.

I record campionati e le misure sono salvati in `manual_samples.json` e
`real_quantitative.json` nella directory della revisione.

## Revisione statica e falsi allarmi

Esaminati il rapporto e il diff precedenti e tutti i moduli richiesti.
Non è stato trovato un difetto riproducibile ulteriore in `corridors.py`,
`segments.py`, `tracks.py`, `dataload.py` o `config.py`: nessuna modifica applicata
solo per migliorare lo stile. Restano passanti i controlli su consolidamento
multi-campagna, assenza di fusioni transitive, overlap, contenimento, opposta
direzione, riuso delle run e ritorno vicino a sé stessi.

Confermati con regressioni aggiuntive: identità file/riga dopo ordinamento e
deduplicazione, riferimenti del ricampionamento ai punti originali, inclusione
degli estremi, esclusione QC, rifiuto di un punto curvilineamente compatibile ma
lontano dalla geometria, determinismo delle due tabelle invertendo passaggi e
match, invalidazione della vecchia pair-cache.

Due possibili falsi allarmi chiariti: la stessa osservazione in segmenti diversi
è un'appartenenza legittima; l'assenza di duplicati nella prova reale a quattro
campagne non dimostrava che lo schema 2 fosse sicuro (la fixture multi-match ne
dimostra il problema). Lo skip condizionale non riguarda i test same/opposite
direction della correzione, che sono tutti passati.

## Test

| Esecuzione | Risultato |
| --- | --- |
| Test repeated_routes esistenti, prima delle modifiche | 31 passati |
| Nuove regressioni prima delle correzioni | 3 fallimenti attesi |
| Mirati revisione e membership | 17 passati |
| Tutti i repeated_routes finali | 37 passati |
| Suite completa, eseguita una sola volta al termine | 478 passati, 1 saltato, 0 fallimenti |
| CLI sulle quattro campagne | exit 0 |

Skip: `test_direction_dependent_campaign_identified_dynamically_if_any`;
nessuna campagna reale della fixture mostra il disaccordo same/opposite
necessario in questa esecuzione. Test preesistente con skip condizionale,
non disabilitato dalla revisione.

## File modificati e protezione dello stato

Moduli in `src/meteotracker_qc/repeated_routes/`:

| File | Motivo |
| --- | --- |
| memberships.py | Separazione tra membership scientifiche e supporti; ID e metriche |
| pipeline.py | Costruzione/scrittura delle due tabelle |
| geopackage.py | Tabella attributi supporti, unicità e FK |
| provenance.py | Schema 3 e descrizione del modello |
| __main__.py | Metriche delle due tabelle nella provenance CLI |
| matching.py | Diagnostiche deterministiche e overlap sugli intervalli emessi |
| cache.py | Invalidation dei risultati pairwise dell'algoritmo precedente |
| tests/test_repeated_routes_high_review.py | Sei test aggiuntivi della revisione |
| tests/test_repeated_routes_memberships.py | Contratto schema 3 e confronto completo CSV/GeoPackage |
| reports/repeated_routes_many_to_many.md | Schema corrente aggiornato, rapporto schema 2 mantenuto come storico |
| reports/repeated_routes_many_to_many_high_review.md | Questo rapporto |

SHA-256: **4.055 file** di `data/raw`, `data/manifests` e `outputs` invariati,
nessuna aggiunta o rimozione in queste directory. Il manifest già dirty prima
della revisione resta identico allo snapshot. Nessun `--apply`, commit o push.
Snapshot dei sorgenti, test, report e altro stato del workspace in
`.tmp_many_to_many_high_review/before.json`; diff isolato in `review.diff`.
Il diff precedente `.tmp_many_to_many/implementation.diff` è preservato.

## Gate successivo

Non rimangono blocchi dimostrati nella correzione many-to-many: la rigenerazione
ufficiale può essere autorizzata come attività successiva. Questa verifica sulle
quattro campagne non certifica l'allineamento QC dell'intero dataset 44/45:
nel passo autorizzato occorrerà verificare/rinfrescare gli input QC completi,
come già previsto dal gate precedente. Nessuna autorizzazione alla rigenerazione
è stata presunta e nessun output ufficiale è stato rigenerato.
