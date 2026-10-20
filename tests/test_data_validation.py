import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_data import check_record, load_records, validate_all  # noqa: E402


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
