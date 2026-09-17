# Gate 2.1 — punto di ripresa, 16 settembre 2026

## Stato conclusivo — Gate 2.1 completato

**PASS_WITH_WARNINGS; GO tecnico al commit del solo Gate 2.1.** Rapporto autorevole:
[GATE_2_1_STATUS.md](GATE_2_1_STATUS.md). Guida: [SESSION_ANALYSIS.md](SESSION_ANALYSIS.md).

Implementazione completa, 36 test mirati superati; suite workspace 572 passed e
1 skipped, candidato isolato da HEAD più 22 file Gate 2.1 **564 passed**, tutti
con `-W error`. Validazione GUI reale su 44 sessioni, preview singola e multipla,
mappa originale automatica, spazio 1280×720 e 853×480, sei CSV nuovi non applicati.

Durante il lavoro l'utente ha confermato una rigenerazione intenzionale separata
dei prodotti ufficiali. La baseline iniziale è conservata e le differenze sono
documentate. Ripetuta la preview dopo tale aggiornamento: **4518 file protetti
invariati** prima/dopo, raw/manifest/configurazioni invariati anche dall'inizio.

Nessun apply ufficiale da questo lavoro, staging, commit, push, executable o
installer. Gate 3 non iniziato. Processi di verifica conclusi; GUI preesistente
dell'utente preservata. Le sezioni sotto sono soltanto lo storico delle pause,
superato dal rapporto conclusivo.

---

## Storico — seconda pausa richiesta dall'utente

Alla seconda pausa questa sezione sostituiva lo stato della prima tranche.
Lo stato di allora era: **Gate ancora incompleto; NO-GO al commit e Gate 3**.
È ora superato dallo stato conclusivo sopra.

Nella seconda tranche sono stati aggiunti:

- `session_analysis.py`: mixin di `ApplicationService` con elenco e ispezione dal manifest,
  filtri, tre vere esecuzioni di profilo, configurazione custom, preset con fingerprint,
  Session QC/metriche/suitability e eligibility tramite funzioni esistenti, confronto,
  preview in temp, cancellazione e cleanup, export confinati a `outputs/custom_analyses`.
- `map_preview.py`: caricamento originale senza QC, CRS dalla configurazione, indicatori
  preliminari, tracce separate/colori deterministici, confine locale opzionale, rendering
  metrico offline, densità/sovrapposizioni esplorative, decimazione solo grafica, export GIS.
- `analysis_plots.py`: grafici riproducibili di temperatura, velocità, flag e prima/dopo.
- `gui/session_analysis.py`, `gui/route_map.py`, `gui/analysis_worker.py`: finestra dedicata,
  stesso service della principale, selezione, gruppi/soglie/preset, mappa automatica in worker,
  risultati obsoleti ignorati, zoom/pan/picking, confronto/export, chiusura con conferma.
- `gui/log_panel.py`: tabella leggibile, filtri, copia, salvataggio e dettagli JSON.
- `gui/window.py`: pulsante visibile, istanza unica, passaggio workspace/service e log nuovo.
- `cli.py`: `sessions list/inspect/qc/compare`, profili/preset/controlli/export opzionale.
- `tests/test_session_analysis.py` e `tests/test_session_analysis_gui.py`.

Validazione effettuata in questa tranche:

1. Test application/map/CLI sintetici: **11 passed in 31.14s**, con `-W error`.
   Comando: `.venv/Scripts/python.exe -m pytest tests/test_session_analysis.py -W error -q
   --basetemp .gate21_audit/pytest_service -o cache_dir=.gate21_audit/pytest_cache`.
2. Primo tentativo GUI: ambiente `.venv` privo di `pytest-qt` e problemi di decodifica dei
   subprocess Windows senza `PYTHONUTF8=1`. Installato offline `pytest-qt==4.5.0` e
   `typing_extensions==4.16.0` dal wheelhouse locale del Gate 2; nessun download o modifica
   a pyproject/requirements. Impostare `PYTHONUTF8=1`, `QT_QPA_PLATFORM=offscreen` nei test.
3. Secondo tentativo GUI/compatibilità **interrotto su richiesta di pausa**, nessun PASS.
   Output parziale `.gate21_audit/gui-tests.log`: `.....F...........`.
   Il sesto test nuovo è `test_geometry_persist_and_720p_layout`: **probabile failure del
   layout minimo a 853×480**, da rieseguire con `-x -vv --tb=long` per il traceback.
   Non interpretare la lentezza come prova di deadlock: il log era bufferizzato e al termine
   forzato mostrava avanzamento nei test della GUI esistente.
   Interrotti solo i PID di questa esecuzione pytest (7764 e 39868, avvio 14:47:05),
   non la GUI preesistente dell'utente. Il codice di uscita della shell era quello
   del successivo Get-Content: **non è un risultato pytest positivo**.
