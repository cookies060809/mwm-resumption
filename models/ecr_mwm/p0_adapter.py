"""Versioned input boundary for B-owned P0 v0.1 and v0.2.

This adapter maps evidence, not mental labels. External message semantics need
a separately audited parser; ACCESSED never implies comprehension.
"""
from copy import deepcopy
import re

from models.ec_jmf.constraints import validate_graph
from models.ec_jmf.structured import resolve_person_event_goal

SCHEMA_VERSION = "p0-record/v0.1.0"
SCHEMA_V02 = "p0-record/v0.2.0"
ADAPTER_VERSION = "a-p0-input/v0.2.0"


def minutes(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ValueError("INVALID_P0_TIME")
    hours, minute = map(int, value.split(":"))
    return hours * 60 + minute


def adapt_record(record):
    """Select input fields only. Run repository schema validation separately.

    Deliberately does not read labels, policy, notes, annotation, sample_id,
    variant, or cutoff snapshots. Full records must pass B's validator before
    admission; this function independently validates the selected input.
    """
    version = record.get("schema_version")
    if version not in (SCHEMA_VERSION, SCHEMA_V02):
        raise ValueError("UNSUPPORTED_SCHEMA_VERSION")
    steps = deepcopy(record["task_steps"])
    dependencies = {step: [] for step in steps}
    for edge in record["task_dependencies"]:
        if edge["after"] not in dependencies:
            raise ValueError("DANGLING_DEPENDENCY")
        dependencies[edge["after"]].append(edge["before"])
    validate_graph(steps, dependencies)
    events = record["observed_events"]
    if not events or events[-1]["event_id"] != record["cutoff_event_id"]:
        raise ValueError("CUTOFF_NOT_LAST")
    horizon = record["horizon"]
    if (horizon.get("type") != "decision_opportunities" or
            type(horizon.get("value")) is not int or horizon["value"] < 1):
        raise ValueError("UNSUPPORTED_HORIZON")
    goal = record["goal_id"]
    graphs = {goal: {"steps": steps, "dependencies": dependencies}}
    nested = record.get("interrupting_task")
    if nested:
        if nested["parent_goal_id"] != goal or not nested.get("goal_id") or nested["goal_id"] == goal:
            raise ValueError("INVALID_NESTED_GOAL")
        nested_steps = deepcopy(nested["steps"])
        validate_graph(nested_steps, {})
        graphs[nested["goal_id"]] = {"steps": nested_steps,
                                   "dependencies": None, "parent_goal_id": goal,
                                   "task_id": nested["task_id"]}
    cutoff = minutes(events[-1]["time"])
    seen, previous, mapped = set(), -1, []
    for event in events:
        now, event_id = minutes(event["time"]), event["event_id"]
        if now < previous or now > cutoff:
            raise ValueError("FUTURE_OR_UNORDERED_EVENT")
        if event_id in seen:
            raise ValueError("DUPLICATE_EVENT_ID")
        seen.add(event_id)
        previous = now
        event_goal, step = event["goal_id"], event["step_id"]
        if event_goal is not None and event_goal not in graphs:
            raise ValueError("UNKNOWN_EVENT_GOAL")
        if step is not None and (event_goal not in graphs or step not in graphs[event_goal]["steps"]):
            raise ValueError("UNKNOWN_EVENT_STEP")
        access = event["person_access"]
        if access not in ("ACCESSED", "NOT_ACCESSED", "UNCERTAIN"):
            raise ValueError("INVALID_ACCESS_EVIDENCE")
        if event["actor"] == "person" and access != "ACCESSED":
            raise ValueError("SELF_EVENT_NOT_ACCESSED")
        # Mixed external descriptions and observer metadata stay world-side.
        person = None
        if event["actor"] == "person" and access == "ACCESSED":
            person = {key: deepcopy(event[key]) for key in
                      ("event_type", "goal_id", "step_id", "description")}
        comprehension = "not_structurally_labeled"
        semantic = {"kind": "none"}
        if version == SCHEMA_V02:
            comprehension = event["person_comprehension"]
            if comprehension not in ("UNDERSTOOD", "MISUNDERSTOOD", "NOT_UNDERSTOOD",
                                      "UNCERTAIN", "NOT_APPLICABLE"):
                raise ValueError("INVALID_COMPREHENSION")
            if access != "ACCESSED" and comprehension != "NOT_APPLICABLE":
                raise ValueError("COMPREHENSION_WITHOUT_ACCESS")
            raw_semantic = event["person_available_semantics"]
            semantic = {k: deepcopy(raw_semantic[k]) for k in
                        ("kind", "value", "interpretation") if k in raw_semantic}
            if (comprehension == "MISUNDERSTOOD" and
                    semantic.get("interpretation") not in ("defer", "complete", "unresolved")):
                raise ValueError("MISUNDERSTANDING_WITHOUT_INTERPRETATION")
        # Explicit whitelist even inside events: injected annotation keys cannot pass.
        world = {k: deepcopy(event[k]) for k in
                 ("actor", "event_type", "goal_id", "step_id", "world_effect",
                  "observer_evidence", "person_access_evidence", "source", "certainty",
                  "description")}
        mapped.append({"event_id": event_id, "time_minutes": now,
                       "world": world,
                       "delivery": {"access_evidence": access,
                                    "comprehension": comprehension},
                       "semantic": semantic,
                       "person": person})
    # Graphs describe observer task metadata, never presumed person knowledge.
    return {"adapter_version": ADAPTER_VERSION, "schema_version": version,
            "goal_id": goal, "horizon": deepcopy(horizon),
            "cutoff_event_id": events[-1]["event_id"], "cutoff_minutes": cutoff,
            "observer_graphs": graphs, "events": mapped}


def person_inputs(adapted, semantic_contract="legacy-v1"):
    """No world payload, private event type/source, or observer task graph."""
    result = []
    for event in adapted["events"]:
        accessible = event["delivery"]["access_evidence"] != "NOT_ACCESSED"
        physical = (semantic_contract == "b-p0-v03/v3" and event["person"] and
                    event["person"]["event_type"] in ("interruption_started", "interruption_ended"))
        result.append({"event_id": event["event_id"], "time_minutes": event["time_minutes"],
                       "delivery": deepcopy(event["delivery"]),
                       "semantic": deepcopy(event["semantic"]) if accessible else {"kind": "none"},
                       "semantic_goal_id": (resolve_person_event_goal(event, adapted["observer_graphs"], adapted["goal_id"], semantic_contract) if accessible and
                                            event["semantic"]["kind"] != "none" else None),
                       "interruption_phase": (event["world"]["event_type"] if accessible and
                                              (event["semantic"]["kind"] == "interruption" or physical) else None),
                       "person": deepcopy(event["person"])})
    return result


def replay_completion_evidence(adapted):
    """Factual evidence replay, not an estimate of B/C/Q or future behavior.

    self_done is a lower bound from the person's own completed actions. External
    notification content is not parsed into subjective knowledge here.
    """
    world_done = {goal: set() for goal in adapted["observer_graphs"]}
    self_done = {goal: set() for goal in adapted["observer_graphs"]}
    for mapped in adapted["events"]:
        event = mapped["world"]
        goal, step = event["goal_id"], event["step_id"]
        if event["event_type"] == "step_completed" and goal in world_done:
            if step is None:
                raise ValueError("COMPLETED_STEP_MISSING_ID")
            world_done[goal].add(step)
        if event["event_type"] == "task_completed_by_other" and goal in world_done:
            world_done[goal].update(adapted["observer_graphs"][goal]["steps"])
        own = mapped["person"]
        if own and own["event_type"] == "step_completed" and goal in self_done:
            self_done[goal].add(step)
    return {"world_done": {g: sorted(s) for g,s in world_done.items()},
            "self_completion_evidence": {g: sorted(s) for g,s in self_done.items()}}


def scripted_targets(record):
    """Evaluation-only; NEVER pass this object to adapt_record or a model."""
    target = record["p0_expected"]
    resume, step = target["resume_within_horizon"], target["first_step"]
    if resume is not None and type(resume) is not bool:
        raise ValueError("INVALID_SCRIPTED_RESUME")
    undefined = record.get("p0_expected_action") == "indeterminate"
    if resume is None or undefined:
        if (resume is not None or not undefined or
                target.get("undefined_reason") != "indistinguishable_inputs"):
            raise ValueError("INVALID_UNDEFINED_TARGET")
    t2_valid = resume is True and step in record["task_steps"]
    if record.get("schema_version") == SCHEMA_V02 and t2_valid:
        # T2 concerns future progress, never repetition of an objectively done step.
        done = replay_completion_evidence(adapt_record(record))["world_done"][record["goal_id"]]
        t2_valid = step not in done
    return {"p0_resume": resume, "t1_mask": resume is not None,
            "undefined_reason": target.get("undefined_reason"), "t2_mask": t2_valid,
            "t2_original_goal_step": step if t2_valid else None,
            "scripted_next_action_step": step,
            "p1_first_step_present": "p1_observed_first_step" in record}
