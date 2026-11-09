"""Audit helpers: flag_table_E0 severities (schema yaml) vs pipeline keep_<profile> (flag_policy.csv).

Pure functions on pandas; no I/O except the line-number readers. Read-only by design.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

STATE_ORDER = ("exclude", "warn_only", "ok")
NON_FLAG_QC_COLS = {
    "qc_severity", "qc_exclusion_reasons", "qc_reason_count", "qc_primary_reason", "qc_bitmask", "qc_reasons",
    "qc_warning_count", "qc_warning_reasons", "qc_time_parse_status",
}


def is_flag_column(c: str) -> bool:
    return c.startswith("qc_") and c not in NON_FLAG_QC_COLS and not c.startswith(
        ("qc_severity_", "qc_exclusion_reasons_"))


def point_flag_state(ft: pd.DataFrame, keys=("canonical_campaign_id", "source_row")) -> pd.DataFrame:
    """Per point: 'exclude' if any exclude-severity flag row, 'warn_only' if only warn/info rows, else absent.
    Also returns the ';'-joined exclude codes and warn codes. File-level rows (source_row < 0) are ignored."""
    k = list(keys)
    f = ft[ft["source_row"] >= 0]
    sev = f["severity"].astype(str)
    ex = f[sev == "exclude"].groupby(k)["flag_code"].agg(lambda s: ";".join(sorted(set(s)))).rename("ft_exclude_codes")
    wn = f[sev != "exclude"].groupby(k)["flag_code"].agg(lambda s: ";".join(sorted(set(s)))).rename("ft_warn_codes")
    out = pd.concat([ex, wn], axis=1).reset_index()
    out["ft_state"] = np.where(out["ft_exclude_codes"].notna(), "exclude", "warn_only")
    return out


def attach_state(points: pd.DataFrame, state: pd.DataFrame, keys=("canonical_campaign_id", "source_row")) -> pd.DataFrame:
    d = points.merge(state, on=list(keys), how="left", validate="one_to_one")
    d["ft_state"] = d["ft_state"].fillna("ok")
    d["ft_exclude"] = d["ft_state"] == "exclude"
    return d


def confusion(d: pd.DataFrame, keep_col: str, by: str | None = None) -> pd.DataFrame:
    """Counts of ft_state (exclude/warn_only/ok) x keep_col (True/False), optionally per group."""
    grp = [by] if by else []
    t = d.groupby(grp + ["ft_state", keep_col]).size().rename("n").reset_index()
    t = t.rename(columns={keep_col: "pipeline_keep"})
    t["mask"] = keep_col
    tot = t.groupby(grp)["n"].transform("sum") if grp else t["n"].sum()
    t["share"] = t["n"] / tot
    return t


def agreement_summary(d: pd.DataFrame, keep_col: str) -> dict:
    keep = d[keep_col].astype(bool)
    ftx = d["ft_exclude"].astype(bool)
    n = len(d)
    return dict(mask=keep_col, n=n, agree_keep=int((keep & ~ftx).sum()), agree_drop=int((~keep & ftx).sum()),
                ft_only_drop=int((keep & ftx).sum()), pipeline_only_drop=int((~keep & ~ftx).sum()),
                agreement=float((keep == ~ftx).mean()) if n else np.nan,
                cohen_kappa=_kappa(~keep, ftx))


def _kappa(a: pd.Series, b: pd.Series) -> float:
    a = np.asarray(a, bool); b = np.asarray(b, bool)
    if len(a) == 0:
        return np.nan
    po = (a == b).mean()
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    return float((po - pe) / (1 - pe)) if pe < 1 else np.nan


def explode_codes(s: pd.Series) -> pd.DataFrame:
    """Series of ';'-joined codes (index = point index) -> long (idx, code, n_codes_on_point)."""
    s = s.fillna("").astype(str)
    lst = s.str.split(";").map(lambda v: [x for x in v if x])
    e = lst.explode().dropna()
    e = e[e != ""]
    out = pd.DataFrame({"idx": e.index, "code": e.values})
    out["n_codes_on_point"] = out["idx"].map(lst.map(len))
    return out


def per_code_disagreement(d: pd.DataFrame, keep_col: str, pipe_reason_col: str) -> pd.DataFrame:
    """Direction A (ft_only_drop): flag table excludes, pipeline keeps -> attributed to ft exclude codes.
    Direction B (pipeline_only_drop): pipeline drops, no ft exclude -> attributed to pipeline exclusion reasons.
    'sole' = the code is the only exclusionary code on that point (unique attribution)."""
    keep = d[keep_col].astype(bool)
    A = d[keep & d["ft_exclude"]]
    B = d[~keep & ~d["ft_exclude"]]
    rows = []
    ea = explode_codes(A["ft_exclude_codes"])
    allx = explode_codes(d.loc[d["ft_exclude"], "ft_exclude_codes"])
    for code, g in ea.groupby("code"):
        rows.append(dict(direction="ft_exclude_but_pipeline_keeps", code=code, n_points=len(g),
                         n_sole=int((g.n_codes_on_point == 1).sum()),
                         n_points_code_ft_exclude_total=int((allx.code == code).sum()),
                         share_of_direction=len(g) / max(len(A), 1)))
    eb = explode_codes(B[pipe_reason_col])
    for code, g in eb.groupby("code"):
        rows.append(dict(direction="pipeline_drops_but_no_ft_exclude", code=code, n_points=len(g),
                         n_sole=int((g.n_codes_on_point == 1).sum()), n_points_code_ft_exclude_total=0,
                         share_of_direction=len(g) / max(len(B), 1)))
    out = pd.DataFrame(rows)
    if len(out):
        out["mask"] = keep_col
        out["share_of_all_disagreement"] = out["n_points"] / max(len(A) + len(B), 1)
        out = out.sort_values(["direction", "n_points"], ascending=[True, False])
    return out


def rates_by(d: pd.DataFrame, by: str, keep_col: str = "keep_recommended", min_n: int = 1) -> pd.DataFrame:
    keep = d[keep_col].astype(bool)
    g = pd.DataFrame({by: d[by], "n": 1, "ft_only": keep & d["ft_exclude"], "pipe_only": ~keep & ~d["ft_exclude"],
                      "disagree": keep == d["ft_exclude"]}).groupby(by, dropna=False).sum()
    g = g[g["n"] >= min_n]
    for c in ("ft_only", "pipe_only", "disagree"):
        g[c + "_rate"] = g[c] / g["n"]
    return g.reset_index().sort_values("disagree_rate", ascending=False)


# ------------------------------------------------------------------------------------------------
def read_schema_lines(path: str | Path) -> dict[str, tuple[str, int]]:
    """code -> (severity, line number) from the E0 schema yaml (flow-style one-line entries)."""
    out = {}
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        m = re.search(r"code:\s*([A-Za-z0-9_]+).*?severity:\s*([a-z]+)", line)
        if m:
            out[m.group(1)] = (m.group(2), i)
    return out


def read_policy_lines(path: str | Path) -> dict[str, tuple[str, int]]:
    """flag_name -> (action, line number) from flag_policy.csv (1-based file lines, header = line 1)."""
    import csv
    out = {}
    with open(path, encoding="utf-8", newline="") as fh:
        rdr = csv.reader(fh)
        next(rdr)
        for row in rdr:
            line = rdr.line_num
            if row:
                out[row[0]] = (row[1], line)
    return out


def policy_excludes(action: str | None, profile: str) -> bool:
    if action == "EXCLUDE_ALL_SCIENTIFIC":
        return True
    if action == "EXCLUDE_RECOMMENDED":
        return profile in ("recommended", "restrictive")
    if action == "EXCLUDE_RESTRICTIVE":
        return profile == "restrictive"
    return False


def mapping_table(schema: dict, policy: dict, flag_counts: dict, ft_counts: dict) -> pd.DataFrame:
    codes = sorted(set(schema) | set(policy) | set(flag_counts))
    rows = []
    for c in codes:
        sev, sl = schema.get(c, (None, None))
        act, pl = policy.get(c, (None, None))
        rec_ex = policy_excludes(act, "recommended")
        ft_ex = sev == "exclude"
        if sev is None and act is None:
            kind = "in_data_only"
        elif sev is None:
            kind = "policy_only_not_emitted_to_flag_table" if policy_excludes(act, "restrictive") else "policy_only_nonexcluding"
        elif act is None:
            kind = "schema_only_no_policy_row" + ("(ft_exclude)" if ft_ex else "")
        elif ft_ex and not rec_ex:
            kind = "MISMATCH_schema_exclude_policy_keeps_recommended"
        elif rec_ex and not ft_ex:
            kind = "MISMATCH_policy_excludes_recommended_schema_not_exclude"
        else:
            kind = "consistent"
        rows.append(dict(code=c, schema_severity=sev, schema_line=sl, policy_action=act, policy_line=pl,
                         policy_excl_permissive=policy_excludes(act, "permissive"), policy_excl_recommended=rec_ex,
                         policy_excl_restrictive=policy_excludes(act, "restrictive"), ft_exclude=ft_ex,
                         n_points_flag_true=flag_counts.get(c), n_points_in_flag_table=ft_counts.get(c), status=kind))
    return pd.DataFrame(rows)
