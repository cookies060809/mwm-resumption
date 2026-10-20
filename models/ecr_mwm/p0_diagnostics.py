"""Controlled diagnostics on repository P0; no behavioral predictions."""
from collections import Counter
from copy import deepcopy
from .p0_adapter import (adapt_record, person_inputs, replay_completion_evidence,
                         scripted_targets)


def run_diagnostics(records):
    from scripts.validate_data import validate_records
    errors = validate_records(records)
    if errors:
        raise ValueError("REPOSITORY_DATA_INVALID: " + "; ".join(errors))
    views = {record["sample_id"]: adapt_record(record) for record in records}
    rows = []
    for record in records:
        view = views[record["sample_id"]]
        replay = replay_completion_evidence(view)
        goal = record["goal_id"]
        matches = set(replay["world_done"][goal]) == set(record["completed_steps_at_cutoff"])
        if record.get("interrupting_task"):
            nested = record["interrupting_task"]
            matches = matches and (set(replay["world_done"][nested["goal_id"]]) ==
                                   set(nested["completed_steps_at_cutoff"]))
        # Poison evaluation/audit/identity fields in memory, never write data.
        changed = deepcopy(record)
        for key in ("state_at_cutoff", "state_evidence_event_ids", "state_evidence_by_factor",
                    "p0_scripted_policy", "p0_expected_action", "p0_expected", "notes", "annotation",
                    "sample_id", "base_story_id", "variant", "p1_observed_resume",
                    "p1_observed_first_step", "p1_censoring_status"):
            changed[key] = {"must_not_enter_model": True}
        invariant = adapt_record(changed) == view
        hidden_isolated = True
        for index, event in enumerate(record["observed_events"]):
            if event["person_access"] == "NOT_ACCESSED":
                changed = deepcopy(record)
                hidden = changed["observed_events"][index]
                for key in ("world_effect", "observer_evidence", "description", "person_access_evidence"):
                    hidden[key] = "hidden observer-only content changed"
                hidden["event_type"] = "notification_sent"
                hidden_isolated &= person_inputs(adapt_record(changed)) == person_inputs(view)
        rows.append({"sample_id": record["sample_id"], "events": len(view["events"]),
                     "progress_snapshot_matches": matches,
                     "forbidden_fields_invariant": invariant,
                     "hidden_world_person_view_invariant": hidden_isolated,
                     "self_completion_evidence": replay["self_completion_evidence"][goal],
                     "scripted_target_audit": scripted_targets(record)})
    by_id = {record["sample_id"]: record for record in records}
    p04b = by_id["P04-B"]
    p04_progress = replay_completion_evidence(views["P04-B"])
    q = p04b["state_at_cutoff"]["Q"]  # evaluation audit only
    checks = {
        "all_input_mapping": len(views) == len(records),
        "all_progress_snapshots": all(r["progress_snapshot_matches"] for r in rows),
        "all_forbidden_field_perturbations": all(r["forbidden_fields_invariant"] for r in rows),
        "all_hidden_world_perturbations": all(r["hidden_world_person_view_invariant"] for r in rows),
        "p07_identical_model_input": views["P07-A"] == views["P07-B"],
        "p01_access_difference_preserved": (
            [e["delivery"] for e in views["P01-A"]["events"]] != [e["delivery"] for e in views["P01-B"]["events"]]),
        "p02_long_history_preserved": (views["P02-A"]["events"][-5:] == views["P02-B"]["events"][-5:]
                                        and person_inputs(views["P02-A"]) != person_inputs(views["P02-B"])),
        "p03_completion_difference_preserved": (
            "print_label" in replay_completion_evidence(views["P03-A"])["self_completion_evidence"][by_id["P03-A"]["goal_id"]]
            and "print_label" not in replay_completion_evidence(views["P03-B"])["self_completion_evidence"][by_id["P03-B"]["goal_id"]]),
        "p04_world_not_copied_to_person": (q in p04_progress["world_done"][p04b["goal_id"]]
                                            and q not in p04_progress["self_completion_evidence"][p04b["goal_id"]]),
        "p04_delivery_difference_preserved": (
            [e["delivery"] for e in views["P04-A"]["events"]] != [e["delivery"] for e in views["P04-B"]["events"]]),
        "p05_world_resource_difference_preserved": (
            [e["world"]["event_type"] for e in views["P05-A"]["events"]] !=
            [e["world"]["event_type"] for e in views["P05-B"]["events"]]),
        "p06_nested_not_original_t2": not scripted_targets(by_id["P06-B"])["t2_mask"],
        "p08_same_access_distinct_self_statements": (
            [e["delivery"] for e in views["P08-A"]["events"]] == [e["delivery"] for e in views["P08-B"]["events"]]
            and person_inputs(views["P08-A"]) != person_inputs(views["P08-B"])),
    }
    return {"kind": "P0_input_and_evidence_contract_only", "records": len(records),
            "families": len({r["base_story_id"] for r in records}),
            "events": sum(len(r["observed_events"]) for r in records),
            "annotation_status": dict(Counter(r["annotation"]["status"] for r in records)),
            "state_label_counts": {factor: dict(Counter(r["state_at_cutoff"][factor] for r in records))
                                   for factor in ("V", "F", "A", "B", "C", "Q")},
            "p1_first_step_key_present": sum("p1_observed_first_step" in r for r in records),
            "original_goal_t2_eligible": sum(scripted_targets(r)["t2_mask"] for r in records),
            "checks": checks, "per_record": rows,
            "unsupported": ["AU/B/C/Q learned transitions", "T1/T2 behavioral prediction",
                            "external-message comprehension parsing", "late-arriving evidence timestamps",
                            "P1 human behavior", "calibration and generalization"]}
