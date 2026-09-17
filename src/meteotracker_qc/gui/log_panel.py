"""Readable event log with expandable structured details."""
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.events = []
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.level = QComboBox()
        self.level.addItems(["Tutti", "info", "warning", "error"])
        self.session = QLineEdit()
        self.session.setPlaceholderText("Filtra sessione")
        self.copy_button = QPushButton("Copia messaggio")
        self.save_button = QPushButton("Salva log")
        for widget in (self.level, self.session, self.copy_button, self.save_button):
            filters.addWidget(widget)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Ora", "Livello", "Fase", "Sessione", "Messaggio", "Avanzamento"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.toggle = QPushButton("Dettagli tecnici")
        self.toggle.setCheckable(True)
        self.technical = QPlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setVisible(False)
        self.technical.setMaximumHeight(160)
        self.toggle.toggled.connect(self.technical.setVisible)
        layout.addWidget(self.toggle)
        layout.addWidget(self.technical)
        self.feedback = QLabel()
        layout.addWidget(self.feedback)
        self.level.currentTextChanged.connect(self.refresh)
        self.session.textChanged.connect(self.refresh)
        self.copy_button.clicked.connect(self.copy_message)
        self.save_button.clicked.connect(self.save_dialog)

    def append_event(self, event):
        item = asdict(event) if is_dataclass(event) else dict(event)
        self.events.append(item)
        self.technical.appendPlainText(json.dumps(item, ensure_ascii=False, default=str))
        self.refresh()

    def message(self, message, level="error", phase="gui"):
        self.append_event({"timestamp_utc": datetime.now(timezone.utc).isoformat(), "level": level,
                           "phase": phase, "message": message})

    def refresh(self, *_):
        rows = [e for e in self.events if (self.level.currentText() == "Tutti" or e.get("level", "info") == self.level.currentText())
                and self.session.text().casefold() in str(e.get("campaign_id") or "").casefold()]
        self.table.setRowCount(len(rows))
        for row, entry in enumerate(rows):
            values = [entry.get("timestamp_utc", ""), entry.get("level", "info"), entry.get("phase", ""),
                      entry.get("campaign_id") or "", entry.get("message", ""),
                      f"{entry['progress']:.0%}" if entry.get("progress") is not None else ""]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, column, item)
        self.table.setColumnWidth(4, 420)

    def copy_message(self):
        row = self.table.currentRow()
        if row >= 0:
            QApplication.clipboard().setText(self.table.item(row, 4).text())

    def save_to(self, path):
        # Exclusive creation prevents accidental replacement of any selected existing file.
        with Path(path).open("x", encoding="utf-8") as handle:
            json.dump(self.events, handle, indent=2, ensure_ascii=False, default=str)

    def save_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva nuovo log", "meteotracker-log.json", "JSON (*.json)")
        if path:
            try:
                self.save_to(path)
                self.feedback.setText("Log salvato")
            except OSError as exc:
                self.feedback.setText(str(exc))
