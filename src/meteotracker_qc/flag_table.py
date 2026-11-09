"""Long-form QC flag table writer (E0 schema contract).

Maps per-row boolean ``qc_*`` columns (and optional file-level DUP_* codes
from the campaign manifest) into a separate long-form flag table. Never
deletes or mutates scientific rows in the session frame: flags are additive
records only (``flags_never_delete`` / ``keep_raw``).

Contract: ``e0/qc_flag_schema_E0_v0.1.yaml``.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from .policy import _excludes_at_profile

ROME = ZoneInfo("Europe/Rome")

RECORD_COLUMNS = [
    "flag_id",
    "canonical_campaign_id",
    "source_file",
    "source_row",
    "observation_id",
    "flag_code",
    "reason",
    "rule_id",
    "qc_profile",
    "threshold",
    "value_observed",
    "severity",
    "reversible",
    "applied_by",
    "applied_at",
    "code_commit",
    "config_fingerprint",
]

# Italian human-readable reasons for known codes (schema reuses detector names).
_REASON_IT: dict[str, str] = {
    "DUP_BYTE_IDENTICAL": "File duplicato byte-identico escluso dall'analisi (keep_raw=true).",
    "DUP_REDUCED_REEXPORT": "File re-export a colonne ridotte escluso dall'analisi (keep_raw=true).",
    "qc_coord_missing": "Latitudine o longitudine mancante.",
    "qc_coord_outside_aoi": "Coordinate fuori dal poligono AOI E0 (Comune di Bologna).",
    "qc_coord_repeated": "Coordinate ripetute entro la soglia di tolleranza.",
    "qc_gps_jump": "Salto GPS oltre soglia distanza/dt.",
    "qc_isolated_position_outlier": "Outlier di posizione isolato (detour eccessivo).",
    "qc_gps_freeze": "Possibile freeze GPS (ripetizione + evidenza di bassa velocità).",
    "qc_off_network_possible": "Possibile posizione fuori rete (informativo).",
    "qc_unrealistic_speed": "Velocità GPS irrealistica.",
    "qc_unrealistic_acceleration": "Accelerazione GPS irrealistica.",
    "qc_speed_disagreement": "Disaccordo velocità dispositivo / GPS.",
    "qc_low_speed_device": "Bassa velocità dispositivo (ventilazione).",
    "qc_low_ventilation_possible": "Possibile bassa ventilazione del sensore.",
    "qc_stationary": "Punto stazionario (coordinate ripetute e velocità basse).",
    "qc_post_stop_recovery": "Recupero post-sosta.",
    "qc_time_parse": "Timestamp non interpretabile.",
    "qc_time_duplicate": "Timestamp duplicato.",
    "qc_time_order": "Ordine temporale non monotono.",
    "qc_time_nonpositive_dt": "dt non positivo.",
    "qc_sampling_gap_short": "Gap di campionamento breve.",
    "qc_sampling_gap_long": "Gap di campionamento lungo (rottura segmento).",
    "qc_segment_restart_recovery": "Recupero dopo riavvio segmento.",
    "qc_sensor_stabilization": "Finestra di stabilizzazione / warm-up sensore.",
    "qc_temp_impossible": "Temperatura fuori limiti fisici.",
    "qc_temp_spike": "Spike termico.",
    "qc_temp_rate_anomaly": "Anomalia di rate termico.",
    "qc_sensor_plateau_possible": "Possibile plateau del sensore.",
    "qc_humidity_impossible": "Umidità fuori limiti fisici.",
    "qc_pressure_impossible": "Pressione fuori limiti fisici.",
    "qc_duplicate_timestamp": "Timestamp duplicato (stesso istante della riga adiacente).",
    "qc_duplicate_record": "Record duplicato: stesso timestamp e contenuto identico alla riga precedente.",
    "qc_nonmonotonic_timestamp": "Timestamp all'indietro (ordine non monotono).",
    "qc_spatial_jump": "Salto spaziale (salto GPS o outlier di posizione isolato).",
    "qc_temp_isolated_spike": "Spike termico isolato.",
    "qc_possible_gps_freeze": "Possibile freeze GPS (segnale ampio, diagnostico).",
    "qc_low_speed_gps": "Bassa velocità GPS (ventilazione).",
    "qc_stop_event": "Sosta significativa rilevata.",
}

_DUP_TYPE_TO_CODE = {
    "byte-identical": "DUP_BYTE_IDENTICAL",
    "byte_identical": "DUP_BYTE_IDENTICAL",
    "reduced-column re-export": "DUP_REDUCED_REEXPORT",
    "reduced_column_reexport": "DUP_REDUCED_REEXPORT",
}


def default_schema_path() -> Path:
    """Prefer project-tree e0 schema; fall back to CWD-relative path."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "e0" / "qc_flag_schema_E0_v0.1.yaml",
        Path.cwd() / "e0" / "qc_flag_schema_E0_v0.1.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def load_flag_schema(schema_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(schema_path) if schema_path is not None else default_schema_path()
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict) or "flag_codes" not in payload:
        raise ValueError(f"Invalid E0 flag schema at {path}")
    return payload


