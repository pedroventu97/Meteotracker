"""Deterministic, fail-closed caches for repeated-routes track and pair work."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import pickle
import sqlite3
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

CACHE_SCHEMA_VERSION = 2
TRACK_ALGORITHM_VERSION = "track-v2-source-provenance"
PAIR_ALGORITHM_VERSION = "pair-v3-emitted-overlap-deterministic"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@lru_cache(maxsize=1)
def _geometry_dependency_versions_cached() -> tuple[tuple[str, str], ...]:
    versions = {}
    for name in ("numpy", "pandas", "shapely", "pyproj", "scipy"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "missing"
    return tuple(sorted(versions.items()))


def geometry_dependency_versions() -> dict[str, str]:
    return dict(_geometry_dependency_versions_cached())


def track_metadata(
    *, campaign_id: str, source_file: str, raw_path: Path, standardized_path: Path,
    qc_config_path: Path, rr_config: Any,
) -> dict[str, Any]:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "kind": "campaign-track",
        "campaign_id": campaign_id,
        "source_file": source_file,
        "raw_sha256": sha256_file(raw_path),
        "standardized_sha256": sha256_file(standardized_path),
        "qc_config_sha256": sha256_file(qc_config_path),
        "repeated_routes_config": rr_config.to_dict(),
        "track_algorithm_version": TRACK_ALGORITHM_VERSION,
        "crs_metric_epsg": rr_config.crs_metric_epsg,
        "crs_geographic_epsg": rr_config.crs_geographic_epsg,
        "resampling_distance_m": rr_config.resampling_distance_m,
        "geometry_dependencies": geometry_dependency_versions(),
    }


def pair_metadata(part_a: Any, track_key_a: str, part_b: Any, track_key_b: str, rr_config: Any) -> dict[str, Any]:
    entries = sorted([
        {"track_id": part_a.track_id, "campaign_cache_key": track_key_a,
         "campaign_part_id": part_a.campaign_part_id},
        {"track_id": part_b.track_id, "campaign_cache_key": track_key_b,
         "campaign_part_id": part_b.campaign_part_id},
    ], key=lambda item: item["track_id"])
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "kind": "track-pair",
        "tracks": entries,
        "repeated_routes_config": rr_config.to_dict(),
        "pair_algorithm_version": PAIR_ALGORITHM_VERSION,
        "crs_metric_epsg": rr_config.crs_metric_epsg,
        "geometry_dependencies": geometry_dependency_versions(),
    }


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class RepeatedRoutesCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.track_dir = self.root / "tracks"
        self.pair_db_path = self.root / "pairs.sqlite3"
        self._pair_db: sqlite3.Connection | None = None

    def _pair_connection(self) -> sqlite3.Connection:
        if self._pair_db is not None:
            return self._pair_db
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(self.pair_db_path)
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("CREATE TABLE IF NOT EXISTS pair_cache (cache_key TEXT PRIMARY KEY, envelope TEXT NOT NULL)")
        except sqlite3.DatabaseError:
            connection.close()
            try:
                corrupt_hash = sha256_file(self.pair_db_path)[:16]
            except OSError:
                corrupt_hash = "unreadable"
            corrupt_path = self.root / f"pairs.corrupt.{corrupt_hash}.sqlite3"
            try:
                if not corrupt_path.exists():
                    os.replace(self.pair_db_path, corrupt_path)
            except OSError:
                pass
            connection = sqlite3.connect(self.root / "pairs.recovered.sqlite3")
            connection.execute("CREATE TABLE IF NOT EXISTS pair_cache (cache_key TEXT PRIMARY KEY, envelope TEXT NOT NULL)")
        self._pair_db = connection
        return connection

    def load_track(self, metadata: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        key = stable_hash(metadata)
        path = self.track_dir / f"{key}.pickle"
        try:
            with path.open("rb") as handle:
                envelope = pickle.load(handle)
            if not isinstance(envelope, dict) or envelope.get("metadata") != metadata:
                return key, None
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                return key, None
            return key, payload
        except (FileNotFoundError, OSError, EOFError, pickle.PickleError, AttributeError, ValueError, TypeError):
            return key, None

    def save_track(self, key: str, metadata: dict[str, Any], payload: dict[str, Any]) -> None:
        _atomic_bytes(self.track_dir / f"{key}.pickle", pickle.dumps(
            {"metadata": metadata, "payload": payload}, protocol=pickle.HIGHEST_PROTOCOL,
        ))

    def load_pair(self, metadata: dict[str, Any], requested_ids: tuple[str, str]) -> tuple[str, list[dict] | None]:
        key = stable_hash(metadata)
        try:
            row = self._pair_connection().execute(
                "SELECT envelope FROM pair_cache WHERE cache_key = ?", (key,),
            ).fetchone()
            if row is None:
                return key, None
            envelope = json.loads(row[0])
            if envelope.get("metadata") != metadata or tuple(envelope.get("requested_track_ids", [])) != requested_ids:
                return key, None
            matches = envelope.get("matches")
            if not isinstance(matches, list) or not all(isinstance(row, dict) for row in matches):
                return key, None
            return key, matches
        except (OSError, UnicodeError, json.JSONDecodeError, sqlite3.DatabaseError, AttributeError, TypeError):
            return key, None

    def save_pair(
        self, key: str, metadata: dict[str, Any], requested_ids: tuple[str, str], matches: list[dict],
    ) -> None:
        envelope = json.dumps(
            {"metadata": metadata, "requested_track_ids": list(requested_ids), "matches": matches},
            sort_keys=True, separators=(",", ":"), allow_nan=True,
        )
        self._pair_connection().execute(
            "INSERT OR REPLACE INTO pair_cache(cache_key, envelope) VALUES (?, ?)", (key, envelope),
        )

    def close(self) -> None:
        if self._pair_db is not None:
            self._pair_db.commit()
            self._pair_db.close()
            self._pair_db = None

    def __enter__(self) -> "RepeatedRoutesCache":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def write_run_manifest(self, payload: dict[str, Any]) -> None:
        envelope = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "track_algorithm_version": TRACK_ALGORITHM_VERSION,
            "pair_algorithm_version": PAIR_ALGORITHM_VERSION,
            **payload,
        }
        _atomic_bytes(
            self.root / "manifest.json",
            json.dumps(envelope, indent=2, sort_keys=True, allow_nan=True).encode("utf-8"),
        )
