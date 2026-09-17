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

from .ingestion import PROFILE_NAMES, ValidationResult, apply_manifest_and_qc, manifest_row, promote, validate_file, sha256_file
from .operation import CancellationToken, OperationCancelled, safe_result_path
from .pipeline import run_qc
from .session_analysis import SessionAnalysisService

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


class ApplicationService(SessionAnalysisService):
    def __init__(self, workspace: str | Path | None = None, emit: Callable[[AppEvent], None] | None = None,
                 *, cancellation: CancellationToken | None = None, read_only: bool = False):
        self.workspace = resolve_workspace(workspace)
        self.emit_callback = emit
        self.workspace_error = self._validate_workspace()
        self.cancellation = cancellation or CancellationToken()
        self.read_only = read_only
        self._run_id = str(uuid.uuid4())

    def lock_status(self) -> dict[str, object] | None:
        path = self.workspace / "logs/.meteotracker.lock"
        return (_read_json(path) or {"error": "Lock illeggibile: verifica manuale necessaria"}) if path.exists() else None

    def doctor(self) -> dict[str, object]:
        return {"workspace": str(self.workspace), "valid": self.workspace_error is None,
                "missing": self._missing_markers(), "python": os.sys.version,
                "package": "meteotracker_qc", "workspace_source": workspace_source(self.workspace)}

    def status(self) -> dict[str, object]:
        self._require_valid()
        manifest = self.workspace / "data/manifests/campaign_manifest.csv"
        frame = pd.read_csv(manifest) if manifest.exists() else pd.DataFrame()
        registered = len(frame)
        discovered = self.discover(include_registered=False)
        return {"workspace": str(self.workspace), "registered_files": registered,
                "registered_campaigns": int(frame.get("canonical_campaign_id", pd.Series(dtype=str)).nunique()),
                "warnings": [f"{i.source_file}: {warning}" for i in discovered for warning in i.validation.get("warnings", [])],
                "new_files": len(discovered), "last_run": self._last_run(),
                "lock": self.lock_status()}

    def discover(self, paths: Iterable[str | Path] | None = None, *, include_registered: bool = True) -> list[DiscoveryResult]:
        self._require_valid()
        raw_root = self.workspace / "data/raw"
        manifest_path = self.workspace / "data/manifests/campaign_manifest.csv"
        manifest = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
        registered = set(manifest.get("source_file", pd.Series(dtype=str)).astype(str))
        roots = [Path(p).expanduser().resolve() for p in paths] if paths else [raw_root]
        files: list[Path] = []
        for root in roots:
            self.cancellation.checkpoint()
            if root.is_file() and root.suffix.lower() == ".csv":
                files.append(root)
            elif root.is_dir():
                files.extend(p.resolve() for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".csv")
            else:
                raise WorkspaceError(f"Cartella o CSV non disponibile: {root}")
        results: list[DiscoveryResult] = []
        for path in sorted(set(files)):
            self.cancellation.checkpoint()
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
            elif validation["classification"] == "canonical" and not validation["blocking_errors"]:
                # Subsequent files in this deterministic batch can reference this
                # canonical trace, even though the real manifest is read-only.
                manifest = pd.concat([manifest, pd.DataFrame([manifest_row(ValidationResult(**validation))])], ignore_index=True)
            owner = next((root for root in roots if root.is_dir() and path.is_relative_to(root)), path.parent)
            batch = rel.split("/", 1)[0] if inside_raw else owner.name
            results.append(DiscoveryResult(rel, str(path), batch, validation))
            self._event(self._run_id, "discover", "file_discovered", rel,
                        source_file=rel, campaign_id=validation.get("proposed_campaign_id"))
        return results

    def check(self, paths: Iterable[str | Path] | None = None, *, new_only: bool = False) -> dict[str, object]:
        self._require_valid()
        self._run_id = str(uuid.uuid4())
        try:
            return self._check(paths, new_only=new_only)
        except OperationCancelled:
            self._event(self._run_id, "check", "run_cancelled", "Controllo annullato")
            if not self.read_only and not self.lock_status():
                with WorkspaceLock(self.workspace, self._run_id):
                    record = self._ledger_start(self._run_id, "check", [])
                    self._ledger_finish(record, "cancelled")
            return {"run_id": self._run_id, "status": "cancelled", "results": []}

    def _check(self, paths: Iterable[str | Path] | None = None, *, new_only: bool = False) -> dict[str, object]:
        run_id = self._run_id
        started = _now()
        self.cancellation.checkpoint()
        snapshot = self._input_snapshot()
        self._event(run_id, "discover", "run_started", "Batch discovery started")
        discovered = self.discover(paths, include_registered=not new_only)
        new_items = [item for item in discovered if item.validation.get("classification") != "registered"]
        blocking = [item for item in new_items if item.validation.get("blocking_errors") or item.validation.get("classification") == "ambiguous"]
        qc_error = None
        preview: dict[str, object] = {}
        per_csv: dict[str, object] = {}
        if not blocking and new_items:
            try:
                self._phase("point_qc", "QC temporaneo e Session QC")
                with tempfile.TemporaryDirectory(prefix="meteotracker_check_", dir=self.workspace / "logs") as temp:
                    stage = Path(temp)
                    internal = all(_is_relative_to(Path(item.absolute_path), self.workspace / "data/raw") for item in new_items)
                    if internal:
                        preview = apply_manifest_and_qc(self.workspace, "batch", stage, {"results": [item.validation for item in new_items]})
                        per_csv = self._csv_preview(preview)
                    else:
                        self._temporary_qc(new_items, stage)
                        preview = {"suitability": "unavailable for external files until copied into data/raw"}
                    self.cancellation.checkpoint()
            except OperationCancelled:
                raise
            except Exception as exc:
                qc_error = f"temporary QC failed: {type(exc).__name__}: {exc}"
        status = "fail" if blocking or qc_error else ("warning" if any(item.validation.get("warnings") for item in new_items) else "pass")
        if snapshot != self._input_snapshot():
            status, qc_error = "fail", "Input della workspace cambiati durante il controllo: ripetere il check"
        self.cancellation.checkpoint()
        report = self._write_check_reports(run_id, discovered, status, qc_error, preview) if not self.read_only else {}
        payload = {"run_id": run_id, "status": status, "started_at": started, "finished_at": _now(),
                   "results": [asdict(item) for item in discovered],
                   "validation_results": [item.validation for item in new_items],
                   "planned_official_targets": self._targets(new_items), "qc_error": qc_error,
                   "report_path": str(report["markdown"]) if report else None,
                   "json_report_path": str(report["json"]) if report else None,
                   "workspace": str(self.workspace), "input_snapshot": snapshot,
                   "per_csv": per_csv, "plan": self._plan(new_items)}
        self._event(run_id, "check", "phase_completed", f"Checked {len(new_items)} new CSV files", 1.0,
                    report_path=payload["report_path"])
        return payload

    def apply(self, paths: Iterable[str | Path] | None = None, *, check: dict[str, object] | None = None) -> dict[str, object]:
        self._require_valid()
        if self.read_only:
            raise WorkspaceError("Workspace aperta in sola lettura: apply vietato")
        check = check or self.check(paths, new_only=paths is None)
        if check.get("status") not in {"pass", "warning"}:
            raise WorkspaceError("apply blocked because check did not pass")
        if any(not _is_relative_to(Path(item["absolute_path"]), self.workspace / "data/raw")
               for item in check.get("results", [])):
            raise WorkspaceError("external CSVs require explicit copy into data/raw before apply")
        results = [ValidationResult(**item) for item in check.get("validation_results", [])
                   if item.get("classification") in {"canonical", "redundant"}]
        if not any(item.classification == "canonical" for item in results):
            raise WorkspaceError("apply requires at least one new canonical CSV")
        run_id = str(uuid.uuid4())
        self._run_id = run_id
        with WorkspaceLock(self.workspace, run_id):
            ledger = self._ledger_start(run_id, "apply", results)
            promoted = False
            try:
                self.cancellation.checkpoint()
                self.validate_check(check)
                self._phase("point_qc", "QC dei punti e Session QC in staging")
                with tempfile.TemporaryDirectory(prefix=f"meteotracker_apply_{run_id}_", dir=self.workspace / "logs") as temp:
                    stage = Path(temp)
                    built = apply_manifest_and_qc(self.workspace, "batch", stage, {"results": [asdict(r) for r in results]})
                    ledger["phases_completed"].extend(["point_qc", "session_qc"])
                    self.cancellation.checkpoint()
                    analyses = self._run_global_analyses(stage, built["canonical_ids"])
                    ledger["phases_completed"].extend(["repeated_routes", "many_to_many_consolidation", "spatial_density", "temporal_drift", "validation"])
                    report = {"run_id": run_id, "status": "staged", "campaigns": built["canonical_ids"],
                              "global_analysis_invocations": 1, "analyses": analyses, "validation": check}
                    report_path = stage / "outputs/ingestion/batch_ingestion_report.json"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_json(report_path, report)
                    targets = [Path("data/manifests/campaign_manifest.csv")]
                    targets.extend(Path("outputs") / name for name in (*PROFILE_NAMES, "session_qc", "repeated_routes", "spatial_density", "temporal_drift", "ingestion"))
                    self.validate_check(check)
                    self.cancellation.checkpoint()
                    self._event(run_id, "promotion", "critical_started",
                                "Promozione in corso: cancellazione al prossimo punto sicuro, con rollback")
                    if self.cancellation.requested:
                        self.cancellation.checkpoint()
                    promote(stage, self.workspace, targets, after_promotion=self.cancellation.checkpoint)
                    promoted = True
                    self._event(run_id, "promotion", "critical_completed", "Promozione completata")
                    ledger["phases_completed"].append("promotion")
                self._ledger_finish(ledger, "completed", report_path=str(self.workspace / "outputs/ingestion/batch_ingestion_report.json"))
                self._event(run_id, "apply", "run_completed", "Batch promoted", 1.0)
            except OperationCancelled:
                self._ledger_finish(ledger, "cancelled", rollback=True)
                self._event(run_id, "apply", "run_cancelled", "Annullato: staging rimosso, eventuale promozione ripristinata")
                return {"run_id": run_id, "status": "cancelled", "rollback": True}
            except Exception as exc:
                self._ledger_finish(ledger, "failed", error=f"{type(exc).__name__}: {exc}", rollback=not promoted)
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
        value = record.get("report_path") if isinstance(record, dict) else None
        return str(self.result_path(value)) if value else None

    def result_path(self, value: str | Path, *, authorized_roots=()) -> Path:
        return safe_result_path(self.workspace, value, authorized_roots=authorized_roots)

    def _phase(self, phase: str, message: str) -> None:
        self.cancellation.checkpoint()
        self._event(self._run_id, phase, "phase_started", message)
        self.cancellation.checkpoint()

    def _input_snapshot(self) -> dict[str, object]:
        """Bind a check to scientific inputs, without persisting data outside the workspace."""
        snapshot = {}
        for base in ("data/raw", "data/manifests", "config", "outputs"):
            for path in sorted((self.workspace / base).rglob("*")):
                self.cancellation.checkpoint()
                if path.is_file():
                    stat = path.stat()
                    snapshot[path.relative_to(self.workspace).as_posix()] = (
                        [stat.st_size, stat.st_mtime_ns] if base == "outputs" else sha256_file(path))
        return snapshot

    def validate_check(self, check: dict[str, object]) -> None:
        """Expensive freshness check, called in the worker and again under the apply lock."""
        if check.get("status") not in {"pass", "warning"}:
            raise WorkspaceError("Controllo non valido")
        if any(item.get("blocking_errors") or item.get("classification") in {"invalid", "ambiguous"}
               for item in check.get("validation_results", [])):
            raise WorkspaceError("CSV invalidi o ambigui: ripetere il controllo")
        if "input_snapshot" in check:
            if check.get("workspace") != str(self.workspace) or check["input_snapshot"] != self._input_snapshot():
                raise WorkspaceError("Input cambiati dopo il check: ripetere il controllo")

    def _plan(self, items: list[DiscoveryResult]) -> dict[str, object]:
        canonical = [i for i in items if i.validation.get("classification") == "canonical"]
        targets = ["data/manifests/campaign_manifest.csv", *[
            f"outputs/{name}" for name in (*PROFILE_NAMES, "session_qc", "repeated_routes", "spatial_density", "temporal_drift", "ingestion")]]
        return {"application_batches": 1 if canonical else 0,
                "batches": sorted({i.batch for i in items}),
                "campaigns": [i.validation["proposed_campaign_id"] for i in canonical],
                "phases": dict.fromkeys(["session_qc", "repeated_routes", "many_to_many_consolidation", "spatial_density", "temporal_drift"], 1 if canonical else 0),
                "targets": targets if canonical else [],
                "backup": "Backup temporaneo dei target durante la promozione; rollback su errore o annullamento. Nessun backup permanente.",
                "stale": [p.relative_to(self.workspace).as_posix() for p in sorted((self.workspace / "outputs").iterdir())
                          if p.relative_to(self.workspace).as_posix() not in targets] + ["reports/ (rapporti storici non rigenerati)"],
                "external": any(not _is_relative_to(Path(i.absolute_path), self.workspace / "data/raw") for i in items)}

    @staticmethod
    def _csv_preview(preview: dict[str, object]) -> dict[str, object]:
        session = preview.get("session", {})
        inventory = session.get("session_qc", pd.DataFrame())
        suitability = session.get("suitability", pd.DataFrame())
        result = {}
        for _, row in inventory.iterrows():
            campaign = str(row["canonical_campaign_id"])
            suits = suitability.loc[suitability.canonical_campaign_id == campaign] if len(suitability) else pd.DataFrame()
            result[campaign] = {"qc": str(row.get("session_qc_status", "")),
                                "suitability": {str(r["analysis_type"]): str(r["suitability_status"]) for _, r in suits.iterrows()},
                                "route_matching": "Pianificato nell'apply globale"}
        return result

    def _temporary_qc(self, items: list[DiscoveryResult], stage: Path) -> None:
        for index, parent in enumerate(sorted({Path(item.absolute_path).parent for item in items})):
            self.cancellation.checkpoint()
            run_qc(parent, stage / str(index),
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
        self._phase("repeated_routes", "Repeated routes e consolidamento many-to-many")
        rr = run_pipeline(raw_dir=raw, qc_output_dir=outputs / "recommended",
                          qc_config_path=self.workspace / "config/qc_recommended.yaml", qc_profile="recommended",
                          manifest_path=manifest, rr_config=config, refresh_qc=False,
                          cache_dir=outputs / "repeated_routes/cache")
        write_outputs(rr, outputs / "repeated_routes")
        self._validate_global_outputs(staging, canonical_ids, rr)
        self._phase("spatial_density", "Densità spaziale")
        tracks, xy, _ = run_density_analysis(raw, outputs / "recommended", manifest, config)
        grid = build_density_grid(tracks, xy, 50.0, config.crs_metric_epsg)
        grid.to_file(outputs / "spatial_density/meteotracker_coverage_50m.gpkg", layer="coverage_cells", driver="GPKG")
        grid.drop(columns="geometry").to_csv(outputs / "spatial_density/meteotracker_coverage_50m.csv", index=False)
        sensitivity_summary(tracks, xy, [25.0, 50.0, 100.0], config.crs_metric_epsg).to_csv(
            outputs / "spatial_density/sensitivity_cell_size_comparison.csv", index=False)
        self._phase("temporal_drift", "Temporal drift")
        run_temporal_drift(root=staging, output_root=outputs / "temporal_drift", campaign_ids=canonical_ids, progress=False)
        self._validate_campaign_inventory(outputs / "temporal_drift/session_temporal_diagnostics.csv", canonical_ids)
        self.cancellation.checkpoint()
        return {"cache_stats": rr.cache_stats, "timings": rr.timings, "invocations": 1,
                "phases": {"session_qc": 1, "repeated_routes": 1, "many_to_many_consolidation": 1,
                           "spatial_density": 1, "temporal_drift": 1}}

    @staticmethod
    def _validate_campaign_inventory(path: Path, canonical_ids: list[str]) -> None:
        inventory = pd.read_csv(path)
        ids = inventory["canonical_campaign_id"].astype(str)
        if not ids.is_unique or set(ids) != set(canonical_ids):
            raise WorkspaceError(f"Staged campaign inventory does not match the manifest: {path}")

    def _validate_global_outputs(self, staging: Path, canonical_ids: list[str], routes: object) -> None:
        from .repeated_routes.memberships import MEMBERSHIP_KEY, SUPPORT_COLUMNS
        self._validate_campaign_inventory(staging / "outputs/session_qc/session_qc_inventory.csv", canonical_ids)
        memberships = routes.point_segment_memberships
        support = routes.point_segment_match_support
        if memberships.duplicated(MEMBERSHIP_KEY).any() or not memberships["membership_id"].is_unique:
            raise WorkspaceError("Staged point/segment memberships are not unique")
        manifest = pd.read_csv(staging / "data/manifests/campaign_manifest.csv")
        expected_sources = set(manifest.loc[manifest.canonical_campaign_id.isin(canonical_ids), "source_file"])
        if set(routes.inventory_df.source_file) != expected_sources or not routes.inventory_df.campaign_id.is_unique:
            raise WorkspaceError("Staged route inventory does not match canonical source files")
        if not set(memberships["campaign_id"]) <= set(routes.inventory_df.campaign_id):
            raise WorkspaceError("Staged memberships contain non-canonical campaigns")
        if not set(memberships.source_file) <= expected_sources:
            raise WorkspaceError("Staged memberships contain non-canonical source files")
        if len(support) and not set(support["membership_id"]) <= set(memberships["membership_id"]):
            raise WorkspaceError("Staged match support references missing memberships")
        if support.duplicated(SUPPORT_COLUMNS).any() or not set(memberships["membership_id"]) <= set(support["membership_id"]):
            raise WorkspaceError("Staged membership support is duplicated or incomplete")

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
                  "campaigns": [r.proposed_campaign_id for r in results if r.classification == "canonical"], "phases_completed": [], "rollback": False}
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
    if os.name == "nt":
        # os.kill(pid, 0) is not a harmless existence probe on Windows.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return ctypes.get_last_error() != 87  # only invalid PID proves absence
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True
