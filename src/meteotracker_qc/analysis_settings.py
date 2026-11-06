"""Versioned, opt-in runtime controls. Official configurations are never edited."""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import yaml

SCHEMA_VERSION = 1
PROFILES = ("recommended", "permissive", "restrictive")

# Controls describe existing detectors, including their aliases, not new flags.
GROUPS = {
    "schema": ("Struttura / schema", "Normalizzazione necessaria al motore; sempre attiva.", (), ()),
    "timestamp": ("Timestamp", "Segnalazione timestamp non interpretabili; parsing sempre necessario.", ("qc_time_parse",), ()),
    "duplicates": ("Timestamp duplicati", "Segnala tutte le righe con timestamp duplicato.", ("qc_duplicate_timestamp", "qc_time_duplicate"), ()),
    "monotonicity": ("Monotonicità", "Ordine temporale; le discontinuità restano confini strutturali.", ("qc_nonmonotonic_timestamp", "qc_time_order"), ()),
    "gaps": ("Gap temporali", "Gap rispetto alla cadenza; segmentazione strutturale sempre attiva.", ("qc_sampling_gap_short", "qc_sampling_gap_long", "qc_time_gap"), ("time",)),
    "coordinates": ("Coordinate mancanti", "Latitudine o longitudine mancanti.", ("qc_coord_missing",), ()),
    "invalid_coordinates": ("Coordinate non valide / AOI", "Punto fuori dal poligono AOI E0 (Comune di Bologna).", ("qc_coord_outside_aoi",), ("gps.aoi_geojson",)),
    "gps_jumps": ("Salti GPS", "Salti e outlier isolati; unione nella policy senza doppio conteggio.", ("qc_gps_jump", "qc_isolated_position_outlier", "qc_spatial_jump"), ("gps.gps_jump_distance_m", "gps.gps_jump_dt_s", "gps.isolated_outlier_excess_m")),
    "gps_freeze": ("GPS freeze", "Ripetizione coordinate, freeze e stazionarietà.", ("qc_coord_repeated", "qc_gps_freeze", "qc_possible_gps_freeze", "qc_stationary"), ("gps.freeze_speed_threshold_kmh", "gps.coord_repeated_tolerance_m")),
    "speed": ("Velocità", "Velocità irrealistica e disaccordo dispositivo / GPS.", ("qc_unrealistic_speed", "qc_speed_disagreement"), ("gps.max_speed_kmh_absolute", "gps.speed_disagreement_abs_kmh", "gps.speed_disagreement_rel_fraction")),
    "acceleration": ("Accelerazione", "Accelerazione GPS assoluta.", ("qc_unrealistic_acceleration", "qc_impossible_acceleration"), ("gps.acceleration_ms2_abs",)),
    "distance": ("Distanza", "Metrica geodetica entro i segmenti, necessaria ai controlli GPS; nessun flag autonomo.", (), ()),
    "temperature": ("Temperatura / plausibilità", "Limiti fisici, spike, rate e plateau.", ("qc_temp_impossible", "qc_temp_isolated_spike", "qc_temp_spike", "qc_temp_rate_anomaly", "qc_sensor_plateau_possible"), ("physical_limits.temp_min_c", "physical_limits.temp_max_c", "thermal")),
    "humidity": ("Umidità / plausibilità", "Limiti fisici di umidità relativa.", ("qc_humidity_impossible",), ("physical_limits.humidity_min_pct", "physical_limits.humidity_max_pct")),
    "pressure": ("Pressione / plausibilità", "Limiti fisici di pressione.", ("qc_pressure_impossible",), ("physical_limits.pressure_min_mbar", "physical_limits.pressure_max_mbar")),
    "warmup": ("Stabilizzazione / warm-up", "Finestra iniziale e recupero dopo un gap.", ("qc_sensor_stabilization", "qc_segment_restart_recovery"), ("warmup", "ventilation.low_speed_threshold_kmh")),
    "ventilation": ("Ventilazione / soste", "Bassa ventilazione, soste e recupero.", ("qc_low_speed_device", "qc_low_speed_gps", "qc_low_ventilation_possible", "qc_stop_event", "qc_post_stop_recovery"), ("ventilation", "stops")),
    "derived": ("Variabili derivate", "Ricalcolo variabili termodinamiche.", (), ()),
    "completeness": ("Completezza", "Disponibilità campi canonici; metrica necessaria al Session QC.", (), ()),
    "suitability": ("Suitability", "Policy Session QC e idoneità per tipo di analisi; riferimento recommended.", (), ()),
}
MANDATORY = {"schema", "distance", "completeness"}
UNAVAILABLE = set()  # invalid_coordinates enabled in E0 step 3 (AOI wired)
DEFAULT_ACTIVE = tuple(k for k in GROUPS if k not in UNAVAILABLE)

