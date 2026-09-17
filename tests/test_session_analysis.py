"""Portable session analysis and offline mapping contracts, synthetic fixtures only."""
import hashlib
import json
from pathlib import Path
import socket

import numpy as np
import pandas as pd
import pytest

from meteotracker_qc.application import ApplicationService
from meteotracker_qc.analysis_settings import DEFAULT_ACTIVE
from meteotracker_qc.cli import main
from meteotracker_qc.map_preview import draw_map, map_crs, render_indices, track_color
from meteotracker_qc.operation import CancellationToken, OperationCancelled
from scientific_fixtures import empty_workspace, write_route, MANIFEST_COLUMNS


def registered_workspace(root):
    empty_workspace(root)
    rows = []
    for i, name in enumerate(("batch città/andata.csv", "batch città/ritorno.csv")):
        raw = root / "data/raw" / name
        write_route(raw, n=101, hour=i, reverse=bool(i))
        row = dict.fromkeys(MANIFEST_COLUMNS, "")
        row.update(source_file=name, canonical_campaign_id=f"campagna_{i}", is_canonical=True,
                   canonical_source_file=name, exclude_from_analysis=False, keep_raw=True,
                   file_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
        rows.append(row)
    redundant = dict(rows[0], source_file="duplicato.csv", is_canonical=False, exclude_from_analysis=True)
    (root / "data/raw/duplicato.csv").write_bytes((root / "data/raw" / rows[0]["source_file"]).read_bytes())
    rows.append(redundant)
    pd.DataFrame(rows).to_csv(root / "data/manifests/campaign_manifest.csv", index=False)
    write_route(root / "data/raw/nuovo/non registrato.csv", n=21)
    return root


@pytest.fixture
def service(tmp_path):
    return ApplicationService(registered_workspace(tmp_path / "workspace città con spazi"), read_only=True)


@pytest.fixture(scope="module")
def preview(tmp_path_factory):
    service = ApplicationService(registered_workspace(tmp_path_factory.mktemp("preview") / "workspace città"))
    with service.preview_qc(["campagna_0", "campagna_1", "campagna_0"]) as result:
        yield service, result


def protected(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for base in ("data", "config", "outputs", "logs") for p in (root / base).rglob("*") if p.is_file()
            and not p.is_relative_to(root / "outputs/custom_analyses")}


def test_manifest_is_only_authority_and_filters(service):
    rows = service.list_sessions()
    assert len(rows) == 2 and {r["batch"] for r in rows} == {"batch città"}
    assert len(service.list_sessions(search="andata")) == 1
    assert len(service.list_sessions(batch="batch città", date_from="2026-01-01", date_to="2026-01-01")) == 2
    assert service.list_sessions(date_from="2026-01-02") == []
    assert service.list_sessions(status="PASS") == []
    assert service.inspect_session("campagna_1")["rows"] == 101
    assert not rows[0]["available_outputs"]
    with pytest.raises(ValueError, match="registrat"):
        service.preview_qc(["non registrato"])
    with pytest.raises(ValueError):
        service.preview_tracks([])


def test_manifest_ambiguity_and_path_escape_rejected(service):
    path = service.workspace / "data/manifests/campaign_manifest.csv"
    frame = pd.read_csv(path)
    frame.loc[1, "canonical_campaign_id"] = "campagna_0"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="duplicate"):
        service.list_sessions()
    frame.loc[1, "canonical_campaign_id"] = "campagna_1"
    frame.loc[0, "source_file"] = "../../config/qc_recommended.yaml"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="fuori"):
        service.preview_tracks(["campagna_0"])


def test_preview_and_compare_are_read_only(service):
    before = protected(service.workspace)
    events = []
    with service.preview_qc(["campagna_0", "campagna_0"], emit=events.append) as analysis:
        assert len(analysis.report["sessions"]) == 1
        summary = analysis.report["sessions"][0]
        assert summary["rows"] == 101
        assert set(summary["keep_by_profile"]) == {"permissive", "recommended", "restrictive"}
        assert isinstance(summary["route_matching_eligible"], bool)
        assert len(summary["suitability"]) == 6
        assert summary["flagged"] <= summary["rows"]
        assert all(v <= summary["rows"] for v in summary["flag_families"].values())
        assert (analysis.root / "report.json").exists()
        comparison = service.compare_sessions(analysis=analysis)
        assert len(comparison) == 1 and comparison[0]["temperature_mean"] == 15
        temp = analysis.root
    assert not temp.exists() and protected(service.workspace) == before
    assert events[-1].progress == 1


