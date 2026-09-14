from pathlib import Path

import pandas as pd
import pytest

from meteotracker_qc.temporal_drift.diagnosis import (
    classify_sensor_drift_interpretation, classify_temporal_change_diagnosis, prepare_diagnosis_metrics,
)

ROOT = Path(__file__).resolve().parent.parent
POLICY = pd.read_csv(ROOT / "config" / "temporal_drift_policy.csv")


def _diagnose(**overrides):
    metrics = {
        "temporal_internal_assessability_status": "ASSESSABLE", "method_agreement": "METHODS_AGREE",
        "any_instability_flag": 0, "temporal_model_form": "LINEAR", "trend_supported_flag": 1,
        "primary_trend_c_per_min": 0.05, "abs_primary_trend_c_per_min": 0.05,
        "primary_confidence_interval_low": 0.02, "primary_confidence_interval_high": 0.08,
        "method1_trend_c_per_min": 0.05,
    }
    metrics.update(overrides)
    df = pd.DataFrame([metrics])
    diag = classify_temporal_change_diagnosis(df, POLICY)
    df["temporal_change_diagnosis"] = diag["status"]
    sdi = classify_sensor_drift_interpretation(df, POLICY)
    return diag.iloc[0], sdi.iloc[0]


def test_not_assessable_propagates():
    diag, sdi = _diagnose(temporal_internal_assessability_status="NOT_ASSESSABLE")
    assert diag["status"] == "NOT_ASSESSABLE"
    assert sdi["status"] == "NOT_ASSESSABLE"


def test_partially_assessable_is_insufficient_revisits():
    diag, _ = _diagnose(temporal_internal_assessability_status="PARTIALLY_ASSESSABLE")
    assert diag["status"] == "INSUFFICIENT_REVISITS"


def test_methods_disagree_is_distinct_diagnosis():
    diag, _ = _diagnose(method_agreement="METHODS_DISAGREE")
    assert diag["status"] == "INTERNAL_METHODS_DISAGREE"


def test_instability_flag_is_inconclusive():
    diag, _ = _diagnose(any_instability_flag=1)
    assert diag["status"] == "INCONCLUSIVE_TEMPORAL_EFFECT"


def test_nonlinear_candidate_diagnosis():
    diag, _ = _diagnose(temporal_model_form="NONLINEAR_CANDIDATE")
    assert diag["status"] == "POSSIBLE_NONLINEAR_BACKGROUND_CHANGE"


def test_supported_diagnosis_when_trend_excludes_zero():
    diag, _ = _diagnose()
    assert diag["status"] == "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED"


def test_no_detectable_change_when_ci_straddles_zero():
    diag, _ = _diagnose(trend_supported_flag=0, primary_confidence_interval_low=-0.02, primary_confidence_interval_high=0.03)
    assert diag["status"] == "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE"


def test_sensor_drift_never_declared_certain_even_when_supported():
    _diag, sdi = _diagnose()
    assert sdi["status"] != "SENSOR_DRIFT"
    assert sdi["status"] in {"CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA", "POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED"}


def test_sensor_drift_no_evidence_when_no_change_detected():
    diag, sdi = _diagnose(trend_supported_flag=0, primary_confidence_interval_low=-0.02, primary_confidence_interval_high=0.03)
    assert diag["status"] == "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE"
    assert sdi["status"] == "NO_SPECIFIC_INSTRUMENT_EVIDENCE"


def test_sensor_drift_external_reference_required_for_large_trend():
    diag, sdi = _diagnose(primary_trend_c_per_min=0.1, abs_primary_trend_c_per_min=0.1, primary_confidence_interval_low=0.05, primary_confidence_interval_high=0.15)
    assert diag["status"] == "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED"
    assert sdi["status"] == "POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED"


def test_sensor_drift_cannot_be_determined_for_modest_supported_trend():
    diag, sdi = _diagnose(primary_trend_c_per_min=0.01, abs_primary_trend_c_per_min=0.01, primary_confidence_interval_low=0.005, primary_confidence_interval_high=0.015)
    assert diag["status"] == "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED"
    assert sdi["status"] == "CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA"


