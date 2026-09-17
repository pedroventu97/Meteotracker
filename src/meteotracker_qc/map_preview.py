"""Offline route preview; no point-QC pipeline, caches or official writes."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import CRS, Geod, Transformer
import yaml

from .session_analysis import file_hash, safe_child

PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#6f42c1", "#5b6422")


def track_color(campaign_id):
    # Stable hue also beyond a fixed palette; independent of selection order.
    import colorsys
    hue = int(hashlib.sha256(campaign_id.encode("utf-8")).hexdigest()[:8], 16) / 0xffffffff
    rgb = colorsys.hsv_to_rgb(hue, .75, .70)
    return "#" + "".join(f"{round(v * 255):02x}" for v in rgb)


def map_crs(config_dir):
    cfg = yaml.safe_load((config_dir / "repeated_routes_recommended.yaml").read_text(encoding="utf-8"))
    geographic = CRS.from_epsg(cfg["crs_geographic_epsg"])
    metric = CRS.from_epsg(cfg["crs_metric_epsg"])
    if not geographic.is_geographic or not metric.is_projected or any(a.unit_name != "metre" for a in metric.axis_info):
        raise ValueError("CRS geografico/metrico incompatibile; serve un CRS proiettato in metri")
    return geographic, metric


def read_track(path, campaign_id, source_file, config_dir, token):
    token.checkpoint()
    source_hash = file_hash(path)
    raw = pd.read_csv(path, na_values=["-"])
    n = len(raw)
    geographic, metric = map_crs(config_dir)
    cfg = yaml.safe_load((config_dir / "qc_recommended.yaml").read_text(encoding="utf-8"))
    numeric = lambda key: pd.to_numeric(raw.get(key, pd.Series(np.nan, index=raw.index)), errors="coerce")
    lat, lon = numeric("Lat"), numeric("Lon")
    valid = lat.between(-90, 90) & lon.between(-180, 180)
    time = pd.to_datetime(raw.get("Time", pd.Series(index=raw.index, dtype=str)), format="mixed", utc=True, errors="coerce")
    dt = time.diff().dt.total_seconds()
    positive = dt[dt.gt(0) & np.isfinite(dt)]
    cadence = float(positive.median()) if len(positive) else cfg["time"]["fallback_expected_dt_s"]
    gap = dt.gt(max(cadence * cfg["time"]["gap_long_multiplier"], cfg["time"]["gap_absolute_floor_s"]))
    distance = np.full(n, np.nan)
    pairs = valid & valid.shift(1, fill_value=False)
    positions = np.flatnonzero(pairs)
    if len(positions):
        _, _, dist = geographic.get_geod().inv(lon.iloc[positions - 1].to_numpy(), lat.iloc[positions - 1].to_numpy(),
                                            lon.iloc[positions].to_numpy(), lat.iloc[positions].to_numpy())
        distance[positions] = dist
    jump = (distance > cfg["gps"]["gps_jump_distance_m"]) & dt.le(cfg["gps"]["gps_jump_dt_s"]).to_numpy()
    breaks = gap | pd.Series(jump) | dt.le(0) | ~valid | ~valid.shift(1, fill_value=False)
    x, y = np.full(n, np.nan), np.full(n, np.nan)
    if valid.any():
        x[valid], y[valid] = Transformer.from_crs(geographic, metric, always_xy=True).transform(lon[valid].to_numpy(), lat[valid].to_numpy())
    points = pd.DataFrame({"source_row": np.arange(n), "time_utc": time, "Lat": lat, "Lon": lon,
                           "x_m": x, "y_m": y, "segment_preview": breaks.cumsum(),
                           "preliminary_missing": lat.isna() | lon.isna(), "preliminary_invalid": ~valid & lat.notna() & lon.notna(),
                           "preliminary_jump": jump, "preliminary_gap": gap, "preliminary_break": breaks,
                           "Temp[°C]": numeric("Temp[°C]"), "Hum[%]": numeric("Hum[%]"),
                           "Press[mbar]": numeric("Press[mbar]"), "Speed[km/h]": numeric("Speed[km/h]")})
    start, end = time.min(), time.max()
    token.checkpoint()
    if file_hash(path) != source_hash:
        raise ValueError("Sorgente cambiata durante il caricamento mappa")
    return {"campaign_id": campaign_id, "source_file": source_file, "color": track_color(campaign_id), "points": points,
            "source_sha256": source_hash, "preliminary_config": cfg,
            "rows": n, "start": str(start) if pd.notna(start) else None, "end": str(end) if pd.notna(end) else None,
            "duration_s": (end - start).total_seconds() if pd.notna(start) and pd.notna(end) else None,
            "distance_km": float(np.nansum(np.where(breaks, 0, distance)) / 1000),
            "missing_coordinates": int(points.preliminary_missing.sum()), "invalid_coordinates": int(points.preliminary_invalid.sum()),
            "preliminary_jumps": int(np.sum(jump)), "preliminary_gaps": int(gap.sum()),
            "geographic_crs": geographic.to_string(), "metric_crs": metric.to_string()}


def load_preview(workspace, entries, token):
    tracks = []
    for entry in entries:
        token.checkpoint()
        tracks.append(read_track(safe_child(workspace / "data/raw", entry["source_file"]), entry["canonical_campaign_id"],
                                 entry["source_file"], workspace / "config", token))
    _, metric = map_crs(workspace / "config")
    boundary, boundary_note = [], "Confine locale non disponibile"
    # Conventional local asset; optional override is user-owned, never a scientific YAML edit.
    boundary_path = "data/external/boundaries/confine_comune_bologna.gpkg"
    preference = workspace / "user_presets/map.json"
    try:
        if preference.exists():
            import json
            boundary_path = json.loads(preference.read_text(encoding="utf-8")).get("boundary_path", boundary_path)
        if Path(boundary_path).is_absolute():
            raise ValueError("Il confine richiede un percorso relativo alla workspace")
        path = safe_child(workspace, boundary_path)
        if path.exists():
            import geopandas as gpd
            area = gpd.read_file(path)
            if area.crs is None or area.empty or not area.is_valid.all():
                raise ValueError("Confine privo di CRS o geometria valida")
            for geometry in area.to_crs(metric).geometry:
                geometries = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
                for polygon in geometries:
                    if polygon.geom_type != "Polygon":
                        raise ValueError("Confine non poligonale")
                    boundary.append(np.asarray(polygon.exterior.coords))
            boundary_note = f"Confine locale: {boundary_path}"
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        boundary = []
        boundary_note = f"Confine non disponibile: {exc}"
    token.checkpoint()
    return {"tracks": tracks, "boundary": boundary, "boundary_note": boundary_note, "metric_crs": metric.to_string(),
            "geographic_crs": tracks[0]["geographic_crs"] if tracks else "EPSG:4326", "mode": "Anteprima originale read-only; indicatori preliminari"}


def render_indices(points, limit=6000):
    """Decimate display only, retaining segment endpoints and first/last fixes."""
    if len(points) <= limit:
        return np.arange(len(points))
    keep = np.linspace(0, len(points) - 1, limit, dtype=int)
    segment = points.segment_preview.to_numpy()
    edges = np.flatnonzero(np.r_[True, segment[1:] != segment[:-1]])
    fixes = np.flatnonzero(np.isfinite(points.x_m) & np.isfinite(points.y_m))
    endpoints = fixes[[0, -1]] if len(fixes) else []
    return np.unique(np.r_[keep, edges, np.maximum(0, edges - 1), endpoints, len(points) - 1]).astype(int)


def draw_map(ax, preview, *, visible=None, frames=None, profile="recommended", mode="Tutti i punti", family_flags=(), density=False, overlaps=False, show_legend=True):
    """Shared rendering for interactive canvas and reproducible PNG exports."""
    ax.clear()
    rendered = []
    visible = set(visible) if visible is not None else {t["campaign_id"] for t in preview["tracks"]}
    for outline in preview.get("boundary", []):
        ax.plot(outline[:, 0], outline[:, 1], color="#888888", linewidth=.6, alpha=.6)
    bounds, cloud, track_bins = [], [], {}
    for track in preview["tracks"]:
        cid = track["campaign_id"]
        if cid not in visible:
            continue
        points = track["points"]
        use = np.isfinite(points.x_m) & np.isfinite(points.y_m)
        flagged = points.preliminary_jump | points.preliminary_invalid | points.preliminary_gap
        frame = (frames or {}).get(cid)
        kept = None
        if frame is not None:
            kept = frame[f"keep_{profile}"].to_numpy(dtype=bool)
            flag_columns = [c for c in frame if c.startswith("qc_") and pd.api.types.is_bool_dtype(frame[c])]
            flags = list(family_flags) if family_flags else flag_columns
            flags = [f for f in flags if f in frame]
            flagged = frame[flags].fillna(False).any(axis=1) if flags else pd.Series(False, index=frame.index)
            if mode == "Punti mantenuti":
                use &= kept
            elif mode in {"Punti flaggati", "Famiglia di flag"}:
                use &= flagged
        idx = render_indices(points)
        display = points.iloc[idx]
        display_use = use.iloc[idx].to_numpy()
        color = track["color"]
        # Lines never cross missing fixes, jumps, temporal breaks or filtered-out points.
        x = display.x_m.to_numpy().copy()
        y = display.y_m.to_numpy().copy()
        breaks = display.segment_preview.ne(display.segment_preview.shift()).to_numpy()
        line_x = np.insert(x, np.flatnonzero(breaks), np.nan)
        line_y = np.insert(y, np.flatnonzero(breaks), np.nan)
        if mode in {"Tutti i punti", "Prima/dopo QC"}:
            ax.plot(line_x, line_y, color=color, lw=.8, alpha=.6)
        scatter = ax.scatter(x[display_use], y[display_use], s=6, color=color, label=cid[:32], picker=5)
        rendered.append((scatter, cid, idx[display_use]))
        valid_positions = np.flatnonzero(np.isfinite(x) & np.isfinite(y))
        if len(valid_positions):
            first, last = valid_positions[0], valid_positions[-1]
            ax.scatter(x[first], y[first], marker="^", s=65, c=color, edgecolors="black")
            ax.scatter(x[last], y[last], marker="s", s=45, c=color, edgecolors="black")
            for pos in np.linspace(1, len(x) - 1, min(6, max(0, len(x) - 1)), dtype=int):
                if not breaks[pos] and np.isfinite(x[pos - 1:pos + 1]).all() and np.isfinite(y[pos - 1:pos + 1]).all():
                    ax.annotate("", (x[pos], y[pos]), (x[pos - 1], y[pos - 1]), arrowprops={"arrowstyle": "->", "color": color})
        suspect = flagged.iloc[idx].to_numpy() & np.isfinite(x) & np.isfinite(y)
        ax.scatter(x[suspect], y[suspect], facecolors="none", edgecolors="#dc2626", s=35, linewidths=.9)
        interrupted = display.preliminary_break.to_numpy() & np.isfinite(x) & np.isfinite(y)
        if len(interrupted):
            interrupted[0] = False
        ax.scatter(x[interrupted], y[interrupted], c="#7c3aed", marker="x", s=30)
        if mode == "Prima/dopo QC" and kept is not None:
            ax.scatter(x[kept[idx]], y[kept[idx]], c="#00a050", s=10, alpha=.7)
        all_xy = points.loc[use, ["x_m", "y_m"]].to_numpy()
        if len(all_xy):
            cloud.append(all_xy)
            bounds.append((all_xy.min(axis=0), all_xy.max(axis=0)))
            if overlaps:
                for key in set(map(tuple, np.floor(all_xy / 50).astype(int))):
                    track_bins[key] = track_bins.get(key, 0) + 1
    if density and cloud:
        xy = np.concatenate(cloud)
        ax.hist2d(xy[:, 0], xy[:, 1], bins=60, cmap="YlOrRd", alpha=.35, cmin=1)
    if overlaps:
        cells = np.array([key for key, count in track_bins.items() if count > 1])
        if len(cells):
            ax.scatter((cells[:, 0] + .5) * 50, (cells[:, 1] + .5) * 50, marker="s", s=70, facecolors="none", edgecolors="black")
    if bounds:
        low, high = np.min([b[0] for b in bounds], axis=0), np.max([b[1] for b in bounds], axis=0)
        pad = np.maximum((high - low) * .07, 30)
        # Expand the metric view to the canvas aspect so long vertical routes do
        # not shrink the entire axes/labels into a narrow strip in a wide window.
        canvas_width, canvas_height = ax.figure.canvas.get_width_height()
        aspect = max(1, canvas_width - 100) / max(80, canvas_height - 80)
        span = high - low + 2 * pad
        target = np.array([max(span[0], span[1] * aspect), max(span[1], span[0] / aspect)])
        pad += (target - span) / 2
        ax.set_xlim(low[0] - pad[0], high[0] + pad[0])
        ax.set_ylim(low[1] - pad[1], high[1] + pad[1])
        width = high[0] - low[0] + 2 * pad[0]
        scale = 10 ** np.floor(np.log10(width / 5))
        origin = low - pad * .5
        ax.plot([origin[0], origin[0] + scale], [origin[1], origin[1]], color="black", lw=3)
        ax.text(origin[0], origin[1], f" {scale:g} m", fontsize=8, va="bottom")
    ax.set_aspect("equal", adjustable="box")
    ax.ticklabel_format(style="plain", useOffset=False)
    ax.grid(alpha=.2)
    ax.locator_params(axis="both", nbins=3)
    ax.tick_params(labelsize=8)
    ax.set_xlabel(f"Est [m] — {preview['metric_crs']}", fontsize=8)
    ax.set_ylabel("Nord [m] (griglia)", fontsize=8)
    ax.set_title("Densità esplorativa — non ufficiale" if density else "Tracce originali / QC — offline", fontsize=10)
    ax.text(.02, .98, "↑ Nord griglia", transform=ax.transAxes, va="top", fontsize=8)
    if rendered and show_legend:
        ax.legend(loc="best", fontsize=7)
    return rendered


def export_geodata(frame, directory, formats, *, campaign_id, geographic_crs="EPSG:4326"):
    if not {"gpkg", "geojson"} & set(formats):
        return
    import geopandas as gpd
    lat, lon = pd.to_numeric(frame["Lat"], errors="coerce"), pd.to_numeric(frame["Lon"], errors="coerce")
    valid = lat.between(-90, 90) & lon.between(-180, 180)
    data = frame.loc[valid].copy()
    data["canonical_campaign_id"] = campaign_id
    for column in data:
        if pd.api.types.is_datetime64_any_dtype(data[column]):
            data[column] = data[column].astype(str)
    geo = gpd.GeoDataFrame(data, geometry=gpd.points_from_xy(lon[valid], lat[valid]), crs=geographic_crs)
    if "gpkg" in formats:
        geo.to_file(directory / "selection.gpkg", layer="points", driver="GPKG")
    if "geojson" in formats:
        geo.to_crs("EPSG:4326").to_file(directory / "selection.geojson", driver="GeoJSON")
