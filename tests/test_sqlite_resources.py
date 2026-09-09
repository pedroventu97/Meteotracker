from __future__ import annotations

import sqlite3

import geopandas as gpd
import pandas as pd

from meteotracker_qc.repeated_routes.geopackage import write_geopackage


def test_geopackage_writer_closes_sqlite_connection(tmp_path, monkeypatch):
    real_connect = sqlite3.connect
    connections = []

    def tracked_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr("meteotracker_qc.repeated_routes.geopackage.sqlite3.connect", tracked_connect)
    memberships = pd.DataFrame([{
        "membership_id": "m1", "repeated_segment_id": "s1", "segment_passage_id": "p1",
        "source_file": "a.csv", "source_row": 0, "geometry": None,
    }])
    support = pd.DataFrame([{"membership_id": "m1", "supporting_match_id": "match1"}])
    empty = gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
    write_geopackage(tmp_path / "routes.gpkg", empty, empty, empty,
                     pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), memberships_df=memberships,
                     match_support_df=support)
    assert len(connections) == 1
    try:
        connections[0].execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return
    raise AssertionError("GeoPackage SQLite connection remained open")
