"""Validation vs diagnostic spine (outputs/diag_20261015) and figures.

Run as a script: ``python -m meteotracker_qc.corridors_v2.validate [OUT_DIR]``. All work happens in main():
importing this module has no side effects (no file reads/writes), which the package import-closure test
requires (tests/test_package_resources.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else list(argv)
    out = Path(argv[0] if argv else "outputs/corridor_passages_20261015")
    diag = Path("outputs/diag_20261015")
    gp = out / "corridors.gpkg"
    corr = gpd.read_file(gp, layer="corridors")
    b100 = gpd.read_file(gp, layer="bins_100m")
    pas = pd.read_csv(out / "passages.csv")
    sp = pd.read_csv(diag / "spine.csv").merge(pd.read_csv(diag / "spine_profile.csv"), on=["i", "j"])
    spg = gpd.GeoDataFrame(sp, geometry=gpd.points_from_xy((sp.i + .5) * 50, (sp.j + .5) * 50), crs=32632)
    # corridors hit by the spine (<=35 m)
    d = np.array([[shapely.distance(l, p) for l in corr.geometry] for p in spg.geometry])
    spg["corr_idx"] = d.argmin(1); spg["dist"] = d.min(1)
    spg = spg[spg.dist <= 35].copy()
    ns_ids = corr.corridor_id.iloc[spg.corr_idx.value_counts().index].tolist()
    spg["corridor_id"] = corr.corridor_id.values[spg.corr_idx]
    spg["s"] = [corr.geometry.iloc[k].project(p) for k, p in zip(spg.corr_idx, spg.geometry)]
    spg["bin_id"] = (spg.s // 100).astype(int)
    spg = spg.merge(b100.drop(columns="geometry")[["corridor_id", "bin_id", "n_passages", "n_campaigns", "n_dates"]],
                    on=["corridor_id", "bin_id"], how="left").sort_values("j")
    spg["s_axis_km"] = (spg.j - spg.j.min()) * 0.05
    spg.drop(columns="geometry").to_csv(out / "validation_ns_axis.csv", index=False)
    # passages on N-S axis: distinct campaign-passages on spine corridors, covering spine part
    ns_pas = pas[pas.corridor_id.isin(ns_ids)]
    res = dict(spine_cells=int(len(sp)), spine_cells_matched=int(len(spg)), ns_corridors=ns_ids,
               ns_bin_passages_median=float(spg.n_passages.median()), ns_bin_passages_p90=float(spg.n_passages.quantile(.9)),
               ns_bin_passages_max=int(spg.n_passages.max()),
               ns_bin_campaigns_median=float(spg.n_campaigns.median()),
               diag_true_campaigns_median=float(spg.true_campaigns.median()),
               product_max_median=float(spg.product_max_passages_one_segment.median()),
               product_max_max=int(spg.product_max_passages_one_segment.max()),
               mean_abs_diff_campaigns_vs_true=float((spg.n_campaigns - spg.true_campaigns).abs().mean()),
               corr_campaigns_vs_true=float(spg[["n_campaigns", "true_campaigns"]].corr().iloc[0, 1]),
               ns_distinct_passages=int(len(ns_pas)), ns_distinct_campaigns=int(ns_pas.campaign_id.nunique()))
    (out / "validation.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))
    # figures
    bd = gpd.read_file("data/external/boundaries/confine_comune_bologna.gpkg").to_crs(32632)
    cm = plt.get_cmap("viridis")
    def mapfig(ax, bbox=None, lw=2.5):
        bd.boundary.plot(ax=ax, color="k", lw=.8)
        b100[b100.n_passages == 0].plot(ax=ax, color="lightgrey", lw=lw)
        b100[b100.n_passages > 0].plot(ax=ax, column="n_passages", cmap=cm, lw=lw, legend=True, vmin=1, vmax=b100.n_passages.max(),
                                       legend_kwds={"label": "n passaggi per bin 100 m", "shrink": .6})
        if bbox:
            ax.set_xlim(bbox[0], bbox[2]); ax.set_ylim(bbox[1], bbox[3])
        ax.set_axis_off()
    fig, ax = plt.subplots(figsize=(10, 10)); x0, y0, x1, y1 = bd.total_bounds
    mapfig(ax, (x0 - 1000, y0 - 1000, x1 + 1000, y1 + 1000)); ax.set_title("Corridoi v2: passaggi per bin 100 m (grigio = 0)")
    fig.savefig(out / "map_bins_passages.png", dpi=130, bbox_inches="tight"); plt.close(fig)
    x0, y0, x1, y1 = spg.total_bounds
    fig, ax = plt.subplots(figsize=(8, 10)); mapfig(ax, (x0 - 700, y0 - 300, x1 + 700, y1 + 300), lw=4)
    ax.set_title("Zoom asse N-S (Pepoli - Colli - Sabbiuno)"); fig.savefig(out / "map_ns_axis_zoom.png", dpi=130, bbox_inches="tight"); plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(spg.s_axis_km, spg.n_passages, label="v2: passaggi per bin 100 m", lw=2)
    ax.plot(spg.s_axis_km, spg.n_campaigns, label="v2: campagne distinte per bin", lw=1.5)
    ax.plot(spg.s_axis_km, spg.true_campaigns, "--", label="diagnosi: campagne vere per cella 50 m", color="grey")
    ax.plot(spg.s_axis_km, spg.product_max_passages_one_segment, label="prodotto ufficiale: max passaggi (1 segmento)", color="red")
    ax.set_xlabel("km lungo l'asse (S->N)"); ax.set_ylabel("conteggio"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title("Profilo asse N-S: conteggi v2 vs prodotto ufficiale")
    fig.savefig(out / "profile_ns_axis.png", dpi=130, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    main()
