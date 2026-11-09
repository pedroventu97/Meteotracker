# P1 – Repeatability on the E0 split (method)

Code: `src/meteotracker_qc/p1_repeatability/core.py` (pure functions), runner `e0/run_p1_repeatability_e0.py`, tests `tests/test_p1_repeatability.py`.
Run: `.venv\Scripts\python.exe e0\run_p1_repeatability_e0.py --n-boot 1000` (about 10 min on DICAM). It writes only a new folder `outputs/p1_repeatability_E0_<YYYYMMDDTHHMM Europe/Rome>/` and refuses to write into existing, 20261015/18 or e0_qc_split folders.

## What it reuses from 20261015
- From `pass_anomaly_20261015T1856` and `short_dt_anomaly_20261015T1927`:
  - R = Σ cov_ab / Σ √(var_a var_b), weighted by common bins;
  - Fisher-mean r;
  - campaign-cluster bootstrap, where the pair weight is the product of the two campaigns' multiplicities (or the multiplicity alone for same-campaign pairs);
  - 50 m bins, ≥2 points per bin, ≥4 common bins.
- New on E0:
  - locations come from the E0 split (route = cv2_* / seg_*; spatial_block = 500 m, EPSG:32632);
  - day = Europe/Rome date;
  - three QC profiles plus a literal flag-table mask, applied as masks;
  - explicit pair types (diff_day / same_day_diff_campaign / same_campaign);
  - leave-one-campaign/day/route/spatial_block;
  - a location-level ICC.

## Steps
1. Join `split_assignments_E0` with the per-campaign `*_flagged.csv` on (canonical_campaign_id, source_row). Masks are `keep_permissive`, `keep_recommended` and `keep_restrictive` from the same E0 QC run. `flagtable_exclude` drops any row with an exclude-severity flag in `flag_table_E0`. No rows are deleted.
2. Passes: a continuous visit of one campaign to one location, split at gaps > 120 s, ≥10 points. Two variants: `centered` (T, centred per pair over the common cells) and `detrended` (T minus a within-pass linear fit vs time, for passes ≥30 s).
3. Pass pairs: built within each location that has ≥3 distinct campaigns, with ≥4 common 50 m cells. For each pair: cov, sd2, r, msd (RMSD of the centred profiles), median Δt, pair type.
4. Pooled metrics per pair group, with a 1000-rep campaign bootstrap (seed 20261109).
5. Leave-one-*:
   - campaign, day and the location's own unit: drop the corresponding pairs (exact);
   - cross unit (block for routes, route for blocks): drop that unit's cells and recompute the pair statistics.
6. Location level:
   - point anomaly vs the campaign, in three variants: mean, linear-in-time, or linear in time + altitude;
   - location × campaign means (≥10 points), re-centred per campaign;
   - ICC(1) between locations, with a leave-one-campaign jackknife CI (a duplicate-campaign bootstrap biases ICC upward);
   - R over pairs of campaigns sharing ≥4 locations.

## Rules respected
- QC flags never delete data.
- No LST/LCZ input, so the 2019–2022 training-year exclusion does not apply.
- LST ≠ Tair.
- V18 untouched.
- Outputs are not committed.
