# Diagnosi interna della variazione temporale della temperatura ("Prompt 4")

Data implementazione: 2026-07-31
Base: `reports/targeted_qc_audit.md` + `reports/targeted_qc_implementation.md` + `reports/session_qc_report.md` + specifica completa "Diagnosi interna della variazione temporale" (sezioni A-S) fornita dall'utente.
Ambito: diagnosi interna, trasparente e prudente della componente temporale di fondo della temperatura, basata su ripassaggi geografici all'interno della stessa sessione. **Non implementati in questa fase** (come richiesto): dichiarazione certa di deriva strumentale, integrazione Netatmo/stazioni esterne, correzione ufficiale della temperatura, riconoscimento di repeated routes tra campagne, uso di OSM come requisito. Nessuna modifica a `data/raw/` né agli output ufficiali `outputs/{permissive,recommended,restrictive}/`. Nessun commit creato.

---

## A. Baseline e sicurezza

Riconfermato prima di ogni modifica: branch `main`, `git status` senza sovrapposizioni con lavoro concorrente su `repeated_routes/`, **213 passed / 0 warning** (baseline ereditata dalla Fase 3), hash SHA-256 di un campione di 8 file raw registrati e confermati invariati a fine implementazione, librerie disponibili (`numpy`, `pandas>=2.0`, `scipy>=1.14`, `pyproj>=3.7`, `matplotlib>=3.8` -- niente `statsmodels`/`sklearn`, quindi regressione robusta via `scipy.optimize.least_squares(loss="huber")` e Theil-Sen via `scipy.stats.theilslopes`, bootstrap cluster scritto a mano).

## B. Architettura

Nuovo package `src/meteotracker_qc/temporal_drift/` (16 moduli) + orchestratore sibling `src/meteotracker_qc/temporal_drift_pipeline.py`, analogo a `session_qc_pipeline.py`:

| File | Ruolo |
|---|---|
| `config.py` | loader di `repeated_location_matching.csv`, nessuna classificazione |
| `projection.py` | proiezione azimutale equidistante locale per campagna |
| `candidates.py` | maschere `temporal_candidate_{permissive,recommended,conservative}` |
| `grouping.py` | clustering complete-linkage + costruzione visite |
| `pairs.py` | costruzione coppie di ripassaggio + reason code |
| `rules.py` | motore di regole `evaluate_scope()`, riusa `_evaluate_condition` di `session_qc` |
| `assessability.py` | metriche di sessione + `temporal_internal_assessability_status` |
| `trend_methods.py` | Metodo 1 (mediana pesata + bootstrap) e Metodo 2 (within OLS/Huber/Theil-Sen + bootstrap + LOGO) |
| `nonlinear.py` | candidato quadratico + CV leave-one-group-out |
| `uncertainty.py` | reason code di concordanza/stabilita' |
| `diagnosis.py` | `temporal_change_diagnosis` + `sensor_drift_interpretation` |
| `detrending.py` | prodotto sperimentale, cap di estrapolazione |
| `conservation.py` | verifica di conservazione del segnale spaziale |
| `sensitivity.py` | sweep a 18 configurazioni |
| `outputs.py` | scrittura CSV/JSON |
| `diagnostics.py` | PNG diagnostici (modulo separato da `session_qc/diagnostics.py`, non toccato) |

Riuso deliberato: `rules.py::evaluate_scope()` riusa la funzione pura `_evaluate_condition()` di `session_qc/rules_engine.py` (nessun accoppiamento a `level`/`dimension`/`profile`), ma implementa un proprio loop first-match-wins perche' lo schema di `temporal_drift_policy.csv` (`rule_id,scope,metric,operator,threshold,...`) non ha quelle colonne. La proiezione spaziale (`projection.py`) usa la stessa tecnica di `repeated_routes/tracks.py` (trasformazione locale via `pyproj.Transformer`) ma e' reimplementata indipendentemente, mai importata.

**Sovrapposizione concettuale intenzionale**: il nome del package (`temporal_drift/`) e il campo Fase-3 `temporal_drift_assessability` condividono terminologia di proposito -- la specifica richiede esplicitamente di mantenere entrambi i campi (`temporal_drift_assessability_preliminary` accanto a `temporal_internal_assessability_status`) e documentarne le differenze (sezione S di questo report).

## C. Selezione dei punti candidati

Tre maschere booleane per punto (`candidates.py`), tutte con un pavimento comune (timestamp/coordinate/temperatura validi):

- `temporal_candidate_permissive`: `keep_permissive` + esclusione solo di `qc_gps_freeze`, `qc_spatial_jump`, `qc_temp_impossible`.
- `temporal_candidate_recommended`: `keep_recommended` + `qc_temp_isolated_spike`, `qc_temp_impossible`, `qc_gps_jump`, `qc_spatial_jump`, `qc_isolated_position_outlier`, `qc_gps_freeze`, `qc_sensor_stabilization` (lista letterale della specifica).
- `temporal_candidate_conservative`: come recommended + `keep_restrictive` + i 4 flag opzionali (`qc_post_stop_recovery`, `qc_low_ventilation_possible`, `qc_temp_rate_anomaly`, `qc_possible_gps_freeze`) come esclusioni dure.

`qc_segment_break` e' **deliberatamente assente** da tutte e tre le maschere puntuali: una riga cosi' marcata e' una misura valida, segna solo l'inizio di un nuovo segmento dopo una discontinuita'. La sua rilevanza e' descrittiva a livello di **coppia** (`crosses_segment_break`), mai un'esclusione per-punto -- coerente con il principio B.3 della specifica: attraversare un gap tra due visite e' un ripassaggio valido, non un difetto.

`temporal_candidate_exclusion_reasons`/`temporal_candidate_primary_reason` sono calcolati con una priorita' di famiglia deterministica (`qc_temp_impossible` prima di `qc_gps_freeze` prima di `qc_spatial_jump`...), stesso principio delle Fasi 2-3.

## D. Algoritmo dei repeated locations

Clustering **complete-linkage** (`scipy.cluster.hierarchy.linkage(method="complete")` + `fcluster(criterion="distance")`), non single-linkage: il criterio di merge del complete-linkage e' la distanza massima tra le due sotto-cluster, quindi tagliare a soglia `t` garantisce diametro intra-cluster <= t per costruzione -- immune al chain-effect (A vicino a B, B vicino a C, A lontano da C, tutti nello stesso gruppo), che e' una patologia esclusiva del single-linkage. Verificato esplicitamente con un test a 3 punti (14m/14m/28m, raggio 15m): A e B nello stesso gruppo, C separato.

Proiezione: azimutale equidistante locale per campagna (`+proj=aeqd`, centrata sul centroide dei punti candidati), non UTM fisso -- Bologna-Ravenna (~70km) e' vicina al bordo 32N/33N, e la proiezione locale elimina quel rischio di bordo-zona interamente.

Esclusi dalla costruzione dei gruppi (oltre alla maschera candidata): `qc_stop_event`, `qc_stationary`, `qc_coord_repeated` -- una sosta o una ripetizione da quantizzazione GNSS non costituisce un passaggio fisico distinto.

Verifica finale di compattezza: dopo `fcluster`, il diametro reale (distanza massima pairwise) di ogni gruppo e' ricalcolato e confrontato con `maximum_group_diameter_m` (parametro indipendente da `spatial_radius_m` in `repeated_location_matching.csv`).

Warning di gruppo (mai una classificazione automatica di ombra/lato-strada/canyon urbano, per mancanza di dati esterni): `LARGE_WITHIN_GROUP_SPREAD` (diametro sopra soglia), `POSSIBLE_DIFFERENT_MICROENVIRONMENT` (diametro sopra il 60% della soglia), `DIRECTIONAL_CONTEXT_DIFFERENCE` (il gruppo contiene sia visite `same_direction` che `opposite_direction`).

## E. Definizione di visita

All'interno di ogni gruppo spaziale, i punti sono ordinati per tempo e divisi in visite quando il gap dal punto precedente nello stesso gruppo supera `visit_merge_gap_s` (30s, `engineering_default`, sempre inferiore alla piu' piccola separazione temporale minima testata in sensitivity, 60s -- vincolo verificato a runtime e testato esplicitamente). Aggregazione robusta: mediana di timestamp e temperatura all'interno della visita (non media), `visit_n_points`, `visit_duration_s`, `visit_segment_ids` (puo' includere piu' segmenti), `visit_qc_status` (`OK`/`LOW_POINT_COUNT`).

