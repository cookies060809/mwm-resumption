import copy
import json
import sys
import unittest

from integration.a_output_adapter import normalize_a_output
from mwm_eval.external import CommandBaseline
from tools.build_integration_fixtures import make_fixtures


class AOutputAdapterTests(unittest.TestCase):
    def setUp(self):
        self.obs = make_fixtures()[0][0]["observation"]
        self.step = self.obs["task_steps"][0]
        self.output = {"t1_resume_probability": 0.75,
                       "t2_conditional_step_distribution": {self.step: 1.0},
                       "t3_state_distributions": {"B": {"UNKNOWN": 1.0}},
                       "evidence_trace": [], "cost": {"tokens": None}}

    def test_probability_and_conditional_step_are_translated_without_fabricating_states(self):
        prediction = normalize_a_output(self.output, self.obs)
        self.assertEqual(prediction["p_resume"], 0.75)
        self.assertEqual(prediction["resume_step"], self.step)
        self.assertEqual(set(prediction["state_probs"]), {"B"})
        self.assertIsNone(prediction["metadata"]["a_cost"]["tokens"])

    def test_zero_probability_requires_undefined_conditional_distribution(self):
        self.output["t1_resume_probability"] = 0
        with self.assertRaises(ValueError):
            normalize_a_output(self.output, self.obs)
        self.output["t2_conditional_step_distribution"] = None
        prediction = normalize_a_output(self.output, self.obs)
        self.assertEqual(prediction["resume_label"], "not_resume")
        self.assertIsNone(prediction["conditional_step_probs"])

    def test_invalid_distributions_future_evidence_and_unimplemented_output_rejected(self):
        for changed in ({"t1_resume_probability": float("nan")},
                        {"t2_conditional_step_distribution": []},
                        {"t2_conditional_step_distribution": {"not_a_step": 1}},
                        {"evidence_trace": ["future_event"]},
                        {"t3_state_distributions": {"B": {"UNKNOWN": 0.2}}}):
            payload = copy.deepcopy(self.output)
            payload.update(changed)
            with self.assertRaises(ValueError):
                normalize_a_output(payload, self.obs)
        with self.assertRaises(ValueError):
            normalize_a_output({"states": [], "weights": []}, self.obs)

    def test_actual_command_transport_can_use_explicit_A_format(self):
        # A protocol fixture only; no trained EC-JMF/model performance claim.
        command = CommandBaseline("B10", {"enabled": True, "output_format": "a-t123-draft-1",
                    "argv": [sys.executable, "-c", "print(" + repr(json.dumps(self.output)) + ")"],
                    "provenance": {"scope": "unit-test protocol fixture"}})
        prediction = command.predict(self.obs)
        self.assertEqual(prediction["resume_step"], self.step)
        self.assertTrue(prediction["metadata"]["external"]["real_child_process_execution"])


if __name__ == "__main__":
    unittest.main()
