"""Section P: multi-panel diagnostic PNGs for the temporal-drift diagnosis.
Deliberately a SEPARATE module from session_qc/diagnostics.py (not modified)
per the spec's explicit instruction. Reuses the matplotlib.use("Agg")
convention already established across this project, and proactively avoids
the known rendering bug already root-caused in session_qc/diagnostics.py:
`ax.axis("off")` on the last axis of a sharex=True multi-panel datetime
figure, combined with any ax.text() call, crashes this environment's
freetype text renderer -- hidden ticks/spines are set manually instead.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
from matplotlib import pyplot as plt

SUPPORTED_DIAGNOSES = {"TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "POSSIBLE_NONLINEAR_BACKGROUND_CHANGE"}
TOP_N_BY_PAIRS = 5


def select_campaigns_for_diagnostics(session_temporal_diagnostics: pd.DataFrame) -> list[str]:
    df = session_temporal_diagnostics
    selected = pd.Series(False, index=df.index)
    selected |= df["temporal_internal_assessability_status"] == "ASSESSABLE"
    selected |= df["temporal_change_diagnosis"].isin(SUPPORTED_DIAGNOSES)
    selected |= df.get("method_agreement", pd.Series("", index=df.index)) == "METHODS_DISAGREE"
    selected |= df.get("temporal_change_diagnosis", pd.Series("", index=df.index)) == "INTERNAL_METHODS_DISAGREE"
    selected |= df.get("temporal_sensitivity_stability_class", pd.Series("", index=df.index)) == "HIGHLY_SENSITIVE"
    if "start_end_pair_consistent_with_revisits" in df.columns:
        selected |= df["start_end_pair_consistent_with_revisits"] == False  # noqa: E712
    if "dominated_by_single_location" in df.columns:
        selected |= df["dominated_by_single_location"] == True  # noqa: E712
    if "n_repeated_location_pairs_valid" in df.columns:
        top_pairs = df.nlargest(TOP_N_BY_PAIRS, "n_repeated_location_pairs_valid")["canonical_campaign_id"]
        selected |= df["canonical_campaign_id"].isin(top_pairs)
    return df.loc[selected, "canonical_campaign_id"].tolist()


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].fillna(False).astype(bool)


def plot_campaign_temporal_diagnostic(
    campaign_id: str, df: pd.DataFrame, groups: pd.DataFrame, visits: pd.DataFrame,
    pairs: pd.DataFrame, session_row: pd.Series, sensitivity: pd.DataFrame,
    detrending_df: pd.DataFrame | None, output_path: Path,
) -> None:
    ref = df.loc[df["time_utc"].notna()].reset_index(drop=True)
    fig, axes = plt.subplots(8, 1, figsize=(14, 24), sharex=False)
    candidate_mask = ref.get("temporal_candidate_recommended", pd.Series(False, index=ref.index)).fillna(False).astype(bool)

    ax = axes[0]
    ax.plot(ref["time_utc"], ref["canonical_temperature_c"], color="#6b7280", lw=0.8, label="raw temperature")
    ax.scatter(ref.loc[candidate_mask, "time_utc"], ref.loc[candidate_mask, "canonical_temperature_c"], s=8, color="#0f766e", label="temporal candidate", zorder=3)
    ax.set_ylabel("Temp [C]")
    ax.legend(loc="upper right", fontsize=7)
    ax.set_title("1. Raw temperature over time, candidate points marked", fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    ax = axes[1]
    if not visits.empty:
        group_ids = visits["repeated_location_group_id"].unique()
        cmap = plt.get_cmap("tab20")
        for i, gid in enumerate(group_ids):
            gvisits = visits[visits["repeated_location_group_id"] == gid]
            ax.scatter(gvisits["visit_representative_timestamp"], [i] * len(gvisits), color=cmap(i % 20), s=25, label=None)
        ax.set_ylabel("group index")
        ax.set_title(f"2. Visits by spatial group ({len(group_ids)} groups, {len(visits)} visits)", fontsize=8)
    else:
        ax.text(0.5, 0.5, "no visits", ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    ax = axes[2]
    if not pairs.empty:
        valid = pairs[pairs["pair_qc_status"] == "VALID"]
        excluded = pairs[pairs["pair_qc_status"] != "VALID"]
        if not valid.empty:
            ax.scatter(valid["time_difference_s"] / 60.0, valid["temperature_difference_c"], s=15, color="#0f766e", label="valid pair")
        if not excluded.empty:
            ax.scatter(excluded["time_difference_s"] / 60.0, excluded["temperature_difference_c"], s=15, color="#dc2626", marker="x", label="excluded pair")
        ax.axhline(0, color="grey", lw=0.5)
        ax.set_xlabel("delta t [min]"); ax.set_ylabel("delta T [C]")
        ax.legend(loc="upper right", fontsize=7)
    else:
        ax.text(0.5, 0.5, "no pairs", ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("3. Pairwise delta-T vs delta-t (valid vs excluded)", fontsize=8)

    ax = axes[3]
    if not pairs.empty:
        valid = pairs[pairs["pair_qc_status"] == "VALID"]
        if not valid.empty:
            per_group = valid.groupby("repeated_location_group_id")["pairwise_slope_c_per_min"].median().sort_values()
            ax.bar(range(len(per_group)), per_group.values, color="#1d4ed8")
            ax.axhline(0, color="grey", lw=0.5)
            ax.set_xlabel("group (sorted by slope)"); ax.set_ylabel("median slope [C/min]")
    ax.set_title("4. Per-group median pairwise slope", fontsize=8)

    ax = axes[4]
    m1 = session_row.get("method1_trend_c_per_min", float("nan"))
    m2 = session_row.get("primary_trend_c_per_min", float("nan"))
    ci_low, ci_high = session_row.get("primary_confidence_interval_low", float("nan")), session_row.get("primary_confidence_interval_high", float("nan"))
    labels, values, errs = [], [], []
    if pd.notna(m1):
        labels.append("Method 1\n(pairwise median)"); values.append(m1); errs.append(0)
    if pd.notna(m2):
        labels.append("Method 2\n(fixed-effects Huber)"); values.append(m2)
        errs.append((m2 - ci_low, ci_high - m2) if pd.notna(ci_low) and pd.notna(ci_high) else 0)
    if values:
        x = np.arange(len(values))
        ax.bar(x, values, color="#0f766e")
        for xi, v, e in zip(x, values, errs):
            if isinstance(e, tuple):
                ax.errorbar([xi], [v], yerr=[[e[0]], [e[1]]], fmt="none", ecolor="black", capsize=4)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
        ax.axhline(0, color="grey", lw=0.5)
        ax.set_ylabel("C/min")
    ax.set_title("5. Aggregated trend estimate per method, with CI where available", fontsize=8)

    ax = axes[5]
    if not sensitivity.empty and "method2_trend_c_per_min" in sensitivity.columns:
        ax.scatter(range(len(sensitivity)), sensitivity["method2_trend_c_per_min"], s=20, color="#7c3aed")
        ax.axhline(0, color="grey", lw=0.5)
        ax.set_xticks(range(len(sensitivity)))
        ax.set_xticklabels(sensitivity["config_name"], rotation=60, ha="right", fontsize=5)
        ax.set_ylabel("C/min")
    ax.set_title("6. Trend sensitivity across the 18-configuration sweep", fontsize=8)

    ax = axes[6]
    if detrending_df is not None and detrending_df["temp_detrended_experimental_c"].notna().any():
        ax.plot(detrending_df["time_utc"], detrending_df["temp_original_c"], color="#6b7280", lw=0.7, label="raw")
        ax.plot(detrending_df["time_utc"], detrending_df["temp_detrended_experimental_c"], color="#dc2626", lw=0.9, label="detrended (experimental)")
        ax.legend(loc="upper right", fontsize=7)
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    else:
        ax.text(0.5, 0.5, "detrending not produced for this session", ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("7. Raw vs experimental detrended series (when available)", fontsize=8)

    ax = axes[7]
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    text = (
        f"assessability = {session_row.get('temporal_internal_assessability_status')}\n"
        f"temporal_change_diagnosis = {session_row.get('temporal_change_diagnosis')}\n"
        f"sensor_drift_interpretation = {session_row.get('sensor_drift_interpretation')}\n"
        f"method_agreement = {session_row.get('method_agreement')}\n"
        f"temporal_model_form = {session_row.get('temporal_model_form')}\n"
        f"sensitivity_stability = {session_row.get('temporal_sensitivity_stability_class')}\n"
        f"detrending_supported = {session_row.get('detrending_supported')}\n"
        f"n_groups_valid={session_row.get('n_repeated_location_groups_valid')}  "
        f"n_visits={session_row.get('n_repeated_location_visits')}  "
        f"n_pairs_valid={session_row.get('n_repeated_location_pairs_valid')}"
    )
    ax.text(0.0, 0.5, text, fontsize=8, va="center", family="monospace", transform=ax.transAxes)
    ax.set_title("8. Reason codes and key metrics (text)", fontsize=8)

    fig.suptitle(f"{campaign_id} -- {session_row.get('temporal_change_diagnosis')}", fontsize=11)
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def write_all_diagnostics(
    campaign_dfs: dict[str, pd.DataFrame], groups_by_campaign: dict[str, pd.DataFrame],
    visits_by_campaign: dict[str, pd.DataFrame], pairs_by_campaign: dict[str, pd.DataFrame],
    sensitivity_by_campaign: dict[str, pd.DataFrame], detrending_by_campaign: dict[str, pd.DataFrame],
    session_temporal_diagnostics: pd.DataFrame, output_dir: Path,
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = select_campaigns_for_diagnostics(session_temporal_diagnostics)
    written = []
    for campaign_id in selected:
        if campaign_id not in campaign_dfs:
            continue
        session_row = session_temporal_diagnostics.loc[session_temporal_diagnostics["canonical_campaign_id"] == campaign_id].iloc[0]
        out_path = output_dir / f"{campaign_id}_temporal_diagnostic.png"
        plot_campaign_temporal_diagnostic(
            campaign_id, campaign_dfs[campaign_id], groups_by_campaign.get(campaign_id, pd.DataFrame()),
            visits_by_campaign.get(campaign_id, pd.DataFrame()), pairs_by_campaign.get(campaign_id, pd.DataFrame()),
            session_row, sensitivity_by_campaign.get(campaign_id, pd.DataFrame()),
            detrending_by_campaign.get(campaign_id), out_path,
        )
        written.append(out_path)
    return written
