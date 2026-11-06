# Design split E0 – giorno / route / blocco spaziale (DRAFT, 5/11/2026)
| Chiave | Definizione | Tag |
|---|---|---|
| day | data di calendario locale Europe/Rome, dal timestamp convertito da UTC | DESIGN |
| route | corridor_id di corridors_v2 (cv2_*) se presente, altrimenti segment_id dei repeated_routes_20261015T0835, altrimenti NA | DESIGN (fonti VERIFIED) |
| spatial_block | griglia da 500 m in EPSG:32632, con classe LCZ come attributo secondario per la stratificazione | DESIGN |
| bootstrap unit | canonical_campaign_id (55 campagne) | DESIGN |
## Separazione
- **Ripetibilità temporale:** stessa route, campagne **diverse** in day **diversi**. Si confrontano le anomalie per passaggio, con bootstrap per campagna.
  - Limite (VERIFIED, `outputs/short_dt_anomaly_20261015T1927/summary.json`): share_same_campaign=1.0, con solo 12 coppie su 7 campagne. Lo short-dt misura quindi la coerenza all'interno di una campagna (andata/ritorno), non la ripetibilità tra un giorno e l'altro.
- **Rappresentatività spaziale:** si stratifica per spatial_block e LCZ, con hold-out per blocco (block CV) per non sovrastimare la copertura. La ripetibilità temporale non va mai usata come prova di rappresentatività.
- **Vincolo di potenza:** solo 23 segmenti hanno almeno 3 passaggi (VERIFIED, `rr_segments_ge3.csv`), quindi i CI di R sono ampi. Va dichiarata una soglia minima: almeno 3 campagne distinte per route (DESIGN).

## Step 4 applicato (2026-11-05)
- Output: `outputs/e0_qc_split_20261105T1703/` (locale, non in git).
- n_obs 72505; n_days 17; n_routes non-null 604 (cv2/seg/NA); n_spatial_blocks 570; routes ≥3 campagne 40.
- LCZ: nessun asset sotto `data/`; usato `D:\\projects\\LCZ\\LCZ_PRISMA.shp` (coverage 0.9148). WARNING da risolvere in seguito.
- Separazione temporale vs spaziale rispettata nel design applicato; i flag non cancellano righe.
