from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.repeated_routes.tracks import CampaignTracks, PartTrack
from meteotracker_qc.spatial_density.grid import (
    cell_indices,
    detect_visits_for_part,
    raw_observation_counts,
)
from meteotracker_qc.spatial_density.pipeline import build_density_grid, sensitivity_summary


def _points(x: list[float], y: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"x_m": x, "y_m": y})


def _part(campaign_id: str, part_id: int, x: list[float], y: list[float]) -> PartTrack:
    return PartTrack(campaign_id=campaign_id, campaign_part_id=part_id, points=_points(x, y), resampled=pd.DataFrame())


# --- cell_indices ------------------------------------------------------------------

def test_cell_indices_basic_and_negative():
    x = np.array([0.0, 9.99, 10.0, 25.0, -0.01, -10.0])
    y = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    col, row = cell_indices(x, y, 10.0)
    assert list(col) == [0, 0, 1, 2, -1, -1]
    assert list(row) == [0, 0, 0, 0, 0, 0]


# --- detect_visits_for_part ---------------------------------------------------------

def test_detect_visits_single_cell_no_split():
    points = _points([1, 2, 3], [1, 1, 1])
    out = detect_visits_for_part(points, 10.0)
    assert list(out["visit_run_id"]) == [0, 0, 0]
    assert (out["col"] == 0).all() and (out["row"] == 0).all()


def test_detect_visits_leave_and_return_creates_new_run():
    # cell(0,0) x3, cell(1,0) x2, cell(0,0) x2 again -> 3 runs, not 2
    x = [1, 2, 3, 15, 16, 1, 2]
    y = [1, 1, 1, 1, 1, 1, 1]
    out = detect_visits_for_part(_points(x, y), 10.0)
    assert list(out["visit_run_id"]) == [0, 0, 0, 1, 1, 2, 2]
    cells_by_run = out.groupby("visit_run_id")[["col", "row"]].first()
    assert tuple(cells_by_run.loc[0]) == (0, 0)
    assert tuple(cells_by_run.loc[1]) == (1, 0)
    assert tuple(cells_by_run.loc[2]) == (0, 0)


def test_detect_visits_empty():
    out = detect_visits_for_part(_points([], []), 10.0)
    assert out.empty


# --- raw_observation_counts ----------------------------------------------------------

def test_raw_observation_counts_sums_across_campaigns():
    xy = {
        "campA": _points([1, 2, 15], [1, 1, 1]),  # 2 in cell(0,0), 1 in cell(1,0)
        "campB": _points([3], [1]),  # 1 more in cell(0,0)
        "campC": _points([], []),  # empty campaign must not error
    }
    counts = raw_observation_counts(xy, 10.0)
    counts = counts.set_index(["col", "row"])["n_observations"]
    assert counts.loc[(0, 0)] == 3
    assert counts.loc[(1, 0)] == 1


# --- build_density_grid: n_observations / n_valid / n_campaigns / n_visits / revisits --

