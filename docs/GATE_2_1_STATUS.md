# METEOTRACKER_SESSION_ANALYSIS_GUI_STATUS

**PASS_WITH_WARNINGS.** Rapporto conclusivo: 17 settembre 2026;
verifiche eseguite il 16 settembre 2026.

Implementazione e verifiche concluse. Le avvertenze riguardano i limiti scientifici
espliciti al punto 17 e l'aggiornamento intenzionale separato degli output ufficiali,
confermato dall'utente. La preview ripetuta dopo tale aggiornamento ha lasciato
invariati tutti i 4518 file protetti.

Branch `feat/meteotracker-windows-app`; HEAD invariato
`f404ae3587033835285be87b5a633dd821938e47`.
Guida operativa: [Analisi delle sessioni](SESSION_ANALYSIS.md).

## 1. Architettura

Il pulsante **Analizza sessioni** della finestra principale apre
`SessionAnalysisWindow`, finestra separata che riceve la stessa workspace e lo
stesso oggetto `ApplicationService`. Un secondo clic riattiva la medesima istanza.
Navigazione indipendente, ritorno alla principale, dimensione/posizione persistenti,
ridimensionamento/massimizzazione e conferma di chiusura durante un'operazione.

Splitter separano selezione, profilo/gruppi e soglie. In basso: Riepilogo, Flag,
Serie temporali, Mappa, Confronto, Export e Log. Il pulsante **Pannelli QC** espande
la mappa. L'analisi completa non è una tab della principale.

`SessionAnalysisService` integra l'application layer tramite un mixin; GUI e CLI
richiamano le stesse operazioni. I widget non implementano detector scientifici.
Token e callback sono propri di ogni operazione, senza sostituire quelli del
servizio condiviso. Worker Qt, cancellazione cooperativa e identificativi delle
richieste impediscono di mostrare risultati asincroni obsoleti.

## 2. Sessioni disponibili

**44 campagne canoniche**, derivate dal manifest; re-export esclusi e nuove
acquisizioni non diventano sessioni aggiuntive. I sei CSV nei batch `8-1` e `9-8`
restano nuovi. La lista espone ID, sorgente, batch, orari, righe, durata, distanza,
Session QC, suitability e disponibilità degli output.

Selezione singola/multipla, seleziona visibili, deseleziona tutto, ricerca per
ID/nome, filtri data/batch/stato. Una selezione nascosta da un filtro resta
esplicitamente selezionata; le cartelle non definiscono l'identità delle sessioni.

## 3. Controlli QC esposti

Catalogo di **20 gruppi**, di cui 16 commutabili: timestamp, duplicati,
monotonicità, gap, coordinate mancanti, salti GPS, freeze/stazionarietà,
velocità, accelerazione, temperatura/plausibilità, umidità, pressione, warm-up,
ventilazione/soste, variabili derivate e suitability.

Schema, distanza e completezza restano prerequisiti/metriche obbligatori.
Coordinate non valide/AOI è dichiarato non disponibile perché manca un detector
autonomo nel motore esistente. Descrizioni, soglie, unità, origine e profilo sono
consultabili; un dialogo espone anche le regole Session QC/suitability effettive.
Le checkbox raggiungono i detector prima delle policy. I flag disabilitati sono
marcati **Disattivato**, non trattati come controlli superati.

## 4. Profili

Recommended, Permissive, Restrictive e Personalizzato. Il confronto standard
esegue realmente le tre configurazioni; non usa le tre proiezioni di policy di
un solo frame come se fossero tre esecuzioni distinte. Gli YAML predefiniti
restano invariati.

## 5. Configurazione personalizzata

Configurazione runtime derivata da un profilo, controlli disabilitati e differenze
espliciti, ripristino e whitelist di parametri modificabili. Validazione di tipi,
unità, intervalli e relazioni tra soglie. Preset separati in `user_presets/`,
con nome, descrizione, data, origine, controlli, override, versione schema e
fingerprint; incompatibilità o contenuti malformati sono rifiutati.

## 6. Preview read-only

La modalità è indicata nella finestra. L'analisi legge i dati sorgente e scrive
soltanto in una directory temporanea, con configurazione/provenienza e verifica
degli hash degli input. Chiusura, cancellazione ed eliminazione esplicita ripuliscono
l'anteprima. Un export è un'operazione separata e non promuove risultati ufficiali.

