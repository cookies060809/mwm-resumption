"""Export small, anonymous engineering result snapshots; exclude source records."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mwm_eval.schema import canonical_hash, file_hash


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results/p0_v02")
    parser.add_argument("--include-source-audit", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/p0_v02_results.json")
    args = parser.parse_args()
    summary, manifest = (read(args.results_dir / name) for name in ("summary.json", "manifest.json"))
    repro = read(args.results_dir / "reproducibility.json")
    if summary["dataset_layer"] != "P0" or not repro["matched"]:
        raise ValueError("a successfully reproduced formal P0 run is required")
    from scripts.check_p0_reproducibility import snapshot
    from mwm_eval.schema import load_jsonl
    predictions = snapshot(load_jsonl(args.results_dir / "predictions.jsonl"))
    if canonical_hash(predictions) != repro["prediction_sha256"]:
        raise ValueError("saved predictions differ from verified predictions")
    methods = {}
    output_relative = args.results_dir.resolve().relative_to(ROOT).as_posix()
    provenance = manifest["dataset_provenance"]
    run_command = ("python scripts/run_p0_evaluation.py --profile " + provenance["run_profile"]
        + " --data " + provenance["source_path"] + " --config " + provenance["configuration_path"]
        + " --methods " + ",".join(manifest["methods"]) + " --seeds " + ",".join(map(str, manifest["seeds"]))
        + " --output-dir " + output_relative)
    for method_id, aggregate in summary["aggregate"].items():
        first = next(r for r in summary["runs"] if r["method_id"] == method_id and r["seed"] == manifest["seeds"][0])
        if first["status"] != "completed":
            raise ValueError("snapshot supports completed local methods only")
        metrics = first["metrics"]
        methods[method_id] = {"aggregate": aggregate["metrics"],
            "implementation": first["spec"]["implementation"],
            "strict_reproduction": first["spec"].get("strict_reproduction", False),
            "limitations": first["spec"].get("limitations"),
            "training": first["spec"].get("training"),
            "first_seed_checkpoint": first.get("artifacts", []),
            "first_seed": {"counts": metrics["counts"], "t1": metrics["t1"], "t2": metrics["t2"],
                "states": metrics["states"], "mechanism_pairs": metrics["mechanism_pairs"]}}
    snapshot_data = {"scope": "scripted P0 diagnostic results; A structured reference model when explicitly enabled; not real human validation",
        "seeds": manifest["seeds"], "split_counts": manifest["validation"]["split_counts"],
        "dataset_provenance": manifest["dataset_provenance"],
        "inputs_sha256": manifest["inputs_sha256"], "labels_sha256": manifest["labels_sha256"],
        "code_sha256": manifest["code_sha256"], "methods": methods, "reproducibility": repro,
        "bootstrap_comparisons": read(args.results_dir / "comparisons.json"),
        "calibration": "not fitted; no independent calibration split",
        "statistical_limits": "few held-out task blueprints; intervals are exploratory; repeated seeds are not extra samples",
        "run_commands": [run_command, "python scripts/check_p0_reproducibility.py --results-dir " + output_relative]}
    write(args.output, snapshot_data)
    if args.include_source_audit:
        audit = read(ROOT / "results/p1_audit/source_inventory.json")
        if audit["errors"]:
            raise ValueError("source audit contains errors")
        holo, rfm = audit["sources"]["holoassist"], audit["sources"]["rfm"]
        candidates = read(ROOT / "results/p1_audit/holoassist/candidate_summary.json")
        people, fps_present = Counter(), 0
        for sample in rfm["samples"]:
            path = ROOT / "data/external/raw/rfm" / sample["sample_key"] / "meta.json"
            meta = read(path)
            if meta.get("participant_id") is not None:
                people[str(meta["participant_id"])] += 1
            fps_present += any(k.lower() in {"fps", "frame_rate", "framerate"} for k in meta)
        aggregate = {"scope": "public-source availability and evidence audit; no validated P1 resumption benchmark",
            "holoassist": {"url": holo["url"], "subset_sha256": holo["subset_sha256"],
                "source_bytes": holo["source_bytes"], "downloaded_prefix_bytes": holo["downloaded_prefix_bytes"],
                "source_sessions_inspected": holo["selected_sessions"], "source_complete": holo["source_complete"],
                "selection": holo["selection"], "candidate_audit": candidates,
                "review_status": "unreviewed; interruption and original-goal step validity need independent review"},
            "rfm": {"repository": rfm["repository"], "commit": rfm["commit"],
                "n_sample_directories": rfm["n_sample_directories"], "category_counts": rfm["category_counts"],
                "n_audited": rfm["n_audited"], "selection": rfm["selection"],
                "n_unique_participants_in_pilot": len(people),
                "samples_per_participant_range": [min(people.values()), max(people.values())] if people else None,
                "n_metadata_with_explicit_fps": fps_present,
                "n_timestamped_transcripts": sum(bool(s["files"]["transcript.txt"].get("timestamps_in_seconds")) for s in rfm["samples"]),
                "n_gaze_files": sum(s["files"]["mediapipe/gaze.csv"]["available"] for s in rfm["samples"]),
                "n_survey_files": sum(s["files"]["survey.csv"]["available"] for s in rfm["samples"]),
                "license_files_found": rfm["license_files"],
                "gaze_time_alignment": "frame indices present; no explicit FPS in sampled meta.json; scene-object mapping not established",
                "survey_scope": "post-trial affect and robot correction preferences, including a Top-3 selection question",
                "modeling_scope": "auxiliary evidence study; not contemporaneous B/C/Q truth or human task-resumption gold"},
            "source_inventory_sha256": file_hash(ROOT / "results/p1_audit/source_inventory.json"),
            "publication": "aggregate counts only; no source records, transcripts, questionnaire responses or participant IDs"}
        write(ROOT / "evaluation/p1_source_inventory.json", aggregate)
    print("Anonymous evaluation snapshots exported to evaluation/.")


if __name__ == "__main__":
    main()
