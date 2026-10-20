"""Validate and evaluate the frozen, formal P0 v0.2 batch. Offline by default."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mwm_eval.engine import dump_json, dump_jsonl, run_experiment
from mwm_eval.p0 import ADAPTER_VERSION, prepare_dataset
from mwm_eval.schema import file_hash
from scripts.validate_data import validate_records


def require_accepted_batch(source):
    if any(record.get("annotation", {}).get("status") not in {"reviewed", "adjudicated"}
           or record.get("annotation", {}).get("annotator_id") == "agent-draft" for record in source):
        raise ValueError("Draft/candidate P0 is excluded from formal evaluation; source-owner review is required")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/p0/p0_samples_v0.2.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/p0_v02")
    parser.add_argument("--seeds", help="Comma-separated override; default uses the team's fixed evaluation_seeds")
    parser.add_argument("--methods", default="B0,B1,B4,B5,B6,B7")
    parser.add_argument("--enable-external", action="store_true")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/external.example.json")
    parser.add_argument("--suite", choices=("core", "all"), default="all")
    args = parser.parse_args()
    source = json.loads(args.data.read_text(encoding="utf-8"))
    errors = validate_records(source)
    if errors:
        raise ValueError("B source validation failed: " + "; ".join(errors[:5]))
    require_accepted_batch(source)
    records, golds = prepare_dataset(source)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    inputs_path, labels_path = output / "prepared_inputs.jsonl", output / "prepared_labels.jsonl"
    dump_jsonl(inputs_path, records)
    dump_jsonl(labels_path, golds)
    provenance = {"adapter": ADAPTER_VERSION, "source_schema": "p0-record/v0.2.0",
                  "source_sha256": file_hash(args.data),
                  "source_scope": "B-reviewed scripted P0, not real human behavior",
                  "source_records": len(source), "source_pairs": len({r['base_story_id'] for r in source}),
                  "source_modified": False, "split_modified": False,
                  "semantic_mapping": "typed message content; access and understanding kept separate",
                  "known_limits": ["no independent calibration split", "template-based P0",
                                   "nested task graph is not represented in C observation",
                                   "A/C human blind review not completed"]}
    dump_json(output / "adaptation.json", provenance)
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    config.setdefault("evaluation", {}).update(
        required_group_isolation=["base_story_id", "person_id", "task_family"],
        bootstrap_cluster_key="task_family",
        dataset_provenance=provenance)
    seed_config = ROOT / "configs/a_ec_jmf_reference.json"
    convention = json.loads(seed_config.read_text(encoding="utf-8"))["evaluation_seeds"]
    seeds = ([int(s) for s in args.seeds.split(",")] if args.seeds else
             convention)
    config["evaluation"]["seed_selection"] = {
        "values": seeds, "matches_team_convention": seeds == convention,
        "convention_source": "configs/a_ec_jmf_reference.json:evaluation_seeds",
        "convention_sha256": file_hash(seed_config)}
    summary, status = run_experiment(inputs_path, labels_path, output, config,
                                    args.methods.split(","), seeds, suite=args.suite,
                                    enable_external=args.enable_external)
    from tools.build_dashboard import build
    build(output, inputs_path, labels_path)
    print(f"P0 evaluation complete: {output / 'report.md'}", flush=True)
    return int(any(run["status"] == "error" for run in summary["runs"]) or
               status["overall"] == "no_methods_executed")


if __name__ == "__main__":
    raise SystemExit(main())
