"""E0-QC-R steps E and F: mask audit (in memory) and full QC rerun with policy v0.2, three REAL profile runs.

  python e0/run_e0R_qc_split.py audit   -> outputs/e0R_mask_audit_<ts>/   (no QC tree written)
  python e0/run_e0R_qc_split.py run     -> outputs/e0R_qc_split_<ts>/{permissive,recommended,restrictive}/...

Configs: config/qc_E0R_<profile>_v0.2.yaml (policy_file=flag_policy_E0R_v0.2.csv, flag_schema=v0.2: flag-table
severities derived per profile from the policy). Read-only on data/raw and on every existing output; v0.1 configs,
policy and schema untouched. Writes only the new folder named above.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meteotracker_qc.flag_table import build_flag_table  # noqa: E402
from meteotracker_qc.pipeline import MeteotrackerQC  # noqa: E402

ROME = ZoneInfo("Europe/Rome")
PROFILES = ("permissive", "recommended", "restrictive")
OLD = ROOT / "outputs" / "e0_qc_split_20261105T1703"
PROTECTED = ("e0_qc_split_", "p1_repeatability_E0_2026", "qc_mask_audit_E0_", "_20261015", "_20261018")


def log(m):
    print(f"[{datetime.now(ROME):%H:%M:%S}] {m}", flush=True)


def git_commit() -> str:
    try:
        h = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                        text=True).strip()
        return h + ("-dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fingerprint(qc: MeteotrackerQC) -> str:
    return f"{qc.config_path.name}:{sha(qc.config_path)[:12]}|{qc.policy_path.name}:{sha(qc.policy_path)[:12]}|" \
           f"{qc.flag_schema_path.name}:{sha(qc.flag_schema_path)[:12]}"


def canonical_manifest() -> pd.DataFrame:
    m = pd.read_csv(ROOT / "data" / "manifests" / "campaign_manifest.csv")
    return m[(m.is_canonical.astype(str) == "True") & (m.exclude_from_analysis.astype(str) != "True")]


def new_out(prefix: str) -> Path:
    out = ROOT / "outputs" / f"{prefix}{datetime.now(ROME):%Y%m%dT%H%M}"
    if out.exists() or any(out.name.startswith(x) or x in out.name for x in PROTECTED):
        raise SystemExit(f"refusing to write {out}")
    out.mkdir(parents=True)
    return out


def qcs():
    out = {}
    for p in PROFILES:
        q = MeteotrackerQC(ROOT / "config" / f"qc_E0R_{p}_v0.2.yaml")
        assert q.profile_name == p and q.policy_path.name == "flag_policy_E0R_v0.2.csv" and q.flag_schema_path
        out[p] = q
    return out


def old_points() -> pd.DataFrame:
    """Old (v0.1) keep_recommended, its exclusion reasons and the old flag-table exclude state, per point."""
    parts = []
    for cdir in sorted((OLD / "campaigns").iterdir()):
        f = next(cdir.glob("*_flagged.csv"))
        x = pd.read_csv(f, usecols=["source_row", "keep_recommended", "qc_exclusion_reasons_recommended"],
                        low_memory=False)
        x["campaign"] = cdir.name
        parts.append(x)
    d = pd.concat(parts, ignore_index=True)
    d["old_keep_recommended"] = d.pop("keep_recommended").astype(str) == "True"
    ft = pd.read_parquet(OLD / "flag_table_E0.parquet", columns=["canonical_campaign_id", "source_row", "severity"])
    ex = ft[(ft.severity == "exclude") & (ft.source_row >= 0)].drop_duplicates(["canonical_campaign_id", "source_row"])
    ex = ex.rename(columns={"canonical_campaign_id": "campaign"}).assign(old_ft_exclude=True)
    d = d.merge(ex[["campaign", "source_row", "old_ft_exclude"]], how="left", on=["campaign", "source_row"])
    d["old_ft_exclude"] = d["old_ft_exclude"].fillna(False).astype(bool)
    return d.rename(columns={"qc_exclusion_reasons_recommended": "old_reasons_recommended"})


# ------------------------------------------------------------------------------------------------- E: audit
def audit():
    out = new_out("e0R_mask_audit_")
    qc = qcs()
    man = canonical_manifest().sort_values("canonical_campaign_id")
    rows, pts = [], []
    for k, (sf, cid) in enumerate(zip(man.source_file, man.canonical_campaign_id), 1):
        per = {}
        for p, q in qc.items():
            df, _ = q.compute_frame(ROOT / "data" / "raw" / sf)
            ft = build_flag_table(df, canonical_campaign_id=cid, source_file=sf, qc_profile=p,
                                  schema_path=q.flag_schema_path, policy_df=q.flag_policy,
                                  include_file_level_duplicates=False)
            ex = set(ft.loc[ft.severity == "exclude", "source_row"].astype(int))
            ft_keep = ~df["source_row"].isin(ex)
            keep = df[f"keep_{p}"].astype(bool)
            rows.append(dict(campaign=cid, profile=p, n_points=len(df), n_keep=int(keep.sum()),
                             n_ft_exclude_points=len(ex), n_mismatch=int((ft_keep != keep).sum()),
                             n_flag_rows=len(ft), codes_emitted=";".join(sorted(ft.flag_code.unique())),
                             legacy_codes_emitted=";".join(sorted(set(ft.flag_code) & {
                                 "qc_time_duplicate", "qc_time_order", "qc_temp_spike", "qc_impossible_acceleration",
                                 "qc_time_nonpositive_dt"}))))
            per[f"v02_keep_{p}"] = keep.to_numpy()
            per[f"v02_reasons_{p}"] = df[f"qc_exclusion_reasons_{p}"].to_numpy()
        pts.append(pd.DataFrame(dict(campaign=cid, source_row=df["source_row"].to_numpy(), **per)))
        log(f"[{k}/{len(man)}] audit {cid[:40]}")
    A = pd.DataFrame(rows)
    A.to_csv(out / "agreement_by_construction_by_campaign.csv", index=False)
    G = A.groupby("profile")[["n_points", "n_keep", "n_ft_exclude_points", "n_mismatch", "n_flag_rows"]].sum()
    G.to_csv(out / "agreement_by_construction.csv")
    P = pd.concat(pts, ignore_index=True)
    O = old_points()
    D = P.merge(O, on=["campaign", "source_row"], how="left", validate="one_to_one")
    assert D.old_keep_recommended.notna().all()
    S = dict(built_at_europe_rome=datetime.now(ROME).isoformat(timespec="seconds"), code_commit=git_commit(),
             fingerprints={p: fingerprint(q) for p, q in qc.items()},
             agreement_by_construction=G.reset_index().to_dict(orient="records"),
             all_profiles_zero_mismatch=bool((G.n_mismatch == 0).all()),
             legacy_codes_emitted=sorted(set(";".join(A.legacy_codes_emitted).split(";")) - {""}))
    # residual disagreement vs the archived v0.1 masks
    cmp_rows = []
    refs = {"old_keep_recommended": D.old_keep_recommended, "old_flagtable_no_exclude": ~D.old_ft_exclude,
            "old_consensus": D.old_keep_recommended & ~D.old_ft_exclude}
    for p in PROFILES:
        for rn, r in refs.items():
            new = D[f"v02_keep_{p}"]
            cmp_rows.append(dict(new_mask=f"v02_{p}", ref_mask=rn, both_keep=int((new & r).sum()),
                                 both_drop=int((~new & ~r).sum()), new_only_keep=int((new & ~r).sum()),
                                 new_only_drop=int((~new & r).sum()), agreement=float((new == r).mean()),
                                 n_keep_new=int(new.sum()), n_keep_ref=int(r.sum())))
    C = pd.DataFrame(cmp_rows)
    C.to_csv(out / "residual_vs_v01_masks.csv", index=False)
    S["residual_vs_v01"] = C.to_dict(orient="records")
    # drivers of the change old recommended -> v0.2 recommended
    ch = D[D.v02_keep_recommended != D.old_keep_recommended]
    drv = []
    for direction, sub, col in (("v02_keeps_old_dropped", ch[ch.v02_keep_recommended], "old_reasons_recommended"),
                                ("v02_drops_old_kept", ch[~ch.v02_keep_recommended], "v02_reasons_recommended")):
        codes = sub[col].fillna("").astype(str).str.split(";").explode()
        vc = codes[codes != ""].value_counts()
        for c, n in vc.items():
            drv.append(dict(direction=direction, code=c, n_points=int(n), n_direction=int(len(sub))))
    pd.DataFrame(drv).to_csv(out / "change_drivers_recommended.csv", index=False)
    S["change_drivers_recommended"] = drv
    # nesting of real profile runs (not guaranteed: thresholds differ per profile)
    S["nesting"] = dict(rec_kept_but_perm_dropped=int((D.v02_keep_recommended & ~D.v02_keep_permissive).sum()),
                        rest_kept_but_rec_dropped=int((D.v02_keep_restrictive & ~D.v02_keep_recommended).sum()))
    D.drop(columns=[c for c in D.columns if "reasons" in c]).to_parquet(out / "points_masks_v01_v02.parquet", index=False)
    json.dump(S, open(out / "summary.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    log(f"audit done -> {out}; zero mismatch: {S['all_profiles_zero_mismatch']}")
    print(out)


# ------------------------------------------------------------------------------------------------- F: run
def _split_module():
    spec = importlib.util.spec_from_file_location("bsa", ROOT / "e0" / "build_split_assignments_e0.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_split(root: Path, prof_dir: Path) -> dict:
    """Same rules as e0/build_split_assignments_e0.py (reused functions), on the recommended run's frames."""
    bsa = _split_module()
    passages, memberships = bsa.load_passages(), bsa.load_memberships_slim()
    lcz_gdf, warns = bsa.try_load_lcz()
    parts = []
    for cdir in sorted((prof_dir / "campaigns").iterdir()):
        pq = next(cdir.glob("*_standardized.parquet"))
        df = pd.read_parquet(pq)
        la, lo = bsa.find_lat_lon(df)
        stem = pq.name.replace("_standardized.parquet", "")
        t_utc = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
        t_loc = t_utc.dt.tz_convert(ROME)
        route = bsa.assign_route_for_campaign(df, stem, passages, memberships)
        blocks, east, north = bsa.spatial_block_ids(df[la], df[lo])
        lcz = bsa.attach_lcz(east, north, lcz_gdf)
        parts.append(pd.DataFrame(dict(canonical_campaign_id=cdir.name, source_file=df["source_file"].iloc[0],
                                       source_row=df["source_row"], time_utc=t_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                       time_local=t_loc.dt.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                       day=t_loc.dt.strftime("%Y-%m-%d"), route=route.values,
                                       spatial_block_id=blocks.values, lcz=lcz.values, lat=df[la].values,
                                       lon=df[lo].values)))
    A = pd.concat(parts, ignore_index=True)
    A.to_parquet(root / "split_assignments_E0R.parquet", index=False)
    old = pd.read_parquet(OLD / "split_assignments_E0.parquet")
    m = A.merge(old, on=["canonical_campaign_id", "source_row"], suffixes=("", "_old"), how="outer", indicator=True)
    same = lambda c: float(((m[c].astype(str) == m[c + "_old"].astype(str))).mean())  # noqa: E731
    return dict(n_obs=int(len(A)), n_campaigns=int(A.canonical_campaign_id.nunique()), lcz_warnings=warns,
                rows_matched_old=int((m._merge == "both").sum()),
                identical_to_v01_split={c: same(c) for c in ("route", "spatial_block_id", "day", "time_utc")})


