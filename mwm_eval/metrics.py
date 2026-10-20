"""Standard-library evaluation for the C-owned integration protocol.

P0, P1 and integration fixtures must be evaluated separately.  ``UNKNOWN``
gold states and unsupported state annotations are masked *per factor*.
An unavailable or failed run is an error in the full eligible accuracy
denominator, never a negative prediction.  Classification F1/BA are withheld
when eligible predictions failed. Probability metrics explicitly describe
their own available-probability subset; hard rules never receive fake scores.
"""

import math
from collections import defaultdict

from mwm_eval.pair_checks import evaluate_checks


FACTORS = ("V", "F", "A", "B", "C", "Q")
LAYERS = {"P0", "P1", "integration_fixture"}
RESUME_LABELS = {"resume", "not_resume", "censored", "unknown"}
BINARY_LABELS = {"resume", "not_resume"}


def _divide(a, b):
    return a / b if b else None


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _index(items, name):
    result = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{name}: every entry must be an object")
        sid = item.get("sample_id")
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError(f"{name}: sample_id must be a nonempty string")
        if sid in result:
            raise ValueError(f"{name}: duplicate sample_id {sid}")
        result[sid] = item
    return result


def _distribution(value, name):
    if value is None:
        return
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{name}: distribution must be nonempty or null")
    if any(not isinstance(k, str) or not k for k in value):
        raise ValueError(f"{name}: distribution labels must be strings")
    if any(not _number(v) or not 0 <= v <= 1 for v in value.values()):
        raise ValueError(f"{name}: probabilities must be finite and in [0, 1]")
    if not math.isclose(sum(value.values()), 1.0, rel_tol=0, abs_tol=1e-6):
        raise ValueError(f"{name}: probabilities must sum to one")


def _validate_inputs(rows, golds, records=None):
    rows, golds = list(rows), list(golds)
    by_row, by_gold = _index(rows, "rows"), _index(golds, "golds")
    if set(by_row) != set(by_gold):
        raise ValueError("rows and golds must have exactly the same sample IDs")
    by_record = None
    if records is not None:
        by_record = _index(list(records), "records")
        if set(by_record) != set(by_gold):
            raise ValueError("records and golds must have exactly the same sample IDs")
    layers = {gold.get("dataset_layer") for gold in golds}
    if not layers <= LAYERS:
        raise ValueError("dataset_layer must be P0, P1 or integration_fixture")
    if len(layers) > 1:
        raise ValueError("mixed dataset_layer aggregation is forbidden")
    for sid, gold in by_gold.items():
        if gold.get("resume_label") not in RESUME_LABELS:
            raise ValueError(f"{sid}: invalid gold resume_label")
        if type(gold.get("window_complete")) is not bool:
            raise ValueError(f"{sid}: window_complete must be boolean")
        if gold.get("resume_step") is not None and gold["resume_label"] != "resume":
            raise ValueError(f"{sid}: a gold resume step requires resume")
        if gold.get("resume_step") is not None and not isinstance(gold["resume_step"], str):
            raise ValueError(f"{sid}: resume_step must be a string or null")
        states = gold.get("state_labels", {})
        evidence = gold.get("state_evidence", {})
        if not isinstance(states, dict) or not set(states) <= set(FACTORS):
            raise ValueError(f"{sid}: unknown gold state factor")
        if not isinstance(evidence, dict) or not set(evidence) <= set(FACTORS):
            raise ValueError(f"{sid}: invalid state evidence")
        if any(v is not None and not isinstance(v, str) for v in states.values()):
            raise ValueError(f"{sid}: state labels must be strings or null")
        for factor, event_ids in evidence.items():
            if (not isinstance(event_ids, list)
                    or any(not isinstance(eid, str) or not eid for eid in event_ids)):
                raise ValueError(f"{sid}/{factor}: evidence must contain event IDs")
            if by_record is not None:
                events = by_record[sid].get("observation", {}).get("events", [])
                allowed = {event.get("event_id") for event in events}
                if not set(event_ids) <= allowed:
                    raise ValueError(f"{sid}/{factor}: gold evidence is outside observation")
        checks = gold.get("constraint_checks", {})
        if not isinstance(checks, dict):
            raise ValueError(f"{sid}: constraint_checks must be an object")
        if "known_cancelled" in checks and type(checks["known_cancelled"]) is not bool:
            raise ValueError(f"{sid}: known_cancelled must be boolean")
        if "forbidden_belief" in checks:
            value = checks["forbidden_belief"]
            if not isinstance(value, str) or not value:
                raise ValueError(f"{sid}: forbidden_belief must be a nonempty string")
        row = by_row[sid]
        if row.get("status") not in {"ok", "error", "unavailable"}:
            raise ValueError(f"{sid}: invalid prediction status")
        if row["status"] != "ok":
            continue
        prediction = row.get("prediction")
        if not isinstance(prediction, dict) or prediction.get("resume_label") not in BINARY_LABELS:
            raise ValueError(f"{sid}: successful prediction needs a binary resume_label")
        probability = prediction.get("p_resume")
        if probability is not None and (not _number(probability) or not 0 <= probability <= 1):
            raise ValueError(f"{sid}: p_resume must be finite and in [0, 1], or null")
        if prediction.get("resume_step") is not None and not isinstance(prediction["resume_step"], str):
            raise ValueError(f"{sid}: predicted resume_step must be a string or null")
        _distribution(prediction.get("conditional_step_probs"), f"{sid}/conditional_step_probs")
        probabilities = prediction.get("state_probs", {})
        if not isinstance(probabilities, dict) or not set(probabilities) <= set(FACTORS):
            raise ValueError(f"{sid}: invalid state_probs factors")
        for factor, distribution in probabilities.items():
            _distribution(distribution, f"{sid}/{factor}")
    return by_row, by_gold, by_record, next(iter(layers), None)