4. `git diff --check`: nessun errore di whitespace, soltanto avvisi CRLF preesistenti.
5. `.gate21_audit/integrity_pause_2.json`: **tutti i 4459 file protetti invariati**
   rispetto a `integrity_before.json`; stessi hash aggregati riportati sotto.

Alla prossima ripresa:

- Ricontrollare Git/processi/hash; le modifiche sono locali, non in staging.
- Diagnosticare prima il test layout/geometria, poi completare i test GUI e la suite intera.
- Raffinare e rivedere il codice nuovo prima di considerarlo completo: dimensioni minime
  di controlli/toolbar/splitter a 125–150%; tooltip soglie aggiornati dopo modifica custom;
  flag disabilitati indicati esplicitamente come non valutati; cleanup e incoerenze di
  selezione/risultati durante refresh; esportazione dei keep realmente distinti per profilo;
  export CRS e provenienza; decimazione con primo/ultimo fix valido esatti.
- Aggiungere test ancora mancanti per confine valido/invalido e CRS differenti, export e
  cancellazione su errore, ciclo completo GUI, filtri e log generali, integrità many-to-many.
- Eseguire validazione reale GUI su 44 sessioni (elenco + una + più), SOLO preview; sei CSV
  nuovi restano non applicati. Non è ancora stata eseguita nessuna preview reale.
- Produrre documentazione utente e rapporto finale completo con hash e limitazioni.

Nessun apply ufficiale, staging, commit o push. Nessun Gate 3 / executable / installer.

---

Lavoro sospeso su richiesta dell'utente per riprendere nel pomeriggio.
Il Gate 2.1 **non è completo**: nessuna dichiarazione di PASS e NO-GO al commit
finché implementazione e verifiche richieste non saranno complete. Gate 3 non iniziato.

## Vincoli persistenti

- Workspace `D:\projects\Meteotracker`.
- Branch `feat/meteotracker-windows-app`, HEAD `f404ae3587033835285be87b5a633dd821938e47`.
- Non usare reset, checkout, clean, stash, rebase o amend.
- Non modificare raw, manifest, output ufficiali, cache ufficiali o soglie scientifiche predefinite.
- Non applicare 8-1 / 9-8. Nessun apply ufficiale, staging, commit, push, executable o installer.
- Preservare tutte le modifiche preesistenti: Git era già ampiamente dirty.
- Nessun sub-agent avviato. L'ultima integrazione chiede ragionamento Ultra;
  non è stato effettuato né dichiarato un cambio di impostazione del modello.

## Richieste autorevoli salvate

- `.gate21_audit/request_original.txt`: richiesta completa iniziale, inclusi test e rapporto finale in 19 punti.
- `.gate21_audit/request_map_extension.txt`: integrazione cartografica completa.
- Correzione intermedia: **non aggiungere una tab di analisi alla finestra principale**.
  Aggiungere il pulsante visibile `Analizza sessioni`, che apre una sola istanza di
  `SessionAnalysisWindow`, con la stessa workspace e lo **stesso oggetto ApplicationService**.
  Finestra indipendente, ridimensionabile/massimizzabile, geometria persistente,
  conferma di chiusura durante analisi attiva, ritorno alla principale senza perdere progetto.
  Splitter per elenco/filtri, gruppi/profili, soglie; area inferiore con Riepilogo,
  Flag, Serie temporali, Mappa, Confronto, Export, Log. Test espliciti su questi contratti.
- La mappa deve comparire automaticamente alla selezione **prima di qualsiasi QC**:
  centrale e interattiva, offline, partenza/arrivo/direzione, discontinuità, punti e tooltip,
  colori deterministici, tracce nascondibili, identità separate, densità esplorativa,
  confine Bologna se configurato e valido, CRS geografico/metrico corretti, worker e
  risultati obsoleti ignorati, decimazione solo grafica, confronto prima/dopo e export separato.

## Modifiche realizzate (fondazioni, non funzionalità completa)

- Nuovo `src/meteotracker_qc/analysis_settings.py`: catalogo dei gruppi derivato dai
  detector esistenti, profili, contratto esplicito di parametri modificabili/unità/intervalli,
  configurazione runtime, differenze, fingerprint e payload preset versionato.
- Hook opt-in nei detector `time_qc.py`, `gps_qc.py`, `meteo_qc.py`,
  `stabilization.py`, `ventilation_qc.py`. Controlli applicati nel motore prima delle
  policy/eligibility; nessuna colonna rimossa dopo il QC. Default esistenti conservati.
