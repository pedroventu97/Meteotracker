"""Read-only session analysis shared by desktop and CLI.

All scientific computations delegate to the existing point and session engines.
Per-call cancellation/events keep the shared ApplicationService safe for workers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import uuid

import numpy as np
import pandas as pd
import yaml

from .analysis_settings import (DEFAULT_ACTIVE, GROUPS, PROFILES, SCHEMA_VERSION, describe_settings,
                                preset_payload, settings_fingerprint, validate_settings)
from .operation import CancellationToken


def json_value(value):
    """Strict JSON, including numpy/pandas missing scalars and timestamps."""
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or (not isinstance(value, (str, Path)) and pd.isna(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime, Path)):
        return str(value)
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(json_value(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def file_hash(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def safe_child(root, relative):
    root = Path(root).resolve()
    path = (root / str(relative)).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f"Percorso fuori dalla directory consentita: {relative}")
    return path


def canonical_manifest(workspace):
    manifest = pd.read_csv(workspace / "data/manifests/campaign_manifest.csv", keep_default_na=False)
    required = {"source_file", "canonical_campaign_id", "exclude_from_analysis"}
    if not required <= set(manifest):
        raise ValueError("Schema manifest incompatibile")
    excluded = manifest["exclude_from_analysis"].astype(str).str.lower().isin({"true", "1", "yes"})
    frame = manifest.loc[~excluded].copy()
    ids = frame["canonical_campaign_id"]
    if ids.eq("").any() or not ids.is_unique or not frame["source_file"].is_unique:
        raise ValueError("Campagne canoniche nulle o duplicate nel manifest")
    return frame


def read_inventory(path, key):
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    if key not in frame or not frame[key].is_unique:
        raise ValueError(f"Inventario incompatibile o duplicato: {path.name}")
    return {str(row[key]): json_value(row) for row in frame.to_dict("records")}


@dataclass
class AnalysisResult:
    root: Path
    report: dict
    frames: dict[str, pd.DataFrame] = field(repr=False)
    closed: bool = False

    def close(self):
        if not self.closed:
            # root is minted internally by mkdtemp; never accept an export destination here.
            temp_root = Path(tempfile.gettempdir()).resolve()
            resolved = self.root.resolve()
            if resolved.parent != temp_root or not resolved.name.startswith("mt_analysis_"):
                raise ValueError("Directory di anteprima non riconosciuta")
            shutil.rmtree(resolved)
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def session_statistics(frame, campaign_id, source_file, profile, baseline, config_dir, suitability=True, *, runtime=False, disabled=()):
    from .session_qc.metrics import build_reference_frame, compute_segment_metrics, compute_session_metrics
    from .session_qc.segment_status import compute_segment_status
    from .session_qc.session_status import compute_drift_assessability, compute_session_status
    from .session_qc.suitability import compute_all_suitability
    from .repeated_routes.config import load_config
    from .repeated_routes.tracks import prepare_campaign_tracks
    from .repeated_routes.campaign_inventory import build_campaign_inventory_row

    policy = pd.read_csv(config_dir / "flag_policy.csv")
    families = dict(zip(policy.flag_name, policy.reason_family))
    # Standard Session QC has always used recommended's own flags/segmentation.
    # A custom run instead evaluates its own mask consistently in all metric slots;
    # true baseline cross-profile counts remain a separate, explicitly named comparison.
    ref = frame.copy() if runtime else build_reference_frame(baseline)
    if runtime:
        for p in PROFILES:
            ref[f"keep_{p}_true"] = frame[f"keep_{profile}"].to_numpy()
    segments = compute_segment_metrics(ref, campaign_id, source_file, families)
    metrics = compute_session_metrics(ref, segments, campaign_id, source_file, families)
    metrics.update(compute_drift_assessability(ref, metrics["nominal_time_span_s"], metrics["n_segments"],
                                              metrics["keep_fraction_recommended"], "recommended_session"))
    session_policy = pd.read_csv(config_dir / "session_qc_policy.csv")
    segment_qc = compute_segment_status(segments, session_policy, "recommended_session")
    session_qc = compute_session_status(pd.DataFrame([metrics]), session_policy, "recommended_session")
    suit = compute_all_suitability(session_qc, pd.read_csv(config_dir / "session_suitability_policy.csv"), segment_qc) if suitability else pd.DataFrame()
    flags = [f for f in policy.loc[policy.action != "NOT_APPLICABLE", "flag_name"] if f in frame]
    flag_frame = frame[flags].fillna(False).astype(bool)
    counts = {f: int(flag_frame[f].sum()) for f in flags}
    family_counts = {str(family): int(flag_frame[[f for f in flags if families[f] == family]].any(axis=1).sum())
                     for family in sorted(set(families.values()))}
    keep = frame[f"keep_{profile}"].astype(bool)
    ranges = {}
    for name, column in (("temperature", "Temp[°C]"), ("humidity", "Hum[%]"), ("pressure", "Press[mbar]"), ("speed", "speed_device_kmh")):
        values = pd.to_numeric(frame.get(column, pd.Series(dtype=float)), errors="coerce")
        valid = values.loc[keep] if len(values) else values
        ranges[name] = {"min": values.min(), "mean": values.mean(), "max": values.max(),
                        "kept_min": valid.min(), "kept_mean": valid.mean(), "kept_max": valid.max()}
    cfg = load_config(str(config_dir / "repeated_routes_recommended.yaml"))
    geometry_frame = frame.copy()
    valid_geometry = pd.to_numeric(frame.Lat, errors="coerce").between(-90, 90) & pd.to_numeric(frame.Lon, errors="coerce").between(-180, 180)
    geometry_frame["use_for_route_mapping"] &= valid_geometry
    tracks = prepare_campaign_tracks(campaign_id, geometry_frame, cfg)
    route = build_campaign_inventory_row(campaign_id, source_file, geometry_frame, tracks, cfg)
    disabled_flags = {flag for group in disabled for flag in GROUPS[group][2]}
    return json_value({"campaign_id": campaign_id, "source_file": source_file, "profile": profile,
        "rows": len(ref), "kept": int(keep.sum()), "flagged": int(flag_frame.any(axis=1).sum()),
        "valid_percent": float(keep.mean() * 100), "flags": counts, "flag_families": family_counts,
        "flag_evaluation": {f: "Disattivato" if f in disabled_flags else "Non disponibile" if frame[f].isna().all() else "Valutato" for f in flags},
        "keep_by_profile": {p: int(baseline[p][f"keep_{p}"].sum()) for p in PROFILES},
        "profile_comparison_basis": "Three independent official-profile runs; custom keep is reported separately",
        "duration_s": metrics["nominal_time_span_s"], "distance_km": metrics["observed_distance_km"],
        "start": metrics["campaign_start_timestamp"], "end": metrics["campaign_end_timestamp"],
        "ranges": ranges, "session_qc": session_qc.iloc[0].to_dict(),
        "session_policy_reference": "recommended_session; custom mask in all metric slots" if runtime else "recommended_session; recommended reference and three real profile masks",
        "suitability": dict(zip(suit.get("analysis_type", []), suit.get("suitability_status", []))),
        "suitability_enabled": suitability, "route_quality": route["campaign_quality_flag"],
        "route_matching_eligible": route["campaign_quality_flag"] != "excluded",
        "route_matching_note": "Eligibility from existing track/inventory engine; no matching or cache writes",
        "warmup_rows": int(frame["qc_sensor_stabilization"].sum()),
        "gap_rows": int(frame["qc_time_gap"].sum()), "gps_jump_rows": int(frame["qc_spatial_jump"].sum())})


class SessionAnalysisService:
    """Mixin: shares the workspace and identity of ApplicationService."""

    def list_qc_profiles(self):
        return list(PROFILES)

    def describe_qc_settings(self, profile="recommended", active_controls=None, overrides=None):
        return describe_settings(self.workspace / "config", profile, active_controls, overrides)

    def validate_custom_settings(self, profile="recommended", active_controls=None, overrides=None):
        return validate_settings(self.workspace / "config", profile, active_controls, overrides)

    def save_analysis_preset(self, name, *, description="", profile="recommended", active_controls=None, overrides=None):
        settings = self.validate_custom_settings(profile, active_controls, overrides)
        payload = preset_payload(settings, name, description)
        root = safe_child(self.workspace, "user_presets")
        if root != self.workspace.resolve() / "user_presets":
            raise ValueError("Directory preset reindirizzata non consentita")
        root.mkdir(exist_ok=True)
        path = root / f"{uuid.uuid4().hex}.json"
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        return str(path)

    def load_analysis_preset(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {"schema_version", "origin_profile", "active_controls", "overrides", "config_fingerprint", "name", "date", "description"}
        if not isinstance(payload, dict) or not required <= payload.keys():
            raise ValueError("Preset incompatibile: campi obbligatori mancanti")
        if type(payload.get("schema_version")) is not int or payload.get("schema_version") != SCHEMA_VERSION or payload.get("config_fingerprint") != settings_fingerprint(self.workspace / "config"):
            raise ValueError("Preset incompatibile: schema o configurazioni di origine cambiati; ricreare il preset")
        self.validate_custom_settings(payload["origin_profile"], payload["active_controls"], payload["overrides"])
        return payload

    def list_sessions(self, *, search="", date_from=None, date_to=None, batch=None, status=None, cancellation=None):
        self._require_valid()
        token = cancellation or CancellationToken()
        manifest = canonical_manifest(self.workspace)
        inventory = read_inventory(self.workspace / "outputs/session_qc/session_qc_inventory.csv", "canonical_campaign_id")
        suit_path = self.workspace / "outputs/session_qc/session_suitability_inventory.csv"
        suit = pd.read_csv(suit_path) if suit_path.exists() else pd.DataFrame()
        rows = []
        for item in manifest.to_dict("records"):
            token.checkpoint()
            campaign_id, source = item["canonical_campaign_id"], item["source_file"]
            raw = safe_child(self.workspace / "data/raw", source)
            row = inventory.get(campaign_id, {})
            if not row and raw.exists():
                from .map_preview import read_track
                track = read_track(raw, campaign_id, source, self.workspace / "config", token)
                row = {"campaign_start_timestamp": track["start"], "campaign_end_timestamp": track["end"],
                       "n_raw": track["rows"], "nominal_time_span_s": track["duration_s"], "observed_distance_km": track["distance_km"]}
            available = [p for p in PROFILES if safe_child(self.workspace / "outputs" / p, campaign_id).is_dir()]
            start = pd.to_datetime(row.get("campaign_start_timestamp"), utc=True)
            local = start.tz_convert("Europe/Rome") if pd.notna(start) else None
            date = str(local.date()) if local is not None else ""
            suitable = {}
            if not suit.empty:
                selected = suit[suit.canonical_campaign_id == campaign_id]
                suitable = dict(zip(selected.analysis_type, selected.suitability_status))
            entry = {"campaign_id": campaign_id, "date": date, "start": row.get("campaign_start_timestamp"),
                     "end": row.get("campaign_end_timestamp"), "source_file": source,
                     "batch": Path(source).parts[0] if len(Path(source).parts) > 1 else "",
                     "rows": row.get("n_raw"), "duration_s": row.get("nominal_time_span_s"),
                     "distance_km": row.get("observed_distance_km"), "session_qc_status": row.get("session_qc_status", "Non disponibile"),
                     "suitability": suitable, "available_outputs": available, "raw_available": raw.is_file()}
            if search.casefold() not in (campaign_id + " " + source).casefold():
                continue
            if batch and entry["batch"] != batch or status and entry["session_qc_status"] != status:
                continue
            if date_from and date < date_from or date_to and date > date_to:
                continue
            rows.append(json_value(entry))
        return rows

    def inspect_session(self, campaign_id, *, cancellation=None):
        rows = self.list_sessions(cancellation=cancellation)
        for row in rows:
            if row["campaign_id"] == campaign_id:
                return row
        raise ValueError(f"Campagna non registrata: {campaign_id}")

    def _selected_sessions(self, campaign_ids):
        ids = list(dict.fromkeys(campaign_ids))
        if not ids:
            raise ValueError("Seleziona almeno una sessione")
        entries = {r["canonical_campaign_id"]: r for r in canonical_manifest(self.workspace).to_dict("records")}
        if set(ids) - entries.keys():
            raise ValueError("Sessioni non registrate: " + ", ".join(sorted(set(ids) - entries.keys())))
        return [entries[i] for i in ids]

    def preview_tracks(self, campaign_ids, *, cancellation=None, emit=None):
        from .map_preview import load_preview
        self._require_valid()
        return load_preview(self.workspace, self._selected_sessions(campaign_ids), cancellation or CancellationToken())

    def preview_qc(self, campaign_ids, *, profile="recommended", active_controls=None, overrides=None, cancellation=None, emit=None):
        from .pipeline import MeteotrackerQC
        from .application import AppEvent
        from .analysis_plots import write_session_figures

        self._require_valid()
        token = cancellation or CancellationToken()
        token.checkpoint()
        selected = self._selected_sessions(campaign_ids)
        settings = self.validate_custom_settings(profile, active_controls, overrides)
        config_dir = self.workspace / "config"
        sources = {r["canonical_campaign_id"]: safe_child(self.workspace / "data/raw", r["source_file"]) for r in selected}
        inputs = [self.workspace / "data/manifests/campaign_manifest.csv", *sources.values(), *sorted(config_dir.glob("*"))]
        hashes = {str(p.relative_to(self.workspace)): file_hash(p) for p in inputs if p.is_file()}
        root = Path(tempfile.mkdtemp(prefix="mt_analysis_"))
        analysis_id = uuid.uuid4().hex
        events = []
        result = AnalysisResult(root, {}, {})
        try:
            (root / "config").mkdir()
            for p in config_dir.iterdir():
                if p.is_file():
                    shutil.copyfile(p, root / "config" / p.name)
            write_json(root / "settings.json", settings)
            summaries = []
            for number, item in enumerate(selected):
                token.checkpoint()
                cid, source = item["canonical_campaign_id"], item["source_file"]
                event = AppEvent("phase_started", analysis_id, "preview_qc", datetime.now(timezone.utc).isoformat(),
                                 f"Anteprima QC {number + 1}/{len(selected)}", number / len(selected), campaign_id=cid)
                events.append(event.__dict__)
                if emit:
                    emit(event)
                frames = {}
                directory = root / "sessions" / f"{number:04d}"
                for p in PROFILES:
                    token.checkpoint()
                    qc = MeteotrackerQC(root / "config" / f"qc_{p}.yaml")
                    frames[p] = qc.process_file(sources[cid], directory / p, cancellation=token, diagnostics=False)
                frame = frames[profile]
                if settings["differences"] or settings["disabled_controls"]:
                    qc = MeteotrackerQC(root / "config" / f"qc_{profile}.yaml")
                    qc.config = settings["config"]
                    frame = qc.process_file(sources[cid], directory / "custom", cancellation=token, diagnostics=False)
                token.checkpoint()
                runtime = bool(settings["differences"] or settings["disabled_controls"])
                summary = session_statistics(frame, cid, source, profile, frames, root / "config", "suitability" in settings["active_controls"],
                                             runtime=runtime, disabled=settings["disabled_controls"])
                summary["disabled_controls"] = settings["disabled_controls"]
                summary["directory"] = directory.relative_to(root).as_posix()
                summary["selected_directory"] = (directory / ("custom" if settings["differences"] or settings["disabled_controls"] else profile)).relative_to(root).as_posix()
                summaries.append(summary)
                result.frames[cid] = frame
                for p in PROFILES:
                    frames[p].loc[frames[p][f"keep_{p}"]].to_csv(directory / f"kept_{p}.csv", index=False)
                write_session_figures(frame, summary, directory, token)
            for rel, digest in hashes.items():
                token.checkpoint()
                if file_hash(self.workspace / rel) != digest:
                    raise ValueError("Input cambiati durante l'anteprima; ripetere l'analisi")
            result.report = {"analysis_id": analysis_id, "mode": "Anteprima read-only", "status": "completed",
                "created_at": datetime.now(timezone.utc).isoformat(), "workspace": str(self.workspace),
                "settings": settings, "provenance": hashes, "sessions": summaries,
                "aggregated_observations": False, "events": events, "preview_directory": str(root)}
            write_json(root / "report.json", result.report)
            text = "# Analisi personalizzata — anteprima read-only\n\nSessioni separate; nessuna promozione ufficiale.\n\n"
            for summary in summaries:
                text += (f"## {summary['campaign_id']}\n\nRighe: {summary['rows']}; mantenute: {summary['kept']}; "
                         f"flaggate: {summary['flagged']}; durata: {summary['duration_s']} s; distanza: {summary['distance_km']} km.\n\n"
                         f"Keep (tre esecuzioni ufficiali): {summary['keep_by_profile']}.\n\n"
                         f"Suitability: {summary['suitability']}; route eligibility: {summary['route_matching_eligible']}.\n\n")
            (root / "report.md").write_text(text, encoding="utf-8")
            token.checkpoint()
            if emit:
                emit(AppEvent("phase_completed", analysis_id, "preview_qc", datetime.now(timezone.utc).isoformat(), "Anteprima completata", 1.0))
            return result
        except BaseException:
            result.close()
            raise

    def compare_sessions(self, campaign_ids=None, *, analysis=None, **kwargs):
        if analysis is None:
            with self.preview_qc(campaign_ids, **kwargs) as preview:
                return self.compare_sessions(analysis=preview)
        return [{"campaign_id": r["campaign_id"], "start": r["start"], "end": r["end"], "rows": r["rows"],
                 "duration_s": r["duration_s"], "distance_km": r["distance_km"], "valid_percent": r["valid_percent"],
                 "main_flags": "; ".join(f"{k}: {v}" for k, v in sorted(r["flags"].items(), key=lambda i: -i[1])[:5] if v),
                 "temperature_mean": r["ranges"]["temperature"]["mean"], "temperature_min": r["ranges"]["temperature"]["min"],
                 "temperature_max": r["ranges"]["temperature"]["max"], "speed_mean": r["ranges"]["speed"]["mean"],
                 "suitability": r["suitability"], "route_matching_eligible": r["route_matching_eligible"]} for r in analysis.report["sessions"]]

    def export_custom_analysis(self, analysis, *, formats=None, cancellation=None):
        from .map_preview import export_geodata
        if analysis.closed:
            raise ValueError("Anteprima già eliminata")
        if analysis.report.get("workspace") != str(self.workspace):
            raise ValueError("Analisi appartenente a un'altra workspace")
        formats = set(formats if formats is not None else ("csv", "parquet", "markdown", "json", "config", "figures", "gpkg", "geojson"))
        if not formats:
            raise ValueError("Selezionare almeno un formato export")
        if formats - {"csv", "parquet", "markdown", "json", "config", "figures", "gpkg", "geojson"}:
            raise ValueError("Formato export non supportato")
        token = cancellation or CancellationToken()
        token.checkpoint()
        custom = safe_child(self.workspace / "outputs", "custom_analyses")
        # Do not follow a redirected custom-output tree into official data.
        if custom != self.workspace.resolve() / "outputs/custom_analyses":
            raise ValueError("Directory custom reindirizzata non consentita")
        custom.mkdir(exist_ok=True)
        destination = custom / uuid.uuid4().hex
        destination.mkdir()
        try:
            for summary in analysis.report["sessions"]:
                token.checkpoint()
                src = safe_child(analysis.root, summary["selected_directory"])
                out = destination / summary["directory"]
                out.mkdir(parents=True)
                if "csv" in formats:
                    for path in safe_child(analysis.root, summary["directory"]).glob("kept_*.csv"):
                        shutil.copyfile(path, out / path.name)
                for path in src.iterdir():
                    if path.suffix == ".csv" and "csv" in formats or path.suffix == ".parquet" and "parquet" in formats:
                        shutil.copyfile(path, out / path.name)
                if "figures" in formats:
                    for path in safe_child(analysis.root, summary["directory"]).glob("*.png"):
                        shutil.copyfile(path, out / path.name)
                frame = analysis.frames[summary["campaign_id"]]
                export_geodata(frame, out, formats, campaign_id=summary["campaign_id"])
            for kind, name in (("markdown", "report.md"), ("json", "report.json"), ("config", "settings.json")):
                if kind in formats:
                    shutil.copyfile(analysis.root / name, destination / name)
            # Every export carries enough provenance to identify it, even data-only selections.
            write_json(destination / "provenance.json", {k: analysis.report[k] for k in ("analysis_id", "created_at", "settings", "provenance")})
            if "config" in formats:
                shutil.copytree(analysis.root / "config", destination / "config")
            token.checkpoint()
            return str(destination)
        except BaseException:
            shutil.rmtree(destination)
            raise

    def export_track_preview(self, preview, *, style=None, frames=None, formats=None, cancellation=None):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from .map_preview import draw_map, export_geodata
        token = cancellation or CancellationToken()
        token.checkpoint()
        style = style or {}
        formats = set(formats if formats is not None else ("figures", "gpkg", "geojson", "config"))
        custom = safe_child(self.workspace / "outputs", "custom_analyses")
        if custom != self.workspace.resolve() / "outputs/custom_analyses":
            raise ValueError("Directory custom reindirizzata non consentita")
        custom.mkdir(exist_ok=True)
        destination = custom / uuid.uuid4().hex
        destination.mkdir()
        try:
            if "figures" in formats:
                figure = Figure(figsize=(10, 7), layout="constrained")
                FigureCanvasAgg(figure)
                draw_map(figure.subplots(), preview, frames=frames, **style)
                figure.savefig(destination / "map.png", dpi=150)
                figure.clear()
            visible = set(style.get("visible", [t["campaign_id"] for t in preview["tracks"]]))
            for number, track in enumerate(preview["tracks"]):
                token.checkpoint()
                if track["campaign_id"] not in visible:
                    continue
                directory = destination / f"session_{number:04d}"
                directory.mkdir()
                data = (frames or {}).get(track["campaign_id"], track["points"])
                export_geodata(data, directory, formats, campaign_id=track["campaign_id"], geographic_crs=track["geographic_crs"])
            metadata = {"mode": "Exploratory map; not official spatial density", "metric_crs": preview["metric_crs"],
                        "geographic_crs": preview["geographic_crs"], "boundary": preview["boundary_note"], "style": style,
                        "legend": {t["campaign_id"]: t["color"] for t in preview["tracks"]},
                        "sessions": [{k: v for k, v in t.items() if k != "points"} for t in preview["tracks"]]}
            write_json(destination / "map_configuration.json", metadata)
            token.checkpoint()
            return str(destination)
        except BaseException:
            shutil.rmtree(destination)
            raise
