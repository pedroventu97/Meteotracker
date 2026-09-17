"""Interactive, offline Qt map. Data loading and science live in the service."""
import json
import time

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from ..map_preview import draw_map, render_indices


class AnalysisNavigationToolbar(NavigationToolbar2QT):
    # File writes are routed through the application's dedicated custom export.
    toolitems = tuple(item for item in NavigationToolbar2QT.toolitems if item[3] != "save_figure")

    def save_figure(self, *args):
        return None


class RouteMap(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.preview = None
        self.frames = {}
        self.profile = "recommended"
        self.family_flags = []
        self.rendered = []
        self._updating = False
        self._last_hover = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        controls = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["Tutti i punti", "Punti mantenuti", "Punti flaggati", "Famiglia di flag", "Prima/dopo QC"])
        self.density = QCheckBox("Densità esplorativa")
        self.overlaps = QCheckBox("Sovrapposizioni 50 m")
        for widget in (self.mode, self.density, self.overlaps):
            controls.addWidget(widget)
        layout.addLayout(controls)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        side = QWidget()
        sl = QVBoxLayout(side)
        self.tracks = QListWidget()
        sl.addWidget(self.tracks, 1)
        visibility = QHBoxLayout()
        for label, checked in (("Tutte", True), ("Nessuna", False)):
            button = QPushButton(label)
            button.setToolTip("Mostra tutte le tracce" if checked else "Nascondi tutte le tracce")
            button.clicked.connect(lambda _=False, value=checked: self.show_all(value))
            visibility.addWidget(button)
        sl.addLayout(visibility)
        side.setMaximumWidth(250)
        splitter.addWidget(side)
        canvas_container = QWidget()
        cl = QVBoxLayout(canvas_container)
        cl.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(8, 5), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(100, 80)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.ax = self.figure.subplots()
        self.toolbar = AnalysisNavigationToolbar(self.canvas, self)
        cl.addWidget(self.toolbar)
        cl.addWidget(self.canvas, 1)
        splitter.addWidget(canvas_container)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([170, 800])
        layout.addWidget(splitter, 1)
        self.summary = QLabel("Seleziona sessioni per vedere le tracce originali prima del QC.")
        self.summary.setWordWrap(False)
        self.summary.setMaximumHeight(20)
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.point = QLabel("Passa sul punto o clicca per i dettagli. Zoom e pan nella barra della mappa.")
        self.point.setWordWrap(False)
        self.point.setMaximumHeight(20)
        self.point.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.point.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        layout.addWidget(self.point)
        legend = QLabel("▲ Partenza   ■ Arrivo   • Ordinari   ○ rosso: sospetti/flag   × viola: interruzione   → Direzione")
        legend.setWordWrap(True)
        layout.addWidget(legend)
        self.tracks.itemChanged.connect(self.redraw)
        self.mode.currentTextChanged.connect(self.redraw)
        self.density.toggled.connect(self.redraw)
        self.overlaps.toggled.connect(self.redraw)
        self.canvas.mpl_connect("pick_event", self.pick_point)
        self.canvas.mpl_connect("motion_notify_event", self.hover_point)

    def set_preview(self, preview):
        self.preview = preview
        self._updating = True
        self.tracks.clear()
        for track in preview["tracks"]:
            item = QListWidgetItem(track["campaign_id"])
            item.setData(Qt.ItemDataRole.UserRole, track["campaign_id"])
            item.setForeground(QColor(track["color"]))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(f"{track['source_file']}\n{track['start']} — {track['end']}\n{track['rows']} punti; {track['duration_s']} s; {track['distance_km']:.3f} km preliminari\nCoordinate mancanti: {track['missing_coordinates']}; non valide: {track['invalid_coordinates']}; salti preliminari: {track['preliminary_jumps']}")
            self.tracks.addItem(item)
        self._updating = False
        total = sum(t["rows"] for t in preview["tracks"])
        drawn = sum(len(render_indices(t["points"])) for t in preview["tracks"])
        descriptions = [f"{t['rows']} punti · {t['start']} — {t['end']} · {t['duration_s']} s · {t['distance_km']:.3f} km · GPS mancanti {t['missing_coordinates']}" for t in preview["tracks"]]
        full_summary = (f"{len(preview['tracks'])} sessioni · {total} punti · {preview['geographic_crs']} → {preview['metric_crs']} · "
                             + (f"Rendering decimato: {drawn}/{total}. Tutti i dati conservati. · " if drawn < total else "")
                             + preview["boundary_note"] + ("\n" + descriptions[0] if len(descriptions) == 1 else "\nStatistiche separate nei tooltip della legenda; densità e sovrapposizioni solo esplorative."))
        self.summary.setText(f"{len(preview['tracks'])} sessioni · {total} punti · {preview['geographic_crs']} → {preview['metric_crs']}" + (f" · Decimazione grafica: {drawn}/{total}" if drawn < total else "") + " · Dettagli al passaggio del mouse")
        self.summary.setToolTip(full_summary)
        self.redraw()

    def visible_ids(self):
        return [self.tracks.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.tracks.count())
                if self.tracks.item(i).checkState() == Qt.CheckState.Checked]

    def style(self):
        return {"visible": self.visible_ids(), "mode": self.mode.currentText(), "density": self.density.isChecked(),
                "overlaps": self.overlaps.isChecked(), "profile": self.profile, "family_flags": self.family_flags}

    def show_all(self, checked):
        self._updating = True
        for i in range(self.tracks.count()):
            self.tracks.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._updating = False
        self.redraw()

    def redraw(self, *_):
        if self._updating or not self.preview:
            return
        self.rendered = draw_map(self.ax, self.preview, frames=self.frames, show_legend=False, **self.style())
        self.canvas.draw_idle()

    def set_analysis(self, analysis):
        self.frames = analysis.frames if analysis else {}
        self.profile = analysis.report["settings"]["origin_profile"] if analysis else "recommended"
        self.redraw()

    def highlight_flags(self, flags):
        self.family_flags = list(flags)
        self.mode.setCurrentText("Famiglia di flag")
        self.redraw()

    def point_text(self, campaign_id, source_row):
        track = next(t for t in self.preview["tracks"] if t["campaign_id"] == campaign_id)
        values = track["points"].iloc[source_row]
        fields = ["time_utc", "Lat", "Lon", "Temp[°C]", "Hum[%]", "Press[mbar]", "Speed[km/h]"]
        text = f"{campaign_id} · riga sorgente {source_row}\n" + " · ".join(f"{k}: {values[k]}" for k in fields)
        flags = [k for k in values.index if k.startswith("preliminary_") and bool(values[k])]
        if campaign_id in self.frames:
            frame = self.frames[campaign_id]
            flags += [k for k in frame if k.startswith("qc_") and str(frame[k].dtype) in {"bool", "boolean"} and frame[k].fillna(False).iloc[source_row]]
        return text + "\nIndicatori: " + (", ".join(flags) or "nessuno")

    def pick_point(self, event):
        for artist, cid, indices in self.rendered:
            if event.artist == artist and len(event.ind):
                self.point.setText(self.point_text(cid, int(indices[event.ind[0]])))
                self.point.setToolTip(self.point.text())
                break

    def hover_point(self, event):
        if event.inaxes != self.ax or time.monotonic() - self._last_hover < .12:
            return
        self._last_hover = time.monotonic()
        for artist, cid, indices in self.rendered:
            contains, info = artist.contains(event)
            if contains and len(info["ind"]):
                self.point.setText(self.point_text(cid, int(indices[info["ind"][0]])))
                self.point.setToolTip(self.point.text())
                break
