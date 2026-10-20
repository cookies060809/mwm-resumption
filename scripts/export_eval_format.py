"""Export P0 v0.2 to C's evaluation protocol (`c-evaluation-draft-1`).

C's engine reads two JSONL files: `inputs.jsonl` (metadata + observation) and
`labels.jsonl` (one gold per sample). Without this exporter every consumer has
to invent the mapping, which is how label semantics drift. The mapping below is
deliberately mechanical and lossless where the protocols overlap; anything C's
protocol cannot express is listed in `MAPPING_NOTES`.

Usage:
    python scripts/export_eval_format.py
    python scripts/export_eval_format.py --data data/p0/p0_samples_v0.2.json \
        --out-dir data/p0/eval_v0.2
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "p0" / "p0_samples_v0.2.json"
DEFAULT_OUT = ROOT / "data" / "p0" / "eval_v0.2"

# B event_type -> (C event_type, action_status, semantic.kind)
EVENT_MAP: dict[str, tuple[str, str | None, str]] = {
    "goal_start": ("goal_started", None, "goal_started"),
    "goal_abandoned": ("goal_abandoned", None, "goal_abandoned"),
    "step_started": ("task_action", "in_progress", "task_action"),
    "step_completed": ("task_action", "completed", "step_completed"),
    "step_attempted": ("task_action", "in_progress", "task_action"),
    "interruption_started": ("interruption_started", None, "interruption_started"),
    "interruption_ended": ("interruption_ended", None, "interruption_ended"),
    "return_to_task": ("location_returned", None, "location_returned"),
    "person_action": ("person_action", None, "task_action"),
    "person_statement": ("person_statement", None, "person_statement"),
    "commitment_expressed": ("commitment_resume", None, "commitment_resume"),
    "task_cancelled": ("cancellation", None, "cancellation"),
    "task_completed_by_other": ("fulfillment", None, "fulfillment"),
    "notification_sent": ("notification", None, "notification_understood"),
    "resource_available": ("resource_ready", None, "resource_ready"),
    "resource_missing": ("resource_blocked", None, "resource_blocked"),
}

CERTAINTY = {"CERTAIN": 1.0, "PROBABLE": 0.75, "UNCERTAIN": 0.5}
UNDERSTOOD = {"UNDERSTOOD": True, "MISUNDERSTOOD": False, "NOT_UNDERSTOOD": False}
MESSAGE_LIKE = {
    "task_cancelled",
    "task_completed_by_other",
    "notification_sent",
    "person_statement",
    "commitment_expressed",
    "goal_abandoned",
}

MAPPING_NOTES = """\
Mapping notes (B -> C), protocol c-evaluation-draft-1
----------------------------------------------------
* HH:MM -> same-day integer minutes for both `time` and `cutoff`; P0 has no date,
  so no cross-day or late-arrival evidence can be represented.
* task_dependencies{before, after} -> task_graph.edges.
* person_access -> person_access_evidence.status; person_comprehension
  UNDERSTOOD/MISUNDERSTOOD/NOT_UNDERSTOOD -> understood true/false/false;
  anything else -> null (unknown, not false).
* person_available_semantics.kind/value/interpretation -> semantic.kind/value/interpretation.
* person_id = target_person = one synthetic person per family; task_family is the
  task blueprint, and the split is blueprint-disjoint so task_family never
  crosses splits. These are identifiers for leakage audits, not real people.
* purpose = "scripted_p0" (never "synthetic_integration_fixture").
* resume_label: indeterminate (future-leak) -> "unknown"; resume_within_horizon
  true -> "resume" with resume_step; otherwise "not_resume" with null step.
  The nested first step of nested_interruption pairs is dropped here because
  C's gold schema only accepts target-task steps as resume_step.
* window_complete is true by construction: P0 windows are scripted, not observed.
* dataset_layer = "P0" for every record; never mix with P1 or C's fixtures.
* Not representable in C's protocol: state_evidence_by_factor granularity is kept,
  but p0_design/notes/annotation and the `mechanism` key stay behind (mechanism is
  carried in gold.pair_factor instead).
