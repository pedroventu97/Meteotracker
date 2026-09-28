# Fase 2.5 — Sanity check scientifico del repeated-segment product

Gate: **PASS_WITH_WARNINGS**

Interpretazione scientifica complessiva: **CONSISTENT_WITH_CAVEATS**

Generato: 2026-09-16/17 (audit read-only)  
Repository: `D:\projects\Meteotracker`  
Branch: `feat/meteotracker-windows-app`  
HEAD all’avvio dell’audit: `f404ae3587033835285be87b5a633dd821938e47`  
HEAD a fine audit: `5358a01c08101941bd9431e88701555218b63b56` (commit GUI session analysis, **non** creato da questa fase)  
Identità del prodotto ufficiale repeated-segment: resta `git_commit` = `f404ae3…` in `provenance.json`  
Questa fase non ha fatto commit, push, checkout, stash, reset, né modifiche ad algoritmo / QC / output ufficiali.

Questa fase verifica se il prodotto ufficiale repeated-segment è internamente coerente e scientificamente plausibile prima del consumo da `bologna_urban_climate_integration`. Non modifica il matching.

---

## Safety / stato git iniziale

Registrato **prima** dell’audit. Working tree già dirty; lasciato intatto.

- Branch: `feat/meteotracker-windows-app`
- HEAD all’avvio: `f404ae3 feat: add Windows desktop GUI` (`f404ae3587033835285be87b5a633dd821938e47`)
- `git diff --stat` iniziale: **23 file modificati**, `+383 / −63`
- File modified preesistenti: `.gitignore`, `README.md`, `data/manifests/campaign_manifest.csv`, `outputs/recommended/inventory.csv`, `reports/QC_Methodology.md`, `requirements.txt`, moduli QC / GUI / repeated_routes / session QC, due test
- Untracked preesistenti: catalogo, `outputs/repeated_routes/`, session QC, report Fase 2, audit, script, GUI, ecc.
- Comandi vietati (reset / clean / checkout / stash / commit / push): non usati

Durante l’audit è atterrato un commit indipendente `5358a01` (*feat: add session analysis GUI workflow*, 2026-09-17 09:30 +02). Non è stato eseguito da questa fase. Non tocca `outputs/repeated_routes/` né il catalogo. Il `git_commit` del prodotto ufficiale resta `f404ae3`.

L’unico file creato da questa fase è questo report.

---

## A. Run identity

Prodotto ispezionato: **`outputs/repeated_routes/`**  
Stato dichiarato: **OFFICIAL**  
Non usato: `outputs/audit/.../reference44/` (`audit_not_used: true` nel catalog provenance)

| Campo | Valore | Verdetto |
|---|---|---|
| `product_status` | OFFICIAL | CONSISTENT |
| `execution_datetime` | 2026-09-16T20:55:30.210305+00:00 | CONSISTENT |
| `git_commit` | `f404ae3587033835285be87b5a633dd821938e47` = HEAD | CONSISTENT |
| `repeated_routes_schema_version` | 3 | CONSISTENT |
| `matching_algorithm_version` | `repeated_routes_schema_version_3` | CONSISTENT |
| `matching_config_fingerprint` | `a757e66cd0b075e9074ff0492d9ab10eb941d3f0659a9ec60dd99189e1117c51` | CONSISTENT |
| `qc_config_fingerprint` | `0e06b2ee5397030ba4592eeaa1e86857cc5a32cfe127821946be60875641ebc4` | CONSISTENT |
| QC profile | `recommended` | CONSISTENT |
| Config matching | `config/repeated_routes_recommended.yaml` | CONSISTENT |
| Config QC | `config/qc_recommended.yaml` | CONSISTENT |
| CRS matching | metric EPSG:32632, geographic EPSG:4326 | CONSISTENT |
| `full_rebuild` | true (cache miss 44 track / 980 pair) | CONSISTENT |
| Input | manifest + **44** CSV raw | CONSISTENT |
| Catalogo | `outputs/campaign_catalog.csv` (44 righe, sha256 coincidente) | CONSISTENT |
| 8-1 / 9-8 | 6 file PENDING, non nel matching | CONSISTENT |

Soglie dichiarate nel run:

- `minimum_shared_length_m` = 250
- `minimum_overlap_fraction` = 0.7
- `matching_tolerance_m` = 20
- `resampling_distance_m` = 10
- `minimum_consecutive_matches` = 15
- `crs_metric_epsg` = 32632

Modello dichiarato:

