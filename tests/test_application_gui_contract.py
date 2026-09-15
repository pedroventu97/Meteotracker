"""Cancellation, freshness and local results shared by CLI and Qt."""
import hashlib
import json
from pathlib import Path

import pytest

import meteotracker_qc.application as application
from meteotracker_qc.application import ApplicationService, WorkspaceError
from meteotracker_qc.ingestion import promote
from meteotracker_qc.operation import CancellationToken, OperationCancelled
from scientific_fixtures import empty_workspace, write_route


@pytest.fixture
def workspace(tmp_path):
    root = empty_workspace(tmp_path / "cancellazione città")
    write_route(root / "data/raw/one/a.csv", n=21)
    return root


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for base in ("data", "outputs", "config") for p in (root / base).rglob("*") if p.is_file()}


@pytest.mark.parametrize("phase", ["before_start", "point_qc", "after_staging", "during_promotion"])
def test_apply_cancellation_restores_workspace_ledger_and_lock(workspace, monkeypatch, phase):
    token = CancellationToken()
    service = ApplicationService(workspace, cancellation=token)
    check = service.check(new_only=True)
    assert check["status"] in {"pass", "warning"}
    before = hashes(workspace)
    if phase == "before_start":
        token.request()
    elif phase == "point_qc":
        service.emit_callback = lambda event: token.request() if event.phase == "point_qc" else None
    original_build = application.apply_manifest_and_qc
    def build(*args, **kwargs):
        result = original_build(*args, **kwargs)
        if phase == "after_staging":
            token.request()
        return result
    monkeypatch.setattr(application, "apply_manifest_and_qc", build)
    # Global science has separate end-to-end tests. This fixture isolates the real transaction.
    def global_stub(stage, ids):
        for name in ("repeated_routes", "spatial_density", "temporal_drift"):
            (stage / "outputs" / name).mkdir(parents=True, exist_ok=True)
        return {"invocations": 1}
    monkeypatch.setattr(service, "_run_global_analyses", global_stub)
    moved = []
    original_replace = Path.replace
    def replace(source, destination):
        result = original_replace(source, destination)
        if (phase == "during_promotion" and source.parent.parent.name.startswith("meteotracker_apply_")
                and Path(destination).parent == workspace / "outputs"):
            moved.append(Path(destination).name)
            if len(moved) == 1:
                token.request()
        return result
    monkeypatch.setattr(Path, "replace", replace)
    result = service.apply(check=check)
    assert result["status"] == "cancelled"
    assert hashes(workspace) == before
    record = service.history()[-1]
    assert record["status"] == "cancelled" and record["rollback"]
    assert not (workspace / "logs/.meteotracker.lock").exists()
    assert not list((workspace / "logs").glob("meteotracker_apply_*"))
    if phase == "during_promotion":
        assert len(moved) == 8  # cancellation did not interrupt the sequence of promoted output trees


def test_check_cancelled_during_qc_cleans_staging_and_records_cancelled(workspace, monkeypatch):
    token = CancellationToken()
    service = ApplicationService(workspace, cancellation=token)
    before = hashes(workspace)
    def cancel(*args, **kwargs):
        token.request()
        return {}
    monkeypatch.setattr(application, "apply_manifest_and_qc", cancel)
    result = service.check(new_only=True)
    assert result["status"] == "cancelled"
    assert hashes(workspace) == before
    assert service.history()[-1]["status"] == "cancelled"
    assert not list((workspace / "logs").glob("meteotracker_check_*"))
    assert not (workspace / "logs/.meteotracker.lock").exists()


def test_promotion_cancel_callback_is_after_all_targets_and_rollback_is_existing(tmp_path):
    root, stage = tmp_path / "root", tmp_path / "stage"
    root.mkdir()
    stage.mkdir()
    for name in ("a.txt", "b.txt"):
        (root / name).write_text("original")
        (stage / name).write_text("new")
    def checkpoint():
        assert all((root / name).read_text() == "new" for name in ("a.txt", "b.txt"))
        raise OperationCancelled()
    with pytest.raises(OperationCancelled):
        promote(stage, root, [Path("a.txt"), Path("b.txt")], after_promotion=checkpoint)
    assert all((root / name).read_text() == "original" for name in ("a.txt", "b.txt"))


@pytest.mark.parametrize("relative", ["data/raw/one/a.csv", "config/qc_recommended.yaml", "data/manifests/campaign_manifest.csv", "outputs/changed.txt"])
def test_stale_check_rejected_under_lock_before_staging(workspace, monkeypatch, relative):
    service = ApplicationService(workspace)
    check = service.check(new_only=True)
    path = workspace / relative
    path.write_bytes((path.read_bytes() if path.exists() else b"") + b"\n")
    before = hashes(workspace)
    monkeypatch.setattr(application, "apply_manifest_and_qc", lambda *a, **k: pytest.fail("stale check reached staging"))
    with pytest.raises(WorkspaceError, match="Input cambiati"):
        service.apply(check=check)
    assert hashes(workspace) == before
    assert not (workspace / "logs/.meteotracker.lock").exists()


def test_read_only_service_guards_apply_without_any_write(workspace):
    before = hashes(workspace)
    with pytest.raises(WorkspaceError, match="apply vietato"):
        ApplicationService(workspace, read_only=True).apply()
    assert hashes(workspace) == before
    assert not (workspace / "logs/run_ledger.json").exists()


def test_missing_or_unreadable_lock_is_conservative(workspace):
    service = ApplicationService(workspace)
    assert service.lock_status() is None
    (workspace / "logs/.meteotracker.lock").write_text("broken json")
    assert service.lock_status()["error"]


def test_safe_results_allow_explicit_root_reject_commands_and_escape(workspace, tmp_path):
    service = ApplicationService(workspace)
    external = tmp_path / "rapporti esterni"
    external.mkdir()
    report = external / "rapporto città.md"
    report.write_text("hello")
    with pytest.raises(ValueError):
        service.result_path(report)
    assert service.result_path(report, authorized_roots=[external]) == report
    for value in ("https://example.com", "file:///C:/Windows", "cmd.exe /c whoami", "logs/test.md:evil"):
        with pytest.raises((OSError, ValueError)):
            service.result_path(value)
    executable = workspace / "logs/evil.cmd"
    executable.write_text("echo no")
    with pytest.raises(ValueError, match="Tipo"):
        service.result_path(executable)
    (workspace / "logs/run_ledger.json").write_text(json.dumps([{"run_id": "external", "report_path": str(report)}]))
    with pytest.raises(ValueError):
        service.open_report("external")


def test_explicit_input_paths_independent_of_current_directory(workspace, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    found = ApplicationService(workspace).discover([workspace / "data/raw/one"])
    assert len(found) == 1
    assert found[0].batch == "one"
