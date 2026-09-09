"""Execution provenance capture (section 18): what ran, on what, with which config."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas
import numpy
import pandas
import pyproj
import shapely
import yaml

from .config import RepeatedRoutesConfig


def _git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, timeout=10, check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_provenance(
    *, repo_root: Path, input_files: list[Path], qc_profile: str,
    rr_config: RepeatedRoutesConfig, qc_config_path: Path,
) -> dict:
    return {
        "repeated_routes_schema_version": 3,
        "membership_model": "unique original-point/passage/segment memberships with separate match support",
        "consolidation_model": "complete corridor compatibility with connected pairwise evidence",
        "execution_datetime": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(repo_root),
        "input_files": [str(p.relative_to(repo_root)) if p.is_relative_to(repo_root) else str(p) for p in input_files],
        "input_checksums": {
            (str(p.relative_to(repo_root)) if p.is_relative_to(repo_root) else str(p)): _sha256(p)
            for p in input_files
        },
        "configuration": {
            "qc_profile": qc_profile,
            "qc_config_path": str(qc_config_path),
            "repeated_routes_config": rr_config.to_dict(),
        },
        "software_versions": {
            "python": sys.version,
            "platform": platform.platform(),
            "pandas": pandas.__version__,
            "numpy": numpy.__version__,
            "geopandas": geopandas.__version__,
            "shapely": shapely.__version__,
            "pyproj": pyproj.__version__,
        },
        "crs": {
            "metric_epsg": rr_config.crs_metric_epsg,
            "geographic_epsg": rr_config.crs_geographic_epsg,
        },
        "qc_profile": qc_profile,
    }


def write_provenance(path: Path, provenance: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")
