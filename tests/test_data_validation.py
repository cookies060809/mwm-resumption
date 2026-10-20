import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_data import semantic_errors, validate_all  # noqa: E402


def test_repository_data_valid() -> None:
    errors = validate_all(verbose=False)
    assert errors == [], "\n".join(errors)


def test_future_event_is_rejected() -> None:
    record = json.loads(
        (ROOT / "data/p0/examples/work/P01-B.json").read_text(encoding="utf-8")
    )
    record["observed_events"][0]["time"] = "10:06"
    errors = semantic_errors(record)
    assert any("after cutoff" in error for error in errors)


def test_p01_pair_is_linked() -> None:
    a = json.loads(
        (ROOT / "data/p0/examples/work/P01-A.json").read_text(encoding="utf-8")
    )
    b = json.loads(
        (ROOT / "data/p0/examples/work/P01-B.json").read_text(encoding="utf-8")
    )
    assert a["counterfactual_pair"]["paired_sample_id"] == b["sample_id"]
    assert b["counterfactual_pair"]["paired_sample_id"] == a["sample_id"]
    assert a["base_story_id"] == b["base_story_id"] == "P01"
    assert a["split"] == b["split"]
