# AOI E0 — Bologna study area (v0.1)

**Status:** IMPLEMENTED locally (step 3, 2026-11-05). Used by `qc_coord_outside_aoi` in `src/meteotracker_qc/gps_qc.py`.

## Asset

| Field | Value |
|-------|-------|
| File | `data/aoi/bologna_e0_aoi_v0.1.geojson` |
| CRS (storage) | EPSG:4326 (WGS84 lon/lat GeoJSON) |
| Geometry | Single Polygon (Comune di Bologna) |
| Buffer | **0 m** (exact administrative boundary; no synthetic hull) |
| Config key | `gps.aoi_geojson` (default: this relative path) |

## Provenance

- **Source asset already in the project:** `data/external/boundaries/confine_comune_bologna.gpkg` (EPSG:32632), the same local boundary used by `map_preview.py` for map overlays.
- **Transform:** reprojected to EPSG:4326 and written as versioned GeoJSON for QC (no geometry invented; not derived from campaign bboxes).
- Attributes kept for audit: `COMUNE`, `PRO_COM`, plus `aoi_id`, `source_asset`, `buffer_m`.

## Scientific note

This is the **official Comune di Bologna polygon**, not a convex hull of campaign bboxes. Inventory bboxes for E0 include a few inter-city / out-of-town legs (centers outside the comune); those points correctly receive `qc_coord_outside_aoi=True` (severity **warn** under profile `recommended` per `e0/qc_flag_schema_E0_v0.1.yaml`). Missing lat/lon stay on `qc_coord_missing` and leave `qc_coord_outside_aoi` as NA — they are **not** treated as outside the AOI.

## Policy

Flags never delete rows. Raw under `data/raw` is untouched. AOI is an eligibility / quality signal only.
