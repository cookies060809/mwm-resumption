"""Engine boundary tests using small local fakes, never claimed external runs."""

import copy
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mwm_eval import engine
from mwm_eval.calibration import apply_temperature, fit_temperature
from mwm_eval.schema import canonical_hash, load_jsonl
from tools.build_integration_fixtures import make_fixtures


def prediction(obs, probability=0.6, evidence=None, usage=None):
    return {"resume_label": "resume", "resume_step": obs["task_steps"][0],
            "p_resume": probability, "conditional_step_probs": None, "state_probs": {},
            "evidence_event_ids": evidence if evidence is not None else [obs["events"][-1]["event_id"]],
            "reason": "Test double for orchestration only.",
            "metadata": {"usage": usage} if usage is not None else {}}


class FakeMethod:
    def __init__(self, method_id="B6", predict=None, available=True, fit_error=False):
        self.method_id = method_id
        self.prediction_function = predict or prediction
        self.is_available = available
        self.fit_error = fit_error
        self.fitted_pairs = None
        self.seen_observations = []

    def availability(self):
        return {"available": self.is_available, "reason": "test fake available" if self.is_available
                else "test fake intentionally unavailable"}

    def fit(self, pairs):
        self.fitted_pairs = copy.deepcopy(pairs)
        if self.fit_error:
            raise ValueError("deliberate test fit failure")
        return self

    def predict(self, obs):
        self.seen_observations.append(copy.deepcopy(obs))
        return self.prediction_function(obs)

    def spec(self):
        return {"method_id": self.method_id, "implementation": "test_fake_not_real_external_method"}