def test_multiple_sessions_real_profiles_and_figures(preview):
    service, result = preview
    assert len(result.frames) == 2
    assert len(service.compare_sessions(analysis=result)) == 2
    assert result.report["aggregated_observations"] is False
    for summary in result.report["sessions"]:
        directory = result.root / summary["directory"]
        for name in ("map.png", "timeseries.png"):
            assert (directory / name).read_bytes().startswith(b"\x89PNG")
        for p in ("recommended", "permissive", "restrictive"):
            frame = pd.read_parquet(next((directory / p).glob("*.parquet")))
            assert summary["keep_by_profile"][p] == int(frame[f"keep_{p}"].sum())


def test_custom_runtime_preset_and_schema_rejection(service):
    before = protected(service.workspace)
    active = [g for g in DEFAULT_ACTIVE if g not in {"warmup", "suitability"}]
    path = service.save_analysis_preset("città", description="prova", active_controls=active)
    preset = service.load_analysis_preset(path)
    assert preset["name"] == "città" and preset["description"] == "prova"
    with service.preview_qc(["campagna_0"], active_controls=active) as custom:
        summary = custom.report["sessions"][0]
        assert summary["warmup_rows"] == 0 and summary["suitability"] == {}
        assert summary["disabled_controls"] == ["warmup", "suitability"]
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["schema_version"] += 1
    Path(path).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="incompatibile"):
        service.load_analysis_preset(path)
    assert protected(service.workspace) == before


def test_export_custom_separated_all_formats(preview):
    service, result = preview
    before = protected(service.workspace)
    destination = Path(service.export_custom_analysis(result))
    assert destination.is_relative_to(service.workspace / "outputs/custom_analyses")
    assert (destination / "settings.json").exists() and (destination / "provenance.json").exists()
    assert {p.suffix for p in destination.rglob("*") if p.is_file()} >= {".csv", ".parquet", ".json", ".md", ".png", ".gpkg", ".geojson", ".yaml"}
    import geopandas as gpd
    for path in destination.rglob("selection.gpkg"):
        geo = gpd.read_file(path)
        assert len(geo) == 101 and geo.source_row.is_unique
    assert protected(service.workspace) == before
    assert Path(service.export_custom_analysis(result, formats=["json"])) != destination
    for summary in result.report["sessions"]:
        for profile, count in summary["keep_by_profile"].items():
            exported = pd.read_csv(destination / summary["directory"] / f"kept_{profile}.csv")
            assert len(exported) == count
    with pytest.raises(ValueError, match="formato"):
        service.export_custom_analysis(result, formats=[])


def test_pre_cancel_and_mid_analysis_cleanup(service, monkeypatch):
    import meteotracker_qc.session_analysis as module
    made = []
    original = module.tempfile.mkdtemp
    def capture(**kwargs):
        path = original(**kwargs)
        made.append(Path(path))
        return path
    monkeypatch.setattr(module.tempfile, "mkdtemp", capture)
    token = CancellationToken()
    token.request()
    with pytest.raises(OperationCancelled):
        service.preview_qc(["campagna_0"], cancellation=token)
    assert made == []
    token = CancellationToken()
    with pytest.raises(OperationCancelled):
        service.preview_qc(["campagna_0"], cancellation=token, emit=lambda e: token.request())
    assert made and not made[-1].exists()


