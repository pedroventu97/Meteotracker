# Integration Guide

> Stato della guida: verificata sulla struttura locale il 27 luglio 2026.

## 1. Ruolo del progetto

Questo progetto conserva i CSV originali Meteotracker e applica una pipeline QC
deterministica e reversibile. I profili disponibili sono `permissive`,
`recommended` e `restrictive`; `recommended` è il default scientifico consegnato
all'integrazione.

## 2. Confini di responsabilità

- I raw restano in `data\raw`.
- QC e output standardizzati sono prodotti qui.
- L'integrazione legge `outputs\recommended`, non ripete la pulizia e non modifica raw.
- `source_file`, `source_row` e `campaign_id` devono sopravvivere al processing.

## 3. Input principali

Salvare ogni nuovo CSV scaricato dal server direttamente in:

```text
D:\projects\Meteotracker\data\raw
```

Conservare il nome server originale. Prima di salvare:

```powershell
Test-Path .\data\raw\<nome-file>.csv
Get-ChildItem .\data\raw -Filter *.csv | Select-Object Name,Length,LastWriteTime
```

Non sovrascrivere. Un re-export va conservato con il proprio nome originale e poi
classificato nel manifest di campagna; non cancellare il precedente.

## 4. Output principali

Ogni campagna genera sotto `outputs\recommended\<campaign_id>\`:

- standardized Parquet;
- CSV flagged, strict e relaxed;
- `config_used.yaml`;
- `*_metrics.json` e report;
- diagnostica grafica.

`outputs\recommended\inventory.csv` inventaria tutti i raw rilevati.

## 5. Struttura rilevante

```text
data\raw\
data\manifests\campaign_manifest.csv
config\qc_{permissive,recommended,restrictive}.yaml
src\meteotracker_qc\
outputs\recommended\
outputs\sensitivity\
run_qc.py
tests\
```

## 6. Avvio in VS Code

```powershell
cd D:\projects\Meteotracker
code .
.\.venv\Scripts\Activate.ps1
```

## 7. Workflow operativo ordinario

Per nuove acquisizioni usare l'entry point transazionale documentato nel README:

```powershell
python ingest_acquisition.py --campaign <cartella_acquisizione> --check
python ingest_acquisition.py --campaign <cartella_acquisizione> --apply
```

Il matching repeated-routes ordinario e' incrementale e riusa le coppie storiche
validate tramite chiavi SHA-256 di raw, configurazioni, algoritmi, CRS e dipendenze
geometriche. Il consolidamento, spatial density e temporal drift sono comunque
ricostruiti globalmente. Per il rebuild/backfill esplicito usare:

```powershell
python ingest_acquisition.py --campaign <cartella_acquisizione> --apply --full-rebuild
```

Il report di ingestione espone hit/miss della cache. Se sensitivity e figure non
sono state rigenerate, `outputs/repeated_routes/stale_artifacts.json` lo dichiara
insieme al comando di rigenerazione.

Il secondo comando aggiorna anche Session QC/suitability e gli aggregati dipendenti;
non sostituisce né modifica mai i CSV raw.

CLI verificata con `python run_qc.py --help`. Il comando recommended elabora i raw
canonici; quelli marcati ridondanti nel manifest vengono esclusi:

```powershell
python run_qc.py `
  --input data/raw `
  --output outputs/recommended `
  --config config/qc_recommended.yaml
```

Lo stesso comando scopre uno o più CSV. `--include-all-files` è riservato alla
riproduzione dell'audit e include anche re-export ridondanti.

Test leggeri:

```powershell
python -m pytest -q
```

Controlli dopo QC:

```powershell
Get-ChildItem .\outputs\recommended
Get-ChildItem .\outputs\recommended\<campaign_id>
Get-Content .\outputs\recommended\<campaign_id>\*_metrics.json
```

## 8. Passaggio all'integrazione

```text
server
→ data\raw Meteotracker
→ run_qc.py
→ outputs\recommended
→ manifest dell'integrazione
→ analisi integrate
```

```powershell
cd D:\projects\bologna_urban_climate_integration
python scripts\build_meteotracker_manifest.py --dry-run
python scripts\build_meteotracker_manifest.py
```

Il manifest registra percorso output, file sorgente, righe, periodo UTC, profilo e
versione QC quando disponibile, dimensione e SHA-256. Una seconda esecuzione è
incrementale:

- `new_imports=0`: nessun nuovo output valido;
- `output_modified`: checksum diverso per una campagna già indicizzata; non viene
  sovrascritto il record storico.

Una rigenerazione intenzionale richiede una decisione documentata: creare una nuova
versione/campagna oppure aggiornare il record con procedura controllata, mai cancellare
silenziosamente la provenienza.

## 9. Verifiche prima del passaggio

- campagna non già presente o correttamente classificata come re-export;
- cartella recommended completa;
- righe e periodo plausibili nei metrics/output;
- `source_file`, `source_row`, `campaign_id` presenti;
- config usata archiviata;
- dry-run senza `output_modified` inattesi.

## 10. Cosa non fare

- Non mettere raw nell'integrazione e non modificare i CSV originali.
- Non usare permissive/restrictive come default senza decisione esplicita.
- Non rinominare cartelle già processate.
- Non eliminare provenienza, colonne o flag QC.
- Non committare raw o output completi.

## 11. Gestione Git

```powershell
git status -sb
```

Versionare codice, configurazioni, test e manifest; non i dati bulk.

## 12. Risoluzione dei problemi

- Collisione nome: non sovrascrivere; verificare manifest e checksum.
- Nessun output: controllare `--input`, manifest canonico e dipendenze.
- `output_modified`: confrontare config, pipeline e checksum prima di decidere.
- Periodo UTC vuoto: verificare classificazione timezone nell'output QC.

## 13. Checklist rapida

- [ ] CSV originale preservato.
- [ ] Nessuna sovrascrittura.
- [ ] Manifest upstream controllato.
- [ ] Profilo recommended usato.
- [ ] Output e metrics presenti.
- [ ] Provenienza conservata.
- [ ] Test leggeri passati.
- [ ] Dry-run integrazione esaminato.
- [ ] Git privo di raw/output bulk.