def _eligible_truth(gold):
    """Return binary truth or an exclusion reason, respecting P1 right censoring."""
    label = gold["resume_label"]
    if label in {"censored", "unknown"}:
        return None, label
    if (gold["dataset_layer"] == "P1" and not gold["window_complete"]
            and label == "not_resume"):
        return None, "censored"
    return label, None


def _prediction(row):
    return row["prediction"] if row["status"] == "ok" else None


def _state_value(prediction, factor):
    if prediction is None:
        return None
    distribution = prediction.get("state_probs", {}).get(factor)
    if not distribution:
        return None
    # Lexical tie-breaking makes decisions independent of JSON key insertion order.
    return sorted(distribution, key=lambda label: (-distribution[label], label))[0]


def _classification(truths, guesses):
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    failures = {"resume": 0, "not_resume": 0}
    for truth, guess in zip(truths, guesses):
        if guess is None:
            failures[truth] += 1
            continue
        key = ("tp" if guess == "resume" else "fn") if truth == "resume" else (
            "fp" if guess == "resume" else "tn")
        counts[key] += 1
    tp, fp, fn, tn = (counts[key] for key in ("tp", "fp", "fn", "tn"))
    n = len(truths)
    n_failure = sum(failures.values())
    recall_positive = _divide(tp, tp + fn)
    recall_negative = _divide(tn, tn + fp)
    complete = n_failure == 0
    return {
        "n_eligible": n,
        "n_success": n - n_failure,
        "n_failure": n_failure,
        "coverage": _divide(n - n_failure, n),
        "n_positive": truths.count("resume"),
        "n_negative": truths.count("not_resume"),
        "accuracy": _divide(tp + tn, n),
        "resume_precision": _divide(tp, tp + fp) if complete else None,
        "resume_recall": recall_positive if complete else None,
        "resume_f1": _divide(2 * tp, 2 * tp + fp + fn) if complete else None,
        "balanced_accuracy": ((recall_positive + recall_negative) / 2
                              if complete and recall_positive is not None
                              and recall_negative is not None else None),
        "confusion_valid_predictions": counts,
        "failed_by_true_label": failures,
        "classification_scope": "all_eligible" if complete else "withheld_incomplete_predictions",
        "decision_rule": "predictor hard labels; not replaced using p_resume",
        "balanced_accuracy_requirement": "both gold classes present",
    }


