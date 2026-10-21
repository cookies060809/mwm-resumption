"""Train A's unchanged neural model on B's frozen data, score with C's evaluator.

All neural train/dev selections finish before any test inference. Six local
baselines receive the same cutoff inputs and train split. Auxiliary data is not
silently mixed in. Checkpoints and predictions stay in the ignored output folder.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch
from integration.a_input_adapter import validate_structured_evidence
from integration.a_neural_output import normalize_neural_output
from models.ecr_mwm.neural_data import load_records
from models.ecr_mwm.neural_metrics import evaluate as a_evaluate
from models.ecr_mwm.neural_model import Batch
from models.ecr_mwm.neural_training import fit_one, reload_model, seed_everything
from mwm_eval.engine import _aggregate, dump_json, predict_rows
from mwm_eval.local_baselines import make_local_baselines
from mwm_eval.metrics import evaluate
from mwm_eval.p0 import prepare_dataset
from mwm_eval.schema import audit_groups, canonical_hash, file_hash, validate_dataset
from scripts.validate_data import validate_records


def state_hash(payload):
    state = torch.load(io.BytesIO(payload), map_location="cpu", weights_only=True)["state_dict"]
    h = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        h.update(name.encode())
        h.update(str(tuple(tensor.shape)).encode())
        h.update(str(tensor.dtype).encode())
        h.update(bytes(tensor.contiguous().view(torch.uint8).flatten().tolist()))
    return h.hexdigest()


def run(data_path, output, seeds, variants, epochs=None):
    config = json.loads((ROOT / "configs/a_neural_p0.json").read_text(encoding="utf-8"))
    if epochs is not None:
        config["epochs"] = epochs
    config["data"] = data_path.resolve().relative_to(ROOT).as_posix()
    config["evaluation_seeds"], config["variants"] = seeds, variants
    config["supplement"] = None  # Complete release includes the 14-row supplement exactly once.
    output.mkdir(parents=True, exist_ok=True)
    raw = json.loads(data_path.read_text(encoding="utf-8"))
    errors = validate_records(raw)
    if errors:
        raise ValueError(errors[:5])
    records, golds = prepare_dataset(raw)
    validation = validate_dataset(records, golds)
    group_audit = audit_groups(records)
    for key in ("base_story_id", "person_id", "task_family"):
        if any(group_audit[key]["pairwise_overlap"].values()):
            raise ValueError("GROUP_CROSSES_SPLITS: " + key)
    examples = load_records(data_path)
    for example, record in zip(examples, records):
        if example["id"] != record["sample_id"]:
            raise ValueError("A_C_RECORD_ORDER_MISMATCH")
        if example["input"] != validate_structured_evidence(record["observation"]["structured_evidence"], record["observation"]):
            raise ValueError("A_C_INPUT_MISMATCH")
    parts = {split: [e for e in examples if e["split"] == split] for split in ("train", "dev", "test")}
    if any(not part for part in parts.values()):
        raise ValueError("TRAIN_DEV_TEST_REQUIRED")
    test_records = [r for r in records if r["split"] == "test"]
    by_gold = {g["sample_id"]: g for g in golds}
    test_golds = [by_gold[r["sample_id"]] for r in test_records]
    train_pairs = [(copy.deepcopy(r["observation"]), copy.deepcopy(by_gold[r["sample_id"]]))
                   for r in records if r["split"] == "train"]
    seed_everything(0, config["threads"])
    start = perf_counter()
    selected, train_batches, runs = {}, {}, []
    for variant in variants:
        print(f"{variant}: compiling {len(parts['train'])} train / {len(parts['dev'])} dev", flush=True)
        train, dev = Batch(parts["train"], variant), Batch(parts["dev"], variant)
        train_batches[variant] = train, dev
        selected[variant] = []
        for seed in seeds:
            payload, metadata = fit_one(train, dev, variant, seed, config)
            metadata["state_dict_sha256"] = state_hash(payload)
            selected[variant].append((payload, metadata))
            print(f"{variant} seed={seed}: trained {config['epochs']} epochs, dev selected {metadata['selected_epoch']}", flush=True)
    # Refit a predeclared representative before inspecting test scores.
    representative_variant, representative_seed = variants[0], seeds[0]
    repeated, repeat_meta = fit_one(*train_batches[representative_variant], representative_variant, representative_seed, config)
    original, original_meta = selected[representative_variant][0]
    if state_hash(repeated) != state_hash(original) or repeat_meta["selected_epoch"] != original_meta["selected_epoch"]:
        raise ValueError("REPRESENTATIVE_RETRAIN_MISMATCH")
    training_seconds = perf_counter() - start
    print("All neural train/dev choices frozen; starting locked test evaluation.", flush=True)
    prediction_hash = hashlib.sha256()
    n_predictions = 0
    first_rows = {}
    with (output / "predictions.jsonl").open("w", encoding="utf-8") as log:
        def record_rows(rows):
            nonlocal n_predictions
            for row in rows:
                # Timing is measured separately, never included in reproduction fingerprints.
                item = {k: row[k] for k in ("method_id", "seed", "sample_id", "status", "prediction", "input_hash", "source_input_hash")}
                prediction_hash.update((canonical_hash(item) + "\n").encode())
                log.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                n_predictions += 1

        for variant in variants:
            # No labels, IDs, mechanism or family metadata in the prediction batch.
            test_batch = Batch([{"input": copy.deepcopy(r["observation"]["structured_evidence"])} for r in test_records], variant)
            for payload, metadata in selected[variant]:
                model = reload_model(payload)
                stamp = perf_counter()
                native = model.predict(test_batch, evidence=True)
                latency = (perf_counter() - stamp) * 1000
                restored = reload_model(payload).predict(test_batch, evidence=True)
                if native != restored:
                    raise ValueError("TEST_RELOAD_PREDICTIONS_MISMATCH")
                method_id = "B10_NEURAL" if variant == "A0" else "NEURAL_" + variant
                rows = []
                for record, pred in zip(test_records, native):
                    obs = record["observation"]
                    rows.append({"sample_id": record["sample_id"], "method_id": method_id,
                                 "seed": metadata["seed"], "split": "test", "status": "ok",
                                 "prediction": normalize_neural_output(pred, obs),
                                 "input_hash": canonical_hash(obs), "source_input_hash": canonical_hash(obs)})
                metrics = evaluate(rows, test_golds, test_records)
                own = a_evaluate(native, [e["target"] for e in parts["test"]])
                for left, right in ((metrics["t1"]["accuracy"], own["t1"]["accuracy"]),
                                    (metrics["t1"]["resume_f1"], own["t1"]["f1"]),
                                    (metrics["t1"]["probability"]["brier"], own["t1"]["brier"])):
                    if left is None or right is None:
                        if left != right:
                            raise ValueError("A_C_METRIC_MISSINGNESS_MISMATCH")
                    elif abs(left - right) > 1e-10:
                        raise ValueError("A_C_PRIMARY_METRIC_MISMATCH")
                runs.append({"method_id": method_id, "seed": metadata["seed"], "status": "completed",
                             "metrics": metrics, "a_internal_metrics": own, "training": metadata,
                             "batch_prediction_ms": latency})
                if metadata["seed"] == seeds[0]:
                    first_rows[method_id] = rows
                record_rows(rows)
            print(f"{variant}: C evaluation and reload checks passed for {len(seeds)} seeds", flush=True)
        for seed in seeds:
            for method_id, method in make_local_baselines(seed).items():
                method.fit(copy.deepcopy(train_pairs))
                rows = predict_rows(method, test_records, seed)
                metrics = evaluate(rows, test_golds, test_records)
                if metrics["counts"]["n_failure"]:
                    raise ValueError("LOCAL_BASELINE_FAILURE: " + method_id)
                runs.append({"method_id": method_id, "seed": seed, "status": "completed", "metrics": metrics})
                if seed == seeds[0]:
                    first_rows[method_id] = rows
                record_rows(rows)
    from mwm_eval.statistics import paired_cluster_bootstrap
    comparisons = []
    if "B10_NEURAL" in first_rows and "B4" in first_rows:
        comparisons.append(paired_cluster_bootstrap(first_rows["B10_NEURAL"], first_rows["B4"],
            test_golds, test_records, metric="accuracy", seed=seeds[0], n_bootstrap=500, cluster_key="task_family"))
    representative = output / "representative.pt"
    representative.write_bytes(original)
    paths = [ROOT / "configs/a_neural_p0.json", Path(__file__).resolve()]
    for folder in ("models", "integration", "mwm_eval"):
        paths.extend((ROOT / folder).rglob("*.py"))
    report = {"scope": "C independent neural training and common-protocol P0 evaluation; scripted data only",
              "a_source_commit": "28525fb03a29ee27c0c85a1d0911f4bbffc0cf57",
              "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "code_sha256": {p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(set(paths))},
              "data": {"path": config["data"], "sha256": file_hash(data_path), "validation": validation,
                       "counts": {k: len(v) for k,v in parts.items()}, "group_audit": group_audit},
              "config": config, "seeds": seeds, "aggregate": _aggregate(runs), "runs": runs,
              "training_seconds": training_seconds, "total_seconds": perf_counter() - start,
              "environment": {"python": sys.version, "torch": str(torch.__version__), "platform": platform.platform(), "device": "cpu", "threads": config["threads"]},
              "verification": {"representative_retrained_identically": True, "all_checkpoint_reloads_exact": True,
                               "all_A_C_T1_accuracy_f1_brier_match": True, "prediction_count": n_predictions,
                               "prediction_sha256": prediction_hash.hexdigest(), "representative_state_dict_sha256": state_hash(original)},
              "representative": {"variant": representative_variant, "seed": representative_seed, "selected_epoch": original_meta["selected_epoch"],
                                 "checkpoint_sha256": file_hash(representative)},
              "seed0_neural_vs_B4_task_cluster_bootstrap": comparisons,
              "limits": ["No real-human P1, independent calibration, LLM or MENTIS experiment.",
                         "20 seeds quantify training randomness, not 20 independent datasets.",
                         "Structured features and supplied understanding evidence; no free-text encoder.",
                         "Inherited B label disputes and A structural zero support remain unchanged.",
                         "A T2 scores conditional argmax; C T2 scores the emitted step, so a negative T1 decision counts as a missing step. Both are reported without forcing equality.",
                         "Native v0.3 only; auxiliary multi-source JSONL requires a separate semantic adapter.",
                         "Checkpoint choice uses dev only, threshold is fixed at 0.5; no test-based model selection."]}
    dump_json(output / "report.json", report)
    print("Completed:", output / "report.json", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/p0/v0.3/p0_samples.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/c_neural_v03")
    parser.add_argument("--seeds", default=",".join(map(str, range(20))))
    parser.add_argument("--variants", default="A0,A1,A2,A3,A4,A5,A6")
    parser.add_argument("--epochs", type=int)
    args = parser.parse_args()
    seeds = [int(x) for x in args.seeds.split(",")]
    variants = args.variants.split(",")
    if not seeds or len(set(seeds)) != len(seeds) or not variants or len(set(variants)) != len(variants):
        raise ValueError("UNIQUE_NONEMPTY_SEEDS_AND_VARIANTS_REQUIRED")
    if set(variants) - {f"A{i}" for i in range(7)} or (args.epochs is not None and args.epochs < 1):
        raise ValueError("INVALID_VARIANTS_OR_EPOCHS")
    run(args.data, args.output_dir, seeds, variants, args.epochs)


if __name__ == "__main__":
    main()
