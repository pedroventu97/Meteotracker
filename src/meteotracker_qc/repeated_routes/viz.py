"""Diagnostic visualizations (section 15). Descriptive only, no scientific interpretation."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import LineString, MultiLineString

QUALITY_COLORS = {"high": "#16a34a", "medium": "#f59e0b", "low": "#dc2626", "excluded": "#6b7280"}
DIRECTION_COLORS = {"same_direction": "#1d4ed8", "opposite_direction": "#dc2626", "direction_uncertain": "#9ca3af"}
TIME_BIN_ORDER = ["night", "early_morning", "morning", "midday", "afternoon", "late_afternoon", "evening"]


def _set_geo_aspect(ax, mean_lat: float = 44.5) -> None:
    """Approximate equirectangular aspect for lon/lat axes (adjustable="box" so the
    axes box itself is shrunk to fit, never the data limits -- adjustable="datalim"
    combined with tight_layout()/out-of-axes text can otherwise silently inflate the
    plotted data range far beyond the actual geometry, see reports/repeated_routes_phase1.md)."""
    ax.set_aspect(1.0 / max(np.cos(np.radians(mean_lat)), 1e-6), adjustable="box")


def _plot_geom(ax, geom, **kwargs) -> None:
    if geom is None:
        return
    if isinstance(geom, LineString):
        xs, ys = geom.xy
        ax.plot(xs, ys, **kwargs)
    elif isinstance(geom, MultiLineString):
        for part in geom.geoms:
            xs, ys = part.xy
            ax.plot(xs, ys, **kwargs)


def fig_all_campaigns(result, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))
    for tracks in result.campaign_tracks_by_id.values():
        for part in tracks.parts:
            ax.plot(part.points["Lon"], part.points["Lat"], linewidth=0.6, alpha=0.6, color="#334155")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"All campaigns (n={len(result.campaign_tracks_by_id)})")
    _set_geo_aspect(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_valid_vs_excluded(result, path: Path) -> None:
    quality_by_campaign = dict(zip(result.inventory_df["campaign_id"], result.inventory_df["campaign_quality_flag"]))
    fig, ax = plt.subplots(figsize=(8, 8))
    plotted_labels = set()
    for campaign_id, tracks in result.campaign_tracks_by_id.items():
        quality = quality_by_campaign.get(campaign_id, "excluded")
        usable = quality in ("high", "medium")
        color = "#16a34a" if usable else "#dc2626"
        label = "usable (high/medium)" if usable else "low/excluded"
        for part in tracks.parts:
            ax.plot(
                part.points["Lon"], part.points["Lat"], linewidth=0.7, alpha=0.7, color=color,
                label=label if label not in plotted_labels else None,
            )
            plotted_labels.add(label)
    ax.legend(loc="best", fontsize=8)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Usable vs low-quality/excluded campaigns")
    _set_geo_aspect(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_segments_by_dates(segments_df: pd.DataFrame, passages_df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))
    if segments_df.empty:
        ax.text(0.5, 0.5, "No repeated segments found", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
    else:
        n_dates = passages_df.groupby("repeated_segment_id")["date"].nunique()
        vmax = max(int(n_dates.max()), 2)
        cmap = plt.get_cmap("viridis")
        for _, seg in segments_df.iterrows():
            n = int(n_dates.get(seg["repeated_segment_id"], 1))
            color = cmap(min(n, vmax) / vmax)
            _plot_geom(ax, seg["geometry"], linewidth=2.0, color=color)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=1, vmax=vmax))
        fig.colorbar(sm, ax=ax, label="n_distinct_dates")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Repeated segments by number of distinct dates")
    _set_geo_aspect(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_segments_by_quality(segments_df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))
    if segments_df.empty:
        ax.text(0.5, 0.5, "No repeated segments found", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
    else:
        plotted = set()
        for _, seg in segments_df.iterrows():
            q = seg["matching_quality"]
            color = QUALITY_COLORS.get(q, "#9ca3af")
            _plot_geom(ax, seg["geometry"], linewidth=2.0, color=color, label=q if q not in plotted else None)
            plotted.add(q)
        ax.legend(loc="best", fontsize=8, title="matching_quality")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Repeated segments by matching quality")
    _set_geo_aspect(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_segment_length_hist(segments_df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    if segments_df.empty:
        ax.text(0.5, 0.5, "No repeated segments found", ha="center", va="center", transform=ax.transAxes)
    else:
        ax.hist(segments_df["segment_length_m"], bins=20, color="#1d4ed8", edgecolor="white")
    ax.set_xlabel("Segment length (m)")
    ax.set_ylabel("Count")
    ax.set_title("Repeated segment length distribution")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_matching_distance_hist(matches_df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    if matches_df.empty:
        ax.text(0.5, 0.5, "No pairwise matches found", ha="center", va="center", transform=ax.transAxes)
    else:
        evidence = matches_df.drop_duplicates("supporting_match_id") if "supporting_match_id" in matches_df else matches_df
        ax.hist(evidence["mean_matching_distance_m"].dropna(), bins=20, color="#0f766e", edgecolor="white")
    ax.set_xlabel("Mean matching distance (m)")
    ax.set_ylabel("Count")
    ax.set_title("Pairwise-match distance distribution")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_passages_hist(segments_df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    if segments_df.empty:
        ax.text(0.5, 0.5, "No repeated segments found", ha="center", va="center", transform=ax.transAxes)
    else:
        max_n = int(segments_df["n_passages"].max())
        ax.hist(segments_df["n_passages"], bins=range(2, max_n + 2), color="#7c3aed", edgecolor="white", align="left")
    ax.set_xlabel("Number of passages per segment")
    ax.set_ylabel("Count")
    ax.set_title("Passages-per-segment distribution")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_campaign_matrix(passages_df: pd.DataFrame, campaign_ids: list[str], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 8))
    n = len(campaign_ids)
    index = {c: i for i, c in enumerate(campaign_ids)}
    matrix = np.zeros((n, n))
    if not passages_df.empty:
        for seg_id, group in passages_df.groupby("repeated_segment_id"):
            campaigns = group["campaign_id"].unique()
            length = float(group["shared_length_m"].max())
            for i, ca in enumerate(campaigns):
                for cb in campaigns[i + 1:]:
                    ia, ib = index.get(ca), index.get(cb)
                    if ia is None or ib is None:
                        continue
                    matrix[ia, ib] += length
                    matrix[ib, ia] += length
    im = ax.imshow(matrix / 1000.0, cmap="magma_r")
    fig.colorbar(im, ax=ax, label="shared length (km)")
    ax.set_title("Campaign x campaign shared-length matrix")
    if n <= 45:
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(campaign_ids, rotation=90, fontsize=5)
        ax.set_yticklabels(campaign_ids, fontsize=5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_segments_per_time_bin(passages_df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    if passages_df.empty:
        ax.text(0.5, 0.5, "No passages found", ha="center", va="center", transform=ax.transAxes)
    else:
        counts = []
        for tb in TIME_BIN_ORDER:
            n = passages_df.loc[passages_df["time_bin"] == tb, "repeated_segment_id"].nunique()
            counts.append(n)
        ax.bar(TIME_BIN_ORDER, counts, color="#0891b2")
        ax.tick_params(axis="x", rotation=45)
    ax.set_ylabel("N distinct repeated segments")
    ax.set_title("Repeated segments observed per time-of-day bin (>=1 passage)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _short_campaign_label(campaign_id: str) -> str:
    """Drop the long device-UUID token (not human-meaningful) for figure labels only."""
    keep = []
    for token in campaign_id.split("_"):
        if token in ("mtdicambo", "private"):
            continue
        if "-" in token and len(token) > 15:  # looks like a device UUID, e.g. B6CCF894-DF13-...
            continue
        keep.append(token)
    return "_".join(keep) if keep else campaign_id


def fig_segment_example(segments_df, passages_df, comparison_row, path: Path) -> None:
    seg_id = comparison_row["repeated_segment_id"]
    seg = segments_df.loc[segments_df["repeated_segment_id"] == seg_id].iloc[0]
    passages = passages_df.loc[passages_df["repeated_segment_id"] == seg_id].sort_values("shared_length_m", ascending=False)

    fig, (ax, ax_text) = plt.subplots(1, 2, figsize=(13, 7), gridspec_kw={"width_ratios": [1, 1.1]})
    _plot_geom(ax, seg["geometry"], linewidth=3.5, color="black", alpha=0.35, zorder=1)
    lines = []
    max_listed = 15
    for i, (_, p) in enumerate(passages.iterrows()):
        color = DIRECTION_COLORS.get(p["direction_class"], "#9ca3af")
        _plot_geom(ax, p["geometry"], linewidth=1.4, color=color, alpha=0.9, zorder=2)
        if i < max_listed:
            label = _short_campaign_label(p["campaign_id"])
            lines.append(f"{p['date']} {p['passage_start_datetime'][11:19]} {p['direction_class']:<19} {p['shared_length_m']:>6.0f} m  {label}")
    if len(passages) > max_listed:
        lines.append(f"... and {len(passages) - max_listed} more passages")

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    mean_lat = float(pd.concat([pd.Series(g.xy[1]) for g in [seg["geometry"]] if g is not None]).mean())
    _set_geo_aspect(ax, mean_lat)
    title = (
        f"{seg_id} — length={seg['segment_length_m']:.0f} m, passages={seg['n_passages']}, "
        f"dates={comparison_row['n_distinct_dates']}, mean_dist={seg['mean_matching_distance_m']:.1f} m, "
        f"score={comparison_row['comparison_potential_score']:.1f} ({comparison_row['comparison_potential_class']})"
    )
    ax.set_title(title, fontsize=8)

    ax_text.axis("off")
    ax_text.text(0.0, 1.0, "\n".join(lines), fontsize=6.5, va="top", ha="left", family="monospace", transform=ax_text.transAxes)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def generate_all_figures(result, figures_dir: Path, cfg) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    fig_all_campaigns(result, figures_dir / "01_all_campaigns.png")
    fig_valid_vs_excluded(result, figures_dir / "02_valid_vs_excluded.png")
    fig_segments_by_dates(result.segments_df, result.passages_df, figures_dir / "03_segments_by_n_dates.png")
    fig_segments_by_quality(result.segments_df, figures_dir / "04_segments_by_quality.png")
    fig_segment_length_hist(result.segments_df, figures_dir / "05_segment_length_hist.png")
    fig_matching_distance_hist(result.matches_df, figures_dir / "06_matching_distance_hist.png")
    fig_passages_hist(result.segments_df, figures_dir / "07_passages_per_segment_hist.png")
    fig_campaign_matrix(result.passages_df, sorted(result.campaign_tracks_by_id.keys()), figures_dir / "08_campaign_matrix.png")
    fig_segments_per_time_bin(result.passages_df, figures_dir / "09_segments_per_time_bin.png")

    if not result.comparison_df.empty:
        top = result.comparison_df.sort_values("comparison_potential_score", ascending=False).head(5)
        for i, (_, row) in enumerate(top.iterrows(), start=1):
            fig_segment_example(result.segments_df, result.passages_df, row, figures_dir / f"10_example_{i}_{row['repeated_segment_id']}.png")
