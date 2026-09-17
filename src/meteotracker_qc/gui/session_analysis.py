"""Dedicated desktop analysis window; no scientific logic in widgets."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..analysis_settings import DEFAULT_ACTIVE
from ..session_analysis import AnalysisResult
from .analysis_worker import AnalysisWorker
from .log_panel import LogPanel
from .route_map import AnalysisNavigationToolbar, RouteMap


def fill_table(table, rows, columns):
    table.setSortingEnabled(False)
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels([label for _, label in columns])
    table.setRowCount(len(rows))
    for row, entry in enumerate(rows):
        for col, (key, _) in enumerate(columns):
            value = entry.get(key)
            text = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else str(value if value is not None else "—")
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            table.setItem(row, col, item)
    table.resizeColumnsToContents()
    for col in range(table.columnCount()):
        table.setColumnWidth(col, min(250, table.columnWidth(col)))


def readonly_table():
    table = QTableWidget()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    return table


def scroll_panel(widget):
    """Keep controls accessible without imposing their summed minimum on the window."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setMinimumSize(80, 60)
    return area


class SessionAnalysisWindow(QMainWindow):
    busy_changed = Signal()

    def __init__(self, service, *, settings=None, persist=True, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.service = service
        self.workspace = service.workspace
        self.settings = settings if settings is not None else QSettings("Meteotracker", "Desktop")
        self.persist = persist
        self.worker = None
        self.map_worker = None
        self.analysis = None
        self.sessions = []
        self.generation = 0
        self.pending_ids = []
        self._closing = False
        self._rendering = False
        self.setWindowTitle("Analizza sessioni — Anteprima read-only")
        self.resize(1240, 700)
        self._build_ui()
        if persist and self.settings.value("analysis_geometry"):
            self.restoreGeometry(self.settings.value("analysis_geometry"))
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(self.width(), area.width()), min(self.height(), area.height()))
        if not any(s.availableGeometry().intersects(self.frameGeometry()) for s in QApplication.screens()):
            self.move(area.topLeft())
        self.map_timer = QTimer(self)
        self.map_timer.setSingleShot(True)
        self.map_timer.setInterval(100)
        self.map_timer.timeout.connect(self._start_map)
        self.load_settings()
        self.refresh_sessions()

    @property
    def busy(self):
        return self.worker is not None

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        self.banner = QLabel(f"Anteprima read-only · {self.workspace}")
        self.banner.setTextFormat(Qt.TextFormat.PlainText)
        self.banner.setWordWrap(True)
        self.banner.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.banner)
        bar = QHBoxLayout()
        self.run_button = QPushButton("Anteprima QC")
        self.run_button.clicked.connect(self.run_preview)
        self.cancel_button = QPushButton("Annulla")
        self.cancel_button.clicked.connect(self.cancel)
        self.refresh_button = QPushButton("Aggiorna")
        self.refresh_button.setToolTip("Aggiorna l'elenco delle sessioni registrate")
        self.refresh_button.clicked.connect(self.refresh_sessions)
        self.back_button = QPushButton("Principale")
        self.back_button.setToolTip("Torna alla finestra principale senza chiudere l'analisi")
        self.back_button.clicked.connect(self.return_to_main)
        for widget in (self.run_button, self.cancel_button, self.refresh_button, self.back_button):
            bar.addWidget(widget)
        self.panels_button = QPushButton("Pannelli QC")
        self.panels_button.setCheckable(True)
        self.panels_button.setChecked(True)
        self.panels_button.toggled.connect(lambda visible: self.top.setVisible(visible))
        bar.addWidget(self.panels_button)
        layout.addLayout(bar)
        self.vertical = QSplitter(Qt.Orientation.Vertical)
        self.top = QSplitter(Qt.Orientation.Horizontal)
        selection = QWidget()
        sl = QVBoxLayout(selection)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cerca nome / campaign ID")
        sl.addWidget(self.search)
        filters = QHBoxLayout()
        self.date_from, self.date_to = QLineEdit(), QLineEdit()
        self.date_from.setPlaceholderText("Dal YYYY-MM-DD")
        self.date_to.setPlaceholderText("Al YYYY-MM-DD")
        self.batch, self.status_filter = QComboBox(), QComboBox()
        self.batch.addItem("Tutti i batch")
        self.status_filter.addItem("Tutti gli stati")
        for widget in (self.date_from, self.date_to, self.batch, self.status_filter):
            widget.setMinimumWidth(70)
            filters.addWidget(widget)
        sl.addLayout(filters)
        self.session_table = readonly_table()
        self.session_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.session_table.itemChanged.connect(self.selection_changed)
        sl.addWidget(self.session_table, 1)
        buttons = QHBoxLayout()
        for label, value in (("Seleziona visibili", True), ("Deseleziona tutto", False)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, checked=value: self.select_all(checked))
            buttons.addWidget(button)
        self.selection_label = QLabel("Nessuna sessione")
        buttons.addWidget(self.selection_label)
        sl.addLayout(buttons)
        self.top.addWidget(scroll_panel(selection))
        config = QWidget()
        cl = QVBoxLayout(config)
        self.profile = QComboBox()
        self.profile.addItems(["Recommended", "Permissive", "Restrictive", "Personalizzato"])
        self.origin = QComboBox()
        self.origin.addItems(["recommended", "permissive", "restrictive"])
        cl.addWidget(QLabel("Profilo QC / origine personalizzato"))
        cl.addWidget(self.profile)
        cl.addWidget(self.origin)
        self.group_box = QWidget()
        self.group_layout = QVBoxLayout(self.group_box)
        self.group_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.group_box)
        cl.addWidget(scroll, 1)
        self.groups = {}
        preset_bar = QHBoxLayout()
        for label, callback in (("Ripristina", self.reset_settings), ("Salva preset", self.save_preset), ("Carica preset", self.load_preset)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            preset_bar.addWidget(button)
        cl.addLayout(preset_bar)
        self.top.addWidget(scroll_panel(config))
        thresholds = QWidget()
        tl = QVBoxLayout(thresholds)
        tl.addWidget(QLabel("Soglie e unità — modifica solo in Personalizzato"))
        self.parameters = QTableWidget()
        self.parameters.itemChanged.connect(self.parameter_changed)
        tl.addWidget(self.parameters, 1)
        self.differences = QPlainTextEdit()
        self.differences.setReadOnly(True)
        self.differences.setMaximumHeight(75)
        tl.addWidget(self.differences)
        rules_button = QPushButton("Soglie e regole Session QC / suitability")
        rules_button.clicked.connect(self.show_session_rules)
        tl.addWidget(rules_button)
        self.top.addWidget(scroll_panel(thresholds))
        self.top.setSizes([540, 280, 360])
        self.vertical.addWidget(self.top)
        lower = QWidget()
        ll = QVBoxLayout(lower)
        ll.setContentsMargins(4, 4, 4, 4)
        self.result_session = QComboBox()
        self.result_session.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.result_session.setMinimumContentsLength(16)
        self.result_session.currentTextChanged.connect(self.show_session_result)
        ll.addWidget(self.result_session)
        self.tabs = QTabWidget()
        self.summary_table = readonly_table()
        self.tabs.addTab(self.summary_table, "Riepilogo")
        flags = QWidget()
        fl = QVBoxLayout(flags)
        self.flags_table = readonly_table()
        self.flags_table.cellClicked.connect(self.show_flag)
        self.flag_details = QPlainTextEdit()
        self.flag_details.setReadOnly(True)
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.flags_table)
        split.addWidget(self.flag_details)
        fl.addWidget(split)
        self.tabs.addTab(flags, "Flag")
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        times = QWidget()
        ts = QVBoxLayout(times)
        self.time_canvas = FigureCanvasQTAgg(Figure(figsize=(8, 5)))
        self.time_toolbar = AnalysisNavigationToolbar(self.time_canvas, self)
        ts.addWidget(self.time_toolbar)
        ts.addWidget(self.time_canvas, 1)
        self.tabs.addTab(times, "Serie temporali")
        self.map = RouteMap()
        self.tabs.addTab(self.map, "Mappa")
        self.comparison = readonly_table()
        self.tabs.addTab(self.comparison, "Confronto")
        export = QWidget()
        el = QVBoxLayout(export)
        export_note = QLabel("Export esclusivamente in outputs/custom_analyses/<id>/ · Nessuna promozione ufficiale")
        export_note.setWordWrap(True)
        el.addWidget(export_note)
        self.formats = {}
        formats = QHBoxLayout()
        for kind in ("csv", "parquet", "markdown", "json", "config", "figures", "gpkg", "geojson"):
            check = QCheckBox(kind)
            check.setChecked(True)
            self.formats[kind] = check
            formats.addWidget(check)
        el.addLayout(formats)
        self.export_button = QPushButton("Salva analisi personalizzata")
        self.export_button.clicked.connect(self.export_analysis)
        self.map_export_button = QPushButton("Esporta mappa e selezione (anche prima del QC)")
        self.map_export_button.clicked.connect(self.export_map)
        self.discard_button = QPushButton("Elimina anteprima temporanea")
        self.discard_button.clicked.connect(self.discard_analysis)
        for widget in (self.export_button, self.map_export_button, self.discard_button):
            el.addWidget(widget)
        self.export_path = QLineEdit()
        self.export_path.setReadOnly(True)
        el.addWidget(self.export_path)
        el.addStretch()
        self.tabs.addTab(scroll_panel(export), "Export")
        self.log = LogPanel()
        self.tabs.addTab(self.log, "Log")
        self.tabs.setCurrentWidget(self.map)
        ll.addWidget(self.tabs, 1)
        self.vertical.addWidget(lower)
        self.vertical.setSizes([180, 490])
        self.vertical.setStretchFactor(1, 1)
        layout.addWidget(self.vertical, 1)
        self.message = QLabel("Pronto")
        self.message.setWordWrap(True)
        self.message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.setCentralWidget(central)
        self.profile.currentTextChanged.connect(self.profile_changed)
        self.origin.currentTextChanged.connect(self.load_settings)
        for edit in (self.search, self.date_from, self.date_to):
            edit.textChanged.connect(self.apply_filters)
        for combo in (self.batch, self.status_filter):
            combo.currentTextChanged.connect(self.apply_filters)

    def selected_ids(self):
        return [self.session_table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in range(self.session_table.rowCount())
                if self.session_table.item(r, 0).checkState() == Qt.CheckState.Checked]

    def select_all(self, checked):
        self._rendering = True
        for row in range(self.session_table.rowCount()):
            if not checked or not self.session_table.isRowHidden(row):
                self.session_table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._rendering = False
        self.selection_changed()

    def apply_filters(self, *_):
        for row, item in enumerate(self.sessions):
            show = self.search.text().casefold() in (item["campaign_id"] + " " + item["source_file"]).casefold()
            show &= not self.date_from.text() or item["date"] >= self.date_from.text()
            show &= not self.date_to.text() or item["date"] <= self.date_to.text()
            show &= self.batch.currentIndex() == 0 or item["batch"] == self.batch.currentText()
            show &= self.status_filter.currentIndex() == 0 or item["session_qc_status"] == self.status_filter.currentText()
            self.session_table.setRowHidden(row, not show)

    def selection_changed(self, *_):
        if self._rendering:
            return
        self.pending_ids = self.selected_ids()
        self.generation += 1
        self.selection_label.setText(f"{len(self.pending_ids)} / {len(self.sessions)} selezionate")
        if self.map_worker:
            self.map_worker.token.request()
        self.map_timer.start()
        self.update_controls()

    def _start_map(self):
        if self._closing or self.map_worker:
            return
        if not self.pending_ids:
            self.map.set_preview({"tracks": [], "boundary": [], "boundary_note": "Nessuna selezione", "metric_crs": "—", "geographic_crs": "—"})
            return
        worker = AnalysisWorker(self.service, "preview_tracks", generation=self.generation,
                                kwargs={"campaign_ids": self.pending_ids.copy()}, parent=self)
        self.map_worker = worker
        worker.result.connect(lambda value, w=worker: self.accept_map(w.generation, value), Qt.ConnectionType.QueuedConnection)
        worker.error.connect(lambda error, w=worker: self.map_error(w.generation, error), Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self.map_finished, Qt.ConnectionType.QueuedConnection)
        worker.start()

    def accept_map(self, generation, value):
        if generation != self.generation or self._closing or value.get("status") == "cancelled":
            return
        self.map.set_preview(value)
        self.update_controls()

    def map_error(self, generation, error):
        if generation == self.generation:
            self.log.message(error, phase="map_preview")
            self.message.setText(error)

    def map_finished(self):
        worker = self.map_worker
        worker.wait()
        previous = worker.generation
        worker.deleteLater()
        self.map_worker = None
        if self._closing:
            self.close()
        elif previous != self.generation:
            self._start_map()

    def load_settings(self, *_):
        if self._rendering:
            return
        self._rendering = True
        self.settings_description = self.service.describe_qc_settings(self.origin.currentText())
        for check in self.groups.values():
            self.group_layout.removeWidget(check)
            check.deleteLater()
        self.groups = {}
        for group in self.settings_description["groups"]:
            check = QCheckBox(group["label"])
            check.setChecked(group["active"])
            check.setEnabled(group["editable"])
            thresholds = "; ".join(f"{k} = {v['value']} {v['unit']}" for k, v in group["parameters"].items())
            check.setToolTip(f"{group['description']}\n{thresholds or 'Nessuna soglia indipendente'}\nOrigine: {group['source']}\nProfilo: {group['profile']}")
            check.toggled.connect(self.control_changed)
            self.group_layout.addWidget(check)
            self.groups[group["id"]] = check
        rows = [{"key": k, **v} for k, v in self.settings_description["parameters"].items()]
        fill_table(self.parameters, rows, [("key", "Parametro"), ("value", "Valore"), ("unit", "Unità"), ("min", "Min"), ("max", "Max")])
        self._rendering = False
        self.update_parameter_editability()
        self.update_differences()

    def profile_changed(self, text):
        if self._rendering:
            return
        if text != "Personalizzato":
            self.origin.blockSignals(True)
            self.origin.setCurrentText(text.lower())
            self.origin.blockSignals(False)
            self.load_settings()
        self.update_parameter_editability()

    def update_parameter_editability(self):
        self._rendering = True
        custom = self.profile.currentText() == "Personalizzato"
        self.origin.setEnabled(custom and not self.busy)
        for row in range(self.parameters.rowCount()):
            for col in range(self.parameters.columnCount()):
                item = self.parameters.item(row, col)
                flags = item.flags() & ~Qt.ItemFlag.ItemIsEditable
                if custom and col == 1:
                    flags |= Qt.ItemFlag.ItemIsEditable
                item.setFlags(flags)
        self._rendering = False

    def control_changed(self, *_):
        if not self._rendering:
            self.profile.setCurrentText("Personalizzato")
            self.update_differences()

    def parameter_changed(self, *_):
        if not self._rendering:
            self.update_differences()

    def runtime_options(self):
        overrides = {}
        if self.profile.currentText() == "Personalizzato":
            for row in range(self.parameters.rowCount()):
                key = self.parameters.item(row, 0).text()
                value = float(self.parameters.item(row, 1).text())
                overrides[key] = {"value": value, "unit": self.parameters.item(row, 2).text()}
        return {"profile": self.origin.currentText(), "active_controls": [k for k, v in self.groups.items() if v.isChecked()], "overrides": overrides}

    def update_differences(self):
        try:
            options = self.runtime_options()
            settings = self.service.validate_custom_settings(**options)
            description = self.service.describe_qc_settings(**options)
            for group in description["groups"]:
                thresholds = "; ".join(f"{k} = {v['value']} {v['unit']}" for k, v in group["parameters"].items())
                self.groups[group["id"]].setToolTip(f"{group['description']}\n{thresholds or 'Nessuna soglia indipendente'}\nOrigine: {group['source']}\nProfilo: {group['profile']}\n{'Attivo' if group['active'] else 'Non valutato'}")
            lines = [f"{k}: {v['from']} → {v['value']} {v['unit']}" for k, v in settings["differences"].items()]
            if settings["disabled_controls"]:
                lines.append("Disattivati: " + ", ".join(settings["disabled_controls"]))
            self.differences.setPlainText("\n".join(lines) or "Valori predefiniti del profilo di origine")
        except ValueError as exc:
            self.differences.setPlainText("Impostazioni non valide: " + str(exc))

    def reset_settings(self):
        self.profile.setCurrentText(self.origin.currentText().capitalize())
        self.load_settings()

    def show_session_rules(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Regole effettive — recommended_session (sola lettura)")
        dialog.resize(850, 450)
        layout = QVBoxLayout(dialog)
        table = readonly_table()
        fill_table(table, self.settings_description["session_rules"], [(k, k) for k in
            ("rule_id", "level", "analysis_type", "metric", "operator", "threshold", "unit", "resulting_status", "source", "rationale")])
        layout.addWidget(table)
        dialog.exec()

    def save_preset(self):
        name, ok = QInputDialog.getText(self, "Preset utente", "Nome")
        if not ok:
            return
        description, ok = QInputDialog.getText(self, "Preset utente", "Descrizione (facoltativa)")
        if not ok:
            return
        try:
            path = self.service.save_analysis_preset(name, description=description, **self.runtime_options())
            self.message.setText(f"Preset salvato: {path}")
        except (ValueError, OSError) as exc:
            self.message.setText(str(exc))

    def load_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "Carica preset", str(self.workspace / "user_presets"), "JSON (*.json)")
        if not path:
            return
        try:
            preset = self.service.load_analysis_preset(path)
            self.profile.setCurrentText("Personalizzato")
            self.origin.setCurrentText(preset["origin_profile"])
            self.load_settings()
            self._rendering = True
            for key, check in self.groups.items():
                check.setChecked(key in preset["active_controls"])
            for row in range(self.parameters.rowCount()):
                override = preset["overrides"].get(self.parameters.item(row, 0).text())
                if override:
                    self.parameters.item(row, 1).setText(str(override["value"]))
            self._rendering = False
            self.update_differences()
        except (ValueError, OSError, KeyError) as exc:
            self._rendering = False
            self.message.setText(str(exc))

    def start_job(self, operation, **kwargs):
        if self.worker or self._closing:
            return False
        self._value = None
        self.worker = AnalysisWorker(self.service, operation, kwargs=kwargs, parent=self)
        self.worker.result.connect(self.receive_result, Qt.ConnectionType.QueuedConnection)
        self.worker.error.connect(self.receive_error, Qt.ConnectionType.QueuedConnection)
        self.worker.event.connect(self.log.append_event, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self.job_finished, Qt.ConnectionType.QueuedConnection)
        self.message.setText("Operazione in corso…")
        self.update_controls()
        self.busy_changed.emit()
        self.worker.start()
        return True

    def receive_result(self, value):
        self._value = value

    def receive_error(self, error):
        self.message.setText(error)
        self.log.message(error)

    def job_finished(self):
        worker = self.worker
        worker.wait()
        operation = worker.operation
        self.worker = None
        worker.deleteLater()
        value = self._value
        if isinstance(value, dict) and value.get("status") == "cancelled":
            self.message.setText("Operazione annullata; dati ufficiali invariati")
        elif operation == "list_sessions" and value is not None:
            self.sessions = value
            self._rendering = True
            fill_table(self.session_table, value, [("campaign_id", "Sessione"), ("date", "Data"), ("start", "Inizio UTC"),
                ("end", "Fine UTC"), ("source_file", "Sorgente"), ("batch", "Batch"), ("rows", "Righe"),
                ("duration_s", "Durata s"), ("distance_km", "Distanza km"), ("session_qc_status", "Session QC"),
                ("suitability", "Suitability"), ("available_outputs", "Output disponibili")])
            for row, entry in enumerate(value):
                item = self.session_table.item(row, 0)
                item.setData(Qt.ItemDataRole.UserRole, entry["campaign_id"])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
            for combo, key, title in ((self.batch, "batch", "Tutti i batch"), (self.status_filter, "session_qc_status", "Tutti gli stati")):
                combo.clear()
                combo.addItems([title, *sorted({str(r[key]) for r in value})])
            self._rendering = False
            self.selection_changed()
            self.message.setText(f"{len(value)} sessioni dal manifest")
        elif isinstance(value, AnalysisResult):
            self.discard_analysis()
            self.analysis = value
            self.result_session.clear()
            self.result_session.addItems([r["campaign_id"] for r in value.report["sessions"]])
            self.map.set_analysis(value)
            rows = self.service.compare_sessions(analysis=value)
            fill_table(self.comparison, rows, [(key, key) for key in rows[0]])
            self.message.setText("Anteprima completata · Sessioni separate · Nessun output ufficiale modificato")
        elif isinstance(value, str):
            self.export_path.setText(value)
            self.message.setText("Export personalizzato salvato")
        self.update_controls()
        self.busy_changed.emit()
        if self._closing:
            self.close()

    def refresh_sessions(self):
        self.start_job("list_sessions")

    def run_preview(self):
        try:
            options = self.runtime_options()
            self.service.validate_custom_settings(**options)
            self.start_job("preview_qc", campaign_ids=self.selected_ids(), **options)
        except ValueError as exc:
            self.message.setText(str(exc))

    def show_session_result(self, cid):
        if not self.analysis or cid not in self.analysis.frames:
            return
        summary = next(r for r in self.analysis.report["sessions"] if r["campaign_id"] == cid)
        fill_table(self.summary_table, [{"key": k, "value": v} for k, v in summary.items()], [("key", "Metrica"), ("value", "Valore")])
        rows = [{"flag": k, "count": v, "kind": "flag", "evaluation": summary["flag_evaluation"][k]} for k, v in summary["flags"].items()]
        rows += [{"flag": k, "count": v, "kind": "famiglia (unione)"} for k, v in summary["flag_families"].items()]
        fill_table(self.flags_table, rows, [("flag", "Flag / famiglia"), ("count", "Osservazioni"), ("kind", "Tipo"), ("evaluation", "Valutazione")])
        # Rendering only: QC and file IO have already completed in the worker.
        from ..analysis_plots import timeseries_figure
        figure = timeseries_figure(self.analysis.frames[cid], summary["profile"])
        self.time_canvas.figure = figure
        figure.set_canvas(self.time_canvas)
        self.time_canvas.draw_idle()
        self.time_toolbar.update()

    def show_flag(self, row, _column):
        if not self.analysis:
            return
        import pandas as pd
        cid = self.result_session.currentText()
        frame = self.analysis.frames[cid]
        name = self.flags_table.item(row, 0).text()
        policy = pd.read_csv(self.analysis.root / "config/flag_policy.csv")
        flags = [name] if name in frame else policy.loc[(policy.reason_family == name) & (policy.action != "NOT_APPLICABLE"), "flag_name"].tolist()
        flags = [f for f in flags if f in frame]
        mask = frame[flags].fillna(False).any(axis=1)
        columns = [c for c in ["source_row", "time_utc", "Lat", "Lon", "Temp[°C]", *flags] if c in frame]
        details = frame.loc[mask, columns]
        self.flag_details.setPlainText(f"{len(details)} osservazioni; prime 500 mostrate, dettaglio completo nel CSV flagged.\n" + details.head(500).to_string(index=False))
        self.map.highlight_flags(flags)

    def export_analysis(self):
        if self.analysis:
            self.start_job("export_custom_analysis", analysis=self.analysis, formats=[k for k, check in self.formats.items() if check.isChecked()])

    def export_map(self):
        if self.map.preview:
            self.start_job("export_track_preview", preview=self.map.preview, style=self.map.style(),
                           frames=self.map.frames, formats=[k for k, check in self.formats.items() if check.isChecked()])

    def discard_analysis(self):
        if self.analysis:
            self.analysis.close()
            self.analysis = None
            self.map.set_analysis(None)
            self.result_session.clear()
            self.summary_table.setRowCount(0)
            self.flags_table.setRowCount(0)
            self.comparison.setRowCount(0)

    def update_controls(self):
        busy = self.busy
        self.run_button.setEnabled(not busy and bool(self.selected_ids()) and not self._closing)
        self.cancel_button.setEnabled(busy)
        self.refresh_button.setEnabled(not busy)
        self.top.setEnabled(not busy)
        self.export_button.setEnabled(not busy and self.analysis is not None)
        self.map_export_button.setEnabled(not busy and self.map.preview is not None and bool(self.map.visible_ids()))
        self.discard_button.setEnabled(not busy and self.analysis is not None)

    def cancel(self):
        if self.worker:
            self.worker.token.request()
            self.message.setText("Annullamento richiesto al prossimo confine di fase")

    def return_to_main(self):
        if self.parentWidget():
            self.parentWidget().showNormal()
            self.parentWidget().raise_()
            self.parentWidget().activateWindow()

    def closeEvent(self, event):
        if self.worker and not self._closing:
            answer = QMessageBox.question(self, "Analisi attiva", "Annullare l'operazione e chiudere al prossimo punto sicuro?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._closing = True
            self.cancel()
        if self.map_worker:
            self._closing = True
            self.map_worker.token.request()
        if self.worker or self.map_worker:
            event.ignore()
            return
        self.map_timer.stop()
        self.discard_analysis()
        if self.persist:
            self.settings.setValue("analysis_geometry", self.saveGeometry())
            self.settings.sync()
        self._closing = False
        event.accept()
