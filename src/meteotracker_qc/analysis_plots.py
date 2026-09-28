"""Lightweight reproducible plots; no pyplot global state in background workers."""
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg


def timeseries_figure(frame, profile):
    figure = Figure(figsize=(9, 7))
    axes = figure.subplots(3, 1, sharex=True)
    time = frame.time_utc
    keep = frame[f"keep_{profile}"]
    for ax, column, label in zip(axes[:2], ("Temp[°C]", "speed_device_kmh"), ("Temperatura [°C]", "Velocità [km/h]")):
        values = pd.to_numeric(frame.get(column, pd.Series(np.nan, index=frame.index)), errors="coerce")
        ax.plot(time, values, color="#999999", lw=.8, label="Prima QC")
        ax.plot(time, values.where(keep), color="#0072B2", lw=1, label="Dopo QC")
        ax.set_ylabel(label)
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    flags = [c for c in frame if c.startswith("qc_") and pd.api.types.is_bool_dtype(frame[c])]
    for i, name in enumerate(f for f in flags if frame[f].fillna(False).any()):
        mask = frame[name].fillna(False)
        axes[2].scatter(time[mask], np.full(int(mask.sum()), i), s=4, label=name)
    axes[2].set_ylabel("Flag QC")
    axes[2].set_xlabel("Ora UTC")
    if axes[2].collections:
        axes[2].legend(fontsize=5, loc="upper left", bbox_to_anchor=(1, 1))
    figure.subplots_adjust(left=0.10, right=0.80, top=0.97, bottom=0.10, hspace=0.24)
    return figure


def write_session_figures(frame, summary, directory, token):
    token.checkpoint()
    figure = timeseries_figure(frame, summary["profile"])
    FigureCanvasAgg(figure)
    figure.savefig(directory / "timeseries.png", dpi=120)
    figure.clear()
    token.checkpoint()
    figure = Figure(figsize=(7, 6), layout="constrained")
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    for _, points in frame.groupby("segment_id"):
        ax.plot(points.Lon, points.Lat, lw=.7, c="#999999")
    keep = frame[f"keep_{summary['profile']}"]
    ax.scatter(frame.loc[keep, "Lon"], frame.loc[keep, "Lat"], s=4, label="Mantenuti")
    ax.scatter(frame.loc[~keep, "Lon"], frame.loc[~keep, "Lat"], s=9, label="Esclusi", color="#dc2626")
    ax.set_xlabel("Longitudine [°] — EPSG:4326")
    ax.set_ylabel("Latitudine [°]")
    ax.set_title("Prima/dopo QC (nessuna misura in gradi)")
    ax.grid(alpha=.2)
    ax.legend()
    figure.savefig(directory / "map.png", dpi=120)
    figure.clear()
