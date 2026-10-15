# Manifest refresh 2026-10-15 08:35 (Europe/Rome)

- Nuovo manifest: `data/manifests/campaign_manifest_20261015T0835.csv`: 60 righe (49 esistenti invariate + 11 nuove), 55 canoniche, 5 escluse (duplicati storici). L'ufficiale `campaign_manifest.csv` NON e' stato toccato.
- Metodo: `scripts/detect_raw_duplicates.py` (file_sha256 + core_content_hash su Time/Lat/Lon arrotondati a 6 decimali); canonical_campaign_id = `<slug>__sha1(rel_path)[:10]` (regola verificata 44/44 sulle righe esistenti).
- Controllo duplicati: le 11 nuove vs tutti i 60 raw e tra loro: nessuna corrispondenza ne' di sha256 ne' di core hash.
- Nota: i file_sha256 delle 49 righe esistenti coincidono 49/49, ma il core_content_hash salvato differisce per 39 righe (sessioni fino a 07-04/06-20; le 10 di luglio coincidono): l'hash core storico era stato calcolato con una variante diversa. I file raw sono identici byte per byte; i valori storici sono stati lasciati invariati.
- Le 11 nuove: device mtdicambo_AC4D162B317E, 45 colonne, offset +02:00, nessun lat/lon NaN. L'ora nel nome file e' UTC (local = +2h).

| file | righe | inizio-fine locale | durata | bbox lat / lon | note |
|---|---|---|---|---|---|
| 8-1 08_39_06 | 1123 | 10:39:06-11:09:58 | 30m52s | 44.505-44.534 / 11.227-11.341 | gap max 307 s |
| 9-8 06_26_24 | 1674 | 08:26:24-09:41:05 | 1h14m | 44.414-44.551 / 11.309-11.381 | gap 923 s |
| 9-8 09_13_52 | 684 | 11:13:52-11:33:00 | 19m | 44.483-44.512 / 11.345-11.382 | |
| 9-8 12_24_03 | 743 | 14:24:03-14:46:49 | 23m | 44.487-44.509 / 11.324-11.347 | gap 335 s |
| 9-8 15_31_21 | 401 | 17:31:21-17:53:23 | 22m | 44.486-44.524 / 11.339-11.346 | gap 786 s |
| 9-8 18_50_44 | 190 | 20:50:44-21:11:25 | 21m | 44.457-44.511 / 11.347-11.362 | gap 612 s, poche righe |
| 9-16 08_30_27 | 1619 | 10:30:27-12:04:14 | 1h34m | 44.479-44.516 / 11.290-11.379 | gap 1842 s (pausa ~31 min) |
| 9-16 11_29_29 | 2041 | 13:29:29-14:16:46 | 47m | 44.476-44.512 / 11.327-11.378 | pulito (passo 2 s) |
| 9-16 15_40_40 | 799 | 17:40:40-17:57:17 | 17m | 44.513-44.566 / 11.244-11.342 | Bologna-Calderara di Reno |
| 9-16 16_58_25 | 1745 | 18:58:25-19:44:17 | 46m | 44.480-44.508 / 11.302-11.358 | gap 344 s |
| 9-16 18_36_31 | 636 | 20:36:31-20:51:07 | 15m | 44.486-44.502 / 11.318-11.342 | pulito |

Tutti i bbox rientrano nell'area di Bologna o nelle sue immediate vicinanze. Temperature plausibili (23.6-35.1 C). Ci sono 0-3 timestamp non monotoni per file.
