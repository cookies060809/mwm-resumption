"""New shared-repository contract regressions using the actual P0 batch.

No local A test files or synthetic stories are migrated. Mutation checks edit
copies in memory only and never rewrite B's dataset.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from models.ecr_mwm.p0_adapter import adapt_record, person_inputs, replay_completion_evidence, scripted_targets  # noqa: E402
from models.ecr_mwm.p0_diagnostics import run_diagnostics  # noqa: E402


@pytest.fixture
def records():
    return json.loads((ROOT / "data/p0/p0_samples.json").read_text(encoding="utf-8"))


def test_real_batch_controlled_contract(records):
    report = run_diagnostics(records)
    assert report["records"] == 16
    assert report["events"] == 123
    assert all(report["checks"].values()), report["checks"]
    assert report["p1_first_step_key_present"] == 0


def test_input_mapping_is_detached(records):
    original = deepcopy(records[0])
    mapped = adapt_record(records[0])
    mapped["events"][0]["world"]["description"] = "changed copy"
    mapped["observer_graphs"][original["goal_id"]]["steps"].append("changed-copy")
    assert records[0] == original


def test_access_does_not_infer_comprehension(records):
    for record in records:
        view = adapt_record(record)
        for raw, mapped, person in zip(record["observed_events"], view["events"], person_inputs(view)):
            assert mapped["delivery"]["comprehension"] == "not_structurally_labeled"
            assert "world" not in person and "observer_graphs" not in person
            if raw["actor"] != "person":
                assert mapped["person"] is None


def test_unknown_version_and_horizon_rejected(records):
    record = deepcopy(records[0])
    record["schema_version"] = "0.1-provisional"
    with pytest.raises(ValueError, match="SCHEMA_VERSION"):
        adapt_record(record)
    record = deepcopy(records[0])
    record["horizon"]["type"] = "time_window"
    with pytest.raises(ValueError, match="HORIZON"):
        adapt_record(record)


def test_future_and_wrong_cutoff_rejected(records):
    record = deepcopy(records[0])
    record["observed_events"][0]["time"] = "23:59"
    with pytest.raises(ValueError, match="FUTURE_OR_UNORDERED"):
        adapt_record(record)
    record = deepcopy(records[0])
    record["cutoff_event_id"] = record["observed_events"][0]["event_id"]
    with pytest.raises(ValueError, match="CUTOFF_NOT_LAST"):
        adapt_record(record)


def test_cycle_and_unknown_steps_rejected(records):
    record = deepcopy(records[0])
    record["task_dependencies"].append({"before": record["task_steps"][-1], "after": record["task_steps"][0]})
    with pytest.raises(ValueError, match="CYCLIC"):
        adapt_record(record)
    record = deepcopy(records[0])
    record["observed_events"][0]["step_id"] = "not-in-graph"
    with pytest.raises(ValueError, match="UNKNOWN_EVENT_STEP"):
        adapt_record(record)


def test_nested_target_is_not_t2(records):
    record = next(r for r in records if r["sample_id"] == "P06-B")
    target = scripted_targets(record)
    assert target["scripted_next_action_step"] == "replace_toner"
    assert target["t2_original_goal_step"] is None
    assert target["t2_mask"] is False


def test_real_completion_evidence_is_not_mental_truth(records):
    record = next(r for r in records if r["sample_id"] == "P04-B")
    progress = replay_completion_evidence(adapt_record(record))
    goal = record["goal_id"]
    assert "fill_form" in progress["world_done"][goal]
    assert "fill_form" not in progress["self_completion_evidence"][goal]
