import json
import os
import socket
import subprocess
import sys

import pytest

from meteotracker_qc.application import ApplicationService, WorkspaceError, WorkspaceLock, _process_alive
from scientific_fixtures import empty_workspace


def test_liveness_probe_does_not_stop_a_running_process():
    # This process is owned by the test, and waits for stdin to close.
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
    try:
        assert _process_alive(child.pid)
        assert child.poll() is None
    finally:
        child.communicate(timeout=10)
    assert not _process_alive(child.pid)


def test_stale_local_lock_is_replaced_without_affecting_data(tmp_path):
    root = empty_workspace(tmp_path / "stale")
    path = root / "logs/.meteotracker.lock"
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=10)
    path.write_text(json.dumps({"pid": child.pid, "host": socket.gethostname(), "run_id": "stale"}), encoding="utf-8")
    with WorkspaceLock(root, "fresh"):
        assert json.loads(path.read_text())["run_id"] == "fresh"
    assert not path.exists()


def test_foreign_host_lock_cannot_be_removed_as_stale(tmp_path):
    root = empty_workspace(tmp_path / "foreign")
    path = root / "logs/.meteotracker.lock"
    path.write_text(json.dumps({"pid": 0, "host": "another-host"}), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(WorkspaceError):
        WorkspaceLock(root, "new").acquire()
    assert path.read_bytes() == before
