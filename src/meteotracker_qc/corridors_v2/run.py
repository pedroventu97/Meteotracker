"""Run corridor-based passage counting on the repeated_routes export.

python -m meteotracker_qc.corridors_v2.run --out outputs/corridor_passages_20261015
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage

from . import core

TIME_BINS = [(0.0, "night"), (5.0, "early_morning"), (7.5, "morning"), (10.5, "midday"),
             (13.5, "afternoon"), (16.5, "late_afternoon"), (19.0, "evening")]


def time_bin(h):
    lab = TIME_BINS[0][1]
    for b, n in TIME_BINS:
        if h >= b:
            lab = n
    return lab


def load_points(parts, manifest, raw_dir):
    man = manifest[manifest.is_canonical & ~manifest.exclude_from_analysis]
    files = {Path(f).stem: raw_dir / f for f in man.source_file}
    pts = []
    for cid, g in parts.groupby("campaign_id"):
        f = files.get(cid)
        if f is None or not f.exists():
            print("missing raw for", cid)
            continue
        df = pd.read_csv(f, encoding="latin-1", low_memory=False)
        tcol = [c for c in df.columns if c.startswith("Temp")][0]
        df = pd.DataFrame({"time": pd.to_datetime(df["Time"], utc=True, errors="coerce"),
                           "lat": pd.to_numeric(df["Lat"], errors="coerce"),
                           "lon": pd.to_numeric(df["Lon"], errors="coerce"),
                           "temp": pd.to_numeric(df[tcol], errors="coerce")}).dropna(subset=["time", "lat", "lon"])
        keep = []
        for _, p in g.iterrows():  # restrict to accepted campaign parts (official part split / QC)
            a, b = pd.Timestamp(p.start_datetime).tz_convert("UTC"), pd.Timestamp(p.end_datetime).tz_convert("UTC")
            m = (df.time >= a) & (df.time <= b)
            keep.append(df[m].assign(part=p.campaign_part_id))
        d = pd.concat(keep).drop_duplicates("time").sort_values("time")
        d["campaign_id"] = cid
        pts.append(d)
    P = pd.concat(pts, ignore_index=True)
    g = gpd.GeoSeries(gpd.points_from_xy(P.lon, P.lat), crs=4326).to_crs(32632)
    P["x"], P["y"] = g.x.values, g.y.values
    return P


def build_corridors(parts, cell, min_campaigns, dilate, min_corr_m, simplify_m=3.0):
    sets = []
    for cid, g in parts.groupby("campaign_id"):
        c = set()
        for geom in g.geometry:
            c |= core.line_cells(geom, cell)
        sets.append(core.dilate_cells(c, dilate))
    A, i0, j0 = core.count_grid(sets)
    M = A >= min_campaigns
    M = ndimage.binary_closing(M, np.ones((3, 3)))
    S = core.zhang_suen(M)
    edges = core.skeleton_edges(S)
    strokes = core.merge_strokes(edges, cell)
    lines = [core.pixels_to_line(s, i0, j0, cell, simplify_m) for s in strokes]
    lines = [l for l in lines if l is not None and l.length >= min_corr_m]
    lines.sort(key=lambda l: -l.length)
    return lines, A, i0, j0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpkg", default="outputs/repeated_routes_20261015T0835/repeated_routes.gpkg")
    ap.add_argument("--manifest", default="data/manifests/campaign_manifest_20261015T0835.csv")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="outputs/corridor_passages_20261015")
    ap.add_argument("--cell", type=float, default=20.0)
    ap.add_argument("--min-campaigns", type=int, default=3)
    ap.add_argument("--dilate", type=int, default=1)
    ap.add_argument("--min-corridor-m", type=float, default=250.0)
    ap.add_argument("--bins", default="100,250")
    ap.add_argument("--simplify-m", type=float, default=3.0)
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    prm = core.PassageParams()
    parts = gpd.read_file(a.gpkg, layer="campaign_parts", engine="pyogrio").to_crs(32632)
    lines, A, i0, j0 = build_corridors(parts, a.cell, a.min_campaigns, a.dilate, a.min_corridor_m, a.simplify_m)
    print("corridors", len(lines), "km", round(sum(l.length for l in lines) / 1000, 1))
    P = load_points(parts, pd.read_csv(a.manifest), Path(a.raw))
    # data-driven re-centring of raster centerlines on observed points (removes raster/simplification offsets)
    lines = [core.refine_centerline(l, P.x.values, P.y.values) for l in lines]
    P["local"] = P.time.dt.tz_convert("Europe/Rome")
    print("points", len(P), "campaigns", P.campaign_id.nunique())
    corr = gpd.GeoDataFrame({"corridor_id": [f"cv2_{k:03d}" for k in range(len(lines))],
                             "length_m": [l.length for l in lines]}, geometry=lines, crs=32632)
    sidx = corr.sindex
    rows, pb = [], []
    for cid, g in P.groupby("campaign_id"):
        x, y = g.x.values, g.y.values
        t = (g.time - g.time.iloc[0]).dt.total_seconds().values
        bb = (x.min() - 50, y.min() - 50, x.max() + 50, y.max() + 50)
        for ci in sidx.intersection(bb):
            line = lines[ci]; cidr = corr.corridor_id[ci]
            for r in core.detect_passages(line, x, y, t, prm):
                sub = g.iloc[r.idx]
                pid = f"{cidr}__{cid}__{sub.time.iloc[0]:%H%M%S}"
                rec = dict(passage_id=pid, corridor_id=cidr, campaign_id=cid,
                           parts=";".join(map(str, sorted(sub.part.unique()))),
                           date=str(sub.local.iloc[0].date()),
                           start_local=sub.local.iloc[0].isoformat(), end_local=sub.local.iloc[-1].isoformat(),
                           time_bin=time_bin(sub.local.iloc[0].hour + sub.local.iloc[0].minute / 60),
                           direction=r.direction, s_start_m=round(r.extent[0], 1), s_end_m=round(r.extent[1], 1),
                           covered_m=round(r.extent[1] - r.extent[0], 1), n_points=len(sub),
                           mean_temp=round(float(sub.temp.mean()), 3))
                for bm in map(float, a.bins.split(",")):
                    bl = core.bins_covered(r.extent, line.length, bm, prm.bin_cover_frac)
                    rec[f"bins_{int(bm)}m"] = ";".join(map(str, bl))
                    kb = np.floor(r.s / bm).astype(int)
                    for k in bl:
                        m = kb == k
                        pb.append(dict(passage_id=pid, corridor_id=cidr, bin_m=int(bm), bin_id=k,
                                       n_points=int(m.sum()), mean_temp=float(sub.temp.values[m].mean()) if m.any() else np.nan))
                rows.append(rec)
    pas = pd.DataFrame(rows); pbin = pd.DataFrame(pb)
    pas.to_csv(out / "passages.csv", index=False)
    pbin.to_csv(out / "passage_bins.csv", index=False)
    meta = pas.set_index("passage_id")[["campaign_id", "date", "direction", "time_bin"]]
    bins_out, summ = [], {}
    gp = out / "corridors.gpkg"
    if gp.exists():
        gp.unlink()
    for bm in map(float, a.bins.split(",")):
        recs = []
        for ci, line in enumerate(lines):
            cidr = corr.corridor_id[ci]
            for k, b0, b1, geom in core.make_bins(line, bm):
                sel = pbin[(pbin.corridor_id == cidr) & (pbin.bin_m == int(bm)) & (pbin.bin_id == k)]
                mm = meta.loc[sel.passage_id] if len(sel) else meta.iloc[:0]
                recs.append(dict(corridor_id=cidr, bin_m=int(bm), bin_id=k, s0_m=round(b0, 1), s1_m=round(b1, 1),
                                 n_passages=len(mm), n_campaigns=mm.campaign_id.nunique(), n_dates=mm.date.nunique(),
                                 n_along=int((mm.direction == "along").sum()), n_against=int((mm.direction == "against").sum()),
                                 n_time_bins=mm.time_bin.nunique(), time_bins=";".join(sorted(mm.time_bin.unique())),
                                 geometry=geom))
        bg = gpd.GeoDataFrame(recs, crs=32632)
        bg.to_file(gp, layer=f"bins_{int(bm)}m", engine="pyogrio")
        bins_out.append(bg.drop(columns="geometry"))
        n = bg.n_passages
        summ[f"bins_{int(bm)}m"] = dict(n_bins=len(bg), share_ge1=round(float((n >= 1).mean()), 3),
                                        share_ge3=round(float((n >= 3).mean()), 3), share_ge5=round(float((n >= 5).mean()), 3),
                                        distribution=n.value_counts().sort_index().astype(int).to_dict())
    pd.concat(bins_out).to_csv(out / "bin_counts.csv", index=False)
    b100 = bins_out[0]
    cs = []
    for ci, row in corr.iterrows():
        sel = pas[pas.corridor_id == row.corridor_id]; bb = b100[b100.corridor_id == row.corridor_id]
        cs.append(dict(corridor_id=row.corridor_id, length_m=round(row.length_m, 1), n_passages=len(sel),
                       n_campaigns=sel.campaign_id.nunique(), n_dates=sel.date.nunique(),
                       max_bin_passages=int(bb.n_passages.max()), median_bin_passages=float(bb.n_passages.median()),
                       share_bins_ge3=round(float((bb.n_passages >= 3).mean()), 3)))
    cs = pd.DataFrame(cs)
    corr = corr.merge(cs.drop(columns="length_m"), on="corridor_id")
    corr.to_file(gp, layer="corridors", engine="pyogrio")
    cs.to_csv(out / "corridor_summary.csv", index=False)
    summary = dict(params=dict(cell_m=a.cell, min_campaigns=a.min_campaigns, dilate_cells=a.dilate,
                               min_corridor_m=a.min_corridor_m, **prm.__dict__),
                   n_corridors=len(lines), total_km=round(sum(l.length for l in lines) / 1000, 2),
                   n_passages=len(pas), n_campaigns_with_passages=int(pas.campaign_id.nunique()),
                   n_points_input=int(len(P)), bins=summ,
                   top_corridors=cs.sort_values("max_bin_passages", ascending=False).head(10).to_dict("records"))
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "top_corridors"}, indent=1, default=str))
    print(cs.sort_values("max_bin_passages", ascending=False).head(10).to_string())


if __name__ == "__main__":
    main()