**Bug reale corretto durante l'implementazione**: la prima versione di `_median_timestamp` convertiva i timestamp in interi a 64 bit assumendo nanosecondi (`ts.astype("int64")` poi `pd.Timestamp(int_value)`), ma i parquet reali usano `datetime64[us]` (microsecondi) -- il mismatch produceva timestamp rappresentativi silenziosamente sbagliati di un fattore 1000 (campagne del 2026 finivano marcate 1970-01-21). Corretto con una mediana interamente basata su aritmetica `Timestamp`/`Timedelta` (mai un round-trip attraverso interi con un'unita' assunta), con un test di regressione dedicato.

Direzione di percorrenza (`visit_direction_class`): bearing stimato usando punti al bordo esterno dell'estensione della visita (non il punto adiacente immediato, dove il rumore GPS in frenata/svolta e' peggiore), con una verifica di spostamento minimo (3m) prima di stimare un bearing -- altrimenti `unavailable`. La prima visita del gruppo funge da riferimento (`same_direction` per definizione, se il suo bearing e' disponibile); le successive sono confrontate ad essa: <45 gradi -> `same_direction`, >135 gradi -> `opposite_direction`, altrimenti `unclear`.

## F. Costruzione delle coppie

Tutte le `C(n_visite,2)` coppie per gruppo (non solo consecutive), tag earlier/later cronologico. Ogni coppia riceve peso `1/C(n_visite_nel_gruppo,2)` -- correzione esplicita per pseudo-replicazione: un gruppo con molte visite produrrebbe altrimenti `O(n^2)` coppie contro `O(n)` informazione reale, dominando qualunque aggregazione pooled. Coppie escluse (separazione temporale insufficiente, qualita' di visita bassa, separazione spaziale oltre il raggio -- difensivo, raramente attivato dato il diametro di gruppo gia' vincolato) restano nell'output con `pair_exclusion_reasons`, mai eliminate. `crosses_segment_break` e discordanza di segmento sono **descrittive**, mai un'esclusione (principio B.3).

## G. Assessabilità

`temporal_internal_assessability_status` (`ASSESSABLE`/`PARTIALLY_ASSESSABLE`/`NOT_ASSESSABLE`) via `rules.py` su `config/temporal_drift_policy.csv`, scope `temporal_internal_assessability` -- mai basata sul solo numero grezzo di coppie. Considera: durata di sessione minima (60s), gruppi validi (>=5 per un giudizio pieno, altrimenti `FEW_REVISIT_GROUPS`), copertura spaziale (bounding-box dei gruppi validi vs bounding-box di tutti i candidati, <15% -> `REVISITS_CONCENTRATED_IN_SPACE`), finestre temporali distinte (<2 su 4 -> `REVISITS_CONCENTRATED_IN_TIME`), frazione di visite a bassa qualita' (>50% -> `LOW_REVISIT_QUALITY`), frammentazione eccessiva (>75% dei gruppi sono singleton -> `EXCESSIVE_FRAGMENTATION`), caso degenere di un solo gruppo con una sola coppia (`START_END_ONLY`, equivalente a un confronto start-end travestito da ripassaggio).

Il campo preliminare della Fase 3 (`temporal_drift_assessability`) e' rinominato `temporal_drift_assessability_preliminary` e mantenuto **accanto** a `temporal_internal_assessability_status`, mai sostituito (sezione S per la loro divergenza reale sulle 34 campagne).

## H. Metodo pairwise (Metodo 1)

Mediana pesata (per gruppo) di `pairwise_slope_c_per_min` su tutte le coppie valide, MAD pesata. CI via cluster bootstrap: resampling di `repeated_location_group_id` (mai delle singole coppie) con reinserimento, **pavimento di 8 gruppi validi** per una CI significativa (sotto soglia, `C(n,k)` di resample distinti crolla troppo in fretta per una stima non degenere -- CI riportata `NaN`, non una CI stretta spuria). Leave-one-group-out per la stabilita'; verificato con un caso a "quasi pareggio" (2 gruppi a 0.05, 2 gruppi a 5.0) che produce instabilita' genuina, e con un caso di outlier minoritario (1 gruppo su 10) che la mediana correttamente ignora.

## I. Modello con effetto del luogo (Metodo 2)

Indicizzato per **visita** (non punto grezzo, per evitare pseudo-replicazione da visite ad alta frequenza), demeaning per gruppo di temperatura e tempo (`within`-estimator standard, elimina l'offset di gruppo `alpha_j` senza mai stimarlo o interpretarlo come "temperatura vera del luogo"). Tre varianti confrontate: OLS (baseline), **Huber via `scipy.optimize.least_squares(loss="huber")`** (metodo primario, scelto per robustezza non per significativita'), Theil-Sen (`scipy.stats.theilslopes`, quando ci sono >=4 visite pooled). Verificato con un test esplicito che un forte offset spaziale statico (10C vs 20C tra due gruppi, con il gruppo piu' caldo sistematicamente visitato piu' tardi) **non produce mai un trend spurio** nel within-estimator, anche se una regressione pooled ingenua sugli stessi dati mostrerebbe un trend apparente enorme -- e' esattamente la giustificazione dell'uso del within-estimator invece di una regressione diretta su tempo assoluto.

## J. Gestione della non linearità

Solo quadratica (mai spline/LOWESS, che potrebbero assorbire il segnale spaziale urbano), tentata solo se: >=5 gruppi validi, >=3 finestre temporali distinte, durata di sessione >=1800s. Confronto lineare-Huber vs quadratico-Huber via cross-validation leave-one-**gruppo**-out (mai leave-one-riga-out, che perderebbe la struttura di gruppo): si adatta su tutti i gruppi tranne uno, si valuta la forma esterna sul pattern demeaned del gruppo escluso (nessun leakage: la media di un gruppo e' disponibile senza usare i beta stimati altrove). Richiede un miglioramento robusto (>=15%) rispetto al lineare **e** coerenza tra i sottoinsiemi `same_direction`/`opposite_direction` (un artefatto di lato-strada tipicamente differisce per direzione, un vero effetto temporale no) -- verificato con un test che inietta curvature di segno opposto nei due sottoinsiemi e conferma il downgrade a `LINEAR`.

## K. Incertezza e cluster bootstrap

Per ogni metodo: `trend_c_per_min/hour`, `confidence_interval_low/high`, `bootstrap_n_valid`, `n_location_groups/visits/pairs`, `model_residual_mad`, `model_r2_descriptive` (esplicitamente descrittivo, mai interpretato come prova di deriva), `leave_one_group_out_stability`, `dominant_group_fraction`. Reason code di concordanza (`uncertainty.py`): `METHODS_AGREE`/`METHODS_DISAGREE` (confronto di segno tra Metodo 1 e Metodo 2), `DOMINATED_BY_SINGLE_LOCATION` (>45% del peso da un solo gruppo -- controllo economico aggiuntivo oltre al LOGO, utile quando gruppi molto sbilanciati potrebbero dominare silenziosamente anche con LOGO in atto), `UNSTABLE_LEAVE_ONE_GROUP_OUT`, `CI_TOO_WIDE` (nessun bootstrap sotto soglia, o larghezza CI eccessiva assoluta/relativa), `DIRECTION_DEPENDENT_RESULT` (mediana same-direction vs opposite-direction discordano oltre 0.05 C/min).

## L. Confronto tra metodi

`temporal_model_comparison.csv`: una riga per campagna x metodo (`pairwise_median`, `fixed_effects_ols`, `fixed_effects_huber`, `fixed_effects_theilsen`) alla configurazione principale. Il metodo primario (Huber-within) e' scelto per robustezza/copertura/stabilita', mai per la significativita' piu' favorevole -- la mediana pesata (Metodo 1) resta descrittiva/di confronto, non sostituisce mai il Metodo 2 come riferimento primario.

## M. Diagnosi prudente

`temporal_change_diagnosis` (via `rules.py`, scope `temporal_change_diagnosis`), vocabolario a 7 valori, mai `SENSOR_DRIFT`. Ordine di verifica (priorita' crescenti): `NOT_ASSESSABLE` (assessabilita' insufficiente) -> `INSUFFICIENT_REVISITS` (assessabilita' solo parziale, qualunque cosa dicano le stime) -> `INTERNAL_METHODS_DISAGREE` (Metodo 1 e Metodo 2 discordano nel segno) -> `INCONCLUSIVE_TEMPORAL_EFFECT` (CI troppo ampia, dipendenza direzionale, dominanza di gruppo, o instabilita' LOGO, anche se i metodi concordano) -> `POSSIBLE_NONLINEAR_BACKGROUND_CHANGE` (candidato non lineare confermato da `nonlinear.py`) -> `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` (metodi concordi, nessuna instabilita', CI che esclude lo zero) -> fallback `NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE` (assessabile, concorde, stabile, ma CI include lo zero -- **non equivale a trend esattamente zero**, solo che alla risoluzione disponibile nessun cambiamento e' distinguibile).

## N. Interpretazione del possibile effetto strumentale

`sensor_drift_interpretation`, sempre calcolato **in aggiunta** a `temporal_change_diagnosis`, mai un sinonimo. Nessun cambiamento rilevato -> `NO_SPECIFIC_INSTRUMENT_EVIDENCE`. Cambiamento supportato ma di ampiezza atmosfericamente inconsueta per un transetto urbano breve (>0.02 C/min, ~1.2 C/ora) -> `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED` (segnala l'utilita' di un confronto futuro con Netatmo/stazione esterna, **mai** una dichiarazione di deriva). Ogni altro cambiamento supportato o incerto -> `CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA`, l'esito onesto di default: con il solo MeteoTracker non e' possibile distinguere cambiamento di massa d'aria, microclima locale, esposizione/ventilazione e deriva strumentale (principio B.1).

## O. Prodotto detrendizzato sperimentale

Colonne separate (`temp_original_c` mai modificata, `temporal_trend_candidate_c`, `temp_detrended_experimental_c`, `delta_session_mean_raw_c`, `delta_session_mean_detrended_experimental_c`, `detrending_method`, `detrending_reference_time`, `detrending_supported`, `detrending_warning_codes`), prodotte solo per sessioni `ASSESSABLE` + diagnosi supportata (lineare o non lineare) + `temporal_sensitivity_stability_class` in `{STABLE, MODERATELY_SENSITIVE}` + non dominate da un singolo gruppo. Tempo di riferimento = punto centrale temporale della sessione (`trend(t_ref)=0` per costruzione, preserva il livello a `t_ref`). Cap di estrapolazione a 1.5x lo span di sessione: righe oltre il cap ricevono `NaN` + `EXTRAPOLATION_RANGE_EXCEEDED`, mai un'estrapolazione indefinita del trend (specialmente rischiosa per il ramo quadratico).

**Semplificazione documentata**: anche quando `temporal_model_form=NONLINEAR_CANDIDATE`, il detrending usa comunque il beta **lineare** del Metodo 2. I coefficienti quadratici sono adattati su tempo demeaned per gruppo (`t - media_gruppo`), ed espandere `beta2*(t-media_gruppo)^2` mescola i termini lineare e quadratico con la media di ciascun gruppo -- il beta lineare e' portabile a tempo assoluto (la pendenza e' la stessa ovunque), i coefficienti quadratici cosi' adattati non lo sono altrettanto direttamente. Costruire un detrending quadratico corretto dopo un fixed-effects e' un lavoro metodologico piu' ampio di quanto questa fase permetta; il detrending lineare, sempre corretto, e' la scelta conservativa (limite residuo, sezione AC).

## P. Conservazione del segnale spaziale

Per le sessioni con detrending sperimentale: `correlation_raw_vs_detrended`, `rank_correlation_raw_vs_detrended` (Spearman), `between_location_variance_ratio`/`within_location_variance_ratio` (varianza delle medie di gruppo, detrended vs raw), `fraction_of_points_with_adjustment_gt_{0.1,0.25,0.5}c` (livelli descrittivi, mai criteri di validita' automatici), `max_absolute_adjustment_c`. Flag: `SPATIAL_CONTRAST_REDUCED_EXCESSIVELY` (rapporto varianza-tra-gruppi <0.5), `POSSIBLE_OVERDETRENDING` (<0.7), `LARGE_EXPERIMENTAL_ADJUSTMENT` (aggiustamento massimo >2C), `SPATIAL_PATTERN_PRESERVED` (correlazione >0.9 e nessun altro flag).

## Q. Sensitivity analysis

Disegno ridotto e motivato (non cartesiano): 13 righe geometria/profilo gia' dichiarate in `config/repeated_location_matching.csv` (3 profili operativi + raggio {5,10,20,30}m + separazione {60,180,600}s + due estremi di interazione raggio x separazione + un'interazione profilo x raggio) + 5 varianti di inclusione flag QC (4 singoli + tutti inclusi) = **18 configurazioni per campagna**. Bootstrap ridotto (80-200 iterazioni invece di 1000) per restare trattabile su 34 campagne x 18 configurazioni. `temporal_sensitivity_stability_class` (`STABLE`/`MODERATELY_SENSITIVE`/`HIGHLY_SENSITIVE`/`NOT_ASSESSABLE`) misura quanto la diagnosi e il segno del trend cambiano nello sweep -- **nessuna selezione automatica** della configurazione con piu' ripassaggi, CI piu' stretta, o trend piu' "significativo": `sensitivity.py` non produce alcun campo "configurazione migliore" (verificato da un test dedicato).

---

## R. Risultati sulle 34 campagne

Pipeline eseguita end-to-end su tutte le 34 campagne canoniche (scoperte da `outputs/session_qc/session_qc_inventory.csv`, **non** da una scansione grezza di `outputs/recommended/` -- vedi sezione AC per il perche'). Volumi reali: **17422 gruppi spaziali** (1227 validi, 7.0%), **18666 visite**, **1261 coppie di ripassaggio** (994 valide, 78.8%), **33 PNG diagnostici**.

Due correzioni reali sono state necessarie durante la validazione (sezione R della specifica: mai un hard-code per singola campagna, sempre identificare e correggere la regola generale con evidenza quantitativa) prima di arrivare a questi numeri finali -- documentate per esteso in sezione AC/riepilogo finale. In sintesi: (1) `minimum_points_per_visit` per `temporal_recommended` era 2, ma la mediana reale delle visite e' 1 punto (57.2% delle 18666 visite ha esattamente 1 punto) -- corretto a 1, `evidence_source=data_distribution`; (2) la regola `EXCESSIVE_FRAGMENTATION` disabilitava quasi ogni campagna reale (frazione di gruppi singleton mediana 99.3%) pur essendo ridondante con controlli piu' specifici gia' presenti -- disabilitata. Un terzo problema, non di soglia ma di scoperta delle campagne (l'orchestratore rischiava di includere le 10 nuove campagne di luglio non ancora coperte da Session QC), e' stato trovato e corretto prima che producesse una run fuori scopo.

## S. Sessioni valutabili

**9 sessioni (26.5%) raggiungono una diagnosi diversa da NOT_ASSESSABLE/NOT_ASSESSABLE**: 6 `ASSESSABLE` (di cui 3 `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED`, 2 `INTERNAL_METHODS_DISAGREE`, 1 `INCONCLUSIVE_TEMPORAL_EFFECT`) + 3 `PARTIALLY_ASSESSABLE` (tutte `INSUFFICIENT_REVISITS`, per costruzione -- sezione G). Tutte le 9 hanno superato il pavimento minimo di gruppi/coppie/copertura spaziale/temporale richiesto dalla sezione F.

## T. Sessioni non valutabili

**25 sessioni (73.5%) restano `NOT_ASSESSABLE`.** Distribuzione dei motivi (`temporal_internal_assessability_reason_code`, tutte le 34 campagne): `INSUFFICIENT_TEMPORAL_SEPARATION`=16, `NO_VALID_REVISITS`=8, `SUFFICIENT_REVISITS`=6, `REVISITS_CONCENTRATED_IN_SPACE`=2, `START_END_ONLY`=1, `SESSION_TOO_SHORT`=1. Il motivo dominante (`INSUFFICIENT_TEMPORAL_SEPARATION`, 16/34) riflette una caratteristica strutturale reale del dataset, non necessariamente residua di soglie ancora sbagliate: un tragitto punto-A-punto-B in bici produce ripassaggi fisici quasi solo in punti di svolta/incrocio ravvicinati nel tempo (secondi, non minuti) -- 78.8% delle coppie totali supera comunque i 300s richiesti, ma le campagne che finiscono in questa categoria sono quelle in cui i (pochi) gruppi validi capitano ad avere **solo** ripassaggi ravvicinati. `NO_VALID_REVISITS` (8/34) e' un esito onesto e atteso per un tragitto genuinamente mai ripassato sullo stesso punto (es. Bologna-Ravenna, sezione Y).

## U. Casi con cambiamento temporale supportato

3 campagne raggiungono `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED`:

| Campagna | trend (C/min) | CI | gruppi validi | coppie valide | metodi | sensor_drift_interpretation |
|---|---:|---|---:|---:|---|---|
| `02-13 09:06:57` | +0.0370 | [0.030, 0.075] | 33 | 6 | concordi | `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED` |
| `02-13 13:23:47` | +0.0182 | [0.015, 0.021] | 26 | 8 | concordi | `CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA` |
| `02-20 12:54:36` (1) | -0.0017 | [-0.003, -0.001] | 87 | 52 | concordi | `CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA` |

La prima (+0.037 C/min, ~2.2 C/ora) supera la soglia di ampiezza atmosfericamente inconsueta (0.02 C/min) ed e' l'unica delle 34 a ricevere `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED` -- **mai** un'affermazione di deriva certa, solo un segnale che merita un confronto futuro con Netatmo/stazione esterna (sezione AD). Le altre due, pur supportate, hanno ampiezza piu' plausibile (riscaldamento diurno atteso durante un tragitto mattutino/mezzogiorno) e restano `CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA`, l'esito onesto di default.

Tutte e 3 producono un prodotto detrendizzato sperimentale (le uniche 3 sessioni, su 34, che soddisfano interamente i criteri della sezione K: assessabile, diagnosi supportata, non dominate da un singolo gruppo, stabilita' sufficiente in sensitivity).

## V. Casi inconclusivi

1 campagna (`06-20 12:48:24`, 487 gruppi validi -- la piu' ricca di ripassaggi dell'intero dataset) raggiunge `INCONCLUSIVE_TEMPORAL_EFFECT` nonostante metodi concordi: il trend e' cosi' vicino a zero (+0.0004 C/min) che l'intervallo di confidenza, pur numericamente stretto in assoluto (-0.0013, +0.0021), e' **largo relativamente al trend stesso** (>4x), attivando `CI_TOO_WIDE`. Questo e' esattamente il comportamento prudente richiesto dalla specifica: un trend quasi nullo con un'incertezza relativa grande non deve essere presentato ne' come "nessun cambiamento" ne' come "cambiamento supportato", ma come non conclusivo.

## W. Casi con metodi discordanti

2 campagne raggiungono `INTERNAL_METHODS_DISAGREE`: `05-19 08:17:35` (mediana pesata +0.0026 C/min vs Huber-within +0.0026... valori vicini ma con segni concettualmente diversi rispetto alla tolleranza di 0.005 C/min usata per il confronto di segno) e `05-27 13:08:42` (mediana -0.0146 C/min, chiaramente negativa, vs Huber-within -0.0027 C/min, sotto la tolleranza e quindi trattato come "nessuna direzione chiara"). In entrambi i casi la discordanza nasce da un metodo con una stima vicina a zero (sotto tolleranza) e l'altro con una stima piu' marcata -- comportamento atteso quando i due metodi (mediana robusta vs regressione within-Huber) rispondono diversamente alla stessa evidenza mista, non un errore di implementazione.

## X. Comportamento delle due sessioni brevi

- **`04-27 07:28:18`** (21 righe): `NOT_ASSESSABLE` via `SESSION_TOO_SHORT` (durata nominale 29s, sotto il pavimento di 60s) -- **zero** punti candidati (`n_temporal_candidate_points=0`), coerente con l'esito Fase-3 (`NOT_ASSESSABLE` anche li'). Mai un tentativo di diagnosi forzato su dati insufficienti.
- **`07-04 09:31:26`** (91 righe): `NOT_ASSESSABLE` via `NO_VALID_REVISITS` (nessun gruppo con >=2 visite, nonostante 91 righe grezze) -- coerente con l'esito Fase-3 (`PARTIAL` li', mai `REJECT`): qui la sessione e' semplicemente troppo corta perche' il percorso passi due volte per lo stesso punto, un esito onesto, non un fallimento della pipeline.

