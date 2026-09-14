"""Versioned configuration bundled in the distribution, independent of cwd.

An explicitly supplied workspace is authoritative: a missing file there is
an error, never a silent fallback to a different set of scientific policies.
"""
from importlib.resources import files
from pathlib import Path

import pandas as pd
import yaml


def resource(name: str):
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("Configuration resource must be a plain filename")
    target = files("meteotracker_qc").joinpath("resources", name)
    if not target.is_file():
        raise FileNotFoundError(f"Packaged configuration is missing: {name}")
    return target


def read_policy(name: str, workspace: Path | None = None) -> pd.DataFrame:
    target = Path(workspace) / "config" / name if workspace is not None else resource(name)
    with target.open("r", encoding="utf-8") as handle:
        return pd.read_csv(handle)


def read_preset(name: str) -> dict:
    with resource(name).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
