"""Generator for config/temporal_drift_policy.csv. Run manually; not part of
the pipeline. Written via csv.writer to avoid hand-typed CSV quoting bugs.
Built incrementally across milestones M4/M7/M8/M9/M10 as each consuming
module's metric names solidify -- rerunning regenerates the whole file, same
discipline as config/session_qc_policy.csv in the previous phase.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COLUMNS = [
    "rule_id", "scope", "metric", "operator", "threshold", "unit", "resulting_status",
    "reason_code", "priority", "evidence_source", "rationale", "sensitivity_values", "enabled",
]

ROWS: list[dict] = []


def add(rule_id, scope, metric, operator, threshold, unit, resulting_status, reason_code,
        priority, evidence_source, rationale, sensitivity_values="", enabled=True):
    ROWS.append({
        "rule_id": rule_id, "scope": scope, "metric": metric, "operator": operator, "threshold": threshold,
        "unit": unit, "resulting_status": resulting_status, "reason_code": reason_code, "priority": priority,
        "evidence_source": evidence_source, "rationale": rationale, "sensitivity_values": sensitivity_values,
        "enabled": enabled,
    })


# ============================================================
# scope: temporal_internal_assessability (Section F)
# ============================================================
S = "temporal_internal_assessability"
add("TDA-NA-01", S, "nominal_time_span_s", "<", 60.0, "s", "NOT_ASSESSABLE", "SESSION_TOO_SHORT", 0,
    "engineering_default", "Sotto 60s non c'e' abbastanza durata di sessione per distinguere alcunche' di temporale.")
add("TDA-NA-02", S, "n_repeated_location_groups_valid", "==", 0, "count", "NOT_ASSESSABLE", "NO_VALID_REVISITS", 0,
    "engineering_default", "Nessun gruppo spaziale con >=2 visite: nessun ripassaggio strutturale possibile.")
add("TDA-NA-03", S, "has_pairs_but_none_valid", "==", 1, "bool", "NOT_ASSESSABLE", "INSUFFICIENT_TEMPORAL_SEPARATION", 0,
    "engineering_default", "Esistevano coppie candidate ma nessuna ha superato la separazione temporale minima o la qualita' minima.")
add("TDA-NA-04", S, "n_repeated_location_pairs_valid", "==", 0, "count", "NOT_ASSESSABLE", "NO_VALID_REVISITS", 0,
    "engineering_default", "Fallback: zero coppie valide per qualunque motivo residuo.")
add("TDA-PA-01", S, "single_valid_group_single_pair", "==", 1, "bool", "PARTIALLY_ASSESSABLE", "START_END_ONLY", 10,
    "engineering_default", "Un solo gruppo valido con una sola coppia: equivalente a un confronto start-end travestito da ripassaggio, non basta da solo.")
add("TDA-PA-02", S, "groups_mostly_invalid", "==", 1, "bool", "PARTIALLY_ASSESSABLE", "EXCESSIVE_FRAGMENTATION", 10,
    "data_distribution",
    (
        "DISABILITATA dopo la prima run reale sulle 34 campagne: la frazione di gruppi singleton (>75% qui) e' "
        "quasi sempre alta per costruzione in un tragitto punto-a-punto (mediana reale 99.3%, media 94.4% sulle "
        "34 campagne) -- la maggior parte dei luoghi lungo un tragitto bici viene naturalmente attraversata una "
        "sola volta, il che non e' indicativo di scarsa qualita' dei VERI ripassaggi. La regola preemptava (priorita' "
        "10, prima riga a parita' di priorita') controlli piu' specifici e gia' sufficienti sull'adeguatezza assoluta "
        "dell'evidenza (FEW_REVISIT_GROUPS, INSUFFICIENT_VALID_PAIRS, REVISITS_CONCENTRATED_IN_SPACE/TIME, "
        "LOW_REVISIT_QUALITY). Verificato sulle 6 campagne reali che la attivavano: 3 avevano evidenza assoluta "
        "gia' adeguata (es. 33 gruppi validi, 6-52 coppie valide) e sarebbero risultate ASSESSABLE senza questa "
        "regola; le altre 3 restano correttamente PARTIALLY_ASSESSABLE ma con un motivo piu' preciso "
        "(REVISITS_CONCENTRATED_IN_SPACE o LOW_REVISIT_QUALITY, gia' presenti come regole separate). Riga mantenuta "
        "disabilitata (non eliminata) per tracciabilita' e per il vocabolario di reason code richiesto dalla specifica."
    ), enabled=False)
add("TDA-PA-03", S, "n_repeated_location_groups_valid", "<", 5, "count", "PARTIALLY_ASSESSABLE", "FEW_REVISIT_GROUPS", 10,
    "engineering_default", "Sotto 5 gruppi validi (soglia minimum_groups_for_model del profilo temporal_recommended) il cluster bootstrap e il within-estimator restano poco informativi.",
    sensitivity_values="3/5/8 (permissive/recommended/conservative)")
add("TDA-PA-04", S, "number_of_distinct_time_windows", "<", 2, "count", "PARTIALLY_ASSESSABLE", "REVISITS_CONCENTRATED_IN_TIME", 10,
    "engineering_default", "Ripassaggi concentrati in una sola finestra temporale (su 4): non si puo' distinguere un trend da rumore a breve termine.")
add("TDA-PA-05", S, "repeated_location_spatial_coverage", "<", 0.15, "fraction", "PARTIALLY_ASSESSABLE", "REVISITS_CONCENTRATED_IN_SPACE", 10,
    "engineering_default", "I gruppi validi coprono meno del 15% dell'estensione spaziale (bounding box) della sessione: i ripassaggi sono concentrati in una sola zona.")
add("TDA-PA-06", S, "n_repeated_location_pairs_valid", "<", 5, "count", "PARTIALLY_ASSESSABLE", "INSUFFICIENT_VALID_PAIRS", 10,
    "engineering_default", "Meno di 5 coppie valide in totale: anche con gruppi sufficienti, il volume di evidenza resta scarso.")
add("TDA-PA-07", S, "fraction_low_quality_visits", ">", 0.5, "fraction", "PARTIALLY_ASSESSABLE", "LOW_REVISIT_QUALITY", 10,
    "engineering_default", "Oltre meta' delle visite ha meno del numero minimo di punti (LOW_POINT_COUNT): l'evidenza disponibile e' rumorosa.")
add("TDA-OK-01", S, "n_repeated_location_groups", "always", "", "count", "ASSESSABLE", "SUFFICIENT_REVISITS", 99,
    "engineering_default", "Fallback obbligatorio: nessuna delle condizioni di insufficienza sopra si applica.")


# ============================================================
# scope: temporal_change_diagnosis (Section J)
# ============================================================
S = "temporal_change_diagnosis"
add("TCD-NA-01", S, "temporal_internal_assessability_status", "==", "NOT_ASSESSABLE", "category", "NOT_ASSESSABLE", "NOT_ASSESSABLE", 0,
    "engineering_default", "Rispecchia direttamente l'assessabilita' interna insufficiente (sezione F): nessuna diagnosi possibile.")
add("TCD-IR-01", S, "temporal_internal_assessability_status", "==", "PARTIALLY_ASSESSABLE", "category", "INSUFFICIENT_REVISITS", "INSUFFICIENT_REVISITS", 2,
    "engineering_default", "Assessabilita' solo parziale: l'evidenza disponibile non basta per nessuna diagnosi piu' specifica, qualunque cosa dicano le stime puntuali.")
add("TCD-MD-01", S, "method_agreement", "==", "METHODS_DISAGREE", "category", "INTERNAL_METHODS_DISAGREE", "METHODS_DISAGREE", 10,
    "engineering_default", "La mediana delle pendenze (Metodo 1) e il modello a effetti fissi (Metodo 2) discordano nel segno: diagnosi distinta e onesta, non una media nascosta tra le due.")
add("TCD-IC-01", S, "any_instability_flag", "==", 1, "bool", "INCONCLUSIVE_TEMPORAL_EFFECT", "UNSTABLE_OR_DIRECTION_DEPENDENT_OR_DOMINATED", 15,
    "engineering_default", "CI troppo ampia, dipendenza dalla direzione di percorrenza, dominanza di un singolo gruppo o instabilita' leave-one-group-out: qualunque di queste rende la stima non conclusiva anche se i metodi concordano nel segno.")
add("TCD-NL-01", S, "temporal_model_form", "==", "NONLINEAR_CANDIDATE", "category", "POSSIBLE_NONLINEAR_BACKGROUND_CHANGE", "NONLINEAR_CANDIDATE_SUPPORTED", 20,
    "engineering_default", "Il modello quadratico batte quello lineare in cross-validation leave-one-group-out con margine sufficiente e coerenza tra direzioni (gia' verificato da nonlinear.py prima di arrivare qui).")
add("TCD-SUP-01", S, "trend_supported_flag", "==", 1, "bool", "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "TREND_SUPPORTED_BY_REVISITS", 25,
    "engineering_default", "Metodi concordi, nessuna instabilita' rilevata, intervallo di confidenza che esclude lo zero: la soglia minima di evidenza richiesta dalla sezione J.1 e' soddisfatta.")
add("TCD-OK-01", S, "temporal_internal_assessability_status", "always", "", "category", "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE", "NO_DETECTABLE_CHANGE", 99,
    "engineering_default", "Fallback: assessabile, metodi concordi, nessuna instabilita', ma l'intervallo di confidenza include lo zero -- nessun cambiamento distinguibile alla risoluzione disponibile (non equivale a trend esattamente zero).")

# ============================================================
# scope: sensor_drift_interpretation (Section J)
# ============================================================
S = "sensor_drift_interpretation"
add("SDI-NA-01", S, "temporal_change_diagnosis", "in", "NOT_ASSESSABLE|INSUFFICIENT_REVISITS", "category", "NOT_ASSESSABLE", "NOT_ASSESSABLE", 0,
    "engineering_default", "Nessuna diagnosi di cambiamento -> nessuna interpretazione di deriva possibile.")
add("SDI-NONE-01", S, "temporal_change_diagnosis", "==", "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE", "category", "NO_SPECIFIC_INSTRUMENT_EVIDENCE", "NO_DETECTABLE_CHANGE", 5,
    "engineering_default", "Nessun cambiamento rilevato: nessuna evidenza, a favore o contro, di un effetto strumentale.")
add("SDI-EXT-01", S, "abs_primary_trend_c_per_min", ">", 0.02, "C/min", "POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED", "LARGE_TREND_MAGNITUDE", 10,
    "engineering_default", "Un trend supportato ma di ampiezza atmosfericamente inconsueta per un transetto urbano breve (>1.2 C/ora) merita un confronto futuro con una stazione esterna, senza per questo dichiarare deriva certa.",
    sensitivity_values="soglia indicativa, mai validata esternamente in questa fase")
add("SDI-DEFAULT-01", S, "temporal_change_diagnosis", "always", "", "category", "CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA", "INTERNAL_DATA_INSUFFICIENT_TO_DISTINGUISH", 99,
    "engineering_default", "Con il solo MeteoTracker non e' possibile distinguere cambiamento di massa d'aria, microclima locale, esposizione/ventilazione e deriva strumentale (principio B.1 della specifica) -- questo e' l'esito onesto di default per qualunque cambiamento rilevato o incerto.")


out_path = ROOT / "config" / "temporal_drift_policy.csv"
with out_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for row in ROWS:
        writer.writerow(row)

n_scopes = len({r["scope"] for r in ROWS})
print(f"wrote {len(ROWS)} rows ({n_scopes} scopes) to {out_path}")