def _probability_metrics(pairs, denominator, ece_bins):
    """AUROC average ties; AUPRC is grouped-threshold average precision.

    ECE is binary positive-class calibration: weighted |mean(p)-mean(y)|.
    Bins are [i/B,(i+1)/B), except the last includes p=1.
    """
    n = len(pairs)
    n_positive = sum(y for y, _ in pairs)
    n_negative = n - n_positive
    result = {
        "scope": "valid_probability_subset",
        "n_eligible": denominator,
        "n_probability": n,
        "n_missing_probability": denominator - n,
        "coverage": _divide(n, denominator),
        "n_positive": n_positive,
        "n_negative": n_negative,
        "auroc": None,
        "average_precision": None,
        "auprc_definition": "non-interpolated average precision; equal scores grouped",
        "brier": None,
        "ece": None,
        "ece_bins": ece_bins,
        "ece_definition": "positive-class probability ECE with fixed equal-width bins",
        "bin_statistics": [],
        "diagnostic_threshold": 0.5,
        "threshold_accuracy": None,
    }
    if not pairs:
        return result
    result["brier"] = sum((p - y) ** 2 for y, p in pairs) / n
    result["threshold_accuracy"] = sum((p >= 0.5) == bool(y) for y, p in pairs) / n
    groups = defaultdict(list)
    for y, p in pairs:
        groups[p].append(y)
    if n_positive and n_negative:
        negatives_before, concordant = 0, 0.0
        for score in sorted(groups):
            positive = sum(groups[score])
            negative = len(groups[score]) - positive
            concordant += positive * (negatives_before + 0.5 * negative)
            negatives_before += negative
        result["auroc"] = concordant / (n_positive * n_negative)
    if n_positive:
        total, positive, ap = 0, 0, 0.0
        for score in sorted(groups, reverse=True):
            new_positive = sum(groups[score])
            total += len(groups[score])
            positive += new_positive
            ap += (new_positive / n_positive) * (positive / total)
        result["average_precision"] = ap
    buckets = [[] for _ in range(ece_bins)]
    for y, p in pairs:
        buckets[min(int(p * ece_bins), ece_bins - 1)].append((y, p))
    ece = 0.0
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        average_p = sum(p for _, p in bucket) / len(bucket)
        fraction_positive = sum(y for y, _ in bucket) / len(bucket)
        ece += len(bucket) / n * abs(average_p - fraction_positive)
        result["bin_statistics"].append({
            "bin_index": index, "n": len(bucket), "mean_probability": average_p,
            "positive_fraction": fraction_positive,
        })
    result["ece"] = ece
    return result


def _state_metrics(by_row, golds):
    results = {}
    for factor in FACTORS:
        examples, unknown, unsubstantiated = [], 0, 0
        for gold in golds:
            label = gold.get("state_labels", {}).get(factor)
            if label is None or label == "UNKNOWN":
                unknown += 1
                continue
            if not gold.get("state_evidence", {}).get(factor):
                unsubstantiated += 1
                continue
            examples.append((label, _state_value(_prediction(by_row[gold["sample_id"]]), factor)))
        supported = sorted({truth for truth, _ in examples})
        labels = sorted({value for pair in examples for value in pair if value is not None})
        missing = sum(guess is None for _, guess in examples)
        recalls, f1s = [], []
        confusion = {truth: {} for truth in supported}
        for truth, guess in examples:
            key = guess if guess is not None else "__MISSING_PREDICTION__"
            confusion[truth][key] = confusion[truth].get(key, 0) + 1
        for label in labels:
            tp = sum(truth == guess == label for truth, guess in examples)
            fp = sum(guess == label and truth != label for truth, guess in examples)
            fn = sum(truth == label and guess != label for truth, guess in examples)
            f1s.append(_divide(2 * tp, 2 * tp + fp + fn))
            if label in supported:
                recalls.append(_divide(tp, tp + fn))
        results[factor] = {
            "n_eligible": len(examples),
            "n_excluded_unknown_or_missing": unknown,
            "n_excluded_unsubstantiated": unsubstantiated,
            "n_missing_prediction": missing,
            "coverage": _divide(len(examples) - missing, len(examples)),
            "accuracy": _divide(sum(truth == guess for truth, guess in examples), len(examples)),
            "macro_f1": (sum(f1s) / len(f1s) if f1s and not missing else None),
            "balanced_accuracy": (sum(recalls) / len(recalls) if recalls and not missing else None),
            "macro_f1_labels": labels,
            "balanced_accuracy_labels": supported,
            "scope": "substantiated_known_gold_states",
            "classification_scope": "withheld_incomplete_predictions" if missing else "all_eligible",
            "confusion": confusion,
        }
    return results