def severity_lookup(schema: dict[str, Any], profile: str = "recommended") -> dict[str, str]:
    """Default severities are those listed on each flag_code (recommended).

    Profile override: if ``schema['profile_severity_overrides'][profile][code]``
    exists it wins; otherwise the per-code ``severity`` field is used.
    """
    overrides = (schema.get("profile_severity_overrides") or {}).get(profile) or {}
    out: dict[str, str] = {}
    for entry in schema.get("flag_codes") or []:
        code = entry.get("code")
        if not code:
            continue
        out[code] = str(overrides.get(code, entry.get("severity", "warn")))
    return out


_POLICY_ACTIONS_EMITTED = {
    "EXCLUDE_ALL_SCIENTIFIC", "EXCLUDE_RECOMMENDED", "EXCLUDE_RESTRICTIVE", "WARNING_ONLY", "INFO_ONLY", "SEGMENT_BREAK",
}


def severity_from_policy(policy_df: pd.DataFrame, profile: str) -> dict[str, str]:
    """Flag-table severity DERIVED from the flag policy for one profile (single source of truth, E0-QC-R R6).

    exclude  <- the action excludes at `profile` (exactly the rule apply_flag_policy uses for keep_<profile>)
    warn     <- WARNING_ONLY, or an EXCLUDE_* action that does not exclude at `profile`
    info     <- INFO_ONLY, SEGMENT_BREAK
    NOT_APPLICABLE rows (internal signals / legacy aliases) are not emitted.
    """
    out: dict[str, str] = {}
    for code, action in zip(policy_df["flag_name"], policy_df["action"]):
        action = str(action)
        if action not in _POLICY_ACTIONS_EMITTED:
            continue
        if _excludes_at_profile(action, profile):
            out[str(code)] = "exclude"
        elif action.startswith("EXCLUDE_") or action == "WARNING_ONLY":
            out[str(code)] = "warn"
        else:
            out[str(code)] = "info"
    return out


def resolve_severities(schema: dict[str, Any], profile: str, policy_df: pd.DataFrame | None) -> dict[str, str]:
    """Severities for a flag-table build. Schema v0.1 (no `severity_source`): static per-code severities.
    Schema v0.2+ (`severity_source: policy`): derived from `policy_df` for `profile`; file-level codes keep the
    schema severity; every non-file schema code must exist in the policy (no silent drift between the two)."""
    if str(schema.get("severity_source", "schema")) != "policy":
        return severity_lookup(schema, profile)
    if policy_df is None:
        raise ValueError("schema has severity_source=policy but no policy_df was supplied")
    derived = severity_from_policy(policy_df, profile)
    policy_codes = set(policy_df["flag_name"].astype(str))
    missing = []
    for entry in schema.get("flag_codes") or []:
        code = entry.get("code")
        if not code:
            continue
        if entry.get("level") == "file":
            derived[code] = str(entry.get("severity", "exclude"))
        elif code not in policy_codes:
            missing.append(code)
    if missing:
        raise ValueError(f"schema codes absent from the flag policy: {sorted(missing)}")
    aliases = set((schema.get("legacy_aliases") or {}).keys())
    leaked = sorted(aliases & set(derived))
    if leaked:
        raise ValueError(f"legacy alias codes must be NOT_APPLICABLE in the policy, found emitted: {leaked}")
    return derived


