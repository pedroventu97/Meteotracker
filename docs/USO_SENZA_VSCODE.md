# Uso senza VS Code

1. Installare l'installer Meteotracker per utente.
2. Aprire Meteotracker dal menu Start.
3. Scegliere una workspace esistente.
4. Aggiungere le cartelle di acquisizione oppure usare `data/raw`.
5. Premere **Controlla nuove campagne** e leggere problemi e warning.
6. Applicare soltanto dopo un controllo riuscito e una conferma esplicita.
7. Aprire report, log e output dalla workspace.

Da PowerShell è disponibile la stessa interfaccia applicativa:

```powershell
meteotracker doctor
meteotracker status
meteotracker discover
meteotracker check --new
meteotracker check --path "C:\Dati\8-1" --path "C:\Dati\9-8"
meteotracker history
```

`meteotracker apply --new` blocca ancora l'applicazione batch nella prima versione del servizio quando richiede l'orchestrazione globale; usare il workflow legacy di ingestione solo dopo una revisione del check e mai sui dati ufficiali durante lo sviluppo.