- membership: *unique original-point/passage/segment memberships with separate match support*
- consolidation: *complete corridor compatibility with connected pairwise evidence*

Log pipeline del run ufficiale (coda del file, 2026-09-16):

```
Loaded 44 canonical campaigns
43/44 usable (excluded=1), 100 campaign parts
prefilter 980/4950
pairwise 980 → 555 accepted matches
consolidation 537 segments from 555 pairwise matches
Done: 44 campaigns, 537 repeated segments, 993.7 km total shared length
```

`pipeline.log` contiene ancora in testa i run storici del 2026-07-30 (27 segmenti). Identità ufficiale = `provenance.json`, non le prime righe del log.

### PROVENANCE_GAP

Ricostruibili: commit, timestamp, schema prodotto, fingerprint config matching/QC, input files, checksum input, n campagne, n segmenti.

Non presente in `provenance.json`:

- checksum degli **output** (CSV / GPKG)
- `cache/manifest.json` ha `schema_version: 2` mentre il prodotto ha `repeated_routes_schema_version: 3` (versioni di cache vs prodotto, non necessariamente un conflitto)

Non aggiunto nulla in questa fase.

---

## B. Dataset summary

| Entità | Conteggio verificato | Dichiarato in provenance | Verdetto |
|---|---:|---:|---|
| Campagne catalogo | 44 | 44 | CONSISTENT |
| Campagne inventory matching | 44 | 44 | CONSISTENT |
| Campagne usable | 43 (1 excluded) | 43 | CONSISTENT |
| Campaign parts (log / GPKG) | 100 / 101 | 100 considered | CONSISTENT_WITH_CAVEATS |
| Coppie candidate | 980 | 980 | CONSISTENT |
| Repeated segments | 537 | 537 | CONSISTENT |
| Passages | 1.096 | 1.096 | CONSISTENT |
| Memberships | 155.435 | 155.435 | CONSISTENT |
| Supporting match **rows** | 157.877 | 157.877 | CONSISTENT |
| Supporting match **ID unici** | 555 | 555 pairwise accepted | CONSISTENT |
| Corridor ID unici | 458 | — | — |
| Lunghezza sommata `segment_length_m` | 993.75 km | 993.7 km | CONSISTENT |

La lunghezza 993.75 km è la **somma delle lunghezze dei 537 segmenti**, non una copertura stradale unica. I segmenti si sovrappongono nello spazio (modello many-to-many). Non è verificabile da questo output un “km unici di strada ripetuta”.

Comparison potential (output ufficiale): 1 excellent, 494 good, 42 limited.

Matching quality: 525 high, 9 medium, 3 low.

---

## C. Length distribution

Soglia dichiarata: **shared length ≥ 250 m** (applicata al match pairwise sull’ascissa di traccia ricampionata, CRS 32632).

`segment_length_m` nel CSV è `ref_end − ref_start` sulla traccia di riferimento, non una lunghezza geometrica WGS84.

| Statistica | `segment_length_m` (CSV) | `shared_length_m` (passages) |
|---|---:|---:|
| n | 537 | 1.096 |
| min | 253.06 m | 252.30 m |
| P1 | 290 m | 263.05 m |
| P5 | 320 m | 300 m |
| P10 | 366 m | 348.94 m |
| mediana | 810 m | 810 m |
| media | 1.850,6 m | 1.818,4 m |
| P90 | 5.810 m | 5.779 m |
| P95 | 6.556 m | 6.541 m |
| P99 | 9.750 m | 9.768 m |
| max | 19.690 m | 19.690 m |

Conteggi per soglia (`segment_length_m`):

| Soglia | n segmenti |
|---|---:|
| < 250 m | **0** |
| < 500 m | 144 |
| < 1 km | 298 |
| < 2 km | 395 |
| < 5 km | 475 |
| < 10 km | 532 |
| ≥ 10 km | 5 |

**Il prodotto CSV rispetta la soglia 250 m.** Nessun segmento e nessun passage ha `shared_length_m` < 250 m.

La lunghezza geometrica ricostruita dal GeoPackage (LineString WGS84 → 32632) ha minimo **249.996 m** sui segmenti e **237.09 m** sui passages. La differenza nasce dalla definizione: soglia sul campionamento metrico della traccia, geometria esportata in 4326. Non è una violazione della soglia di matching. Classificato **CONSISTENT_WITH_CAVEATS** (definizione di lunghezza).

Verdetto C: **CONSISTENT** sul CSV ufficiale; **CONSISTENT_WITH_CAVEATS** se si usa la lunghezza del GPKG come proxy della soglia.