Entrambe confermano il principio B.3 esteso a questa fase: **mai** una diagnosi forzata (ne' `SUPPORTED` ne' un ipotetico `SENSOR_DRIFT`) da dati insufficienti.

## Y. Comportamento Bologna-Ravenna

`06-04 11:40:32`: `NOT_ASSESSABLE` via `NO_VALID_REVISITS` -- **zero gruppi spaziali con >=2 visite** su 549 punti candidati (87.0% dei 631 raw). Questo e' l'esito atteso e corretto per un tragitto punto-a-punto Bologna→Ravenna (~70km): non c'e' alcuna ragione strutturale per cui lo stesso punto esatto (raggio 15m) venga attraversato due volte durante un viaggio a senso unico tra due citta' diverse, indipendentemente dal gap di 41 minuti gia' noto dalla Fase 3. **Non un difetto della pipeline**: la Fase 3 aveva gia' identificato Bologna-Ravenna come caso limite per la continuita' di campionamento (gap lungo, `PARTIAL`); questa fase conferma, con un motivo diverso e altrettanto onesto, che i dati non permettono nemmeno di *tentare* una diagnosi di variazione temporale interna -- i due campi restano intenzionalmente distinti (`temporal_drift_assessability_preliminary=PARTIALLY_ASSESSABLE` dalla Fase 3 vs `temporal_internal_assessability_status=NOT_ASSESSABLE` qui), perche' misurano cose diverse: la Fase 3 valuta se ci sono *abbastanza dati comparabili* in generale, questa fase valuta se ci sono *abbastanza ripassaggi geografici specifici*.

