# Build Windows

Prerequisiti: Python 3.11 o successivo, dipendenze geospaziali installabili dall'indice configurato e, per l'installer, Inno Setup con `iscc` nel `PATH`.

```powershell
python -m pip install -e ".[gui,build]"
.\scripts\build_windows.ps1 -Version 0.1.0
.\scripts\build_windows.ps1 -Version 0.1.0 -Installer
```

La prima variante produce la directory portable `dist/Meteotracker`; la seconda produce anche `dist/Meteotracker-<version>-setup.exe`. La configurazione Inno Setup usa installazione per-utente e non rimuove la workspace durante la disinstallazione.

La build non include `data/raw`, output reali, cache, log, manifest personali o credenziali. Verificare sempre il contenuto di `dist` prima della distribuzione. Gli artefatti di build locali sono esclusi da Git.