class EngineBoundaryTests(unittest.TestCase):
    def _run(self, method, directory, records=None, golds=None):
        if records is None:
            records, golds = make_fixtures()
        directory = Path(directory)
        input_path, label_path = directory / "inputs.jsonl", directory / "labels.jsonl"
        engine.dump_jsonl(input_path, records)
        engine.dump_jsonl(label_path, golds)
        with patch.object(engine, "make_local_baselines", return_value={method.method_id: method}), \
                patch.object(engine, "make_external_baselines", return_value={}):
            return engine.run_experiment(input_path, label_path, directory / "results", {},
                                         [method.method_id], [0], suite="core")

    def test_temperature_scaling_handles_exact_zero_one_and_keeps_raw_inputs(self):
        _records, golds = make_fixtures()
        selected = [gold for gold in golds if gold["sample_id"] in {
            "calibration_P01_A", "calibration_P01_B"}]
        rows = [{"sample_id": gold["sample_id"], "split": "calibration", "status": "ok",
                 "prediction": {"p_resume": float(gold["resume_label"] == "resume"), "metadata": {}}}
                for gold in selected]
        original = copy.deepcopy(rows)
        calibration = fit_temperature(rows, selected)
        self.assertTrue(calibration["applicable"])
        self.assertTrue(math.isfinite(calibration["nll_before"]))
        self.assertTrue(math.isfinite(calibration["nll_after"]))
        calibrated = apply_temperature(rows, calibration)
        for row in calibrated:
            probability = row["prediction"]["p_resume"]
            self.assertTrue(math.isfinite(probability))
            self.assertTrue(0 <= probability <= 1)
            self.assertEqual(row["prediction"]["metadata"]["calibration"]["split"], "calibration")
        self.assertEqual(rows, original)

    def test_graph_gated_zero_is_preserved_exactly_after_temperature_scaling(self):
        rows = [{"sample_id": "gated", "status": "ok", "prediction": {
            "p_resume": 0.0, "resume_label": "not_resume",
            "metadata": {"graph_gate_applied": True},
        }}, {"sample_id": "ungated", "status": "ok", "prediction": {
            "p_resume": 0.0, "resume_label": "not_resume", "metadata": {},
        }}]
        original = copy.deepcopy(rows)
        result = apply_temperature(rows, {"applicable": True, "temperature": 3.0, "n": 2})
        self.assertEqual(result[0]["prediction"]["p_resume"], 0.0)
        self.assertTrue(result[0]["prediction"]["metadata"]["calibration"]["structural_zero_preserved"])
        self.assertGreater(result[1]["prediction"]["p_resume"], 0.0)
        self.assertEqual(rows, original)

    def test_graph_gated_zero_cannot_influence_fitted_temperature_or_nll(self):
        golds = [{"sample_id": sid, "dataset_layer": "P1", "resume_label": label,
                  "window_complete": True} for sid, label in (
                      ("p", "resume"), ("n", "not_resume"), ("gated", "resume"))]
        # Even a contradictory positive outcome at a hard zero cannot persuade
        # temperature fitting to relax that graph constraint.
        rows = [{"sample_id": "p", "status": "ok", "prediction": {"p_resume": 0.8, "metadata": {}}},
                {"sample_id": "n", "status": "ok", "prediction": {"p_resume": 0.2, "metadata": {}}},
                {"sample_id": "gated", "status": "ok", "prediction": {
                    "p_resume": 0.0, "metadata": {"graph_gate_applied": True}}}]
        reference = fit_temperature(rows[:2], golds[:2])
        fitted = fit_temperature(rows, golds)
        self.assertTrue(fitted["applicable"])
        self.assertEqual(fitted["temperature"], reference["temperature"])
        self.assertEqual(fitted["nll_before"], reference["nll_before"])
        self.assertEqual(fitted["nll_after"], reference["nll_after"])
        self.assertEqual(fitted["n"], 2)
        self.assertEqual(fitted["n_eligible_probability"], 3)
        self.assertEqual(fitted["n_excluded_structural_zero"], 1)

    def test_only_graph_gated_zeros_cannot_supply_a_calibration_fit(self):
        rows = [{"sample_id": "gated", "status": "ok", "prediction": {
            "p_resume": 0.0, "metadata": {"graph_gate_applied": True}}}]
        golds = [{"sample_id": "gated", "dataset_layer": "P1",
                  "resume_label": "not_resume", "window_complete": True}]
        fitted = fit_temperature(rows, golds)
        self.assertFalse(fitted["applicable"])
        self.assertEqual(fitted["n"], 0)
        self.assertEqual(fitted["n_eligible_probability"], 1)
        self.assertEqual(fitted["n_excluded_structural_zero"], 1)
        self.assertEqual(apply_temperature(rows, fitted), rows)

    def test_experiment_fits_only_train_and_selects_temperature_only_on_calibration(self):
        method = FakeMethod()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(engine, "fit_temperature", wraps=fit_temperature) as select:
                _summary, _status = self._run(method, directory)
            self.assertEqual(select.call_count, 1)
            rows, golds = select.call_args.args
            self.assertTrue(rows)
            self.assertTrue(all(row["split"] == "calibration" for row in rows))
            self.assertTrue(all(gold["sample_id"].startswith("calibration_") for gold in golds))
            self.assertTrue(method.fitted_pairs)
            self.assertTrue(all(gold["sample_id"].startswith("train_")
                                for _obs, gold in method.fitted_pairs))
            test_rows = load_jsonl(Path(directory) / "results" / "predictions.jsonl")
            self.assertTrue(all(row["split"] == "test" for row in test_rows))
            calibration_ids = {gold["sample_id"] for gold in golds}
            self.assertFalse(calibration_ids & {row["sample_id"] for row in test_rows})

    def test_b1_actual_input_hash_excludes_discarded_prefix(self):
        records, _golds = make_fixtures()
        records = [record for record in records if record["sample_id"] in {"test_P02_A", "test_P02_B"}]
        method = FakeMethod("B1")
        rows = engine.predict_rows(method, records, 0)
        self.assertEqual([row["status"] for row in rows], ["ok", "ok"])
        self.assertEqual(rows[0]["input_hash"], rows[1]["input_hash"])
        self.assertNotEqual(rows[0]["source_input_hash"], rows[1]["source_input_hash"])
        for record, row, actual in zip(records, rows, method.seen_observations):
            self.assertEqual(len(actual["events"]), 5)
            self.assertEqual(row["input_event_count"], 5)
            self.assertEqual(row["input_hash"], canonical_hash(actual))
            self.assertEqual(actual["events"], record["observation"]["events"][-5:])

    def test_b1_cannot_cite_an_event_removed_from_its_actual_input(self):
        records, _golds = make_fixtures()
        record = next(record for record in records if record["sample_id"] == "test_P02_A")
        method = FakeMethod("B1", predict=lambda obs: prediction(obs, evidence=["e01"]))
        row = engine.predict_rows(method, [record], 0)[0]
        self.assertNotIn("e01", row["actual_input_event_ids"])
        self.assertEqual(row["status"], "error")
        self.assertIsNone(row["prediction"])
        self.assertIn("outside actual input", row["error"])

    def test_invalid_prediction_keeps_known_usage_for_cost_accounting(self):
        record = make_fixtures()[0][0]
        usage = {"prompt_tokens": 17, "completion_tokens": 5, "total_tokens": 22}
        method = FakeMethod(predict=lambda obs: prediction(obs, probability=1.2, usage=usage))
        row = engine.predict_rows(method, [record], 0)[0]
        self.assertEqual(row["status"], "error")
        self.assertIsNone(row["prediction"])
        self.assertEqual(row["usage"], usage)
        self.assertEqual(engine._cost([row])["tokens"]["total_tokens"], 22)

    def test_all_unavailable_is_not_reported_as_completed_or_zero_accuracy(self):
        method = FakeMethod("B8", available=False)
        with tempfile.TemporaryDirectory() as directory:
            summary, status = self._run(method, directory)
            self.assertEqual(status["overall"], "no_methods_executed")
            self.assertEqual(status["methods"]["B8"]["status"], "unavailable")
            self.assertEqual(summary["runs"][0]["status"], "unavailable")
            for metric in summary["aggregate"]["B8"]["metrics"].values():
                self.assertIsNone(metric["mean"])
                self.assertIsNone(metric["sample_sd"])
                self.assertEqual(metric["n_defined"], 0)
            rows = load_jsonl(Path(directory) / "results" / "predictions.jsonl")
            self.assertTrue(all(row["status"] == "unavailable" for row in rows))
            self.assertIsNone(method.fitted_pairs)
            self.assertEqual(method.seen_observations, [])

    def test_fit_failure_is_error_and_overall_completed_with_errors(self):
        method = FakeMethod(fit_error=True)
        with tempfile.TemporaryDirectory() as directory:
            summary, status = self._run(method, directory)
            self.assertEqual(status["overall"], "completed_with_errors")
            self.assertEqual(status["methods"]["B6"]["status"], "error")
            self.assertEqual(summary["runs"][0]["status"], "error")
            rows = load_jsonl(Path(directory) / "results" / "predictions.jsonl")
            self.assertTrue(all(row["status"] == "error" for row in rows))
            self.assertTrue(all("fit failed" in row["error"] for row in rows))
            self.assertEqual(method.seen_observations, [])

    def test_calibration_execution_errors_are_reported_even_when_test_succeeds(self):
        calibration_hashes = {canonical_hash(record["observation"]) for record in make_fixtures()[0]
                              if record["split"] == "calibration"}
        def predict_with_calibration_error(obs):
            if canonical_hash(obs) in calibration_hashes:
                raise ValueError("deliberate calibration failure")
            return prediction(obs)
        with tempfile.TemporaryDirectory() as directory:
            summary, status = self._run(FakeMethod(predict=predict_with_calibration_error), directory)
            self.assertEqual(status["overall"], "completed_with_errors")
            self.assertEqual(summary["runs"][0]["status"], "error")
            self.assertEqual(summary["runs"][0]["calibration"]["prediction_counts"]["n_error"], 18)
            self.assertEqual(summary["runs"][0]["counts"]["n_error"], 0)

    def test_pipeline_rejects_mixed_prediction_horizons(self):
        records, golds = make_fixtures()
        records[-1]["observation"]["horizon"]["value"] = 4
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "fixed horizon"):
                self._run(FakeMethod(), directory, records, golds)

    def test_pipeline_rejects_training_calibration_person_overlap(self):
        records, golds = make_fixtures()
        train_person = next(record["person_id"] for record in records if record["split"] == "train")
        for record in records:
            if record["base_story_id"] == "calibration_P01":
                old_person = record["person_id"]
                record["person_id"] = train_person
                record["observation"]["target_person"] = train_person
                for event in record["observation"]["events"]:
                    if event["actor"] == old_person:
                        event["actor"] = train_person
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "disjoint people"):
                self._run(FakeMethod(), directory, records, golds)


if __name__ == "__main__":
    unittest.main()