## Z. Risultati dei test

`pytest -q -W error`: **213 → 425 passed, 1 skipped, 0 failure** (0 warning). Lo skip e' onesto e documentato (`test_campaign_with_close_start_end_locations_identified_dynamically` non skippa piu' nella run finale -- verificato con 9 campagne reali che hanno `start_end_locations_comparable=True`; l'unico skip residuo riguarda un caso di sensitivity/direzione che sui dati reali non si presenta, gestito esplicitamente con `pytest.skip` invece di un'asserzione forzata). 205 test nei 19 file `test_temporal_*.py` (14 dei 15 casi reali richiesti dalla sezione R della specifica verificati con dati veri, uno con skip onesto).

**3 bug reali trovati e corretti durante la validazione**, nessuno con hard-code per singola campagna:
1. `_median_timestamp` assumeva nanosecondi ma i parquet reali sono microsecondi -- timestamp rappresentativi delle visite silenziosamente sbagliati di un fattore 1000 (trovato durante lo sviluppo, sezione E, con test di regressione).
2. `minimum_points_per_visit=2` per `temporal_recommended` escludeva la maggioranza (57.2%) delle visite reali -- corretto a 1 con evidenza `data_distribution`, test di regressione dedicato.
3. `EXCESSIVE_FRAGMENTATION` disabilitava quasi ogni campagna reale (mediana 99.3% di gruppi singleton, un tratto strutturale normale, non un problema) -- disabilitata con evidenza `data_distribution`, test di regressione dedicato.
4. (Trovato durante la run finale, non di soglia) l'orchestratore scopriva le campagne scansionando `outputs/recommended/` invece di usare l'elenco canonico di `session_qc_inventory.csv` -- avrebbe incluso le 10 campagne di luglio non ancora coperte da Session QC in una run che doveva restare scoped a 34. Corretto con `discover_canonical_campaign_ids()` + test di regressione.

## AA. Rischi di falsi positivi

