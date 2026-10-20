"""Build synthetic C-system acceptance fixtures, never P0/P1 research data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mwm_eval.schema import canonical_hash, validate_dataset


SPLITS = ("train", "dev", "calibration", "test")
DOMAINS = {"train": "office", "dev": "daily", "calibration": "daily", "test": "service"}
STEPS = ["verify", "prepare", "print", "handover"]
SOURCE = "synthetic_integration_script_v1; NOT observed human data"


def _event(time, kind, person, goal, *, actor=None, step=None, accessed=True,
           understood=True, world=None, **semantic):
    result = {
        "event_id": f"e{time:02d}", "time": time, "actor": actor or person,
        "event_type": "task_action" if kind in {"task_action", "step_completed"} else kind,
        "goal_id": goal, "step_id": step, "world_effect": world,
        "observer_evidence": f"Scripted observable event at {time}: {kind}",
        "person_access_evidence": {
            "status": "ACCESSED" if accessed else "NOT_ACCESSED", "understood": understood},
        "source": SOURCE, "certainty": 1.0, "semantic": {"kind": kind, **semantic}}
    if kind in {"task_action", "step_completed"}:
        result["action_status"] = "completed" if kind == "step_completed" else "in_progress"
    return result


def _base(person, goal):
    e = lambda time, kind, **kwargs: _event(time, kind, person, goal, **kwargs)
    return [e(0, "resource_ready", actor="resource_log", world={"F": "READY"}),
            e(1, "goal_started", world={"V": "VALID"}),
            e(2, "step_completed", step="verify"), e(3, "task_action", step="prepare"),
            e(4, "goal_suspended"), e(5, "interruption_started", demand_level=0.5,
                                           interrupting_goal_id="phone"),
            e(15, "interruption_ended", interrupting_goal_id="phone"),
            e(20, "location_returned")]


def _default_gold():
    return {"resume_label": "resume", "resume_step": "prepare", "window_complete": True,
            "state_labels": {"V": "VALID", "F": "READY", "A": "ACCESSED",
                             "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": "prepare"},
            "state_evidence": {"V": ["e01"], "F": ["e00"], "A": ["e00"],
                               "B": ["e01"], "C": ["e04"], "Q": ["e02", "e03"]}}


def _state(gold, factor, value, evidence):
    gold["state_labels"][factor] = value
    gold["state_evidence"][factor] = list(evidence)


def _no_resume(gold):
    gold["resume_label"], gold["resume_step"] = "not_resume", None


def _scenario(pair, variant, person, goal):
    events, gold = _base(person, goal), _default_gold()
    e = lambda time, kind, **kwargs: _event(time, kind, person, goal, **kwargs)
    a = variant == "A"
    if pair in {"P01", "P08"}:
        events.append(e(10, "cancellation", actor="backend", accessed=False, understood=False,
                        world={"V": "CANCELLED"}))
        if pair == "P01" and not a:
            events.append(e(12, "notification_queued", actor="app", accessed=False,
                            understood=False, value="cancellation", reference_event_id="e10"))
        else:
            events.append(e(12, "notification_understood", actor="app", understood=a,
                            value="cancellation", reference_event_id="e10",
                            **({} if a else {"interpretation": "defer"})))
        _state(gold, "V", "CANCELLED", ["e10"])
        _state(gold, "A", "ACCESSED" if a or pair == "P08" else "NOT_ACCESSED", ["e12"])
        if a:
            _state(gold, "B", "BELIEVES_INVALID", ["e12"])
            _state(gold, "C", "ABANDONED", ["e12"])
            _state(gold, "Q", "NOT_APPLICABLE", ["e12"])
            _no_resume(gold)
            gold["constraint_checks"] = {"known_cancelled": True}
        elif pair == "P08":
            _state(gold, "B", "UNRESOLVED", ["e12"])
            _state(gold, "C", "SUSPENDED", ["e12"])
            _no_resume(gold)  # Script waits after reading cancellation as a temporary hold.
            gold["constraint_checks"] = {"forbidden_belief": "BELIEVES_INVALID"}
        else:
            gold["constraint_checks"] = {"forbidden_belief": "BELIEVES_INVALID"}
    elif pair == "P02":
        # The differing old commitment is outside the identical last five events.
        events = [event for event in events if event["time"] < 10]
        events.append(e(6, "commitment_resume" if a else "goal_abandoned"))
        events.extend([e(10, "clock_tick", actor="clock"), e(12, "ambient_noise", actor="clock"),
                       e(15, "interruption_ended", interrupting_goal_id="phone"),
                       e(18, "clock_tick", actor="clock"), e(20, "location_returned")])
        _state(gold, "C", "SUSPENDED" if a else "ABANDONED", ["e06"])
        if not a:
            _state(gold, "Q", "NOT_APPLICABLE", ["e06"])
            _no_resume(gold)
    elif pair == "P03":
        events = [e(0, "resource_ready", actor="resource_log", world={"F": "READY"}),
                  e(1, "goal_started", world={"V": "VALID"}),
                  e(2, "step_completed", step="verify"),
                  e(3, "step_completed", step="prepare"),
                  e(4, "step_completed" if a else "task_action", step="print"),
                  e(5, "goal_suspended"),
                  e(6, "interruption_started", demand_level=0.5, interrupting_goal_id="phone"),
                  e(15, "interruption_ended", interrupting_goal_id="phone"), e(20, "location_returned")]
        step = "handover" if a else "print"
        gold["resume_step"] = step
        _state(gold, "C", "SUSPENDED", ["e05"])
        _state(gold, "Q", step, ["e02", "e03", "e04"])
    elif pair == "P04":
        # World is complete in both. Repeating a completed step is not T1 recovery.
        for time, step in ((7, "prepare"), (8, "print"), (9, "handover")):
            events.append(e(time, "step_completed", actor="colleague", step=step,
                            accessed=False, understood=False))
        events.append(e(10, "fulfillment", actor="colleague", accessed=False, understood=False,
                        world={"V": "FULFILLED"}))
        events.append(e(12, "notification_understood" if a else "notification_queued", actor="app",
                        accessed=a, understood=a, value="fulfillment", reference_event_id="e10"))
        _state(gold, "V", "FULFILLED", ["e07", "e08", "e09", "e10"])
        _state(gold, "A", "ACCESSED" if a else "NOT_ACCESSED", ["e12"])
        if a:
            _state(gold, "B", "BELIEVES_INVALID", ["e12"])
            _state(gold, "C", "COMPLETED", ["e12"])
            _state(gold, "Q", "NOT_APPLICABLE", ["e12"])
        else:
            gold["constraint_checks"] = {"forbidden_belief": "BELIEVES_INVALID"}
        _no_resume(gold)
    elif pair == "P05":
        events.append(e(10, "resource_blocked", actor="resource_log", world={"F": "BLOCKED"}))
        events.append(e(12, "resource_ready" if a else "resource_blocked", actor="resource_log",
                        world={"F": "READY" if a else "BLOCKED"}))
        _state(gold, "F", "READY" if a else "BLOCKED", ["e12"])
        _state(gold, "A", "ACCESSED", ["e12"])
        if not a:
            _no_resume(gold)
    elif pair == "P06":
        urgent = goal + "_urgent"
        events = [event for event in events if event["time"] < 5]
        events.extend([
            e(5, "interruption_started", demand_level=0.6),
            _event(6, "goal_started", person, urgent, parent_goal_id=goal),
            _event(7, "task_action", person, urgent, step="resolve"),
            _event(8, "goal_suspended", person, urgent),
            _event(9, "interruption_started", person, urgent, interrupting_goal_id="phone", demand_level=0.8),
            _event(12, "interruption_ended", person, urgent, interrupting_goal_id="phone"),
            _event(14, "goal_completed" if a else "task_action", person, urgent,
                   **({"task_completed": True} if a else {"step": "resolve"})),
            e(20, "location_returned")])
        if not a:
            _no_resume(gold)  # The script prioritizes the unfinished inserted task for H=3.
    elif pair == "P07":
        # Gold-only future behavior differs; nothing in the prediction input changes.
        if not a:
            _no_resume(gold)
    else:
        raise ValueError(f"unknown scenario {pair}")
    events.sort(key=lambda event: event["time"])
    gold["annotation_source"] = SOURCE + f"; scenario={pair}; variant={variant}; cutoff states scripted"
    return events, gold


def _record(split, family, variant, events, person, goal):
    return {"sample_id": f"{split}_{family}_{variant}", "base_story_id": f"{split}_{family}",
            "person_id": person, "task_family": f"{split}_{family}_script_template",
            "domain": DOMAINS[split], "split": split, "purpose": "synthetic_integration_fixture",
            "observation": {"target_person": person, "goal_id": goal, "task_steps": list(STEPS),
                            "task_graph": {"nodes": list(STEPS),
                                           "edges": [[STEPS[i], STEPS[i + 1]] for i in range(len(STEPS) - 1)]},
                            "cutoff": 20, "horizon": {"type": "decision_opportunities", "value": 3},
                            "events": events}}


def make_fixtures():
    """Return 72 deterministic records and separately held scripted gold rows."""
    records, golds = [], []
    for split in SPLITS:
        for index in range(1, 9):
            pair = f"P{index:02d}"
            person, goal = f"person_{split}_{pair}", f"goal_{split}_{pair}"
            for variant in ("A", "B"):
                events, gold = _scenario(pair, variant, person, goal)
                record = _record(split, pair, variant, events, person, goal)
                gold.update(sample_id=record["sample_id"], dataset_layer="integration_fixture")
                if pair in {"P01", "P04", "P08"}:
                    gold.update(pair_id=record["base_story_id"], pair_relation="different_belief", pair_factor="B")
                elif pair == "P07":
                    gold.update(pair_id=record["base_story_id"], pair_relation="same_prediction")
                records.append(record)
                golds.append(gold)
        for status in ("censored", "unknown"):
            family = "status_" + status
            person, goal = f"person_{split}_{family}", f"goal_{split}_{family}"
            record = _record(split, family, "single", _base(person, goal), person, goal)
            gold = _default_gold()
            gold.update(sample_id=record["sample_id"], dataset_layer="integration_fixture",
                        resume_label=status, resume_step=None, window_complete=status != "censored",
                        annotation_source=SOURCE + "; outcome deliberately unobservable/unattributable")
            records.append(record)
            golds.append(gold)
    validate_dataset(records, golds)
    return records, golds


def build(output_dir=None):
    """Write inputs.jsonl / labels.jsonl and return their paths plus counts/hashes."""
    records, golds = make_fixtures()
    destination = Path(output_dir) if output_dir else ROOT / "data" / "integration"
    destination.mkdir(parents=True, exist_ok=True)
    paths = {"inputs": destination / "inputs.jsonl", "labels": destination / "labels.jsonl"}
    for key, rows in (("inputs", records), ("labels", golds)):
        paths[key].write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                      for row in rows), encoding="utf-8")
    return {"inputs": str(paths["inputs"]), "labels": str(paths["labels"]),
            **validate_dataset(records, golds), "inputs_hash": canonical_hash(records),
            "labels_hash": canonical_hash(golds)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    print(json.dumps(build(parser.parse_args().output_dir), ensure_ascii=False, indent=2))
