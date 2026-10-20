import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_data import check_record, load_records, validate_all  # noqa: E402

V02_PATH = ROOT / "data" / "p0" / "p0_samples_v0.2.json"


def load_v02():
    return json.loads(V02_PATH.read_text(encoding="utf-8"))


def test_repository_data_valid() -> None:
    errors = validate_all(verbose=False)
    assert errors == [], "\n".join(errors)


def test_seed_batch_shape() -> None:
    records = load_records()
    assert len(records) == 16
    assert {record["base_story_id"] for record in records} == {
        f"P{index:02d}" for index in range(1, 9)
    }
    assert {record["variant"] for record in records} == {"A", "B"}
    assert all(record["annotation"]["status"] == "draft" for record in records)
    assert all(record["p1_observed_resume"] is None for record in records)


def test_p07_input_identity() -> None:
    records = load_records()
    p07 = {record["variant"]: record for record in records if record["base_story_id"] == "P07"}
    ignore = {"sample_id", "variant", "notes"}
    a_core = {key: value for key, value in p07["A"].items() if key not in ignore}
    b_core = {key: value for key, value in p07["B"].items() if key not in ignore}
    assert json.dumps(a_core, ensure_ascii=False, sort_keys=True) == json.dumps(
        b_core, ensure_ascii=False, sort_keys=True
    )


def test_future_event_is_rejected() -> None:
    record = copy.deepcopy(
        next(record for record in load_records() if record["sample_id"] == "P07-A")
    )
    record["observed_events"][0]["time"] = "23:59"
    errors: list[str] = []
    check_record(record, errors)
    assert any(
        "non-decreasing" in message or "after cutoff" in message for message in errors
    )


def test_v02_batch_shape() -> None:
    records = load_v02()
    families = {record["base_story_id"] for record in records}
    assert len(families) == 120
    assert len(records) == 240
    assert {record["variant"] for record in records} == {"A", "B"}
    assert all(record["schema_version"] == "p0-record/v0.2.0" for record in records)
    assert all(len(family_events(record)) > 0 for record in records)


def family_events(record):
    return record["observed_events"]


def test_v02_split_is_family_level_and_stratified() -> None:
    records = load_v02()
    split_by_family = {}
    for record in records:
        previous = split_by_family.setdefault(record["base_story_id"], record["split"])
        assert previous == record["split"], "A/B variants must share one split"
    totals = {}
    for split in split_by_family.values():
        totals[split] = totals.get(split, 0) + 1
    assert totals == {"train": 72, "dev": 24, "test": 24}
    for mechanism in {record["mechanism"] for record in records}:
        per_split = {}
        for record in records:
            if record["mechanism"] != mechanism:
                continue
            per_split[record["split"]] = per_split.get(record["split"], 0) + (record["variant"] == "A")
        assert per_split == {"train": 9, "dev": 3, "test": 3}


def test_v02_future_leak_families_are_indeterminate() -> None:
    records = [record for record in load_v02() if record["mechanism"] == "future_leak"]
    assert len({record["base_story_id"] for record in records}) == 15
    for record in records:
        assert record["p0_expected_action"] == "indeterminate"
        assert record["p0_expected"]["resume_within_horizon"] is None
        assert record["p0_expected"]["undefined_reason"] == "indistinguishable_inputs"
        assert record["p0_design"]["undefined_target"] is True
        assert "未来泄漏" in record["notes"]


def test_v02_comprehension_requires_access() -> None:
    for record in load_v02():
        for event in record["observed_events"]:
            if event["person_access"] != "ACCESSED":
                assert event["person_comprehension"] == "NOT_APPLICABLE"


def test_v02_comprehension_pairs_are_isolated() -> None:
    records = load_v02()
    by_family = {}
    for record in records:
        by_family.setdefault(record["base_story_id"], {})[record["variant"]] = record
    for family, pair in by_family.items():
        if pair["A"]["mechanism"] != "comprehension":
            continue
        a_labels = [e["person_comprehension"] for e in pair["A"]["observed_events"]]
        b_labels = [e["person_comprehension"] for e in pair["B"]["observed_events"]]
        assert "UNDERSTOOD" in a_labels, family
        assert "MISUNDERSTOOD" in b_labels, family
        assert pair["A"]["state_at_cutoff"]["A"] == "ACCESSED"
        assert pair["B"]["state_at_cutoff"]["A"] == "ACCESSED"


def test_v02_other_completion_repeat_is_not_resume() -> None:
    records = load_v02()
    p04 = {
        record["variant"]: record
        for record in records
        if record["base_story_id"] == "P04"
    }
    assert p04["B"]["p0_expected"]["resume_within_horizon"] is False
    assert p04["B"]["p0_expected"]["first_step"] is None
    assert p04["B"]["state_at_cutoff"]["Q"] != "NOT_APPLICABLE"


def test_v02_completed_steps_replay() -> None:
    for record in load_v02():
        steps = set(record["task_steps"])
        completed = {
            event["step_id"]
            for event in record["observed_events"]
            if event["event_type"] == "step_completed" and event["goal_id"] == record["goal_id"]
        }
        if any(
            event["event_type"] == "task_completed_by_other"
            and event["goal_id"] == record["goal_id"]
            for event in record["observed_events"]
        ):
            assert record["completed_steps_at_cutoff"] == list(record["task_steps"])
        else:
            assert set(record["completed_steps_at_cutoff"]) == completed & steps


def test_v02_unknown_labels_carry_no_evidence() -> None:
    for record in load_v02():
        for factor, value in record["state_at_cutoff"].items():
            if value == "UNKNOWN":
                assert record["state_evidence_by_factor"][factor] == []
