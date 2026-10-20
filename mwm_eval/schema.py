"""结构化事件协议草案。输入与 gold 分离；不替代 B 的标注手册。"""

import hashlib
import json
import math
from pathlib import Path


FACTORS = {
    "V": {"VALID", "CANCELLED", "FULFILLED", "UNKNOWN"},
    "F": {"READY", "BLOCKED", "UNKNOWN"},
    "A": {"ACCESSED", "NOT_ACCESSED", "UNCERTAIN", "UNKNOWN"},
    "B": {"BELIEVES_VALID", "BELIEVES_INVALID", "UNRESOLVED", "UNKNOWN"},
    "C": {"ACTIVE", "SUSPENDED", "ABANDONED", "COMPLETED", "UNKNOWN"},
}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_jsonl(path):
    def unique_pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result

    rows = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line, object_pairs_hook=unique_pairs, parse_float=finite_float,
                                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"{path}:{number}: invalid JSON: {exc}") from exc
    return rows


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_graph(graph, steps):
    if not isinstance(graph, dict) or set(graph) != {"nodes", "edges"}:
        raise ValueError("task_graph must contain nodes and edges")
    nodes, edges = graph["nodes"], graph["edges"]
    if not isinstance(nodes, list) or len(set(nodes)) != len(nodes) or set(nodes) != set(steps):
        raise ValueError("task_graph nodes must match task_steps")
    if not isinstance(edges, list):
        raise ValueError("task_graph edges must be a list")
    outgoing = {node: [] for node in nodes}
    indegree = dict.fromkeys(nodes, 0)
    seen = set()
    for edge in edges:
        if (not isinstance(edge, list) or len(edge) != 2 or any(node not in outgoing for node in edge)
                or edge[0] == edge[1] or tuple(edge) in seen):
            raise ValueError("invalid or duplicate task dependency")
        seen.add(tuple(edge))
        outgoing[edge[0]].append(edge[1])
        indegree[edge[1]] += 1
    queue = [node for node, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for successor in outgoing[node]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if visited != len(nodes):
        raise ValueError("task_graph contains a cycle")


def validate_observation(obs):
    required = {"target_person", "goal_id", "task_steps", "task_graph", "cutoff", "horizon", "events"}
    if not isinstance(obs, dict) or set(obs) != required:
        raise ValueError("observation fields must match protocol; no labels or sample IDs")
    if not text(obs["target_person"]) or not text(obs["goal_id"]):
        raise ValueError("target_person and goal_id are required")
    steps = obs["task_steps"]
    if not isinstance(steps, list) or not steps or not all(text(step) for step in steps) or len(set(steps)) != len(steps):
        raise ValueError("task_steps must be nonempty and unique")
    validate_graph(obs["task_graph"], steps)
    if not number(obs["cutoff"]):
        raise ValueError("cutoff must be finite numeric time")
    horizon = obs["horizon"]
    if (not isinstance(horizon, dict) or set(horizon) != {"type", "value"}
            or horizon["type"] not in {"decision_opportunities", "seconds"}
            or not number(horizon["value"]) or horizon["value"] <= 0
            or (horizon["type"] == "decision_opportunities" and type(horizon["value"]) is not int)):
        raise ValueError("invalid prediction horizon")
    if not isinstance(obs["events"], list):
        raise ValueError("events must be a list")
    required_event = {"event_id", "time", "actor", "event_type", "goal_id", "step_id", "world_effect",
                      "observer_evidence", "person_access_evidence", "source", "certainty"}
    semantic_keys = {"kind", "value", "belief", "reference_event_id", "interpretation", "step_id",
                     "demand", "demand_level", "interruption_duration", "goal_priority", "reason",
                     "completed_steps", "parent_goal_id", "task_completed", "interrupting_goal_id"}
    ids, previous = set(), -math.inf
    for event in obs["events"]:
        if (not isinstance(event, dict) or not required_event <= set(event)
                or set(event) - required_event - {"semantic", "action_status"}):
            raise ValueError("invalid event fields")
        if not text(event["event_id"]) or event["event_id"] in ids:
            raise ValueError("duplicate or empty event_id")
        if not number(event["time"]) or not previous <= event["time"] <= obs["cutoff"]:
            raise ValueError("event time unordered or beyond cutoff (future leakage)")
        previous = event["time"]
        if not all(text(event[key]) for key in ("actor", "event_type", "observer_evidence", "source")):
            raise ValueError("event actor/type/evidence/source missing")
        for key in ("goal_id", "step_id"):
            if event[key] is not None and not text(event[key]):
                raise ValueError("goal/step must be string or null")
        if event["world_effect"] is not None and not isinstance(event["world_effect"], (str, dict)):
            raise ValueError("world_effect must be string, object, or null")
        if isinstance(event["world_effect"], dict):
            effect = event["world_effect"]
            if set(effect) - {"V", "F", "completed_steps"}:
                raise ValueError("world_effect object may contain only objective V/F/completed_steps")
            if "V" in effect and effect["V"] not in FACTORS["V"]:
                raise ValueError("invalid objective V")
            if "F" in effect and effect["F"] not in FACTORS["F"]:
                raise ValueError("invalid objective F")
            if "completed_steps" in effect and (not isinstance(effect["completed_steps"], list)
                    or any(step not in steps for step in effect["completed_steps"])):
                raise ValueError("invalid objective completed steps")
        access = event["person_access_evidence"]
        if (not isinstance(access, dict) or set(access) != {"status", "understood"}
                or access["status"] not in {"ACCESSED", "NOT_ACCESSED", "UNCERTAIN"}
                or (access["understood"] is not None and type(access["understood"]) is not bool)):
            raise ValueError("invalid person_access_evidence")
        if not number(event["certainty"]) or not 0 <= event["certainty"] <= 1:
            raise ValueError("certainty must be in [0,1]")
        semantic = event.get("semantic", {})
        if not isinstance(semantic, dict) or set(semantic) - semantic_keys:
            raise ValueError("invalid semantic keys; never include annotation answers")
        for key, value in semantic.items():
            if key == "completed_steps":
                if not isinstance(value, list) or not all(text(step) for step in value):
                    raise ValueError("semantic completed_steps must be a string list")
            elif key in {"demand", "demand_level", "interruption_duration", "goal_priority"}:
                if not number(value):
                    raise ValueError("semantic numeric fields must be finite scalars")
            elif key == "task_completed":
                if type(value) is not bool:
                    raise ValueError("semantic task_completed must be boolean")
            elif value is not None and not text(value):
                raise ValueError("semantic text fields must be strings or null; nested objects prohibited")
        reference = semantic.get("reference_event_id")
        if reference is not None and reference not in ids:
            raise ValueError("semantic reference must point to an earlier event")
        if event["event_type"] == "task_action":
            if (event.get("action_status") not in {"in_progress", "completed"}
                    or not text(event["goal_id"]) or not text(event["step_id"])):
                raise ValueError("task_action requires goal, step, action_status")
            if event["goal_id"] == obs["goal_id"] and event["step_id"] not in steps:
                raise ValueError("task action points to unknown target step")
        ids.add(event["event_id"])


def validate_dataset(records, golds):
    if not records or len(records) != len(golds):
        raise ValueError("nonempty records and one gold per record are required")
    record_keys = {"sample_id", "base_story_id", "person_id", "task_family", "domain", "split", "purpose", "observation"}
    by_id, family_splits = {}, {}
    for record in records:
        if set(record) != record_keys:
            raise ValueError("record fields differ from protocol")
        if not all(text(record[key]) for key in record_keys - {"observation"}):
            raise ValueError("record metadata must be nonempty strings")
        if record["sample_id"] in by_id:
            raise ValueError("duplicate sample_id")
        if record["split"] not in {"train", "dev", "calibration", "test"}:
            raise ValueError("split must be train/dev/calibration/test")
        old_split = family_splits.setdefault(record["base_story_id"], record["split"])
        if old_split != record["split"]:
            raise ValueError("base_story_id crosses data splits")
        validate_observation(record["observation"])
        by_id[record["sample_id"]] = record
    seen, layers = set(), set()
    allowed_gold = {"sample_id", "dataset_layer", "resume_label", "resume_step", "state_labels", "state_evidence",
                    "window_complete", "pair_id", "pair_relation", "pair_factor", "constraint_checks", "annotation_source"}
    for gold in golds:
        needed = {"sample_id", "dataset_layer", "resume_label", "resume_step", "state_labels", "state_evidence", "window_complete"}
        if not needed <= set(gold) or set(gold) - allowed_gold:
            raise ValueError("gold fields differ from protocol")
        sample_id = gold["sample_id"]
        if sample_id not in by_id or sample_id in seen:
            raise ValueError("duplicate/unmatched gold sample_id")
        seen.add(sample_id)
        layer = gold["dataset_layer"]
        if layer not in {"P0", "P1", "integration_fixture"}:
            raise ValueError("unknown dataset_layer")
        layers.add(layer)
        if (by_id[sample_id]["purpose"] == "synthetic_integration_fixture") != (layer == "integration_fixture"):
            raise ValueError("fixture and research layers must not be relabeled as one another")
        if gold["resume_label"] not in {"resume", "not_resume", "censored", "unknown"}:
            raise ValueError("invalid gold resume_label")
        if type(gold["window_complete"]) is not bool:
            raise ValueError("window_complete must be boolean")
        obs = by_id[sample_id]["observation"]
        if gold["resume_step"] is not None and (gold["resume_label"] != "resume" or gold["resume_step"] not in obs["task_steps"]):
            raise ValueError("gold step incompatible with target task")
        if not isinstance(gold["state_labels"], dict) or not isinstance(gold["state_evidence"], dict):
            raise ValueError("state labels and evidence must be objects")
        if set(gold["state_labels"]) - (set(FACTORS) | {"Q"}) or set(gold["state_evidence"]) - (set(FACTORS) | {"Q"}):
            raise ValueError("unknown state factor")
        event_ids = {event["event_id"] for event in obs["events"]}
        for evidence in gold["state_evidence"].values():
            if not isinstance(evidence, list) or any(event_id not in event_ids for event_id in evidence):
                raise ValueError("state evidence must be within observed events")
        for factor, value in gold["state_labels"].items():
            legal = FACTORS.get(factor, set(obs["task_steps"]) | {"UNKNOWN", "NOT_APPLICABLE"} if factor == "Q" else set())
            if value not in legal and value is not None:
                raise ValueError(f"invalid {factor} state label")
            evidence = gold["state_evidence"].get(factor, [])
            if not isinstance(evidence, list) or any(e not in {x["event_id"] for x in obs["events"]} for e in evidence):
                raise ValueError("state evidence must be within observed events")
            if value not in {None, "UNKNOWN", "UNCERTAIN"} and not evidence:
                raise ValueError("non-unknown state gold requires evidence")
        if gold.get("pair_relation") not in {None, "same_prediction", "different_belief", "same_mental"}:
            raise ValueError("unknown pair relation")
    if len(layers) != 1:
        raise ValueError("P0/P1/fixtures must be evaluated separately")
    return {"n": len(records), "dataset_layer": next(iter(layers)),
            "split_counts": {split: sum(r["split"] == split for r in records) for split in ("train", "dev", "calibration", "test")}}


def validate_prediction(prediction, obs):
    needed = {"resume_label", "resume_step", "p_resume", "conditional_step_probs", "state_probs", "evidence_event_ids", "reason", "metadata"}
    if not isinstance(prediction, dict) or not needed <= set(prediction):
        raise ValueError("prediction missing canonical output fields")
    if prediction["resume_label"] not in {"resume", "not_resume"}:
        raise ValueError("invalid prediction resume_label")
    step = prediction["resume_step"]
    if step is not None and step not in obs["task_steps"]:
        raise ValueError("predicted step does not exist")
    if prediction["resume_label"] == "not_resume" and step is not None:
        raise ValueError("not_resume cannot carry a selected step")
    probability = prediction["p_resume"]
    if probability is not None and (not number(probability) or not 0 <= probability <= 1):
        raise ValueError("invalid p_resume")
    distributions = []
    steps = prediction["conditional_step_probs"]
    if steps is not None:
        if not isinstance(steps, dict) or set(steps) - set(obs["task_steps"]):
            raise ValueError("conditional step distribution has unknown steps")
        distributions.append(steps)
    states = prediction["state_probs"]
    if not isinstance(states, dict):
        raise ValueError("state_probs must be object")
    for factor, probs in states.items():
        legal = FACTORS.get(factor, set(obs["task_steps"]) | {"UNKNOWN", "NOT_APPLICABLE"} if factor == "Q" else set())
        if not isinstance(probs, dict) or set(probs) - legal:
            raise ValueError("invalid state probability labels")
        distributions.append(probs)
    for dist in distributions:
        if not dist or any(not number(v) or v < 0 or v > 1 for v in dist.values()) or abs(sum(dist.values()) - 1) > 1e-6:
            raise ValueError("probability distribution must be finite, nonnegative and sum to 1")
    evidence = prediction["evidence_event_ids"]
    if not isinstance(evidence, list) or any(e not in {x["event_id"] for x in obs["events"]} for e in evidence):
        raise ValueError("prediction cites evidence outside actual input")
    if not text(prediction["reason"]) or not isinstance(prediction["metadata"], dict):
        raise ValueError("prediction requires reason and metadata")


def audit_groups(records):
    result = {}
    for key in ("base_story_id", "person_id", "task_family", "domain"):
        splits = {split: {r[key] for r in records if r["split"] == split}
                  for split in ("train", "dev", "calibration", "test")}
        keys = list(splits)
        overlaps = {f"{a}__{b}": len(splits[a] & splits[b]) for i, a in enumerate(keys) for b in keys[i+1:]}
        result[key] = {"n_train": len(splits["train"]), "n_test": len(splits["test"]),
                       "n_overlap": len(splits["train"] & splits["test"]), "pairwise_overlap": overlaps}
    return result
