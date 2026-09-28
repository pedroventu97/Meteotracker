"""Read-only performance audit harness for the repeated-routes pipeline.

The harness deliberately skips QC refresh and output writers. It reads the
existing standardized parquet corpus, records phase/call counters, and writes
only profiler artefacts to the explicitly supplied directory.
"""
from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import sys
import threading
import time
import tracemalloc
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meteotracker_qc.repeated_routes import candidates, matching, segments, tracks  # noqa: E402
from meteotracker_qc.repeated_routes.config import load_config  # noqa: E402
from meteotracker_qc.repeated_routes.pipeline import run_pipeline  # noqa: E402


def _working_set_bytes() -> int:
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]
    counters = PMC()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    return int(counters.WorkingSetSize) if ok else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--light", action="store_true", help="Disable cProfile/tracemalloc overhead")
    args = parser.parse_args()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)

    counts: Counter[str] = Counter()
    maxima: Counter[str] = Counter()

    original_project = matching.project_onto_line
    def counted_project(line, xs, ys):
        counts["project_onto_line_calls"] += 1
        counts["points_projected"] += len(xs)
        return original_project(line, xs, ys)
    matching.project_onto_line = counted_project
    segments.project_onto_line = counted_project

    original_match = matching.match_tracks
    def counted_match(track_id_a, resampled_a, track_id_b, resampled_b, cfg):
        counts["match_tracks_calls"] += 1
        counts["match_input_points"] += len(resampled_a) + len(resampled_b)
        maxima["max_pair_input_points"] = max(maxima["max_pair_input_points"], len(resampled_a) + len(resampled_b))
        return original_match(track_id_a, resampled_a, track_id_b, resampled_b, cfg)
    matching.match_tracks = counted_match
    import meteotracker_qc.repeated_routes.pipeline as pipeline_mod
    pipeline_mod.match_tracks = counted_match

    original_candidate_line = candidates.LineString
    def counted_candidate_line(*a, **kw):
        counts["candidate_linestrings"] += 1
        return original_candidate_line(*a, **kw)
    candidates.LineString = counted_candidate_line

    original_track_transformer = tracks.Transformer.from_crs
    # Transformer.from_crs is not safely monkey-patchable across pyproj builds;
    # track/part counts below give the exact construction/transform upper bounds.
    del original_track_transformer

    stop = threading.Event()
    rss_samples: list[int] = []
    def sample_memory() -> None:
        while not stop.wait(0.1):
            rss_samples.append(_working_set_bytes())
    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()

    cfg = load_config(str(ROOT / "config" / "repeated_routes_recommended.yaml"))
    profiler = cProfile.Profile()
    if not args.light:
        tracemalloc.start()
    cpu0 = time.process_time()
    wall0 = time.perf_counter()
    if not args.light:
        profiler.enable()
    result = run_pipeline(
        raw_dir=ROOT / "data" / "raw",
        qc_output_dir=ROOT / "outputs" / "recommended",
        qc_config_path=ROOT / "config" / "qc_recommended.yaml",
        qc_profile="recommended",
        manifest_path=ROOT / "data" / "manifests" / "campaign_manifest.csv",
        rr_config=cfg,
        refresh_qc=False,
    )
    if not args.light:
        profiler.disable()
    wall_s = time.perf_counter() - wall0
    cpu_s = time.process_time() - cpu0
    if not args.light:
        current_py, peak_py = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    else:
        current_py = peak_py = 0
    stop.set()
    sampler.join(timeout=1)

    parts = list(result.parts_by_track.values())
    resampled_lengths = {p.track_id: len(p.resampled) for p in parts}
    candidate_point_work = 0
    for row in result.candidate_pairs_df.itertuples(index=False):
        candidate_point_work += resampled_lengths[row.track_id_a] + resampled_lengths[row.track_id_b]

    profile_path = args.artifact_dir / "repeated_routes.prof"
    if not args.light:
        profiler.dump_stats(profile_path)
        with (args.artifact_dir / "repeated_routes_top.txt").open("w", encoding="utf-8") as handle:
            stats = pstats.Stats(profiler, stream=handle).strip_dirs().sort_stats("cumulative")
            stats.print_stats(60)
            handle.write("\n--- callers of project_onto_line ---\n")
            stats.print_callers("project_onto_line")

    payload = {
        "wall_s": wall_s,
        "process_cpu_s": cpu_s,
        "cpu_to_wall_ratio": cpu_s / wall_s if wall_s else None,
        "logical_cpu_count": os.cpu_count(),
        "estimated_total_machine_cpu_percent": (cpu_s / wall_s / os.cpu_count() * 100.0) if wall_s and os.cpu_count() else None,
        "pipeline_timings": result.timings,
        "campaigns": len(result.campaign_tracks_by_id),
        "usable_campaigns": len({p.campaign_id for p in result.usable_parts}),
        "parts_all": len(parts),
        "parts_usable": len(result.usable_parts),
        "original_geometry_points": sum(len(p.points) for p in parts),
        "resampled_geometry_points": sum(len(p.resampled) for p in parts),
        "candidate_stats": result.candidate_stats,
        "candidate_rows": len(result.candidate_pairs_df),
        "candidate_point_work": candidate_point_work,
        "pairwise_matches": len(result.matches_df),
        "segments": len(result.segments_df),
        "passages": len(result.passages_df),
        "comparison_opportunities": len(result.comparison_df),
        "instrumentation_counts": dict(counts),
        "instrumentation_maxima": dict(maxima),
        "python_alloc_current_bytes": current_py,
        "python_alloc_peak_bytes": peak_py,
        "working_set_peak_bytes": max(rss_samples, default=_working_set_bytes()),
        "standardized_parquet_reads": len(result.standardized_by_campaign),
        "forward_campaign_reprojections": len(result.campaign_tracks_by_id),
        "inverse_part_reprojections": len(parts),
    }
    (args.artifact_dir / "repeated_routes_metrics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