# Explicit editing contract: units and admissible input ranges, not new defaults.
PARAMETERS = {
    "physical_limits.temp_min_c": ("°C", -100, 100), "physical_limits.temp_max_c": ("°C", -100, 100),
    "physical_limits.humidity_min_pct": ("%", 0, 100), "physical_limits.humidity_max_pct": ("%", 0, 100),
    "physical_limits.pressure_min_mbar": ("mbar", 100, 1500), "physical_limits.pressure_max_mbar": ("mbar", 100, 1500),
    "gps.max_speed_kmh_absolute": ("km/h", 1, 1000), "gps.gps_jump_distance_m": ("m", 0.1, 100000),
    "gps.gps_jump_dt_s": ("s", 0.01, 3600), "gps.acceleration_ms2_abs": ("m/s²", 0.01, 1000),
    "gps.freeze_speed_threshold_kmh": ("km/h", 0, 100), "gps.coord_repeated_tolerance_m": ("m", 0, 1000),
    "gps.isolated_outlier_excess_m": ("m", 0, 100000), "gps.speed_disagreement_abs_kmh": ("km/h", 0, 1000),
    "gps.speed_disagreement_rel_fraction": ("fraction", 0, 10),
    "warmup.window_size": ("rows", 1, 10000), "warmup.window_size_s": ("s", 0.01, 3600),
    "warmup.slope_threshold_c_per_s": ("°C/s", 0, 100), "warmup.min_stable_seconds": ("s", 1, 7200),
    "warmup.max_window_s": ("s", 1, 86400), "warmup.min_ventilated_duration_s": ("s", 0, 7200),
    "time.min_samples_for_cadence_estimate": ("rows", 1, 10000), "time.fallback_expected_dt_s": ("s", 0.01, 3600),
    "time.outlier_multiplier": ("×", 1, 1000), "time.gap_short_multiplier": ("×", 1, 1000),
    "time.gap_long_multiplier": ("×", 1, 10000), "time.gap_absolute_floor_s": ("s", 0.01, 86400),
    "thermal.spike_window_s": ("s", 0.01, 3600), "thermal.spike_mad_multiplier": ("×", 0, 100),
    "thermal.spike_floor_c": ("°C", 0, 100), "thermal.rate_anomaly_threshold_c_per_s": ("°C/s", 0, 100),
    "thermal.rate_anomaly_persistence_s": ("s", 0.01, 86400), "thermal.plateau_std_epsilon_c": ("°C", 0, 100),
    "thermal.plateau_min_duration_s": ("s", 0.01, 86400),
    "ventilation.low_speed_threshold_kmh": ("km/h", 0, 300), "ventilation.day_start_local_hour": ("hour", 0, 24),
    "ventilation.day_end_local_hour": ("hour", 0, 24), "stops.min_significant_stop_s": ("s", 0, 7200),
    "stops.recovery_min_duration_s": ("s", 0, 7200),
    "filtering.strict_keep_threshold": ("count", 0, 100), "filtering.relaxed_keep_threshold": ("count", 0, 100),
}


def enabled(config, group):
    return group in (config or {}).get("analysis_controls", DEFAULT_ACTIVE)


