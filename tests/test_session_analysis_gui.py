"""Separate-window behavior and asynchronous map selection, entirely synthetic."""
import json
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
import pytest

from meteotracker_qc.application import ApplicationService, AppEvent
from meteotracker_qc.gui.window import MainWindow
from meteotracker_qc.gui.session_analysis import SessionAnalysisWindow
from meteotracker_qc.gui.log_panel import LogPanel
from meteotracker_qc.operation import OperationCancelled
from test_session_analysis import registered_workspace, protected


def idle(qtbot, window):
    qtbot.waitUntil(lambda: window.worker is None and window.map_worker is None and not window.map_timer.isActive(), timeout=60000)


@pytest.fixture
def main_window(qtbot, tmp_path):
    service = ApplicationService(registered_workspace(tmp_path / "progetto città con spazi"), read_only=True)
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    main = MainWindow(settings=settings, startup=False, read_only=True)
    qtbot.addWidget(main)
    main.service = service
    main.update_controls()
    main.show()
    yield main
    if main.analysis_window:
        child = main.analysis_window
        if child.worker:
            child.worker.token.request()
        if child.map_worker:
            child.map_worker.token.request()
        idle(qtbot, child)
        child.close()
    main.close()


def open_window(qtbot, main):
    main.open_analysis()
    child = main.analysis_window
    idle(qtbot, child)
    return child


def select(window, row, state=True):
    window.session_table.item(row, 0).setCheckState(Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)


def test_open_single_instance_same_service_workspace_independence(qtbot, main_window):
    window = open_window(qtbot, main_window)
    assert window.service is main_window.service
    assert window.workspace == main_window.service.workspace
    assert window.isWindow() and window.isVisible()
    assert window.session_table.rowCount() == 2
    main_window.open_analysis()
    assert main_window.analysis_window is window
    assert sum(isinstance(w, SessionAnalysisWindow) for w in QApplication.topLevelWidgets()) == 1
    main_window.tabs.setCurrentIndex(1)
    assert window.isVisible()
    window.return_to_main()
    assert main_window.service is window.service
    assert window.close()
    main_window.open_analysis()
    assert main_window.analysis_window is window and window.isVisible()


def test_single_multi_selection_filters_map_and_track_visibility(qtbot, main_window):
    window = open_window(qtbot, main_window)
    before = protected(window.workspace)
    select(window, 0)
    idle(qtbot, window)
    assert window.selected_ids() == ["campagna_0"]
    assert len(window.map.preview["tracks"]) == 1
    assert "riga sorgente 0" in window.map.point_text("campagna_0", 0)
    assert "Temp[°C]" in window.map.point_text("campagna_0", 0)
    select(window, 1)
    idle(qtbot, window)
    assert len(window.map.preview["tracks"]) == 2
    assert len(window.map.rendered) == 2
    window.map.show_all(False)
    assert window.map.visible_ids() == [] and window.map.rendered == []
    window.map.show_all(True)
    assert len(window.map.rendered) == 2
    window.select_all(False)
    window.search.setText("ritorno")
    assert window.session_table.isRowHidden(0)
    window.select_all(True)
    idle(qtbot, window)
    assert window.selected_ids() == ["campagna_1"]
    assert protected(window.workspace) == before


def test_outdated_map_ignored_and_fast_selection(qtbot, main_window, monkeypatch):
    window = open_window(qtbot, main_window)
    original = window.service.preview_tracks
    first_started = threading.Event()
    release = threading.Event()
    def slow(campaign_ids, **kwargs):
        if campaign_ids == ["campagna_0"]:
            first_started.set()
            release.wait(5)
        return original(campaign_ids, **kwargs)
    monkeypatch.setattr(window.service, "preview_tracks", slow)
    select(window, 0)
    qtbot.waitUntil(first_started.is_set)
    select(window, 1)
    select(window, 0, False)
    stale = original(["campagna_0"])
    window.accept_map(window.generation - 1, stale)
    assert window.map.preview is None or not window.map.preview["tracks"]
    release.set()
    idle(qtbot, window)
    assert [t["campaign_id"] for t in window.map.preview["tracks"]] == ["campagna_1"]


