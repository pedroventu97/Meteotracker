"""Synthetic raw input only; all scientific outputs are produced by the service."""
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from pyproj import Transformer

from meteotracker_qc.config_resources import resource
from meteotracker_qc.ingestion import PROFILE_NAMES
from meteotracker_qc.repeated_routes.config import load_config

CONFIG_NAMES = [
    "qc_permissive.yaml", "qc_recommended.yaml", "qc_restrictive.yaml",
    "repeated_routes_recommended.yaml", "flag_policy.csv", "session_qc_policy.csv",
    "session_suitability_policy.csv", "repeated_location_matching.csv", "temporal_drift_policy.csv",
]
MANIFEST_COLUMNS = [
    "source_file", "file_sha256", "core_content_hash", "canonical_campaign_id",
    "duplicate_group_id", "duplicate_type", "is_canonical", "canonical_source_file",
    "exclude_from_analysis", "exclude_reason", "keep_raw", "notes",
]


def empty_workspace(root: Path) -> Path:
    for name in ("data/raw", "data/manifests", "config", "logs", "outputs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for name in (*PROFILE_NAMES, "session_qc", "repeated_routes", "spatial_density", "temporal_drift"):
        (root / "outputs" / name).mkdir()
    for name in CONFIG_NAMES:
        (root / "config" / name).write_bytes(resource(name).read_bytes())
    pd.DataFrame(columns=MANIFEST_COLUMNS).to_csv(root / "data/manifests/campaign_manifest.csv", index=False)
    return root


def write_route(path: Path, *, offset: float = 0, reverse: bool = False, n: int = 101,
                gap: bool = False, hour: int = 0) -> None:
    cfg = load_config("recommended")
    forward = Transformer.from_crs(cfg.crs_geographic_epsg, cfg.crs_metric_epsg, always_xy=True)
    inverse = Transformer.from_crs(cfg.crs_metric_epsg, cfg.crs_geographic_epsg, always_xy=True)
    x0, y0 = forward.transform(11.34, 44.49)
    x = np.full(n, x0 + offset)
    y = y0 + np.arange(n, dtype=float) * 5
    if reverse:
        y = y[::-1]
    lon, lat = inverse.transform(x, y)
    seconds = np.arange(n)
    if gap:
        seconds[n // 2:] += 3600
    time = pd.Timestamp("2026-01-01T10:00:00Z") + pd.Timedelta(hours=hour) + pd.to_timedelta(seconds, unit="s")
    frame = pd.DataFrame({"Time": time.astype(str), "Lat": lat, "Lon": lon,
                          "Temp[°C]": 15.0, "Hum[%]": 50.0, "Press[mbar]": 1010.0,
                          "Speed[km/h]": 18.0, "Alt[m]": 50.0})
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def batch_workspace(root: Path) -> Path:
    empty_workspace(root)
    for i, offset in enumerate((-10, 0, 10, 20)):
        write_route(root / f"data/raw/batch città/route{i}.csv", offset=offset, hour=i)
    write_route(root / "data/raw/batch two/deep/opposite.csv", reverse=True, hour=4)
    write_route(root / "data/raw/batch two/short21.csv", n=21, hour=5)
    write_route(root / "data/raw/batch two/short91.csv", n=91, hour=6)
    write_route(root / "data/raw/batch two/gap.csv", n=202, gap=True, hour=7)
    shutil.copyfile(root / "data/raw/batch città/route0.csv", root / "data/raw/batch two/z_redundant.csv")
    return root
