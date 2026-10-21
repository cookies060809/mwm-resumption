"""Versioned C-side adaptation of B's frozen P0 v0.2. No source data edits."""

import copy
from collections import defaultdict

from scripts.export_eval_format import to_input, to_label
from mwm_eval.schema import validate_dataset

ADAPTER_VERSION = "c-p0-v02-adapter/1.1.0"
CONTENT = {"cancellation": "cancellation", "completion_by_other": "fulfillment",
           "resource_available": "resource_ready", "resource_missing": "resource_blocked",
           "commitment": "commitment_resume", "abandonment": "goal_abandoned"}


def adapt_input(record, include_structured=True):
    """Read only pre-cutoff input fields; never inspect any supervision."""
    if record.get("schema_version") != "p0-record/v0.2.0":
        raise ValueError("C P0 adapter requires p0-record/v0.2.0")
    mapped = copy.deepcopy(to_input(record))
    # A fixed role token avoids leaking family/mechanism IDs into the model.
    mapped["observation"]["target_person"] = "person"
    for event, original in zip(mapped["observation"]["events"], record["observed_events"]):
        semantics = original.get("person_available_semantics") or {}
        if original["event_type"] == "notification_sent":
            content = CONTENT.get(semantics.get("kind"))
            # The type comes from annotated message CONTENT, never world status/gold.
            # Accessibility/comprehension remain independent gates in the predictor.
            if content:
                event["semantic"]["value"] = content
            else:
                event["semantic"].pop("value", None)
        if original["event_type"] in {"interruption_started", "interruption_ended"}:
            # B's goal_id denotes the interrupted goal, not the interrupting goal.
            # No nested completion snapshots or invented child IDs are introduced.
            event["semantic"].pop("interrupting_goal_id", None)
    if include_structured:
        from models.ecr_mwm.p0_adapter import adapt_record
        mapped["observation"]["structured_evidence"] = adapt_record(record)
    return mapped


def prepare_dataset(source):
    inputs = [adapt_input(record) for record in source]
    golds = [to_label(record) for record in source]
    groups = defaultdict(list)
    for gold in golds:
        gold["pair_mechanism"] = gold.pop("pair_factor")
        groups[gold["pair_id"]].append(gold)
    for pair_id, members in groups.items():
        if len(members) != 2 or len({m["pair_mechanism"] for m in members}) != 1:
            raise ValueError(f"{pair_id}: exactly two members with one mechanism required")
        checks = []
        if all(m["resume_label"] in {"resume", "not_resume"} for m in members):
            checks.append({"target": "T1", "relation": "match_gold"})
        if all(m.get("resume_step") is not None for m in members):
            checks.append({"target": "T2", "relation": "match_gold"})
        for factor in ("V", "F", "A", "B", "C", "Q"):
            if all(m["state_labels"].get(factor) not in {None, "UNKNOWN", "UNCERTAIN"}
                   and m["state_evidence"].get(factor) for m in members):
                checks.append({"target": factor, "relation": "match_gold"})
        if members[0]["pair_mechanism"] == "future_leak":
            checks += [{"target": target, "relation": "equal"} for target in
                       ("hard_decision", "p_resume", "state_probs", "conditional_step_probs")]
        for member in members:
            member["pair_checks"] = copy.deepcopy(checks)
    validate_dataset(inputs, golds)
    return inputs, golds
