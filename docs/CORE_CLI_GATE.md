# Gate 1: core e CLI

## Installazione

```powershell
python -m pip install -e ".[test]"
meteotracker --help
python -m meteotracker_qc --help
```

La workspace viene risolta in questo ordine: `--workspace`, `METEOTRACKER_WORKSPACE`, ricerca dalla directory corrente verso i genitori, directory corrente. E' valida quando contiene `data/raw`, `data/manifests`, `config`, `outputs` e `logs`.

## Comandi

```powershell
meteotracker doctor
meteotracker status
meteotracker discover
meteotracker check --new
meteotracker check --path "C:\Dati\8-1" --path "C:\Dati\9-8"
meteotracker apply --new
meteotracker run --new --yes
meteotracker history
meteotracker history --run-id <run_id>
```

`discover` classifica ogni CSV, inclusi quelli gia registrati. `check` crea rapporti JSON e Markdown sotto `logs/check_reports/` e usa solo directory temporanee per il QC preview. Non modifica raw, manifest, output ufficiali o cache ufficiale.

`apply` acquisisce un lock con PID, timestamp, run ID, workspace, host e versione del processo. Esegue manifest, profili QC, Session QC, repeated routes, spatial density e temporal drift in staging; la promozione usa il rollback gia presente nel core. Un batch con piu cartelle invoca le analisi globali una sola volta. Il ledger atomico e' `logs/run_ledger.json`.

Codici principali: `0` successo o warning, `1` errore interno, `2` file invalidi/ambigui, `3` workspace bloccata o operazione non consentita.

Gli script precedenti `python run_qc.py` e `python ingest_acquisition.py` restano compatibili. Il loro percorso storico non viene duplicato o reinterpretato dal core scientifico; la nuova CLI usa le stesse funzioni di pipeline e ingestione.
