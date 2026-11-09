"""E0-QC-R final validation, item 3: v0.2 presets load schema+policy from the repo AND from a built wheel (non-editable)."""
import hashlib, json, os, sys
from pathlib import Path
import pandas as pd
REPO = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
import meteotracker_qc
from meteotracker_qc.config_resources import resource
from meteotracker_qc.pipeline import MeteotrackerQC
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
canon = REPO / "e0" / "qc_flag_schema_E0_v0.2.yaml"
res = {"package_file": meteotracker_qc.__file__, "cwd": os.getcwd(), "canonical_schema": str(canon), "canonical_sha256": h(canon),
       "old_reference_from_package_resolves": (Path(str(resource("qc_E0R_recommended_v0.2.yaml"))).parent /
                                               "../e0/qc_flag_schema_E0_v0.2.yaml").resolve().is_file(), "profiles": {}}
camp = "05-27__20260527T13_08_42_mtdicambo_AC4D162B317E_Bologna-Bologna__99cbc5b816"
raw = REPO / "data" / "raw" / "05-27" / "20260527T13_08_42_mtdicambo_AC4D162B317E_Bologna-Bologna.csv"
for p in ("permissive", "recommended", "restrictive"):
    r = {}
    for where, cfg in (("repo_config", REPO / "config" / f"qc_E0R_{p}_v0.2.yaml"), ("package_resources", Path(str(resource(f"qc_E0R_{p}_v0.2.yaml"))))):
        q = MeteotrackerQC(cfg)
        r[where] = {"config": str(cfg), "flag_schema_path": str(q.flag_schema_path), "schema_exists": q.flag_schema_path.is_file(),
                    "schema_sha256_equals_canonical": h(q.flag_schema_path) == res["canonical_sha256"],
                    "policy_sha256": h(q.policy_path)}
    # end-to-end: package preset on one campaign (in memory) == archived v0.2 run
    q = MeteotrackerQC(Path(str(resource(f"qc_E0R_{p}_v0.2.yaml"))))
    std, _ = q.compute_frame(raw)
    arch = pd.read_parquet(next((REPO / "outputs" / "e0R_qc_split_20261109T1240" / p / "campaigns" / camp).glob("*_standardized.parquet")))
    ft = q.emit_flag_table(std, OUT / f"_tmp_ft_{p}.csv", canonical_campaign_id=camp, source_file=raw.name) if False else None
    r["e2e_0527_keep_equal_archive"] = bool((std[f"keep_{p}"].to_numpy() == arch[f"keep_{p}"].to_numpy()).all())
    r["e2e_0527_n_keep"] = int(std[f"keep_{p}"].sum())
    r["policy_sha_equal_repo_vs_package"] = r["repo_config"]["policy_sha256"] == r["package_resources"]["policy_sha256"]
    res["profiles"][p] = r
name = "package_check_" + ("unrelated_cwd" if Path.cwd().resolve() != REPO.resolve() else "repo_cwd") + ".json"
(OUT / name).write_text(json.dumps(res, indent=2), encoding="utf-8"); print(json.dumps(res, indent=1))
