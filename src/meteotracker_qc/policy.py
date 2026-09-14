from __future__ import annotations

import pandas as pd

PROFILE_ORDER = ["permissive", "recommended", "restrictive"]
_EXCLUDE_ACTIONS = {"EXCLUDE_RECOMMENDED", "EXCLUDE_RESTRICTIVE", "EXCLUDE_ALL_SCIENTIFIC"}


def _excludes_at_profile(action: str, profile_name: str) -> bool:
    if action == "EXCLUDE_ALL_SCIENTIFIC":
        return True
    if action == "EXCLUDE_RECOMMENDED":
        return profile_name in ("recommended", "restrictive")
    if action == "EXCLUDE_RESTRICTIVE":
        return profile_name == "restrictive"
    return False  # INFO_ONLY, WARNING_ONLY, SEGMENT_BREAK, NOT_APPLICABLE


def _reason_strings(df: pd.DataFrame, flags: list[str]) -> pd.Series:
    if not flags:
        return pd.Series("", index=df.index)
    sub = pd.DataFrame({f: df[f].fillna(False).astype(bool) for f in sorted(flags)}, index=df.index)
    return sub.apply(lambda row: ";".join(row.index[row.to_numpy()]), axis=1)


def apply_flag_policy(df: pd.DataFrame, policy_df: pd.DataFrame, own_profile_name: str) -> dict[str, pd.Series]:
    """Apply config/flag_policy.csv's flag -> action mapping to an
    already-QC-flagged frame.

    Produces, for all three profiles, `qc_severity_<p>`,
    `qc_exclusion_reasons_<p>`, `keep_<p>`; plus the run's-own-profile
    aliases `qc_severity`, `qc_exclusion_reasons`, `qc_reason_count`,
    `qc_primary_reason`, `qc_bitmask`, `qc_reasons` (legacy name),
    `qc_warning_count`, `qc_warning_reasons`, and the legacy `keep_strict`
    is *not* produced here (still computed by the caller from the
    `filtering.*` budget, see pipeline.py).

    Important caveat: permissive/recommended/restrictive differ in this
    codebase in TWO ways -- (1) which flags are True at all, since their
    underlying thresholds (e.g. `gps.gps_jump_distance_m`) differ per
    profile's own YAML config, and (2) which *action* a True flag maps to
    (this table, shared across all three YAMLs). This function only
    re-applies dimension (2) to a single run's already-computed flag values;
    it cannot retroactively account for (1). `qc_severity_<profile>` /
    `keep_<profile>` are therefore a *policy-only projection*, not
    equivalent to actually re-running the pipeline with that profile's own
    config (which is what the separate `outputs/{permissive,recommended,
    restrictive}` output trees and `outputs/sensitivity/` already do, and
    remain the authoritative source for true cross-profile comparison).
    """
    if own_profile_name not in PROFILE_ORDER:
        raise ValueError(f"Unknown point-QC profile: {own_profile_name}")
    required = {"flag_name", "action"}
    if not required <= set(policy_df.columns) or policy_df.empty:
        raise ValueError("A non-empty flag policy with flag_name and action is required")
    allowed = _EXCLUDE_ACTIONS | {"INFO_ONLY", "WARNING_ONLY", "SEGMENT_BREAK", "NOT_APPLICABLE"}
    if policy_df["flag_name"].isna().any() or not policy_df["flag_name"].is_unique or not set(policy_df["action"]) <= allowed:
        raise ValueError("Invalid or duplicated flag policy entries")
    eligible = policy_df[policy_df["action"] != "NOT_APPLICABLE"]
    action_by_flag = dict(zip(eligible["flag_name"], eligible["action"]))
    flags_present = [f for f in action_by_flag if f in df.columns]

    results: dict[str, pd.Series] = {}
    for profile_name in PROFILE_ORDER:
        excluding_flags = [f for f in flags_present if _excludes_at_profile(action_by_flag[f], profile_name)]
        if excluding_flags:
            active = pd.DataFrame({f: df[f].fillna(False).astype(bool) for f in excluding_flags}, index=df.index)
            severity = active.sum(axis=1).astype(int)
        else:
            severity = pd.Series(0, index=df.index, dtype=int)
        results[f"qc_severity_{profile_name}"] = severity
        results[f"qc_exclusion_reasons_{profile_name}"] = _reason_strings(df, excluding_flags)
        results[f"keep_{profile_name}"] = severity == 0

    own_excluding = [f for f in flags_present if _excludes_at_profile(action_by_flag[f], own_profile_name)]
    warning_flags = [
        f for f in flags_present
        if action_by_flag[f] == "WARNING_ONLY" or (f in action_by_flag and action_by_flag[f] in _EXCLUDE_ACTIONS and f not in own_excluding)
    ]
    if warning_flags:
        active_w = pd.DataFrame({f: df[f].fillna(False).astype(bool) for f in warning_flags}, index=df.index)
        results["qc_warning_count"] = active_w.sum(axis=1).astype(int)
    else:
        results["qc_warning_count"] = pd.Series(0, index=df.index, dtype=int)
    results["qc_warning_reasons"] = _reason_strings(df, warning_flags)

    results["qc_severity"] = results[f"qc_severity_{own_profile_name}"]
    results["qc_exclusion_reasons"] = results[f"qc_exclusion_reasons_{own_profile_name}"]
    results["qc_reason_count"] = results["qc_severity"]
    results["qc_primary_reason"] = results["qc_exclusion_reasons"].str.split(";").str[0].replace("", pd.NA)
    results["qc_bitmask"] = results["qc_severity"]
    results["qc_reasons"] = results["qc_exclusion_reasons"]
    return results
