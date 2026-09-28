"""Orchestrator for the session-QC aggregation layer (points -> segments ->
session -> suitability), sibling to pipeline.py. Reads the 3 already-real
per-profile output trees; never re-derives point-level QC flags, never
touches data/raw/.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .analysis_settings import settings_fingerprint
from .session_qc.diagnostics import write_all_diagnostics
from .session_qc.metrics import build_reference_frame, compute_segment_metrics, compute_session_metrics, load_campaign_frames
from .session_qc.outputs import build_segment_reason_codes, build_session_reason_codes, write_campaign_json, write_policy_snapshot
from .session_qc.segment_status import SEGMENT_DIMENSIONS, compute_segment_status
from .session_qc.sensitivity import run_session_sensitivity
from .session_qc.session_status import SESSION_DIMENSIONS, compute_drift_assessability, compute_session_status
from .session_qc.suitability import compute_all_suitability

MAIN_PROFILE = "recommended_session"
CONFIG_VERSION = "session_qc_v1"


def _load_all_campaign_metrics(campaign_ids: list[str], profile_roots: dict[str, Path], family_lookup: dict[str, str], profile: str):
    segment_frames = []
    session_rows = []
    refs = {}
    for campaign_id in campaign_ids:
        frames = load_campaign_frames(campaign_id, profile_roots)
        ref = build_reference_frame(frames)
        source_file = str(ref["source_file"].iloc[0])
        seg = compute_segment_metrics(ref, campaign_id, source_file, family_lookup)
        session = compute_session_metrics(ref, seg, campaign_id, source_file, family_lookup)
        drift = compute_drift_assessability(
            ref, session["nominal_time_span_s"], session["n_segments"], session["keep_fraction_recommended"], profile
        )
        session.update(drift)
        segment_frames.append(seg)
        session_rows.append(session)
        refs[campaign_id] = ref
    return pd.concat(segment_frames, ignore_index=True), pd.DataFrame(session_rows), refs


def run_session_qc(
    root: str | Path | None = None,
    output_root: str | Path | None = None,
    profile: str = MAIN_PROFILE,
) -> dict[str, pd.DataFrame]:
    root = Path(root) if root else Path.cwd()
    output_root = Path(output_root) if output_root else root / "outputs" / "session_qc"
    output_root.mkdir(parents=True, exist_ok=True)

    profile_roots = {
        "permissive": root / "outputs" / "permissive",
        "recommended": root / "outputs" / "recommended",
        "restrictive": root / "outputs" / "restrictive",
    }
    flag_policy = pd.read_csv(root / "config" / "flag_policy.csv")
    family_lookup = dict(zip(flag_policy["flag_name"], flag_policy["reason_family"]))
    session_policy = pd.read_csv(root / "config" / "session_qc_policy.csv")
    suitability_policy = pd.read_csv(root / "config" / "session_suitability_policy.csv")

    manifest = pd.read_csv(root / "data/manifests/campaign_manifest.csv")
    excluded = manifest["exclude_from_analysis"].astype(str).str.lower().isin({"true", "1", "yes"})
    canonical = manifest.loc[~excluded, "canonical_campaign_id"]
    if canonical.isna().any() or not canonical.is_unique:
        raise ValueError("Canonical campaign IDs in the manifest must be non-null and unique")
    campaign_ids = sorted(canonical.astype(str))
    if not campaign_ids:
        raise ValueError("Session QC requires at least one canonical campaign")

    segment_metrics, session_metrics, refs = _load_all_campaign_metrics(campaign_ids, profile_roots, family_lookup, profile)

    segment_qc = compute_segment_status(segment_metrics, session_policy, profile)
    session_qc = compute_session_status(session_metrics, session_policy, profile)
    suitability = compute_all_suitability(session_qc, suitability_policy, segment_qc)

    qc_fingerprint = settings_fingerprint(root / "config")
    session_qc["qc_config_fingerprint"] = qc_fingerprint
    session_qc["qc_version"] = CONFIG_VERSION

    segment_qc.to_csv(output_root / "segment_qc_inventory.csv", index=False)
    session_qc.to_csv(output_root / "session_qc_inventory.csv", index=False)
    suitability.to_csv(output_root / "session_suitability_inventory.csv", index=False)

    segment_reason_codes = build_segment_reason_codes(segment_qc, SEGMENT_DIMENSIONS)
    session_reason_codes = build_session_reason_codes(session_qc, SESSION_DIMENSIONS)
    segment_reason_codes.to_csv(output_root / "segment_reason_codes.csv", index=False)
    session_reason_codes.to_csv(output_root / "session_reason_codes.csv", index=False)

    write_policy_snapshot(session_policy, profile, output_root / "session_qc_policy_effective.csv")

    sensitivity = run_session_sensitivity(session_metrics, session_policy)
    sensitivity.to_csv(output_root / "session_qc_sensitivity.csv", index=False)

    for campaign_id in campaign_ids:
        session_row = session_qc.loc[session_qc["canonical_campaign_id"] == campaign_id].iloc[0]
        seg_rows = segment_qc.loc[segment_qc["canonical_campaign_id"] == campaign_id]
        suit_rows = suitability.loc[suitability["canonical_campaign_id"] == campaign_id]
        write_campaign_json(campaign_id, session_row, seg_rows, suit_rows, output_root, CONFIG_VERSION)

    diagnostic_paths = write_all_diagnostics(refs, session_qc, output_root / "figures")

    return {
        "segment_qc": segment_qc,
        "session_qc": session_qc,
        "suitability": suitability,
        "segment_reason_codes": segment_reason_codes,
        "session_reason_codes": session_reason_codes,
        "campaign_ids": campaign_ids,
        "diagnostic_paths": diagnostic_paths,
        "refs": refs,
        "sensitivity": sensitivity,
    }
