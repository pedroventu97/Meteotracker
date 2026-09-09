"""Sensitivity analysis (section 14): a reasoned one-factor-at-a-time sweep.

A full cartesian product of the three suggested parameters (3x3x3=27 configs)
is computationally feasible on this dataset size, but a one-factor-at-a-time
(OFAT) design around the recommended baseline is more directly interpretable
(each row isolates the effect of exactly one threshold) and is what section 14
explicitly allows ("non e' necessario eseguire tutte le combinazioni... un set
ragionato"). Track building is config-independent (only resampling_distance_m
would affect it, which is not swept here) and is done once by the caller;
this module only re-runs the candidate/matching/consolidation stages.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from . import candidates as candidates_mod
from .config import RepeatedRoutesConfig
from .matching import match_tracks
from .segments import consolidate_segments
from .tracks import PartTrack

TOLERANCE_VALUES = [10.0, 20.0, 30.0]
MIN_LENGTH_VALUES = [100.0, 250.0, 500.0]
MIN_OVERLAP_VALUES = [0.60, 0.70, 0.80]


def build_sensitivity_configs(baseline: RepeatedRoutesConfig) -> dict[str, RepeatedRoutesConfig]:
    configs = {"recommended_baseline": baseline}
    for tol in TOLERANCE_VALUES:
        if tol == baseline.matching_tolerance_m:
            continue
        configs[f"tolerance_{int(tol)}m"] = dataclasses.replace(baseline, name=f"tolerance_{int(tol)}m", matching_tolerance_m=tol)
    for length in MIN_LENGTH_VALUES:
        if length == baseline.minimum_shared_length_m:
            continue
        configs[f"minlength_{int(length)}m"] = dataclasses.replace(baseline, name=f"minlength_{int(length)}m", minimum_shared_length_m=length)
    for overlap in MIN_OVERLAP_VALUES:
        if overlap == baseline.minimum_overlap_fraction:
            continue
        configs[f"minoverlap_{overlap:.2f}"] = dataclasses.replace(baseline, name=f"minoverlap_{overlap:.2f}", minimum_overlap_fraction=overlap)
    return configs


def run_one_configuration(
    parts_by_track: dict[str, PartTrack], usable_parts: list[PartTrack],
    standardized_by_campaign: dict, cfg: RepeatedRoutesConfig,
) -> dict:
    candidate_pairs_df, candidate_stats = candidates_mod.build_candidate_pairs(usable_parts, cfg)

    pairwise_matches: list[dict] = []
    for _, row in candidate_pairs_df.iterrows():
        part_a = parts_by_track[row["track_id_a"]]
        part_b = parts_by_track[row["track_id_b"]]
        pairwise_matches.extend(match_tracks(part_a.track_id, part_a.resampled, part_b.track_id, part_b.resampled, cfg))

    segments_df, passages_df, _matches_df = consolidate_segments(parts_by_track, pairwise_matches, standardized_by_campaign, cfg)

    n_multi_date = 0
    n_three_plus_date = 0
    if not segments_df.empty and not passages_df.empty:
        dates_per_segment = passages_df.groupby("repeated_segment_id")["date"].nunique()
        n_multi_date = int((dates_per_segment >= 2).sum())
        n_three_plus_date = int((dates_per_segment >= 3).sum())

    return {
        "matching_tolerance_m": cfg.matching_tolerance_m,
        "minimum_shared_length_m": cfg.minimum_shared_length_m,
        "minimum_overlap_fraction": cfg.minimum_overlap_fraction,
        "n_candidate_pairs": candidate_stats["n_candidate_pairs"],
        "n_pairwise_matches": len(pairwise_matches),
        "n_repeated_segments": int(len(segments_df)),
        "n_segments_multiple_dates": n_multi_date,
        "n_segments_three_or_more_dates": n_three_plus_date,
        "total_repeated_length_km": float(segments_df["segment_length_m"].sum() / 1000.0) if not segments_df.empty else 0.0,
        "median_segment_length_m": float(segments_df["segment_length_m"].median()) if not segments_df.empty else np.nan,
        "median_matching_distance_m": float(segments_df["mean_matching_distance_m"].median()) if not segments_df.empty else np.nan,
    }


def run_sensitivity_analysis(
    parts_by_track: dict[str, PartTrack], usable_parts: list[PartTrack],
    standardized_by_campaign: dict, baseline: RepeatedRoutesConfig,
) -> pd.DataFrame:
    configs = build_sensitivity_configs(baseline)
    rows = []
    for configuration_id, cfg in configs.items():
        stats = run_one_configuration(parts_by_track, usable_parts, standardized_by_campaign, cfg)
        rows.append({"configuration_id": configuration_id, **stats})
    return pd.DataFrame(rows)