def run():
    root = new_out("e0R_qc_split_")
    started = datetime.now(ROME)
    commit = git_commit()
    qc = qcs()
    man = canonical_manifest().sort_values("canonical_campaign_id")
    meta = dict(started_local_europe_rome=started.isoformat(timespec="seconds"), output_root=str(root),
                code_commit=commit, profiles={}, raw_untouched=True, archives_untouched=True)
    for p, q in qc.items():
        pdir = root / p
        (pdir / "campaigns").mkdir(parents=True)
        fp = fingerprint(q)
        frames, fails, summ = [], [], []
        for k, row in enumerate(man.itertuples(index=False), 1):
            cid, sf = row.canonical_campaign_id, row.source_file
            dup = None if pd.isna(row.duplicate_type) else str(row.duplicate_type)
            sha256 = None if pd.isna(row.file_sha256) else row.file_sha256
            try:
                od = pdir / "campaigns" / cid
                st = q.process_file(ROOT / "data" / "raw" / sf, od, diagnostics=False)
                ft = q.emit_flag_table(st, od / f"{Path(sf).stem}_flag_table.csv", canonical_campaign_id=cid,
                                       source_file=sf, file_sha256=sha256, duplicate_type=dup,
                                       config_fingerprint=fp, code_commit=commit)
                frames.append(ft)
                summ.append(dict(canonical_campaign_id=cid, n_rows=len(st), n_keep=int(st[f"keep_{p}"].sum()),
                                 n_segments=int(st.segment_id.nunique()), n_flag_rows=len(ft)))
            except Exception as e:  # noqa: BLE001
                fails.append(dict(canonical_campaign_id=cid, error=str(e), tb=traceback.format_exc()[-1500:]))
            if k % 11 == 0 or k == len(man):
                log(f"[{p}] {k}/{len(man)}")
        F = pd.concat(frames, ignore_index=True)
        F.insert(0, "flag_row_id", np.arange(1, len(F) + 1))
        F.to_parquet(pdir / "flag_table_E0R.parquet", index=False)
        pd.DataFrame(summ).to_csv(pdir / "campaign_summary_E0R.csv", index=False)
        pd.DataFrame(fails).to_csv(pdir / "FAILED_CAMPAIGNS.csv", index=False)
        meta["profiles"][p] = dict(config=str(q.config_path.relative_to(ROOT)), fingerprint=fp, attempted=len(man),
                                   succeeded=len(summ), failed=len(fails), n_flag_rows=int(len(F)),
                                   n_points=int(sum(s["n_rows"] for s in summ)),
                                   n_keep=int(sum(s["n_keep"] for s in summ)),
                                   severity_breakdown=F.severity.value_counts().to_dict(),
                                   qc_profiles_in_table=sorted(F.qc_profile.unique().tolist()),
                                   code_commit_values=sorted(F.code_commit.unique().tolist()))
        log(f"[{p}] done keep={meta['profiles'][p]['n_keep']} flags={len(F)} fails={len(fails)}")
    meta["split"] = build_split(root, root / "recommended")
    meta["finished_local_europe_rome"] = datetime.now(ROME).isoformat(timespec="seconds")
    (root / "E0R_QC_RUN_META.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=str),
                                              encoding="utf-8")
    (root / "README.md").write_text(
        "# E0-QC-R QC split (policy v0.2)\n\n"
        f"- Code commit: `{commit}`; started {meta['started_local_europe_rome']} (Europe/Rome)\n"
        "- Three REAL runs with their own YAMLs: `config/qc_E0R_<profile>_v0.2.yaml` -> `<profile>/campaigns/...`\n"
        "- Policy `config/flag_policy_E0R_v0.2.csv`; schema `e0/qc_flag_schema_E0_v0.2.yaml` (severities derived "
        "per profile from the policy: flag table exclude <=> keep_<profile> False)\n"
        "- Split (same rules as `e0/build_split_assignments_e0.py`): `split_assignments_E0R.parquet`\n"
        "- Criteria: `e0/QC_R_CRITERIA_E0.md`. **No QC declared official.** Raw and archived outputs untouched.\n",
        encoding="utf-8")
    log(f"run done -> {root}")
    print(root)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "audit":
        audit()
    elif cmd == "run":
        run()
    else:
        raise SystemExit("usage: run_e0R_qc_split.py audit|run")