Il Session QC standard riusa il riferimento recommended e le tre maschere reali.
Per un risultato custom, le metriche usano la maschera custom nei tre slot interni;
il confronto con i tre profili standard resta separato. La policy di classificazione
rimane `recommended_session`; la scelta è dichiarata nel rapporto.
L'eligibility riusa preparazione tracce e inventario senza lanciare matching/cache.

## 7. Visualizzazioni

Mappa originale automatica alla selezione, prima del QC: tracce separate, colori
deterministici, partenza/arrivo, frecce, punti sospetti, discontinuità, legenda e
visibilità individuale. Zoom/pan, selezione/hover con dettagli del punto, confine
locale di Bologna quando valido, griglia metrica, scala e nord della griglia.
Funziona offline; nessuna nuova libreria cartografica o basemap di rete.

CRS letto dalla configurazione: nella workspace EPSG:4326 → EPSG:32632. La
decimazione riguarda soltanto il rendering e conserva estremi/segmenti; statistiche,
QC ed export usano tutti i punti. Densità dei punti e sovrapposizioni a celle di
50 m sono esplorative, distinte dai prodotti scientifici ufficiali.

Dopo il QC: tutti i punti, mantenuti, flaggati, famiglia e prima/dopo. La scelta
di un flag/famiglia evidenzia i punti; gli esclusi restano recuperabili.
Serie temporali di temperatura, velocità, flag e confronto prima/dopo.

## 8. Confronto sessioni

Tabella con orari, righe, durata, distanza, percentuale valida, flag, temperatura,
velocità, suitability ed eligibility. Nessuna fusione implicita delle osservazioni.
Conteggi per famiglia come unioni di righe, senza sommare più volte lo stesso punto.

## 9. Export

Nuova directory `outputs/custom_analyses/<id>/` per ogni export: CSV flagged,
strict/relaxed, keep dei tre profili realmente eseguiti, Parquet, GeoPackage,
GeoJSON, Markdown, JSON, configurazioni e PNG. Provenienza sempre inclusa.
La mappa originale è esportabile anche prima del QC con CRS e legenda/configurazione.
Percorsi deviati tramite link sono rifiutati; errori di export ripuliscono la
directory parziale. Il salvataggio libero della toolbar cartografica è disabilitato.

## 10. Log

Tabella con ora, livello, fase, sessione, messaggio e avanzamento; filtri per
livello/sessione, copia e salvataggio. **Dettagli tecnici** espande il JSON completo.
La principale mantiene il log generale e la finestra dedicata il log dell'analisi.

## 11. CLI equivalente

