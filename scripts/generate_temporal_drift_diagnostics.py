"""Cheap follow-up step: generate the Section-P diagnostic PNGs from an
already-completed outputs/temporal_drift/ run, without re-running the
expensive bootstrap-heavy trend estimation. Re-derives only cheap
per-campaign pieces (candidate masks, grouping, pairs -- no bootstrap) and
reuses the already-computed primary trend value from
session_temporal_diagnostics.csv to reconstruct the detrended series where
applicable. Used once, ad hoc, because diagnostics.py was not yet wired into
temporal_drift_pipeline.py when the first full run was launched (fixed for
future runs in temporal_drift_pipeline.py itself).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from meteotracker_qc.temporal_drift.candidates import build_temporal_candidate_masks
from meteotracker_qc.temporal_drift.config import MAIN_PROFILE, get_profile, load_matching_policy
from meteotracker_qc.temporal_drift.detrending import compute_experimental_detrending
from meteotracker_qc.temporal_drift.diagnostics import select_campaigns_for_diagnostics, write_all_diagnostics
from meteotracker_qc.temporal_drift.grouping import compute_groups_and_visits
from meteotracker_qc.temporal_drift.pairs import build_pairs
from meteotracker_qc.temporal_drift_pipeline import _load_campaign_df

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ROOT / "outputs" / "temporal_drift"


def main():
    session = pd.read_csv(OUTPUT_ROOT / "session_temporal_diagnostics.csv")
    sensitivity_all = pd.read_csv(OUTPUT_ROOT / "temporal_drift_sensitivity.csv")
    matching_policy = load_matching_policy(ROOT)
    profile = get_profile(matching_policy, MAIN_PROFILE)

    selected = select_campaigns_for_diagnostics(session)
    print(f"{len(selected)} campaigns selected for diagnostics: {selected}")

    campaign_dfs, groups_by_campaign, visits_by_campaign = {}, {}, {}
    pairs_by_campaign, sensitivity_by_campaign, detrending_by_campaign = {}, {}, {}

    for campaign_id in selected:
        df = _load_campaign_df(campaign_id, ROOT)
        candidate_col = "temporal_candidate_recommended"
        groups, visits, obs = compute_groups_and_visits(df, candidate_col, profile)
        pairs = build_pairs(visits, df, profile)

        campaign_dfs[campaign_id] = df
        groups_by_campaign[campaign_id] = groups
        visits_by_campaign[campaign_id] = visits
        pairs_by_campaign[campaign_id] = pairs
        sensitivity_by_campaign[campaign_id] = sensitivity_all[sensitivity_all["canonical_campaign_id"] == campaign_id]

        row = session.loc[session["canonical_campaign_id"] == campaign_id].iloc[0]
        if bool(row.get("detrending_supported")):
            session_start, session_end = df["time_utc"].min(), df["time_utc"].max()
            method2_primary = {"trend_c_per_min": row.get("primary_trend_c_per_min")}
            detrending_df = compute_experimental_detrending(
                df, candidate_col, session_start, session_end, method2_primary, eligible=True,
            )
            detrending_by_campaign[campaign_id] = detrending_df

    written = write_all_diagnostics(
        campaign_dfs, groups_by_campaign, visits_by_campaign, pairs_by_campaign,
        sensitivity_by_campaign, detrending_by_campaign, session, OUTPUT_ROOT / "figures",
    )
    print(f"wrote {len(written)} diagnostic PNGs to {OUTPUT_ROOT / 'figures'}")


if __name__ == "__main__":
    main()
