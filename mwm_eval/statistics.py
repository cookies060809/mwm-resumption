"""Paired bootstrap intervals that resample whole story/person clusters.

Intervals describe only the supplied dataset layer and eligible binary
outcomes. They are not significance tests or evidence of real-human validity
when evaluated on integration fixtures or P0 controlled scripts.
"""

import math
import random
from collections import defaultdict

from .metrics import _classification, _eligible_truth, _prediction, _validate_inputs


def _quantile(values, probability):
    values = sorted(values)
    index = probability * (len(values) - 1)
    lower, upper = math.floor(index), math.ceil(index)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def paired_cluster_bootstrap(rows_a, rows_b, golds, records, metric="accuracy",
                             cluster_key="base_story_id", seed=0,
                             n_bootstrap=500, confidence=0.95):
    """Return paired A-minus-B metric difference with a percentile interval.

    ``metric`` accepts accuracy, resume_f1 (or f1), balanced_accuracy.
    Both methods must have exactly the gold/record sample IDs. Failures count
    wrong in accuracy; F1/BA are withheld when predictions failed. Each draw
    samples the original number of clusters *with replacement*, retaining all
    eligible members of each sampled cluster and using identical draws for A/B.
    At least two clusters and >=80% defined replicates are required for a CI.
    """
    if metric == "f1":
        metric = "resume_f1"
    if metric not in {"accuracy", "resume_f1", "balanced_accuracy"}:
        raise ValueError("metric must be accuracy, resume_f1 or balanced_accuracy")
    if type(n_bootstrap) is not int or n_bootstrap < 2:
        raise ValueError("n_bootstrap must be an integer >= 2")
    if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
            or not 0 < confidence < 1):
        raise ValueError("confidence must be between zero and one")
    if not isinstance(cluster_key, str) or not cluster_key:
        raise ValueError("cluster_key must be a nonempty string")
    golds, records, rows_a, rows_b = list(golds), list(records), list(rows_a), list(rows_b)
    a, by_gold, by_record, layer = _validate_inputs(rows_a, golds, records)
    b, _, _, _ = _validate_inputs(rows_b, golds, records)
    clusters = defaultdict(list)
    excluded = {"censored": 0, "unknown": 0}
    for sid, gold in by_gold.items():
        truth, reason = _eligible_truth(gold)
        if reason:
            excluded[reason] += 1
            continue
        cluster = by_record[sid].get(cluster_key)
        if not isinstance(cluster, str) or not cluster.strip():
            raise ValueError(f"{sid}: eligible record lacks string {cluster_key}")
        pred_a, pred_b = _prediction(a[sid]), _prediction(b[sid])
        clusters[cluster].append((truth, pred_a["resume_label"] if pred_a else None,
                                 pred_b["resume_label"] if pred_b else None))
    # Sorting guarantees deterministic intervals when input rows are reordered.
    cluster_ids = sorted(clusters)
    examples = [example for cid in cluster_ids for example in clusters[cid]]

    def score(items, method_index):
        report = _classification([item[0] for item in items], [item[method_index] for item in items])
        return report[metric]

    score_a, score_b = score(examples, 1), score(examples, 2)
    difference = score_a - score_b if score_a is not None and score_b is not None else None
    result = {
        "computed": False, "reason": None, "dataset_layer": layer,
        "metric": metric, "difference_definition": "method_A_minus_method_B",
        "cluster_key": cluster_key, "seed": seed, "confidence": confidence,
        "n_bootstrap_requested": n_bootstrap, "n_bootstrap_valid": 0,
        "n_bootstrap_undefined": 0, "n_samples": len(examples),
        "n_clusters": len(clusters), "n_excluded": excluded,
        "score_a": score_a, "score_b": score_b, "difference": difference,
        "ci_low": None, "ci_high": None, "ci_method": "paired_cluster_percentile",
        "failure_policy": "accuracy counts failure wrong; incomplete F1/BA withheld",
    }
    if len(clusters) < 2:
        result["reason"] = "at_least_two_eligible_clusters_required"
        return result
    if difference is None:
        result["reason"] = "point_metric_undefined_or_incomplete_predictions"
        return result
    rng = random.Random(seed)
    differences = []
    for _ in range(n_bootstrap):
        draw = [rng.choice(cluster_ids) for _ in cluster_ids]
        sampled = [example for cid in draw for example in clusters[cid]]
        sampled_a, sampled_b = score(sampled, 1), score(sampled, 2)
        if sampled_a is not None and sampled_b is not None:
            differences.append(sampled_a - sampled_b)
    result["n_bootstrap_valid"] = len(differences)
    result["n_bootstrap_undefined"] = n_bootstrap - len(differences)
    if len(differences) < max(2, math.ceil(0.8 * n_bootstrap)):
        result["reason"] = "fewer_than_80_percent_defined_bootstrap_replicates"
        return result
    tail = (1 - confidence) / 2
    result.update(computed=True, ci_low=_quantile(differences, tail),
                  ci_high=_quantile(differences, 1 - tail))
    return result