---

## D. Passages distribution

| Statistica | n passages / segmento |
|---|---:|
| min | 2 |
| mediana | 2 |
| P90 | 2 |
| P95 | 2 |
| P99 | 3 |
| max | 7 |
| media | 2.041 |

| Classe | n segmenti |
|---|---:|
| 1 passage | **0** |
| 2 passages | **519** (96.6%) |
| 3–5 | 17 |
| 6–10 | 1 (`seg_0231`, 7 passages) |
| 10 | 0 |
| 20 | 0 |

Date distinte per segmento: 107 con 1 data, 424 con 2, 5 con 3, 1 con 4.  
Campagne per segmento: 8 con 1 campagna (due parti della stessa campagna), mediana 2, max 7.

Interpretazione (non è un errore): il consolidamento attuale produce **quasi un segmento per match pairwise**. Un repeated segment con 2 passages è un overlap accettato tra due tracce, non necessariamente un corridoio multi-giorno consolidato. I 18 segmenti con ≥3 passages sono i casi più vicini a un “tratto ripetuto” multi-passaggio.

Verdetto D: **CONSISTENT_WITH_CAVEATS**

---

## E. Many-to-many verification

Chiave semantica verificata: `(repeated_segment_id, segment_passage_id, source_file, source_row)`

| Metrica | Valore | Dichiarato | Verdetto |
|---|---:|---:|---|
| memberships | 155.435 | 155.435 | CONSISTENT |
| `membership_id` unici | 155.435 | — | CONSISTENT |
| duplicati della chiave semantica | **0** | 0 | CONSISTENT |
| source row uniche con membership | 36.338 | 36.338 | CONSISTENT |
| source row in >1 segmento | **26.106** | 26.106 | CONSISTENT |
| max segmenti per source row | **16** | 16 | CONSISTENT |

Distribuzione n segmenti per source row:

| n segmenti | n source row |
|---:|---:|
| 1 | 10.232 |
| 2 | 4.678 |
| 3 | 3.674 |
| 4 | 4.724 |
| 5 | 2.416 |
| 6 | 1.671 |
| 7 | 1.519 |
| 8 | 1.722 |
| 9 | 1.742 |
| 10 | 1.950 |
| 11 | 1.031 |
| 12 | 343 |
| 13 | 277 |
| 14 | 239 |
| 15 | 88 |
| 16 | 32 |

Esempio concreto max=16 (non deduplicato):

- file `05-27/20260527T13_08_42_mtdicambo_AC4D162B317E_Bologna-Bologna.csv`
- `source_row` 1729
- lon/lat 11.354739, 44.50624
- timestamp 2026-05-27T13:52:42Z
- segmenti: `seg_0190`, `seg_0228`, `seg_0239`, `seg_0291`, `seg_0299`, `seg_0313`, `seg_0336`–`seg_0345`

Esempio moderato (3 segmenti): `02-20/...Bologna-Bologna (1).csv` row 1404 → `seg_0017`, `seg_0035`, `seg_0050`.

Il many-to-many è reale, riprodotto dal prodotto, e coerente con un consolidamento che **non consuma** i passaggi sovrapposti. Non è un difetto di join. Per l’integration: un punto originale non è una chiave 1:1 verso `repeated_segment_id`.

Verdetto E: **CONSISTENT**

---

## F. Geometry checks

Matching dichiarato e membership CSV: **EPSG:32632** (metrico) + **EPSG:4326** (lon/lat). Tutte le 155.435 membership hanno `geographic_crs=EPSG:4326` e `metric_crs=EPSG:32632`. Zero NaN lon/lat.

GeoPackage ufficiale `outputs/repeated_routes/repeated_routes.gpkg` (195.207.168 byte):

| Layer | Tipo | CRS | n feature | vuote | invalide |
|---|---|---|---:|---:|---:|
| campaign_tracks | MultiLineString | EPSG:4326 | 19 | 0 | 0 |
| campaign_parts | LineString | EPSG:4326 | 101 | 0 | 0 |
| excluded_or_low_quality_tracks | MultiLineString | EPSG:4326 | 25 | 0 | 0 |
| repeated_segments | LineString | EPSG:4326 | 537 | 0 | 0 |
| segment_passages | LineString | EPSG:4326 | 1.096 | 0 | 0 |
| pairwise_matches | LineString | EPSG:4326 | 559 | 0 | 0 |
| point_segment_memberships | Point | EPSG:4326 | 155.435 | — | — |
| point_segment_match_support | attributes | — | 157.877 | — | — |

