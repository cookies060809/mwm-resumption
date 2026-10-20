"""Counterexample-focused tests for distinct local baseline implementations."""

import json
import math
import unittest
from copy import deepcopy

from mwm_eval.local_baselines import make_local_baselines
from mwm_eval.schema import validate_observation, validate_prediction


def event(kind, time=1, *, goal="order", actor="person", step=None,
          accessed=True, understood=True, **semantic):
    result = {
        "event_id": "e" + str(time), "time": time, "actor": actor,
        "event_type": "task_action" if kind in {"task_action", "step_completed"} else kind,
        "goal_id": goal, "step_id": step,
        "world_effect": None, "observer_evidence": "controlled observed event",
        "person_access_evidence": {
            "status": "ACCESSED" if accessed else "NOT_ACCESSED", "understood": understood},
        "source": "controlled_test", "certainty": 1.0,
        "semantic": {"kind": kind, **semantic}}
    if kind in {"task_action", "step_completed"}:
        result["action_status"] = "completed" if kind == "step_completed" else "in_progress"
    return result


def observation(events=None, *, nodes=None, edges=None):
    nodes = nodes or ["check", "pack", "send"]
    return {"target_person": "person", "goal_id": "order", "task_steps": nodes,
            "task_graph": {"nodes": nodes, "edges": edges if edges is not None else
                           [[nodes[i], nodes[i + 1]] for i in range(len(nodes) - 1)]},
            "cutoff": 20, "horizon": {"type": "decision_opportunities", "value": 3},
            "events": events if events is not None else [event("task_action", step="check")]}


def train_examples():
    examples = []
    for i in range(12):
        events = [event("goal_started", time=1), event("task_action", time=2, step="check"),
                  event("interruption_started", time=3, demand_level=0.5),
                  event("interruption_ended", time=9)]
        examples.append((observation(events + [event("cue", time=10)]),
                         {"resume_label": "resume", "state_labels": {"C": "SUSPENDED"},
                          "state_evidence": {"C": ["e3"]}}))
        examples.append((observation(events + [event("goal_abandoned", time=10)]),
                         {"resume_label": "not_resume", "state_labels": {"C": "ABANDONED"},
                          "state_evidence": {"C": ["e10"]}}))
    return examples


