from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from meteotracker_qc.application import ApplicationService


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_COLUMNS = ["source_file", "file_sha256", "core_content_hash", "canonical_campaign_id",
                    "duplicate_group_id", "duplicate_type", "is_canonical", "canonical_source_file",
                    "exclude_from_analysis", "exclude_reason", "keep_raw", "notes"]


def make_real_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "synthetic workspace Unicode"
    for relative in ("data/raw/batch one", "data/raw/batch two/nested", "data/manifests", "outputs", "logs"):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "config", workspace / "config")
    for name in ("permissive", "recommended", "restrictive", "session_qc", "repeated_routes", "spatial_density", "temporal_drift"):
        (workspace / "outputs" / name).mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=MANIFEST_COLUMNS).to_csv(workspace / "data/manifests/campaign_manifest.csv", index=False)
    return workspace


def write_fixture(path: Path, offset: float) -> None:
    times = pd.date_range("2026-01-01T10:00:00Z", periods=12, freq="1s")
    frame = pd.DataFrame({
        "Time": times.astype(str), "Lat": 44.5 + offset + pd.Series(range(12)) * 0.00001,
        "Lon": 11.3 + pd.Series(range(12)) * 0.00001, "Temp[°C]": 10 + pd.Series(range(12)) * 0.1,
        "Hum[%]": 50, "Press[mbar]": 1000, "Speed[km/h]": 20,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def test_real_synthetic_batch_transaction_and_single_global_plan(tmp_path, monkeypatch):
    workspace = make_real_workspace(tmp_path)
    write_fixture(workspace / "data/raw/batch one/a.csv", 0)
    write_fixture(workspace / "data/raw/batch one/b.csv", 0.001)
    write_fixture(workspace / "data/raw/batch two/nested/c.csv", 0.002)
    service = ApplicationService(workspace)
    check = service.check(new_only=True)
    assert check["status"] in {"pass", "warning"}, check.get("qc_error")
    assert len(check["results"]) == 3
    assert {item["batch"] for item in check["results"]} == {"batch one", "batch two"}

    calls: list[tuple[str, ...]] = []
    def spy_global(staging, ids):
        calls.append(tuple(ids))
        for name in ("repeated_routes", "spatial_density", "temporal_drift"):
            (staging / "outputs" / name).mkdir(parents=True, exist_ok=True)
        return {"invocations": 1}
    monkeypatch.setattr(service, "_run_global_analyses", spy_global)
    result = service.apply(check=check)
    assert result["status"] == "completed"
    assert len(calls) == 1
    assert len(calls[0]) == 3
    manifest = pd.read_csv(workspace / "data/manifests/campaign_manifest.csv")
    assert len(manifest) == 3
    assert manifest["canonical_campaign_id"].is_unique
    assert not (workspace / "logs/.meteotracker.lock").exists()
    ledger = service.history(result["run_id"])
    assert ledger["status"] == "completed"
    assert ledger["rollback"] is False
    assert Path(result["report_path"]).exists()
