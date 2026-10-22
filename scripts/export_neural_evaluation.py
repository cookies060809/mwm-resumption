"""Verify local neural artifacts and publish aggregate-only result snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mwm_eval.schema import canonical_hash, file_hash


def export(results, target):
    report = json.loads((results / "report.json").read_text(encoding="utf-8"))
    for name, expected in report["code_sha256"].items():
        if file_hash(ROOT / name) != expected:
            raise ValueError("SOURCE_CHANGED: " + name)
    if file_hash(ROOT / report["data"]["path"]) != report["data"]["sha256"]:
        raise ValueError("DATA_CHANGED")
    if file_hash(results / "representative.pt") != report["representative"]["checkpoint_sha256"]:
        raise ValueError("CHECKPOINT_CHANGED")
    digest, count, keys = hashlib.sha256(), 0, set()
    with (results / "predictions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = row["method_id"], row["seed"], row["sample_id"]
            if key in keys or row["status"] != "ok":
                raise ValueError("DUPLICATE_OR_FAILED_PREDICTION")
            keys.add(key)
            item = {k:row[k] for k in ("method_id","seed","sample_id","status","prediction","input_hash","source_input_hash")}
            digest.update((canonical_hash(item) + "\n").encode())
            count += 1
    verification = report["verification"]
    if count != verification["prediction_count"] or digest.hexdigest() != verification["prediction_sha256"]:
        raise ValueError("PREDICTIONS_CHANGED")
    runs = report["runs"]
    expected = len(runs) * report["data"]["counts"]["test"]
    if count != expected:
        raise ValueError("INCOMPLETE_RUNS")
    methods = {}
    for method, aggregate in report["aggregate"].items():
        selected = [r for r in runs if r["method_id"] == method]
        if [r["seed"] for r in selected] != report["seeds"]:
            raise ValueError("MISSING_SEED: " + method)
        per_seed = []
        for r in selected:
            m = r["metrics"]
            per_seed.append({"seed":r["seed"], "t1_accuracy":m["t1"]["accuracy"],
                             "t1_f1":m["t1"]["resume_f1"],
                             "t1_probability":{k:m["t1"]["probability"][k] for k in ("auroc","average_precision","brier","ece")},
                             "C_emitted_step_accuracy":m["t2"]["top1_accuracy"],
                             "A_conditional_step_accuracy":r.get("a_internal_metrics",{}).get("t2",{}).get("top1"),
                             "training":r.get("training")})
        first = selected[0]
        methods[method] = {"aggregate":aggregate, "per_seed":per_seed,
                           "first_seed_C_metrics":first["metrics"],
                           "first_seed_A_metrics":first.get("a_internal_metrics")}
    snapshot = {k:report[k] for k in ("scope","a_source_commit","code_commit","code_sha256","data","config","seeds","environment","verification","representative","limits","seed0_neural_vs_B4_task_cluster_bootstrap")}
    snapshot["methods"] = methods
    snapshot["artifact_verification"] = "all source/data/checkpoint/prediction hashes matched; aggregate only"
    snapshot["run_command"] = ("python scripts/run_neural_p0_evaluation.py --data " + report["data"]["path"]
        + " --output-dir " + results.resolve().relative_to(ROOT).as_posix()
        + " --seeds " + ",".join(map(str, report["seeds"]))
        + " --variants " + ",".join(report["config"]["variants"])
        + " --epochs " + str(report["config"]["epochs"]))
    if report.get('config_path'):
        snapshot['config_path'] = report['config_path']
        snapshot['run_command'] += ' --config ' + report['config_path']
    if (results / "original_A_check.json").exists():
        snapshot["original_A_reproduction"] = json.loads((results / "original_A_check.json").read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Verified {count} predictions; exported {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.results_dir, args.output)
