"""Orchestrator for the temporal-drift diagnosis layer ("Prompt 4"), sibling
to session_qc_pipeline.py. Reads only the `recommended` point-level tree
(same reference-frame choice as session_qc's segment inventory); never
touches data/raw/, never writes to outputs/{permissive,recommended,
restrictive}/, never imports repeated_routes/.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .temporal_drift.assessability import (
    add_derived_assessability_columns, add_start_end_consistency, classify_assessability,
    compute_session_assessability_metrics,
)
from .temporal_drift.candidates import build_temporal_candidate_masks
from .temporal_drift.config import MAIN_PROFILE, get_profile, load_matching_policy
from .temporal_drift.conservation import compute_conservation_metrics
from .temporal_drift.detrending import (
    compute_experimental_detrending, is_detrending_eligible, session_mean_deltas,
)
from .temporal_drift.diagnostics import write_all_diagnostics
from .temporal_drift.diagnosis import (
    classify_sensor_drift_interpretation, classify_temporal_change_diagnosis, prepare_diagnosis_metrics,
)
from .temporal_drift.grouping import compute_groups_and_visits
from .temporal_drift.nonlinear import evaluate_nonlinear_candidate
from .temporal_drift.outputs import write_campaign_json, write_detrended_experimental_csv
from .temporal_drift.pairs import build_pairs
from .temporal_drift.sensitivity import classify_stability, run_session_sensitivity
from .temporal_drift.trend_methods import (
    RESULT_FIELDS, fixed_effects_huber_trend, fixed_effects_ols_trend, fixed_effects_theilsen_trend,
    pairwise_median_trend,
)
from .temporal_drift.uncertainty import compute_uncertainty_flags

CONFIG_VERSION = "temporal_drift_v1"
MAIN_N_BOOTSTRAP = 1000
SENSITIVITY_N_BOOTSTRAP = 200


def _prefix(d: dict, prefix: str) -> dict:
    return {f"{prefix}{k}": v for k, v in d.items() if k != "method"}


def discover_canonical_campaign_ids(root: Path, session_qc_inventory: pd.DataFrame | None = None) -> list[str]:
    """The 34-campaign (or whatever session_qc currently covers) canonical
    set, read from session_qc_inventory.csv -- deliberately NOT a directory
    scan of outputs/recommended/, which can contain more campaigns than
    session_qc/temporal_drift have been re-run for (see the regression test
    in tests/test_temporal_pipeline.py for the real incident this guards
    against).
    """
    if session_qc_inventory is None:
        session_qc_inventory = pd.read_csv(root / "outputs" / "session_qc" / "session_qc_inventory.csv")
    return sorted(session_qc_inventory["canonical_campaign_id"].unique())


def _load_campaign_df(campaign_id: str, root: Path) -> pd.DataFrame:
    campaign_dir = root / "outputs" / "recommended" / campaign_id
    files = list(campaign_dir.glob("*_standardized.parquet"))
    if not files:
        raise FileNotFoundError(f"no standardized parquet for {campaign_id} under {campaign_dir}")
    df = pd.read_parquet(files[0])
    return build_temporal_candidate_masks(df)


def process_campaign(
    campaign_id: str, df: pd.DataFrame, matching_policy: pd.DataFrame, temporal_drift_policy: pd.DataFrame,
    preliminary_drift_fields: dict | None = None, main_n_bootstrap: int = MAIN_N_BOOTSTRAP,
    sensitivity_n_bootstrap: int = SENSITIVITY_N_BOOTSTRAP,
) -> dict:
    profile = get_profile(matching_policy, MAIN_PROFILE)
    candidate_col = "temporal_candidate_recommended"

    groups, visits, obs = compute_groups_and_visits(df, candidate_col, profile)
    pairs = build_pairs(visits, df, profile)
    session_start, session_end = df["time_utc"].min(), df["time_utc"].max()

    assess_metrics = compute_session_assessability_metrics(df, candidate_col, groups, visits, pairs, session_start, session_end)
    preliminary_drift_fields = preliminary_drift_fields or {}
    assess_metrics = add_start_end_consistency(
        assess_metrics,
        preliminary_drift_fields.get("start_end_locations_comparable", False),
        preliminary_drift_fields.get("start_temperature_c"),
        preliminary_drift_fields.get("end_temperature_c"),
        preliminary_drift_fields.get("raw_start_end_time_difference_s"),
    )
    assess_df = add_derived_assessability_columns(pd.DataFrame([assess_metrics]))
    assessability = classify_assessability(assess_df, temporal_drift_policy).iloc[0]

    method1 = pairwise_median_trend(pairs, n_visits_total=len(visits), n_bootstrap=main_n_bootstrap)
    method2_ols = fixed_effects_ols_trend(visits, pairs, session_start, n_bootstrap=main_n_bootstrap)
    method2_huber = fixed_effects_huber_trend(visits, pairs, session_start, n_bootstrap=main_n_bootstrap)
    method2_theilsen = fixed_effects_theilsen_trend(visits, pairs, session_start, n_bootstrap=main_n_bootstrap)

    nonlinear_result = evaluate_nonlinear_candidate(
        visits, pairs, session_start, assess_metrics["n_repeated_location_groups_valid"],
        assess_metrics["number_of_distinct_time_windows"], assess_metrics["nominal_time_span_s"],
    )

    uncertainty = compute_uncertainty_flags(method1, method2_huber, pairs)
    diag_metrics = prepare_diagnosis_metrics(assessability["status"], method1, method2_huber, nonlinear_result, uncertainty)
    diagnosis = classify_temporal_change_diagnosis(pd.DataFrame([diag_metrics]), temporal_drift_policy).iloc[0]
    diag_metrics_with_status = dict(diag_metrics)
    diag_metrics_with_status["temporal_change_diagnosis"] = diagnosis["status"]
    sensor_drift = classify_sensor_drift_interpretation(pd.DataFrame([diag_metrics_with_status]), temporal_drift_policy).iloc[0]

    sensitivity_df = run_session_sensitivity(df, matching_policy, temporal_drift_policy, n_bootstrap=sensitivity_n_bootstrap)
    sensitivity_df.insert(0, "canonical_campaign_id", campaign_id)
    stability = classify_stability(sensitivity_df)

    eligible, detrend_warnings = is_detrending_eligible(
        assessability["status"], diagnosis["status"], stability["temporal_sensitivity_stability_class"], method2_huber,
    )
    detrending_df = compute_experimental_detrending(df, candidate_col, session_start, session_end, method2_huber, eligible, base_warnings=detrend_warnings)
    deltas = session_mean_deltas(detrending_df, session_start, session_end)

    conservation = {
        "correlation_raw_vs_detrended": float("nan"), "rank_correlation_raw_vs_detrended": float("nan"),
        "between_location_variance_ratio": float("nan"), "within_location_variance_ratio": float("nan"),
        "fraction_of_points_with_adjustment_gt_0_1c": float("nan"), "fraction_of_points_with_adjustment_gt_0_25c": float("nan"),
        "fraction_of_points_with_adjustment_gt_0_5c": float("nan"), "max_absolute_adjustment_c": float("nan"),
        "conservation_flags": "",
    }
    if eligible:
        group_id_by_row = pd.Series(index=df.index, dtype=object)
        if not obs.empty:
            group_id_by_row.loc[obs["row_index"]] = obs["repeated_location_group_id"].values
        conservation = compute_conservation_metrics(detrending_df, group_id_by_row)

    session_row = {
        "canonical_campaign_id": campaign_id, **assess_metrics,
        "temporal_internal_assessability_status": assessability["status"],
        "temporal_internal_assessability_reason_code": assessability["reason_code"],
        "temporal_drift_assessability_preliminary": preliminary_drift_fields.get("temporal_drift_assessability_preliminary"),
        **_prefix(method1, "method1_"), **_prefix(method2_huber, "primary_"),
        **{k: v for k, v in nonlinear_result.items()},
        **uncertainty, "temporal_change_diagnosis": diagnosis["status"],
        "sensor_drift_interpretation": sensor_drift["status"],
        "temporal_sensitivity_stability_class": stability["temporal_sensitivity_stability_class"],
        "sensitivity_diagnosis_change_fraction": stability["diagnosis_change_fraction"],
        "detrending_supported": eligible, "detrending_warning_codes": ";".join(detrend_warnings),
        **deltas, **conservation,
    }
    # The **_prefix(...) spreads above republish method1/method2_huber's raw values, which
    # have no awareness of assessability and can be numerically extreme or merely present
    # when the session never reached ASSESSABLE (see reports/temporal_drift_diagnostics.md,
    # section AA, and diagnosis.py::prepare_diagnosis_metrics, which already computes the
    # correctly-nulled versions of exactly these five fields). Overwrite them explicitly,
    # by name, so the published record cannot silently diverge from diag_metrics again --
    # this must stay a plain, explicit assignment, never re-derived from assessability_status
    # here (that classification logic belongs solely to prepare_diagnosis_metrics).
    session_row.update({
        "method1_trend_c_per_min": diag_metrics["method1_trend_c_per_min"],
        "primary_trend_c_per_min": diag_metrics["primary_trend_c_per_min"],
        "abs_primary_trend_c_per_min": diag_metrics["abs_primary_trend_c_per_min"],
        "primary_confidence_interval_low": diag_metrics["primary_confidence_interval_low"],
        "primary_confidence_interval_high": diag_metrics["primary_confidence_interval_high"],
    })

    model_comparison_rows = []
    for result in (method1, method2_ols, method2_huber, method2_theilsen):
        row = {k: result.get(k) for k in RESULT_FIELDS}
        row["canonical_campaign_id"] = campaign_id
        row["configuration"] = "main"
        model_comparison_rows.append(row)
    # nonlinear_quadratic uses a different internal schema (nonlinear.py) --
    # only the fields with a direct RESULT_FIELDS equivalent are mapped, the
    # rest stay NaN/absent rather than fabricating a false equivalence.
    nonlinear_row = {k: None for k in RESULT_FIELDS}
    nonlinear_row["method"] = "nonlinear_quadratic"
    nonlinear_row["n_location_groups"] = assess_metrics["n_repeated_location_groups_valid"]
    nonlinear_row["n_visits"] = len(visits)
    nonlinear_row["model_residual_mad"] = nonlinear_result.get("nonlinear_cv_quadratic_residual_mad")
    nonlinear_row["canonical_campaign_id"] = campaign_id
    nonlinear_row["configuration"] = "main"
    nonlinear_row["temporal_model_form"] = nonlinear_result.get("temporal_model_form")
    nonlinear_row["nonlinear_cv_improvement_fraction"] = nonlinear_result.get("nonlinear_cv_improvement_fraction")
    model_comparison_rows.append(nonlinear_row)
    model_comparison = pd.DataFrame(model_comparison_rows)

    observations = _enrich_observations(obs, df, candidate_col)

    return {
        "session_row": session_row, "groups": groups, "visits": visits, "pairs": pairs,
        "model_comparison": model_comparison, "sensitivity": sensitivity_df,
        "detrending_df": detrending_df, "obs": obs, "observations": observations,
        "eligible_detrending": eligible,
    }


_OBSERVATION_QC_COLUMNS = [
    "time_utc", "canonical_latitude", "canonical_longitude", "canonical_temperature_c", "segment_id",
    "temporal_candidate_permissive", "temporal_candidate_recommended", "temporal_candidate_conservative",
    "temporal_candidate_primary_reason", "qc_gps_freeze", "qc_possible_gps_freeze", "qc_temp_isolated_spike",
    "qc_sensor_stabilization", "qc_stop_event",
]


def _enrich_observations(obs: pd.DataFrame, df: pd.DataFrame, candidate_col: str) -> pd.DataFrame:
    if obs.empty:
        return obs
    cols_present = [c for c in _OBSERVATION_QC_COLUMNS if c in df.columns]
    context = df.loc[obs["row_index"], cols_present].reset_index(drop=True)
    return pd.concat([obs.reset_index(drop=True), context], axis=1)


def run_temporal_drift(
    root: str | Path | None = None, output_root: str | Path | None = None,
    campaign_ids: list[str] | None = None, main_n_bootstrap: int = MAIN_N_BOOTSTRAP,
    sensitivity_n_bootstrap: int = SENSITIVITY_N_BOOTSTRAP, progress: bool = False,
) -> dict:
    import sys
    import time

    root = Path(root) if root else Path.cwd()
    output_root = Path(output_root) if output_root else root / "outputs" / "temporal_drift"
    output_root.mkdir(parents=True, exist_ok=True)

    matching_policy = load_matching_policy(root)
    temporal_drift_policy = pd.read_csv(root / "config" / "temporal_drift_policy.csv")
    session_qc_inventory = pd.read_csv(root / "outputs" / "session_qc" / "session_qc_inventory.csv")

    if campaign_ids is None:
        campaign_ids = discover_canonical_campaign_ids(root, session_qc_inventory)

    session_rows, all_groups, all_visits, all_pairs = [], [], [], []
    all_model_comparison, all_sensitivity, all_observations = [], [], []
    campaign_dfs, groups_by_campaign, visits_by_campaign = {}, {}, {}
    pairs_by_campaign, sensitivity_by_campaign, detrending_by_campaign = {}, {}, {}
    t_start = time.time()
    for i, campaign_id in enumerate(campaign_ids, start=1):
        t_campaign = time.time()
        if progress:
            print(f"[{i}/{len(campaign_ids)}] {campaign_id} ...", flush=True, file=sys.stderr)
        df = _load_campaign_df(campaign_id, root)
        prelim_row = session_qc_inventory.loc[session_qc_inventory["canonical_campaign_id"] == campaign_id]
        prelim_fields = {}
        if not prelim_row.empty:
            r = prelim_row.iloc[0]
            prelim_fields = {
                "temporal_drift_assessability_preliminary": r.get("temporal_drift_assessability"),
                "start_end_locations_comparable": bool(r.get("start_end_locations_comparable", False)),
                "start_temperature_c": r.get("start_temperature_c"),
                "end_temperature_c": r.get("end_temperature_c"),
                "raw_start_end_time_difference_s": r.get("raw_start_end_time_difference_s"),
            }
        result = process_campaign(
            campaign_id, df, matching_policy, temporal_drift_policy, prelim_fields,
            main_n_bootstrap=main_n_bootstrap, sensitivity_n_bootstrap=sensitivity_n_bootstrap,
        )
        session_rows.append(result["session_row"])
        for name, frame in (
            ("groups", result["groups"]), ("visits", result["visits"]), ("pairs", result["pairs"]),
            ("observations", result["observations"]),
        ):
            frame = frame.copy()
            frame.insert(0, "canonical_campaign_id", campaign_id)
            {"groups": all_groups, "visits": all_visits, "pairs": all_pairs, "observations": all_observations}[name].append(frame)
        mc = result["model_comparison"]
        all_model_comparison.append(mc)
        all_sensitivity.append(result["sensitivity"])

        campaign_dfs[campaign_id] = df
        groups_by_campaign[campaign_id] = result["groups"]
        visits_by_campaign[campaign_id] = result["visits"]
        pairs_by_campaign[campaign_id] = result["pairs"]
        sensitivity_by_campaign[campaign_id] = result["sensitivity"]
        if result["eligible_detrending"]:
            detrending_by_campaign[campaign_id] = result["detrending_df"]

        if progress:
            elapsed = time.time() - t_campaign
            total_elapsed = time.time() - t_start
            status = result["session_row"].get("temporal_change_diagnosis")
            print(f"    -> {status} ({elapsed:.1f}s, total {total_elapsed / 60:.1f} min)", flush=True, file=sys.stderr)

        write_campaign_json(
            campaign_id, result["session_row"], result["groups"], result["visits"], result["pairs"],
            result["model_comparison"], result["sensitivity"], output_root, CONFIG_VERSION,
        )
        if result["eligible_detrending"]:
            write_detrended_experimental_csv(campaign_id, result["detrending_df"], output_root)

    session_temporal_diagnostics = pd.DataFrame(session_rows)
    repeated_location_groups = pd.concat(all_groups, ignore_index=True) if all_groups else pd.DataFrame()
    repeated_location_visits = pd.concat(all_visits, ignore_index=True) if all_visits else pd.DataFrame()
    repeated_location_pairs = pd.concat(all_pairs, ignore_index=True) if all_pairs else pd.DataFrame()
    repeated_location_observations = pd.concat(all_observations, ignore_index=True) if all_observations else pd.DataFrame()
    temporal_model_comparison = pd.concat(all_model_comparison, ignore_index=True) if all_model_comparison else pd.DataFrame()
    temporal_drift_sensitivity = pd.concat(all_sensitivity, ignore_index=True) if all_sensitivity else pd.DataFrame()

    session_temporal_diagnostics.to_csv(output_root / "session_temporal_diagnostics.csv", index=False)
    repeated_location_groups.to_csv(output_root / "repeated_location_groups.csv", index=False)
    repeated_location_visits.to_csv(output_root / "repeated_location_visits.csv", index=False)
    repeated_location_pairs.to_csv(output_root / "repeated_location_pairs.csv", index=False)
    repeated_location_observations.to_csv(output_root / "repeated_location_observations.csv", index=False)
    temporal_model_comparison.to_csv(output_root / "temporal_model_comparison.csv", index=False)
    temporal_drift_sensitivity.to_csv(output_root / "temporal_drift_sensitivity.csv", index=False)
    temporal_drift_policy.to_csv(output_root / "temporal_policy_effective.csv", index=False)

    detrending_validation_cols = [
        "canonical_campaign_id", "detrending_supported", "detrending_warning_codes",
        "delta_session_mean_raw_c", "delta_session_mean_detrended_experimental_c",
        "correlation_raw_vs_detrended", "rank_correlation_raw_vs_detrended",
        "between_location_variance_ratio", "within_location_variance_ratio",
        "fraction_of_points_with_adjustment_gt_0_1c", "fraction_of_points_with_adjustment_gt_0_25c",
        "fraction_of_points_with_adjustment_gt_0_5c", "max_absolute_adjustment_c", "conservation_flags",
    ]
    present_cols = [c for c in detrending_validation_cols if c in session_temporal_diagnostics.columns]
    detrending_validation = session_temporal_diagnostics[present_cols].copy()
    detrending_validation.to_csv(output_root / "detrending_validation.csv", index=False)

    if progress:
        print("writing diagnostic PNGs ...", flush=True, file=sys.stderr)
    diagnostic_paths = write_all_diagnostics(
        campaign_dfs, groups_by_campaign, visits_by_campaign, pairs_by_campaign,
        sensitivity_by_campaign, detrending_by_campaign, session_temporal_diagnostics,
        output_root / "figures",
    )
    if progress:
        print(f"wrote {len(diagnostic_paths)} diagnostic PNGs. TOTAL elapsed {(time.time() - t_start) / 60:.1f} min", flush=True, file=sys.stderr)

    return {
        "session_temporal_diagnostics": session_temporal_diagnostics,
        "repeated_location_groups": repeated_location_groups,
        "repeated_location_visits": repeated_location_visits,
        "repeated_location_pairs": repeated_location_pairs,
        "temporal_model_comparison": temporal_model_comparison,
        "temporal_drift_sensitivity": temporal_drift_sensitivity,
        "repeated_location_observations": repeated_location_observations,
        "detrending_validation": detrending_validation,
        "diagnostic_paths": diagnostic_paths,
        "campaign_ids": campaign_ids, "output_root": output_root,
    }
