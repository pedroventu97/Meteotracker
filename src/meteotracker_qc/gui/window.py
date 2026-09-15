"""Desktop presentation and operation coordination; ApplicationService owns all data work."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path

from PySide6.QtCore import QSettings, QSortFilterProxyModel, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSplitter, QTableView, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..application import ApplicationService
from .models import CsvModel
from .worker import ServiceWorker

PHASES = {"session_qc": "Session QC", "repeated_routes": "Repeated routes",
          "many_to_many_consolidation": "Consolidamento many-to-many",
          "spatial_density": "Spatial density", "temporal_drift": "Temporal drift"}


class MainWindow(QMainWindow):
    def __init__(self, *, workspace=None, settings=None, startup=True, persist=True, read_only=False):
        super().__init__()
        self.setWindowTitle("Meteotracker QC")
        self.resize(1250, 800)
        self.setAcceptDrops(True)
        self.settings = settings if settings is not None else QSettings("Meteotracker", "Desktop")
        self.persist = persist
        self.read_only = read_only
        self.service = None
        self.worker = None
        self.check_payload = None
        self.check_selection = ()
        self._rendering = False
        self._closing = False
        self._critical = False
        self._result = None
        self._error = None
        self.last_report = None
        self.events = []
        self._workspace_argument = workspace
        self._build_ui()
        if persist:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
            self.filter_edit.setText(self.settings.value("filter", ""))
        self._fit_screen()
        self.lock_timer = QTimer(self)
        self.lock_timer.setInterval(750)
        self.lock_timer.timeout.connect(self.update_controls)
        self.lock_timer.start()
        self.update_controls()
        if startup:
            QTimer.singleShot(0, self.startup)

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        bar = QHBoxLayout()
        self.workspace_label = QLabel("Nessuna workspace selezionata")
        self.workspace_label.setTextFormat(Qt.TextFormat.PlainText)
        self.choose_button = QPushButton("Scegli workspace")
        self.choose_button.clicked.connect(self.choose_workspace)
        bar.addWidget(self.workspace_label, 1)
        bar.addWidget(self.choose_button)
        layout.addLayout(bar)
        if self.read_only:
            layout.addWidget(QLabel("Sola lettura — aggiornamento del progetto disabilitato"))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        overview = QWidget()
        ov = QVBoxLayout(overview)
        self.overview_text = QPlainTextEdit()
        self.overview_text.setReadOnly(True)
        self.overview_text.setPlainText("Seleziona una workspace esistente per iniziare.")
        ov.addWidget(self.overview_text)
        self.refresh_button = QPushButton("Aggiorna panoramica e cronologia")
        self.refresh_button.clicked.connect(self.refresh)
        ov.addWidget(self.refresh_button)
        links = QHBoxLayout()
        self.report_button = QPushButton("Apri ultimo rapporto")
        self.report_button.clicked.connect(lambda: self.open_result(self.last_report))
        self.outputs_button = QPushButton("Apri cartella output")
        self.outputs_button.clicked.connect(lambda: self.open_result("outputs"))
        self.logs_button = QPushButton("Apri cartella log")
        self.logs_button.clicked.connect(lambda: self.open_result("logs"))
        for widget in (self.report_button, self.outputs_button, self.logs_button):
            links.addWidget(widget)
        ov.addLayout(links)
        self.tabs.addTab(overview, "Panoramica")

        campaigns = QWidget()
        cl = QVBoxLayout(campaigns)
        actions = QHBoxLayout()
        self.scan_button = QPushButton("Scansiona data/raw")
        self.scan_button.clicked.connect(self.scan_raw)
        self.add_button = QPushButton("Aggiungi cartella")
        self.add_button.clicked.connect(self.add_folders)
        self.check_button = QPushButton("Controlla nuove campagne")
        self.check_button.clicked.connect(self.check_campaigns)
        self.apply_button = QPushButton("Elabora e aggiorna il progetto")
        self.apply_button.clicked.connect(self.prepare_apply)
        for widget in (self.scan_button, self.add_button, self.check_button, self.apply_button):
            actions.addWidget(widget)
        cl.addLayout(actions)
        cl.addWidget(QLabel("Seleziona uno o più batch (Ctrl/Shift), oppure trascina cartelle. Una cartella può contenere più CSV."))
        self.batch_list = QListWidget()
        self.batch_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.batch_list.setMaximumHeight(115)
        self.batch_list.itemSelectionChanged.connect(self.selection_changed)
        cl.addWidget(self.batch_list)
        self.batch_summary = QLabel("Nessun batch")
        cl.addWidget(self.batch_summary)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filtra i CSV per stato, batch, nome o problemi…")
        cl.addWidget(self.filter_edit)
        self.model = CsvModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.filter_edit.textChanged.connect(self.proxy.setFilterFixedString)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        self.table.doubleClicked.connect(self.show_details)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setSizes([350, 100])
        cl.addWidget(splitter, 1)
        self.csv_report_button = QPushButton("Apri rapporto del controllo")
        self.csv_report_button.clicked.connect(lambda: self.open_result(self.model.report))
        cl.addWidget(self.csv_report_button)
        self.tabs.addTab(campaigns, "Nuove campagne")

        history_page = QWidget()
        hl = QVBoxLayout(history_page)
        self.history_table = QTableWidget(0, 8)
        self.history_table.setHorizontalHeaderLabels(["Run ID", "Data", "Comando", "Stato", "Durata", "Campagne", "Rapporto", "Rollback"])
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSortingEnabled(True)
        self.history_table.cellDoubleClicked.connect(self.open_history_report)
        hl.addWidget(self.history_table)
        hl.addWidget(QLabel("Doppio clic su un run per aprire il rapporto, se disponibile."))
        self.tabs.addTab(history_page, "Cronologia")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.tabs.addTab(self.log, "Log")

        bottom = QHBoxLayout()
        self.status_label = QLabel("Pronto")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.cancel_button = QPushButton("Annulla")
        self.cancel_button.clicked.connect(self.cancel_operation)
        bottom.addWidget(self.status_label, 2)
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.cancel_button)
        layout.addLayout(bottom)
        self.setCentralWidget(central)

    def _fit_screen(self):
        screens = QApplication.screens()
        if not any(s.availableGeometry().intersects(self.frameGeometry()) for s in screens):
            area = QApplication.primaryScreen().availableGeometry()
            self.resize(min(self.width(), area.width()), min(self.height(), area.height()))
            self.move(area.topLeft())

    @Slot()
    def startup(self):
        saved = self._workspace_argument or (self.settings.value("last_workspace", "") if self.persist else "")
        if saved and self.set_workspace(saved):
            return
        self.choose_workspace()

    @Slot()
    def choose_workspace(self):
        path = QFileDialog.getExistingDirectory(self, "Seleziona workspace Meteotracker esistente")
        if path:
            self.set_workspace(path)

    def set_workspace(self, path):
        if self.worker:
            return False
        candidate = ApplicationService(path, read_only=self.read_only)
        if not candidate.doctor()["valid"]:
            self.status_label.setText("Workspace non valida: " + str(candidate.workspace_error))
            return False
        self.service = candidate
        self.workspace_label.setText(f"Workspace: {candidate.workspace}")
        if self.persist:
            self.settings.setValue("last_workspace", str(candidate.workspace))
        self._rendering = True
        self.batch_list.clear()
        self.model.set_payload({})
        self._rendering = False
        self.last_report = None
        self.invalidate_check()
        self.refresh()
        return True

    @Slot()
    def refresh(self):
        self.start_job("overview")

    def batch_paths(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.batch_list.selectedItems()]

    def selected_paths(self):
        batches = self.batch_paths()
        selected = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        rows = [item for i, item in enumerate(self.model.items) if not selected or i in selected]
        return tuple(sorted(item["absolute_path"] for item in rows
                            if any(Path(item["absolute_path"]).is_relative_to(Path(b)) for b in batches)))

    @Slot()
    def selection_changed(self, *_):
        if not self._rendering:
            self.invalidate_check()
            indexes = self.table.selectionModel().selectedRows()
            if indexes:
                self.show_details(indexes[0])

    def invalidate_check(self):
        self.check_payload = None
        self.check_selection = ()
        self.update_controls()

    @Slot()
    def scan_raw(self):
        self.invalidate_check()
        self.start_job("discover")

    @Slot()
    def add_folders(self):
        dialog = QFileDialog(self, "Aggiungi cartelle di acquisizione")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        for view in dialog.findChildren(QAbstractItemView):
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_paths(dialog.selectedFiles())

    def add_paths(self, paths):
        if self.worker or not self.service:
            return
        roots = set(self.batch_paths())
        for value in paths:
            path = Path(value).expanduser().resolve()
            if path.is_file() and path.suffix.lower() == ".csv":
                path = path.parent
            if not path.is_dir():
                self.status_label.setText(f"Cartella non disponibile: {value}")
                return
            roots.add(str(path))
        self.invalidate_check()
        self.start_job("discover", paths=sorted(roots))

    def dragEnterEvent(self, event):
        if self.service and not self.worker and event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.service and not self.worker and all(u.isLocalFile() for u in event.mimeData().urls()):
            self.add_paths([u.toLocalFile() for u in event.mimeData().urls()])
            event.acceptProposedAction()

    @Slot()
    def check_campaigns(self):
        paths = self.selected_paths()
        if paths and not self.worker:
            self.invalidate_check()
            self.check_selection = paths
            self.start_job("check", paths=list(paths))

    @Slot()
    def prepare_apply(self):
        self.update_controls()
        if self.apply_button.isEnabled():
            self.start_job("prepare", check=self.check_payload)

    def confirm_apply(self, check):
        plan = check["plan"]
        phases = "\n".join(f"• {PHASES.get(k, k)}: {v}" for k, v in plan["phases"].items())
        text = (f"Un unico batch applicativo\nBatch: {', '.join(plan['batches'])}\n"
                f"Campagne ({len(plan['campaigns'])}):\n" + "\n".join(plan["campaigns"]) +
                f"\n\nFasi (oltre al QC dei punti):\n{phases}\n\nOutput e manifest:\n" + "\n".join(plan["targets"]) +
                "\n\nBackup:\n" + plan["backup"] + "\n\nArtefatti stale (da rigenerare separatamente):\n" + "\n".join(plan["stale"]))
        box = QMessageBox(self)
        box.setWindowTitle("Conferma aggiornamento del progetto")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText("Elaborare le campagne e aggiornare questa workspace?")
        box.setInformativeText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText("Elabora e aggiorna")
        box.button(QMessageBox.StandardButton.No).setText("Annulla")
        return box.exec() == QMessageBox.StandardButton.Yes

    def start_job(self, operation, **kwargs):
        if self.worker or not self.service or self._closing:
            return False
        self._result = self._error = None
        self.worker = ServiceWorker(self.service.workspace, operation, read_only=self.read_only, parent=self, **kwargs)
        self.worker.result.connect(self._receive_result, Qt.ConnectionType.QueuedConnection)
        self.worker.error.connect(self._receive_error, Qt.ConnectionType.QueuedConnection)
        self.worker.event.connect(self._receive_event, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        self.progress.setRange(0, 0)
        self.status_label.setText("Operazione in corso…")
        self.update_controls()
        self.worker.start()
        return True

    @Slot(object)
    def _receive_result(self, value):
        self._result = value

    @Slot(str)
    def _receive_error(self, error):
        self._error = error

    @Slot(object)
    def _receive_event(self, event):
        self.events.append(asdict(event))
        self.log.appendPlainText(json.dumps(asdict(event), ensure_ascii=False))
        if event.event == "critical_started":
            self._critical = True
        elif event.event in {"critical_completed", "run_cancelled", "run_failed"}:
            self._critical = False
        if not (self.worker and self.worker.token.requested):
            self.status_label.setText(event.message)

    @Slot()
    def _finished(self):
        worker = self.worker
        if worker is None:
            return
        worker.wait()
        operation, paths = worker.operation, worker.paths
        worker.deleteLater()
        self.worker = None
        self._critical = False
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        value = self._result or {}
        if self._error:
            self.invalidate_check()
            self.status_label.setText("Errore: " + self._error)
            self.log.appendPlainText("Errore: " + self._error)
        elif value.get("status") == "cancelled":
            self.invalidate_check()
            self.status_label.setText("Operazione annullata; pulizia completata")
        elif operation == "overview":
            self.show_overview(value)
        elif operation in {"discover", "check"}:
            self._rendering = True
            self.model.set_payload(value)
            if operation == "discover":
                self._show_batches(value["results"], paths)
            self._rendering = False
            self.table.resizeColumnsToContents()
            for column in range(self.model.columnCount()):
                self.table.setColumnWidth(column, min(self.table.columnWidth(column), 320))
            if operation == "check" and value.get("status") in {"pass", "warning"}:
                self.check_payload = value
                self.check_selection = self.selected_paths()
            self.last_report = value.get("report_path") or self.last_report
            self.status_label.setText(f"{len(self.model.items)} CSV · " + {"pass": "Controllo superato", "warning": "Controllo con avvisi", "fail": "Controllo fallito"}.get(value.get("status"), "Scansione completata"))
            if value.get("qc_error"):
                self.status_label.setText(str(value["qc_error"]))
            self.tabs.setCurrentIndex(1)
        elif operation == "apply":
            self.invalidate_check()
            self.last_report = value.get("report_path")
            self.status_label.setText("Aggiornamento completato")
            self.refresh()
        self.update_controls()
        if self._closing:
            self.close()
        elif operation == "prepare" and not self._error and value.get("status") in {"pass", "warning"}:
            if self.confirm_apply(value):
                self.update_controls()
                if self.apply_button.isEnabled():
                    self.start_job("apply", check=value)

    def _show_batches(self, items, paths):
        self.batch_list.clear()
        roots = paths or [str(self.service.workspace / "data/raw" / name) for name in sorted({i["batch"] for i in items})]
        for root in roots:
            path = Path(root)
            if path.is_file():
                path = path.parent
            count = sum(Path(i["absolute_path"]).is_relative_to(path) for i in items)
            item = QListWidgetItem(f"{path.name} · {count} CSV")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.batch_list.addItem(item)
            item.setSelected(True)
        counts = Counter(i["validation"].get("classification") for i in items)
        self.batch_summary.setText(f"{self.batch_list.count()} batch · {len(items)} CSV · {counts['canonical']} nuovi canonici · {counts['redundant']} ridondanti · {counts['ambiguous']} ambigui · {counts['invalid']} invalidi")

    def show_overview(self, value):
        status = value["status"]
        last = status.get("last_run") or {}
        self.last_report = self.last_report or last.get("report_path")
        warnings = status.get("warnings", [])
        self.overview_text.setPlainText(
            f"Workspace: {status['workspace']}\nDoctor: {'OK' if value['doctor']['valid'] else 'Non valida'}\n"
            f"Campagne registrate: {status.get('registered_campaigns', status['registered_files'])}\n"
            f"CSV registrati: {status['registered_files']}\nNuovi CSV: {status['new_files']}\n"
            f"Ultimo run: {last.get('run_id', 'Nessuno')} · {last.get('status', '')}\n"
            f"Lock: {status.get('lock') or 'Libero'}\nAvvisi: " + ("; ".join(warnings) or "Nessuno"))
        self.show_history(value["history"])
        self.status_label.setText("Panoramica aggiornata")

    def show_history(self, entries):
        self.history_table.setSortingEnabled(False)
        self.history_table.setRowCount(len(entries))
        for row, entry in enumerate(reversed(entries)):
            try:
                duration = f"{(datetime.fromisoformat(entry['finished_at']) - datetime.fromisoformat(entry['started_at'])).total_seconds():.1f} s" if entry.get("finished_at") else "In corso"
            except (ValueError, TypeError, KeyError):
                duration = "Non disponibile"
            values = [entry.get("run_id"), entry.get("started_at"), entry.get("command"), entry.get("status"),
                      duration, ", ".join(entry.get("campaigns", [])), entry.get("report_path") or "—", "Sì" if entry.get("rollback") else "No"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(value or ""))
                self.history_table.setItem(row, col, item)
        self.history_table.setSortingEnabled(True)
        self.history_table.resizeColumnsToContents()
        for column in range(self.history_table.columnCount()):
            self.history_table.setColumnWidth(column, min(self.history_table.columnWidth(column), 280))

    @Slot()
    def update_controls(self):
        ready = self.service is not None and self.worker is None and not self._closing
        for widget in (self.scan_button, self.add_button, self.refresh_button, self.batch_list, self.table):
            widget.setEnabled(ready)
        self.choose_button.setEnabled(self.worker is None and not self._closing)
        self.check_button.setEnabled(ready and bool(self.selected_paths()))
        self.cancel_button.setEnabled(self.worker is not None and not self.worker.token.requested)
        check = self.check_payload or {}
        try:
            locked = bool(self.service and self.service.lock_status())
        except (OSError, ValueError):
            locked = True
        allowed = (ready and not self.read_only and not locked and check.get("status") in {"pass", "warning"}
                   and self.selected_paths() == self.check_selection and check.get("plan", {}).get("campaigns")
                   and not check.get("plan", {}).get("external")
                   and not any(i.get("blocking_errors") or i.get("classification") in {"invalid", "ambiguous"}
                               for i in check.get("validation_results", [])))
        self.apply_button.setEnabled(bool(allowed))
        self.apply_button.setToolTip("Workspace bloccata" if locked else "Richiede un check valido della selezione corrente")
        for widget in (self.outputs_button, self.logs_button):
            widget.setEnabled(ready)
        self.report_button.setEnabled(ready and bool(self.last_report))
        self.csv_report_button.setEnabled(ready and bool(self.model.report))

    @Slot()
    def cancel_operation(self):
        if self.worker:
            self.worker.token.request()
            self.status_label.setText("Fase critica: annullamento al prossimo punto sicuro con rollback" if self._critical else "Annullamento richiesto: attendo il prossimo punto sicuro…")
            self.update_controls()

    @Slot(object)
    def show_details(self, index):
        if index.isValid():
            self.details.setPlainText(self.model.details(self.proxy.mapToSource(index).row()))

    @Slot(int, int)
    def open_history_report(self, row, _column):
        self.open_result(self.history_table.item(row, 6).text())

    def open_result(self, value):
        if not self.service or not value:
            self.status_label.setText("Nessun rapporto disponibile")
            return False
        try:
            path = self.service.result_path(value)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise OSError("Nessuna applicazione associata al risultato")
            return True
        except (OSError, ValueError) as exc:
            self.status_label.setText(f"Impossibile aprire il risultato: {exc}")
            return False

    def closeEvent(self, event):
        if self.worker:
            self._closing = True
            self.cancel_operation()
            event.ignore()
            return
        self.lock_timer.stop()
        if self.persist:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("filter", self.filter_edit.text())
            self.settings.sync()
        event.accept()