def rule_meta_lookup(schema: dict[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for entry in schema.get("flag_codes") or []:
        code = entry.get("code")
        if not code:
            continue
        out[code] = {
            "rule_id": str(entry.get("rule") or entry.get("rule_id") or ""),
            "threshold": str(entry.get("threshold_rec") or entry.get("threshold") or ""),
            "reason": _REASON_IT.get(code, str(entry.get("note") or code)),
        }
    return out


def _observation_id(file_sha256: str | None, source_row: int) -> str:
    digest = (file_sha256 or "unknown").strip()
    prefix = digest[:12] if len(digest) >= 12 else digest.ljust(12, "0")
    return f"{prefix}:{int(source_row)}"


def _truthy_mask(series: pd.Series) -> pd.Series:
    """True only for explicit True; NA/False stay inactive (flags-never-delete)."""
    return series.fillna(False).astype(bool)


def build_flag_table(
    df: pd.DataFrame,
    *,
    canonical_campaign_id: str,
    source_file: str,
    file_sha256: str | None = None,
    qc_profile: str = "recommended",
    schema: dict[str, Any] | None = None,
    schema_path: str | Path | None = None,
    config_fingerprint: str = "TBD",
    code_commit: str = "TBD",
    applied_by: str = "meteotracker_qc.flag_table",
    applied_at: datetime | None = None,
    flag_id_start: int = 1,
    duplicate_type: str | None = None,
    include_file_level_duplicates: bool = True,
    extra_flag_columns: Iterable[str] | None = None,
    policy_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Emit long-form flag rows for True ``qc_*`` columns in ``df``.

    Parameters
    ----------
    df:
        Session / point frame after QC detectors (must not be row-deleted).
    duplicate_type:
        Manifest ``duplicate_type`` when applicable; emits one file-level DUP_*
        row (``source_row`` = -1) if ``include_file_level_duplicates``.
    """
    schema_payload = schema if schema is not None else load_flag_schema(schema_path)
    severities = resolve_severities(schema_payload, qc_profile, policy_df)
    meta = rule_meta_lookup(schema_payload)
    when = applied_at or datetime.now(ROME)
    if when.tzinfo is None:
        when = when.replace(tzinfo=ROME)
    else:
        when = when.astimezone(ROME)
    applied_at_iso = when.isoformat()

    known_codes = set(severities)
    qc_cols = [c for c in df.columns if c.startswith("qc_") and c in known_codes]
    if extra_flag_columns:
        for col in extra_flag_columns:
            if col in df.columns and col not in qc_cols:
                qc_cols.append(col)

    records: list[dict[str, Any]] = []
    next_id = int(flag_id_start)

    if include_file_level_duplicates and duplicate_type:
        code = _DUP_TYPE_TO_CODE.get(str(duplicate_type).strip().lower()) or _DUP_TYPE_TO_CODE.get(
            str(duplicate_type).strip()
        )
        # also try exact keys
        if code is None:
            code = _DUP_TYPE_TO_CODE.get(str(duplicate_type).strip())
        if code is None:
            # direct match against schema codes
            raw = str(duplicate_type).strip()
            if raw in known_codes:
                code = raw
            elif raw.upper().replace("-", "_").replace(" ", "_") in {
                "DUP_BYTE_IDENTICAL",
                "DUP_REDUCED_REEXPORT",
            }:
                code = raw.upper().replace("-", "_").replace(" ", "_")
        if code in known_codes:
            info = meta.get(code, {})
            records.append(
                {
                    "flag_id": f"E0F-{next_id:06d}",
                    "canonical_campaign_id": canonical_campaign_id,
                    "source_file": source_file,
                    "source_row": -1,
                    "observation_id": _observation_id(file_sha256, -1),
                    "flag_code": code,
                    "reason": info.get("reason") or _REASON_IT.get(code, code),
                    "rule_id": info.get("rule_id") or "manifest.duplicate_type",
                    "qc_profile": qc_profile,
                    "threshold": info.get("threshold") or "",
                    "value_observed": str(duplicate_type),
                    "severity": severities.get(code, "exclude"),
                    "reversible": True,
                    "applied_by": applied_by,
                    "applied_at": applied_at_iso,
                    "code_commit": code_commit,
                    "config_fingerprint": config_fingerprint,
                }
            )
            next_id += 1

    if len(df) == 0 and not records:
        return pd.DataFrame(columns=RECORD_COLUMNS)

    # Prefer an explicit source_row column; else use positional index 0..n-1
    if "source_row" in df.columns:
        source_rows = pd.to_numeric(df["source_row"], errors="coerce")
    else:
        source_rows = pd.Series(range(len(df)), index=df.index, dtype=int)

    for col in qc_cols:
        mask = _truthy_mask(df[col])
        if not mask.any():
            continue
        info = meta.get(col, {})
        severity = severities.get(col, "warn")
        reason = info.get("reason") or _REASON_IT.get(col, col)
        rule_id = info.get("rule_id") or ""
        threshold = info.get("threshold") or ""
        for idx in df.index[mask]:
            row_i = source_rows.loc[idx]
            if pd.isna(row_i):
                row_i = int(df.index.get_loc(idx)) if not isinstance(idx, int) else int(idx)
            row_i = int(row_i)
            value_observed = "True"
            records.append(
                {
                    "flag_id": f"E0F-{next_id:06d}",
                    "canonical_campaign_id": canonical_campaign_id,
                    "source_file": source_file,
                    "source_row": row_i,
                    "observation_id": _observation_id(file_sha256, row_i),
                    "flag_code": col,
                    "reason": reason,
                    "rule_id": rule_id,
                    "qc_profile": qc_profile,
                    "threshold": threshold,
                    "value_observed": value_observed,
                    "severity": severity,
                    "reversible": True,
                    "applied_by": applied_by,
                    "applied_at": applied_at_iso,
                    "code_commit": code_commit,
                    "config_fingerprint": config_fingerprint,
                }
            )
            next_id += 1

    return pd.DataFrame.from_records(records, columns=RECORD_COLUMNS)


def write_flag_table(flag_df: pd.DataFrame, output_path: str | Path) -> Path:
    """Write CSV (and create parents). Does not touch session parquet/raw."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flag_df.to_csv(path, index=False)
    return path


def build_and_write_flag_table(
    df: pd.DataFrame,
    output_path: str | Path,
    **kwargs: Any,
) -> pd.DataFrame:
    """Convenience wrapper callable from pipeline / session_qc without a full re-run."""
    table = build_flag_table(df, **kwargs)
    write_flag_table(table, output_path)
    return table
