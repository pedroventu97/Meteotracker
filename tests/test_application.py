from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import meteotracker_qc.application as application
from meteotracker_qc.application import ApplicationService, WorkspaceError, WorkspaceLock, resolve_workspace
from meteotracker_qc.cli import build_parser
from meteotracker_qc.ingestion import promote


def make_workspace(tmp_path: Path) -> Path:
    for relative in ("data/raw/batch A", "data/manifests", "config", "outputs", "logs"):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    manifest = pd.DataFrame(columns=["source_file", "file_sha256", "core_content_hash", "canonical_campaign_id",
                                     "duplicate_group_id", "duplicate_type", "is_canonical",
                                     "canonical_source_file", "exclude_from_analysis", "exclude_reason", "keep_raw", "notes"])
    manifest.to_csv(tmp_path / "data/manifests/campaign_manifest.csv", index=False)
    return tmp_path


def test_workspace_resolution_environment_and_external_cwd(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path / "Workspace with spaces")
    monkeypatch.setenv("METEOTRACKER_WORKSPACE", str(workspace))
    monkeypatch.chdir(tmp_path)
    assert resolve_workspace() == workspace.resolve()
    assert ApplicationService().doctor()["workspace"] == str(workspace.resolve())


def test_cli_public_commands_are_explicit():
    parser = build_parser()
    assert set(parser._subparsers._group_actions[0].choices) == {
        "doctor", "status", "discover", "check", "apply", "run", "history",
    }


def test_discover_is_recursive_and_assigns_deterministic_ids(tmp_path):
    workspace = make_workspace(tmp_path)
    frame = pd.DataFrame({"Time": ["2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"],
                          "Lat": [44.5, 44.5001], "Lon": [11.3, 11.3001], "Temp[°C]": [10, 11],
                          "Hum[%]": [50, 51], "Press[mbar]": [1000, 1000], "Speed[km/h]": [5, 5]})
    path = workspace / "data/raw/batch A/deep/campaign.csv"
    path.parent.mkdir()
    frame.to_csv(path, index=False)
    service = ApplicationService(workspace)
    first = service.discover()[0]
    second = service.discover()[0]
    assert first.batch == "batch A"
    assert first.validation["classification"] == "canonical"
    assert first.validation["proposed_campaign_id"] == second.validation["proposed_campaign_id"]