19 track “high/medium” + 25 “excluded or low” = **44 campagne**. Coerente.

Il GPKG è in **EPSG:4326 per interoperabilità** (documentato nel codice di export). Il matching non è eseguito in 4326. Non è una contraddizione; è una scelta di prodotto.

BBox segmenti (WGS84): lon 10.8439–12.0370, lat 44.3950–44.7686.  
BBox inventory (tutte le campagne): lon 10.8420–12.2001, lat 44.3548–44.7832.

L’area è quella attesa (Bologna e hinterland, Carpi/Modena a ovest, verso Imola/Ravenna a est). Nessun segmento fuori dall’Italia settentrionale. I tratti più orientali dell’inventory (Ravenna ~12.20) non formano repeated segments: assenza di ripetizione, non geometria errata.

Corrispondenza CSV/GPKG feature count: segmenti 537=537, passages 1096=1096, memberships 155435=155435.

Caveat: lunghezza geometrica GPKG vs `segment_length_m` CSV (vedi C).

Verdetto F: **CONSISTENT_WITH_CAVEATS**

---

## G. Overlap checks

Soglia dichiarata: **overlap ≥ 0.7**, applicata in `matching.py` sia al run grezzo sia all’intervallo emesso (`emitted_overlap`).

Campo disponibile:

- GPKG `pairwise_matches.overlap_fraction` (match ufficiali): n=559, min=0.7016, mediana=0.9555, **0 sotto 0.7**
- CSV `repeated_segments.mean_overlap_fraction`: min=0.7016, **0 sotto 0.7**
- CSV `segment_passages.overlap_fraction`: min=0.7016, **0 sotto 0.7**

I campi CSV sono medie dei `overlap_fraction` pairwise copiate su passage/segment, non un overlap di cluster ricalcolato. La verifica della soglia è possibile e positiva sul layer pairwise del GPKG.

Verdetto G: **CONSISTENT**

---

## H. Direction checks

Categorie effettive nel codice/prodotto: `same_direction`, `opposite_direction`, `direction_uncertain`.

Passages:

| direction_class | n |
|---|---:|
| same_direction | 863 |
| opposite_direction | 232 |
| direction_uncertain | 1 |

`normalized_direction` è più bilanciato (535 same / 560 opposite / 1 uncertain): misura diversa rispetto a `direction_class`.

224 segmenti hanno sia `n_same_direction>0` sia `n_opposite_direction>0`. Con il 96.6% dei segmenti a 2 passages, questo è il caso **andata/ritorno sullo stesso tratto**, non una incoerenza strutturale.

Unico passage uncertain: `seg_0060`, campagna 2026-02-13 pomeriggio, shared_length 566 m. REVIEW_CANDIDATE visivo.

Nessuna inversione di prodotto corretta o segnalata come errore automatico. Route apparentemente “opposte” (Bologna–Sasso vs Sasso–Bologna, Bologna–Carpi vs Carpi–Bologna) sono attese.

Verdetto H: **CONSISTENT_WITH_CAVEATS** (1 uncertain; mixed direction da interpretare come bidirezionale)

---

## I. Temporal distribution

Campagne per data (catalogo, 13 date locali):

| Data | n campagne catalogo | n campagne con passages | n passages | n memberships |
|---|---:|---:|---:|---:|
| 2025-07-04 | 4 | 3 | 59 | 7.712 |
| 2026-02-13 | 2 | 2 | 13 | 2.092 |
| 2026-02-20 | 2 | 2 | 14 | 2.115 |
| 2026-02-21 | 2 | 2 | 62 | 14.021 |
| 2026-02-28 | 3 | 3 | 29 | 5.212 |
| 2026-03-04 | 3 | 3 | 50 | 9.838 |
| 2026-04-27 | 3 | 2 | 24 | 1.951 |
| 2026-05-19 | 1 | 1 | 52 | 8.880 |
| 2026-05-27 | 5 | 5 | 190 | 25.133 |
| 2026-06-04 | 4 | 4 | 35 | 3.633 |
| 2026-06-20 | 5 | 5 | 238 | 41.944 |
| 2026-07-22 | 4 | 3 | 86 | 13.233 |
| 2026-07-30 | 6 | 5 | 226 | 17.992 |
| 2026-07-31 | — | 1* | 18 | 1.679 |

\* `2026-07-31` non è una campagna extra: è il prolungamento oltre mezzanotte locale di `20260730T21_47_28` (Bologna–Bologna serale).

