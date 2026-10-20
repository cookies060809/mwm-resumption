"""Validate ECR-MWM P0 records and P1 templates against the v0.1 schemas."""

from __future__ import annotations

import json
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schema"
SCHEMA_FILES = (
    "events.schema.json",
    "task_graph.schema.json",
    "state.schema.json",
    "annotation.schema.json",
)
SENTINEL_Q = {"UNKNOWN", "NOT_APPLICABLE"}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_validator() -> Draft202012Validator:
    schemas = {name: load_json(SCHEMA_DIR / name) for name in SCHEMA_FILES}
    registry = Registry().with_resources(
        (
            schema["$id"],
            Resource.from_contents(schema, default_specification=DRAFT202012),
        )
        for schema in schemas.values()
    )
    return Draft202012Validator(schemas["annotation.schema.json"], registry=registry)


def parse_time(value: Any) -> datetime | time | None:
    if not isinstance(value, str):
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def semantic_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    steps = record["task_graph"]["steps"]
    step_ids = [step["step_id"] for step in steps]
    step_id_set = set(step_ids)

    if len(step_ids) != len(step_id_set):
        errors.append("task_graph has duplicate step_id values")
    if record["task_graph"]["goal_id"] != record["goal_id"]:
        errors.append("task_graph.goal_id does not match goal_id")
    for step in steps:
        unknown = set(step["depends_on"]) - step_id_set
        if unknown:
            errors.append(
                f"step {step['step_id']!r} depends on unknown steps: {sorted(unknown)}"
            )
        if step["step_id"] in step["depends_on"]:
            errors.append(f"step {step['step_id']!r} depends on itself")

    events = record["observed_events"]
    event_ids = [event["event_id"] for event in events]
    event_id_set = set(event_ids)
    if len(event_ids) != len(event_id_set):
        errors.append("observed_events has duplicate event_id values")
    if record["cutoff_event_id"] not in event_id_set:
        errors.append(
            f"cutoff_event_id {record['cutoff_event_id']!r} is not in observed_events"
        )

    for event in events:
        if event["goal_id"] is not None and event["goal_id"] != record["goal_id"]:
            errors.append(
                f"event {event['event_id']!r} has goal_id {event['goal_id']!r} "
                f"but record goal_id is {record['goal_id']!r}"
            )
        if event["step_id"] is not None and event["step_id"] not in step_id_set:
            errors.append(
                f"event {event['event_id']!r} references unknown step "
                f"{event['step_id']!r}"
            )

    evidence = set(record["state_evidence_event_ids"])
    missing_evidence = evidence - event_id_set
    if missing_evidence:
        errors.append(
            "state_evidence_event_ids not observed: "
            f"{sorted(missing_evidence)}"
        )

    q_value = record["state_at_cutoff"]["Q"]
    if q_value not in SENTINEL_Q and q_value not in step_id_set:
        errors.append(f"state_at_cutoff.Q references unknown step {q_value!r}")

    cutoff_event = next(
        (event for event in events if event["event_id"] == record["cutoff_event_id"]),
        None,
    )
    if cutoff_event is not None:
        cutoff_time = parse_time(cutoff_event["time"])
        if cutoff_time is not None:
            for event in events:
                event_time = parse_time(event["time"])
                if event_time is None or type(event_time) is not type(cutoff_time):
                    continue
                try:
                    if event_time > cutoff_time:
                        errors.append(
                            f"event {event['event_id']!r} occurs after cutoff "
                            f"{record['cutoff_event_id']!r}"
                        )
                except TypeError:
                    continue

    p0 = record.get("p0_expectation")
    if p0 is not None:
        expected_step = p0["expected_resume_step"]
        if expected_step is not None and expected_step not in step_id_set:
            errors.append(f"p0_expectation references unknown step {expected_step!r}")
        if p0["expected_resume"] and expected_step is None:
            errors.append("p0_expectation.expected_resume is true but no step is given")
        if not p0["expected_resume"] and expected_step is not None:
            errors.append(
                "p0_expectation.expected_resume is false but a step is given"
            )

    p1 = record.get("p1_observation")
    if p1 is not None:
        resume_step = p1["resume_step"]
        if resume_step is not None and resume_step not in step_id_set:
            errors.append(f"p1_observation references unknown step {resume_step!r}")
        if p1["observed_resume"] is True and resume_step is None:
            errors.append("p1_observation.observed_resume is true but no step is given")
        if p1["observed_resume"] is not True and resume_step is not None:
            errors.append(
                "p1_observation.resume_step is set but observed_resume is not true"
            )
        if (
            p1["censoring_status"] == "complete_window"
            and p1["observed_resume"] is None
        ):
            errors.append(
                "p1_observation.censoring_status is complete_window but "
                "observed_resume is null"
            )
        if (
            p1["censoring_status"] == "not_collected"
            and p1["observed_resume"] is not None
        ):
            errors.append(
                "p1_observation.censoring_status is not_collected but "
                "observed_resume is not null"
            )

    return errors


