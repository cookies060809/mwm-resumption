import copy
import json
import tempfile
import unittest
from pathlib import Path

from integration.a_model import StructuredECJMF
from integration.a_input_adapter import validate_structured_evidence
from models.ecr_mwm.p0_adapter import adapt_record
from mwm_eval.engine import actual_observation, dump_jsonl, run_experiment
from mwm_eval.p0 import adapt_input, prepare_dataset
from mwm_eval.schema import canonical_hash, validate_observation
from scripts.check_p0_reproducibility import snapshot

ROOT = Path(__file__).resolve().parents[1]


class AModelIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / "data/p0/p0_samples_v0.2.json").read_text(encoding="utf-8"))
        cls.records, cls.golds = prepare_dataset(cls.source)

    def test_actual_A_view_is_lossless_and_rejects_injected_labels_or_different_history(self):
        for raw, record in zip(self.source, self.records):
            observation = record["observation"]
            self.assertEqual(observation["structured_evidence"], adapt_record(raw))
            validate_observation(observation)
        for transform in ("gold", "person", "time", "canonical"):
            obs = copy.deepcopy(self.records[0]["observation"])
            if transform == "gold":
                obs["structured_evidence"]["state_at_cutoff"] = {"B": "BELIEVES_VALID"}
            elif transform == "person":
                obs["structured_evidence"]["events"][0]["person"]["gold"] = True
            elif transform == "time":
                obs["structured_evidence"]["events"][-1]["time_minutes"] += 1
            else:
                obs["events"][0]["observer_evidence"] = "different evidence"
            with self.assertRaises(ValueError):
                validate_observation(obs)

    def test_comprehension_and_nested_identity_survive_while_short_window_stays_short(self):
        source = json.loads((ROOT / "data/p0/p0_samples_v0.3.json").read_text(encoding="utf-8"))
        values = {event["delivery"]["comprehension"] for raw in source
                  for event in adapt_input(raw)["observation"]["structured_evidence"]["events"]}
        self.assertTrue({"MISUNDERSTOOD", "NOT_UNDERSTOOD", "UNCERTAIN"} <= values)
        nested = next(raw for raw in self.source if raw["sample_id"] == "P06-A")
        self.assertIn(nested["interrupting_task"]["goal_id"], adapt_input(nested)["observation"]["structured_evidence"]["observer_graphs"])
        obs = actual_observation(self.records[0], "B1")
        self.assertEqual([e["event_id"] for e in obs["events"]], [e["event_id"] for e in obs["structured_evidence"]["events"]])
        validate_observation(obs)

    def test_train_only_fits_checkpoint_and_future_leak_invariance_uses_real_A(self):
        pairs = [(r["observation"], g) for r, g in zip(self.records, self.golds) if r["split"] == "train"]
        model = StructuredECJMF(config={"state_epochs": 0, "joint_epochs": 1})
        # Two actual training records are sufficient for a contract regression;
        # the experiment runner trains on the entire frozen training split.
        model.fit(pairs[:2])
        self.assertEqual(model.training["train_n"], 2)
        self.assertLessEqual(model.training["stages"][0]["history"][-1]["loss"], model.training["stages"][0]["initial"]["loss"])
        future = [r for r in self.records if r["base_story_id"] == "P07"]
        rows = [{"method_id": "B10", "seed": 0, "sample_id": r["sample_id"], "status": "ok",
                 "input_hash": "same", "source_input_hash": "same", "prediction": model.predict(r["observation"])} for r in future]
        values = list(snapshot(rows).values())
        self.assertEqual(values[0], values[1])
        self.assertEqual(rows[0]["prediction"]["metadata"]["usage"]["total_tokens"], 0)
        self.assertTrue(rows[0]["prediction"]["metadata"]["a_evidence_trace"])
        with tempfile.TemporaryDirectory() as folder:
            artifacts = model.save_artifacts(Path(folder) / "B10")
            self.assertEqual(len(artifacts), 1)
        other = copy.deepcopy(pairs[:1])
        other[0][1]["dataset_layer"] = "P1"
        with self.assertRaises(ValueError):
            model.fit(other)

    def test_A_reference_runs_through_actual_engine_and_excludes_test_labels_from_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            dump_jsonl(path / "inputs.jsonl", self.records)
            dump_jsonl(path / "labels.jsonl", self.golds)
            summary, status = run_experiment(path / "inputs.jsonl", path / "labels.jsonl", path / "out",
                {"a_model": {"enabled": True}}, ["B10_REFERENCE"], [0], suite="core")
            run = summary["runs"][0]
            self.assertEqual(run["spec"]["training"]["train_n"], 144)
            self.assertEqual(run["counts"]["n_success"], 48)
            self.assertEqual(run["cost"]["tokens"]["total_tokens"], 0)
            self.assertEqual(run["calibration"]["n"], 0)
            self.assertTrue(run["artifacts"])


if __name__ == "__main__":
    unittest.main()