I 537 segmenti **non** derivano da un solo giorno, ma tre giornate dominano i passages:

- 2026-06-20 + 2026-07-30 + 2026-05-27 = **654 / 1.096 passages (60%)**
- membership 2026-06-20 da sola = 27.0%
- 419 segmenti toccano almeno una di queste tre date

430/537 segmenti hanno ≥2 date (80%). Il prodotto è temporalmente più ripetuto del vecchio snapshot (9/27), anche se frammentato.

Verdetto I: **CONSISTENT_WITH_CAVEATS** (distribuzione sbilanciata, non monopolio di un solo run)

---

## J. Spatial distribution

BBox membership = BBox segmenti, interno all’inventory. Zero coordinate NaN.

Quadranti rispetto a Bologna (~11.34 E, 44.50 N), centroidi di segmento:

| Quadrante | n segmenti |
|---|---:|
| ES | 190 |
| EN | 171 |
| WS | 151 |
| WN | 25 |

Griglia 0.05° (~4–5 km): 14 celle occupate. Cella dominante `11.30–11.35 E, 44.45–44.50 N`: **268 segmenti** (nucleo urbano / radiali Bologna). 6 celle isolate (1 segmento), coerenti con Carpi / Modena / tratti extraurbani.

Nessuna mappa ufficiale creata. Cluster denso urbano atteso per overlapping many-to-many; celle isolate non sono anomalie geografiche.

Verdetto J: **CONSISTENT_WITH_CAVEATS** (densità urbana elevata da frammentazione + overlapping)

---

## K. 2026-07-22

Le quattro campagne sono nel catalogo, nel matching input e nel cache manifest.

| Rotta | canonical_campaign_id (suffisso) | Session QC | Suitability spatial / route | recommended keep | inventory quality | passages | memberships | repeated segments | direzione passages |
|---|---|---|---|---:|---|---:|---:|---:|---|
| Bologna → Sasso Marconi | `...Bologna-Sasso_Marconi__bcc4dea3ed` | PASS_WITH_WARNINGS (LONG_GAP) | YES / YES | 0.743 | low | 38 | 5.672 | 38 | 25 same / 13 opposite |
| Sasso Marconi → Bologna | `...Sasso_Marconi-Bologna__e32ec47dca` | PASS_WITH_WARNINGS (TEMP_RATE_ANOMALIES) | YES / YES | 0.759 | medium | 34 | 6.741 | 34 | 27 same / 7 opposite |
| Bologna → Bologna | `...Bologna-Bologna__070b4b2f1a` | PASS_WITH_WARNINGS (LONG_GAP) | YES / YES | 0.693 | low | 14 | 820 | 14 | 7 / 7 |
| Modena → Modena | `...Modena-Modena__46996109ab` | PASS_WITH_WARNINGS (TEMP_RATE_ANOMALIES) | YES / YES | 0.710 | medium | **0** | **0** | **0** | — |

Modena → Modena: 390 keep recommended, 516 punti validi inventory, qualità medium, ma **nessun overlap ≥250 m / ≥0.7** con altre tracce. Assenza attesa (rotta disgiunta). Non è un errore.

Le tre campagne bolognesi hanno membership. I segmenti sono molti e corti (38+34+14), coerenti con il modello pairwise frammentato, non con un unico corridoio Bologna–Sasso.

Verdetto K: **CONSISTENT**

---

## L. 2026-07-30

Sei campagne nel catalogo e nel matching. Downscaling non usato.

| Rotta | canonical_campaign_id (suffisso) | Session QC | Suitability spatial / route | keep | quality | passages | memberships | segments |
|---|---|---|---|---:|---|---:|---:|---:|
| Bologna → Bologna 07:42 | `...97801b6027` | PASS_WITH_WARNINGS | YES / YES | 0.710 | low | 85 | 5.836 | 84 |
| Bologna → Modena | `...ad679738e7` | PARTIAL (LONG_GAP) | YES / YES | 0.777 | low | 32 | 3.178 | 32 |
| Castelfranco Emilia → S. Giovanni in Persiceto | `...77c6b88c91` | PARTIAL (LONG_GAP) | YES / YES | 0.883 | low | **0** | **0** | **0** |
| Bologna → Bologna 13:12 | `...040424d98d` | PASS_WITH_WARNINGS | YES / YES | 0.760 | medium | 37 | 2.332 | 37 |
| Bologna → Bentivoglio | `...f46967787c` | PASS_WITH_WARNINGS | YES / YES | 0.751 | low | 36 | 3.405 | 36 |
| Bologna → Bologna 21:47 | `...a55b7644d6` | PASS_WITH_WARNINGS | YES / YES | 0.688 | medium | 54 | 4.920 | 54 |