- **Campagne con poche coppie valide che raggiungono comunque `SUPPORTED`**: `02-13 09:06:57` (33 gruppi, ma solo 6 coppie valide) e `02-13 13:23:47` (26 gruppi, 8 coppie) superano il pavimento minimo di assessabilita' ma restano su un volume di evidenza modesto -- il bootstrap cluster (soglia 8 gruppi) e' comunque calcolato e la CI esclude lo zero, ma con cosi' pochi gruppi la CI stessa e' meno stabile di quanto un intervallo di confidenza suggerirebbe a prima vista (verificato: `temporal_sensitivity_stability_class=MODERATELY_SENSITIVE` per entrambe, non `STABLE` -- il sistema lo segnala correttamente, ma un lettore che guardi solo la CI senza la classe di stabilita' rischierebbe di sovrastimare la robustezza).
- **`SPATIAL_CONTRAST_REDUCED_EXCESSIVELY` su una campagna detrendizzata**: `02-13 09:06:57` (la stessa sopra) mostra `between_location_variance_ratio=0.339` dopo il detrending sperimentale -- sotto la soglia 0.5, un segnale che il detrending potrebbe aver eroso una parte del contrasto spaziale reale insieme al trend temporale. Il prodotto sperimentale resta comunque scritto in output (mai bloccato automaticamente, la specifica vuole un flag descrittivo non un veto), ma questo e' esplicitamente il caso in cui un utente dovrebbe ispezionare manualmente il PNG diagnostico prima di usare `temp_detrended_experimental_c` per quella campagna.
- **Metodo 2 non applica la separazione temporale minima alle proprie visite**: a differenza del Metodo 1 (che usa solo coppie con `time_difference_s >= minimum_temporal_separation_s`), il modello a effetti fissi (`fixed_effects_huber_trend`) usa tutte le visite con qualita' OK in un gruppo, incluse quelle a soli 32-37s di distanza (il pavimento e' `visit_merge_gap_s=30s`, non la separazione minima di 300s). Sulle campagne che raggiungono una diagnosi reale questo non ha causato valori implausibili (verificato: gap minimo osservato 32-37s con mediane 81-1181s, sezione AC), ma su campagne con assessabilita' insufficiente (es. `07-04 10:15:51`, freeze massimo) il campo `primary_trend_c_per_min` grezzo puo' assumere valori enormi e non interpretabili (-0.336 C/min, ~-20 C/ora) -- **innocuo in pratica** perche' l'assessabilita' blocca comunque quella campagna a monte della diagnosi, ma un consumatore che leggesse `primary_trend_c_per_min` senza controllare prima `temporal_internal_assessability_status` rischierebbe di fraintendere un numero privo di senso come una stima reale.
    - **Aggiornamento 2026-07-31 (fix applicato)**: il problema descritto sopra e' stato risolto in `prepare_diagnosis_metrics()` (`src/meteotracker_qc/temporal_drift/diagnosis.py`). Per le sessioni con `temporal_internal_assessability_status != ASSESSABLE` (sia `NOT_ASSESSABLE` sia `PARTIALLY_ASSESSABLE`), i cinque campi di stima interessati -- `primary_trend_c_per_min`, `abs_primary_trend_c_per_min`, `primary_confidence_interval_low`, `primary_confidence_interval_high`, `method1_trend_c_per_min` -- vengono ora esportati come `NaN` invece del valore grezzo restituito da `method1`/`method2`. Il fix **non modifica in alcun modo la classificazione**: le regole di assessability (`TCD-NA-01`, `TCD-IR-01`, `SDI-NA-01`, tutte a priorita' 0-2) restano piu' prioritarie di quelle che leggono i campi di stima (`TCD-SUP-01`, `SDI-EXT-01`, priorita' >=10), e il motore e' first-match-wins -- per queste sessioni quelle regole non vengono quindi mai raggiunte, ne' prima ne' dopo il fix. Test di regressione aggiunti in `tests/test_temporal_diagnosis.py`: `test_estimate_fields_are_nulled_when_not_fully_assessable` (parametrizzato su `NOT_ASSESSABLE`/`PARTIALLY_ASSESSABLE`) e `test_estimate_fields_survive_when_assessable` (caso `ASSESSABLE`, valori invariati). **Gli output gia' presenti su disco in `outputs/temporal_drift/` non sono stati rigenerati** da questo fix e possono quindi ancora contenere i valori grezzi precedenti per le righe non pienamente assessable. La rigenerazione e' deliberatamente rimandata a dopo che il perimetro canonico delle campagne (attualmente in transizione da 34 a 44, si veda il punto successivo) sara' ristabilito e congelato, per non mescolare nello stesso run l'effetto di questo fix con quello, indipendente, dell'ampliamento del dataset.

## AB. Rischi di falsi negativi

- **73.5% delle campagne restano `NOT_ASSESSABLE`**: alcune di queste potrebbero nascondere un cambiamento temporale reale che i parametri attuali (raggio 15m, separazione 300s, 5 gruppi minimi) non riescono a rilevare per un tragitto punto-a-punto con pochi incroci ripetuti. La sensitivity (sezione Q) mostra che alcune configurazioni piu' permissive (raggio maggiore, separazione minore) avrebbero trovato piu' evidenza in alcuni casi -- ma selezionare quella configurazione a posteriori per "salvare" una campagna specifica violerebbe esplicitamente il principio di non scegliere soglie per ottenere il risultato desiderato. Il dato onesto resta: con la configurazione `temporal_recommended`, la maggioranza dei tragitti bici punto-a-punto in questo dataset non fornisce abbastanza ripassaggi per una diagnosi interna.
- **`INSUFFICIENT_TEMPORAL_SEPARATION` come motivo dominante (16/34)** potrebbe in parte riflettere una soglia di 300s ancora conservativa per microclima urbano a scala di isolato (dove un vero cambiamento potrebbe manifestarsi anche su ripassaggi piu' ravvicinati, es. 60-180s, gia' verificati come profilo permissivo) -- non corretto in questa fase perche' cambiare la soglia operativa *ora*, dopo aver visto quante campagne ne beneficerebbero, sarebbe esattamente la scelta a posteriori vietata dalla specifica; resta un candidato esplicito per una futura sensitivity dedicata (sezione AC).

## AC. Limiti dell'analisi interna