def pair_errors(
    records: dict[str, dict[str, Any]], record_paths: dict[str, str]
) -> list[str]:
    errors: list[str] = []
    for sample_id, record in records.items():
        pair = record.get("counterfactual_pair")
        if pair is None:
            continue
        path = record_paths[sample_id]
        other_id = pair["paired_sample_id"]
        other = records.get(other_id)
        if other is None:
            errors.append(f"{path}: paired_sample_id {other_id!r} not found")
            continue
        other_pair = other.get("counterfactual_pair")
        if other_pair is None or other_pair.get("paired_sample_id") != sample_id:
            errors.append(
                f"{path}: counterfactual_pair is not reciprocal with {other_id!r}"
            )
        if record["base_story_id"] != other["base_story_id"]:
            errors.append(f"{path}: paired records use different base_story_id")
        if record["pair_id"] != other["pair_id"]:
            errors.append(f"{path}: paired records use different pair_id")
        if record["variant_id"] == other["variant_id"]:
            errors.append(f"{path}: paired records use the same variant_id")
        if record["split"] != other["split"]:
            errors.append(f"{path}: paired records use different split values")
        if pair["information_equivalence"] != other_pair.get("information_equivalence"):
            errors.append(
                f"{path}: paired records disagree on information_equivalence"
            )
    return errors


def validate_all(verbose: bool = True) -> list[str]:
    validator = build_validator()
    errors: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    record_paths: dict[str, str] = {}

    data_paths = sorted((ROOT / "data" / "p0").rglob("*.json"))
    p1_templates = ROOT / "data" / "p1" / "templates"
    if p1_templates.exists():
        data_paths.extend(sorted(p1_templates.rglob("*.json")))

    for path in data_paths:
        relative = str(path.relative_to(ROOT))
        record = load_json(path)
        schema_errors = sorted(
            validator.iter_errors(record), key=lambda error: list(error.absolute_path)
        )
        if schema_errors:
            for error in schema_errors:
                location = "/".join(str(part) for part in error.absolute_path) or "<root>"
                errors.append(f"{relative}: {location}: {error.message}")
            continue

        errors.extend(f"{relative}: {message}" for message in semantic_errors(record))
        sample_id = record["sample_id"]
        if sample_id in records:
            errors.append(
                f"{relative}: duplicate sample_id {sample_id!r} "
                f"also used in {record_paths[sample_id]}"
            )
            continue
        records[sample_id] = record
        record_paths[sample_id] = relative

    errors.extend(pair_errors(records, record_paths))

    if verbose:
        for error in errors:
            print(error, file=sys.stderr)
        print(
            f"Validated {len(data_paths)} record file(s); "
            f"{len(errors)} error(s)."
        )
    return errors


def main() -> int:
    errors = validate_all(verbose=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