Assenza Castelfranco → S. Giovanni: campagna inclusa, punti validi presenti, nessun match ripetuto con il resto del set. Plausibile (corridoio diverso). Non errore.

Verdetto L: **CONSISTENT**

---

## M. Review candidates

Non eliminati, non corretti. Solo etichetta **REVIEW_CANDIDATE** per ispezione visiva.

Criteri che hanno prodotto candidati (34 ID unici, con overlap di motivi):

- lunghezza vicina alla soglia (8 più corti; nessuno sotto 250 m CSV)
- n passages anomalo rispetto alla moda=2 (17 con 3–5, 1 con 7)
- membership molto alte
- densità punti / m elevata
- source point in molti segmenti (cluster 16)
- direzioni miste (attese su andata/ritorno; da verificare visivamente sui casi corti)
- match frammentati
- 1 passage senza membership originali
- 1 direction_uncertain
- 8 segmenti intra-campagna (`n_campaigns=1`)

### 5 segmenti rappresentativi

| ID | motivo | length m | passages | memberships | support rows | pairwise | date | campagne | direzione |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| `seg_0305` | corto (min CSV) | 253.06 | 2 | 23 | 23 | 1 | 2026-05-27, 2026-07-30 | Sasso→BO; BO serale 30/07 | 1 same / 1 opposite |
| `seg_0156` | mediano (~810 m) | 810.00 | 2 | 237 | 237 | 1 | 2026-03-04, 2026-07-30 | BO sera 03-04; BO→Modena | 2 same |
| `seg_0377` | lungo (max) | 19.690 | 2 | 1.178 | 1.178 | 1 | 2026-06-04 | BO→Carpi; Carpi→BO | 1 / 1 |
| `seg_0231` | molti passages | 520.00 | 7 | 290 | 650 | 6 | 4 date (19/05–30/07) | 7 campagne BO/Sasso | 1 same / 6 opposite |
| `seg_0457` | molte membership | 13.081 | 2 | 1.797 | 1.797 | 1 | 2026-06-20 | due BO–BO stesso giorno | 2 same |

### 5 segmenti potenzialmente sospetti

| ID | motivo | length m | passages | memberships | note |
|---|---|---:|---:|---:|---|
| `seg_0381` | frammento corto same-day autostrada | 270 | 2 | 22 | BO→Carpi / Carpi→BO, 04/06, overlap 0.95 |
| `seg_0338` | membro del cluster 16-way | 5.348 | 2 | (nel cluster overlapping) | 27/05 e 20/06; un punto originale cade in 16 segmenti |
| `seg_0313` | 16-way **e** `n_campaigns=1` | 1.770 | 2 | — | due parti della stessa campagna 27/05 13:08 |
| `seg_0177` | passage di riferimento con 0 punti originali | 890 | 2 | 60 (solo l’altro passage) | 27/04; `n_original_points=0` sul reference |
| `seg_0060` | unica `direction_uncertain` | 636 | 2 | — | 13/02, due sessioni stesso giorno |

Lista aggiuntiva corta da ispezionare: `seg_0304` (263 m), `seg_0158`/`seg_0101` (290 m), cluster `seg_0336`–`seg_0345`.

Verdetto M: **REQUIRES_REVIEW** (visivo; nessuna correzione in questa fase)

---

## N. Old vs new

Confronto **descrittivo**. Snapshot storici diversi, non una replica dello stesso run.

| Voce | Snapshot storico (Fase 1, 2026-07-30, commit `cec4ca2`, report `repeated_routes_phase1.md`) | Prodotto ufficiale attuale |
|---|---|---|
| Campagne canoniche | 34 (33 usable) | 44 (43 usable) |
| Periodo | 2025-07-04 → 2026-06-20 | fino a **2026-07-30** (22/07 e 30/07 inclusi) |
| Campaign parts | 74 | 100 |
| Coppie candidate | 512 | 980 |
| Overlap pairs / match | 236 / 301 | 555 match accettati |
| Segmenti | **27** | **537** |
| Lunghezza sommata | ~84 km | 993.7 km (somma overlapping) |
| Passages / memberships | schema precedente, consolidamento aggressivo | 1.096 / 155.435, many-to-many |
| Input | 34 campagne, QC recommended di allora | 44 campagne + catalogo ufficiale + schema 3 |
| 8-1 / 9-8 | assenti | PENDING, esclusi |

