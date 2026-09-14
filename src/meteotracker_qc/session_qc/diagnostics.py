"""Multi-panel diagnostic PNGs for problematic campaigns. Reuses the
matplotlib.use("Agg") convention already established in
pipeline.py::_write_diagnostic_artifacts. Never color-only: every panel uses
labels, markers, hatched/shaded bands, or text alongside color.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from .session_status import SESSION_DIMENSIONS


def select_campaigns_for_diagnostics(session_qc: pd.DataFrame, min_session_duration_s: float = 30.0) -> list[str]:
    problematic = session_qc["session_qc_status"].isin(["PARTIAL", "REJECT", "NOT_ASSESSABLE"])
    for dim in SESSION_DIMENSIONS:
        col = f"{dim}_status"
        if col in session_qc.columns:
            problematic = problematic | (session_qc[col] == "POOR")
    problematic = problematic | (session_qc["nominal_time_span_s"] < min_session_duration_s)
    return session_qc.loc[problematic, "canonical_campaign_id"].tolist()


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].fillna(False).astype(bool)


def plot_campaign_diagnostic(ref: pd.DataFrame, session_row: pd.Series, output_path: Path) -> None:
    ref = ref.loc[ref["time_utc"].notna()].reset_index(drop=True)
    fig, axes = plt.subplots(7, 1, figsize=(14, 20), sharex=True)
    time = ref["time_utc"]

    ax = axes[0]
    temp = pd.to_numeric(ref.get("canonical_temperature_c"), errors="coerce")
    ax.plot(time, temp, color="#0f766e", lw=1, label="temperature")
    spike, rate = _bool_col(ref, "qc_temp_isolated_spike"), _bool_col(ref, "qc_temp_rate_anomaly")
    if spike.any():
        ax.scatter(time[spike], temp[spike], marker="x", color="#dc2626", s=35, label="spike", zorder=5)
    if rate.any():
        ax.scatter(time[rate], temp[rate], marker="^", color="#ea580c", s=22, label="rate anomaly", zorder=5)
    ax.set_ylabel("Temp [C]")
    ax.legend(loc="upper right", fontsize=7)
    ax.set_title("1. Temperature over time (markers, not color alone, flag spikes/rate anomalies)", fontsize=8)

    ax = axes[1]
    ax.plot(time, pd.to_numeric(ref.get("speed_device_kmh"), errors="coerce"), color="#1d4ed8", lw=1, label="speed device")
    ax.plot(time, pd.to_numeric(ref.get("speed_gps_kmh"), errors="coerce"), color="#dc2626", lw=0.8, ls="--", label="speed GPS")
    low_vent = _bool_col(ref, "qc_low_ventilation_possible")
    if low_vent.any():
        ax.fill_between(time, 0, 1, where=low_vent, transform=ax.get_xaxis_transform(), color="grey", alpha=0.25, hatch="//", label="low ventilation risk")
    ax.set_ylabel("Speed [km/h]")
    ax.legend(loc="upper right", fontsize=7)
    ax.set_title("2. Device vs GPS speed (solid/dashed), hatched low-ventilation band", fontsize=8)

    # Segment-start and gap markers use axvline + a legend/summary text block
    # (panel 7) rather than per-point rotated ax.text() annotations -- this
    # environment's matplotlib/freetype build raises a TypeError inside
    # font._set_transform() for rotated per-point text at this figure size
    # (reproduced even on a single-segment, 21-row campaign, so it is a
    # rendering-path issue, not a data-volume one); axvline avoids the path
    # entirely while keeping every marker readable from the axis itself.
    ax = axes[2]
    ax.step(time, ref["segment_id"], where="post", color="black", lw=1)
    reason_markers = {"long_gap": ("#dc2626", "--"), "nonpositive_dt": ("#ea580c", ":"), "campaign_start": ("#16a34a", "-")}
    seen_reasons = set()
    for seg_id, g in ref.groupby("segment_id"):
        label_time = g["time_utc"].iloc[0]
        if pd.isna(label_time) or seg_id == ref["segment_id"].iloc[0]:
            continue
        reason = str(g["segment_start_reason"].iloc[0])
        color, style = reason_markers.get(reason, ("#6b7280", "-."))
        ax.axvline(label_time, color=color, ls=style, lw=0.8, alpha=0.6, label=reason if reason not in seen_reasons else None)
        seen_reasons.add(reason)
    ax.set_ylabel("segment_id")
    if seen_reasons:
        ax.legend(loc="upper left", fontsize=6, ncol=3)
    ax.set_title("3. Segment id (vertical lines mark segment_start_reason)", fontsize=8)

    ax = axes[3]
    gap_rows = ref[_bool_col(ref, "qc_sampling_gap_long") & ref["time_utc"].notna()]
    gap_summary_parts = []
    if len(gap_rows):
        for _, r in gap_rows.iterrows():
            ax.axvline(r["time_utc"], color="#dc2626", lw=1.5)
            gap_summary_parts.append(f"{r['time_utc']:%H:%M:%S}={r['dt_s']:.0f}s")
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_ylabel("long gaps")
    ax.set_title("4. Long gaps (vertical lines; durations listed in panel 7)", fontsize=8)

    ax = axes[4]
    stab = _bool_col(ref, "qc_sensor_stabilization") | _bool_col(ref, "qc_segment_restart_recovery")
    freeze, stop, recovery = _bool_col(ref, "qc_gps_freeze"), _bool_col(ref, "qc_stop_event"), _bool_col(ref, "qc_post_stop_recovery")
    if stab.any():
        ax.fill_between(time, 0, 1, where=stab, transform=ax.get_xaxis_transform(), color="#7c3aed", alpha=0.2, hatch="\\\\", label="stabilization/restart")
    if freeze.any():
        ax.scatter(time[freeze], [0.8] * int(freeze.sum()), marker="s", s=12, color="black", label="gps freeze")
    if stop.any():
        ax.scatter(time[stop], [0.5] * int(stop.sum()), marker="o", s=12, color="#92400e", label="stop")
    if recovery.any():
        ax.scatter(time[recovery], [0.25] * int(recovery.sum()), marker="v", s=12, color="#16a34a", label="post-stop recovery")
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.legend(loc="upper right", fontsize=6, ncol=4)
    ax.set_title("5. Stabilization band, freeze/stop/recovery markers", fontsize=8)

    ax = axes[5]
    ax.step(time, ref["keep_recommended"].astype(int), where="post", color="#0f766e", lw=1.3, label="keep_recommended")
    ax.step(time, ref["keep_restrictive"].astype(int) * 0.9, where="post", color="#dc2626", lw=1.0, ls="--", label="keep_restrictive")
    ax.set_ylim(-0.1, 1.2)
    ax.set_yticks([0, 1])
    ax.legend(loc="upper right", fontsize=7)
    ax.set_title("6. keep_recommended vs keep_restrictive (step lines)", fontsize=8)

    ax = axes[6]
    # Note: `ax.axis("off")` on the last axis of a sharex=True figure with a
    # datetime x-axis reproducibly crashes this environment's matplotlib/
    # freetype text renderer (font._set_transform overflow) when combined
    # with any text() call here -- root-caused via bisection, reproduced in
    # a minimal synthetic example. Hiding ticks/spines manually avoids the
    # bug path entirely while producing the same visual result.
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    keep_frac = session_row.get("keep_fraction_recommended")
    keep_frac_text = f"{keep_frac:.3f}" if pd.notna(keep_frac) else "n/a"
    gaps_text = ", ".join(gap_summary_parts) if gap_summary_parts else "none"
    text = (
        f"session_qc_status = {session_row.get('session_qc_status')}\n"
        f"primary reason: {session_row.get('session_primary_reason')}\n"
        f"secondary reasons: {session_row.get('session_secondary_reasons')}\n"
        f"reason families: {session_row.get('session_reason_families')}\n"
        f"keep_fraction_recommended = {keep_frac_text}\n"
        f"long gaps (time=duration): {gaps_text}"
    )
    ax.text(0.0, 0.5, text, fontsize=8, va="center", family="monospace", transform=ax.transAxes)
    ax.set_title("7. Reason codes and gap summary (text, not color-coded)", fontsize=8)

    fig.suptitle(
        f"{session_row['canonical_campaign_id']}  --  status={session_row.get('session_qc_status')}",
        fontsize=11,
    )
    for ax in axes[:6]:
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=130)
    plt.close(fig)


def write_all_diagnostics(campaign_refs: dict[str, pd.DataFrame], session_qc: pd.DataFrame, output_dir: Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = select_campaigns_for_diagnostics(session_qc)
    written = []
    for campaign_id in selected:
        if campaign_id not in campaign_refs:
            continue
        session_row = session_qc.loc[session_qc["canonical_campaign_id"] == campaign_id].iloc[0]
        out_path = output_dir / f"{campaign_id}_diagnostic.png"
        plot_campaign_diagnostic(campaign_refs[campaign_id], session_row, out_path)
        written.append(out_path)
    return written
