"""Validate the ECR-MWM P0 datasets (v0.1 seed and v0.2 full batch).

Checks JSON Schema structure plus cross-field invariants the schema cannot
express: cutoff ordering, evidence chains, per-factor evidence, action/step
alignment, resource/task implications, comprehension vs access, family-level
split integrity, and future-leakage controls.

Usage:
    python scripts/validate_data.py
    python scripts/validate_data.py --file data/p0/p0_samples_v0.2.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "p0-record/v0.1.0": ROOT / "schema" / "p0_record.schema.json",
    "p0-record/v0.2.0": ROOT / "schema" / "p0_record_v0.2.schema.json",
}
DATA_FILES = (
    ROOT / "data" / "p0" / "p0_samples.json",
    ROOT / "data" / "p0" / "p0_samples_v0.2.json",
)
DATA_PATH = DATA_FILES[0]


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_records(path: Path = DATA_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_json(path)


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

        # v0.2: comprehension (U) may only be a positive label when the person
        # actually received the event, and must be NOT_APPLICABLE otherwise.
        comprehension = event.get("person_comprehension")
        if comprehension is not None:
            access = event.get("person_access")
            if access != "ACCESSED" and comprehension != "NOT_APPLICABLE":
                err(
                    f"event {event.get('event_id')}: comprehension={comprehension} "
                    f"requires person_access=ACCESSED (got {access})"
                )
            semantics = event.get("person_available_semantics") or {}
            if comprehension == "MISUNDERSTOOD" and semantics.get("interpretation") not in (
                "defer",
                "complete",
                "unresolved",
            ):
                err(
                    f"event {event.get('event_id')}: MISUNDERSTOOD requires a "
                    "non-accurate interpretation"
                )

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
    design = record.get("p0_design") or {}

    if action == "indeterminate":
        if resume is not None or first_step is not None:
            err("indeterminate action requires resume_within_horizon=null and first_step=null")
        if not design.get("undefined_target"):
            err("indeterminate action requires p0_design.undefined_target=true")
        if expected.get("undefined_reason") != "indistinguishable_inputs":
            err("indeterminate action requires undefined_reason=indistinguishable_inputs")
    elif resume is None:
        err(f"action {action!r} must not leave resume_within_horizon=null")

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
    elif action != "indeterminate":
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

    seen_samples: set[str] = set()
    for record in records:
        sample_id = record.get("sample_id")
        if sample_id in seen_samples:
            errors.append(f"duplicate sample_id: {sample_id}")
        seen_samples.add(sample_id)

    for story_id, pair in sorted(by_story.items()):
        variants = [record.get("variant") for record in pair]
        if sorted(variants) != ["A", "B"] or len(pair) != 2:
            errors.append(f"{story_id}: expected exactly one A and one B record")
            continue

        splits = {record.get("split") for record in pair}
        if len(splits) > 1:
            errors.append(f"{story_id}: A/B variants must share one split")
        if splits and splits != {None} and None in splits:
            errors.append(f"{story_id}: split must be set on every record")

        if story_id.startswith("P07"):
            a, b = sorted(pair, key=lambda record: record["variant"])
            ignore = {"sample_id", "variant", "notes"}
            a_core = {key: value for key, value in a.items() if key not in ignore}
            b_core = {key: value for key, value in b.items() if key not in ignore}
            if not equal_json(a_core, b_core):
                errors.append(f"{story_id}-A/B: pre-cutoff inputs are not identical")
            for record in pair:
                if "未来泄漏" not in record.get("notes", ""):
                    errors.append(
                        f"{story_id}-{record['variant']}: notes must document the future-leakage design"
                    )
                design = record.get("p0_design") or {}
                if record.get("p0_design") is not None and not design.get("undefined_target"):
                    errors.append(
                        f"{story_id}-{record['variant']}: future-leak pair needs undefined_target=true"
                    )


def print_summary(records: list[dict[str, Any]], label: str) -> None:
    print(f"--- {label}: {len(records)} records ---")
    if len(records) <= 40:
        print(
            f"{'sample':13} {'V':10} {'F':8} {'A':13} {'B':18} "
            f"{'C':11} {'Q':16} expected"
        )
        for record in records:
            state = record.get("state_at_cutoff", {})
            print(
                f"{record.get('sample_id', '?'):13} "
                f"{state.get('V', '?'):10} {state.get('F', '?'):8} "
                f"{state.get('A', '?'):13} {state.get('B', '?'):18} "
                f"{state.get('C', '?'):11} {state.get('Q', '?'):16} "
                f"{record.get('p0_expected_action', '?')}"
            )
    domains = Counter(record.get("domain", "?") for record in records)
    statuses = Counter(
        record.get("annotation", {}).get("status", "?") for record in records
    )
    print("domains:", dict(domains))
    print("annotation status:", dict(statuses))
    if records and "mechanism" in records[0]:
        print("mechanisms:", dict(Counter(record.get("mechanism") for record in records)))
        families = {record["base_story_id"] for record in records}
        split_by_family = {
            record["base_story_id"]: record.get("split") for record in records
        }
        print(
            "splits(families):",
            dict(Counter(split_by_family[family] for family in families)),
        )
        print("events:", sum(len(record.get("observed_events", [])) for record in records))


def validate_records(
    records: list[dict[str, Any]], schema_path: Path | None = None
) -> list[str]:
    errors: list[str] = []
    schema = load_json(schema_path or SCHEMAS["p0-record/v0.1.0"])
    Draft7Validator.check_schema(schema)
    validators: dict[str, Draft7Validator] = {}
    default_validator = Draft7Validator(schema)
    for version, path in SCHEMAS.items():
        if path.exists():
            validators[version] = Draft7Validator(load_json(path))

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"$[{index}]: record is not an object")
            continue
        version = record.get("schema_version")
        validator = validators.get(version, default_validator)
        for error in sorted(
            validator.iter_errors(record), key=lambda item: list(item.absolute_path)
        ):
            errors.append(f"$[{index}] {error.json_path}: {error.message}")
        check_record(record, errors)

    check_pairs(records, errors)
    return errors


def validate_file(path: Path, verbose: bool = True) -> list[str]:
    records = load_json(path)
    if not isinstance(records, list):
        return [f"{path.name}: data file must contain a JSON array"]
    errors = validate_records(records)
    if verbose:
        print_summary(records, path.name)
        if errors:
            for message in errors[:40]:
                print(f"  - {message}", file=sys.stderr)
            if len(errors) > 40:
                print(f"  ... {len(errors) - 40} more", file=sys.stderr)
            print(f"FAILED with {len(errors)} error(s).", file=sys.stderr)
        else:
            pair_count = len({record.get("base_story_id") for record in records})
            print(
                f"OK: {len(records)} records, {pair_count} A/B pairs; "
                "schema and cross-field checks passed."
            )
    return errors


def validate_all(verbose: bool = True) -> list[str]:
    errors: list[str] = []
    for path in DATA_FILES:
        if path.exists():
            errors.extend(validate_file(path, verbose=verbose))
    return errors


def main() -> int:
    if "--file" in sys.argv:
        path = Path(sys.argv[sys.argv.index("--file") + 1])
        return 1 if validate_file(path) else 0
    return 1 if validate_all(verbose=True) else 0


if __name__ == "__main__":
    raise SystemExit(main())
