"""Fixed, label-free neural features and separately masked P0 supervision.

Categorical vocabularies come from the versioned contract, never a data split.
Observer step positions identify candidates; they do not establish person knowledge.
"""
import json
from pathlib import Path

from models.ecr_mwm.p0_adapter import SCHEMA_V02, adapt_record, scripted_targets


EVENT_TYPES = (
    "goal_start", "goal_abandoned", "step_started", "step_completed",
    "step_attempted", "interruption_started", "interruption_ended",
    "return_to_task", "person_action", "person_statement", "commitment_expressed",
    "task_cancelled", "task_completed_by_other", "notification_sent",
    "resource_available", "resource_missing",
)
SOURCES = ("direct_observation", "person_report", "third_party_report", "notification",
           "backend_record", "sensor_log", "inference", "other")
ACTORS = ("person", "colleague", "customer", "manager", "system", "environment", "other")
CERTAINTIES = ("CERTAIN", "PROBABLE", "UNCERTAIN")
SEMANTICS = ("none", "cancellation", "completion_by_other", "resource_missing",
             "resource_available", "commitment", "abandonment", "interruption", "nested_task_state")
INTERPRETATIONS = ("none", "accurate", "defer", "complete", "unresolved")
COMPREHENSION = ("UNDERSTOOD", "MISUNDERSTOOD", "NOT_UNDERSTOOD", "UNCERTAIN",
                 "NOT_APPLICABLE", "not_structurally_labeled")
ACCESS = ("ACCESSED", "NOT_ACCESSED", "UNCERTAIN")
VALIDITY = ("VALID", "CANCELLED", "FULFILLED", "UNKNOWN")
FEASIBILITY = ("READY", "BLOCKED", "UNKNOWN")
BELIEF = ("BELIEVES_VALID", "BELIEVES_INVALID", "UNRESOLVED", "UNKNOWN")
COMMITMENT = ("ACTIVE", "SUSPENDED", "ABANDONED", "COMPLETED", "UNKNOWN")
MAX_STEPS = 8
# Event slots: eight candidate positions plus absent position, three goal roles.
WORLD_DIM = len(EVENT_TYPES) + len(SOURCES) + len(CERTAINTIES) + len(ACTORS) + 9 + 3
PERSON_DIM = (len(EVENT_TYPES) + 9 + 3 + len(SEMANTICS) + len(INTERPRETATIONS)
              + len(COMPREHENSION) + len(ACCESS) + 3 + len(EVENT_TYPES))
MENTAL_DIM = len(BELIEF) + len(COMMITMENT) + 10 + 5
STATE_DIM = MENTAL_DIM + len(VALIDITY) + len(FEASIBILITY) + 1


def _onehot(value, vocabulary):
    return [float(value == item) for item in vocabulary]


def load_records(path):
    """Read reviewed P0 records; model inputs and target dictionaries stay apart.

    File admission checks supplement, rather than replace, B's schema validator.
    UNKNOWN and unsupported evidence never become state supervision. Undefined
    scripted behavior and non-original/finished steps remain masked as None.
    """
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    families = {}
    examples = []
    for raw in records:
        if raw.get("schema_version") != SCHEMA_V02:
            raise ValueError("NEURAL_TRAINING_REQUIRES_P0_V02_SCHEMA")
        if raw["annotation"]["status"] not in ("reviewed", "adjudicated"):
            raise ValueError("UNREVIEWED_TRAINING_RECORD")
        split, family = raw["split"], raw["base_story_id"]
        if split not in ("train", "dev", "calibration", "test"):
            raise ValueError("UNKNOWN_DATA_SPLIT")
        if family in families and families[family] != split:
            raise ValueError("FAMILY_CROSSES_SPLITS")
        families[family] = split
        adapted = adapt_record(raw)
        if any(len(graph["steps"]) > MAX_STEPS for graph in adapted["observer_graphs"].values()):
            raise ValueError("NEURAL_STEP_BUDGET_EXCEEDED")
        targets = scripted_targets(raw)
        observed_ids = {event["event_id"] for event in adapted["events"]}
        states = {}
        for factor in "VFABCQ":
            label = raw["state_at_cutoff"][factor]
            evidence = raw["state_evidence_by_factor"][factor]
            if not set(evidence) <= observed_ids:
                raise ValueError("STATE_EVIDENCE_OUTSIDE_CUTOFF")
            if label != "UNKNOWN" and evidence:
                states[factor] = label
        examples.append({
            "input": adapted,
            "target": {"resume": targets["p0_resume"] if targets["t1_mask"] else None,
                       "step": targets["t2_original_goal_step"], "states": states,
                       "steps": list(raw["task_steps"])},
            "split": split, "id": raw["sample_id"], "family": family,
            "mechanism": raw["mechanism"],
        })
    return examples


