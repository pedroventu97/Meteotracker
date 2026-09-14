"""Spatial gridding and visit-detection for repeated-passage density analysis.

Operates on the metric x_m/y_m coordinates already produced by
``repeated_routes.tracks.prepare_campaign_tracks`` (EPSG:32632 by default,
section 4 of the repeated-routes spec). A grid cell is a square of side
``cell_size_m`` anchored at the metric-CRS origin (col = floor(x / size),
row = floor(y / size)), so grids at different resolutions are defined the
same reproducible way regardless of data extent.

A "visit" is a maximal run of temporally consecutive points, within one
campaign part, that fall in the same cell. No additional time-gap check is
applied here: campaign parts (``PartTrack.points``) are already split on long
temporal gaps and implausible-speed jumps in ``tracks.assign_campaign_parts``
(``part_split_time_gap_s`` / ``part_split_max_speed_kmh``), and only QC-valid
points (``use_for_route_mapping`` & non-missing coordinates) ever reach a
part in the first place (``tracks.valid_geometry_mask``). A visit therefore
never bridges a GPS-freeze/jump-excluded stretch or an unrelated long stop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def cell_indices(x: np.ndarray, y: np.ndarray, cell_size_m: float) -> tuple[np.ndarray, np.ndarray]:
    col = np.floor(np.asarray(x, dtype=float) / cell_size_m).astype(np.int64)
    row = np.floor(np.asarray(y, dtype=float) / cell_size_m).astype(np.int64)
    return col, row


def detect_visits_for_part(points: pd.DataFrame, cell_size_m: float) -> pd.DataFrame:
    """Assign (col, row, visit_run_id) to each point of one time-ordered, continuous
    campaign part. visit_run_id increments whenever the cell differs from the
    previous point's cell; a later return to the same cell starts a new run.
    """
    if points.empty:
        return pd.DataFrame(columns=["col", "row", "visit_run_id"])
    col, row = cell_indices(points["x_m"].to_numpy(), points["y_m"].to_numpy(), cell_size_m)
    changed = np.empty(len(col), dtype=bool)
    changed[0] = True
    if len(col) > 1:
        changed[1:] = (col[1:] != col[:-1]) | (row[1:] != row[:-1])
    visit_run_id = np.cumsum(changed) - 1
    return pd.DataFrame({"col": col, "row": row, "visit_run_id": visit_run_id})


def raw_observation_counts(xy_by_campaign: dict[str, pd.DataFrame], cell_size_m: float) -> pd.DataFrame:
    """Count all geolocatable points (any campaign, any QC status) per cell.

    ``xy_by_campaign`` values must carry x_m/y_m columns in the same metric CRS
    used for ``cell_size_m``; callers decide which points are "geolocatable"
    (e.g. non-missing coordinates only).
    """
    frames = [df[["x_m", "y_m"]] for df in xy_by_campaign.values() if not df.empty]
    if not frames:
        return pd.DataFrame(columns=["col", "row", "n_observations"])
    all_points = pd.concat(frames, ignore_index=True)
    col, row = cell_indices(all_points["x_m"].to_numpy(), all_points["y_m"].to_numpy(), cell_size_m)
    counted = pd.DataFrame({"col": col, "row": row})
    return counted.groupby(["col", "row"]).size().rename("n_observations").reset_index()
