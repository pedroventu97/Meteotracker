"""Behavioral Qt tests. All mutations are restricted to pytest workspaces."""
from collections import Counter
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

from PySide6.QtCore import QItemSelectionModel, QMimeData, QPoint, QPointF, QSettings, QTimer, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
import pandas as pd
import pytest

import meteotracker_qc.application as application
from meteotracker_qc.application import ApplicationService, WorkspaceLock
from meteotracker_qc.gui.window import MainWindow
from meteotracker_qc.gui.worker import ServiceWorker
from scientific_fixtures import batch_workspace, empty_workspace, write_route


@pytest.fixture(autouse=True)
def guard_official_apply(monkeypatch, tmp_path):
    original = ApplicationService.apply
    def guarded(service, *args, **kwargs):
        # Explicitly deny the official workspace, including when tests run from an installed wheel.
        assert service.workspace.resolve() != Path("D:/projects/Meteotracker").resolve(), "OFFICIAL APPLY FORBIDDEN"
        assert service.workspace.resolve().is_relative_to(tmp_path.resolve()), "Apply only in this test's temporary workspace"
        return original(service, *args, **kwargs)
    monkeypatch.setattr(ApplicationService, "apply", guarded)


@pytest.fixture
def workspace(tmp_path):
    root = empty_workspace(tmp_path / "workspace città con spazi")
    write_route(root / "data/raw/primo batch/a.csv", n=21)
    write_route(root / "data/raw/secondo batch/nested/b.csv", n=21, hour=1)
    return root


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)


def idle(qtbot, window):
    qtbot.waitUntil(lambda: window.worker is None, timeout=180000)


@pytest.fixture
def window(qtbot, settings):
    instance = MainWindow(settings=settings, startup=False)
    qtbot.addWidget(instance)
    instance.show()
    yield instance
    if instance.worker:
        instance.cancel_operation()
        idle(qtbot, instance)
    instance.close()


def load_and_scan(qtbot, window, workspace):
    assert window.set_workspace(workspace)
    idle(qtbot, window)
    window.scan_raw()
    idle(qtbot, window)
    assert window.model.rowCount() > 0


def protected(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for base in ("data", "config", "outputs") for p in (root / base).rglob("*") if p.is_file()}


def test_first_start_prompts_and_workspace_invalid_keeps_previous(qtbot, window, workspace, tmp_path, monkeypatch):
    chosen = []
    def choose(*args):
        chosen.append(True)
        return str(workspace)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose)
    window.startup()
    idle(qtbot, window)
    assert chosen == [True]
    assert window.service.workspace == workspace
    assert "Doctor: OK" in window.overview_text.toPlainText()
    assert not window.set_workspace(tmp_path / "invalid")
    assert window.service.workspace == workspace
    assert "non valida" in window.status_label.text()


def test_first_start_cancel_and_settings_restore(qtbot, window, settings, workspace, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: "")
    window.startup()
    assert window.service is None and not window.check_button.isEnabled()
    window.set_workspace(workspace)
    idle(qtbot, window)
    window.filter_edit.setText("avvisi")
    window.close()
    assert set(settings.allKeys()) == {"last_workspace", "geometry", "filter"}
    other = MainWindow(settings=settings, startup=False)
    qtbot.addWidget(other)
    other.startup()
    idle(qtbot, other)
    assert other.service.workspace == workspace
    assert other.filter_edit.text() == "avvisi"
    other.close()


def test_offscreen_geometry_recovered(qtbot, settings):
    source = MainWindow(settings=settings, startup=False)
    source.move(100000, 100000)
    source.close()
    restored = MainWindow(settings=settings, startup=False)
    qtbot.addWidget(restored)
    assert any(s.availableGeometry().intersects(restored.frameGeometry()) for s in QApplication.screens())
    restored.close()