class LocalBaselineTests(unittest.TestCase):
    def test_all_methods_interoperate_with_common_schema(self):
        pairs = train_examples()
        for obs, _ in pairs:
            validate_observation(obs)
        for method in make_local_baselines().values():
            method.fit(pairs)
            for obs in (pairs[0][0], pairs[1][0], observation([])):
                validate_observation(obs)
                validate_prediction(method.predict(obs), obs)

    def test_six_ids_and_explicit_reproduction_limits(self):
        methods = make_local_baselines()
        self.assertEqual(set(methods), {"B0", "B1", "B4", "B5", "B6", "B7"})
        for method in methods.values():
            self.assertEqual(method.spec()["method_id"], method.method_id)
            self.assertFalse(method.spec()["strict_reproduction"])
            json.dumps(method.spec())
        self.assertIn("SET-PR", methods["B1"].spec()["limitations"])
        self.assertIn("SIPS", methods["B7"].spec()["limitations"])

    def test_b1_really_drops_events_outside_five_without_cache(self):
        methods = make_local_baselines()
        obs = observation([event("task_action", time=1, step="check")]
                          + [event("noise", time=i, actor="clock", goal=None) for i in range(2, 8)])
        self.assertEqual(methods["B0"].predict(obs)["resume_label"], "resume")
        self.assertEqual(methods["B1"].predict(obs)["resume_label"], "not_resume")
        self.assertEqual(methods["B1"].predict(obs)["evidence_event_ids"], [])

    def test_recent_other_goal_is_not_silently_treated_as_target(self):
        obs = observation([event("task_action", time=1, step="check"),
                           event("task_action", time=2, goal="phone", step="talk")])
        result = make_local_baselines()["B0"].predict(obs)
        self.assertEqual(result["resume_label"], "not_resume")
        self.assertEqual(result["evidence_event_ids"], ["e2"])

    def test_recency_obeys_graph_branch_dependencies(self):
        # Checking the left branch does not complete the independent right branch.
        obs = observation([event("step_completed", step="left")],
                          nodes=["root", "left", "right", "merge"],
                          edges=[["root", "left"], ["root", "right"],
                                 ["left", "merge"], ["right", "merge"]])
        self.assertEqual(make_local_baselines()["B0"].predict(obs)["resume_step"], "right")

    def test_b4_copies_hidden_world_while_b5_keeps_person_belief_separate(self):
        obs = observation([event("goal_started", time=1), event("task_action", time=2, step="check"),
                           event("goal_suspended", time=3),
                           event("cancellation", time=4, actor="backend", accessed=False,
                                 understood=False)])
        methods = make_local_baselines()
        self.assertEqual(methods["B4"].predict(obs)["resume_label"], "not_resume")
        prediction = methods["B5"].predict(obs)
        self.assertEqual(prediction["resume_label"], "resume")
        self.assertEqual(prediction["state_probs"]["V"], {"CANCELLED": 1.0})
        self.assertEqual(prediction["state_probs"]["B"], {"BELIEVES_VALID": 1.0})

    def test_access_without_understanding_does_not_imply_invalid_belief(self):
        obs = observation([event("goal_started", time=1),
                           event("cancellation", time=2, actor="backend", understood=False)])
        result = make_local_baselines()["B5"].predict(obs)
        self.assertEqual(result["state_probs"]["A"], {"ACCESSED": 1.0})
        self.assertEqual(result["state_probs"]["B"], {"BELIEVES_VALID": 1.0})
        self.assertEqual(result["resume_label"], "resume")

    def test_explicit_notification_content_changes_rule_belief(self):
        events = [event("goal_started", time=1), event("cancellation", time=2, actor="backend",
                  accessed=False, understood=False),
                  event("notification_understood", time=3, actor="app", value="cancellation",
                        reference_event_id="e2")]
        result = make_local_baselines()["B5"].predict(observation(events))
        self.assertEqual(result["resume_label"], "not_resume")
        self.assertEqual(result["state_probs"]["B"], {"BELIEVES_INVALID": 1.0})

    def test_teammate_completion_only_moves_b5_progress_when_known(self):
        events = [event("goal_started", time=1), event("task_action", time=2, step="check"),
                  event("step_completed", time=3, actor="colleague", step="check",
                        accessed=False, understood=False)]
        methods = make_local_baselines()
        self.assertEqual(methods["B4"].predict(observation(events))["resume_step"], "pack")
        self.assertEqual(methods["B5"].predict(observation(events))["resume_step"], "check")
        events[-1]["person_access_evidence"] = {"status": "ACCESSED", "understood": True}
        self.assertEqual(methods["B5"].predict(observation(events))["resume_step"], "pack")

    def test_blocked_resource_preserves_suspended_commitment(self):
        obs = observation([event("goal_started", time=1), event("goal_suspended", time=2),
                           event("resource_blocked", time=3, actor="sensor")])
        result = make_local_baselines()["B5"].predict(obs)
        self.assertEqual(result["resume_label"], "not_resume")
        self.assertEqual(result["state_probs"]["C"], {"SUSPENDED": 1.0})

    def test_nested_inserted_goal_must_finish_under_bdi_rule(self):
        events = [event("goal_started", time=1), event("goal_suspended", time=2),
                  event("goal_started", time=3, goal="urgent"),
                  event("interruption_started", time=4, interrupting_goal_id="phone"),
                  event("interruption_ended", time=5, interrupting_goal_id="phone")]
        method = make_local_baselines()["B5"]
        self.assertEqual(method.predict(observation(events))["resume_label"], "not_resume")
        events.append(event("goal_completed", time=6, goal="urgent"))
        self.assertEqual(method.predict(observation(events))["resume_label"], "resume")

    def test_trainable_methods_require_training_and_reject_empty_labels(self):
        methods = make_local_baselines()
        for name in ("B6", "B7"):
            with self.assertRaisesRegex(RuntimeError, "not_fitted"):
                methods[name].predict(observation())
            with self.assertRaisesRegex(ValueError, "no_train_labels"):
                methods[name].fit([(observation(), {"resume_label": "censored"})])

    def test_b6_fits_cue_feature_and_ignores_censored_outcomes(self):
        pairs = train_examples()
        pairs.append((observation(), {"resume_label": "censored"}))
        model = make_local_baselines(seed=9)["B6"].fit(pairs)
        positive, negative = pairs[0][0], pairs[1][0]
        self.assertGreater(model.predict(positive)["p_resume"], model.predict(negative)["p_resume"])
        self.assertEqual(model.training_samples, 24)
        self.assertEqual(model.spec()["fit_state"], "fitted")
        self.assertEqual(len(model.spec()["coefficients"]), 8)

    def test_hmm_has_fitted_normalized_transition_and_forward_posterior(self):
        model = make_local_baselines(seed=4)["B7"].fit(train_examples())
        for row in [model.initial] + model.transition + model.emission:
            self.assertAlmostEqual(sum(row), 1.0)
            self.assertTrue(all(value > 0 for value in row))
        positive, negative = train_examples()[0][0], train_examples()[1][0]
        pos, neg = model.predict(positive), model.predict(negative)
        self.assertAlmostEqual(sum(pos["metadata"]["latent_posterior"]), 1.0)
        self.assertEqual(pos["state_probs"], {})  # Only two semantic states have anchors.
        self.assertGreater(pos["metadata"]["latent_posterior"][1],
                           neg["metadata"]["latent_posterior"][1])
        self.assertGreater(pos["p_resume"], neg["p_resume"])
        self.assertEqual(model.spec()["fit_state"], "fitted")

    def test_incomplete_p1_negative_is_excluded_from_binary_training_but_can_anchor_state(self):
        pairs = train_examples()
        extra_obs = observation([event("goal_started", time=1),
                                 event("goal_completed", time=2)])
        extra_gold = {"dataset_layer": "P1", "window_complete": False,
                      "resume_label": "not_resume", "state_labels": {"C": "COMPLETED"},
                      "state_evidence": {"C": ["e2"]}}
        b6 = make_local_baselines()["B6"].fit(pairs + [(extra_obs, extra_gold)])
        self.assertEqual(b6.training_samples, len(pairs))
        self.assertEqual(b6.weights, make_local_baselines()["B6"].fit(pairs).weights)
        b7 = make_local_baselines()["B7"].fit(pairs + [(extra_obs, extra_gold)])
        self.assertEqual(b7.resume_training_samples, len(pairs))
        self.assertEqual(b7.training_samples, len(pairs) + 1)
        self.assertEqual(b7.anchor_counts["COMPLETED"], 1)

    def test_hmm_ignores_terminal_labels_without_evidence_and_suppresses_semantic_probs(self):
        pairs = train_examples()
        for _obs, gold in pairs:
            gold.pop("state_evidence")
        b7 = make_local_baselines()["B7"].fit(pairs)
        self.assertEqual(sum(b7.anchor_counts.values()), 0)
        result = b7.predict(pairs[0][0])
        self.assertEqual(result["state_probs"], {})
        self.assertEqual(len(result["metadata"]["latent_posterior"]), 4)
        self.assertFalse(b7.spec()["semantic_state_probs_available"])

    def test_hmm_emits_semantic_c_only_when_all_four_states_have_evidence_anchors(self):
        pairs = train_examples()
        pairs.extend([
            (observation([event("goal_started", time=1), event("task_action", time=2, step="check")]),
             {"resume_label": "resume", "state_labels": {"C": "ACTIVE"},
              "state_evidence": {"C": ["e2"]}}),
            (observation([event("goal_started", time=1), event("goal_completed", time=2)]),
             {"resume_label": "not_resume", "state_labels": {"C": "COMPLETED"},
              "state_evidence": {"C": ["e2"]}})])
        b7 = make_local_baselines()["B7"].fit(pairs)
        self.assertTrue(b7.spec()["semantic_state_probs_available"])
        result = b7.predict(pairs[0][0])
        self.assertEqual(set(result["state_probs"]["C"]), set(b7.states))
        self.assertAlmostEqual(sum(result["state_probs"]["C"].values()), 1.0)

    def test_hmm_handles_unseen_observation_symbol_and_no_events(self):
        model = make_local_baselines()["B7"].fit(train_examples())
        for obs in (observation([event("never_seen_before")]), observation([])):
            prediction = model.predict(obs)
            self.assertTrue(math.isfinite(prediction["p_resume"]))
            self.assertTrue(0 <= prediction["p_resume"] <= 1)

    def test_fit_and_predict_do_not_mutate_inputs_and_are_seed_reproducible(self):
        pairs = train_examples()
        original = deepcopy(pairs)
        left, right = make_local_baselines(seed=17), make_local_baselines(seed=17)
        for name in left:
            left[name].fit(pairs)
            right[name].fit(pairs)
            result = left[name].predict(pairs[0][0])
            self.assertEqual(result, right[name].predict(pairs[0][0]))
            json.dumps(result)
        self.assertEqual(pairs, original)

    def test_every_predict_rejects_future_events(self):
        methods = make_local_baselines()
        obs = observation([event("task_action", time=21, step="check")])
        for method in methods.values():
            method.fit(train_examples())
            with self.assertRaisesRegex(ValueError, "future_event"):
                method.predict(obs)

    def test_trainable_probabilities_respect_exhausted_graph(self):
        obs = observation([event("step_completed", time=i + 1, step=step)
                           for i, step in enumerate(["check", "pack", "send"])])
        for name in ("B6", "B7"):
            model = make_local_baselines()[name].fit(train_examples())
            prediction = model.predict(obs)
            self.assertEqual(prediction["p_resume"], 0.0)
            self.assertEqual(prediction["resume_label"], "not_resume")
            self.assertTrue(prediction["metadata"]["graph_gate_applied"])


if __name__ == "__main__":
    unittest.main()
