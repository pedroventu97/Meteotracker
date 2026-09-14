import numpy as np

from meteotracker_qc.temporal_drift.projection import build_local_transformer, planar_distance_m, project_xy


def test_projection_preserves_known_short_distance():
    # Two points ~11m apart in latitude near Bologna (1 arcsecond of lat ~= 30.9m,
    # so 0.00010 deg ~= 11.1m).
    lats = np.array([44.4949, 44.4949 + 0.0001])
    lons = np.array([11.3426, 11.3426])
    transformer = build_local_transformer(lats, lons)
    x, y = project_xy(transformer, lats, lons)
    dist = planar_distance_m(x[0], y[0], x[1], y[1])
    assert 10.5 < dist < 11.7


def test_projection_centroid_is_near_origin():
    lats = np.array([44.49, 44.50, 44.495])
    lons = np.array([11.34, 11.35, 11.345])
    transformer = build_local_transformer(lats, lons)
    x, y = project_xy(transformer, lats, lons)
    assert abs(np.mean(x)) < 50
    assert abs(np.mean(y)) < 50


def test_distance_is_symmetric_and_zero_for_identical_points():
    lats = np.array([44.49, 44.49])
    lons = np.array([11.34, 11.34])
    transformer = build_local_transformer(lats, lons)
    x, y = project_xy(transformer, lats, lons)
    assert planar_distance_m(x[0], y[0], x[1], y[1]) == 0.0


def test_bologna_ravenna_distance_scale_stays_planar_consistent():
    # Bologna and Ravenna are ~70km apart -- confirms the per-campaign AEQD
    # projection stays well-behaved (no blow-up) at this scale, unlike a
    # fixed UTM zone near its boundary.
    lats = np.array([44.4949, 44.4184])
    lons = np.array([11.3426, 12.2035])
    transformer = build_local_transformer(lats, lons)
    x, y = project_xy(transformer, lats, lons)
    dist_km = planar_distance_m(x[0], y[0], x[1], y[1]) / 1000.0
    assert 60 < dist_km < 80
