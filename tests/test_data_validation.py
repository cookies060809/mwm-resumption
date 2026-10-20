import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_data import check_record, load_records, validate_all  # noqa: E402

V02_PATH = ROOT / "data" / "p0" / "p0_samples_v0.2.json"
V03_PATH = ROOT / "data" / "p0" / "p0_samples_v0.3.json"


def load_v02():
    return json.loads(V02_PATH.read_text(encoding="utf-8"))


def load_v03():
    return json.loads(V03_PATH.read_text(encoding="utf-8"))


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


def test_v02_split_is_blueprint_disjoint() -> None:
    """A task blueprint must not appear in two splits, otherwise the model can
    memorise the task rather than the mechanism. Checked over every v0.2-line
    batch, because a follow-up batch is where a reused blueprint would slip in."""
    records = load_v02() + load_v03()
    blueprint_splits: dict[str, set[str]] = {}
    for record in records:
        family = record["base_story_id"]
        blueprint = family.split("-", 1)[1] if "-" in family else f"seed_{family}"
        blueprint_splits.setdefault(blueprint, set()).add(record["split"])
    crossed = {key: value for key, value in blueprint_splits.items() if len(value) > 1}
    assert crossed == {}, f"blueprints crossing splits: {crossed}"


def test_v03_batch_is_draft_candidate_work() -> None:
    records = load_v03()
    assert len(records) == 14
    assert len({record["base_story_id"] for record in records}) == 7
    assert all(record["schema_version"] == "p0-record/v0.2.0" for record in records)
    # B has not signed this batch yet, so it must not look like accepted data.
    assert all(record["annotation"]["status"] == "draft" for record in records)
    assert all(record["annotation"]["annotator_id"] == "agent-draft" for record in records)


def test_v03_closes_the_uncertainty_enum_gaps() -> None:
    """v0.2 hits its 240-record target while 11 uncertainty values stay unused, so
    volume alone cannot show the mechanism cells are covered. Pooling v0.2 with the
    v0.3 uncertainty batch must leave only the split C has not decided on."""
    from scripts.p0_quality_report import enum_counts
    from scripts.validate_data import SCHEMAS, load_json

    schema = load_json(SCHEMAS["p0-record/v0.2.0"])
    records = load_v02() + load_v03()
    events = [event for record in records for event in record["observed_events"]]
    unused = [
        f"{label}.{value}"
        for label, (allowed, counts) in enum_counts(records, events, schema).items()
        for value in allowed
        if not counts.get(value)
    ]
    assert unused == ["record.split.calibration"]


def test_export_matches_evaluation_protocol() -> None:
    from scripts.export_eval_format import to_input, to_label

    records = load_v02()
    inputs = [to_input(record) for record in records]
    labels = [to_label(record) for record in records]
    assert len(inputs) == len(labels) == 240

    resume = {}
    for label in labels:
        resume[label["resume_label"]] = resume.get(label["resume_label"], 0) + 1
        assert label["dataset_layer"] == "P0"
        assert label["window_complete"] is True
        if label["resume_label"] != "resume":
            assert label["resume_step"] is None
    assert resume == {"resume": 90, "not_resume": 120, "unknown": 30}

    for item in inputs:
        assert item["purpose"] == "scripted_p0"
        observation = item["observation"]
        assert set(observation) == {
            "target_person",
            "goal_id",
            "task_steps",
            "task_graph",
            "cutoff",
            "horizon",
            "events",
        }
        assert all(isinstance(event["time"], int) for event in observation["events"])
        assert observation["events"][-1]["time"] <= observation["cutoff"]
        for event in observation["events"]:
            assert set(event["person_access_evidence"]) == {"status", "understood"}
            assert event["person_access_evidence"]["understood"] in (True, False, None)

    # Future-leak pairs have no point label but keep identical observations.
    leak = {
        record["base_story_id"]: to_input(record)
        for record in records
        if record["mechanism"] == "future_leak"
    }
    for family, item in leak.items():
        pair = [r for r in records if r["base_story_id"] == family and r["mechanism"] == "future_leak"]
        a, b = (to_input(record)["observation"] for record in sorted(pair, key=lambda r: r["variant"]))
        assert json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(
            b, sort_keys=True, ensure_ascii=False
        )
        assert item["observation"]["cutoff"] > 0