def test_check_writes_reports_without_touching_manifest(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    path = workspace / "data/raw/batch A/campaign.csv"
    pd.DataFrame({"Time": ["2026-01-01T00:00:00Z"], "Lat": [44.5], "Lon": [11.3],
                  "Temp[°C]": [10], "Hum[%]": [50], "Press[mbar]": [1000], "Speed[km/h]": [5]}).to_csv(path, index=False)
    monkeypatch.setattr(application, "run_qc", lambda *args, **kwargs: None)
    monkeypatch.setattr(application, "apply_manifest_and_qc", lambda *args, **kwargs: {"preview": True})
    manifest = workspace / "data/manifests/campaign_manifest.csv"
    before = manifest.read_bytes()
    result = ApplicationService(workspace).check(new_only=True)
    assert result["status"] == "pass"
    assert Path(result["report_path"]).exists()
    assert Path(result["json_report_path"]).exists()
    assert manifest.read_bytes() == before
    assert not (workspace / "outputs/recommended/inventory.csv").exists()


def test_lock_blocks_live_process_and_releases(tmp_path):
    workspace = make_workspace(tmp_path)
    first = WorkspaceLock(workspace, "run-1")
    first.acquire()
    with pytest.raises(WorkspaceError):
        WorkspaceLock(workspace, "run-2").acquire()
    first.release()
    assert not first.path.exists()


def test_failed_apply_updates_ledger_and_releases_lock(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    result = {"source_file": "batch A/campaign.csv", "absolute_path": str(workspace / "data/raw/batch A/campaign.csv"),
              "batch": "batch A", "validation": {"classification": "canonical"}}
    validation = {"source_file": "batch A/campaign.csv", "file_sha256": "x", "core_content_hash": "y", "size_bytes": 1,
                  "rows": 1, "columns": 7, "classification": "canonical", "canonical_source_file": "batch A/campaign.csv",
                  "duplicate_group_id": "", "blocking_errors": [], "warnings": [], "time_start_utc": None,
                  "time_end_utc": None, "duplicate_timestamps": 0, "missing_coordinates": 0,
                  "proposed_campaign_id": "campaign"}
    monkeypatch.setattr(ApplicationService, "check", lambda self, *args, **kwargs: {
        "status": "pass", "results": [result], "validation_results": [validation]})
    monkeypatch.setattr(application, "apply_manifest_and_qc", lambda *args, **kwargs: {"canonical_ids": ["campaign"]})
    monkeypatch.setattr(ApplicationService, "_run_global_analyses", lambda *args, **kwargs: {"invocations": 1})
    def fail_promote(*args, **kwargs):
        raise RuntimeError("promotion failed")
    monkeypatch.setattr(application, "promote", fail_promote)
    with pytest.raises(RuntimeError, match="promotion failed"):
        ApplicationService(workspace).apply()
    ledger = json.loads((workspace / "logs/run_ledger.json").read_text(encoding="utf-8"))
    assert ledger[-1]["status"] == "failed"
    assert ledger[-1]["rollback"] is True
    assert not (workspace / "logs/.meteotracker.lock").exists()


def test_apply_plans_global_analysis_once(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    source = workspace / "data/raw/batch A/campaign.csv"
    source.write_text("Time,Lat,Lon,Temp[°C],Hum[%],Press[mbar],Speed[km/h]\n2026-01-01T00:00:00Z,44.5,11.3,10,50,1000,5\n", encoding="utf-8")
    validation = {"source_file": "batch A/campaign.csv", "file_sha256": "x", "core_content_hash": "y", "size_bytes": 1,
                  "rows": 1, "columns": 7, "classification": "canonical", "canonical_source_file": "batch A/campaign.csv",
                  "duplicate_group_id": "", "blocking_errors": [], "warnings": [], "time_start_utc": None,
                  "time_end_utc": None, "duplicate_timestamps": 0, "missing_coordinates": 0,
                  "proposed_campaign_id": "campaign"}
    result = {"source_file": "batch A/campaign.csv", "absolute_path": str(source), "batch": "batch A", "validation": validation}
    monkeypatch.setattr(ApplicationService, "check", lambda self, *args, **kwargs: {
        "status": "pass", "results": [result], "validation_results": [validation]})
    monkeypatch.setattr(application, "apply_manifest_and_qc", lambda *args, **kwargs: {"canonical_ids": ["campaign"]})
    calls = []
    monkeypatch.setattr(ApplicationService, "_run_global_analyses", lambda *args, **kwargs: calls.append(1) or {"invocations": 1})
    monkeypatch.setattr(application, "promote", lambda *args, **kwargs: None)
    output = ApplicationService(workspace).apply()
    assert output["status"] == "completed"
    assert calls == [1]


def test_promotion_failure_restores_previous_targets(tmp_path):
    root = tmp_path / "workspace"
    staging = tmp_path / "staging"
    destination_one = root / "outputs/one.txt"
    destination_two = root / "outputs/two.txt"
    source_one = staging / "outputs/one.txt"
    destination_one.parent.mkdir(parents=True)
    source_one.parent.mkdir(parents=True)
    destination_one.write_text("official-one", encoding="utf-8")
    destination_two.write_text("official-two", encoding="utf-8")
    source_one.write_text("staged-one", encoding="utf-8")
    try:
        promote(staging, root, [Path("outputs/one.txt"), Path("outputs/two.txt")])
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("promotion should fail when a staged target is missing")
    assert destination_one.read_text(encoding="utf-8") == "official-one"
    assert destination_two.read_text(encoding="utf-8") == "official-two"


def test_apply_failure_before_promotion_records_failed_run(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    source = workspace / "data/raw/batch A/campaign.csv"
    source.write_text("synthetic", encoding="utf-8")
    validation = {"source_file": "batch A/campaign.csv", "file_sha256": "x", "core_content_hash": "y", "size_bytes": 1,
                  "rows": 1, "columns": 7, "classification": "canonical", "canonical_source_file": "batch A/campaign.csv",
                  "duplicate_group_id": "", "blocking_errors": [], "warnings": [], "time_start_utc": None,
                  "time_end_utc": None, "duplicate_timestamps": 0, "missing_coordinates": 0,
                  "proposed_campaign_id": "campaign"}
    item = {"source_file": validation["source_file"], "absolute_path": str(source), "batch": "batch A", "validation": validation}
    monkeypatch.setattr(ApplicationService, "check", lambda self, *args, **kwargs: {
        "status": "pass", "results": [item], "validation_results": [validation]})
    monkeypatch.setattr(application, "apply_manifest_and_qc", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("staging failed")))
    with pytest.raises(RuntimeError, match="staging failed"):
        ApplicationService(workspace).apply()
    ledger = json.loads((workspace / "logs/run_ledger.json").read_text(encoding="utf-8"))
    assert ledger[-1]["status"] == "failed"
    assert ledger[-1]["rollback"] is True
    assert not (workspace / "logs/.meteotracker.lock").exists()
