import ast
import importlib
import importlib.util
import os
from pathlib import Path

import pytest

import meteotracker_qc
from meteotracker_qc.config_resources import resource, read_policy
from meteotracker_qc.repeated_routes.config import load_config
from meteotracker_qc.temporal_drift.config import load_matching_policy


def test_bundled_configs_match_authoritative_scientific_files():
    config = Path(__file__).resolve().parent.parent / "config"
    for path in sorted(config.iterdir()):
        if path.suffix in {".yaml", ".csv"}:
            assert resource(path.name).read_bytes() == path.read_bytes(), path.name


def test_default_resources_work_from_an_unrelated_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_config("recommended").minimum_shared_length_m > 0
    assert len(load_matching_policy()) > 0
    for name in ["flag_policy.csv", "session_qc_policy.csv", "session_suitability_policy.csv", "temporal_drift_policy.csv"]:
        assert not read_policy(name).empty


def test_explicit_missing_workspace_policy_does_not_fall_back(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_matching_policy(tmp_path)


def test_runtime_import_closure_is_in_the_installed_package():
    package = Path(meteotracker_qc.__file__).resolve().parent
    expected = os.environ.get("METEOTRACKER_EXPECT_PACKAGE_ROOT")
    if expected:
        assert package == Path(expected).resolve()
    paths = {"meteotracker_qc." + ".".join(p.relative_to(package).with_suffix("").parts): p
             for p in package.rglob("*.py") if "gui" not in p.parts}
    paths = {name.removesuffix(".__init__"): path for name, path in paths.items()}
    for name, path in paths.items():
        if not name.endswith(".__main__"):
            imported = importlib.import_module(name)
            assert Path(imported.__file__).resolve().is_relative_to(package)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            targets = []
            if isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names if alias.name.startswith("meteotracker_qc"))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = name if path.name == "__init__.py" else name.rpartition(".")[0]
                    targets.append(importlib.util.resolve_name("." * node.level + (node.module or ""), parent))
                elif node.module and node.module.startswith("meteotracker_qc"):
                    targets.append(node.module)
            for target in targets:
                assert target in paths, (name, target)


@pytest.mark.parametrize("name", ["../flag_policy.csv", "config/flag_policy.csv", "..\\flag_policy.csv"])
def test_resource_names_cannot_escape_the_bundle(name):
    with pytest.raises(ValueError):
        resource(name)
