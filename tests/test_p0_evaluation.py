"""Regression checks against B's actual frozen P0, including silent mapping bugs."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from mwm_eval.engine import dump_jsonl, predict_rows, run_experiment
from mwm_eval.local_baselines import make_local_baselines
from mwm_eval.metrics import evaluate
from mwm_eval.p0 import adapt_input, prepare_dataset
from mwm_eval.schema import audit_groups, canonical_hash, validate_dataset
from scripts.run_p0_evaluation import require_accepted_batch

ROOT = Path(__file__).resolve().parents[1]


class P0EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / "data/p0/p0_samples_v0.2.json").read_text(encoding="utf-8"))
        cls.records, cls.golds = prepare_dataset(cls.source)

    def test_frozen_batch_has_valid_splits_and_no_group_overlap(self):
        report = validate_dataset(self.records, self.golds)
        self.assertEqual(report["split_counts"], {"train": 144, "dev": 48, "calibration": 0, "test": 48})
        for key in ("base_story_id", "person_id", "task_family"):
            self.assertFalse(any(audit_groups(self.records)[key]["pairwise_overlap"].values()))
        self.assertEqual(sum(g["resume_label"] == "unknown" for g in self.golds), 30)

    def test_draft_candidate_batch_cannot_enter_formal_evaluation(self):
        require_accepted_batch(self.source)
        candidates = json.loads((ROOT / "data/p0/p0_samples_v0.3.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "Draft/candidate"):
            require_accepted_batch(candidates)

    def test_own_actor_matches_target_without_family_id_in_observation(self):
        self.assertTrue(all(r["observation"]["target_person"] == "person" for r in self.records))
        self.assertEqual(sum(e["actor"] == r["observation"]["target_person"]
                             for r in self.records for e in r["observation"]["events"]), 1227)

    def test_identity_labels_and_future_design_cannot_change_model_observation(self):
        original = self.source[0]
        mutated = copy.deepcopy(original)
        for key in ("state_at_cutoff", "state_evidence_by_factor", "p0_expected", "p0_design",
                    "annotation", "notes", "p1_observed_resume", "p0_scripted_policy"):
            mutated[key] = {"POISON_FUTURE_SECRET": True}
        for key in ("sample_id", "base_story_id", "variant"):
            mutated[key] = "POISON_FUTURE_SECRET"
        left, right = adapt_input(original)["observation"], adapt_input(mutated)["observation"]
        self.assertEqual(left, right)
        self.assertNotIn("POISON_FUTURE_SECRET", json.dumps(right))

    def test_typed_message_content_is_not_world_state_or_gold(self):
        record = next(r for r in self.source if r["sample_id"] == "P01-A")
        obs = adapt_input(record)["observation"]
        notification = next(e for e in obs["events"] if e["event_type"] == "notification")
        self.assertEqual(notification["semantic"]["value"], "cancellation")
        self.assertTrue(notification["person_access_evidence"]["understood"])
        variant = copy.deepcopy(record)
        original = next(e for e in variant["observed_events"] if e["event_type"] == "notification_sent")
        original["person_available_semantics"]["kind"] = "none"
        mapped = next(e for e in adapt_input(variant)["observation"]["events"] if e["event_type"] == "notification")
        self.assertNotIn("value", mapped["semantic"])

    def test_pair_definitions_preserve_unknown_future_and_completed_target_masks(self):
        by_id = {g["sample_id"]: g for g in self.golds}
        self.assertNotIn({"target": "T1", "relation": "match_gold"}, by_id["P07-A"]["pair_checks"])
        self.assertIn({"target": "p_resume", "relation": "equal"}, by_id["P07-A"]["pair_checks"])
        self.assertEqual(by_id["P04-B"]["resume_label"], "not_resume")
        self.assertIsNone(by_id["P04-B"]["resume_step"])
        self.assertIsNone(by_id["P06-B"]["resume_step"])
        for record in self.records:
            for event in record["observation"]["events"]:
                if event["event_type"] == "interruption_started":
                    self.assertNotIn("interrupting_goal_id", event["semantic"])

    def test_future_probability_change_detected_even_when_hard_label_is_same(self):
        records = [r for r in self.records if r["base_story_id"] == "P07"]
        golds = [g for g in self.golds if g["pair_id"] == "P07"]
        rows = predict_rows(make_local_baselines()["B0"], records, 0)
        rows[0]["prediction"]["p_resume"] = 0.6
        rows[1]["prediction"]["p_resume"] = 0.8
        result = evaluate(rows, golds, records)["mechanism_pairs"]["future_leak"]
        self.assertEqual(result["hard_decision:equal"]["rate"], 1)
        self.assertEqual(result["p_resume:equal"]["rate"], 0)
        self.assertIsNone(result["state_probs:equal"]["rate"])
        self.assertEqual(result["state_probs:equal"]["n_missing_output"], 1)

    def test_both_members_must_match_gold_not_merely_differ(self):
        records = [r for r in self.records if r["base_story_id"] == "P01"]
        golds = [g for g in self.golds if g["pair_id"] == "P01"]
        rows = predict_rows(make_local_baselines()["B0"], records, 0)
        for row, gold in zip(rows, golds):
            row["prediction"]["resume_label"] = "resume" if gold["resume_label"] == "not_resume" else "not_resume"
        result = evaluate(rows, golds, records)["mechanism_pairs"]["contact_cancellation"]
        self.assertEqual(result["T1:match_gold"]["rate"], 0)

    def test_formal_batch_scores_all_methods_without_touching_source(self):
        before = canonical_hash(self.source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump_jsonl(root / "inputs.jsonl", self.records)
            dump_jsonl(root / "labels.jsonl", self.golds)
            summary, status = run_experiment(root / "inputs.jsonl", root / "labels.jsonl", root / "run", {},
                                            ["B0", "B1", "B4", "B5", "B6", "B7"], [0], suite="all")
        self.assertEqual(status["overall"], "independent_C_pipeline_completed")
        for run in summary["runs"]:
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["metrics"]["counts"]["n_eligible_t1"], 42)
            self.assertEqual(run["metrics"]["counts"]["n_excluded"]["unknown"], 6)
            self.assertEqual(len(run["metrics"]["mechanism_pairs"]), 8)
            self.assertFalse(run["calibration"]["applicable"])
        self.assertEqual(canonical_hash(self.source), before)


if __name__ == "__main__":
    unittest.main()
