"""Independent boundary cases for the draft event/data/output protocol.

These cases verify structural leakage checks; no schema can detect an answer
hidden inside otherwise permitted natural-language evidence.
"""

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from mwm_eval.schema import (
    audit_groups, canonical_hash, file_hash, load_jsonl, validate_dataset,
    validate_graph, validate_observation, validate_prediction,
)


def observed_event(eid="e1", time=1):
    return {
        "event_id": eid, "time": time, "actor": "worker",
        "event_type": "task_action", "goal_id": "delivery", "step_id": "pack",
        "action_status": "completed", "world_effect": None,
        "observer_evidence": "The worker finished packing before the cutoff.",
        "person_access_evidence": {"status": "ACCESSED", "understood": True},
        "source": "independent_protocol_test", "certainty": 1,
    }


def observation():
    return {
        "target_person": "worker", "goal_id": "delivery", "task_steps": ["pack", "ship"],
        "task_graph": {"nodes": ["pack", "ship"], "edges": [["pack", "ship"]]},
        "cutoff": 3, "horizon": {"type": "decision_opportunities", "value": 3},
        "events": [observed_event()],
    }


def record(sid="a", split="test", story=None, person=None, purpose="synthetic_integration_fixture"):
    return {
        "sample_id": sid, "base_story_id": story or "story-" + sid,
        "person_id": person or "person-" + sid, "task_family": "delivery",
        "domain": "warehouse", "split": split, "purpose": purpose,
        "observation": observation(),
    }


def gold(sid="a", layer="integration_fixture"):
    return {
        "sample_id": sid, "dataset_layer": layer, "resume_label": "resume",
        "resume_step": "ship", "state_labels": {"Q": "ship"},
        "state_evidence": {"Q": ["e1"]}, "window_complete": True,
    }


def prediction():
    return {
        "resume_label": "resume", "resume_step": "ship", "p_resume": 0.7,
        "conditional_step_probs": {"pack": 0.1, "ship": 0.9},
        "state_probs": {"C": {"SUSPENDED": 1}}, "evidence_event_ids": ["e1"],
        "reason": "A point prediction using only the observed packing event.", "metadata": {},
    }


