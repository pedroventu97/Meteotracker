import json
import hashlib
import shutil
from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.application import ApplicationService
from meteotracker_qc.repeated_routes.memberships import MEMBERSHIP_KEY, SUPPORT_COLUMNS


def test_real_batch_pipeline_promotes_all_layers_once(scientific_run):
    root = scientific_run["workspace"]
    assert scientific_run["calls"] == dict.fromkeys([
        "session_qc", "repeated_routes", "many_to_many_consolidation", "spatial_density", "temporal_drift",
    ], 1)
    assert scientific_run["result"]["status"] == "completed"
    check = scientific_run["check"]
    assert len(check["results"]) == 9
    assert sum(item["validation"]["classification"] == "canonical" for item in check["results"]) == 8
    assert sum(item["validation"]["classification"] == "redundant" for item in check["results"]) == 1
    service = ApplicationService(root)
    assert service.discover(include_registered=False) == []
    record = service.history(scientific_run["result"]["run_id"])
    assert record["status"] == "completed" and record["rollback"] is False
    assert len(record["campaigns"]) == 8
    assert record["phases_completed"][-2:] == ["validation", "promotion"]
    assert not (root / "logs/.meteotracker.lock").exists()
    assert not list((root / "logs").glob("meteotracker_apply_*"))
    report = json.loads((root / "outputs/ingestion/batch_ingestion_report.json").read_text())
    assert report["analyses"]["phases"] == scientific_run["calls"]


def test_promoted_many_to_many_and_density_do_not_double_count(scientific_workspace):
    root = scientific_workspace
    members = pd.read_csv(root / "outputs/repeated_routes/point_segment_memberships.csv")
    support = pd.read_csv(root / "outputs/repeated_routes/point_segment_match_support.csv")
    assert len(members) > 0
    assert not members.duplicated(MEMBERSHIP_KEY).any()
    assert not support.duplicated(SUPPORT_COLUMNS).any()
    assert set(members.membership_id) == set(support.membership_id)
    summary = json.loads((root / "outputs/repeated_routes/membership_summary.json").read_text())
    assert summary["n_duplicate_semantic_memberships"] == 0
    assert summary["n_original_points_in_multiple_segments"] > 0
    assert members.passage_direction.nunique() > 1
    inventory = pd.read_csv(root / "outputs/session_qc/session_qc_inventory.csv")
    manifest = pd.read_csv(root / "data/manifests/campaign_manifest.csv")
    canonical = manifest.loc[~manifest.exclude_from_analysis.astype(bool)]
    raw_rows = sum(len(pd.read_csv(root / "data/raw" / name)) for name in canonical.source_file)
    assert inventory.n_raw.sum() == raw_rows
    density = pd.read_csv(root / "outputs/spatial_density/meteotracker_coverage_50m.csv")
    assert density.n_observations.sum() == raw_rows
    assert (density.n_valid_observations <= density.n_observations).all()


def test_global_rebuild_reuses_cache_and_preserves_scientific_results(scientific_workspace, tmp_path):
    root = scientific_workspace
    stage = tmp_path / "staged rebuild"
    shutil.copytree(root, stage)
    inventory = pd.read_csv(root / "outputs/session_qc/session_qc_inventory.csv")
    result = ApplicationService(root)._run_global_analyses(stage, inventory.canonical_campaign_id.tolist())
    assert result["cache_stats"]["track_hits"] == len(inventory)
    assert result["cache_stats"]["pair_hits"] > 0
    for relative in [
        "repeated_routes/point_segment_memberships.csv", "repeated_routes/point_segment_match_support.csv",
        "spatial_density/meteotracker_coverage_50m.csv", "temporal_drift/session_temporal_diagnostics.csv",
    ]:
        pd.testing.assert_frame_equal(pd.read_csv(root / "outputs" / relative), pd.read_csv(stage / "outputs" / relative))


def test_real_promotion_failure_rolls_back_all_previous_outputs(scientific_workspace, tmp_path, monkeypatch):
    from scientific_fixtures import write_route
    root = tmp_path / "rollback workspace"
    shutil.copytree(scientific_workspace, root)
    write_route(root / "data/raw/new batch/new.csv", offset=50, hour=20)
    service = ApplicationService(root)
    check = service.check(new_only=True)
    assert check["status"] in {"pass", "warning"}, check.get("qc_error")

    def protected_hashes():
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for base in ("data", "outputs") for p in (root / base).rglob("*") if p.is_file()}

    before = protected_hashes()
    replace = Path.replace
    injected = []

    def fail_once(source, target):
        if (not injected and Path(target) == root / "outputs/recommended"
                and source.parent.parent.name.startswith("meteotracker_apply_")):
            injected.append(True)
            raise OSError("injected promotion failure")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_once)
    with pytest.raises(OSError, match="injected promotion failure"):
        service.apply(check=check)
    assert injected == [True]
    assert before == protected_hashes()
    record = service.history()[-1]
    assert record["status"] == "failed" and record["rollback"] is True
    assert not (root / "logs/.meteotracker.lock").exists()


def test_same_stem_campaigns_are_not_overwritten_in_route_or_density_loading(tmp_path):
    from scientific_fixtures import empty_workspace, write_route
    from meteotracker_qc.ingestion import apply_manifest_and_qc
    from meteotracker_qc.repeated_routes.config import load_config
    from meteotracker_qc.repeated_routes.pipeline import build_campaign_tracks

    root = empty_workspace(tmp_path / "same filenames")
    write_route(root / "data/raw/a/same.csv")
    write_route(root / "data/raw/b/same.csv", hour=1)
    service = ApplicationService(root)
    check = service.check(new_only=True)
    assert check["status"] in {"pass", "warning"}, check.get("qc_error")
    stage = tmp_path / "staging"
    apply_manifest_and_qc(root, "batch", stage, {"results": check["validation_results"]})
    inventory, frames, tracks = build_campaign_tracks(root / "data/raw", stage / "outputs/recommended",
                                                    stage / "data/manifests/campaign_manifest.csv", load_config("recommended"))
    assert len(inventory) == len(frames) == len(tracks) == 2
    assert inventory.campaign_id.is_unique
    assert set(inventory.source_file) == {"a/same.csv", "b/same.csv"}