- `pipeline.py`: cancellazione cooperativa a confini di fase, diagnostici opzionali,
  possibilità di disattivare variabili derivate in runtime.
- `tests/test_analysis_settings.py`: 13 test sintetici per profili/default intatti,
  validazione parametri e unità, differenze/preset, effetti dei controlli su flag e keep.

Non sono ancora implementati: application layer per sessioni, preview isolata,
lettura/validazione e salvataggio preset, finestra separata, anteprima mappa,
visualizzazioni/comparazioni/export, log leggibile, CLI sessions, test GUI nuovi.

## Evidenze di validazione al punto di pausa

Comando eseguito:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analysis_settings.py tests/test_time_qc.py tests/test_gps_qc.py tests/test_meteo_qc.py tests/test_stabilization.py tests/test_ventilation_qc.py tests/test_pipeline_integrity.py tests/test_keep_contract.py -W error -q --basetemp .gate21_audit/pytest_tmp -o cache_dir=.gate21_audit/pytest_cache
```

Risultato: **99 passed, 1 skipped in 18.80s**. Suite completa e nuovi test GUI ancora da eseguire.

Hash per file e hash aggregati registrati in `.gate21_audit/integrity_before.json`
e confrontati con `.gate21_audit/integrity_pause.json`: **tutti invariati**.

| Gruppo | File | SHA-256 aggregato iniziale = pausa |
|---|---:|---|
| raw | 56 | `60f46f443f9067810451e07ea59229c0cde6ffcb4f27181ae59ac179abc1d8c7` |
| manifest | 3 | `748e769e9172037ffd3f41153a181af8436247cd6d674484d1e7a9f819690b5b` |
| output ufficiali | 4380 | `ca59839394454a392481f1befadb1b4d660a1ec2ab5afcb06ef300bbb537844a` |
| configurazioni scientifiche | 20 | `ac6dad42f005aea9f16aca8355fd95230d351c6007369d693607e2c365b6d74e` |

Sono salvati anche Git iniziale/pausa, stato sessioni/nuovi CSV e processi.
`Get-CimInstance Win32_Process` negato dal sistema; usato `Get-Process` come fallback.
Rilevata una GUI esistente (`meteotracker-gui` PID 43272 e processi Python associati),
non avviata né terminata da questo lavoro. Nessun lock applicativo rilevato al controllo.
Prima di riprendere ricontrollare processi, Git e hash: l'utente può lavorare nel frattempo.

## Note tecniche per la prosecuzione

1. `ApplicationService` in `application.py` è condiviso da CLI e GUI; la GUI usa
   `gui/worker.py` e `CancellationToken`. Il worker di analisi deve usare lo stesso service
   senza mutarne token/callback globali durante operazioni concorrenti.
2. Sessioni dal manifest, canonical ID unico; escludere re-export senza doppio conteggio.
   Non dedurre sessioni dalle cartelle. Arricchire da inventari ufficiali solo in lettura.
3. `MeteotrackerQC.process_file` produce frame e output per singolo CSV.
   I tre `keep_*` di un singolo frame sono **proiezioni della policy**, non tre vere
   esecuzioni con soglie diverse. Per confronto reale eseguire i tre profili separatamente.
4. Riutilizzare `session_qc.metrics` (`build_reference_frame`, `compute_segment_metrics`,
   `compute_session_metrics`), `session_status`, `segment_status`, `suitability`.
   La pipeline Session QC attuale usa recommended come riferimento. Indicarlo chiaramente.
5. Schema, distanza e completezza sono metriche/prerequisiti obbligatori nel catalogo;
   coordinate non valide/AOI è dichiarato non disponibile, non inventare un detector.
   Parsing e segmentazione strutturale restano necessari anche disabilitando relativi flag.
6. `analysis_settings.py` è iniziale: rivedere dipendenze (es. warm-up/ventilazione),
   semantica dei controlli disabilitati e unità nei test completi. Non presentare un
   controllo disattivato come verificato con esito positivo. Validare preset incompatibili.
7. Visualizzazione con stack già installato (matplotlib/pyproj/Qt) per evitare nuove
   dipendenze pesanti; nessuna modifica alla logica many-to-many/repeated routes.
8. Preview in directory temporanea con provenienza e snapshot; export solo sotto
   `outputs/custom_analyses/<analysis_id>/`, senza sovrascritture e senza promozione ufficiale.
9. Test portabili sintetici. Poi prova reale su 44 campagne elencate, una e più selezioni;
   sei nuovi CSV devono restare nuovi. Confrontare nuovamente tutti gli hash iniziali/finali.

Nessuna analisi ufficiale o preview reale è stata eseguita in questa prima tranche.
