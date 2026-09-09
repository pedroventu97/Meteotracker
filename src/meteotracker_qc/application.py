"""Shared application services for the portable CLI and future clients."""
from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from .ingestion import PROFILE_NAMES, ValidationResult, apply_manifest_and_qc, promote, validate_file
from .pipeline import run_qc

WORKSPACE_MARKERS = ("data/raw", "data/manifests", "config", "outputs", "logs")


@dataclass(frozen=True)
class AppEvent:
    event: str
    run_id: str
    phase: str
    timestamp_utc: str
    message: str
    progress: float | None = None
    level: str = "info"
    campaign_id: str | None = None
    source_file: str | None = None
    report_path: str | None = None


@dataclass
class DiscoveryResult:
    source_file: str
    absolute_path: str
    batch: str
    validation: dict[str, object]


class WorkspaceError(RuntimeError):
    """Raised when a workspace cannot safely host an operation."""


class WorkspaceLock:
    def __init__(self, workspace: Path, run_id: str):
        self.workspace = workspace.resolve()
        self.path = self.workspace / "logs" / ".meteotracker.lock"
        self.run_id = run_id
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            data = _read_json(self.path)
            if data is None:
                raise WorkspaceError("workspace lock is unreadable; remove it only after manual inspection")
            pid = int(data.get("pid", 0))
            if pid and _process_alive(pid):
                raise WorkspaceError(f"workspace is locked by PID {pid} (run {data.get('run_id', '?')})")
            if data.get("host") == socket.gethostname() and pid:
                self.path.unlink()
            else:
                raise WorkspaceError("workspace lock cannot be proven stale on another host")
        payload = {"pid": os.getpid(), "timestamp_utc": _now(), "run_id": self.run_id,
                   "workspace": str(self.workspace), "host": socket.gethostname(),
                   "process_version": "meteotracker-qc/0.1.0"}
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except FileExistsError as exc:
            raise WorkspaceError("workspace lock was acquired by another process") from exc
        self.acquired = True

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False

    def __enter__(self) -> "WorkspaceLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