def test_scan_nested_one_row_per_csv_filter_sort_details_and_multiselect(qtbot, window, workspace):
    load_and_scan(qtbot, window, workspace)
    assert window.batch_list.count() == 2
    assert window.model.rowCount() == 2
    assert window.model.columnCount() == 12
    assert len(window.batch_list.selectedItems()) == 2
    assert len(window.selected_paths()) == 2
    window.filter_edit.setText("nested")
    assert window.proxy.rowCount() == 1
    window.show_details(window.proxy.index(0, 0))
    assert "nested" in window.details.toPlainText()
    window.filter_edit.clear()
    window.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
    assert window.model.data(window.model.index(0, 4)) == 21
    assert window.model.data(window.model.index(0, 0), Qt.ItemDataRole.ToolTipRole)
    window.batch_list.item(0).setSelected(False)
    assert len(window.selected_paths()) == 1
    window.batch_list.item(0).setSelected(True)
    window.table.selectAll()
    assert len(window.selected_paths()) == 2


def test_drag_drop_multiple_folders_and_repeated_add_no_double_count(qtbot, window, workspace):
    window.set_workspace(workspace)
    idle(qtbot, window)
    paths = [workspace / "data/raw/primo batch", workspace / "data/raw/secondo batch"]
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    drag = QDragEnterEvent(QPoint(1, 1), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dragEnterEvent(drag)
    assert drag.isAccepted()
    drop = QDropEvent(QPointF(1, 1), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(drop)
    idle(qtbot, window)
    assert drop.isAccepted()
    assert len(window.selected_paths()) == 2
    window.add_paths(paths)
    idle(qtbot, window)
    assert window.model.rowCount() == 2
    assert window.batch_list.count() == 2
    bad = QMimeData()
    bad.setUrls([QUrl("https://example.com/folder")])
    event = QDragEnterEvent(QPoint(1, 1), Qt.DropAction.CopyAction, bad, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dragEnterEvent(event)
    assert not event.isAccepted()


def test_check_read_only_events_apply_gating_and_selection_invalidation(qtbot, window, workspace):
    load_and_scan(qtbot, window, workspace)
    before = protected(workspace)
    assert not window.apply_button.isEnabled()
    window.check_campaigns()
    assert window.worker is not None
    assert not window.apply_button.isEnabled()
    idle(qtbot, window)
    assert protected(workspace) == before
    assert window.check_payload, window.status_label.text()
    assert window.apply_button.isEnabled()
    assert len(window.check_payload["per_csv"]) == 2
    assert all(v["qc"] for v in window.check_payload["per_csv"].values())
    assert all(v["suitability"] for v in window.check_payload["per_csv"].values())
    assert {e["event"] for e in window.events} >= {"file_discovered", "phase_started", "phase_completed"}
    assert "file_discovered" in window.log.toPlainText()
    with WorkspaceLock(workspace, "other"):
        window.update_controls()
        assert not window.apply_button.isEnabled()
    window.update_controls()
    assert window.apply_button.isEnabled()
    window.batch_list.item(0).setSelected(False)
    assert window.check_payload is None and not window.apply_button.isEnabled()


def test_table_selection_invalidates_check_and_invalid_csv_blocks(qtbot, window, workspace):
    load_and_scan(qtbot, window, workspace)
    window.check_campaigns()
    idle(qtbot, window)
    window.table.selectionModel().select(window.proxy.index(0, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    assert window.check_payload is None
    (workspace / "data/raw/primo batch/bad.csv").write_text("nonsense\ninvalid\n")
    window.scan_raw()
    idle(qtbot, window)
    window.check_campaigns()
    idle(qtbot, window)
    assert not window.apply_button.isEnabled()
    assert any("Invalido" in window.model.values(i)[0] for i in window.model.items)


def test_worker_responsive_queued_events_cancel_and_close(qtbot, window, workspace, monkeypatch):
    window.set_workspace(workspace)
    idle(qtbot, window)
    started = threading.Event()
    def slow(service, *args, **kwargs):
        started.set()
        service._event("test", "discover", "phase_started", "attesa")
        while not service.cancellation.requested:
            threading.Event().wait(0.01)
        service.cancellation.checkpoint()
    monkeypatch.setattr(ApplicationService, "discover", slow)
    beats = []
    timer = QTimer(window)
    timer.setInterval(5)
    timer.timeout.connect(lambda: beats.append(threading.get_ident()))
    timer.start()
    window.scan_raw()
    qtbot.waitUntil(lambda: started.is_set() and len(beats) >= 3)
    assert all(t == threading.get_ident() for t in beats)
    assert window.worker is not None
    assert not window.start_job("overview")
    window.close()
    idle(qtbot, window)
    timer.stop()
    assert not window.isVisible()
    assert "phase_started" in window.log.toPlainText()


def test_worker_error_cleanup(qtbot, window, workspace, monkeypatch):
    window.set_workspace(workspace)
    idle(qtbot, window)
    def fail(*args, **kwargs):
        raise RuntimeError("errore worker controllato")
    monkeypatch.setattr(ApplicationService, "discover", fail)
    window.scan_raw()
    idle(qtbot, window)
    assert "errore worker controllato" in window.status_label.text()
    assert window.scan_button.isEnabled() and not window.apply_button.isEnabled()


def test_confirm_apply_displays_plan_and_defaults_to_no(qtbot, window, workspace, monkeypatch):
    load_and_scan(qtbot, window, workspace)
    window.check_campaigns()
    idle(qtbot, window)
    shown = []
    def reject(box):
        shown.append(box.informativeText())
        assert box.defaultButton() == box.button(QMessageBox.StandardButton.No)
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "exec", reject)
    window.prepare_apply()
    idle(qtbot, window)
    assert len(shown) == 1
    assert all(word in shown[0] for word in ("primo batch", "secondo batch", "Session QC", "many-to-many", "Backup", "stale", "outputs/recommended"))
    assert window.service.history() == []


def test_apply_real_temporary_batch_once_many_to_many_and_history(qtbot, window, tmp_path, monkeypatch):
    root = batch_workspace(tmp_path / "batch città completo")
    load_and_scan(qtbot, window, root)
    window.check_campaigns()
    idle(qtbot, window)
    assert window.check_payload, window.status_label.text()
    counts = Counter()
    import meteotracker_qc.session_qc_pipeline as session
    import meteotracker_qc.repeated_routes.pipeline as routes
    import meteotracker_qc.spatial_density.pipeline as density
    import meteotracker_qc.temporal_drift_pipeline as temporal
    for module, name, phase in ((session, "run_session_qc", "session_qc"), (routes, "run_pipeline", "repeated_routes"),
                               (routes, "consolidate_segments", "many_to_many_consolidation"),
                               (density, "run_density_analysis", "spatial_density"), (temporal, "run_temporal_drift", "temporal_drift")):
        original = getattr(module, name)
        def spy(*args, _original=original, _phase=phase, **kwargs):
            counts[_phase] += 1
            return _original(*args, **kwargs)
        monkeypatch.setattr(module, name, wraps(original)(spy))
    monkeypatch.setattr(window, "confirm_apply", lambda check: True)
    window.prepare_apply()
    idle(qtbot, window)
    assert counts == dict.fromkeys(["session_qc", "repeated_routes", "many_to_many_consolidation", "spatial_density", "temporal_drift"], 1)
    assert window.service.history()[-1]["status"] == "completed", window.status_label.text()
    assert window.history_table.rowCount() == 1
    assert window.history_table.item(0, 7).text() == "No"
    assert not window.apply_button.isEnabled()
    members = pd.read_csv(root / "outputs/repeated_routes/point_segment_memberships.csv")
    summary = json.loads((root / "outputs/repeated_routes/membership_summary.json").read_text())
    assert members.membership_id.is_unique
    assert summary["n_original_points_in_multiple_segments"] > 0
    assert summary["n_duplicate_semantic_memberships"] == 0
    inventory = pd.read_csv(root / "outputs/session_qc/session_qc_inventory.csv")
    density_frame = pd.read_csv(root / "outputs/spatial_density/meteotracker_coverage_50m.csv")
    assert inventory.n_raw.sum() == density_frame.n_observations.sum()
    assert len(inventory) == 8  # nine CSVs, one redundant, no double counting


def test_freshness_rechecked_before_confirmation(qtbot, window, workspace, monkeypatch):
    load_and_scan(qtbot, window, workspace)
    window.check_campaigns()
    idle(qtbot, window)
    (workspace / "config/qc_recommended.yaml").write_text("changed after check")
    monkeypatch.setattr(window, "confirm_apply", lambda _: pytest.fail("stale check reached confirmation"))
    window.prepare_apply()
    idle(qtbot, window)
    assert "Input cambiati" in window.status_label.text()
    assert not window.apply_button.isEnabled()


def test_read_only_window_never_enables_apply(qtbot, workspace, settings):
    instance = MainWindow(settings=settings, startup=False, read_only=True)
    qtbot.addWidget(instance)
    load_and_scan(qtbot, instance, workspace)
    instance.check_campaigns()
    idle(qtbot, instance)
    assert instance.check_payload
    assert not instance.apply_button.isEnabled()
    assert not (workspace / "logs/check_reports").exists()
    instance.close()


def test_safe_report_open_and_missing_no_crash(qtbot, window, workspace, tmp_path, monkeypatch):
    window.set_workspace(workspace)
    idle(qtbot, window)
    report = workspace / "logs/rapporto città con spazi.md"
    report.write_text("report")
    from meteotracker_qc.gui import window as module
    opened = []
    monkeypatch.setattr(module.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    assert window.open_result(report)
    assert opened[0].isLocalFile() and Path(opened[0].toLocalFile()) == report
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    for bad in ("logs/missing.md", outside, "https://example.com", "cmd.exe /c echo hi"):
        assert not window.open_result(bad)
    assert len(opened) == 1


def test_ambiguous_and_external_check_block_apply(qtbot, window, workspace, monkeypatch):
    load_and_scan(qtbot, window, workspace)
    window.check_campaigns()
    idle(qtbot, window)
    window.check_payload["validation_results"][0]["classification"] = "ambiguous"
    window.update_controls()
    assert not window.apply_button.isEnabled()
    window.check_payload["validation_results"][0]["classification"] = "canonical"
    window.check_payload["plan"]["external"] = True
    window.update_controls()
    assert not window.apply_button.isEnabled()


def test_critical_cancellation_message_and_no_second_job(qtbot, window, workspace, monkeypatch):
    load_and_scan(qtbot, window, workspace)
    def critical(service, *args, **kwargs):
        service._event("test-critical", "promotion", "critical_started", "Promozione")
        while not service.cancellation.requested:
            threading.Event().wait(0.01)
        return {"status": "cancelled"}
    monkeypatch.setattr(ApplicationService, "apply", critical)
    window.start_job("apply", check={})
    qtbot.waitUntil(lambda: window._critical)
    window.cancel_operation()
    assert "prossimo punto sicuro" in window.status_label.text()
    assert "rollback" in window.status_label.text()
    assert not window.cancel_button.isEnabled()
    idle(qtbot, window)
    assert window.worker is None and window.scan_button.isEnabled()


def test_smoke_does_not_access_service(qtbot, monkeypatch):
    from meteotracker_qc.gui import main
    for name in ("doctor", "discover", "check", "apply"):
        monkeypatch.setattr(ApplicationService, name, lambda *a, **k: pytest.fail("smoke accessed service"))
    assert main(["--smoke-test"]) == 0


@pytest.mark.parametrize("module", [True, False])
def test_entrypoints_smoke_from_other_cwd_with_spaces(tmp_path, module):
    cwd = tmp_path / "directory esterna città con spazi"
    cwd.mkdir()
    command = [sys.executable, "-W", "error", "-m", "meteotracker_qc.gui"] if module else [str(Path(sys.executable).with_name("meteotracker-gui.exe" if os.name == "nt" else "meteotracker-gui"))]
    result = subprocess.run([*command, "--smoke-test"], cwd=cwd, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout and "nessuna pipeline" in result.stdout
