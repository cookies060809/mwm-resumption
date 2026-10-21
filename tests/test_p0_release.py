"""Standalone release admission: provenance, split leakage and stale artifacts."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_p0_release import OUT, SOURCES, check_release, release_files  # noqa: E402
from scripts.export_eval_format import to_input, to_label  # noqa: E402


@pytest.fixture(scope="module")
def release():
    return json.loads((OUT / "p0_samples.json").read_bytes())


def test_standalone_release_preserves_signed_source_records(release):
    originals = {r["sample_id"]: r for path in SOURCES for r in json.loads(path.read_bytes())}
    assert len(release) == len(originals) == 254
    assert {r["sample_id"]: r for r in release} == originals
    assert check_release(release) == []
    assert Counter(r["split"] for r in release) == {"train": 150, "dev": 52, "test": 52}
    assert len({r["base_story_id"] for r in release}) == 127


def test_committed_release_is_reproducible_and_hashes_match():
    for name, expected in release_files().items():
        assert (OUT / name).read_bytes() == expected, name
    manifest = json.loads((OUT / "manifest.json").read_bytes())
    assert manifest["unused_enum_values"] == ["record.split.calibration"]
    for name, info in manifest["artifacts"].items():
        raw = (OUT / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == info["sha256"]
        assert len(raw) == info["bytes"]


def test_release_split_files_partition_all_records(release):
    seen = set()
    for split in ("train", "dev", "test", "calibration"):
        records = json.loads((OUT / "splits" / f"{split}.json").read_bytes())
        assert all(r["split"] == split for r in records)
        ids = {r["sample_id"] for r in records}
        assert not seen & ids
        seen |= ids
    assert seen == {r["sample_id"] for r in release}
    assert json.loads((OUT / "splits/calibration.json").read_bytes()) == []


def test_release_rejects_duplicates_and_cross_split_blueprints(release):
    assert any("duplicate sample_id" in e for e in check_release(release + release[:2]))
    changed = deepcopy(release)
    # Move an intact A/B family while leaving other mechanisms of its blueprint.
    family = next(r["base_story_id"] for r in changed if r["base_story_id"].endswith("-W1"))
    for record in changed:
        if record["base_story_id"] == family:
            record["split"] = "test"
    assert any("blueprint crosses splits" in e for e in check_release(changed))
    with pytest.raises(ValueError, match="duplicate sample_id"):
        release_files(sources=(SOURCES[0], SOURCES[0]))


def test_release_export_and_future_controls_are_aligned(release):
    inputs = [json.loads(line) for line in (OUT / "eval/inputs.jsonl").read_text(encoding="utf-8").splitlines()]
    labels = [json.loads(line) for line in (OUT / "eval/labels.jsonl").read_text(encoding="utf-8").splitlines()]
    assert inputs == [to_input(r) for r in release]
    assert labels == [to_label(r) for r in release]
    assert len(inputs) == len(labels) == 254
    by_id = {r["sample_id"]: r for r in inputs}
    label_by_id = {r["sample_id"]: r for r in labels}
    future_pairs = [r for r in release if r["mechanism"] == "future_leak" and r["variant"] == "A"]
    assert len(future_pairs) == 15
    for record in future_pairs:
        a, b = record["base_story_id"] + "-A", record["base_story_id"] + "-B"
        assert by_id[a]["observation"] == by_id[b]["observation"]
        assert label_by_id[a]["resume_label"] == label_by_id[b]["resume_label"] == "unknown"
    # Changing gold/audit data cannot change the emitted model observation.
    changed = deepcopy(release[0])
    for key in ("state_at_cutoff", "state_evidence_by_factor", "p0_expected", "p0_design", "annotation", "notes"):
        changed[key] = {"poisoned_gold": True}
    assert to_input(changed) == to_input(release[0])