class SchemaBoundaryTests(unittest.TestCase):
    def test_canonical_hash_is_order_invariant_sensitive_and_rejects_nan(self):
        self.assertEqual(canonical_hash({"a": 1, "b": [2]}), canonical_hash({"b": [2], "a": 1}))
        self.assertNotEqual(canonical_hash({"a": 1}), canonical_hash({"a": 2}))
        with self.assertRaises(ValueError):
            canonical_hash({"value": float("nan")})
        with tempfile.TemporaryDirectory(prefix="mwm-schema-") as folder:
            path = Path(folder) / "source.txt"
            path.write_bytes(b"protocol-source\n")
            self.assertEqual(file_hash(path), hashlib.sha256(b"protocol-source\n").hexdigest())

    def test_jsonl_handles_bom_blanks_and_reports_physical_line_number(self):
        with tempfile.TemporaryDirectory(prefix="mwm-schema-") as folder:
            path = Path(folder) / "rows.jsonl"
            path.write_text('\ufeff\n{"id":"a"}\n\n{"id":"b"}\n', encoding="utf-8")
            self.assertEqual(load_jsonl(path), [{"id": "a"}, {"id": "b"}])
            path.write_text('\n{"id":"a"}\n{broken}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r":3: invalid JSON"):
                load_jsonl(path)

    def test_jsonl_rejects_duplicate_keys_even_in_nested_objects(self):
        with tempfile.TemporaryDirectory(prefix="mwm-schema-") as folder:
            path = Path(folder) / "duplicate.jsonl"
            for raw in ('{"sample_id":"a","sample_id":"b"}',
                        '{"event":{"time":1,"time":99}}'):
                with self.subTest(raw=raw):
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                        load_jsonl(path)

    def test_jsonl_rejects_nonfinite_constants_and_float_overflow(self):
        with tempfile.TemporaryDirectory(prefix="mwm-schema-") as folder:
            path = Path(folder) / "invalid-number.jsonl"
            for token in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
                with self.subTest(token=token):
                    path.write_text('{"certainty":' + token + '}', encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_jsonl(path)

    def test_observation_rejects_labels_ids_and_extra_event_annotation_fields(self):
        for key in ("sample_id", "gold", "resume_label", "state_labels"):
            obs = observation()
            obs[key] = "future answer"
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_observation(obs)
        obs = observation()
        obs["events"][0]["gold"] = {"resume_label": "resume"}
        with self.assertRaises(ValueError):
            validate_observation(obs)

    def test_nested_answers_cannot_hide_in_semantic_text_or_world_effect(self):
        for key in ("reason", "value", "belief"):
            obs = observation()
            obs["events"][0]["semantic"] = {key: {"gold": {"resume_label": "resume"}}}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_observation(obs)
        obs = observation()
        obs["events"][0]["world_effect"] = {"gold": {"resume_label": "resume"}}
        with self.assertRaises(ValueError):
            validate_observation(obs)

    def test_objective_effect_is_typed_without_forcing_person_knowledge(self):
        obs = observation()
        obs["events"][0]["world_effect"] = {"V": "CANCELLED", "F": "BLOCKED", "completed_steps": ["pack"]}
        obs["events"][0]["person_access_evidence"] = {"status": "NOT_ACCESSED", "understood": False}
        # An observer may know cancellation while the person did not access it.
        validate_observation(obs)
        for effect in ({"V": "BELIEVES_INVALID"}, {"F": "ACTIVE"}, {"completed_steps": ["future_step"]}):
            obs["events"][0]["world_effect"] = effect
            with self.subTest(effect=effect), self.assertRaises(ValueError):
                validate_observation(obs)

    def test_semantic_numeric_flags_and_step_lists_require_correct_types(self):
        for semantic in ({"demand_level": float("inf")}, {"demand_level": True},
                         {"task_completed": "yes"}, {"completed_steps": {"pack": True}},
                         {"completed_steps": ["pack", {"gold": "ship"}]}):
            obs = observation()
            obs["events"][0]["semantic"] = semantic
            with self.subTest(semantic=semantic), self.assertRaises(ValueError):
                validate_observation(obs)
        obs = observation()
        obs["events"][0]["semantic"] = {"kind": "step_completed", "completed_steps": ["pack"],
                                          "demand_level": 0.4, "task_completed": False}
        validate_observation(obs)

    def test_semantic_reference_must_point_to_an_earlier_event(self):
        for reference in ("e1", "e2", "absent"):
            obs = observation()
            obs["events"][0]["semantic"] = {"reference_event_id": reference}
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                validate_observation(obs)
        obs = observation()
        second = observed_event("e2", 2)
        second["semantic"] = {"reference_event_id": "e1"}
        obs["events"].append(second)
        validate_observation(obs)

    def test_graph_accepts_branching_dag_and_rejects_cycles_and_invalid_edges(self):
        steps = ["prepare", "left", "right", "join"]
        graph = {"nodes": steps, "edges": [["prepare", "left"], ["prepare", "right"],
                                             ["left", "join"], ["right", "join"]]}
        validate_graph(graph, steps)
        for edges in ([["prepare", "left"], ["left", "prepare"]],
                      [["prepare", "prepare"]], [["prepare", "left"], ["prepare", "left"]],
                      [["prepare", "absent"]]):
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                validate_graph({"nodes": steps, "edges": edges}, steps)
        with self.assertRaises(ValueError):
            validate_graph({"nodes": ["prepare", "left", "right"], "edges": []}, steps)

    def test_event_chronology_duplicates_and_nonfinite_time_are_rejected(self):
        for timestamp in (4, float("nan"), float("inf"), True):
            obs = observation()
            obs["events"][0]["time"] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                validate_observation(obs)
        obs = observation()
        obs["events"].append(observed_event("e1", 2))
        with self.assertRaises(ValueError):
            validate_observation(obs)
        obs["events"] = [observed_event("e2", 2), observed_event("e1", 1)]
        with self.assertRaises(ValueError):
            validate_observation(obs)

    def test_horizon_and_task_action_have_structural_requirements(self):
        for horizon in ({"type": "decision_opportunities", "value": 1.5},
                        {"type": "decision_opportunities", "value": True},
                        {"type": "seconds", "value": 0}, {"type": "unknown", "value": 3}):
            obs = observation()
            obs["horizon"] = horizon
            with self.subTest(horizon=horizon), self.assertRaises(ValueError):
                validate_observation(obs)
        obs = observation()
        obs["horizon"] = {"type": "seconds", "value": 0.25}
        validate_observation(obs)
        for key, value in (("step_id", "absent"), ("action_status", None)):
            obs = observation()
            obs["events"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_observation(obs)

    def test_known_gold_requires_evidence_while_unknown_is_a_valid_mask(self):
        g = gold()
        validate_dataset([record()], [g])
        g["state_evidence"] = {}
        with self.assertRaises(ValueError):
            validate_dataset([record()], [g])
        g["state_labels"] = {"B": "UNKNOWN", "Q": None}
        validate_dataset([record()], [g])
        g["state_labels"] = {"B": "BELIEVES_INVALID"}
        g["state_evidence"] = {"B": ["after_cutoff"]}
        with self.assertRaises(ValueError):
            validate_dataset([record()], [g])

    def test_all_state_evidence_fields_are_checked_even_without_matching_label(self):
        g = gold()
        g["state_labels"] = {}
        g["state_evidence"] = {"C": ["after_cutoff"]}
        with self.assertRaises(ValueError):
            validate_dataset([record()], [g])
        g["state_evidence"] = {"C": "e1"}
        with self.assertRaises(ValueError):
            validate_dataset([record()], [g])

    def test_gold_rejects_unknown_factors_duplicate_ids_and_unmatched_rows(self):
        for field in ("state_labels", "state_evidence"):
            g = gold()
            g[field]["typo"] = None if field == "state_labels" else []
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_dataset([record()], [g])
        with self.assertRaises(ValueError):
            validate_dataset([record("a"), record("a")], [gold("a"), gold("a")])
        with self.assertRaises(ValueError):
            validate_dataset([record("a"), record("b")], [gold("a"), gold("a")])
        with self.assertRaises(ValueError):
            validate_dataset([record("a")], [gold("b")])

    def test_story_family_cannot_cross_any_split_including_calibration(self):
        for split in ("dev", "calibration", "test"):
            records = [record("a", "train", story="shared"), record("b", split, story="shared")]
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "crosses data splits"):
                validate_dataset(records, [gold("a"), gold("b")])

    def test_layers_and_fixture_provenance_cannot_be_relabelled(self):
        with self.assertRaisesRegex(ValueError, "must not be relabeled"):
            validate_dataset([record()], [gold(layer="P0")])
        with self.assertRaisesRegex(ValueError, "must not be relabeled"):
            validate_dataset([record(purpose="observed_human_trajectory")], [gold()])
        records = [record("a", purpose="controlled_script"), record("b", purpose="observed_human_trajectory")]
        with self.assertRaisesRegex(ValueError, "evaluated separately"):
            validate_dataset(records, [gold("a", "P0"), gold("b", "P1")])

    def test_group_audit_exposes_train_calibration_person_overlap(self):
        records = [record("a", "train", person="shared-person"),
                   record("b", "calibration", person="shared-person"), record("c", "test")]
        result = audit_groups(records)
        self.assertEqual(result["person_id"]["pairwise_overlap"]["train__calibration"], 1)
        self.assertEqual(result["person_id"]["pairwise_overlap"]["train__test"], 0)
        self.assertEqual(result["person_id"]["pairwise_overlap"]["calibration__test"], 0)
        self.assertEqual(len(result["person_id"]["pairwise_overlap"]), 6)
        self.assertEqual(result["base_story_id"]["pairwise_overlap"]["train__calibration"], 0)

    def test_predictions_allow_null_probabilities_but_not_fake_or_invalid_numbers(self):
        pred = prediction()
        pred.update(p_resume=None, conditional_step_probs=None, state_probs={})
        validate_prediction(pred, observation())
        # A missing chosen step can be scored as an incorrect T2 prediction.
        pred["resume_step"] = None
        validate_prediction(pred, observation())
        for p in (float("nan"), float("inf"), -0.01, 1.01, True):
            pred = prediction()
            pred["p_resume"] = p
            with self.subTest(p=p), self.assertRaises(ValueError):
                validate_prediction(pred, observation())

    def test_predictions_reject_unknown_steps_states_evidence_and_label_step_conflict(self):
        mutations = [
            {"resume_step": "missing"}, {"resume_label": "not_resume"},
            {"conditional_step_probs": {"missing": 1}},
            {"state_probs": {"C": {"READY": 1}}},
            {"state_probs": {"typo": {"UNKNOWN": 1}}},
            {"evidence_event_ids": ["after_cutoff"]},
        ]
        for change in mutations:
            pred = prediction()
            pred.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_prediction(pred, observation())

    def test_probability_distribution_sum_tolerance_is_one_in_a_million(self):
        pred = prediction()
        pred["conditional_step_probs"] = {"pack": 0.5000025, "ship": 0.5000025}
        with self.assertRaises(ValueError):
            validate_prediction(pred, observation())
        pred["conditional_step_probs"] = {"pack": 0.50000025, "ship": 0.50000025}
        validate_prediction(pred, observation())
        for distribution in ({}, {"pack": -0.1, "ship": 1.1}, {"pack": float("nan"), "ship": 1}):
            pred["conditional_step_probs"] = deepcopy(distribution)
            with self.subTest(distribution=distribution), self.assertRaises(ValueError):
                validate_prediction(pred, observation())


if __name__ == "__main__":
    unittest.main()