`meteotracker sessions list`, `inspect <id>`, `qc <id1> <id2>` e
`compare <id1> <id2>` condividono il servizio applicativo. Filtri, profilo,
controlli disabilitati, preset ed export sono disponibili dove pertinenti.
Senza export il rapporto viene restituito e l'anteprima temporanea rimossa.
Esempi completi nella [guida](SESSION_ANALYSIS.md#cli-equivalente).

## 12. File del Gate 2.1

I **22 file** di implementazione/test/guida sono elencati con SHA-256 in
[`gate21-scope.json`](../.gate21_audit/gate21-scope.json), usato anche per costruire
il candidato isolato da HEAD:

| Area | File |
|---|---|
| Application/CLI | `src/meteotracker_qc/application.py`, `cli.py`, `analysis_settings.py`, `session_analysis.py` |
| Motore | `gps_qc.py`, `meteo_qc.py`, `pipeline.py`, `stabilization.py`, `time_qc.py`, `ventilation_qc.py` sotto `src/meteotracker_qc/` |
| Visualizzazioni | `src/meteotracker_qc/map_preview.py`, `analysis_plots.py` |
| GUI | `src/meteotracker_qc/gui/window.py`, `analysis_worker.py`, `log_panel.py`, `route_map.py`, `session_analysis.py` |
| Test | `tests/test_application.py`, `test_analysis_settings.py`, `test_session_analysis.py`, `test_session_analysis_gui.py` |
| Guida | `docs/SESSION_ANALYSIS.md` |

Documenti aggiuntivi: questo rapporto e `docs/GATE_2_1_RESUME.md`. Evidenze e
script di verifica sono locali in `.gate21_audit/` e non fanno parte del candidato.

Le modifiche preesistenti e quelle del lavoro separato su catalogo/provenienza,
inventari e prodotti ufficiali sono preservate e non incluse nel candidato Gate 2.1.
Non sono stati modificati requirements o configurazioni scientifiche da questo lavoro.

## 13. Test mirati

**36 passed in 31.40 s**, con `-W error`: 13 casi impostazioni, 16 application/map/CLI,
7 test GUI che raggruppano apertura/istanza unica, passaggio workspace/servizio,
indipendenza, selezioni/filtri, profili, mappa automatica, stale results, rendering,
chiusura/conferma/cancellazione, persistenza geometria e log.
Fixture sintetiche, percorsi con spazi/Unicode, preset incompatibili, input modificati,
export completi e falliti, CRS geografico/metrico, confine valido/assente/invalido,
decimazione, mantenimento estremi e preview senza rete.

Evidenze: [`targeted-final.log`](../.gate21_audit/targeted-final.log),
[`targeted-final.xml`](../.gate21_audit/targeted-final.xml).
In precedenza: 99 passed e 1 skipped nei detector e contratti del motore.

## 14. Suite completa

Workspace: **572 passed, 1 skipped in 407.12 s**, con `-W error`.
Il caso saltato richiede un raw storico e l'opzione esplicita `--real-data`.
Incluse regressioni scientifiche, many-to-many, assenza di doppio conteggio,
transazioni sintetiche e compatibilità della GUI esistente.

La prima esecuzione completa aveva un solo fallimento: l'elenco esatto dei comandi
CLI non includeva ancora `sessions`. Aggiornato il contratto atteso, la suite finale
è interamente verde. Nessun fallimento è stato mascherato o trasformato in skip.

Candidato isolato da `git archive HEAD` più i soli 22 file del Gate:
**564 passed in 431.18 s**, con `-W error`, nessun failure o skip.
Non usa le modifiche estranee al Gate presenti nella workspace. Gli SHA-256 dei
22 file correnti coincidono con quelli del candidato sottoposto a test.

Ambiente: Python 3.14.5, pytest 9.1.1, PySide6/Qt 6.11.2, pytest-qt 4.5.0;
`PYTHONUTF8=1`, `QT_QPA_PLATFORM=offscreen`, `MPLBACKEND=Agg`.
`pytest-qt` e `typing_extensions` mancanti sono stati installati dal wheelhouse
locale, senza download. Nessun raw privato necessario alla suite portabile.

```powershell
$env:PYTHONUTF8='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
.venv/Scripts/python.exe -u -m pytest -vv -W error --tb=short --basetemp .gate21_audit/pytest_full_final -o cache_dir=.gate21_audit/pytest_cache --junitxml=.gate21_audit/full-final.xml
```

Evidenze: [`full-final.log`](../.gate21_audit/full-final.log),
[`full-final.xml`](../.gate21_audit/full-final.xml),
[`isolated-suite.log`](../.gate21_audit/isolated-suite.log),
[`isolated-suite.xml`](../.gate21_audit/isolated-suite.xml).

## 15. Validazione reale

GUI offscreen sulla workspace reale, stesso servizio della principale, `apply`
bloccato nello script di verifica. Elenco di 44 sessioni, mappa originale prima
del QC, selezione singola e poi multipla, worker responsivo, chiusura e cleanup.
Layout controllato a 1280×720 e 853×480 logici (spazio equivalente a 150% su 720p).
Questo verifica la disponibilità dello spazio; non è una certificazione su ogni
monitor Windows o configurazione multi-monitor.

| Sessione, inizio UTC | Righe | Keep permissive | Keep recommended | Keep restrictive | Distanza osservata |
|---|---:|---:|---:|---:|---:|
| 03-04, 2026-03-04 08:41:51 | 2101 | 2101 | 1913 | 1640 | 7.132 km |
| 05-27, 2026-05-27 13:08:42 | 2053 | 2053 | 1729 | 312 | 26.578 km |

4154 osservazioni complessive, mantenute distinte per sessione. Entrambe eleggibili
al route matching secondo l'inventario esistente. Il conteggio dei punti con almeno
un flag non equivale al conteggio degli esclusi: alcune segnalazioni sono informative.
I sei CSV di `8-1`/`9-8` rimangono nuovi e non applicati.

Ripetizione finale dopo l'aggiornamento esterno degli output: **PASS**. Completate
entrambe le preview, 869 tick del timer GUI durante il ciclo di verifica,
directory temporanee eliminate e sei CSV ancora nuovi.
Evidenze: [`real-validation.json`](../.gate21_audit/real-validation.json),
[`log`](../.gate21_audit/real-validation.log),
[mappa originale](../.gate21_audit/real-single-original.png),
[confronto multiplo](../.gate21_audit/real-multiple-qc.png),
[layout ridotto](../.gate21_audit/real-150percent-layout.png).

## 16. Integrità e aggiornamento esterno

Gli hash iniziali sono conservati, senza sostituire la baseline. L'utente ha
confermato esplicitamente una rigenerazione intenzionale separata degli output
Session QC/repeated routes/catalogo. Il log ufficiale registra il completamento
alle 23:07 del 16 settembre. Questi file sono stati preservati.

| Gruppo | File iniziali → aggiornati | SHA-256 iniziale | SHA-256 aggiornato |
|---|---:|---|---|
| raw | 56 → 56 | `60f46f443f9067810451e07ea59229c0cde6ffcb4f27181ae59ac179abc1d8c7` | identico |
| manifest | 3 → 3 | `748e769e9172037ffd3f41153a181af8436247cd6d674484d1e7a9f819690b5b` | identico |
| output ufficiali | 4380 → 4439 | `ca59839394454a392481f1befadb1b4d660a1ec2ab5afcb06ef300bbb537844a` | `a5803198547fa6ef627658e9e001af0718a0ef6a86fb9b9ab0e05591a784daec` |
| configurazioni scientifiche | 20 → 20 | `ac6dad42f005aea9f16aca8355fd95230d351c6007369d693607e2c365b6d74e` | identico |

Rispetto all'inizio: **59 output aggiunti, 80 modificati, 0 rimossi**. Non è
quindi corretto dichiarare tutti gli output invariati per l'intera giornata.
L'elenco completo e gli hash per file sono registrati negli snapshot.

Una nuova fotografia dopo il completamento del lavoro esterno delimita la
ripetizione della preview GUI, senza cancellare l'evidenza iniziale.
Confronto prima/dopo questa validazione: **PASS**, tutti i **4518 file protetti
invariati**, nessuna aggiunta, rimozione o modifica. Gli hash finali coincidono
con la colonna "aggiornato" della tabella. Questa verifica dimostra l'integrità
della preview sullo stato aggiornato; non annulla le differenze intenzionali
rispetto alla baseline iniziale della giornata.

Evidenze: [`baseline iniziale`](../.gate21_audit/integrity_before.json),
[`stato aggiornato prima della preview`](../.gate21_audit/integrity_updated_before.json),
[`stato finale`](../.gate21_audit/integrity_final.json),
[`verifica conclusiva`](../.gate21_audit/final-verification.json).
Hash aggregato: SHA-256 del JSON ordinato della mappa percorso relativo → SHA-256
del file. Inventari completi, incluse aggiunte/rimozioni e cache ufficiali;
esclusi soltanto gli export custom dal gruppo output ufficiali.

## 17. Limiti dichiarati

- Nessun detector autonomo nuovo per coordinate non valide/AOI; prerequisiti
  strutturali obbligatori e dipendenze del warm-up restano attivi.
- La densità rappresenta punti campionati, non un conteggio scientificamente
  validato dei passaggi; sovrapposizioni esplorative, nessun nuovo matching.
- Session QC custom usa la maschera runtime con policy `recommended_session`;
  non introduce nuove policy scientifiche di sessione.
- Cancellazione cooperativa ai confini di fase; il detector corrente può dover
  terminare prima della chiusura. Il dettaglio GUI limita a 500 righe, l'export è completo.
- Nessun GIS generale, basemap online o verifica di packaging/PyInstaller in questo Gate.
- La workspace include lavoro estraneo: il candidato validato è delimitato
  dall'elenco dei 22 file, non dall'intero stato Git dirty.

## 18. Operazioni non eseguite

Questo lavoro non ha eseguito apply sulla workspace ufficiale, staging, commit,
push, executable o installer. Nessuna applicazione dei sei CSV nuovi. HEAD
invariato. I test delle transazioni usano soltanto workspace sintetiche protette
dal controllo `OFFICIAL APPLY FORBIDDEN`. La GUI preesistente dell'utente non è
stata terminata. La rigenerazione esterna è registrata separatamente al punto 16.

## 19. Decisione

**GO tecnico per il commit del solo Gate 2.1**, delimitato dai 22 file del candidato
e dalla relativa documentazione, preservando il lavoro separato. Nessun commit
è stato eseguito; staging vuoto e HEAD invariato alla verifica finale.

**Gate 3 non iniziato.** Il Gate 2.1 è pronto come prerequisito tecnico; build
portable, executable e installer restano a una successiva richiesta dopo il commit.
Nessuna operazione di test o validazione di questa sessione è rimasta in esecuzione.