def test_sensor_drift_vocabulary_never_contains_certain_drift_value():
    values = set(POLICY.loc[POLICY["scope"] == "sensor_drift_interpretation", "resulting_status"])
    assert "SENSOR_DRIFT" not in values
    assert values <= {
        "NOT_ASSESSABLE", "NO_SPECIFIC_INSTRUMENT_EVIDENCE",
        "POSSIBLE_INSTRUMENT_EFFECT_EXTERNAL_REFERENCE_REQUIRED", "CANNOT_BE_DETERMINED_WITH_INTERNAL_DATA",
    }


def test_temporal_change_diagnosis_vocabulary_never_contains_certain_drift_value():
    values = set(POLICY.loc[POLICY["scope"] == "temporal_change_diagnosis", "resulting_status"])
    assert "SENSOR_DRIFT" not in values
    assert values <= {
        "NOT_ASSESSABLE", "INSUFFICIENT_REVISITS", "INTERNAL_METHODS_DISAGREE", "INCONCLUSIVE_TEMPORAL_EFFECT",
        "POSSIBLE_NONLINEAR_BACKGROUND_CHANGE", "TEMPORAL_BACKGROUND_CHANGE_SUPPORTED", "NO_DETECTABLE_TEMPORAL_BACKGROUND_CHANGE",
    }


def test_prepare_diagnosis_metrics_wires_all_inputs_together():
    method1 = {"trend_c_per_min": 0.05}
    method2 = {"trend_c_per_min": 0.05, "confidence_interval_low": 0.02, "confidence_interval_high": 0.08}
    nonlinear = {"temporal_model_form": "LINEAR"}
    uncertainty = {"method_agreement": "METHODS_AGREE", "ci_too_wide": False, "dominated_by_single_location": False,
                   "leave_one_group_out_unstable": False, "direction_consistency": "consistent"}
    metrics = prepare_diagnosis_metrics("ASSESSABLE", method1, method2, nonlinear, uncertainty)
    assert metrics["trend_supported_flag"] == 1
    assert metrics["any_instability_flag"] == 0


@pytest.mark.parametrize("status", ["NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"])
def test_estimate_fields_are_nulled_when_not_fully_assessable(status):
    """method1/method2 still compute a numeric trend even on sessions that never
    reach ASSESSABLE (they have no awareness of the assessability gate) -- seen on
    real data as e.g. -0.336 C/min on a NOT_ASSESSABLE session (reports/
    temporal_drift_diagnostics.md, AA). The output schema must not present that
    number as if it were a usable estimate."""
    method1 = {"trend_c_per_min": -0.336}
    method2 = {"trend_c_per_min": -0.336, "confidence_interval_low": -0.5, "confidence_interval_high": -0.2}
    nonlinear = {"temporal_model_form": "LINEAR"}
    uncertainty = {"method_agreement": "METHODS_AGREE", "ci_too_wide": False, "dominated_by_single_location": False,
                   "leave_one_group_out_unstable": False, "direction_consistency": "consistent"}
    metrics = prepare_diagnosis_metrics(status, method1, method2, nonlinear, uncertainty)
    assert metrics["temporal_internal_assessability_status"] == status
    for key in [
        "primary_trend_c_per_min", "abs_primary_trend_c_per_min",
        "primary_confidence_interval_low", "primary_confidence_interval_high", "method1_trend_c_per_min",
    ]:
        assert pd.isna(metrics[key]), f"{key} should be NaN when status={status}, got {metrics[key]}"


def test_estimate_fields_survive_when_assessable():
    method1 = {"trend_c_per_min": 0.012}
    method2 = {"trend_c_per_min": 0.012, "confidence_interval_low": 0.008, "confidence_interval_high": 0.016}
    nonlinear = {"temporal_model_form": "LINEAR"}
    uncertainty = {"method_agreement": "METHODS_AGREE", "ci_too_wide": False, "dominated_by_single_location": False,
                   "leave_one_group_out_unstable": False, "direction_consistency": "consistent"}
    metrics = prepare_diagnosis_metrics("ASSESSABLE", method1, method2, nonlinear, uncertainty)
    assert metrics["primary_trend_c_per_min"] == pytest.approx(0.012)
    assert metrics["method1_trend_c_per_min"] == pytest.approx(0.012)
    assert metrics["primary_confidence_interval_low"] == pytest.approx(0.008)
    assert metrics["primary_confidence_interval_high"] == pytest.approx(0.016)