Fattori che **possono** produrre l’aumento, senza dichiarare quale prodotto è “giusto”:

1. **Più campagne e copertura temporale** (34→44, +22/07, +30/07): i match pairwise crescono 301→555 (~1.8×). Questo da solo non spiega 27→537.
2. **Più parti di traccia** (74→100) e più coppie candidate (512→980).
3. **Input diverso**: QC/session QC/catalogo della Fase 2, non lo snapshot di luglio.
4. **Algoritmo/config di consolidamento (fattore dominante)**:
   - vecchio: 301 match → 27 segmenti (≈11 match/segmento)
   - nuovo schema 3: 555 match → 537 segmenti (≈1.03 match/segmento)
   - sensitivity attuale resta 370–694 segmenti al variare di soglie: la frammentazione è strutturale al consolidamento *complete corridor compatibility*, non un outlier del baseline
5. **Segmentazione in parti** (gap 120 s) e **clique/corridoi non fusi**: overlapping spaziale contato come segmenti distinti.
6. **Campagne aggiuntive extraurbane** (Carpi, Ravenna/Imola, Bentivoglio, Modena) creano match lunghi same-day (`seg_0377` 19.7 km) che il vecchio set poteva non avere o fondeva diversamente.

Il vecchio 27 non è dimostrato “sbagliato”. Il nuovo 537 non è “migliore” perché più grande. Sono **due prodotti con consolidamento e input diversi**. Per l’integration il contratto da consumare è quello attuale (schema 3, many-to-many, 537 ID), non il report Fase 1.

Verdetto N: **CONSISTENT_WITH_CAVEATS**

---

## O. Scientific interpretation

Classi usate sotto, senza good/bad.

| Tema | Classe | Motivo breve |
|---|---|---|
| Identità run / OFFICIAL vs audit | CONSISTENT | provenance, HEAD, 44 campagne, audit non usato |
| Riconciliazione campagne | CONSISTENT | 44=44=44; 4 senza membership spiegate |
| Soglia 250 m (CSV) | CONSISTENT | min 253 m |
| Soglia 250 m (geometria GPKG) | CONSISTENT_WITH_CAVEATS | passages fino a 237 m ricostruiti |
| Soglia overlap 0.7 | CONSISTENT | min pairwise 0.7016 |
| Conteggi 537 / 1096 / 155435 / 157877 | CONSISTENT | riprodotto dal prodotto |
| Many-to-many 26106 / max 16 | CONSISTENT | esempi concreti |
| 96.6% segmenti con 2 passages | CONSISTENT_WITH_CAVEATS | prodotto pairwise, non corridoi fusi |
| 993 km vs 84 km | CONSISTENT_WITH_CAVEATS | somma overlapping + consolidamento diverso |
| 22/07 e 30/07 | CONSISTENT | Modena e Castelfranco senza membership, atteso |
| Densità urbana / cluster 16 | REQUIRES_REVIEW | ispezione visiva, non incoerenza numerica |
| Passage `seg_0177` senza punti originali | REQUIRES_REVIEW | permesso dal modello resampled? da confermare visivamente |
| Hash output in provenance | PROVENANCE_GAP / NOT_VERIFIABLE dal file provenance | input hash OK; output hash assenti |
| Copertura stradale unica | NOT_VERIFIABLE | non è nel prodotto |

**Giudizio d’insieme: CONSISTENT_WITH_CAVEATS.**

Il prodotto è internamente coerente con lo schema 3 e con le soglie dichiarate. È scientificamente un catalogo di **overlap pairwise consolidati debolmente**, non il catalogo di 27 corridoi lunghi della Fase 1. Può essere consumato dall’integration **a condizione** che il consumer:

- tratti `repeated_segment_id` come many-to-many rispetto ai punti originali;
- non usi 537 come “numero di strade ripetute indipendenti”;
- non usi 993 km come copertura unica;
- non assuma che ogni segmento abbia ripetizioni multi-giorno (107 hanno 1 sola data);
- ispezioni visivamente i REVIEW_CANDIDATE prima di usi climatici puntuali su segmenti corti / overlapping estremi.

---

## P. Final gate

**PASS_WITH_WARNINGS**

Non emerge contraddizione strutturale che impedisca l’uso (soglie rispettate nel CSV, campagne 44 riconciliate, many-to-many verificato, 22/07 e 30/07 coerenti, GPKG allineato ai CSV, input hash OK).