def test_profile_controls_runtime_and_preview_results(qtbot, main_window):
    window = open_window(qtbot, main_window)
    select(window, 0)
    idle(qtbot, window)
    before = protected(window.workspace)
    window.profile.setCurrentText("Permissive")
    assert window.origin.currentText() == "permissive"
    window.groups["warmup"].setChecked(False)
    assert window.profile.currentText() == "Personalizzato"
    assert "warmup" not in window.runtime_options()["active_controls"]
    assert "Disattivati" in window.differences.toPlainText()
    window.run_preview()
    assert window.worker is not None and window.worker.service is window.service
    idle(qtbot, window)
    assert window.analysis is not None, window.message.text()
    assert window.analysis.report["sessions"][0]["warmup_rows"] == 0
    assert window.summary_table.rowCount() > 10 and window.flags_table.rowCount() > 10
    assert window.comparison.rowCount() == 1
    window.map.mode.setCurrentText("Prima/dopo QC")
    assert window.map.frames
    window.show_flag(0, 0)
    assert window.map.mode.currentText() == "Famiglia di flag"
    assert "osservazioni" in window.flag_details.toPlainText()
    assert protected(window.workspace) == before


def test_responsive_worker_cancel_close_confirmation(qtbot, main_window, monkeypatch):
    window = open_window(qtbot, main_window)
    select(window, 0)
    idle(qtbot, window)
    started = threading.Event()
    release = threading.Event()
    def pending(campaign_ids, cancellation, **kwargs):
        started.set()
        release.wait(5)
        cancellation.checkpoint()
        raise AssertionError("Expected cancellation")
    monkeypatch.setattr(window.service, "preview_qc", pending)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(5)
    window.run_preview()
    qtbot.waitUntil(started.is_set)
    qtbot.waitUntil(lambda: len(ticks) >= 3)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    assert not window.close() and window.isVisible()
    assert not window.worker.token.requested
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert not window.close()
    assert window.worker.token.requested
    release.set()
    idle(qtbot, window)
    qtbot.waitUntil(lambda: not window.isVisible())
    timer.stop()
    assert main_window.service is window.service


def test_geometry_persist_and_720p_layout(qtbot, main_window):
    window = open_window(qtbot, main_window)
    # Saved geometry must fit the virtual offscreen screen as well as native Windows.
    area = QApplication.primaryScreen().availableGeometry()
    window.resize(min(740, area.width()), min(520, area.height()))
    window.move(35, 45)
    window.close()
    saved = main_window.settings.value("analysis_geometry")
    assert saved
    second = SessionAnalysisWindow(window.service, settings=main_window.settings)
    qtbot.addWidget(second)
    second.show()
    idle(qtbot, second)
    assert second.size() == window.size()
    second.select_all(True)
    idle(qtbot, second)
    second.result_session.addItem("campagna_" + "con_nome_molto_lungo_" * 12)
    second.message.setText("Anteprima completata · Sessioni separate · Nessun output ufficiale modificato")
    second.resize(853, 480)  # 1280x720 at 150% logical scaling
    QApplication.processEvents()
    assert second.width() <= 853
    assert second.height() <= 480
    second.close()


def test_readable_log_filters_copy_and_full_json(qtbot, tmp_path):
    log = LogPanel()
    qtbot.addWidget(log)
    log.append_event(AppEvent("phase_started", "run", "preview_qc", "2026-01-01T10:00:00Z", "Controllo", .5, campaign_id="one"))
    log.message("Errore utile")
    assert log.table.rowCount() == 2
    assert log.table.item(0, 5).text() == "50%"
    log.level.setCurrentText("error")
    assert log.table.rowCount() == 1
    log.table.selectRow(0)
    log.copy_message()
    assert QApplication.clipboard().text() == "Errore utile"
    log.level.setCurrentText("Tutti")
    log.session.setText("one")
    assert log.table.rowCount() == 1
    assert "phase_started" in log.technical.toPlainText()
    path = tmp_path / "log città.json"
    log.save_to(path)
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 2
    with pytest.raises(FileExistsError):
        log.save_to(path)
