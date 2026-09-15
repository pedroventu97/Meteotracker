"""Installed CLI remains compatible with the desktop application layer."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scientific_fixtures import empty_workspace, write_route


@pytest.mark.parametrize("command", ["doctor", "status", "discover", "history", "check"])
def test_cli_json_from_external_cwd(tmp_path, command):
    root = empty_workspace(tmp_path / "CLI città con spazi")
    write_route(root / "data/raw/batch/a.csv", n=21)
    assert root.resolve().is_relative_to(tmp_path.resolve())
    args = [sys.executable, "-W", "error", "-m", "meteotracker_qc", "--workspace", str(root), "--json", command]
    if command == "check":
        args.append("--new")
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=90)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list if command in {"discover", "history"} else dict)
    if command == "check":
        assert payload["status"] in {"pass", "warning"}
        assert payload["plan"]["application_batches"] == 1
        assert Path(payload["report_path"]).is_file()
    assert not (root / "outputs/ingestion").exists()


def test_cli_invalid_workspace_is_blocked_without_apply(tmp_path):
    result = subprocess.run([sys.executable, "-m", "meteotracker_qc", "apply", "--workspace", str(tmp_path / "absent"), "--json"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 3
    assert json.loads(result.stderr)["status"] == "blocked"
    assert not (tmp_path / "absent").exists()


def test_cli_relative_path_keeps_original_cwd_semantics(tmp_path):
    root = empty_workspace(tmp_path / "workspace")
    source = tmp_path / "external batch/a.csv"
    write_route(source, n=21)
    result = subprocess.run([sys.executable, "-W", "error", "-m", "meteotracker_qc", "--workspace", str(root),
                             "--json", "discover", "--path", "external batch"],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]["absolute_path"] == str(source.resolve())
