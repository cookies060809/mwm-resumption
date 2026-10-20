"""Hand-checkable cases for the production-draft metric denominators."""

import unittest

from mwm_eval.metrics import evaluate
from mwm_eval.statistics import paired_cluster_bootstrap


def gold(sid, label="resume", layer="P0", complete=True, step=None, **extra):
    return dict(sample_id=sid, dataset_layer=layer, resume_label=label,
                resume_step=step, window_complete=complete,
                state_labels=extra.pop("state_labels", {}),
                state_evidence=extra.pop("state_evidence", {}), **extra)


def row(sid, label="resume", p=None, status="ok", step=None, states=None, **extra):
    return {"sample_id": sid, "status": status, "prediction": {
        "resume_label": label, "resume_step": step, "p_resume": p,
        "state_probs": states or {}, **extra,
    } if status == "ok" else None}


class FullMetricTests(unittest.TestCase):
    def test_empty_and_single_class_metrics_are_explicitly_undefined(self):
        report = evaluate([], [])
        self.assertIsNone(report["t1"]["accuracy"])
        self.assertIsNone(report["t1"]["probability"]["coverage"])
        self.assertIsNone(report["t2"]["top1_accuracy"])
        report = evaluate([row("a", p=0.9)], [gold("a")])
        self.assertIsNone(report["t1"]["balanced_accuracy"])
        self.assertIsNone(report["t1"]["probability"]["auroc"])
        self.assertEqual(report["t1"]["probability"]["average_precision"], 1)

    def test_confusion_f1_balanced_accuracy_hand_calculation(self):
        labels = ["resume", "resume", "resume", "not_resume", "not_resume", "not_resume"]
        guesses = ["resume", "resume", "not_resume", "resume", "not_resume", "not_resume"]
        report = evaluate([row(str(i), guess) for i, guess in enumerate(guesses)],
                          [gold(str(i), label) for i, label in enumerate(labels)])
        self.assertEqual(report["t1"]["confusion_valid_predictions"], {"tp": 2, "fn": 1, "fp": 1, "tn": 2})
        for key in ("accuracy", "resume_precision", "resume_recall", "resume_f1", "balanced_accuracy"):
            self.assertAlmostEqual(report["t1"][key], 2 / 3)

    def test_auc_ap_group_equal_scores_and_ece_endpoints(self):
        labels = ["resume", "not_resume", "resume", "not_resume"]
        ps = [0.8, 0.8, 0.2, 0.1]
        report = evaluate([row(str(i), p=p) for i, p in enumerate(ps)],
                          [gold(str(i), label) for i, label in enumerate(labels)], ece_bins=2)
        probability = report["t1"]["probability"]
        # Two of four positive-negative pairs win, one ties: 2.5 / 4.
        self.assertAlmostEqual(probability["auroc"], 0.625)
        self.assertAlmostEqual(probability["average_precision"], 0.5 * 0.5 + 0.5 * (2 / 3))
        self.assertAlmostEqual(probability["brier"], (0.04 + 0.64 + 0.64 + 0.01) / 4)
        self.assertAlmostEqual(probability["ece"], 0.5 * 0.3 + 0.5 * 0.35)
        endpoints = evaluate([row("p", p=1), row("n", "not_resume", p=0)],
                             [gold("p"), gold("n", "not_resume")])["t1"]["probability"]
        self.assertEqual(endpoints["ece"], 0)
        self.assertEqual(endpoints["bin_statistics"][-1]["bin_index"], 9)

    def test_hard_labels_are_not_replaced_by_probability_threshold(self):
        report = evaluate([row("a", "not_resume", p=0.9)], [gold("a")])
        self.assertEqual(report["t1"]["accuracy"], 0)
        self.assertEqual(report["t1"]["probability"]["threshold_accuracy"], 1)

    def test_failures_stay_in_accuracy_and_probability_subset_is_named(self):
        rows = [row("a", p=0.8), row("b", status="error"), row("c", "not_resume")]
        report = evaluate(rows, [gold("a"), gold("b"), gold("c", "not_resume")])
        self.assertAlmostEqual(report["t1"]["accuracy"], 2 / 3)
        self.assertIsNone(report["t1"]["resume_f1"])
        self.assertIsNone(report["t1"]["balanced_accuracy"])
        probability = report["t1"]["probability"]
        self.assertEqual(probability["n_probability"], 1)
        self.assertEqual(probability["n_eligible"], 3)
        self.assertEqual(probability["scope"], "valid_probability_subset")
        self.assertAlmostEqual(probability["coverage"], 1 / 3)
        no_prob = evaluate([row("a")], [gold("a")])["t1"]["probability"]
        self.assertEqual(no_prob["coverage"], 0)
        self.assertIsNone(no_prob["brier"])

    def test_p1_incomplete_window_positive_kept_negative_censored(self):
        labels = [gold("a", layer="P1", complete=False, step="s1"),
                  gold("b", "not_resume", layer="P1", complete=False),
                  gold("c", "not_resume", layer="P1"),
                  gold("d", "unknown", layer="P1")]
        report = evaluate([row("a", step="s1"), row("b"), row("c", "not_resume"), row("d")], labels)
        self.assertEqual(report["counts"]["n_eligible_t1"], 2)
        self.assertEqual(report["counts"]["n_excluded"], {"censored": 1, "unknown": 1})
        self.assertEqual(report["t2"]["n_eligible"], 1)
        self.assertEqual(report["t1"]["accuracy"], 1)

    def test_t2_eligibility_uses_gold_and_missing_step_is_wrong(self):
        rows = [row("a", "not_resume"), row("b", step="s2", conditional_step_probs={"s1": 0.6, "s2": 0.4}),
                row("c", step="s1"), row("d", step="s3")]
        labels = [gold("a", step="s1"), gold("b", step="s1"), gold("c", step="s1"),
                  gold("d", "not_resume")]
        report = evaluate(rows, labels)["t2"]
        self.assertEqual(report["n_eligible"], 3)
        self.assertAlmostEqual(report["top1_accuracy"], 1 / 3)
        self.assertAlmostEqual(report["top3_accuracy"], 1 / 3)
        self.assertEqual(report["n_missing_step"], 1)

    def test_state_unknown_and_unsubstantiated_masks_are_per_factor(self):
        labels = [gold("a", state_labels={"C": "ACTIVE", "B": "UNKNOWN"}, state_evidence={"C": ["e1"]}),
                  gold("b", state_labels={"C": "SUSPENDED", "B": "BELIEVES_VALID"}, state_evidence={"C": ["e1"]}),
                  gold("c", state_labels={"C": "SUSPENDED"}, state_evidence={"C": ["e1"]})]
        rows = [row("a", states={"C": {"ACTIVE": 1}}), row("b", states={"C": {"ACTIVE": 1}}),
                row("c", states={"C": {"SUSPENDED": 1}})]
        states = evaluate(rows, labels)["states"]
        self.assertEqual(states["B"]["n_eligible"], 0)
        self.assertEqual(states["B"]["n_excluded_unsubstantiated"], 1)
        self.assertAlmostEqual(states["C"]["accuracy"], 2 / 3)
        self.assertAlmostEqual(states["C"]["macro_f1"], 2 / 3)
        self.assertAlmostEqual(states["C"]["balanced_accuracy"], 0.75)
        rows[1] = row("b")
        states = evaluate(rows, labels)["states"]
        self.assertAlmostEqual(states["C"]["accuracy"], 2 / 3)
        self.assertIsNone(states["C"]["macro_f1"])

    def test_duplicate_missing_ids_layer_mixing_and_invalid_probabilities_rejected(self):
        for rows, golds in [([row("a"), row("a")], [gold("a")]),
                            ([row("a")], [gold("a"), gold("a")]),
                            ([row("a")], [gold("b")]),
                            ([row("a"), row("b")], [gold("a"), gold("b", layer="P1")])]:
            with self.subTest(rows=rows, golds=golds), self.assertRaises(ValueError):
                evaluate(rows, golds)
        for p in (float("nan"), float("inf"), -0.1, True):
            with self.subTest(p=p), self.assertRaises(ValueError):
                evaluate([row("a", p=p)], [gold("a")])
        with self.assertRaises(ValueError):
            evaluate([row("a", states={"C": {"ACTIVE": 0.2}})], [gold("a")])

    def test_pairs_require_two_members_and_actual_specified_outputs(self):
        labels = [gold("a", pair_id="p", pair_relation="different_belief"),
                  gold("b", pair_id="p", pair_relation="different_belief"),
                  gold("c", pair_id="q", pair_relation="same_prediction"),
                  gold("d", pair_id="r", pair_relation="same_mental"),
                  gold("e", pair_id="r", pair_relation="same_mental")]
        rows = [row("a", states={"B": {"BELIEVES_VALID": 1}}),
                row("b", states={"B": {"BELIEVES_INVALID": 1}}), row("c"), row("d"), row("e")]
        pairs = evaluate(rows, labels)["pairs"]
        self.assertEqual(pairs["different_belief"]["rate"], 1)
        self.assertEqual(pairs["same_prediction"]["n_incomplete_pairs"], 1)
        self.assertIsNone(pairs["same_prediction"]["rate"])
        self.assertEqual(pairs["same_mental"]["n_missing_output"], 1)
        self.assertIsNone(pairs["same_mental"]["rate"])

    def test_constraints_only_use_explicit_annotations(self):
        labels = [gold("a", constraint_checks={"known_cancelled": True, "forbidden_belief": "BELIEVES_INVALID"}),
                  gold("b", state_labels={"V": "CANCELLED"}, state_evidence={"V": ["e1"]}),
                  gold("c", constraint_checks={"known_cancelled": True})]
        rows = [row("a", states={"B": {"BELIEVES_INVALID": 1}}), row("b"), row("c", status="unavailable")]
        constraints = evaluate(rows, labels)["constraints"]
        self.assertEqual(constraints["invalid_resume"]["n_defined"], 2)
        self.assertEqual(constraints["invalid_resume"]["n_evaluable"], 1)
        self.assertEqual(constraints["invalid_resume"]["rate"], 1)
        self.assertEqual(constraints["knowledge_leakage"]["n_defined"], 1)
        self.assertEqual(constraints["knowledge_leakage"]["rate"], 1)

    def test_cluster_bootstrap_preserves_whole_clusters_and_pairing(self):
        # Two clusters each contain two rows. A always wins cluster X and loses
        # cluster Y, so paired accuracy differences are only -1, 0 or 1.
        labels = [gold(str(i), "resume" if i % 2 == 0 else "not_resume") for i in range(4)]
        records = [{"sample_id": str(i), "base_story_id": "X" if i < 2 else "Y"} for i in range(4)]
        a = [row(str(i), labels[i]["resume_label"] if i < 2 else ("not_resume" if i % 2 == 0 else "resume")) for i in range(4)]
        b = [row(str(i), labels[i]["resume_label"] if i >= 2 else ("not_resume" if i % 2 == 0 else "resume")) for i in range(4)]
        report = paired_cluster_bootstrap(a, b, labels, records, seed=7, n_bootstrap=200)
        self.assertTrue(report["computed"])
        self.assertEqual(report["n_clusters"], 2)
        self.assertEqual(report["n_samples"], 4)
        self.assertEqual(report["difference"], 0)
        self.assertEqual((report["ci_low"], report["ci_high"]), (-1, 1))
        reverse = paired_cluster_bootstrap(b, a, labels, records, seed=7, n_bootstrap=200)
        self.assertEqual(reverse["ci_low"], -report["ci_high"])
        identical = paired_cluster_bootstrap(a, a, labels, records, seed=7, n_bootstrap=200)
        self.assertEqual((identical["ci_low"], identical["ci_high"]), (0, 0))
        self.assertEqual(report, paired_cluster_bootstrap(a, b, labels, records, seed=7, n_bootstrap=200))

    def test_cluster_bootstrap_insufficient_clusters_and_failure_policy(self):
        labels = [gold("a"), gold("b", "not_resume")]
        records = [{"sample_id": sid, "base_story_id": "only"} for sid in ("a", "b")]
        a, b = [row("a"), row("b", status="error")], [row("a"), row("b", "not_resume")]
        report = paired_cluster_bootstrap(a, b, labels, records, n_bootstrap=20)
        self.assertFalse(report["computed"])
        self.assertEqual(report["difference"], -0.5)
        records[1]["base_story_id"] = "other"
        report = paired_cluster_bootstrap(a, b, labels, records, metric="resume_f1", n_bootstrap=20)
        self.assertFalse(report["computed"])
        self.assertIsNone(report["difference"])
        records[1].pop("base_story_id")
        with self.assertRaises(ValueError):
            paired_cluster_bootstrap(a, b, labels, records, n_bootstrap=20)


if __name__ == "__main__":
    unittest.main()