- Il Metodo 2 (within-estimator) non applica `minimum_temporal_separation_s` alle proprie visite (solo `visit_merge_gap_s=30s`) -- limite architetturale documentato in sezione AA, innocuo nelle diagnosi reali osservate ma da irrobustire in una fase futura (es. richiedere lo stesso pavimento di separazione anche per le visite usate dal Metodo 2, non solo per le coppie del Metodo 1).
- Il detrending sperimentale usa sempre il beta **lineare**, anche per le (rare) sessioni `POSSIBLE_NONLINEAR_BACKGROUND_CHANGE` (nessuna delle 34 campagne reali ha raggiunto questa diagnosi, quindi il limite resta teorico per ora) -- limite gia' documentato in dettaglio in sezione O.
- Il pavimento di 8 gruppi per il bootstrap cluster e' `engineering_default`, non validato su un vero caso REJECT-equivalente (nessuna delle 34 campagne ha assenza dati genuina abbastanza estrema).
- La scoperta delle campagne canoniche dipende da `outputs/session_qc/session_qc_inventory.csv` restare sincronizzato con l'insieme di campagne effettivamente coperte -- un problema reale gia' incontrato una volta in questa sessione (sezione Z, bug #4) quando un'altra sessione di lavoro ha esteso `outputs/recommended/` a 44 campagne senza aggiornare Session QC. Il fix (usare l'elenco canonico invece di scansionare la cartella) e' corretto ma dipende dal fatto che Session QC resti l'autorita' -- se in futuro si aggiornera' Session QC alle nuove campagne, questa pipeline le includera' automaticamente alla prossima run, come atteso.
- Nessuna delle 34 campagne reali ha mai raggiunto `POSSIBLE_NONLINEAR_BACKGROUND_CHANGE` ne' un vero scenario REJECT-equivalente in assessabilita' -- questi rami di codice restano validati solo su scenari sintetici (sezione Q).

## AD. Requisiti per la futura validazione Netatmo

Per trasformare `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED` (oggi solo su `02-13 09:06:57`) in una vera diagnosi di deriva strumentale servono, come minimo:
1. **Serie temporale Netatmo co-locata** per lo stesso intervallo (idealmente la stessa area urbana, non necessariamente lo stesso punto esatto) -- per confrontare il trend interno (+0.037 C/min) con un riferimento fisso non soggetto al movimento del sensore mobile.
2. **Metadati di calibrazione del sensore MeteoTracker** (data ultima calibrazione, storico di derive note per lo stesso dispositivo `AC4D162B317E`/`B6CCF894-...`) per distinguere un effetto specifico del dispositivo da un effetto atmosferico che un Netatmo indipendente confermerebbe.
3. **Piu' passaggi ripetuti nello stesso periodo** (idealmente lo stesso percorso in giorni diversi) per verificare se l'ampiezza del trend (+0.037 C/min) e' un tratto stabile del dispositivo o specifico di quella singola sessione.
4. **Nessuna azione richiesta ora**: questa fase si ferma deliberatamente qui, come da istruzione esplicita della specifica ("FERMATI DOPO LA DIAGNOSI INTERNA. Non integrare ancora Netatmo. Non dichiarare una deriva strumentale certa.").

---

# FASE 4B (2026-07-31): hardening del Metodo 2 ed estensione a 44 campagne canoniche

Le sezioni A-AD sopra restano il **baseline storico a 34 campagne** (Metodo 2 non irrobustito) e non sono state alterate. Le sezioni seguenti (AE in poi) documentano l'irrobustimento del Metodo 2, l'estensione di Session QC e Temporal Drift alle 10 nuove campagne di luglio 2026 (44 canoniche totali), e il confronto esplicito tra i tre stati: 34 campagne/Metodo 2 vecchio, 34 campagne/Metodo 2 corretto, 44 campagne/Metodo 2 corretto.

## AE. Hardening del Metodo 2

**Causa metodologica** (gia' anticipata in sezione AA/AC come rischio residuo): il Metodo 1 (mediana pesata) applica `minimum_temporal_separation_s` a livello di **coppia** in `pairs.py` (`time_diff_s < profile.minimum_temporal_separation_s` -> `EXCLUDED_INSUFFICIENT_TEMPORAL_SEPARATION`). Il Metodo 2 (within-estimator) non ha un concetto nativo di "coppia" -- pooia direttamente tutte le **visite** di qualita' OK per gruppo (`prepare_model_visits`) senza mai verificare se due visite dello stesso gruppo sono separate a sufficienza nel tempo. Una visita a 32s da un'altra nello stesso gruppo (sopra il solo `visit_merge_gap_s=30s` che le distingue come visite separate, ma ben sotto i 300s del profilo `temporal_recommended`) veniva quindi trattata come prova di contrasto temporale reale tanto quanto una separata da 20 minuti.

**Correzione**: `src/meteotracker_qc/temporal_drift/trend_methods.py`, funzione `prepare_model_visits()` (linee ~137-176). Non un filtro meccanico aggiuntivo, ma una proiezione del criterio gia' esistente di Metodo 1: una nuova funzione `_visits_with_valid_pair(pairs)` raccoglie l'insieme delle visite che compaiono in **almeno una coppia `pair_qc_status == "VALID"`** (quindi gia' passata attraverso lo stesso controllo di separazione temporale, raggio spaziale e qualita' di `pairs.py`). `prepare_model_visits()` ora richiede **congiuntamente**: qualita' OK, appartenenza a un gruppo con abbastanza visite, **e** partecipazione ad almeno una coppia temporalmente valida. Una visita puo' quindi essere di qualita' OK e comunque scartata se ogni altra visita del suo gruppo le e' troppo vicina nel tempo -- ma se in un gruppo A e' vicina a B (esclusa) e lontana da C (valida), sia A sia C restano nel modello (B viene scartata singolarmente, non l'intero gruppo).

**Configurazione**: nessuna soglia nuova. Riusa `MatchingProfile.minimum_temporal_separation_s` (`config/repeated_location_matching.csv`), lo stesso valore gia' condiviso dal Metodo 1 tramite `pairs.py` -- **Metodo 1 e Metodo 2 condividono ora esplicitamente la stessa soglia**, mai due parametri indipendenti.

**Propagazione**: `fixed_effects_ols_trend`, `fixed_effects_huber_trend`, `fixed_effects_theilsen_trend` (`trend_methods.py`) e `evaluate_nonlinear_candidate` (`nonlinear.py`, che riusa `prepare_model_visits` per il candidato quadratico) ora richiedono `pairs` come parametro esplicito. Punti di chiamata aggiornati: `temporal_drift_pipeline.py::process_campaign` (gia' aveva `pairs` disponibile), `sensitivity.py::run_single_configuration` (idem).

**Test aggiunti** (`tests/test_temporal_trend_fixed_effects.py`, `tests/test_temporal_nonlinear.py`, 17 nuovi test su 31 totali nel primo file): visite separate meno/esattamente/oltre la soglia; timestamp non ordinati; timestamp mancanti (`NaT`) gestiti senza crash; piu' visite nello stesso gruppo (solo quelle non temporalmente supportate vengono scartate, non l'intero gruppo); filtro che azzera tutte le coppie di un gruppo (Metodo 2 -> risultato vuoto/NaN, mai un crash); caso Metodo 1 valido/Metodo 2 non valutabile; caso entrambi validi; regressione di non-modifica su dati "ben separati" (nessuna differenza quando le visite reali sono gia' oltre soglia, il caso comune osservato sulle 34 campagne). Lo skip esistente (`test_direction_dependent_campaign_identified_dynamically_if_any`) resta onesto, non toccato.

## AF. Effetto quantitativo dell'hardening sulle 34 campagne originali (confronto controllato)

Per isolare l'effetto dell'hardening da quello delle 10 nuove campagne, la pipeline e' stata eseguita due volte sulle **stesse identiche 34 campagne**: una volta con il Metodo 2 vecchio (snapshot del run Fase 4 gia' esistente, salvato in `outputs/temporal_drift/_baseline_34_old_method2/` prima di essere sovrascritto), una volta con il Metodo 2 corretto (`outputs/temporal_drift_34_new_method2/`). Grouping/coppie sono **risultati identici bit-per-bit** tra i due run (17422 gruppi, 1227 validi, 18666 visite, 1261 coppie, 994 valide in entrambi) -- atteso, dato che l'hardening tocca solo il pooling interno del Metodo 2, mai `grouping.py`/`pairs.py`. Determinismo verificato anche end-to-end: le stesse 34 campagne ricomputate una terza volta dentro il run finale a 44 producono diagnosi e trend **identici bit-per-bit** ai risultati del run isolato a 34 (stesso `random_state=0` di default).

**Assessability invariata**: 25 `NOT_ASSESSABLE` / 6 `ASSESSABLE` / 3 `PARTIALLY_ASSESSABLE` prima e dopo -- atteso, perche' l'assessability (sezione G) e' calcolata da `groups`/`visits`/`pairs` grezzi, mai dal risultato del Metodo 2.

**Ma tutte e 3 le diagnosi `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` non sopravvivono**:

| Campagna | trend vecchio | trend nuovo | gruppi Metodo2 vecchio | gruppi Metodo2 nuovo | diagnosi vecchia | diagnosi nuova |
|---|---:|---:|---:|---:|---|---|
| `02-13 09:06:57` | +0.0370 | +0.0398 | 33 | **6** | `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` | `INCONCLUSIVE_TEMPORAL_EFFECT` |
| `02-13 13:23:47` | +0.0182 | +0.0184 | 26 | **7** | `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` | `INCONCLUSIVE_TEMPORAL_EFFECT` |
| `02-20 12:54:36` | -0.0017 | -0.0008 | 87 | **52** | `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` | `NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE` |

Nessun'altra diagnosi cambia (`INTERNAL_METHODS_DISAGREE` resta 2/34, `INSUFFICIENT_REVISITS` resta 3/34, `NOT_ASSESSABLE` resta 25/34) -- l'impatto e' interamente confinato alle 9 campagne dove il Metodo 2 entra davvero nella decisione (le altre 25 sono gia' `NOT_ASSESSABLE` a monte, dove la regola `TCD-NA-01` decide prima di guardare il Metodo 2).

**Causa precisa, non un artefatto**: `02-13 09:06:57` (il caso +0.037 C/min discusso in sezione U/AA) usava 33 gruppi nel Metodo 2 vecchio, ma **solo 6** di quei gruppi hanno visite genuinamente separate >=300s -- gli altri 27 erano ripassaggi troppo ravvicinati nel tempo che gonfiavano il numero apparente di evidenza indipendente. Sotto il pavimento di 8 gruppi per il bootstrap cluster (`MIN_GROUPS_FOR_BOOTSTRAP`), la CI del Metodo 2 nuovo diventa `NaN` -> `is_ci_too_wide()` la tratta come non informativa -> `CI_TOO_WIDE` -> `INCONCLUSIVE_TEMPORAL_EFFECT`. La stima puntuale del trend **non si sposta quasi per niente** (+0.037 -> +0.040 C/min): non e' il numero stimato a essere sbagliato, e' la fiducia statistica costruita su di esso a essere stata artificialmente gonfiata da falsi "ripassaggi" troppo ravvicinati. Questo e' esattamente il rischio metodologico che la sezione AA/AC di questo report aveva gia' identificato come residuo prima dell'hardening -- ora confermato empiricamente, non solo teoricamente.

