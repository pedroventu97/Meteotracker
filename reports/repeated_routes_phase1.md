# Repeated Routes — Fase 1: inventario e identificazione automatica dei tratti ripetuti

Data: 2026-07-30
Branch: `main`, commit di partenza `cec4ca2` ("chore: initialize cleaned Meteotracker QC workspace")
Ambito: solo geometria, tempi di acquisizione e qualità dei dati Meteotracker. Nessuna integrazione Netatmo/satellite/ERA5, nessuna classificazione meteorologica delle giornate, nessuna interpretazione termica.

> **Nota su concorrenza.** Durante questa sessione un secondo processo (un'altra sessione Claude Code, evidente da `config/qc_permissive.yaml`, `config/qc_recommended.yaml`, `config/qc_restrictive.yaml`, `src/meteotracker_qc/time_qc.py`, `tests/test_time_qc.py` modificati e da `src/meteotracker_qc/schema.py`, `config/flag_policy.csv`, `config/threshold_provenance.csv`, `tests/test_regression_real_data.py`, `tests/test_schema.py` non tracciati, tutti con mtime tra le 17:51 e le 18:15) ha lavorato in parallelo sulla stessa pipeline QC, verosimilmente implementando le raccomandazioni di `reports/targeted_qc_audit.md`. **Non è farina di questo sacco**: nessuno di questi file è stato toccato, letto in scrittura o commesso da questo lavoro. È stato verificato che `gps_qc.py`, `stabilization.py`, `meteo_qc.py`, `pipeline.py`, `inventory.py`, `derived_variables.py` — i moduli QC da cui dipende `repeated_routes` — sono rimasti alla versione committata per tutta la sessione. L'inventario QC "recommended" usato qui (`outputs/recommended/`, timestamp 17:41-17:42) è stato generato **prima** che l'altra sessione iniziasse a modificare `config/qc_recommended.yaml` (17:51) ed è quindi internamente coerente con il commit di partenza. Rilanciare `python -m meteotracker_qc.repeated_routes` dopo che l'altro lavoro sarà commesso rigenererà automaticamente tutto contro la nuova pipeline QC — è il comportamento previsto, non un limite.

---

## Dataset analizzato

| Voce | Valore |
|---|---|
| File CSV raw trovati | 39 (`data/raw/**/*.csv`) |
| Campagne canoniche (manifest, `exclude_from_analysis=False`) | 34 |
| Campagne ridondanti escluse (re-export) | 5 |
| Intervallo temporale | 2025-07-04 → 2026-06-20 |
| Punti raw totali (somma righe CSV) | 48 173 |
| Punti "validi per geometria" (vedi sotto) | 46 232 |
| CRS metrico usato | EPSG:32632 (UTM 32N) |
| CRS interoperabile output | EPSG:4326 (WGS84) |
| Profilo QC usato | `recommended` (`config/qc_recommended.yaml`, rigenerato all'inizio della pipeline via `run_qc()`, invariato) |

**Corrispondenza dei flag QC usata per la geometria** (documentata come richiesto, non assunta):
un punto è "valido per geometria" se `use_for_route_mapping` (= `gps_valid` = `~(qc_gps_freeze | qc_gps_jump)`, la colonna che la pipeline esistente designa esplicitamente per il route mapping) **e** non `qc_coord_missing`. La seconda condizione è necessaria perché nel codice attuale `qc_coord_missing` non esclude nulla da `gps_valid` (gap noto, documentato in `reports/targeted_qc_audit.md` §C.8) — la correzione è applicata solo qui, a livello di `repeated_routes`, senza toccare `gps_qc.py`.

A questo si aggiunge, solo nel livello geometrico (non nella QC standard), un filtro per **spike GPS isolati**: punti la cui distanza dal punto precedente valido implica una velocità > `part_split_max_speed_kmh` (150 km/h) entro `part_split_jump_dt_s` (5s) *e* che si ricongiungono in modo plausibile al punto successivo se rimossi, vengono scartati come outlier puntuali invece di spezzare la traccia in due parti — vedi "Limiti" più sotto per il perché era necessario.

---

## Risultati principali

| Voce | Valore |
|---|---|
| Campagne usabili per il matching (quality ≠ `excluded`) | 33 / 34 |
| Campagna esclusa | `20260427T07_28_18_..._Bologna-Bologna` — 21 righe, 29 secondi, 18 punti validi (sotto `min_campaign_valid_points_excluded=20`) |
| Campaign parts costruiti (dopo split su gap/salti) | 74 |
| Coppie totali possibili (part × part) | 2 701 |
| Coppie escluse dal prefiltro spaziale | 2 189 (81%) |
| **Coppie candidate** (bounding box/buffer sovrapposti) | **512** |
| Coppie candidate con ≥1 match geometrico accettato | 236 |
| Match pairwise accettati (run riconciliati A↔B) | 301 |
| Match confluiti in un repeated_segment (≥2 track) | 276 |
| Match rimasti isolati (nessun secondo track compatibile) | 25 |
| **Repeated segment finali** | **27** |
| Lunghezza totale condivisa | **84.0 km** (su 511.8 km di distanza valida totale percorsa, ~16%) |
| Segmenti con ≥2 date distinte | 9 / 27 |
| Segmenti con ≥3 date distinte | 1 / 27 (`seg_0003`, 6 date) |
| Segmenti con ≥5 date distinte | 1 / 27 (lo stesso `seg_0003`) |
| Segmenti osservati in più di una fascia oraria | 17 / 27 |
| Segmenti osservati in entrambi i versi | 2 / 27 (`seg_0003`: 7 stesso verso / 16 verso opposto; `seg_0010`: 2/1) |
| Classe di opportunità | 1 `excellent`, 12 `good`, 14 `limited`, 0 `poor` |

### Campagne escluse o problematiche

- **1 esclusa** dal matching (sopra), ma resta nell'inventario con `campaign_quality_flag=excluded`.
- **10 `low`**, **11 `medium`**, **12 `high`** sulle 34 totali. Le `low` restano candidate al matching (non vengono rimosse, come richiesto), ma sono anche riportate nel layer GeoPackage `excluded_or_low_quality_tracks` per trasparenza visiva.
- Le campagne con `n_campaign_parts` più alto (fino a 8) corrispondono direttamente ai gap Bluetooth più gravi già documentati nell'audit storico (es. `20260604T11_40_32_..._Bologna-Ravenna`, gap massimo 2469 s; `20260519T08_17_35_...`, gap massimo 1237 s) — la soglia di split (120 s, configurabile) intercetta correttamente queste interruzioni senza essere innescata dai gap normali di ricampionamento a 1-2 Hz.

---

## Sensitivity analysis

Non è stato eseguito il prodotto cartesiano completo (27 combinazioni): il costo computazionale sarebbe stato accettabile su questo dataset, ma un disegno **one-factor-at-a-time** attorno alla configurazione di base è più interpretabile (ogni riga isola l'effetto di una sola soglia), com'è esplicitamente permesso dalla richiesta ("non è necessario eseguire tutte le combinazioni... un set ragionato"). 7 configurazioni eseguite, salvate in `outputs/repeated_routes/sensitivity_summary.csv`.

| configuration_id | tolerance_m | min_length_m | min_overlap | n_candidate_pairs | n_matches | n_segments | segments ≥2 date | segments ≥3 date | lunghezza tot. km | mediana lunghezza m | mediana dist. matching m |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **recommended_baseline** | **20** | **250** | **0.70** | 512 | 301 | **27** | 9 | 1 | **84.03** | 600 | 3.98 |
| tolerance_10m | 10 | 250 | 0.70 | 512 | 304 | 23 | 10 | 4 | 48.90 | 564 | 1.86 |
| tolerance_30m | 30 | 250 | 0.70 | 519 | 320 | 24 | 7 | 1 | 92.61 | 705 | 4.67 |
| minlength_100m | 20 | 100 | 0.70 | 512 | 408 | 32 | 8 | 2 | 85.25 | 560 | 4.52 |
| minlength_500m | 20 | 500 | 0.70 | 512 | 211 | 19 | 7 | 3 | 95.71 | 2100 | 3.98 |
| minoverlap_0.60 | 20 | 250 | 0.60 | 512 | 309 | 27 | 9 | 1 | 84.03 | 600 | 3.98 |
| minoverlap_0.80 | 20 | 250 | 0.80 | 512 | 290 | 26 | 9 | 1 | 83.31 | 590 | 4.20 |

**Osservazioni concrete:**

- `minimum_overlap_fraction` è il parametro **meno sensibile** in questo dataset: 0.60→0.80 cambia il conteggio segmenti solo da 27 a 26 e la lunghezza totale dell'1%. Non è quasi mai il vincolo attivo — la maggior parte dei match o supera ampiamente 0.80 o non arriva nemmeno a 0.60.
- `matching_tolerance_m` è il parametro **più sensibile**: 10m dimezza la lunghezza totale condivisa (48.9 vs 84.0 km) perché frammenta il corridoio più lungo (`seg_0003`, verso Sasso Marconi) nei tratti dove il rumore GPS delle campagne di febbraio (device `B6CCF894…`, già segnalato nell'audit storico per multipath urbano) supera i 10m. Interessante: a tolleranza 10m i segmenti con ≥3 date **quadruplicano** (4 vs 1), perché lo stesso corridoio frammentato produce più segmenti distinti invece di uno solo dominante — un segnale che tolleranze più strette meritano un secondo sguardo in una fase successiva, anche se non sono state scelte come default qui.
- `minimum_shared_length_m` mostra un compromesso chiaro: 100m massimizza il numero di segmenti (32) ma con qualità geometrica leggermente peggiore (distanza mediana 4.52m) e meno segnale multi-data; 500m produce meno segmenti (19) ma più solidi (mediana 2100m, distanza mediana invariata, 3 segmenti con ≥3 date invece di 1).

**Configurazione `recommended` scelta**: `matching_tolerance_m=20`, `minimum_shared_length_m=250`, `minimum_overlap_fraction=0.70` — non i valori centrali per convenzione, ma perché: (a) 20m è coerente con l'ordine di grandezza dell'errore GPS osservato nell'audit storico (freeze/multipath fino al 20% delle righe in alcune campagne urbane) senza essere così largo da rischiare falsi positivi su strade parallele ravvicinate; (b) 250m è il punto in cui il numero di segmenti (27) resta gestibile per un'ispezione manuale mantenendo comunque 9 segmenti multi-data, senza scendere fino ai frammenti da 100m che aggiungono soprattutto rumore; (c) `minimum_overlap_fraction` essendo poco sensibile, 0.70 è mantenuto come valore intermedio prudente. Questa non è una scelta scientificamente definitiva — la fase successiva potrà rivalutarla, specialmente il caso `tolerance_10m` che merita approfondimento.

---

## Migliori opportunità (top 10 per comparison_potential_score)

| ID | Lunghezza | Passaggi | Date | Fasce orarie | Versi (stesso/opposto) | Qualità | Dist. media | Score |
|---|---|---|---|---|---|---|---|---|
| `seg_0003` | 19 620 m | 23 | 6 | mattina, mezzogiorno, pomeriggio, sera | 7 / 16 | high | 2.7 m | 97.7 (excellent) |
| `seg_0010` | 2 100 m | 3 | 2 | mattina, pomeriggio | 2 / 1 | high | 3.0 m | 65.9 (good) |
| `seg_0014` | 2 763 m | 3 | 2 | mattina, pomeriggio | 3 / 0 | high | 0.8 m | 62.2 (good) |
| `seg_0002` | 3 930 m | 3 | 1 | mattina, mezzogiorno, pomeriggio | 3 / 0 | high | 3.0 m | 59.6 (good) |
| `seg_0007` | 650 m | 4 | 2 | mezzogiorno, pomeriggio | 0 / 4 | high | 3.1 m | 58.7 (good) |
| `seg_0008` | 540 m | 3 | 2 | mezzogiorno, pomeriggio | 3 / 0 | high | 2.3 m | 56.5 (good) |
| `seg_0025` | 460 m | 2 | 2 | mattina, pomeriggio | 2 / 0 | high | 1.2 m | 55.0 (good) |
| `seg_0001` | 340 m | 2 | 2 | mattina, mezzogiorno | 0 / 2 | high | 1.8 m | 53.2 (good) |
| `seg_0009` | 270 m | 2 | 2 | pomeriggio, sera | 0 / 2 | high | 2.6 m | 51.8 (good) |
| `seg_0011` | 620 m | 2 | 1 | mattina, pomeriggio | 2 / 0 | high | 1.1 m | 51.6 (good) |

`seg_0003` domina nettamente il punteggio: è il corridoio Bologna → Sasso Marconi, percorso da 14 campagne diverse in 23 passaggi (alcuni per l'intera lunghezza, altri solo per un tratto iniziale/finale condiviso con un percorso urbano diverso — esattamente il caso "sotto-tratto comune" della sezione 7), su 6 date diverse e in entrambi i versi.

---

## Validazione

### Controlli manuali (§20)

11 repeated segment ispezionati visivamente (`outputs/repeated_routes/figures/manual_qa/` + i 5 esempi cartografici automatici), scelti per coprire tutti i casi richiesti:

| Segmento | Lunghezza | Verso | Zona | Note |
|---|---|---|---|---|
| `seg_0003` | 19 620 m | entrambi | periferica (Sasso Marconi) | corridoio principale, 23 passaggi, geometria coerente lungo tutta la lunghezza |
| `seg_0020` | 19 690 m | opposto | periferica (Carpi) | andata/ritorno stesso giorno, distanza media 7.6m |
| `seg_0017` | 14 200 m | opposto | periferica (Carpi) | sotto-tratto del precedente, coerente |
| `seg_0026` | 4 690 m | opposto | periferica (Ravenna/Imola) | tratto finale di due tappe consecutive dello stesso giro |
| `seg_0002` | 3 930 m | stesso | centro urbano | 3 passaggi sovrapposti strettamente, forma a "U" seguita correttamente |
| `seg_0010` | 2 100 m | entrambi | centro urbano | percorso con tornante, tutti e 3 i passaggi seguono la stessa forma |
| `seg_0014` | 2 763 m | stesso | suburbana | distanza media 0.8m, il migliore per qualità geometrica |
| `seg_0018` | 340 m | opposto | periferica (SP verso Carpi) | **vedi Limiti — scostamento laterale sistematico ~9-19m, coerente con corsie separate** |
| `seg_0022` | 310 m | opposto | periferica (SP verso Carpi) | come sopra, scostamento minore (~9m) |
| `seg_0024` | 270 m | opposto | periferica (SP verso Carpi) | buona sovrapposizione, piccola divergenza solo agli estremi (rumore GPS normale) |
| `seg_0009` | 270 m | opposto | centro urbano | buona sovrapposizione, piccola divergenza agli estremi |

Nessun segmento è risultato dalla fusione di corridoi palesemente diversi al termine delle correzioni descritte sotto; nessuna interpolazione spuria attraverso gap è stata osservata; date e orari sono coerenti con i timestamp originali (verificati a campione contro `Time` nei CSV raw).

**Due bug reali sono stati trovati e corretti proprio grazie a questo controllo manuale**, non dai test sintetici (che infatti non li avevano intercettati perché testavano geometrie pulite):

1. **Frammentazione eccessiva delle campagne.** La prima versione produceva fino a 20 `campaign_part_id` per una singola campagna pulita. Causa: singoli punti con salto GPS implausibile (es. 43-46m in 1s, ~160 km/h in un giro urbano) che superano la soglia QC esistente di `qc_gps_jump` (80m/2s, tarata per salti più grandi) ma non quella di plausibilità di velocità — mai collegata a nessun flag nella QC attuale (gap noto, audit §C.3). Uno spike isolato spaccava la traccia in due parti anche quando il punto successivo tornava perfettamente in linea. **Fix**: nuova funzione `remove_isolated_gps_outliers` in `tracks.py` che rimuove il singolo punto anomalo se il punto successivo si ricongiunge in modo plausibile, e spacca in una nuova parte solo se l'anomalia persiste. Risultato: da 193 a 74 parti totali su 33 campagne, mediana 1 parte per campagna.
2. **Fusione transitiva di corridoi non correlati.** Il consolidamento union-find univa due "run" sulla stessa traccia se i loro intervalli si sovrapponevano anche solo marginalmente, permettendo catene transitive attraverso una strada arteriale lunga condivisa da molte campagne diverse per tratti *differenti* — esattamente il rischio descritto in §10 ("non fondere segmenti... geometricamente vicini ma non lo stesso corridoio"). Un singolo segmento arrivava a includere passaggi con distanza media dalla geometria di riferimento fino a 1600m (ben oltre la tolleranza di 20m). **Fix a due livelli**: (a) l'unione di run sulla stessa traccia richiede ora una sovrapposizione ≥70% dell'intervallo più corto (`consolidation_same_track_overlap_fraction`); (b) ogni passaggio non-riferimento viene ri-verificato direttamente contro la geometria di riferimento finale del componente (non solo transitivamente), tenendo solo il sotto-tratto contiguo effettivamente entro tolleranza. Risultato: distanza massima osservata tra un passaggio e il proprio riferimento scesa da 1600m a 18.5m (sotto la tolleranza di 20m su tutti gli 81 passaggi finali).

### Test aggiunti

14 test sintetici nuovi in `tests/test_repeated_routes.py`, tutti i 14 casi richiesti dalla sezione 17:

1. tracce quasi identiche, stesso verso — `test_two_nearly_identical_tracks_same_direction`
2. tracce quasi identiche, verso opposto — `test_two_nearly_identical_tracks_opposite_direction`
3. traccia interamente contenuta in una più lunga — `test_track_entirely_contained_in_longer_track`
4. solo un sotto-tratto comune (entrambe le tracce si estendono oltre) — `test_only_a_common_sub_stretch`
5. strade parallele non fuse (60m di distanza, tolleranza 20m) — `test_parallel_streets_not_merged`
6. solo un incrocio condiviso — `test_tracks_sharing_only_a_crossing`
7. GPS freeze escluso dalla geometria — `test_gps_freeze_points_excluded_from_geometry`
8. grande gap temporale → split in due parti — `test_large_temporal_gap_splits_into_two_parts`
9. due parti separate non collegate da interpolazione lineare — `test_separate_parts_not_linearly_interpolated_across_gap`
10. segmento sotto la lunghezza minima scartato — `test_segment_below_minimum_length_rejected`
11. distanza appena sopra/sotto la tolleranza — `test_distance_boundary_around_tolerance`
12. consolidamento di 4 campagne in un solo repeated segment — `test_four_campaigns_consolidate_into_one_segment`
13. gestione Europe/Rome incluso passaggio CET/CEST — `test_europe_rome_local_time_handling`
14. determinismo su run ripetuti — `test_deterministic_repeated_pipeline_runs`

### Test totali passati

**43/43** (29 pre-esistenti + 14 nuovi), `python -m pytest -vv -W error`, 0 warning, 0 failure. La suite completa nel repository al momento della stesura di questo report ne mostra 60 perché include anche i test della sessione concorrente descritta in apertura (`test_time_qc.py` esteso, `test_regression_real_data.py`, `test_schema.py`) — non fanno parte di questo lavoro e non sono stati scritti né validati qui.

### Warning

Nessuno, con `-W error` attivo.

---

## Output prodotti

```text
outputs/repeated_routes/
  campaign_inventory.csv              — 34 righe, una per campagna canonica
  candidate_pairs.csv                 — 512 righe, coppie candidate a livello di campaign_part
  comparison_opportunities.csv        — 27 righe, una per repeated segment
  sensitivity_summary.csv             — 7 configurazioni
  provenance.json                     — datetime, git commit, checksum input, config, versioni software
  pipeline.log                        — log completo dell'ultima esecuzione
  repeated_routes.gpkg                — GeoPackage, 6 layer:
    campaign_tracks                   — 23 campagne (quality high/medium)
    campaign_parts                    — 75 parti continue (tutte le 34 campagne, incl. quella excluded)
    excluded_or_low_quality_tracks    — 11 campagne (10 low + 1 excluded)
    repeated_segments                 — 27 righe + geometria di riferimento
    segment_passages                  — 81 righe + geometria per passaggio
    pairwise_matches                  — 301 righe + geometria del tratto condiviso lato A
  figures/
    01_all_campaigns.png
    02_valid_vs_excluded.png
    03_segments_by_n_dates.png
    04_segments_by_quality.png
    05_segment_length_hist.png
    06_matching_distance_hist.png
    07_passages_per_segment_hist.png
    08_campaign_matrix.png
    09_segments_per_time_bin.png
    10_example_{1..5}_seg_*.png       — 5 migliori per score
    manual_qa/*.png                   — 10 figure aggiuntive per il controllo manuale (sezione Validazione)

config/repeated_routes_recommended.yaml   — configurazione recommended salvata
src/meteotracker_qc/repeated_routes/       — codice della pipeline (vedi sotto)
tests/test_repeated_routes.py              — 14 test sintetici
```

---

## Limiti

- **Incertezza GPS**: il metodo non stima esplicitamente l'accuratezza GPS per campagna; la tolleranza di matching (20m) è una soglia unica globale, non calibrata per-device o per-condizioni (urbano/multipath vs extraurbano). L'audit storico ha già documentato differenze di qualità significative tra device.
- **Differenze di corsia/carreggiata — osservate concretamente**: `seg_0018` e `seg_0022` (tratto sulla provinciale verso Carpi, verso opposto, stesso giorno) mostrano uno scostamento laterale sistematico e costante per tutta la lunghezza del tratto (~9-19m, fino al 97° percentile appena sotto la tolleranza di 20m) — compatibile con due carreggiate separate della stessa strada piuttosto che con rumore GPS casuale. Il metodo li considera correttamente "lo stesso corridoio" (fisicamente lo sono, ai fini del confronto spazio-temporale), ma un'analisi futura che usi questi tratti per confronti fini di posizione dovrebbe esserne consapevole.
- **Nessun map matching sulla rete stradale**: il metodo è puramente geometrico (distanza punto-linea in proiezione metrica). Non usa OpenStreetMap né altra rete stradale come verità di base, come richiesto, ma questo significa anche che non distingue "stessa strada" da "traiettorie GPS che casualmente passano vicine" oltre a quanto imposto dalla tolleranza e dalla lunghezza minima.
- **Strade parallele ravvicinate**: rischio residuo per strade a meno di ~20-30m di distanza reciproca (tipico di alcune strade urbane a doppio senso con spartitraffico largo, o di strade e piste ciclabili adiacenti). Nessun caso di questo tipo è stato osservato nei 27 segmenti finali durante il controllo manuale, ma il dataset attuale (34 campagne, area Bologna) non lo esclude in generale.
- **Tratti brevi**: 14 dei 27 segmenti sono sotto i 250m più la soglia minima stessa (i 250m sono il minimo assoluto configurato) — utili come conferma di ripetizione ma geometricamente meno ricchi per un confronto fine.
- **Traffico e corsia**: nessuna informazione su corsia, senso di marcia multiplo, o condizioni di traffico è disponibile nei CSV Meteotracker; due passaggi sullo stesso `repeated_segment` possono aver vissuto condizioni di guida molto diverse.
- **Limiti del ricampionamento**: il passo di 10m è un compromesso; tratti con curve molto strette (es. tornanti, rotonde) possono essere rappresentati in modo grossolano, e l'interpolazione lineare tra punti radi (dopo l'esclusione di punti QC-invalidi) può tagliare leggermente gli angoli.
- **Campagne con gap o GPS freeze**: gestite esplicitamente (vedi `campaign_part_id`), ma una campagna con molte interruzioni brevi produce molte parti corte che raramente raggiungono la lunghezza minima per il matching — queste campagne restano sotto-rappresentate nei repeated segment anche se il tragitto reale era comparabile ad altre.
- **Rischio di sovrapposizioni geometriche non semanticamente equivalenti**: mitigato ma non eliminato dai due fix descritti in Validazione. Il metodo non ha alcuna nozione semantica di "strada" — solo prossimità geometrica verificata reciprocamente. Con più dati (più campagne, più device) il rischio di catene transitive spurie cresce; la soglia di sovrapposizione dello stesso track (70%) e la ri-verifica finale contro il riferimento sono le difese principali, ma sono soglie euristiche, non garanzie formali.
- **`campaign_part_id` non denso**: gli ID di parte sono assegnati in modo sequenziale durante lo split e non rinumerati dopo lo scarto di frammenti troppo corti (`min_part_points`); è normale osservare, per una campagna, ID come 1 e 9 senza 2-8 nel mezzo.

Le temperature, l'umidità e ogni altra variabile meteorologica non sono state interpretate in nessun punto di questa fase.

---

## Prossima fase

Pronti per l'integrazione successiva:

- **Inventario dei tratti ripetuti** (`repeated_segments` + `segment_passages`) con identificatori stabili (`repeated_segment_id`, `passage_id`) pensati per essere joinati con dati esterni per `campaign_id` + intervallo temporale (`passage_start_datetime`/`passage_end_datetime`, già in UTC+Europe/Rome).
- **Campi temporali** (`date`, `time_bin`, `local_hour_decimal` sottostante) pronti per essere incrociati con classificazioni meteorologiche/sinottiche esterne (Netatmo, ERA5, pioggia, ondate di calore) nella fase successiva, senza bisogno di ricalcolare la geometria.
- **`comparison_potential_score`** è calcolato oggi solo su diversità di data/ora/direzione/qualità geometrica — nella fase successiva potrà incorporare la diversità meteorologica reale (giorni caldi vs miti vs freddi, come nel lavoro di downscaling collegato) senza modificare la geometria sottostante.
- **Normalizzazione rispetto al fondo urbano**: i `repeated_segment` più lunghi e con più passaggi (in primis `seg_0003`) sono i candidati naturali per un primo confronto Meteotracker-vs-Meteotracker prima ancora di introdurre MODIS o Netatmo, perché offrono già oggi più date, più fasce orarie ed entrambi i versi di marcia sullo stesso tracciato fisico.
- Non ancora pronti: alba/tramonto/posizione solare (rimandati esplicitamente), qualsiasi forma di map-matching su rete stradale reale (nessuna infrastruttura del genere esiste ancora nel repository).
