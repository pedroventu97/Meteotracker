"""One-off generator for config/repeated_location_matching.csv. Run manually;
not part of the pipeline. Written via csv.writer to avoid hand-typed CSV
quoting bugs (recurring issue in this project when text fields contain
commas)."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COLUMNS = [
    "profile_name", "spatial_radius_m", "maximum_group_diameter_m",
    "minimum_temporal_separation_s", "visit_merge_gap_s", "minimum_points_per_visit",
    "minimum_groups_for_model", "minimum_time_windows", "direction_handling",
    "qc_profile", "evidence_source", "rationale",
]

THESIS_NOTE = (
    "La tesi giustifica solo il principio dei ripassaggi come evidenza di variazione "
    "temporale, non un raggio metrico o una separazione temporale specifici -- nessuna "
    "cifra di accuratezza GPS in metri e' documentata nell'audit (grep verificato su "
    "reports/targeted_qc_audit.md), quindi mai evidence_source=thesis_documented o "
    "audit_observed per questi parametri."
)

ROWS = [
    {
        "profile_name": "temporal_permissive", "spatial_radius_m": 20.0, "maximum_group_diameter_m": 20.0,
        "minimum_temporal_separation_s": 180, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 3, "minimum_time_windows": 2, "direction_handling": "include_all",
        "qc_profile": "temporal_permissive", "evidence_source": "engineering_default",
        "rationale": f"Profilo operativo piu' permissivo (sezione C/M). Raggio ampio, separazione minima piu' bassa, requisiti minimi di modello bassi. {THESIS_NOTE}",
    },
    {
        "profile_name": "temporal_recommended", "spatial_radius_m": 15.0, "maximum_group_diameter_m": 15.0,
        "minimum_temporal_separation_s": 300, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "data_distribution",
        "rationale": (
            "Profilo operativo primario (analogo a recommended_session in Fase 3), configurazione-ancora della "
            "sensitivity (sezione M). minimum_points_per_visit corretto da 2 a 1 dopo la prima run reale sulle 34 "
            "campagne: sulle 18666 visite reali osservate, la mediana e' 1 punto/visita e il 57.2% delle visite ha "
            "esattamente 1 punto (un passaggio veloce in bici copre un raggio di 15m in pochi secondi, spesso con "
            "una sola lettura GPS+temperatura al suo interno) -- richiedere >=2 punti escludeva la maggioranza dei "
            "ripassaggi reali come LOW_POINT_COUNT, cascata che a sua volta escludeva il 94% delle coppie via "
            "EXCLUDED_LOW_VISIT_QUALITY. Una singola lettura robusta durante un passaggio veloce non e' meno "
            "affidabile di due letture a un secondo di distanza nello stesso punto. Il profilo conservative "
            "mantiene la soglia piu' severa (3, ~23imo percentile) come livello intenzionalmente piu' cauto."
        ) + f" {THESIS_NOTE}",
    },
    {
        "profile_name": "temporal_conservative", "spatial_radius_m": 10.0, "maximum_group_diameter_m": 10.0,
        "minimum_temporal_separation_s": 600, "visit_merge_gap_s": 30, "minimum_points_per_visit": 3,
        "minimum_groups_for_model": 8, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_conservative", "evidence_source": "engineering_default",
        "rationale": f"Profilo piu' severo: raggio stretto, separazione ampia, richiede >=8 gruppi validi (pavimento minimo per un cluster bootstrap non degenere, sezione G). {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_radius_5m", "spatial_radius_m": 5.0, "maximum_group_diameter_m": 5.0,
        "minimum_temporal_separation_s": 300, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Sweep raggio spaziale (sezione M), tutto il resto ancorato a temporal_recommended. Usato solo da sensitivity.py, mai come profilo operativo. {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_radius_10m", "spatial_radius_m": 10.0, "maximum_group_diameter_m": 10.0,
        "minimum_temporal_separation_s": 300, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Sweep raggio spaziale (sezione M). {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_radius_20m", "spatial_radius_m": 20.0, "maximum_group_diameter_m": 20.0,
        "minimum_temporal_separation_s": 300, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Sweep raggio spaziale (sezione M). {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_radius_30m", "spatial_radius_m": 30.0, "maximum_group_diameter_m": 30.0,
        "minimum_temporal_separation_s": 300, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Sweep raggio spaziale (sezione M). {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_sep_60s", "spatial_radius_m": 15.0, "maximum_group_diameter_m": 15.0,
        "minimum_temporal_separation_s": 60, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Sweep separazione temporale minima (sezione M), radius ancorato a temporal_recommended (15m). {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_sep_180s", "spatial_radius_m": 15.0, "maximum_group_diameter_m": 15.0,
        "minimum_temporal_separation_s": 180, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Sweep separazione temporale minima (sezione M). {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_sep_600s", "spatial_radius_m": 15.0, "maximum_group_diameter_m": 15.0,
        "minimum_temporal_separation_s": 600, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Sweep separazione temporale minima (sezione M). {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_extreme_tight", "spatial_radius_m": 5.0, "maximum_group_diameter_m": 5.0,
        "minimum_temporal_separation_s": 600, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Estremo di interazione raggio x separazione (piu' stretto x piu' severo), sezione M -- verifica che l'interazione piu' rischiosa non produca comportamento anomalo. {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_extreme_loose", "spatial_radius_m": 30.0, "maximum_group_diameter_m": 30.0,
        "minimum_temporal_separation_s": 60, "visit_merge_gap_s": 30, "minimum_points_per_visit": 1,
        "minimum_groups_for_model": 5, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_recommended", "evidence_source": "sensitivity_selected",
        "rationale": f"Estremo di interazione raggio x separazione (piu' largo x piu' permissivo), sezione M. {THESIS_NOTE}",
    },
    {
        "profile_name": "sens_profile_conservative_radius5", "spatial_radius_m": 5.0, "maximum_group_diameter_m": 5.0,
        "minimum_temporal_separation_s": 600, "visit_merge_gap_s": 30, "minimum_points_per_visit": 3,
        "minimum_groups_for_model": 8, "minimum_time_windows": 3, "direction_handling": "track_direction",
        "qc_profile": "temporal_conservative", "evidence_source": "sensitivity_selected",
        "rationale": f"Interazione profilo QC x raggio (segnalata in revisione architetturale): profilo conservative con raggio ristretto a 5m, per verificare l'effetto congiunto di maschera QC piu' severa e clustering piu' stretto. {THESIS_NOTE}",
    },
]

assert {r["profile_name"] for r in ROWS if r["evidence_source"] == "sensitivity_selected"}.isdisjoint(
    {"temporal_permissive", "temporal_recommended", "temporal_conservative"}
)
for r in ROWS:
    assert r["visit_merge_gap_s"] < 60, "visit_merge_gap_s must stay below the smallest swept minimum_temporal_separation_s (60s)"

out_path = ROOT / "config" / "repeated_location_matching.csv"
with out_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for row in ROWS:
        writer.writerow(row)

print(f"wrote {len(ROWS)} rows to {out_path}")