Warnings che restano aperti, senza modifica di codice:

1. Consolidamento schema 3 ≈ 1 segmento per match: 537 non è confrontabile con 27.
2. 26.106 punti in più segmenti (max 16): l’integration deve preservare many-to-many.
3. Dominanza temporale 20/06, 27/05, 30/07.
4. Cluster urbano denso da rivedere visivamente.
5. 1 passage ufficiale senza membership di punti originali (`seg_0177`).
6. 1 direction_uncertain (`seg_0060`).
7. PROVENANCE_GAP sugli hash di output; cache manifest `schema_version=2`.
8. Lunghezza geometrica GPKG non identica a `segment_length_m`.

**BLOCKED non assegnato.**

---

## Reconciliation campagne (dettaglio)

Catalogo vs matching vs passages: **nessuna campagna mancante o duplicata**.

Session QC catalogo: PASS_WITH_WARNINGS 28, PARTIAL 13, PASS 2, NOT_ASSESSABLE 1.

Inventory matching: high 9, medium 10, low 24, excluded 1.

Quattro campagne senza passages/membership (non automaticamente errori):

1. `20260427T07_28_18` Bologna–Bologna — NOT_ASSESSABLE, **excluded**, 21 raw, 0 keep, 18 valid (<20). Fuori matching per soglia.
2. `20250704T09_31_26` Bologna–Bologna moto — PARTIAL, 91 raw, **0 keep recommended**. Nessun punto geometrico utile.
3. `20260722T10_41_01` Modena–Modena — PASS_WITH_WARNINGS, 390 keep, nessuna ripetizione con il resto del set.
4. `20260730T12_17_53` Castelfranco Emilia–S. Giovanni — PARTIAL, 370 keep, nessuna ripetizione.

8-1 e 9-8: PENDING_RAW_NOT_IN_MANIFEST, non nel prodotto. Non promosse.

---

## Supporting matches (relazione reale)

Non sono membership.

```
555 pairwise match ID
   ├─ pairwise_match_segments.csv: 559 righe (4 match puntano a 2 segmenti)
   ├─ GPKG pairwise_matches: 559 geometrie, overlap tutti ≥ 0.7
   └─ point_segment_match_support.csv: 157.877 righe
         = link (membership_id, supporting_match_id)
         155.435 membership coperte (0 senza support)
         2.154 membership con >1 match (max 6)
         rapporto support rows / memberships = 1.016
```

Un supporting match è evidenza pairwise. Una membership è un punto originale assegnato a (segmento, passage). Lo stesso match sostiene molte membership; una membership può avere più match se il punto sta in un segmento alimentato da più evidenze.

Nessun match orfano rispetto ai segmenti. Nessuna membership senza support. Un passage senza membership (`seg_0177` reference, 0 original points): il modello lo permette a livello di intervallo ricampionato.

Verdetto supporting: **CONSISTENT**

---

## Check raw integrity

Checksum `provenance.input_checksums`: **45/45 OK**, 0 mismatch, 0 missing (manifest + 44 raw).

`campaign_catalog_provenance.catalog_sha256` = sha256 attuale del catalogo.

Non ricalcolati/alterati: raw CSV, manifest, QC, recommended, session QC, repeated routes, config.

Hash output calcolati solo in memoria per documentazione; **non scritti** nel prodotto (PROVENANCE_GAP lasciato tale).

---

## File modificati da questa fase

Creato da questa fase:

- `reports/fase2_5_repeated_segments_sanity_check.md`

Nessun altro file toccato da Fase 2.5. Script di calcolo eseguito fuori repo (`%TEMP%\fase25_audit.py`). Nessun commit e nessun push da questa fase.

Stato git a fine audit (working tree ancora dirty, come all’inizio):

- HEAD corrente: `5358a01` (GUI session analysis; preesistente rispetto a questo report, non prodotto da Fase 2.5)
- Modified residui (preesistenti, non toccati qui): 13 file, `+240 / −35`
- Untracked nuovo di Fase 2.5: solo `reports/fase2_5_repeated_segments_sanity_check.md`
- Gli altri untracked (catalogo, repeated_routes, session QC, report Fase 2, …) erano già presenti all’avvio

---

## Stop

Fase 2.5 conclusa. In attesa di autorizzazione per la Fase 3.

Non autorizzato da questa fase: matching, QC, promozione 8-1/9-8, manifest, integration, Netatmo, kriging, temporal correction, MODIS, Landsat, Downscaling, LCZ.
