"""Regression tests anchored to real campaigns found during the QC audit
(reports/targeted_qc_audit.md), not synthetic fixtures. These read data/raw/
directly (read-only) and must never be affected by anything that writes to
outputs/.
"""
from pathlib import Path

import pandas as pd

from meteotracker_qc.time_qc import detect_time_issues

RAW_ROOT = Path(__file__).resolve().parent.parent / "data" / "raw"
BOLOGNA_RAVENNA_CSV = RAW_ROOT / "06-04" / "20260604T11_40_32_mtdicambo_AC4D162B317E_Bologna-Ravenna.csv"


def test_bologna_ravenna_long_gap_regression():
    """The audit found this campaign has a single ~2469s (41 minute) gap,
    ~84% of its nominal session duration. This must become >= 2 segments,
    with valid points preserved on both sides and no synthesized spatial
    link across the gap, and the observed (segment) duration must stay
    distinct from the nominal start-end duration.
    """
    assert BOLOGNA_RAVENNA_CSV.exists(), f"regression fixture missing: {BOLOGNA_RAVENNA_CSV}"
    raw = pd.read_csv(BOLOGNA_RAVENNA_CSV, na_values=["-"])
    n_raw = len(raw)

    out = detect_time_issues(raw)

    # No rows dropped -- valid points on both sides of the gap are preserved.
    assert len(out) == n_raw

    # The gap is recognized as a long sampling gap and a segment break.
    assert out["qc_sampling_gap_long"].any()
    assert out["qc_segment_break"].any()

    max_gap_s = out["dt_s"].max()
    assert max_gap_s > 2000  # the known ~2469s gap

    # At least 2 distinct segments are produced.
    n_segments = out["segment_id"].nunique()
    assert n_segments >= 2

    # The row where the gap ends starts a new segment_id, and the segment
    # covering the gap-adjacent tail is not merged with the pre-gap segment.
    gap_row_positions = out.index[out["qc_sampling_gap_long"]].tolist()
    assert len(gap_row_positions) >= 1
    first_gap_pos = gap_row_positions[0]
    segment_before = out["segment_id"].iloc[max(first_gap_pos - 1, 0)]
    segment_after = out["segment_id"].iloc[first_gap_pos]
    assert segment_after == segment_before + 1

    # No artificial spatial/time continuity is synthesized across the gap:
    # elapsed_s (real observed span) differs from a naive nominal duration
    # that would treat the whole file as one continuous block.
    valid_time = out["time_utc"].notna()
    nominal_duration_s = (out.loc[valid_time, "time_utc"].max() - out.loc[valid_time, "time_utc"].min()).total_seconds()
    # Sum of within-segment observed spans (excludes the gap itself).
    observed_duration_s = 0.0
    for _, seg in out.groupby("segment_id"):
        seg_valid = seg.loc[seg["time_utc"].notna(), "time_utc"]
        if len(seg_valid) >= 2:
            observed_duration_s += (seg_valid.max() - seg_valid.min()).total_seconds()
    assert observed_duration_s < nominal_duration_s
    assert (nominal_duration_s - observed_duration_s) > 2000  # the gap itself is excluded from observed time
