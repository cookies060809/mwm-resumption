"""Build or verify `data/RELEASE.json`, the cross-artifact data contract.

`--write` recomputes the manifest from the delivered files. The default mode
recomputes it and fails if the committed manifest or any invariant drifts.

Usage:
    python scripts/release_manifest.py --write
    python scripts/release_manifest.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "RELEASE.json"

P0_DIR = ROOT / "data" / "p0" / "v0.3"
READY_DIR = ROOT / "data" / "training_ready" / "v1"
P1_DIR = ROOT / "data" / "p1" / "public_derived"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def p0_block() -> dict:
    records = load_json(P0_DIR / "p0_samples.json")
    require(len(records) == 254, f"P0 record count {len(records)} != 254")
    ids = [record["sample_id"] for record in records]
    require(len(ids) == len(set(ids)), "P0 has duplicate sample_id")
    require(all(record["schema_version"] == "p0-record/v0.2.0" for record in records), "P0 schema version drift")
    require(all(record["annotation"]["status"] == "reviewed" for record in records), "P0 annotation not all reviewed")

    families = {}
    for record in records:
        families.setdefault(record["base_story_id"], set()).add(record["split"])
        require(record["observed_events"][-1]["event_id"] == record["cutoff_event_id"], f"{record['sample_id']} cutoff not last")
        for factor in ("V", "F", "A", "B", "C", "Q"):
            value = record["state_at_cutoff"][factor]
            if value != "UNKNOWN":
                require(
                    bool(record["state_evidence_by_factor"].get(factor)),
                    f"{record['sample_id']} {factor}={value} without evidence",
                )
    require(all(len(splits) == 1 for splits in families.values()), "P0 family crosses splits")

    splits = Counter(record["split"] for record in records)
    require(dict(splits) == {"train": 150, "dev": 52, "test": 52}, f"P0 splits drift: {dict(splits)}")

    inputs = load_jsonl(P0_DIR / "eval" / "inputs.jsonl")
    labels = load_jsonl(P0_DIR / "eval" / "labels.jsonl")
    require(len(inputs) == len(labels) == 254, "P0 eval export is not 254/254")
    require({row["sample_id"] for row in inputs} == set(ids) == {row["sample_id"] for row in labels}, "P0 eval id drift")
    require(all(label["dataset_layer"] == "P0" for label in labels), "P0 eval layer drift")

    factors = {
        factor: sum(1 for record in records if record["state_at_cutoff"][factor] != "UNKNOWN")
        for factor in ("V", "F", "A", "B", "C", "Q")
    }
    files = [
        "p0_samples.json",
        "manifest.json",
        "splits/train.json",
        "splits/dev.json",
        "splits/test.json",
        "splits/calibration.json",
        "eval/inputs.jsonl",
        "eval/labels.jsonl",
    ]
    return {
        "path": rel(P0_DIR),
        "release_version": "p0-release/v0.3.0",
        "record_schema": "p0-record/v0.2.0",
        "dataset_layer": "P0",
        "records": len(records),
        "families": len(families),
        "events": sum(len(record["observed_events"]) for record in records),
        "splits": dict(splits),
        "calibration_records": 0,
        "annotation": {"status": "reviewed", "adjudicated": False},
        "supervised_factors": factors,
        "eval_view": {"path": rel(P0_DIR / "eval"), "records": len(inputs), "protocol": "c-evaluation-draft-1"},
        "files": {name: {"sha256": sha256(P0_DIR / name)} for name in files},
    }


def ready_block(p0: dict) -> dict:
    manifest = load_json(READY_DIR / "manifest.json")
    require(manifest["version"] == "ready-v1.0", "ready-v1 version drift")
    require(manifest["human_P1_records"] == 0, "ready-v1 claims human P1 records")
    require(manifest["sources"]["p0.json"] == p0["files"]["p0_samples.json"]["sha256"], "ready-v1 P0 source differs from P0 release")

    p0_records = {record["sample_id"]: record for record in load_json(P0_DIR / "p0_samples.json")}
    counts = {}
    groups: dict[str, set[str]] = {}
    seen_p0: set[str] = set()
    for split in ("train", "dev", "test"):
        rows = load_jsonl(READY_DIR / f"{split}.jsonl")
        tasks = Counter(row["task"] for row in rows)
        counts[split] = dict(tasks)
        groups[split] = {row["group_id"] for row in rows}
        for row in rows:
            require(row["split"] == split, f"ready-v1 {row['id']} split drift")
            if row["task"] != "state_inference":
                continue
            sample_id = row["id"].split(":", 1)[1]
            require(sample_id not in seen_p0, f"ready-v1 duplicate P0 row {sample_id}")
            seen_p0.add(sample_id)
            record = p0_records[sample_id]
            require(record["split"] == split, f"ready-v1 {sample_id} split differs from P0")
            for factor in ("V", "F", "A", "B", "C", "Q"):
                expected = record["state_at_cutoff"][factor]
                if expected == "UNKNOWN":
                    require(row["state_loss_mask"][factor] == 0, f"ready-v1 {sample_id} {factor} masks UNKNOWN")
                else:
                    require(row["target"].get(factor) == expected, f"ready-v1 {sample_id} {factor} target drift")
                    require(row["state_loss_mask"][factor] == 1, f"ready-v1 {sample_id} {factor} mask drift")

    require(seen_p0 == set(p0_records), "ready-v1 state rows do not cover P0 exactly once")
    require(counts == {"train": {"state_inference": 150, "interruption_response": 288},
                       "dev": {"state_inference": 52, "interruption_response": 71},
                       "test": {"state_inference": 52, "interruption_response": 69}},
            f"ready-v1 task counts drift: {counts}")
    require(not (groups["train"] & groups["dev"] or groups["train"] & groups["test"] or groups["dev"] & groups["test"]),
            "ready-v1 group crosses splits")
    for name, meta in manifest["files"].items():
        require(sha256(READY_DIR / name) == meta["sha256"], f"ready-v1 file hash drift: {name}")
    for name, expected in manifest["sources"].items():
        require(sha256(READY_DIR / "sources" / name) == expected, f"ready-v1 source hash drift: {name}")

    return {
        "path": rel(READY_DIR),
        "release_version": manifest["version"],
        "dataset_layer": "P0 + auxiliary dialogue",
        "human_P1_records": 0,
        "tasks": {"state_inference": 254, "interruption_response": 428},
        "files": {name: {"rows": meta["rows"], "sha256": meta["sha256"]} for name, meta in manifest["files"].items()},
        "sources_p0_sha256": manifest["sources"]["p0.json"],
    }


def p1_block() -> dict:
    rows = load_jsonl(P1_DIR / "processed" / "p1_combined.jsonl")
    require(len(rows) == 2863, f"P1 row count {len(rows)} != 2863")
    require(len({row["sample_id"] for row in rows}) == len(rows), "P1 duplicate sample_id")
    sources = Counter(row["source_dataset"] for row in rows)
    require(dict(sources) == {"IHBench": 856, "InterruptBench": 1815, "REBOOT": 192}, f"P1 source drift: {dict(sources)}")
    censoring = Counter(row["p1_censoring_status"] for row in rows)
    require(dict(censoring) == {"observed_resume": 786, "observed_not_resume": 126, "censored": 1951},
            f"P1 censoring drift: {dict(censoring)}")
    splits = Counter(row["split"] for row in rows)
    require(dict(splits) == {"train": 1996, "val": 499, "test": 368}, f"P1 split drift: {dict(splits)}")

    group_splits: dict[str, set[str]] = {}
    mask_ids = set()
    withdrawn: Counter = Counter()
    for row in rows:
        group_splits.setdefault(row["split_group_id"], set()).add(row["split"])
        events = row["observed_events"]
        require(events[-1]["event_id"] == row["cutoff_event_id"], f"{row['sample_id']} cutoff not last")
        require(
            (row["p1_censoring_status"] == "censored") == (row["p1_observed_resume"] is None),
            f"{row['sample_id']} censoring/label disagree",
        )
        for factor, detail in (row.get("state_withdrawn") or {}).items():
            withdrawn[factor] += 1
            if factor in {"F", "A", "B", "C", "Q"}:
                require(row["state_at_cutoff"][factor] == "UNKNOWN", f"{row['sample_id']} withdrawn {factor} not UNKNOWN")
                require(detail.get("rule") and detail.get("reason"), f"{row['sample_id']} withdrawal lacks rule/reason")
        for factor in ("V", "F", "A", "B", "C", "Q"):
            value = row["state_at_cutoff"][factor]
            expected_mask = 0 if value == "UNKNOWN" else 1
            require(row["state_loss_mask"][factor] == expected_mask, f"{row['sample_id']} {factor} mask/label drift")
        if row.get("resume_loss_mask") == 1:
            mask_ids.add(row["sample_id"])
            require(row["eligible_for_resume_eval"] is True, f"{row['sample_id']} mask without eligibility")
            require(not any(event["event_type"] in ("resume", "completion") for event in events),
                    f"{row['sample_id']} eval row leaks a resume/completion event")
            step = row.get("p1_resume_step")
            if step is not None:
                require(step in row["task_steps"], f"{row['sample_id']} resume_step outside task_steps")
                completed = {event["step_id"] for event in events if event["event_type"] == "completion"}
                require(step not in completed, f"{row['sample_id']} resume_step already completed before cutoff")
    require(all(len(values) == 1 for values in group_splits.values()), "P1 split_group_id crosses splits")
    require(len(group_splits) == 270, f"P1 split group count {len(group_splits)} != 270")

    inputs = load_jsonl(P1_DIR / "eval" / "inputs.jsonl")
    labels = load_jsonl(P1_DIR / "eval" / "labels.jsonl")
    require(len(inputs) == len(labels) == 842, "P1 eval view is not 842/842")
    require({row["sample_id"] for row in inputs} == mask_ids == {row["sample_id"] for row in labels},
            "P1 eval view ids differ from resume_loss_mask=1")
    require(all(label["dataset_layer"] == "P1" for label in labels), "P1 eval layer drift")
    require(all(label["state_labels"].keys() == {"V"} for label in labels), "P1 eval view carries non-V state labels")
    resume_labels = Counter(label["resume_label"] for label in labels)
    require(dict(resume_labels) == {"resume": 716, "not_resume": 126}, f"P1 eval resume labels drift: {dict(resume_labels)}")
    eval_splits = Counter(row["split"] for row in inputs)
    require(dict(eval_splits) == {"train": 603, "dev": 177, "test": 62}, f"P1 eval splits drift: {dict(eval_splits)}")

    doc_rules = {
        "README.md": ("786", "1,951", "2,863"),
        "docs/dataset_card.md": ("**786**", "**1,951**"),
        "docs/coverage_report.md": ("observed_not_resume=126", "786"),
    }
    for name, needles in doc_rules.items():
        text = (P1_DIR / name).read_text(encoding="utf-8")
        for needle in needles:
            require(needle in text, f"P1 doc {name} missing current count {needle}")
        for line in text.splitlines():
            if "修订前" in line:
                continue
            require("1,937" not in line, f"P1 doc {name} still quotes pre-revision censored count")
            require("2,303" not in line, f"P1 doc {name} still quotes pre-revision validation count")
            require("observed_not_resume **138**" not in line, f"P1 doc {name} still quotes pre-revision negative count")

    return {
        "path": rel(P1_DIR),
        "release_version": "p1-public-derived/v1.5.1",
        "dataset_layer": "P1 (public-data derived; no human records)",
        "records": len(rows),
        "sources": dict(sorted(sources.items())),
        "splits": dict(splits),
        "split_groups": len(group_splits),
        "censoring": dict(censoring),
        "resume_eval_view": {
            "path": rel(P1_DIR / "eval"),
            "records": len(inputs),
            "splits": dict(eval_splits),
            "resume_labels": dict(resume_labels),
            "protocol": "c-evaluation-draft-1 (validated with origin/Bill mwm_eval/schema.py)",
        },
        "withdrawn_claims": dict(withdrawn.most_common()),
        "supervised_factors": {
            factor: sum(1 for row in rows if row["state_at_cutoff"][factor] != "UNKNOWN")
            for factor in ("V", "F", "A", "B", "C", "Q")
        },
        "concrete_q_labels": sum(
            1 for row in rows if row["state_at_cutoff"]["Q"] not in ("UNKNOWN", "NOT_APPLICABLE")
        ),
        "files": {
            name: {"sha256": sha256(P1_DIR / name)}
            for name in ("processed/p1_combined.jsonl", "eval/inputs.jsonl", "eval/labels.jsonl",
                         "docs/CHECKSUMS.sha256", "docs/schema.json")
        },
    }


def build() -> dict:
    p0 = p0_block()
    ready = ready_block(p0)
    p1 = p1_block()

    p0_ids = {row["sample_id"] for row in load_jsonl(P0_DIR / "eval" / "inputs.jsonl")}
    p1_ids = {row["sample_id"] for row in load_jsonl(P1_DIR / "eval" / "inputs.jsonl")}
    require(not (p0_ids & p1_ids), "P0 and P1 sample ids overlap")

    return {
        "manifest_version": "data-release/v1",
        "generated_by": "scripts/release_manifest.py",
        "artifacts": {"p0_v03": p0, "ready_v1": ready, "p1_public_derived": p1},
        "routing": {
            "six_factor_supervision": "p0_v03 (SFT bundle: ready_v1)",
            "resume_evaluation": "p1_public_derived/eval (842 observed rows; report per source)",
            "interruption_response_sft": "ready_v1",
            "state_prediction_cutoffs": "p1_public_derived native rows with resume_loss_mask=0",
        },
        "policies": {
            "never_mix": ["P0 and P1 in one metric", "P1 censored rows as negatives", "withdrawn P1 claims as gold"],
            "splits": {
                "P0": {"train": "fit only", "dev": "A model selection; C calibration only if it declares the overlap",
                       "test": "held out", "calibration": "empty by decision"},
                "P1": {"train": "fit only", "val": "calibration / early stopping", "test": "held out"},
            },
            "claims": {
                "human_p1_records": 0,
                "double_blind_adjudication": False,
                "six_factor_supervision_source": "P0 scripted data only",
                "not_resume_ceiling": "126 rows, all IHBench text-agent",
            },
            "licenses": {
                "P0": "project-generated; repository private",
                "IHBench": "CC-BY-4.0 (attribution required)",
                "REBOOT": "Apache-2.0 per source manifest",
                "InterruptBench": "unresolved; internal evaluation only; remove before any redistribution",
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write data/RELEASE.json")
    args = parser.parse_args()

    manifest = build()
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {rel(OUT)}")
        return 0

    if not OUT.exists():
        fail("data/RELEASE.json is missing; run with --write")
    committed = json.loads(OUT.read_text(encoding="utf-8"))
    if committed != manifest:
        fail("data/RELEASE.json is stale; run python scripts/release_manifest.py --write")
    print("OK: data/RELEASE.json matches all three artifacts and their invariants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
