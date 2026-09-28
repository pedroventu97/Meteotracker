"""Reproducible staging-only equivalence and timing evidence; never promotes."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pickle
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'outputs/audit/incremental_validation_20260909'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')


def run_reference():
    sys.path.insert(0, str(AUDIT / 'frozen_src'))
    from meteotracker_qc.repeated_routes.config import load_config
    from meteotracker_qc.repeated_routes.pipeline import run_pipeline, write_outputs
    from meteotracker_qc.repeated_routes.dataload import list_canonical_campaigns
    from meteotracker_qc.temporal_drift_pipeline import run_temporal_drift
    stage = AUDIT / 'reference44'
    stage.mkdir(exist_ok=False)
    shutil.copytree(AUDIT / 'config', stage / 'config')
    (stage / 'data/manifests').mkdir(parents=True)
    shutil.copy2(AUDIT / 'campaign_manifest.csv', stage / 'data/manifests/campaign_manifest.csv')
    sources = list_canonical_campaigns(ROOT / 'data/raw', ROOT / 'outputs/recommended', AUDIT / 'campaign_manifest.csv')
    hashes = {}
    for source in sources:
        dest = stage / 'outputs/recommended' / source.output_dir.name / source.standardized_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.standardized_path, dest)
        hashes[str(source.standardized_path.relative_to(ROOT))] = digest(dest)
    shutil.copytree(ROOT / 'outputs/session_qc', stage / 'outputs/session_qc')
    save_json(stage / 'input_hashes.json', hashes)
    cfg = load_config(str(stage / 'config/repeated_routes_recommended.yaml'))
    start = time.perf_counter()
    result = run_pipeline(raw_dir=ROOT / 'data/raw', qc_output_dir=stage / 'outputs/recommended',
        qc_config_path=stage / 'config/qc_recommended.yaml', qc_profile='recommended',
        manifest_path=stage / 'data/manifests/campaign_manifest.csv', rr_config=cfg,
        refresh_qc=False, cache_dir=None, full_rebuild=True)
    elapsed = time.perf_counter() - start
    with (stage / 'result.pickle').open('wb') as handle:
        pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)
    write_outputs(result, stage / 'outputs/repeated_routes')
    save_json(stage / 'route_summary.json', {'mode': 'frozen_science_no_cache', 'seconds': elapsed,
        'timings': result.timings, 'campaign_ids': list(result.campaign_tracks_by_id),
        'matches': len(result.matches_df), 'segments': len(result.segments_df)})
    print('REFERENCE_ROUTES_COMPLETE', flush=True)
    start = time.perf_counter()
    run_temporal_drift(root=stage, output_root=stage / 'outputs/temporal_drift',
        campaign_ids=sorted(s.output_dir.name for s in sources), progress=False)
    save_json(stage / 'temporal_summary.json', {'seconds': time.perf_counter()-start})
    save_json(stage / 'artifact_hashes.json', {str(p.relative_to(stage)): digest(p)
        for p in sorted(stage.rglob('*')) if p.is_file() and p.name != 'artifact_hashes.json'})
    print('REFERENCE_COMPLETE', flush=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['reference'])
    args = parser.parse_args()
    run_reference()