def _pair_value(prediction, relation, factor):
    if prediction is None:
        return None
    if factor in FACTORS:
        return _state_value(prediction, factor)
    if factor in {"resume_step", "T2"}:
        return prediction.get("resume_step")
    if factor in {"resume_label", "T1"} or (factor is None and relation == "same_prediction"):
        return prediction.get("resume_label")
    if factor is None and relation == "different_belief":
        return _state_value(prediction, "B")
    if factor is None and relation == "same_mental":
        values = tuple(_state_value(prediction, field) for field in ("B", "C", "Q"))
        return values if all(value is not None for value in values) else None
    raise ValueError(f"unsupported pair_factor: {factor}")


def _pairs(by_row, golds):
    groups = defaultdict(list)
    for gold in golds:
        if gold.get("pair_id") is not None and not gold.get("pair_checks"):
            groups[gold["pair_id"]].append(gold)
    results = {}
    for relation in ("same_prediction", "different_belief", "same_mental"):
        results[relation] = {
            "n_pairs_defined": 0, "n_evaluable": 0, "n_pass": 0,
            "n_incomplete_pairs": 0, "n_missing_output": 0,
            "n_inconsistent_annotations": 0,
        }
    for pair_id, members in groups.items():
        relations = {member.get("pair_relation") for member in members}
        if not relations <= set(results):
            raise ValueError(f"{pair_id}: pair_relation must be explicit and recognized")
        if len(relations) != 1:
            for relation in relations:
                results[relation]["n_inconsistent_annotations"] += 1
            continue
        relation = next(iter(relations))
        target = results[relation]
        target["n_pairs_defined"] += 1
        if len(members) != 2:
            target["n_incomplete_pairs"] += 1
            continue
        factors = {member.get("pair_factor") for member in members}
        if len(factors) != 1:
            target["n_inconsistent_annotations"] += 1
            continue
        factor = next(iter(factors))
        values = [_pair_value(_prediction(by_row[m["sample_id"]]), relation, factor) for m in members]
        if any(value is None for value in values):
            target["n_missing_output"] += 1
            continue
        target["n_evaluable"] += 1
        passed = values[0] != values[1] if relation == "different_belief" else values[0] == values[1]
        target["n_pass"] += passed
    for target in results.values():
        target["coverage"] = _divide(target["n_evaluable"], target["n_pairs_defined"])
        target["rate"] = _divide(target["n_pass"], target["n_evaluable"])
        target["scope"] = "complete_two_member_pairs_with_required_outputs"
    return results


def _constraints(by_row, golds):
    results = {key: {"n_defined": 0, "n_evaluable": 0, "n_violation": 0}
               for key in ("invalid_resume", "knowledge_leakage")}
    for gold in golds:
        checks = gold.get("constraint_checks", {})
        prediction = _prediction(by_row[gold["sample_id"]])
        if checks.get("known_cancelled") is True:
            target = results["invalid_resume"]
            target["n_defined"] += 1
            if prediction is not None:
                target["n_evaluable"] += 1
                target["n_violation"] += prediction["resume_label"] == "resume"
        if "forbidden_belief" in checks:
            target = results["knowledge_leakage"]
            target["n_defined"] += 1
            belief = _state_value(prediction, "B")
            if belief is not None:
                target["n_evaluable"] += 1
                target["n_violation"] += belief == checks["forbidden_belief"]
    for target in results.values():
        target["n_missing_output"] = target["n_defined"] - target["n_evaluable"]
        target["coverage"] = _divide(target["n_evaluable"], target["n_defined"])
        target["rate"] = _divide(target["n_violation"], target["n_evaluable"])
        target["scope"] = "explicit_constraint_annotations_with_required_outputs"
    return results


