"""Installed CLI remains compatible with the desktop application layer."""
import json
import os
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


@pytest.mark.parametrize("command", ["doctor", "status", "discover"])
def test_cli_json_is_utf8_without_utf8_environment(tmp_path, command):
    """Regression: --json output must be UTF-8 even without PYTHONUTF8/PYTHONIOENCODING."""
    root = empty_workspace(tmp_path / "CLI citt\u00e0 \u03c4 \u0141\u00f3d\u017a")
    write_route(root / "data/raw/batch/a.csv", n=21)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONUTF8", "PYTHONIOENCODING"}}
    result = subprocess.run([sys.executable, "-X", "utf8=0", "-W", "error", "-m", "meteotracker_qc",
                             "--workspace", str(root), "--json", command],
                            cwd=tmp_path, capture_output=True, env=env, timeout=90)
    assert result.returncode == 0, result.stderr.decode("utf-8", "backslashreplace")
    text = result.stdout.decode("utf-8")
    payload = json.loads(text)
    assert "\u03c4" in text and "citt\u00e0" in text
    assert isinstance(payload, list if command == "discover" else dict)
