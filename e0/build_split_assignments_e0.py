"""Build E0 split assignments (day / route / spatial_block) from Step-4 QC outputs.

Reusable helper. Reads standardized/flagged QC outputs under an e0_qc_split_* root.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(r"D:\projects\Meteotracker")
ROME = ZoneInfo("Europe/Rome")


def find_lat_lon(df: pd.DataFrame) -> tuple[str, str]:
    for la, lo in (
        ("canonical_latitude", "canonical_longitude"),
        ("Lat", "Lon"),
        ("latitude", "longitude"),
        ("lat", "lon"),
    ):
        if la in df.columns and lo in df.columns:
            return la, lo
    raise KeyError(f"No lat/lon columns in {list(df.columns)[:30]}")


def load_passages() -> pd.DataFrame:
    path = ROOT / "outputs" / "corridor_passages_20261015" / "passages.csv"
    pas = pd.read_csv(path)
    # parse times to UTC for comparison
    pas["start_utc"] = pd.to_datetime(pas["start_local"], utc=True, errors="coerce")
    pas["end_utc"] = pd.to_datetime(pas["end_local"], utc=True, errors="coerce")
    return pas


def load_memberships_slim() -> pd.DataFrame:
    path = ROOT / "outputs" / "repeated_routes_20261015T0835" / "point_segment_memberships.csv"
    usecols = [
        "repeated_segment_id",
        "campaign_id",
        "source_file",
        "source_row",
        "distance_to_passage_m",
    ]
    m = pd.read_csv(path, usecols=usecols)
    m["source_basename"] = m["source_file"].astype(str).map(lambda s: Path(s).name)
    # keep best (nearest) membership per campaign_id+source_row
    m = m.sort_values("distance_to_passage_m", ascending=True)
    m = m.drop_duplicates(subset=["campaign_id", "source_row"], keep="first")
    return m[["campaign_id", "source_row", "source_basename", "repeated_segment_id"]]


def try_load_lcz():
    """Prefer project data/; else documented external LCZ_PRISMA if present."""
    warnings = []
    under_data = []
    data = ROOT / "data"
    for p in data.rglob("*"):
        if ".venv" in p.parts or ".gate" in "".join(p.parts):
            continue
        name = p.name.lower()
        if p.is_file() and p.suffix.lower() in {".shp", ".tif", ".tiff", ".gpkg", ".geojson"}:
            if "lcz" in name or "wudapt" in name:
                under_data.append(p)
    if under_data:
        path = under_data[0]
        warnings.append(f"Using LCZ under data/: {path}")
    else:
        path = Path(r"D:\projects\LCZ\LCZ_PRISMA.shp")
        if path.exists():
            warnings.append(
                "WARNING: no LCZ raster/vector under data/; using documented external "
                f"asset from B2 metadata: {path}"
            )
        else:
            warnings.append(
                "WARNING: LCZ asset missing under data/ and external D:\\projects\\LCZ\\LCZ_PRISMA.shp not found; lcz=NA"
            )
            return None, warnings
    try:
        import geopandas as gpd
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf = gdf.set_crs(32632)
        else:
            gdf = gdf.to_crs(32632)
        # class column
        class_col = None
        for c in ("DN", "lcz", "LCZ", "class", "CODE"):
            if c in gdf.columns:
                class_col = c
                break
        if class_col is None:
            warnings.append(f"WARNING: LCZ file has no class column among DN/lcz/LCZ; cols={list(gdf.columns)}; lcz=NA")
            return None, warnings
        gdf = gdf[[class_col, "geometry"]].rename(columns={class_col: "lcz"})
        return gdf, warnings
    except Exception as e:
        warnings.append(f"WARNING: failed to load LCZ ({e}); lcz=NA")
        return None, warnings


def assign_route_for_campaign(
    obs: pd.DataFrame,
    campaign_stem: str,
    passages: pd.DataFrame,
    memberships: pd.DataFrame,
) -> pd.Series:
    """Return route series aligned to obs index."""
    route = pd.Series(pd.NA, index=obs.index, dtype="object")
    # 1) corridors_v2 via passage time windows
    sub = passages.loc[passages["campaign_id"] == campaign_stem]
    if len(sub) and "time_utc" in obs.columns:
        t = pd.to_datetime(obs["time_utc"], utc=True, errors="coerce")
        # sort passages by covered_m desc for preference
        sub = sub.sort_values("covered_m", ascending=False)
        assigned = pd.Series(False, index=obs.index)
        for _, preg in sub.iterrows():
            if pd.isna(preg["start_utc"]) or pd.isna(preg["end_utc"]):
                continue
            mask = (~assigned) & t.notna() & (t >= preg["start_utc"]) & (t <= preg["end_utc"])
            if mask.any():
                route.loc[mask] = preg["corridor_id"]
                assigned.loc[mask] = True
        # 2) fallback memberships for remaining
        need = route.isna()
        if need.any():
            mem = memberships.loc[memberships["campaign_id"] == campaign_stem]
            if len(mem) and "source_row" in obs.columns:
                merged = obs.loc[need, ["source_row"]].merge(
                    mem[["source_row", "repeated_segment_id"]],
                    on="source_row",
                    how="left",
                )
                route.loc[need] = merged["repeated_segment_id"].values
    else:
        # no passages: memberships only
        mem = memberships.loc[memberships["campaign_id"] == campaign_stem]
        if len(mem) and "source_row" in obs.columns:
            merged = obs[["source_row"]].merge(
                mem[["source_row", "repeated_segment_id"]],
                on="source_row",
                how="left",
            )
            route = merged["repeated_segment_id"]
            route.index = obs.index
    return route


def spatial_block_ids(lat: pd.Series, lon: pd.Series) -> pd.Series:
    from pyproj import Transformer

    tr = Transformer.from_crs(4326, 32632, always_xy=True)
    valid = lat.notna() & lon.notna()
    east = np.full(len(lat), np.nan)
    north = np.full(len(lat), np.nan)
    if valid.any():
        e, n = tr.transform(lon.loc[valid].to_numpy(dtype=float), lat.loc[valid].to_numpy(dtype=float))
        east[valid.to_numpy()] = e
        north[valid.to_numpy()] = n
    ei = np.floor(east / 500.0)
    ni = np.floor(north / 500.0)
    out = pd.Series(pd.NA, index=lat.index, dtype="object")
    ok = np.isfinite(ei) & np.isfinite(ni)
    out.loc[ok] = [
        f"{int(a)}_{int(b)}" for a, b in zip(ei[ok], ni[ok])
    ]
    return out, east, north


def attach_lcz(east, north, lcz_gdf):
    if lcz_gdf is None:
        return pd.Series(pd.NA, index=range(len(east)), dtype="object")
    import geopandas as gpd
    from shapely.geometry import Point

    ok = np.isfinite(east) & np.isfinite(north)
    lcz = pd.Series(pd.NA, index=range(len(east)), dtype="object")
    if not ok.any():
        return lcz
    pts = gpd.GeoDataFrame(
        {"_i": np.where(ok)[0]},
        geometry=[Point(xy) for xy in zip(east[ok], north[ok])],
        crs=32632,
    )
    joined = gpd.sjoin(pts, lcz_gdf, how="left", predicate="within")
    # if duplicates from overlapping polys, keep first
    joined = joined.drop_duplicates(subset=["_i"], keep="first")
    lcz.iloc[joined["_i"].to_numpy()] = joined["lcz"].astype(str).where(joined["lcz"].notna(), other=pd.NA).values
    return lcz


def build_for_root(output_root: Path) -> dict:
    assert output_root.name.startswith("e0_qc_split_"), output_root
    campaigns_dir = output_root / "campaigns"
    passages = load_passages()
    print("Loaded passages", len(passages), flush=True)
    memberships = load_memberships_slim()
    print("Loaded memberships unique", len(memberships), flush=True)
    lcz_gdf, lcz_warnings = try_load_lcz()
    for w in lcz_warnings:
        print(w, flush=True)

    parts = []
    camp_dirs = sorted([p for p in campaigns_dir.iterdir() if p.is_dir()])
    for i, cdir in enumerate(camp_dirs, start=1):
        canonical_id = cdir.name
        # prefer parquet
        parquets = list(cdir.glob("*_standardized.parquet"))
        if not parquets:
            print(f"SKIP no parquet {canonical_id}", flush=True)
            continue
        df = pd.read_parquet(parquets[0])
        la, lo = find_lat_lon(df)
        # campaign stem = file stem from parquet name
        stem = parquets[0].name.replace("_standardized.parquet", "")
        # source_file relative if present
        source_file = df["source_file"].iloc[0] if "source_file" in df.columns else stem + ".csv"
        # time
        if "time_utc" not in df.columns:
            print(f"SKIP no time_utc {canonical_id}", flush=True)
            continue
        t_utc = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
        t_local = t_utc.dt.tz_convert(ROME)
        day = t_local.dt.strftime("%Y-%m-%d")
        route = assign_route_for_campaign(df, stem, passages, memberships)
        blocks, east, north = spatial_block_ids(df[la], df[lo])
        lcz = attach_lcz(east, north, lcz_gdf)
        out = pd.DataFrame(
            {
                "canonical_campaign_id": canonical_id,
                "source_file": source_file,
                "source_row": df["source_row"] if "source_row" in df.columns else np.arange(len(df)),
                "time_utc": t_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "time_local": t_local.dt.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "day": day,
                "route": route.values,
                "spatial_block_id": blocks.values,
                "lcz": lcz.values,
                "lat": df[la].values,
                "lon": df[lo].values,
            }
        )
        parts.append(out)
        if i % 5 == 0 or i == len(camp_dirs):
            print(f"split progress {i}/{len(camp_dirs)}", flush=True)
        del df

    if not parts:
        raise SystemExit("No campaign parts for split")
    assign = pd.concat(parts, ignore_index=True)
    assign_path = output_root / "split_assignments_E0.csv"
    assign.to_csv(assign_path, index=False)
    try:
        assign.to_parquet(output_root / "split_assignments_E0.parquet", index=False)
    except Exception as e:
        print("parquet assign skip", e)

    route_nonnull = assign["route"].notna() & (assign["route"].astype(str) != "<NA>")
    # pandas NA
    route_nonnull = assign["route"].notna()
    n_routes = int(assign.loc[route_nonnull, "route"].nunique())
    # routes with >=3 distinct campaigns
    rc = (
        assign.loc[route_nonnull]
        .groupby("route")["canonical_campaign_id"]
        .nunique()
    )
    routes_ge3 = int((rc >= 3).sum())
    lcz_cov = float(assign["lcz"].notna().mean()) if len(assign) else 0.0
    # route source coverage: cv2 vs seg
    routes_s = assign.loc[route_nonnull, "route"].astype(str)
    n_cv2 = int(routes_s.str.startswith("cv2_").sum())
    n_seg = int(routes_s.str.startswith("seg_").sum())
    n_other = int(route_nonnull.sum() - n_cv2 - n_seg)

    summary = {
        "n_campaigns": int(assign["canonical_campaign_id"].nunique()),
        "n_obs": int(len(assign)),
        "n_days": int(assign["day"].nunique()),
        "n_routes_nonnull": n_routes,
        "n_obs_with_route": int(route_nonnull.sum()),
        "n_obs_route_cv2": n_cv2,
        "n_obs_route_seg": n_seg,
        "n_obs_route_other": n_other,
        "n_obs_route_na": int((~route_nonnull).sum()),
        "n_spatial_blocks": int(assign["spatial_block_id"].nunique(dropna=True)),
        "routes_with_ge3_campaigns": routes_ge3,
        "lcz_coverage_fraction": lcz_cov,
        "warnings": lcz_warnings,
        "built_at_europe_rome": datetime.now(ROME).isoformat(timespec="seconds"),
        "split_assignments_path": str(assign_path),
    }
    (output_root / "split_summary_E0.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md = [
        "# split_summary_E0",
        "",
        f"- n_campaigns: **{summary['n_campaigns']}**",
        f"- n_obs: **{summary['n_obs']}**",
        f"- n_days: **{summary['n_days']}**",
        f"- n_routes (non-null): **{summary['n_routes_nonnull']}**",
        f"- n_obs with route: {summary['n_obs_with_route']} (cv2={n_cv2}, seg={n_seg}, other={n_other}, NA={summary['n_obs_route_na']})",
        f"- n_spatial_blocks: **{summary['n_spatial_blocks']}**",
        f"- routes with ≥3 distinct campaigns: **{routes_ge3}**",
        f"- LCZ coverage fraction: **{lcz_cov:.4f}**",
        "",
        "## Warnings",
    ]
    for w in lcz_warnings:
        md.append(f"- {w}")
    md.append("")
    md.append("## Rules")
    md.append("- day = calendar date Europe/Rome from time_utc")
    md.append("- route = corridors_v2 cv2_* via passage time window if available; else repeated_routes segment_id; else NA")
    md.append("- spatial_block_id = floor(easting/500)_floor(northing/500) in EPSG:32632")
    md.append("- bootstrap unit = canonical_campaign_id")
    (output_root / "split_summary_E0.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main():
    if len(sys.argv) > 1:
        output_root = Path(sys.argv[1])
    else:
        # latest e0_qc_split_*
        outs = sorted((ROOT / "outputs").glob("e0_qc_split_*"))
        if not outs:
            raise SystemExit("No e0_qc_split_* found")
        output_root = outs[-1]
    print("Using", output_root, flush=True)
    build_for_root(output_root)


if __name__ == "__main__":
    main()
