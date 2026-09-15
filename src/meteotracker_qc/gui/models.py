"""Presentation of service payloads; no scientific calculations."""
import json

from PySide6.QtCore import QAbstractTableModel, Qt

HEADERS = ["Stato", "Batch", "File", "Campagna", "Righe", "Inizio", "Fine", "QC", "Suitability", "Route matching", "Problemi", "Rapporto"]
STATES = {"canonical": "Nuovo canonico", "redundant": "Ridondante", "registered": "Registrato",
          "ambiguous": "Ambiguo", "invalid": "Invalido"}


class CsvModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.preview = {}
        self.report = None

    def set_payload(self, payload):
        self.beginResetModel()
        self.items = payload.get("results", [])
        self.preview = payload.get("per_csv", {})
        self.report = payload.get("report_path")
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent and parent.isValid() else len(self.items)

    def columnCount(self, parent=None):
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]

    def values(self, item):
        value = item["validation"]
        campaign = value.get("proposed_campaign_id", "")
        preview = self.preview.get(campaign, {})
        state = "Invalido" if value.get("blocking_errors") else STATES.get(value.get("classification"), "Sconosciuto")
        if value.get("warnings"):
            state += " · Avvisi"
        return [state, item["batch"], item["source_file"], campaign, value.get("rows", 0),
                value.get("time_start_utc") or "—", value.get("time_end_utc") or "—",
                preview.get("qc", "Da controllare"),
                "; ".join(f"{k}: {v}" for k, v in preview.get("suitability", {}).items()) or "Non disponibile",
                preview.get("route_matching", "Non eseguito"),
                "; ".join(value.get("blocking_errors", []) + value.get("warnings", [])), self.report or "—"]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole):
            return self.values(item)[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return "\n".join(f"{h}: {v}" for h, v in zip(HEADERS, self.values(item)))

    def details(self, row):
        item = self.items[row]
        return json.dumps(item | {"anteprima": self.preview.get(item["validation"].get("proposed_campaign_id"), {})},
                          ensure_ascii=False, indent=2, default=str)