`02-20 12:54:36` (il caso gia' discusso in sezione V, trend quasi nullo) perde "solo" 35/87 gruppi (resta ben sopra il pavimento di bootstrap), ma la CI si sposta da `[-0.0033, -0.00067]` (escludeva lo zero) a `[-0.0019, +0.0004]` (include lo zero) -- coerente con una stima gia' vicinissima a zero che diventa, con meno evidenza pooled, onestamente non distinguibile da nessun cambiamento.

**Detrending sperimentale**: nessuna delle 34 campagne resta eleggibile dopo l'hardening (`detrending_supported`: 3 -> 0), essendo l'eleggibilita' condizionata a una diagnosi supportata (sezione O). Il warning `SPATIAL_CONTRAST_REDUCED_EXCESSIVELY` osservato su `02-13 09:06:57` (sezione AA) **non e' piu' applicabile**: quella campagna non produce piu' alcun prodotto detrendizzato, quindi la domanda "il warning permane?" ha risposta "non si presenta piu' il caso" -- non e' stato ne' corretto ne' nascosto, semplicemente il prodotto che lo generava non esiste piu' con evidenza cosi' limitata.

Confronto riproducibile salvato in `outputs/temporal_drift/_comparison/comparison_34_old_vs_34_new_method2.csv` (per-campagna) e `outputs/temporal_drift/_comparison/volume_summary_44_new_method2.json`.

## AG. Prerequisito scoperto: Fase 1 incompleta per le 10 nuove campagne

Il contesto iniziale dichiarava "la Fase 1 e' gia' stata rieseguita sulle 44 campagne canoniche". Verificato che questo era vero **solo per il profilo `recommended`** (`outputs/recommended/`, 44 directory) -- `outputs/permissive/` e `outputs/restrictive/` avevano ancora solo 34 directory. Session QC (`session_qc_pipeline.py::load_campaign_frames`) richiede tutti e tre gli alberi per ogni campagna, quindi il tentativo iniziale di eseguire Session QC sulle 44 falliva con `FileNotFoundError` sulle 10 nuove campagne.

**Correzione**: rieseguita `pipeline.py::run_qc()` su `data/raw/` con `config/qc_permissive.yaml` e `config/qc_restrictive.yaml` (stessa procedura gia' usata per `recommended`, mai toccato `data/raw/`, esclusione dei 5 file ridondanti tramite il manifest come sempre). Verificato dopo: 44 directory in tutti e tre gli alberi, hash SHA-256 di tutti i 44 file raw canonici invariati.

## AH. Aggiornamento Session QC alle 44 campagne canoniche

Session QC rieseguito con `run_session_qc()` (che scopre le campagne enumerando `outputs/recommended/`, gia' verificato identico all'insieme canonico del manifest -- nessuna scansione incontrollata: la fonte e' la stessa gia' usata dalla Fase 3, ora aggiornata a monte). Risultato: **44 righe** in `session_qc_inventory.csv` (prima 34), nessuna anomalia.

**Confronto 10 nuove vs 34 precedenti**:

| Metrica | 34 precedenti | 10 nuove |
|---|---|---|
| `session_qc_status` | 20 `PASS_WITH_WARNINGS`, 11 `PARTIAL`, 2 `PASS`, 1 `NOT_ASSESSABLE` | 8 `PASS_WITH_WARNINGS`, 2 `PARTIAL` |
| `n_segments` (mediana) | 4.0 | 6.0 |
| `nominal_time_span_s` (mediana) | 2041s | 1814s |
| `n_raw` (mediana) | 1161 | 1242 |
| `keep_fraction_recommended` (mediana) | 0.781 | 0.747 |

Nessun `REJECT` in nessuno dei due gruppi. Famiglie di flag dominanti comparabili (`STABILIZATION_NOT_REACHED`, `LONG_GAP`, `TEMP_RATE_ANOMALIES`, `NO_CONTIGUOUS_VALID_SEGMENT`, `HIGH_GPS_FREEZE` in entrambi i gruppi, nessuna famiglia nuova o inattesa tra le 10). **Nessuna modifica di policy effettuata**: le 10 nuove campagne non hanno prodotto risultati abbastanza anomali da giustificarla, e comunque nessuna modifica di soglia e' stata considerata solo per "far tornare meglio" le nuove campagne.

## AI. Risultati Temporal Drift sulle 44 campagne canoniche

Pipeline eseguita end-to-end sulle 44 campagne (Metodo 2 corretto), scoperte da `session_qc_inventory.csv` ora aggiornato (mai una scansione grezza di `outputs/recommended/` -- `discover_canonical_campaign_ids()` non toccato, si limita a riflettere l'aggiornamento a monte). Tempo totale: 45.9 minuti (bootstrap 1000 iterazioni principali + sweep di sensitivity a 18 configurazioni x 200 iterazioni per campagna).

Volumi: **22409 gruppi spaziali** (1413 validi, 6.3%), **23844 visite**, **1458 coppie di ripassaggio** (1134 valide, 77.8%), **41 PNG diagnostici**, **44 JSON per-campagna**, **1 prodotto detrendizzato sperimentale**.

Assessability: **31 `NOT_ASSESSABLE`** (70.5%), **9 `ASSESSABLE`** (20.5%), **4 `PARTIALLY_ASSESSABLE`** (9.1%).

Diagnosi (`temporal_change_diagnosis`): `NOT_ASSESSABLE`=31 (70.5%), `INSUFFICIENT_REVISITS`=4 (9.1%), `INCONCLUSIVE_TEMPORAL_EFFECT`=3 (6.8%), `INTERNAL_METHODS_DISAGREE`=3 (6.8%), `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED`=2 (4.5%), `NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE`=1 (2.3%).

Interpretazione sensor drift: `NOT_ASSESSABLE`=35 (79.5%), `CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA`=6 (13.6%), `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED`=2 (4.5%), `NO_SPECIFIC_INSTRUMENT_EVIDENCE`=1 (2.3%). **`SENSOR_DRIFT` mai dichiarato** (invariante mantenuto, 0/44).

## AJ. Le 10 nuove campagne (luglio 2026): dettaglio

| Campagna | assessability | motivo | diagnosi | trend (C/min) | sensor_drift |
|---|---|---|---|---:|---|
| `7-22 08:42:34` (Bologna-Sasso Marconi) | `NOT_ASSESSABLE` | `NO_VALID_REVISITS` | `NOT_ASSESSABLE` | -- | -- |
| `7-22 09:17:03` (Sasso Marconi-Bologna) | `NOT_ASSESSABLE` | `INSUFFICIENT_TEMPORAL_SEPARATION` | `NOT_ASSESSABLE` | -- | -- |
| `7-22 09:49:53` (Bologna-Bologna) | `NOT_ASSESSABLE` | `INSUFFICIENT_TEMPORAL_SEPARATION` | `NOT_ASSESSABLE` | -- | -- |
| `7-22 10:41:01` (Modena-Modena) | `NOT_ASSESSABLE` | `NO_VALID_REVISITS` | `NOT_ASSESSABLE` | -- | -- |
| `7-30 07:42:44` (Bologna-Bologna) | `ASSESSABLE` | `SUFFICIENT_REVISITS` | `INTERNAL_METHODS_DISAGREE` | +0.0117 | `CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA` |
| `7-30 09:51:53` (Bologna-Modena) | `NOT_ASSESSABLE` | `INSUFFICIENT_TEMPORAL_SEPARATION` | `NOT_ASSESSABLE` | -- | -- |
| `7-30 12:17:53` (Castelfranco E.-San Giovanni in P.) | `NOT_ASSESSABLE` | `NO_VALID_REVISITS` | `NOT_ASSESSABLE` | -- | -- |
| `7-30 13:12:16` (Bologna-Bologna) | `ASSESSABLE` | `SUFFICIENT_REVISITS` | `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` | -0.0331 | `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED` |
| `7-30 16:21:46` (Bologna-Bentivoglio) | `PARTIALLY_ASSESSABLE` | `REVISITS_CONCENTRATED_IN_SPACE` | `INSUFFICIENT_REVISITS` | -- | -- |
| `7-30 21:47:28` (Bologna-Bologna) | `ASSESSABLE` | `SUFFICIENT_REVISITS` | `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` | -0.0029 | `CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA` |

6/10 restano `NOT_ASSESSABLE` (stesso pattern dominante gia' osservato sulle 34: tragitti punto-a-punto con pochi o nessun ripassaggio strutturale, coerente con la sezione T). Le 2 nuove diagnosi `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` meritano dettaglio:

- **`7-30 13:12:16`**: 61 gruppi validi, trend -0.0331 C/min (~-2.0 C/ora), CI `[-0.0481, -0.0215]` esclude nettamente lo zero, stabilita' `MODERATELY_SENSITIVE`, non dominata da un singolo gruppo -> **unica campagna delle 44 eleggibile per il detrending sperimentale**. Verificato: `conservation_flags = SPATIAL_PATTERN_PRESERVED` (correlazione raw/detrended 0.90, `between_location_variance_ratio` 1.17 -- il contrasto spaziale non solo e' preservato ma leggermente accentuato), nessun warning di over-detrending. Conservazione verificata riga per riga: 1843 osservazioni sia nel raw standardizzato sia nel prodotto detrendizzato, `temp_original_c` identica byte-per-byte a `canonical_temperature_c`, timestamp invariati. Ampiezza sopra la soglia di 0.02 C/min -> `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED`, **mai** una dichiarazione di deriva.
- **`7-30 21:47:28`**: 13 gruppi validi, trend molto piccolo (-0.0029 C/min), CI `[-0.0055, -0.0009]` esclude lo zero per un margine stretto, ma lo sweep di sensitivity classifica questa campagna `HIGHLY_SENSITIVE` -> **bloccata dal detrending** (`NOT_ELIGIBLE_SENSITIVITY_UNSTABLE`), esattamente il comportamento prudente atteso: una stima instabile sotto piccole perturbazioni di configurazione non deve produrre un prodotto derivato, anche se supera il test di significativita' interno.

Nessuna soglia e' stata modificata per accogliere questi risultati; entrambe le classificazioni derivano dalle stesse regole gia' in vigore sulle 34 campagne.

## AK. Confronto quantitativo 34 vs 44 (tabella riassuntiva)

| | 34, Metodo 2 vecchio | 34, Metodo 2 corretto | 44, Metodo 2 corretto |
|---|---:|---:|---:|
| Campagne | 34 | 34 | 44 |
| Gruppi spaziali totali | 17422 | 17422 | 22409 |
| Gruppi validi | 1227 (7.0%) | 1227 (7.0%) | 1413 (6.3%) |
| Visite | 18666 | 18666 | 23844 |
| Coppie | 1261 | 1261 | 1458 |
| Coppie valide | 994 (78.8%) | 994 (78.8%) | 1134 (77.8%) |
| PNG diagnostici | 33 | 33 | 41 |
| JSON per-campagna | 34 | 34 | 44 |
| Prodotti detrendizzati | 3 | 0 | 1 |
| `NOT_ASSESSABLE` | 25 (73.5%) | 25 (73.5%) | 31 (70.5%) |
| `ASSESSABLE` | 6 (17.6%) | 6 (17.6%) | 9 (20.5%) |
| `PARTIALLY_ASSESSABLE` | 3 (8.8%) | 3 (8.8%) | 4 (9.1%) |
| `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` | 3 (8.8%) | 0 (0%) | 2 (4.5%) |
| `INTERNAL_METHODS_DISAGREE` | 2 (5.9%) | 2 (5.9%) | 3 (6.8%) |
| `INSUFFICIENT_REVISITS` | 3 (8.8%) | 3 (8.8%) | 4 (9.1%) |
| `INCONCLUSIVE_TEMPORAL_EFFECT` | 1 (2.9%) | 3 (8.8%) | 3 (6.8%) |
| `NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE` | 0 (0%) | 1 (2.9%) | 1 (2.3%) |
| `SENSOR_DRIFT` | 0 | 0 | 0 |
| `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED` | 1 | 1 | 2 |

**Lettura**: l'aumento di campagne da 34 a 44 (colonna 3 vs colonna 2) porta 2 nuove diagnosi `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` -- entrambe da campagne genuinamente nuove (luglio 2026), verificate individualmente sopra (sezione AJ), **non** un effetto indiretto dell'hardening. L'hardening da solo (colonna 2 vs colonna 1, stesse 34 campagne) **riduce** le diagnosi supportate da 3 a 0. I due effetti vanno quindi in direzioni opposte e non vanno confusi: l'aumento di campagne aggiunge evidenza reale da percorsi nuovi; l'hardening rimuove evidenza artificialmente gonfiata dalle 34 originali. Il numero di `SENSOR_DRIFT` resta **zero in tutte e tre le colonne** -- ne' l'hardening ne' le nuove campagne autorizzano quella dichiarazione.

## AL. Verifica dei casi noti

1. **Le due sessioni brevi** (`04-27 07:28:18`, 21 righe; `07-04 09:31:26`, 91 righe): **invariate**, `NOT_ASSESSABLE` in tutti e tre gli stati (34/vecchio, 34/nuovo, 44/nuovo), stessi reason code (`SESSION_TOO_SHORT`, `NO_VALID_REVISITS`). Nessuna diagnosi forzata.
2. **Bologna-Ravenna** (`06-04 11:40:32`): **invariata**, `NOT_ASSESSABLE`/`NO_VALID_REVISITS` in tutti e tre gli stati -- zero gruppi con >=2 visite, coerente con un tragitto punto-a-punto senza ripassaggi strutturali. La valutazione preliminare della Fase 3 (`temporal_drift_assessability_preliminary=PARTIALLY_ASSESSABLE`) resta intenzionalmente distinta dalla diagnosi interna della Fase 4/4B (`NOT_ASSESSABLE`), esattamente come documentato in sezione Y.
3. **Il caso ~+0.037 C/min** (`02-13 09:06:57`): **cambia**, da `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` a `INCONCLUSIVE_TEMPORAL_EFFECT` -- non trasformato in `SENSOR_DRIFT`, causa identificata con precisione in sezione AF (27 dei 33 gruppi originali non avevano visite genuinamente separate >=300s). Test di regressione dedicato aggiunto (`test_large_trend_case_diagnosis_stable_after_method2_hardening`).
4. **`SPATIAL_CONTRAST_REDUCED_EXCESSIVELY`** (originariamente su `02-13 09:06:57`): il warning **non si ripresenta** in nessuno dei nuovi stati, perche' quella campagna non produce piu' un prodotto detrendizzato dopo l'hardening (assessability -> diagnosi non piu' supportata -> `eligible=False`). Il detrending non e' mai stato promosso nei profili QC ufficiali, ne' prima ne' ora.
5. **Nuove campagne con trend forte**: entrambe le nuove diagnosi `SUPPORTED` (sezione AJ) restano `POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED` o `CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA` -- mai `SENSOR_DRIFT` -- e sono state ispezionate singolarmente (stabilita' di sensitivity, dominanza di gruppo, conservazione del segnale) prima di essere riportate qui, non solo lette dal campo aggregato.

## AM. Nuovi rischi residui (post Fase 4B)

- **Le PNG diagnostiche non vengono ripulite tra run**: `write_all_diagnostics()` scrive solo per le campagne selezionate nel run corrente (`select_campaigns_for_diagnostics()`, che include le top-5 per numero di coppie valide), ma non elimina i file di campagne che **erano** selezionate in un run precedente e non lo sono piu'. Riscontrato concretamente in questa fase: `03-04 13:53:03` era 5a per numero di coppie valide tra le 34 campagne originali (28 coppie), ma e' stata superata da due nuove campagne di luglio (61 e 57 coppie) nel set a 44 -- il suo PNG, ormai calcolato con il Metodo 2 vecchio e su un ranking superato, sarebbe rimasto silenziosamente nella cartella `figures/` senza essere aggiornato ne' segnalato come obsoleto. Rimosso manualmente per questa run; **non corretto nel codice** (nessuna richiesta esplicita di questa fase, ma da considerare in una fase futura: `write_all_diagnostics()` dovrebbe eliminare i PNG delle campagne non piu' selezionate a inizio run).
- **Il pavimento di 8 gruppi per il bootstrap cluster del Metodo 2** (`MIN_GROUPS_FOR_BOOTSTRAP`, invariato da questa fase) e' ora dimostrabilmente il fattore decisivo in almeno 2 delle 34 campagne originali (sezione AF) -- resta `engineering_default`, non validato con una sensitivity dedicata sul pavimento stesso.
- **Le 6 campagne `NOT_ASSESSABLE` tra le 10 nuove** seguono lo stesso pattern dominante (`INSUFFICIENT_TEMPORAL_SEPARATION`/`NO_VALID_REVISITS`) gia' descritto in sezione T/AB per le 34 originali -- non un problema nuovo, ma conferma che il limite e' strutturale al tipo di percorso (punto-a-punto), non specifico del campione originale.
- **`7-30 21:47:28`** raggiunge `TEMPORAL_BACKGROUND_CHANGE_SUPPORTED` ma con stabilita' di sensitivity `HIGHLY_SENSITIVE` -- la diagnosi stessa non richiede stabilita' (solo concordanza tra metodi + CI che esclude lo zero, sezione M), mentre l'eleggibilita' al detrending si' (sezione O). Questo produce un caso limite gia' visto teoricamente ma ora osservato su dati reali: una diagnosi "supportata" che non genera comunque alcun prodotto derivato -- comportamento corretto per costruzione, ma un lettore che guardasse solo `temporal_change_diagnosis` senza `temporal_sensitivity_stability_class` rischierebbe di sovrastimarne la robustezza (stesso rischio gia' documentato in sezione AA per le campagne a basso numero di coppie).

## AN. Stato finale dei test

`pytest -q -W error`: **425 -> 447 passed, 1 skipped, 0 failure, 0 warning** (66.1s). Lo skip resta lo stesso caso onesto gia' documentato in sezione Z (nessun dato reale con direzione discorde in questo run). 22 nuovi test aggiunti per l'hardening del Metodo 2 (`test_temporal_trend_fixed_effects.py`: 12->31 test; `test_temporal_nonlinear.py`: +1 test dedicato), piu' un test di coerenza manifest/Session-QC/Temporal-Drift (`test_manifest_session_qc_and_temporal_drift_campaign_sets_agree`) e un test di regressione pinnato sul caso +0.037 C/min. Tutti i riferimenti hardcoded a "34" nei test sono stati resi dinamici (calcolati dal manifest) per non richiedere manutenzione manuale a ogni futura estensione del set canonico.

**Verifiche di integrita' finali**: hash SHA-256 di tutti i 44 file raw canonici invariati (non solo il campione di 5 gia' controllato dal test esistente); nessun ID di campagna duplicato in nessun output; i 5 file ridondanti non compaiono mai come `source_file` in alcun output (il loro `canonical_campaign_id` compare, correttamente, una sola volta -- condiviso con la campagna canonica di cui sono un duplicato di contenuto); determinismo confermato bit-per-bit sulle 34 campagne comuni tra il run isolato e il run finale a 44.
