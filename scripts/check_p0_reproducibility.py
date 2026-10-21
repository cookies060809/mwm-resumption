"""Rerun the local P0 experiment and compare all non-timing predictions."""

import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mwm_eval.schema import canonical_hash, load_jsonl


def snapshot(rows):
    rows = copy.deepcopy(rows)
    for row in rows:
        prediction = row.get("prediction") or {}
        cost = prediction.get("metadata", {}).get("a_cost")
        if isinstance(cost, dict):
            cost.pop("latency_ms", None)  # measured by A, excluded just like row wall time
    return {f"{r['method_id']}:{r['seed']}:{r['sample_id']}": {
        key: r[key] for key in ("status", "prediction", "input_hash", "source_input_hash")}
        for r in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results/p0_v02")
    args = parser.parse_args()
    original = json.loads((args.results_dir / "manifest.json").read_text(encoding="utf-8"))
    if set(original["methods"]) - {"B0", "B1", "B4", "B5", "B6", "B7", "B10", "B10_REFERENCE", "A1", "A2", "A3", "A4", "A5", "A6"}:
        raise ValueError("this reproducibility check supports local methods only")
    with tempfile.TemporaryDirectory(prefix="mwm_p0_repro_") as folder:
        subprocess.run([sys.executable, "-B", str(ROOT / "scripts/run_p0_evaluation.py"),
                        "--suite", "core", "--output-dir", folder,
                        "--methods", ",".join(original["methods"]),
                        "--profile", original["dataset_provenance"]["run_profile"],
                        "--data", str(ROOT / original["dataset_provenance"]["source_path"]),
                        "--config", str(ROOT / original["dataset_provenance"]["configuration_path"]),
                        "--seeds", ",".join(map(str, original["seeds"]))], cwd=ROOT,
                       env={**os.environ, "PYTHONUTF8": "1"}, check=True)
        repeated = json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))
        for key in ("code_sha256", "inputs_sha256", "labels_sha256", "effective_configuration_sha256"):
            if original[key] != repeated[key]:
                raise ValueError(f"reproducibility input/source/config drift: {key}")
        before = snapshot(load_jsonl(args.results_dir / "predictions.jsonl"))
        after = snapshot(load_jsonl(Path(folder) / "predictions.jsonl"))
        if not before or before != after:
            raise ValueError("P0 repeated predictions differ")
        source_summary = json.loads((args.results_dir / "summary.json").read_text(encoding="utf-8"))
        repeated_summary = json.loads((Path(folder) / "summary.json").read_text(encoding="utf-8"))
        checkpoints_before = {(run["method_id"], run["seed"]): run.get("artifacts", []) for run in source_summary["runs"]}
        checkpoints_after = {(run["method_id"], run["seed"]): run.get("artifacts", []) for run in repeated_summary["runs"]}
        if checkpoints_before != checkpoints_after:
            raise ValueError("repeated trained checkpoints differ")
    result = {"matched": True, "n_test_predictions": len(before),
              "prediction_sha256": canonical_hash(before), "dataset_layer": "P0",
              "source_sha256": original["dataset_provenance"]["source_sha256"],
              "trained_checkpoint_hashes_matched": True,
              "scope": "same source, inputs, configuration and environment; timing excluded"}
    (args.results_dir / "reproducibility.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
