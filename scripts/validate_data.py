"""Validate the ECR-MWM P0 seed dataset.

Checks JSON Schema structure plus cross-field invariants that the schema cannot
express: cutoff ordering, evidence chains, per-factor evidence, action/step
alignment, resource/task implications, and P07 input identity.

Usage: python scripts/validate_data.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "p0_record.schema.json"
DATA_PATH = ROOT / "data" / "p0" / "p0_samples.json"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_records() -> list[dict[str, Any]]:
    return load_json(DATA_PATH)


def equal_json(left: Any, right: Any) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(
        right, ensure_ascii=False, sort_keys=True
    )


def non_unknown(factor: str, value: Any) -> bool:
    if factor == "Q":
        return value not in ("UNKNOWN",)
    return value != "UNKNOWN"


def check_record(record: dict[str, Any], errors: list[str]) -> None:
    sample_id = record.get("sample_id", "<unknown>")

    def err(message: str) -> None:
        errors.append(f"{sample_id}: {message}")

    events = record.get("observed_events", [])
    if not isinstance(events, list) or not events:
        err("observed_events is empty or not an array")
        return

    event_by_id = {event.get("event_id"): event for event in events}
    if len(event_by_id) != len(events):
        err("duplicate event_id")

    if record.get("sample_id") != (
        f"{record.get('base_story_id')}-{record.get('variant')}"
    ):
        err("sample_id does not match base_story_id-variant")
    if events[-1].get("event_id") != record.get("cutoff_event_id"):
        err("cutoff_event_id is not the last observed event")

    times = [event.get("time", "") for event in events]
    if times != sorted(times):
        err("event times are not non-decreasing")
    cutoff_time = events[-1].get("time")
    if any(event.get("time", "") > cutoff_time for event in events):
        err("event after cutoff")

    allowed_goals = {record.get("goal_id")}
    interrupting = record.get("interrupting_task")
    if interrupting:
        allowed_goals.add(interrupting.get("goal_id"))
        if interrupting.get("parent_goal_id") != record.get("goal_id"):
            err("interrupting_task.parent_goal_id does not match top-level goal_id")
        if not set(interrupting.get("completed_steps_at_cutoff", [])).issubset(
            set(interrupting.get("steps", []))
        ):
            err("interrupting_task completed steps not subset of its steps")

    for event in events:
        goal = event.get("goal_id")
        if goal is not None and goal not in allowed_goals:
            err(f"event {event.get('event_id')} references unexpected goal_id {goal!r}")
        if event.get("actor") == "person" and event.get("person_access") != "ACCESSED":
            err(f"person event {event.get('event_id')} must be ACCESSED")

    steps = set(record.get("task_steps", []))
    completed = set(record.get("completed_steps_at_cutoff", []))
    if not completed.issubset(steps):
        err("completed_steps_at_cutoff not subset of task_steps")
    for dependency in record.get("task_dependencies", []):
        if dependency.get("before") not in steps or dependency.get("after") not in steps:
            err(f"task dependency references unknown step: {dependency}")

    state = record.get("state_at_cutoff", {})
    evidence = record.get("state_evidence_by_factor", {})
    if set(evidence) != {"V", "F", "A", "B", "C", "Q"}:
        err("state_evidence_by_factor must have exactly V/F/A/B/C/Q")

    for factor, value in state.items():
        ids = evidence.get(factor, [])
        unknown_ids = [event_id for event_id in ids if event_id not in event_by_id]
        if unknown_ids:
            err(f"{factor} evidence references unknown events {unknown_ids}")
        if non_unknown(factor, value) and not ids:
            err(f"{factor}={value} requires at least one evidence event")
        if factor != "Q" and value == "UNKNOWN" and ids:
            err(f"{factor}=UNKNOWN should not carry positive evidence")

    ordered_ids = [event.get("event_id") for event in events]
    expected_flat = [
        event_id
        for event_id in ordered_ids
        if any(event_id in ids for ids in evidence.values())
    ]
    if record.get("state_evidence_event_ids") != expected_flat:
        err("state_evidence_event_ids is not the ordered union of per-factor evidence")

    q_value = state.get("Q")
    all_steps = set(record.get("task_steps", []))
    if interrupting:
        all_steps |= set(interrupting.get("steps", []))
    if q_value not in ("UNKNOWN", "NOT_APPLICABLE") and q_value not in all_steps:
        err(f"Q={q_value!r} is neither a known step nor UNKNOWN/NOT_APPLICABLE")

    commitment = state.get("C")
    if commitment in ("ABANDONED", "COMPLETED") and q_value != "NOT_APPLICABLE":
        err("C=ABANDONED/COMPLETED requires Q=NOT_APPLICABLE")
    if q_value == "NOT_APPLICABLE" and commitment not in ("ABANDONED", "COMPLETED"):
        err("Q=NOT_APPLICABLE requires C=ABANDONED/COMPLETED")

    expected = record.get("p0_expected", {})
    first_step = expected.get("first_step")
    action = record.get("p0_expected_action", "")
    resume = expected.get("resume_within_horizon")
    if first_step is not None and first_step not in all_steps:
        err(f"p0_expected.first_step={first_step!r} is not a known step")
    if action.startswith("resume_"):
        action_step = action[len("resume_") :]
        if first_step != action_step:
            err("p0_expected_action step does not match p0_expected.first_step")
        if action_step in record.get("task_steps", []):
            if resume is not True:
                err("resuming an original task step requires resume_within_horizon=true")
        elif interrupting and action_step in interrupting.get("steps", []):
            if not isinstance(resume, bool):
                err("nested-task resume must set resume_within_horizon explicitly")
        else:
            err("resume action references a step outside both task graphs")
    else:
        if first_step is not None:
            err("non-resume action must have first_step=null")
        if resume is not False:
            err("non-resume action must have resume_within_horizon=false")

    if record.get("p1_censoring_status") == "not_collected":
        if record.get("p1_observed_resume") is not None:
            err("P0 not_collected record must keep p1_observed_resume=null")
        if record.get("p1_observed_first_step") is not None:
            err("P0 not_collected record must keep p1_observed_first_step=null")

    for label, value in state.items():
        if label == "V":
            if any(
                event.get("event_type") == "task_cancelled"
                and event.get("goal_id") == record.get("goal_id")
                for event in events
            ) and value != "CANCELLED":
                err("task_cancelled event implies V=CANCELLED")
            if any(
                event.get("event_type") == "task_completed_by_other"
                and event.get("goal_id") == record.get("goal_id")
                for event in events
            ) and value != "FULFILLED":
                err("task_completed_by_other implies V=FULFILLED")
        if label == "F":
            if any(event.get("event_type") == "resource_missing" for event in events) and value != "BLOCKED":
                err("resource_missing implies F=BLOCKED")
            if any(event.get("event_type") == "resource_available" for event in events) and value != "READY":
                err("resource_available implies F=READY")

    interruption = record.get("interruption")
    if interruption:
        if interruption.get("start_event_id") not in event_by_id:
            err("interruption.start_event_id does not exist")
        end_id = interruption.get("end_event_id")
        if end_id is not None and end_id not in event_by_id:
            err("interruption.end_event_id does not exist")


def check_pairs(records: list[dict[str, Any]], errors: list[str]) -> None:
    by_story: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_story[record.get("base_story_id")].append(record)

    for story_id, pair in sorted(by_story.items()):
        variants = {record.get("variant") for record in pair}
        if variants != {"A", "B"} or len(pair) != 2:
            errors.append(f"{story_id}: expected exactly one A and one B record")
            continue
        if story_id == "P07":
            a, b = sorted(pair, key=lambda record: record["variant"])
            ignore = {"sample_id", "variant", "notes"}
            a_core = {key: value for key, value in a.items() if key not in ignore}
            b_core = {key: value for key, value in b.items() if key not in ignore}
            if not equal_json(a_core, b_core):
                errors.append("P07-A/B: pre-cutoff inputs are not identical")
            if "未来泄漏" not in a.get("notes", "") or "未来泄漏" not in b.get(
                "notes", ""
            ):
                errors.append("P07-A/B: notes must document the future-leakage design")


def print_summary(records: list[dict[str, Any]]) -> None:
    print(
        f"{'sample':7} {'V':10} {'F':8} {'A':13} {'B':18} "
        f"{'C':11} {'Q':16} expected"
    )
    for record in records:
        state = record.get("state_at_cutoff", {})
        print(
            f"{record.get('sample_id', '?'):7} "
            f"{state.get('V', '?'):10} {state.get('F', '?'):8} "
            f"{state.get('A', '?'):13} {state.get('B', '?'):18} "
            f"{state.get('C', '?'):11} {state.get('Q', '?'):16} "
            f"{record.get('p0_expected_action', '?')}"
        )
    domains = Counter(record.get("domain", "?") for record in records)
    statuses = Counter(
        record.get("annotation", {}).get("status", "?") for record in records
    )
    print()
    print("domains:", dict(domains))
    print("annotation status:", dict(statuses))


def validate_records(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    schema = load_json(SCHEMA_PATH)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"$[{index}]: record is not an object")
            continue
        for error in sorted(
            validator.iter_errors(record), key=lambda item: list(item.absolute_path)
        ):
            errors.append(f"$[{index}] {error.json_path}: {error.message}")
        check_record(record, errors)

    check_pairs(records, errors)
    return errors


def validate_all(verbose: bool = True) -> list[str]:
    records = load_records()
    if not isinstance(records, list):
        return ["data file must contain a JSON array"]

    errors = validate_records(records)
    if verbose:
        print_summary(records)
        if errors:
            for message in errors:
                print(f"  - {message}", file=sys.stderr)
            print(f"FAILED with {len(errors)} error(s).", file=sys.stderr)
        else:
            pair_count = len({record.get("base_story_id") for record in records})
            print(
                f"OK: {len(records)} records, {pair_count} A/B pairs; "
                "schema and cross-field checks passed."
            )
    return errors


def main() -> int:
    return 1 if validate_all(verbose=True) else 0


if __name__ == "__main__":
    raise SystemExit(main())
