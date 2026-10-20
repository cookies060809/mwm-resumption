"""Acceptance properties for synthetic system fixtures, not model accuracy."""

import tempfile
import unittest
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

from mwm_eval.schema import canonical_hash, load_jsonl, validate_dataset, validate_observation
from tools.build_integration_fixtures import build, make_fixtures


class IntegrationFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.golds = make_fixtures()
        cls.by_id = {row["sample_id"]: row for row in cls.records}
        cls.by_gold = {row["sample_id"]: row for row in cls.golds}

    def test_complete_dataset_passes_canonical_contract(self):
        summary = validate_dataset(self.records, self.golds)
        self.assertEqual(summary["n"], 72)
        self.assertEqual(summary["dataset_layer"], "integration_fixture")
        self.assertEqual(set(summary["split_counts"].values()), {18})

    def test_rebuild_is_deterministic_and_disk_files_validate(self):
        self.assertEqual(make_fixtures(), (self.records, self.golds))
        with tempfile.TemporaryDirectory() as directory:
            result = build(directory)
            records = load_jsonl(result["inputs"])
            golds = load_jsonl(result["labels"])
            validate_dataset(records, golds)
            self.assertEqual(canonical_hash(records), result["inputs_hash"])
            self.assertEqual(canonical_hash(golds), result["labels_hash"])
            self.assertTrue(Path(result["labels"]).is_file())

    def test_family_person_and_task_ids_do_not_cross_splits(self):
        for field in ("base_story_id", "person_id", "task_family"):
            assignments = defaultdict(set)
            for record in self.records:
                assignments[record[field]].add(record["split"])
            self.assertTrue(all(len(splits) == 1 for splits in assignments.values()))
        broken = deepcopy(self.records)
        broken[-1]["base_story_id"] = broken[0]["base_story_id"]
        with self.assertRaisesRegex(ValueError, "crosses"):
            validate_dataset(broken, self.golds)

    def test_censored_and_unknown_are_explicit_and_not_negative_labels(self):
        counts = Counter(gold["resume_label"] for gold in self.golds)
        self.assertEqual(counts["censored"], 4)
        self.assertEqual(counts["unknown"], 4)
        self.assertEqual(counts["resume"] + counts["not_resume"], 64)
        for gold in self.golds:
            if gold["resume_label"] == "censored":
                self.assertFalse(gold["window_complete"])
                self.assertIsNone(gold["resume_step"])

    def test_gold_and_sample_ids_never_enter_prediction_observation(self):
        forbidden = {"sample_id", "resume_label", "resume_step", "state_labels", "state_evidence",
                     "dataset_layer", "pair_id", "pair_relation", "constraint_checks"}
        def assert_clean(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden & value.keys())
                for item in value.values():
                    assert_clean(item)
            elif isinstance(value, list):
                for item in value:
                    assert_clean(item)
        for record in self.records:
            assert_clean(record["observation"])

    def test_p02_latest_five_are_exactly_equal_despite_older_commitment(self):
        for split in ("train", "dev", "calibration", "test"):
            a = self.by_id[f"{split}_P02_A"]["observation"]["events"]
            b = self.by_id[f"{split}_P02_B"]["observation"]["events"]
            self.assertEqual(a[-5:], b[-5:])
            self.assertNotEqual(a[:-5], b[:-5])

    def test_p07_same_input_and_cutoff_state_but_different_future_outcomes(self):
        for split in ("train", "dev", "calibration", "test"):
            left, right = f"{split}_P07_A", f"{split}_P07_B"
            self.assertEqual(self.by_id[left]["observation"], self.by_id[right]["observation"])
            a, b = self.by_gold[left], self.by_gold[right]
            self.assertEqual(a["state_labels"], b["state_labels"])
            self.assertEqual(a["state_evidence"], b["state_evidence"])
            self.assertNotEqual(a["resume_label"], b["resume_label"])
            self.assertEqual(a["pair_relation"], "same_prediction")

    def test_p04_does_not_count_repeating_fulfilled_task_as_recovery(self):
        for split in ("train", "dev", "calibration", "test"):
            a, b = self.by_gold[f"{split}_P04_A"], self.by_gold[f"{split}_P04_B"]
            self.assertEqual(a["resume_label"], "not_resume")
            self.assertEqual(b["resume_label"], "not_resume")
            self.assertEqual(a["state_labels"]["V"], "FULFILLED")
            self.assertEqual(b["state_labels"]["V"], "FULFILLED")
            self.assertNotEqual(a["state_labels"]["B"], b["state_labels"]["B"])

    def test_p05_blocked_does_not_imply_abandonment(self):
        for split in ("train", "dev", "calibration", "test"):
            gold = self.by_gold[f"{split}_P05_B"]
            self.assertEqual(gold["state_labels"]["F"], "BLOCKED")
            self.assertEqual(gold["state_labels"]["C"], "SUSPENDED")

    def test_state_evidence_is_before_cutoff_and_all_nonunknown_states_are_supported(self):
        for record, gold in zip(self.records, self.golds):
            obs = record["observation"]
            validate_observation(obs)
            events = {event["event_id"]: event for event in obs["events"]}
            self.assertTrue(any(event["semantic"]["kind"] == "interruption_started"
                                for event in obs["events"]))
            for factor, label in gold["state_labels"].items():
                if label not in {"UNKNOWN", "UNCERTAIN"}:
                    self.assertTrue(gold["state_evidence"][factor])
                self.assertTrue(all(events[event_id]["time"] <= obs["cutoff"]
                                    for event_id in gold["state_evidence"][factor]))


if __name__ == "__main__":
    unittest.main()
