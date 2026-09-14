"""Per-campaign local azimuthal-equidistant projection for planar distance
math. A fixed UTM zone was considered but rejected: Bologna-Ravenna sits near
the 32N/33N boundary (~70km apart), so a campaign-centered AEQD projection
removes zone-boundary risk entirely and is standard practice for local-scale
distance clustering. Independently implemented (same *technique* as
repeated_routes/tracks.py's forward/inverse transformer, never imported from
it).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Transformer


def build_local_transformer(latitudes: pd.Series | np.ndarray, longitudes: pd.Series | np.ndarray) -> Transformer:
    lat0 = float(np.nanmean(np.asarray(latitudes, dtype=float)))
    lon0 = float(np.nanmean(np.asarray(longitudes, dtype=float)))
    proj4 = f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +units=m +ellps=WGS84"
    return Transformer.from_crs("EPSG:4326", proj4, always_xy=True)


def project_xy(transformer: Transformer, latitudes: pd.Series | np.ndarray, longitudes: pd.Series | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lon = np.asarray(longitudes, dtype=float)
    lat = np.asarray(latitudes, dtype=float)
    x, y = transformer.transform(lon, lat)
    return np.asarray(x, dtype=float), np.asarray(y, dtype=float)


def planar_distance_m(x1: float, y1: float, x2: float, y2: float) -> float:
    return float(np.hypot(x2 - x1, y2 - y1))


def inverse_xy_to_lonlat(transformer: Transformer, x: float, y: float) -> tuple[float, float]:
    lon, lat = transformer.transform(x, y, direction="INVERSE")
    return float(lon), float(lat)