"""


def minutes(value: str) -> int:
    hours, minute = value.split(":")
    return int(hours) * 60 + int(minute)


def map_event(event: dict[str, Any]) -> dict[str, Any]:
    c_type, action_status, kind = EVENT_MAP[event["event_type"]]
    semantics = event.get("person_available_semantics") or {}
    semantic: dict[str, Any] = {"kind": kind}
    if event["event_type"] in MESSAGE_LIKE:
        value = semantics.get("value") or event.get("description")
        if value:
            semantic["value"] = value
    interpretation = semantics.get("interpretation")
    if interpretation and interpretation != "none":
        semantic["interpretation"] = interpretation
    if event["person_comprehension"] == "MISUNDERSTOOD" and "interpretation" not in semantic:
        semantic["interpretation"] = "defer"
    if event["event_type"] == "interruption_started" and event.get("goal_id"):
        semantic["interrupting_goal_id"] = event["goal_id"]

    mapped: dict[str, Any] = {
        "event_id": event["event_id"],
        "time": minutes(event["time"]),
        "actor": event["actor"],
        "event_type": c_type,
        "goal_id": event["goal_id"],
        "step_id": event["step_id"],
        "world_effect": event["world_effect"],
        "observer_evidence": event["observer_evidence"] or event["description"],
        "person_access_evidence": {
            "status": event["person_access"],
            "understood": UNDERSTOOD.get(event["person_comprehension"]),
        },
        "source": event["source"],
        "certainty": CERTAINTY[event["certainty"]],
        "semantic": semantic,
    }
    if action_status is not None:
        mapped["action_status"] = action_status
    return mapped


def person_id(record: dict[str, Any]) -> str:
    return f"person_{record['base_story_id'].lower().replace('-', '_')}"


def task_family(record: dict[str, Any]) -> str:
    family = record["base_story_id"]
    if "-" in family:
        return family.split("-", 1)[1]
    return f"seed_{family.lower()}"


def to_input(record: dict[str, Any]) -> dict[str, Any]:
    events = [map_event(event) for event in record["observed_events"]]
    return {
        "sample_id": record["sample_id"],
        "base_story_id": record["base_story_id"],
        "person_id": person_id(record),
        "task_family": task_family(record),
        "domain": record["domain"],
        "split": record["split"],
        "purpose": "scripted_p0",
        "observation": {
            "target_person": person_id(record),
            "goal_id": record["goal_id"],
            "task_steps": list(record["task_steps"]),
            "task_graph": {
                "nodes": list(record["task_steps"]),
                "edges": [[edge["before"], edge["after"]] for edge in record["task_dependencies"]],
            },
            "cutoff": minutes(record["observed_events"][-1]["time"]),
            "horizon": {
                "type": record["horizon"]["type"],
                "value": record["horizon"]["value"],
            },
            "events": events,
        },
    }


def to_label(record: dict[str, Any]) -> dict[str, Any]:
    expected = record["p0_expected"]
    action = record["p0_expected_action"]
    steps = set(record["task_steps"])
    if action == "indeterminate":
        resume_label, resume_step = "unknown", None
    elif expected["resume_within_horizon"] is True:
        resume_label = "resume"
        resume_step = expected["first_step"] if expected["first_step"] in steps else None
    else:
        resume_label, resume_step = "not_resume", None
    return {
        "sample_id": record["sample_id"],
        "dataset_layer": "P0",
        "resume_label": resume_label,
        "resume_step": resume_step,
        "state_labels": dict(record["state_at_cutoff"]),
        "state_evidence": {key: list(value) for key, value in record["state_evidence_by_factor"].items()},
        "window_complete": True,
        "pair_id": record["base_story_id"],
        "pair_factor": record["mechanism"],
        "annotation_source": "scripted P0 expectation, B-reviewed",
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    records = json.loads(args.data.read_text(encoding="utf-8"))
    records.sort(key=lambda record: (record["base_story_id"], record["variant"]))
    inputs = [to_input(record) for record in records]
    labels = [to_label(record) for record in records]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "inputs.jsonl", inputs)
    write_jsonl(args.out_dir / "labels.jsonl", labels)
    (args.out_dir / "MAPPING.md").write_text(MAPPING_NOTES, encoding="utf-8", newline="\n")

    splits: dict[str, int] = {}
    resume: dict[str, int] = {}
    for record in records:
        splits[record["split"]] = splits.get(record["split"], 0) + 1
    for label in labels:
        resume[label["resume_label"]] = resume.get(label["resume_label"], 0) + 1

    print(f"wrote {len(inputs)} inputs and {len(labels)} labels to {args.out_dir.relative_to(ROOT)}")
    print("records per split:", {k: v for k, v in splits.items() if k in ("train", "dev", "test", "calibration")})
    print("resume_label:", resume)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