def test_tracks_before_qc_offline_identity_and_crs(service, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No QC or network needed for the original preview")
    monkeypatch.setattr(service, "preview_qc", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    before = protected(service.workspace)
    preview = service.preview_tracks(["campagna_0", "campagna_1", "campagna_0"])
    assert len(preview["tracks"]) == 2 and preview["boundary"] == []
    assert preview["metric_crs"] == "EPSG:32632"
    a, b = preview["tracks"]
    assert a["rows"] == b["rows"] == 101
    assert a["color"] == track_color("campagna_0") != b["color"]
    assert a["points"].source_row.is_unique
    assert a["distance_km"] == pytest.approx(.5, rel=.001)
    assert a["points"].y_m.iloc[0] < a["points"].y_m.iloc[-1]
    assert b["points"].y_m.iloc[0] > b["points"].y_m.iloc[-1]
    assert protected(service.workspace) == before


def test_suspicious_breaks_and_render_only_decimation(service):
    raw = service.workspace / "data/raw/batch città/andata.csv"
    data = pd.read_csv(raw)
    data.loc[10, "Lat"] = 46
    data.loc[30, "Lon"] = np.nan
    data.to_csv(raw, index=False)
    preview = service.preview_tracks(["campagna_0"])
    track = preview["tracks"][0]
    assert track["preliminary_jumps"] >= 1 and track["missing_coordinates"] == 1
    points = track["points"]
    before = points.copy(deep=True)
    indices = render_indices(points, limit=10)
    assert len(indices) < len(points) and indices[0] == 0 and indices[-1] == 100
    pd.testing.assert_frame_equal(points, before)
    from matplotlib.figure import Figure
    figure = Figure()
    ax = figure.subplots()
    assert len(draw_map(ax, preview)) == 1
    assert not draw_map(ax, preview, visible=[])


def test_map_export_before_qc(service):
    preview = service.preview_tracks(["campagna_0", "campagna_1"])
    before = protected(service.workspace)
    path = Path(service.export_track_preview(preview, style={"visible": ["campagna_1"], "density": True, "overlaps": True}))
    assert (path / "map.png").exists()
    assert len(list(path.rglob("*.gpkg"))) == 1
    metadata = json.loads((path / "map_configuration.json").read_text())
    assert metadata["metric_crs"] == "EPSG:32632" and metadata["style"]["density"]
    assert protected(service.workspace) == before


def test_cli_equivalent(service, capsys):
    root = str(service.workspace)
    assert main(["sessions", "list", "--workspace", root, "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
    assert main(["sessions", "inspect", "campagna_0", "--workspace", root, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["campaign_id"] == "campagna_0"
    assert main(["sessions", "qc", "campagna_0", "campagna_1", "--profile", "permissive", "--workspace", root, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["sessions"]) == 2 and payload["preview_directory"] is None
    assert main(["sessions", "compare", "campagna_0", "campagna_1", "--workspace", root, "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["comparison"]) == 2


def test_boundary_optional_valid_invalid_and_metric_crs(service):
    import geopandas as gpd
    import yaml
    from shapely.geometry import box
    root = service.workspace
    boundary = root / "data/external/boundaries/confine_comune_bologna.gpkg"
    boundary.parent.mkdir(parents=True)
    gpd.GeoDataFrame({"name": ["synthetic"]}, geometry=[box(11.3, 44.4, 11.4, 44.6)], crs="EPSG:4326").to_file(boundary)
    preview = service.preview_tracks(["campagna_0"])
    assert len(preview["boundary"]) == 1 and preview["boundary"][0][:, 0].min() > 100000
    config_path = root / "config/repeated_routes_recommended.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["crs_metric_epsg"] = 3857
    config_path.write_text(yaml.safe_dump(config))
    projected = service.preview_tracks(["campagna_0"])
    assert projected["metric_crs"] == "EPSG:3857"
    assert not np.allclose(preview["tracks"][0]["points"].x_m, projected["tracks"][0]["points"].x_m)
    config["crs_metric_epsg"] = 4326
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="metrico"):
        service.preview_tracks(["campagna_0"])
    config["crs_metric_epsg"] = 32632
    config_path.write_text(yaml.safe_dump(config))
    preference = root / "user_presets/map.json"
    preference.parent.mkdir()
    preference.write_text('{"boundary_path": "../outside.gpkg"}')
    invalid = service.preview_tracks(["campagna_0"])
    assert not invalid["boundary"] and "non disponibile" in invalid["boundary_note"]
    preference.write_text("broken JSON")
    assert not service.preview_tracks(["campagna_0"])["boundary"]


def test_decimation_retains_exact_valid_endpoints(service):
    track = service.preview_tracks(["campagna_0"])["tracks"][0]
    points = track["points"]
    points.loc[[0, 1, 99, 100], ["x_m", "y_m"]] = np.nan
    indices = render_indices(points, limit=5)
    assert {2, 98} <= set(indices)
    assert len(points) == 101


def test_export_failure_cleans_partial_custom_directory(preview, monkeypatch):
    import meteotracker_qc.map_preview as maps
    service, analysis = preview
    custom = service.workspace / "outputs/custom_analyses"
    before = set(custom.iterdir()) if custom.exists() else set()
    protected_before = protected(service.workspace)
    def broken(*args, **kwargs):
        raise OSError("synthetic export failure")
    monkeypatch.setattr(maps, "export_geodata", broken)
    with pytest.raises(OSError, match="synthetic"):
        service.export_custom_analysis(analysis)
    assert set(custom.iterdir()) == before
    assert protected(service.workspace) == protected_before


def test_changed_input_invalidates_preview(service, monkeypatch):
    import meteotracker_qc.session_analysis as module
    original = module.session_statistics
    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        raw = service.workspace / "data/raw/batch città/andata.csv"
        raw.write_bytes(raw.read_bytes() + b"\n")
        return value
    monkeypatch.setattr(module, "session_statistics", changed)
    with pytest.raises(ValueError, match="Input cambiati"):
        service.preview_qc(["campagna_0"])


def test_preset_malformed_or_old_config_rejected(service):
    path = Path(service.save_analysis_preset("test"))
    payload = json.loads(path.read_text())
    for invalid in ([], {}, {**payload, "schema_version": True}, {**payload, "config_fingerprint": "old"},
                    {**payload, "overrides": [1]}, {**payload, "active_controls": [{}]}):
        path.write_text(json.dumps(invalid))
        with pytest.raises(ValueError):
            service.load_analysis_preset(path)