def settings_fingerprint(config_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in [*(f"qc_{p}.yaml" for p in PROFILES), "flag_policy.csv", "session_qc_policy.csv", "session_suitability_policy.csv"]:
        digest.update(name.encode())
        digest.update((config_dir / name).read_bytes())
    digest.update(json.dumps([SCHEMA_VERSION, GROUPS, PARAMETERS], sort_keys=True).encode())
    return digest.hexdigest()


def validate_settings(config_dir, profile="recommended", active_controls=None, overrides=None):
    if profile not in PROFILES:
        raise ValueError(f"Profilo sconosciuto: {profile}")
    if active_controls is not None and (not isinstance(active_controls, (list, tuple)) or any(not isinstance(g, str) for g in active_controls)):
        raise ValueError("Controlli attivi: richiesta una lista di identificativi")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("Soglie modificate: richiesto un oggetto parametro/valore")
    active = list(DEFAULT_ACTIVE if active_controls is None else active_controls)
    if len(active) != len(set(active)) or set(active) - set(DEFAULT_ACTIVE) or not MANDATORY <= set(active):
        raise ValueError("Controlli sconosciuti, duplicati, non disponibili o dipendenze obbligatorie disattivate")
    config = yaml.safe_load((Path(config_dir) / f"qc_{profile}.yaml").read_text(encoding="utf-8"))
    original = deepcopy(config)
    changes = {}
    for key, item in (overrides or {}).items():
        if key not in PARAMETERS:
            raise ValueError(f"Parametro non modificabile: {key}")
        unit, lower, upper = PARAMETERS[key]
        if isinstance(item, dict):
            if set(item) != {"value", "unit"} or item["unit"] != unit:
                raise ValueError(f"Unità non valida per {key}; richiesta {unit}")
            value = item["value"]
        else:
            value = item
        section, name = key.split(".")
        default = original[section][name]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f"{key}: richiesto numero finito in [{lower}, {upper}] {unit}")
        if isinstance(default, int) and not float(value).is_integer():
            raise ValueError(f"{key}: richiesto intero")
        value = int(value) if isinstance(default, int) else float(value)
        config[section][name] = value
        if value != default:
            changes[key] = {"from": default, "value": value, "unit": unit}
    limits = config["physical_limits"]
    for stem, suffix in (("temp", "c"), ("humidity", "pct"), ("pressure", "mbar")):
        if limits[f"{stem}_min_{suffix}"] >= limits[f"{stem}_max_{suffix}"]:
            raise ValueError(f"{stem}: minimo deve essere inferiore al massimo")
    if config["time"]["gap_short_multiplier"] > config["time"]["gap_long_multiplier"]:
        raise ValueError("Gap breve deve essere <= gap lungo")
    if config["ventilation"]["day_start_local_hour"] >= config["ventilation"]["day_end_local_hour"]:
        raise ValueError("Ora inizio giorno deve precedere ora fine")
    if config["filtering"]["strict_keep_threshold"] > config["filtering"]["relaxed_keep_threshold"]:
        raise ValueError("Budget strict deve essere <= relaxed")
    config["analysis_controls"] = active
    return {"schema_version": SCHEMA_VERSION, "origin_profile": profile, "active_controls": active,
            "disabled_controls": [g for g in DEFAULT_ACTIVE if g not in active], "differences": changes,
            "overrides": {k: {"value": v["value"], "unit": v["unit"]} for k, v in changes.items()},
            "config": config, "config_fingerprint": settings_fingerprint(Path(config_dir))}


def describe_settings(config_dir, profile="recommended", active_controls=None, overrides=None):
    settings = validate_settings(config_dir, profile, active_controls, overrides)
    flat = {f"{section}.{key}": value for section, values in settings["config"].items() if isinstance(values, dict) for key, value in values.items()}
    groups = []
    for key, (label, description, flags, prefixes) in GROUPS.items():
        parameters = {k: {"value": v, "unit": PARAMETERS[k][0], "min": PARAMETERS[k][1], "max": PARAMETERS[k][2]}
                      for k, v in flat.items() if k in PARAMETERS and any(k == p or k.startswith(p + ".") for p in prefixes)}
        source = f"config/qc_{profile}.yaml; config/flag_policy.csv"
        if key in {"schema", "completeness"}:
            source = "src/meteotracker_qc/schema.py; src/meteotracker_qc/session_qc/metrics.py"
        elif key == "derived":
            source = "src/meteotracker_qc/derived_variables.py"
        elif key == "distance":
            source = "src/meteotracker_qc/gps_qc.py (metrica geodetica)"
        if key == "suitability":
            source = "config/session_qc_policy.csv; config/session_suitability_policy.csv (recommended_session)"
        groups.append({"id": key, "label": label, "description": description, "flags": list(flags),
                       "active": key in settings["active_controls"], "editable": key not in MANDATORY | UNAVAILABLE,
                       "available": key not in UNAVAILABLE, "parameters": parameters, "source": source, "profile": profile})
    settings["groups"] = groups
    settings["parameters"] = {k: {"value": flat[k], "unit": v[0], "min": v[1], "max": v[2]} for k, v in PARAMETERS.items()}
    settings["session_rules"] = []
    for filename in ("session_qc_policy.csv", "session_suitability_policy.csv"):
        with (Path(config_dir) / filename).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("profile", "recommended_session") == "recommended_session" and row.get("enabled", "true").lower() in {"true", "1", "yes"}:
                    settings["session_rules"].append({**row, "source": f"config/{filename}"})
    return settings


def preset_payload(settings, name, description=""):
    if not name.strip():
        raise ValueError("Nome preset richiesto")
    return {k: settings[k] for k in ("schema_version", "origin_profile", "active_controls", "overrides", "config_fingerprint")} | {
        "name": name.strip(), "description": description, "date": datetime.now(timezone.utc).isoformat()}
