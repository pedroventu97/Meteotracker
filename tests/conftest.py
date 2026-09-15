"""Portable default suite; historical case studies require explicit opt-in."""
from collections import Counter
from functools import wraps
import hashlib
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def forbid_official_apply():
    """Every test session must reject writes to the real project workspace."""
    from meteotracker_qc.application import ApplicationService
    original = ApplicationService.apply
    def guarded(service, *args, **kwargs):
        assert service.workspace.resolve() != Path("D:/projects/Meteotracker").resolve(), "OFFICIAL APPLY FORBIDDEN"
        return original(service, *args, **kwargs)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ApplicationService, "apply", guarded)
        yield

REAL_DATA_MODULES = {
    "test_regression_real_data.py", "test_session_regression_real_data.py", "test_temporal_real_data.py",
}


def pytest_addoption(parser):
    parser.addoption("--real-data", action="store_true", help="Also collect historical case studies requiring local raw and official outputs")


def pytest_configure(config):
    config.addinivalue_line("markers", "real_data: historical regression requiring local scientific data")


def pytest_ignore_collect(collection_path, config):
    return collection_path.name in REAL_DATA_MODULES and not config.getoption("--real-data")


def pytest_report_header(config):
    if not config.getoption("--real-data"):
        return "Portable scientific suite: historical real-data studies are outside the checkpoint; output contracts use generated synthetic data."


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--real-data"):
        for item in items:
            if "real_data" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="historical raw fixture: enable --real-data"))


@pytest.fixture(scope="session")
def scientific_run(tmp_path_factory):
    from scientific_fixtures import batch_workspace
    import meteotracker_qc.application as application
    import meteotracker_qc.session_qc_pipeline as session
    import meteotracker_qc.repeated_routes.pipeline as routes
    import meteotracker_qc.spatial_density.pipeline as density
    import meteotracker_qc.temporal_drift_pipeline as temporal

    root = batch_workspace(tmp_path_factory.mktemp("scientific workspace città"))
    service = application.ApplicationService(root)
    def protected_hashes():
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for base in ("data", "outputs", "config") for p in (root / base).rglob("*") if p.is_file()}
    before_check = protected_hashes()
    check = service.check(new_only=True)
    assert check["status"] in {"pass", "warning"}, check.get("qc_error")
    assert protected_hashes() == before_check
    counts = Counter()
    with pytest.MonkeyPatch.context() as patch:
        for module, name, phase in (
            (session, "run_session_qc", "session_qc"), (routes, "run_pipeline", "repeated_routes"),
            (routes, "consolidate_segments", "many_to_many_consolidation"),
            (density, "run_density_analysis", "spatial_density"), (temporal, "run_temporal_drift", "temporal_drift"),
        ):
            original = getattr(module, name)
            def spy(*args, _original=original, _phase=phase, **kwargs):
                counts[_phase] += 1
                return _original(*args, **kwargs)
            patch.setattr(module, name, wraps(original)(spy))
        result = service.apply(check=check)
    return {"workspace": root, "check": check, "result": result, "calls": dict(counts)}


@pytest.fixture(scope="session")
def scientific_workspace(scientific_run):
    return scientific_run["workspace"]