def evaluate(rows, golds, records=None, ece_bins=10):
    """Evaluate exactly matching IDs from one dataset layer.

    Returns ``dataset_layer/counts/t1/t2/states/pairs/constraints`` plus a few
    named compatibility aliases. Probabilities are never inferred from labels.
    The probability-only diagnostic threshold is fixed at 0.5; T1's primary
    metrics always use the predictor's explicit hard decision.
    """
    if type(ece_bins) is not int or ece_bins <= 0:
        raise ValueError("ece_bins must be a positive integer")
    by_row, by_gold, _, layer = _validate_inputs(rows, golds, records)
    golds = list(by_gold.values())
    truths, guesses, probabilities = [], [], []
    excluded = {"censored": 0, "unknown": 0}
    steps = {"n_eligible": 0, "n_top1_correct": 0, "n_with_conditional_distribution": 0,
             "n_top3_correct": 0, "n_missing_step": 0}
    for gold in golds:
        truth, exclusion = _eligible_truth(gold)
        prediction = _prediction(by_row[gold["sample_id"]])
        if exclusion:
            excluded[exclusion] += 1
        else:
            truths.append(truth)
            guesses.append(prediction["resume_label"] if prediction is not None else None)
            if prediction is not None and prediction.get("p_resume") is not None:
                probabilities.append((int(truth == "resume"), prediction["p_resume"]))
        if truth == "resume" and gold.get("resume_step") is not None:
            steps["n_eligible"] += 1
            step = prediction.get("resume_step") if prediction is not None else None
            steps["n_missing_step"] += step is None
            steps["n_top1_correct"] += step == gold["resume_step"]
            distribution = prediction.get("conditional_step_probs") if prediction is not None else None
            if distribution:
                steps["n_with_conditional_distribution"] += 1
                ranked = sorted(distribution, key=lambda key: (-distribution[key], key))
                steps["n_top3_correct"] += gold["resume_step"] in ranked[:3]
    t1 = _classification(truths, guesses)
    t1["probability"] = _probability_metrics(probabilities, len(truths), ece_bins)
    steps["top1_accuracy"] = _divide(steps["n_top1_correct"], steps["n_eligible"])
    steps["top3_accuracy"] = (_divide(steps["n_top3_correct"], steps["n_eligible"])
                               if steps["n_with_conditional_distribution"] else None)
    steps["conditional_distribution_coverage"] = _divide(steps["n_with_conditional_distribution"], steps["n_eligible"])
    steps["scope"] = "gold_resume_with_identifiable_gold_step; missing predictions count as incorrect"
    steps["top3_scope"] = "all_T2_eligible; missing distribution counts as incorrect; null if none available"
    steps["top1_source"] = "explicit resume_step; not unconditional joint probability"
    counts = {
        "n_planned": len(golds), "n_success": sum(row["status"] == "ok" for row in by_row.values()),
        "n_error": sum(row["status"] == "error" for row in by_row.values()),
        "n_unavailable": sum(row["status"] == "unavailable" for row in by_row.values()),
        "n_eligible_t1": len(truths), "n_excluded": excluded,
        "censored_fraction": _divide(excluded["censored"], len(golds)),
    }
    counts["n_failure"] = counts["n_error"] + counts["n_unavailable"]
    return {
        "schema_version": "c-evaluation-draft-1", "dataset_layer": layer,
        "counts": counts, "t1": t1, "t2": steps,
        "states": _state_metrics(by_row, golds), "pairs": _pairs(by_row, golds),
        "mechanism_pairs": evaluate_checks(by_row, golds),
        "constraints": _constraints(by_row, golds),
        "n_eligible_t1": len(truths), "accuracy_all_eligible": t1["accuracy"],
        "resume_f1": t1["resume_f1"], "step_accuracy": steps["top1_accuracy"],
        "n_eligible_t2": steps["n_eligible"],
    }
