"""Validate a lossless, input-only A view shared by every P0 method."""

import copy


def validate_structured_evidence(view, observation):
    """Round-trip through A's whitelist and C's projection; reject hidden fields.

    Full U and nested observer graphs are retained as evidence, never labels or
    assumed person knowledge. The second view must describe the same events.
    """
    from models.ecr_mwm.p0_adapter import adapt_record, SCHEMA_V02
    from mwm_eval.p0 import adapt_input
    from mwm_eval.schema import canonical_hash

    try:
        required = {"adapter_version", "schema_version", "goal_id", "horizon", "cutoff_event_id",
                    "cutoff_minutes", "observer_graphs", "events"}
        if not isinstance(view, dict) or set(view) != required or view["schema_version"] != SCHEMA_V02:
            raise ValueError("invalid structured evidence root")
        goal = view["goal_id"]
        graphs = view["observer_graphs"]
        if not isinstance(graphs, dict) or not 1 <= len(graphs) <= 2:
            raise ValueError("P0 structured view supports target and one nested task")
        graph = graphs[goal]
        raw = {"schema_version": SCHEMA_V02, "sample_id": "input_only", "base_story_id": "input_only",
               "domain": "input_only", "split": "train", "goal_id": goal,
               "task_steps": copy.deepcopy(graph["steps"]),
               "task_dependencies": [{"before": before, "after": after}
                   for after, predecessors in graph["dependencies"].items() for before in predecessors],
               "horizon": copy.deepcopy(view["horizon"]), "cutoff_event_id": view["cutoff_event_id"],
               "interrupting_task": None, "observed_events": []}
        for nested_goal, nested in graphs.items():
            if nested_goal != goal:
                raw["interrupting_task"] = {"task_id": nested["task_id"], "goal_id": nested_goal,
                    "parent_goal_id": nested["parent_goal_id"], "steps": copy.deepcopy(nested["steps"])}
        for event in view["events"]:
            minute = event["time_minutes"]
            if type(minute) is not int or not 0 <= minute < 1440:
                raise ValueError("structured P0 time must be same-day integer minutes")
            if any(value is not None and not isinstance(value, str) for value in event["world"].values()):
                raise ValueError("structured P0 world fields must be text or null")
            if (set(event["semantic"]) - {"kind", "value", "interpretation"}
                    or any(value is not None and not isinstance(value, str) for value in event["semantic"].values())):
                raise ValueError("invalid input-only message content")
            raw["observed_events"].append({**copy.deepcopy(event["world"]),
                "event_id": event["event_id"], "time": f"{minute // 60:02d}:{minute % 60:02d}",
                "person_access": event["delivery"]["access_evidence"],
                "person_comprehension": event["delivery"]["comprehension"],
                "person_available_semantics": copy.deepcopy(event["semantic"])})
        if canonical_hash(adapt_record(raw)) != canonical_hash(view):
            raise ValueError("structured view includes unsupported or inconsistent fields")
        expected = adapt_input(raw, include_structured=False)["observation"]
        primary = {key: value for key, value in observation.items() if key != "structured_evidence"}
        if canonical_hash(expected) != canonical_hash(primary):
            raise ValueError("structured and canonical observations describe different evidence")
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("malformed structured evidence") from exc
    return copy.deepcopy(view)
