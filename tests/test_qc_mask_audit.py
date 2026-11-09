import pandas as pd

from meteotracker_qc.qc_mask_audit import (agreement_summary, attach_state, mapping_table, per_code_disagreement,
                                           point_flag_state, policy_excludes)


def _data():
    ft = pd.DataFrame(dict(canonical_campaign_id="c", source_row=[0, 0, 1, 2, -1],
                           flag_code=["qc_a", "qc_w", "qc_w", "qc_a", "DUP"],
                           severity=["exclude", "warn", "warn", "exclude", "exclude"]))
    pts = pd.DataFrame(dict(canonical_campaign_id="c", source_row=[0, 1, 2, 3],
                            keep_recommended=[False, False, True, True],
                            qc_exclusion_reasons_recommended=["qc_a", "qc_b", "", ""]))
    return attach_state(pts, point_flag_state(ft))


def test_states_and_agreement():
    d = _data()
    assert d.ft_state.tolist() == ["exclude", "warn_only", "exclude", "ok"]
    s = agreement_summary(d, "keep_recommended")
    assert (s["agree_drop"], s["agree_keep"], s["ft_only_drop"], s["pipeline_only_drop"]) == (1, 1, 1, 1)
    assert s["agreement"] == 0.5


def test_per_code_directions():
    t = per_code_disagreement(_data(), "keep_recommended", "qc_exclusion_reasons_recommended")
    a = t[t.direction == "ft_exclude_but_pipeline_keeps"].set_index("code")
    b = t[t.direction == "pipeline_drops_but_no_ft_exclude"].set_index("code")
    assert a.loc["qc_a", "n_points"] == 1 and b.loc["qc_b", "n_points"] == 1


def test_policy_and_mapping():
    assert policy_excludes("EXCLUDE_ALL_SCIENTIFIC", "permissive")
    assert not policy_excludes("EXCLUDE_RECOMMENDED", "permissive")
    m = mapping_table({"qc_a": ("exclude", 3)}, {"qc_a": ("INFO_ONLY", 9)}, {}, {}).iloc[0]
    assert m.status == "MISMATCH_schema_exclude_policy_keeps_recommended"