def test_build_density_grid_counts_and_revisits():
    # campA: visits cell(0,0) [3 pts] -> cell(1,0) [2 pts] -> cell(0,0) again [2 pts]
    part_a = _part("campA", 1, [1, 2, 3, 15, 16, 1, 2], [1, 1, 1, 1, 1, 1, 1])
    # campB: single visit to cell(0,0) only
    part_b = _part("campB", 1, [3, 4], [1, 1])
    campaign_tracks_by_id = {
        "campA": CampaignTracks(campaign_id="campA", parts=[part_a], n_valid_points_before_part_filter=7),
        "campB": CampaignTracks(campaign_id="campB", parts=[part_b], n_valid_points_before_part_filter=2),
    }
    # Raw (pre-QC) points: campA has 2 extra excluded pings in cell(0,0) beyond its 5 valid ones;
    # campB's raw exactly matches its valid points; cell(1,0) has no excluded points.
    xy_by_campaign = {
        "campA": _points([1, 2, 3, 15, 16, 1, 2, 1, 2], [1, 1, 1, 1, 1, 1, 1, 1, 1]),
        "campB": _points([3, 4], [1, 1]),
    }

    gdf = build_density_grid(campaign_tracks_by_id, xy_by_campaign, cell_size_m=10.0, crs_metric_epsg=32632)
    cells = gdf.set_index(["col", "row"])

    c00 = cells.loc[(0, 0)]
    assert c00["n_observations"] == 9  # 7 campA raw + 2 campB raw
    assert c00["n_valid_observations"] == 7  # 5 campA valid + 2 campB valid
    assert c00["n_campaigns"] == 2
    assert c00["n_visits"] == 3  # campA run0 + campA run2 + campB's single visit
    assert c00["n_same_campaign_revisits"] == 1  # campA revisits once beyond its first
    assert c00["n_excluded_observations"] == 2
    assert c00["pct_excluded"] == pytest.approx(2 / 9 * 100)

    c10 = cells.loc[(1, 0)]
    assert c10["n_observations"] == 2
    assert c10["n_valid_observations"] == 2
    assert c10["n_campaigns"] == 1
    assert c10["n_visits"] == 1
    assert c10["n_same_campaign_revisits"] == 0
    assert c10["pct_excluded"] == 0.0

    assert gdf.crs is not None
    assert gdf.crs.to_epsg() == 32632


def test_build_density_grid_single_campaign_never_inflates_n_campaigns():
    # A single campaign passing through a cell many times must still count n_campaigns == 1.
    part_a = _part("campA", 1, [1, 15, 1, 15, 1], [1, 1, 1, 1, 1])
    campaign_tracks_by_id = {
        "campA": CampaignTracks(campaign_id="campA", parts=[part_a], n_valid_points_before_part_filter=5),
    }
    xy_by_campaign = {"campA": _points([1, 15, 1, 15, 1], [1, 1, 1, 1, 1])}
    gdf = build_density_grid(campaign_tracks_by_id, xy_by_campaign, cell_size_m=10.0, crs_metric_epsg=32632)
    assert (gdf["n_campaigns"] == 1).all()
    c00 = gdf.set_index(["col", "row"]).loc[(0, 0)]
    assert c00["n_visits"] == 3  # visits at positions 0, 2, 4
    assert c00["n_same_campaign_revisits"] == 2


# --- sensitivity_summary --------------------------------------------------------------

def test_sensitivity_summary_smaller_cells_show_less_apparent_repetition():
    # Two campaigns overlapping over a 30 m stretch: at 10 m resolution they share 3 cells,
    # at 50 m resolution they collapse into 1 shared cell -- coarser cells cannot show *less*
    # apparent cross-campaign repetition than finer ones for the same physical overlap.
    xs = [0, 10, 20]
    part_a = _part("campA", 1, xs, [1, 1, 1])
    part_b = _part("campB", 1, xs, [1, 1, 1])
    campaign_tracks_by_id = {
        "campA": CampaignTracks(campaign_id="campA", parts=[part_a], n_valid_points_before_part_filter=3),
        "campB": CampaignTracks(campaign_id="campB", parts=[part_b], n_valid_points_before_part_filter=3),
    }
    xy_by_campaign = {"campA": _points(xs, [1, 1, 1]), "campB": _points(xs, [1, 1, 1])}

    summary = sensitivity_summary(campaign_tracks_by_id, xy_by_campaign, [10.0, 50.0], crs_metric_epsg=32632)
    by_size = summary.set_index("cell_size_m")
    assert by_size.loc[10.0, "n_cells_traversed"] >= by_size.loc[50.0, "n_cells_traversed"]
    assert by_size.loc[50.0, "max_n_campaigns"] == 2
    assert by_size.loc[10.0, "max_n_campaigns"] == 2
