# Corridor passages v2 (many-to-many) - 2026-10-15

Experimental, independent of the official `repeated_routes` product (no existing file modified).
Code: `src/meteotracker_qc/corridors_v2/` (`core.py`, `run.py`, `validate.py`); tests: `tests/test_corridors_v2.py`.
Reproduce: `$env:PYTHONPATH="src"; .venv\Scripts\python -m meteotracker_qc.corridors_v2.run; .venv\Scripts\python src\meteotracker_qc\corridors_v2\validate.py`

## Input
- `outputs/repeated_routes_20261015T0835/repeated_routes.gpkg`, layer `campaign_parts` (55 campaigns, 128 parts; reprojected to EPSG:32632).
- Point times/temperature from `data/raw/<source_file>` of canonical, non-excluded manifest rows (`campaign_manifest_20261015T0835.csv`), restricted to each accepted part's [start, end] time window (so the official part split / campaign selection is inherited; no further point QC applied).

## Method
1. **Corridor centerlines (raster density + skeleton)**. Each campaign's parts are densified (5 m) onto a 20 m grid; each campaign's cell set is dilated by 1 cell (lateral GPS spread / lane offset) and distinct campaigns are counted per cell. Cells with >=3 campaigns, morphological closing 3x3, Zhang-Suen thinning, then the skeleton is traced with 8-connectivity (no diagonal-gap problem of the 50 m diagnostic grid), junction pixels clustered into nodes, spurs <60 m pruned, edges joined through nodes by best straight continuation (turn <=45 deg, "strokes"). Lines are lightly smoothed, simplified (3 m), kept if >=250 m, then **re-centred on the data** (median signed lateral offset of all track points within 40->30 m, 10 m stations, 2 iterations).
   *Why not merge official segment geometries*: they are pairwise reference pieces already fragmented, shifted toward one reference track and overlapping each other; merging them would inherit the fragmentation and require arbitrary dedup. The density approach depends only on where tracks are, and is reproducible.
2. **Bins**: fixed length along each corridor, 100 m (default) and 250 m (last bin shorter).
3. **Passages** (per campaign, all parts concatenated in time order, both directions): points within 20 m of the corridor are projected (s along line). A run continues while along-corridor gap |ds| <= 40 m and time gap <= 120 s (brief excursions off the band are bridged; consecutive parts of a campaign join if they satisfy the same rule). Runs are split at direction reversals > 40 m (U-turns). A passage = run whose s-extent >= 250 m. Direction: along/against the corridor digitisation. A bin is covered if the passage overlaps >= 50% of it.
4. **Per bin**: n passages, n distinct campaigns, n dates (Europe/Rome), n along/against, n and list of time bins (config boundaries). Per passage per bin: n points and mean temperature (aggregate only, no thermal interpretation).

## Outputs
- `corridors.gpkg`: `corridors` (lines + summary), `bins_100m`, `bins_250m` (with counts).
- `passages.csv` (one row per passage), `passage_bins.csv` (passage x bin, n_points, mean_temp), `bin_counts.csv`, `corridor_summary.csv`, `summary.json`.
- `validation.json`, `validation_ns_axis.csv` (diagnostic spine cells vs v2 bins vs official product).
- Figures: `map_bins_passages.png`, `map_ns_axis_zoom.png`, `profile_ns_axis.png`. Logs: `run_log.txt`, `validate_log.txt`.

## Results (see summary.json)
- Corridors: 34, total 57.1 km; passages 416 from 49 campaigns.
- bins_100m: 587 bins, share >=1 91.5%, >=3 76.1%, >=5 48.2%
- bins_250m: 246 bins, share >=1 91.5%, >=3 75.2%, >=5 48.0%
- Top corridors (max bin passages): cv2_001 5.8 km max 17, cv2_004 3.0 km max 16, cv2_000 7.1 km max 14, cv2_003 3.4 km max 14, cv2_009 1.9 km max 12

## Comparison with official product
Official pairwise matching splits the N-S axis (Viale Pepoli - Via dei Colli - Via di Sabbiuno) into many stacked segments with max 3 passages each (median 3). v2 counts on the same spine cells: median 9 passages / 8 distinct campaigns per 100 m bin (max 14), vs diagnostic "true campaigns per 50 m cell" median 9 (mean abs diff 1.3 campaigns, r = 0.64). The diagnostic counts any campaign touching a 150 m wide strip (crossings included), so it is an upper bound.

## Assumptions / limits
- A passage counts repeat traversals: one campaign may contribute several passages to a bin (back-and-forth, multiple loops); use `n_campaigns`/`n_dates` for independence.
- Corridor network depends on threshold (>=3 campaigns) and 20 m cell + 1-cell dilation: parallel streets closer than ~40 m may merge; bins at junctions may get passages from two corridors (a track is evaluated against each corridor independently).
- Some corridor pieces of the N-S axis remain split into several strokes (junctions, low-density stretches); a track passage is counted per corridor, so a passage that crosses a junction appears once per corridor.
- Raw points are not re-QC'd (only the official part time windows); temperature means are descriptive.
- 20 m tolerance on noisy GPS: tracks that deviate > 20 m for > 40 m along-corridor are split; passages < 250 m are not counted.