class ApplicationService:
    def __init__(self, workspace: str | Path | None = None, emit: Callable[[AppEvent], None] | None = None):
        self.workspace = resolve_workspace(workspace)
        self.emit_callback = emit
        self.workspace_error = self._validate_workspace()

    def doctor(self) -> dict[str, object]:
        return {"workspace": str(self.workspace), "valid": self.workspace_error is None,
                "missing": self._missing_markers(), "python": os.sys.version,
                "package": "meteotracker_qc", "workspace_source": workspace_source(self.workspace)}

    def status(self) -> dict[str, object]:
        self._require_valid()
        manifest = self.workspace / "data/manifests/campaign_manifest.csv"
        registered = int(pd.read_csv(manifest).shape[0]) if manifest.exists() else 0
        discovered = self.discover(include_registered=False)
        return {"workspace": str(self.workspace), "registered_files": registered,
                "new_files": len(discovered), "last_run": self._last_run(),
                "lock": _read_json(self.workspace / "logs/.meteotracker.lock")}

    def discover(self, paths: Iterable[str | Path] | None = None, *, include_registered: bool = True) -> list[DiscoveryResult]:
        self._require_valid()
        raw_root = self.workspace / "data/raw"
        manifest_path = self.workspace / "data/manifests/campaign_manifest.csv"
        manifest = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
        registered = set(manifest.get("source_file", pd.Series(dtype=str)).astype(str))
        roots = [Path(p).expanduser().resolve() for p in paths] if paths else [raw_root]
        files: list[Path] = []
        for root in roots:
            if root.is_file() and root.suffix.lower() == ".csv":
                files.append(root)
            elif root.is_dir():
                files.extend(root.rglob("*.csv"))
        results: list[DiscoveryResult] = []
        for path in sorted(set(files)):
            inside_raw = _is_relative_to(path, raw_root)
            rel = path.relative_to(raw_root).as_posix() if inside_raw else path.name
            is_registered = inside_raw and rel in registered
            if is_registered and not include_registered:
                continue
            validation = asdict(validate_file(path, raw_root if inside_raw else path.parent, manifest))
            if is_registered:
                validation["classification"] = "registered"
                validation["canonical_source_file"] = rel
                validation["blocking_errors"] = []
            batch = rel.split("/", 1)[0] if inside_raw else path.parent.name
            results.append(DiscoveryResult(rel, str(path), batch, validation))
        return results

    def check(self, paths: Iterable[str | Path] | None = None, *, new_only: bool = False) -> dict[str, object]:
        run_id = str(uuid.uuid4())
        started = _now()
        self._event(run_id, "discover", "run_started", "Batch discovery started")
        discovered = self.discover(paths, include_registered=not new_only)
        new_items = [item for item in discovered if item.validation.get("classification") != "registered"]
        for item in discovered:
            self._event(run_id, "discover", "file_discovered", item.source_file,
                        campaign_id=str(item.validation.get("proposed_campaign_id") or ""), source_file=item.source_file)
        blocking = [item for item in new_items if item.validation.get("blocking_errors") or item.validation.get("classification") == "ambiguous"]
        qc_error = None
        preview: dict[str, object] = {}
        if not blocking and new_items:
            try:
                with tempfile.TemporaryDirectory(prefix="meteotracker_check_") as temp:
                    stage = Path(temp)
                    internal = all(_is_relative_to(Path(item.absolute_path), self.workspace / "data/raw") for item in new_items)
                    if internal:
                        preview = apply_manifest_and_qc(self.workspace, "batch", stage, {"results": [item.validation for item in new_items]})
                    else:
                        self._temporary_qc(new_items, stage)
                        preview = {"suitability": "unavailable for external files until copied into data/raw"}
            except Exception as exc:
                qc_error = f"temporary QC failed: {type(exc).__name__}: {exc}"
        status = "fail" if blocking or qc_error else ("warning" if any(item.validation.get("warnings") for item in new_items) else "pass")
        report = self._write_check_reports(run_id, discovered, status, qc_error, preview)
        payload = {"run_id": run_id, "status": status, "started_at": started, "finished_at": _now(),
                   "results": [asdict(item) for item in discovered],
                   "validation_results": [item.validation for item in new_items],
                   "planned_official_targets": self._targets(new_items), "qc_error": qc_error,
                   "report_path": str(report["markdown"]), "json_report_path": str(report["json"])}
        self._event(run_id, "check", "phase_completed", f"Checked {len(new_items)} new CSV files", 1.0,
                    report_path=str(report["markdown"]))
        return payload

    def apply(self, paths: Iterable[str | Path] | None = None, *, check: dict[str, object] | None = None) -> dict[str, object]:
        self._require_valid()
        check = check or self.check(paths, new_only=paths is None)
        if check.get("status") not in {"pass", "warning"}:
            raise WorkspaceError("apply blocked because check did not pass")
        if any(not _is_relative_to(Path(item["absolute_path"]), self.workspace / "data/raw")
               for item in check.get("results", [])):
            raise WorkspaceError("external CSVs require explicit copy into data/raw before apply")
        results = [ValidationResult(**item) for item in check.get("validation_results", [])
                   if item.get("classification") == "canonical"]
        if not results:
            raise WorkspaceError("apply requires at least one new canonical CSV")
        run_id = str(uuid.uuid4())
        ledger = self._ledger_start(run_id, "apply", results)
        try:
            with WorkspaceLock(self.workspace, run_id):
                self._event(run_id, "apply", "phase_started", "Building isolated staging")
                with tempfile.TemporaryDirectory(prefix=f"meteotracker_apply_{run_id}_") as temp:
                    stage = Path(temp)
                    built = apply_manifest_and_qc(self.workspace, "batch", stage, {"results": [asdict(r) for r in results]})
                    self._run_global_analyses(stage, built["canonical_ids"])
                    report = {"run_id": run_id, "status": "staged", "campaigns": built["canonical_ids"],
                              "global_analysis_invocations": 1, "validation": check}
                    report_path = stage / "outputs/ingestion/batch_ingestion_report.json"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_json(report_path, report)
                    targets = [Path("data/manifests/campaign_manifest.csv")]
                    targets.extend(Path("outputs") / name for name in (*PROFILE_NAMES, "session_qc", "repeated_routes", "spatial_density", "temporal_drift", "ingestion"))
                    promote(stage, self.workspace, targets)
                self._ledger_finish(ledger, "completed", report_path=str(self.workspace / "outputs/ingestion/batch_ingestion_report.json"))
                self._event(run_id, "apply", "run_completed", "Batch promoted", 1.0)
        except Exception as exc:
            self._ledger_finish(ledger, "failed", error=f"{type(exc).__name__}: {exc}", rollback=True)
            self._event(run_id, "apply", "run_failed", str(exc), level="error")
            raise
        return {"run_id": run_id, "status": "completed", "report_path": str(self.workspace / "outputs/ingestion/batch_ingestion_report.json")}

    def run(self, paths: Iterable[str | Path] | None = None, *, yes: bool = False) -> dict[str, object]:
        check = self.check(paths, new_only=paths is None)
        if check["status"] not in {"pass", "warning"}:
            return check | {"status": "blocked"}
        if not yes and input("Apply this batch to the workspace? [y/N] ").strip().lower() not in {"y", "yes"}:
            return check | {"status": "cancelled"}
        return self.apply(paths, check=check)

    def history(self, run_id: str | None = None) -> list[dict[str, object]] | dict[str, object] | None:
        entries = _read_json(self.workspace / "logs/run_ledger.json") or []
        if run_id is None:
            return entries
        return next((entry for entry in entries if entry.get("run_id") == run_id), None)

    def open_report(self, run_id: str | None = None) -> str | None:
        record = self.history(run_id)
        return record.get("report_path") if isinstance(record, dict) else None

    def _temporary_qc(self, items: list[DiscoveryResult], stage: Path) -> None:
        for item in items:
            source = Path(item.absolute_path)
            run_qc(source.parent, stage / source.parent.name,
                   self.workspace / "config/qc_recommended.yaml", include_all_files=True)

    def _run_global_analyses(self, staging: Path, canonical_ids: list[str]) -> dict[str, object]:
        from .repeated_routes.config import load_config
        from .repeated_routes.pipeline import run_pipeline, write_outputs
        from .spatial_density.pipeline import build_density_grid, run_density_analysis, sensitivity_summary
        from .temporal_drift_pipeline import run_temporal_drift
        raw = self.workspace / "data/raw"
        outputs = staging / "outputs"
        manifest = staging / "data/manifests/campaign_manifest.csv"
        for name in ("repeated_routes", "spatial_density", "temporal_drift"):
            shutil.copytree(self.workspace / "outputs" / name, outputs / name, dirs_exist_ok=True)
        config = load_config(str(self.workspace / "config/repeated_routes_recommended.yaml"))
        rr = run_pipeline(raw_dir=raw, qc_output_dir=outputs / "recommended",
                          qc_config_path=self.workspace / "config/qc_recommended.yaml", qc_profile="recommended",
                          manifest_path=manifest, rr_config=config, refresh_qc=False,
                          cache_dir=outputs / "repeated_routes/cache")
        write_outputs(rr, outputs / "repeated_routes")
        tracks, xy, _ = run_density_analysis(raw, outputs / "recommended", manifest, config)
        grid = build_density_grid(tracks, xy, 50.0, config.crs_metric_epsg)
        grid.to_file(outputs / "spatial_density/meteotracker_coverage_50m.gpkg", layer="coverage_cells", driver="GPKG")
        grid.drop(columns="geometry").to_csv(outputs / "spatial_density/meteotracker_coverage_50m.csv", index=False)
        sensitivity_summary(tracks, xy, [25.0, 50.0, 100.0], config.crs_metric_epsg).to_csv(
            outputs / "spatial_density/sensitivity_cell_size_comparison.csv", index=False)
        run_temporal_drift(root=staging, output_root=outputs / "temporal_drift", campaign_ids=canonical_ids, progress=False)
        return {"cache_stats": rr.cache_stats, "timings": rr.timings, "invocations": 1}

    def _write_check_reports(self, run_id: str, discovered: list[DiscoveryResult], status: str,
                             qc_error: str | None, preview: dict[str, object]) -> dict[str, Path]:
        report_dir = self.workspace / "logs/check_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        payload = {"run_id": run_id, "status": status, "files": [asdict(item) for item in discovered],
                   "qc_error": qc_error, "preview": {key: str(value) for key, value in preview.items() if key != "manifest"}}
        json_path = report_dir / f"{run_id}.json"
        markdown_path = report_dir / f"{run_id}.md"
        _atomic_json(json_path, payload)
        lines = [f"# Meteotracker check {run_id}", "", f"Status: **{status}**", "", "| Batch | CSV | Classification | Rows | Period | Errors |", "|---|---|---|---:|---|---|"]
        for item in discovered:
            value = item.validation
            period = f"{value.get('time_start_utc')} - {value.get('time_end_utc')}"
            errors = "; ".join(value.get("blocking_errors", [])) or "; ".join(value.get("warnings", []))
            lines.append(f"| {item.batch} | {item.source_file} | {value.get('classification')} | {value.get('rows', 0)} | {period} | {errors} |")
        markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"json": json_path, "markdown": markdown_path}

    def _ledger_start(self, run_id: str, command: str, results: list[ValidationResult]) -> dict[str, object]:
        record = {"run_id": run_id, "started_at": _now(), "finished_at": None, "workspace": str(self.workspace),
                  "command": command, "status": "running", "inputs": {r.source_file: r.file_sha256 for r in results},
                  "campaigns": [r.proposed_campaign_id for r in results], "phases_completed": [], "rollback": False}
        entries = _read_json(self.workspace / "logs/run_ledger.json") or []
        entries.append(record)
        _atomic_json(self.workspace / "logs/run_ledger.json", entries)
        return record

    def _ledger_finish(self, record: dict[str, object], status: str, **updates: object) -> None:
        record.update(updates, status=status, finished_at=_now())
        entries = _read_json(self.workspace / "logs/run_ledger.json") or []
        for index, entry in enumerate(entries):
            if entry.get("run_id") == record["run_id"]:
                entries[index] = record
        _atomic_json(self.workspace / "logs/run_ledger.json", entries)

    def _last_run(self) -> dict[str, object] | None:
        entries = self.history()
        return entries[-1] if entries else None

    def _targets(self, results: list[DiscoveryResult]) -> list[str]:
        return ["data/manifests/campaign_manifest.csv", "outputs/{permissive,recommended,restrictive}/",
                "outputs/session_qc/", "outputs/repeated_routes/", "outputs/spatial_density/", "outputs/temporal_drift/"] if results else []

    def _event(self, run_id: str, phase: str, event: str, message: str, progress: float | None = None,
               level: str = "info", campaign_id: str | None = None, source_file: str | None = None,
               report_path: str | None = None) -> None:
        if self.emit_callback:
            self.emit_callback(AppEvent(event, run_id, phase, _now(), message, progress, level, campaign_id, source_file, report_path))

    def _missing_markers(self) -> list[str]:
        return [item for item in WORKSPACE_MARKERS if not (self.workspace / item).exists()]

    def _validate_workspace(self) -> str | None:
        missing = self._missing_markers()
        return "missing workspace folders: " + ", ".join(missing) if missing else None

    def _require_valid(self) -> None:
        if self.workspace_error:
            raise WorkspaceError(self.workspace_error)


def resolve_workspace(explicit: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    elif os.environ.get("METEOTRACKER_WORKSPACE"):
        candidates.append(Path(os.environ["METEOTRACKER_WORKSPACE"]).expanduser())
    else:
        current = Path.cwd().resolve()
        candidates.extend([current, *current.parents])
    for candidate in candidates:
        resolved = candidate.resolve()
        if all((resolved / marker).exists() for marker in WORKSPACE_MARKERS):
            return resolved
    return candidates[0].resolve() if candidates else Path.cwd().resolve()


def workspace_source(workspace: Path) -> str:
    explicit = os.environ.get("METEOTRACKER_WORKSPACE")
    return "environment" if explicit and workspace == Path(explicit).expanduser().resolve() else "explicit-or-search"


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temp.replace(path)


def _read_json(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _process_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True
