"""Deterministic P0 context stressors for adapted examples; no label-led edits.

Public API: transform_example(example, kind, level=1).
  rename_ids, level=1: bijective goal/step/event renaming, preserving order.
  invisible_noops, level=10 or 30: insert exactly that many null-scope events.

The transformations test ID invariance and context robustness, not real-world
generalization. They are frozen before evaluation. Original examples are never
mutated. Labels are consulted only to rename their output symbols consistently.
"""
from copy import deepcopy


STRESS_SPEC_VERSION = "p0-context-stress/v1"
KINDS = ("rename_ids", "invisible_noops")


def _rename_ids(example, level):
    adapted = example["input"]
    original_target = adapted["goal_id"]
    graphs = adapted["observer_graphs"]
    prefix = f"stress_v{level}"
    goal_map = {goal: f"{prefix}_goal_{i}" for i, goal in enumerate(graphs)}
    step_map = {
        goal: {step: f"{prefix}_g{gi}_step_{si}"
               for si, step in enumerate(graph["steps"])}
        for gi, (goal, graph) in enumerate(graphs.items())
    }
    event_map = {event["event_id"]: f"{prefix}_event_{i}"
                 for i, event in enumerate(adapted["events"])}
    if len(event_map) != len(adapted["events"]):
        raise ValueError("DUPLICATE_INPUT_EVENT_ID")

    # Ordered dict construction keeps graph roles and candidate indices fixed.
    renamed_graphs = {}
    for goal, graph in graphs.items():
        new_graph = deepcopy(graph)
        new_graph["steps"] = [step_map[goal][step] for step in graph["steps"]]
        if graph["dependencies"] is not None:
            new_graph["dependencies"] = {
                step_map[goal][step]: [step_map[goal][before] for before in dependencies]
                for step, dependencies in graph["dependencies"].items()
            }
        if "parent_goal_id" in graph:
            new_graph["parent_goal_id"] = goal_map[graph["parent_goal_id"]]
        renamed_graphs[goal_map[goal]] = new_graph

    # Semantic values may contain exact symbolic step/goal/event references.
    # Free-text descriptions and strings containing IDs remain untouched.
    def rename_exact_value(value, event_goal):
        if not isinstance(value, str):
            return value
        if value in step_map.get(event_goal, {}):
            return step_map[event_goal][value]
        if value in goal_map:
            return goal_map[value]
        if value in event_map:
            return event_map[value]
        return value

    for event in adapted["events"]:
        old_goal = event["world"]["goal_id"]
        event["event_id"] = event_map[event["event_id"]]
        for payload in (event["world"], event["person"]):
            if payload is None:
                continue
            payload_goal = payload["goal_id"]
            step = payload["step_id"]
            payload["goal_id"] = goal_map.get(payload_goal, payload_goal)
            if step is not None:
                payload["step_id"] = step_map[payload_goal][step]
        if "value" in event["semantic"]:
            event["semantic"]["value"] = rename_exact_value(event["semantic"]["value"], old_goal)

    adapted["goal_id"] = goal_map[original_target]
    adapted["observer_graphs"] = renamed_graphs
    adapted["cutoff_event_id"] = event_map[adapted["cutoff_event_id"]]
    # Output labels are transformed by the already-fixed input-derived map.
    # They never determine which transformation, IDs, or events are selected.
    if "target" in example:
        target = example["target"]
        mapping = step_map[original_target]
        if "steps" in target:
            target["steps"] = [mapping.get(step, step) for step in target["steps"]]
        if target.get("step") is not None:
            target["step"] = mapping.get(target["step"], target["step"])
        if "Q" in target.get("states", {}):
            target["states"]["Q"] = mapping.get(target["states"]["Q"], target["states"]["Q"])
    return example


def _invisible_noops(example, count):
    adapted = example["input"]
    original = adapted["events"]
    if len(original) < 2:
        raise ValueError("NOOP_STRESS_REQUIRES_TWO_ORIGINAL_EVENTS")
    if original[-1]["event_id"] != adapted["cutoff_event_id"]:
        raise ValueError("CUTOFF_NOT_LAST")
    used_ids = {event["event_id"] for event in original}
    buckets = [[] for _ in range(len(original) - 1)]
    for index in range(count):
        # Distribute equally among original gaps, without changing event order.
        gap = index % len(buckets)
        event_id = f"__p0_context_noop_{count}_{index}"
        while event_id in used_ids:
            event_id += "_"
        used_ids.add(event_id)
        buckets[gap].append({
            "event_id": event_id,
            "time_minutes": original[gap]["time_minutes"],
            "world": {
                "actor": "environment", "event_type": "person_action",
                "goal_id": None, "step_id": None, "world_effect": None,
                "observer_evidence": "neutral context stress record",
                "person_access_evidence": "not observed by the person",
                "source": "sensor_log", "certainty": "CERTAIN",
                "description": "No task state or person state change.",
            },
            "delivery": {"access_evidence": "NOT_ACCESSED", "comprehension": "NOT_APPLICABLE"},
            "semantic": {"kind": "none"},
            "person": None,
        })
    events = []
    for index, event in enumerate(original):
        events.append(event)
        if index < len(buckets):
            events.extend(buckets[index])
    adapted["events"] = events
    return example


def transform_example(example, kind, level=1):
    """Return a deep copy under a fixed input-only context transformation.

    Existing IDs/family/split/mechanism remain unchanged for paired evaluation.
    For rename_ids, only target step symbols are synchronized with renamed input.
    Noop insertion never reads target, preserves cutoff/horizon/timestamps, and
    only lengthens the input between its original first and last events.
    """
    if type(level) is not int:
        raise ValueError("STRESS_LEVEL_MUST_BE_INTEGER")
    result = deepcopy(example)
    if kind == "rename_ids":
        if level != 1:
            raise ValueError("RENAME_LEVEL_MUST_BE_ONE")
        return _rename_ids(result, level)
    if kind == "invisible_noops":
        if level not in (10, 30):
            raise ValueError("NOOP_LEVEL_MUST_BE_10_OR_30")
        return _invisible_noops(result, level)
    raise ValueError(f"UNKNOWN_STRESS_KIND: {kind}")