def _position(goal, step, graphs):
    steps = graphs[goal]["steps"] if goal in graphs else ()
    if len(steps) > MAX_STEPS:
        raise ValueError("NEURAL_STEP_BUDGET_EXCEEDED")
    return steps.index(step) if step in steps else MAX_STEPS


def _role(goal, target, graphs):
    return 0 if goal == target else 1 if goal in graphs else 2


def event_features(adapted, leak=False):
    """Return world/person event vectors and possible person-visibility flags.

    No descriptions, IDs, free-text values or supervision enter the vectors.
    UNCERTAIN contact retains possible access, with its uncertainty explicit;
    NOT_ACCESSED is exactly zero unless A1 deliberately enables leakage.
    Only A1 may place private world event types into the person feature block.
    """
    world_vectors, person_vectors, visible = [], [], []
    graphs, target = adapted["observer_graphs"], adapted["goal_id"]
    for event in adapted["events"]:
        world, delivery = event["world"], event["delivery"]
        position = _position(world["goal_id"], world["step_id"], graphs)
        role = _role(world["goal_id"], target, graphs)
        world_vectors.append(
            _onehot(world["event_type"], EVENT_TYPES)
            + _onehot(world["source"], SOURCES)
            + _onehot(world["certainty"], CERTAINTIES)
            + _onehot(world["actor"], ACTORS)
            + _onehot(position, range(MAX_STEPS + 1)) + _onehot(role, range(3)))
        own = event["person"]
        accessible = delivery["access_evidence"] != "NOT_ACCESSED"
        available = bool(own) or accessible or leak
        visible.append(available)
        if not available:
            person_vectors.append([0.0] * PERSON_DIM)
            continue
        semantic = event["semantic"] if accessible or leak else {"kind": "none"}
        has_semantic = semantic["kind"] != "none"
        # For external information goal role is usable only with available content.
        person_position = position if own else MAX_STEPS
        person_role = role if own or has_semantic else 2
        phase = (1 if world["event_type"] == "interruption_started" else
                 2 if world["event_type"] == "interruption_ended" else 0)
        if not (has_semantic and semantic["kind"] == "interruption"):
            phase = 0
        person_vectors.append(
            _onehot(own["event_type"] if own else None, EVENT_TYPES)
            + _onehot(person_position, range(MAX_STEPS + 1))
            + _onehot(person_role, range(3))
            + _onehot(semantic["kind"], SEMANTICS)
            + _onehot(semantic.get("interpretation", "none"), INTERPRETATIONS)
            + _onehot(delivery["comprehension"], COMPREHENSION)
            + _onehot(delivery["access_evidence"], ACCESS)
            + _onehot(phase, range(3))
            + _onehot(world["event_type"] if leak else None, EVENT_TYPES))
    return world_vectors, person_vectors, visible


def state_features(state, target, graphs, mental_only=False):
    """Fixed features of one structured hypothesis, with a strict mental view.

    Mental features never contain objective validity, resources or completion.
    Eight Q candidate slots are followed by UNKNOWN and NOT_APPLICABLE slots.
    Counts describe the hypothesis's own knowledge, not the observer graph.
    """
    goal = state.goal(target)
    steps = graphs[target]["steps"]
    if len(steps) > MAX_STEPS:
        raise ValueError("NEURAL_STEP_BUDGET_EXCEEDED")
    if goal.q in steps:
        q = steps.index(goal.q)
    elif goal.q == "NOT_APPLICABLE":
        q = MAX_STEPS + 1
    else:
        q = MAX_STEPS
    denominator = max(1, len(steps))
    mental = (_onehot(goal.belief, BELIEF) + _onehot(goal.commitment, COMMITMENT)
              + _onehot(q, range(MAX_STEPS + 2))
              + [float(goal.remembered), float(goal.waiting),
                 len(goal.person_done) / denominator, len(goal.known_steps) / denominator,
                 len(state.stack) / 4.0])
    if mental_only:
        return mental
    return (mental + _onehot(goal.validity, VALIDITY)
            + _onehot(goal.feasibility, FEASIBILITY)
            + [len(goal.world_done) / denominator])
