"""Explicit, evaluation-only mechanism checks; never passed to a predictor."""

import json
import math
from collections import defaultdict

TARGETS = {"T1", "T2", "V", "F", "A", "B", "C", "Q", "hard_decision",
           "p_resume", "state_probs", "conditional_step_probs"}
DISTRIBUTIONS = {"p_resume", "state_probs", "conditional_step_probs"}


def validate_checks(checks):
    if not isinstance(checks, list) or not checks:
        raise ValueError("pair_checks must be a nonempty list")
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"target", "relation"}:
            raise ValueError("each pair check requires exactly target and relation")
        target, relation = check["target"], check["relation"]
        if target not in TARGETS or relation not in {"match_gold", "equal"}:
            raise ValueError("unsupported pair check")
        if relation == "match_gold" and target in DISTRIBUTIONS | {"hard_decision"}:
            raise ValueError("distribution checks require equal; no distribution gold exists")
        key = (target, relation)
        if key in seen:
            raise ValueError("duplicate pair check")
        seen.add(key)


def _value(prediction, target):
    if target == "hard_decision":
        return (prediction["resume_label"], prediction.get("resume_step"))
    if target == "T1":
        return prediction["resume_label"]
    if target == "T2":
        return prediction.get("resume_step")
    if target in DISTRIBUTIONS:
        value = prediction.get(target)
        return value if value not in (None, {}) else None
    distribution = prediction.get("state_probs", {}).get(target)
    return max(sorted(distribution), key=distribution.get) if distribution else None


def _gold(gold, target):
    if target == "T1":
        value = gold["resume_label"]
        return value if value in {"resume", "not_resume"} else None
    if target == "T2":
        return gold.get("resume_step") if gold["resume_label"] == "resume" else None
    value = gold.get("state_labels", {}).get(target)
    return value if value not in {None, "UNKNOWN", "UNCERTAIN"} else None


def _equal(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        keys = set(left) | set(right)
        return all(_equal(left.get(k, 0.0), right.get(k, 0.0)) for k in keys)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=0, abs_tol=1e-9)
    return left == right


def evaluate_checks(by_row, golds):
    groups = defaultdict(list)
    for gold in golds:
        if "pair_checks" in gold:
            validate_checks(gold["pair_checks"])
            if any(not isinstance(gold.get(key), str) or not gold[key]
                   for key in ("pair_id", "pair_mechanism")):
                raise ValueError("mechanism checks require pair_id and pair_mechanism")
            groups[gold["pair_id"]].append(gold)
    result = {}
    for pair_id, members in groups.items():
        first = members[0]
        checks = first["pair_checks"]
        validate_checks(checks)
        definition = json.dumps(checks, sort_keys=True)
        if any(json.dumps(m["pair_checks"], sort_keys=True) != definition
               or m.get("pair_mechanism") != first.get("pair_mechanism") for m in members):
            raise ValueError(f"{pair_id}: inconsistent mechanism check definitions")
        mechanism = result.setdefault(first["pair_mechanism"], {})
        for check in checks:
            target, relation = check["target"], check["relation"]
            counts = mechanism.setdefault(f"{target}:{relation}", {
                "n_defined": 0, "n_evaluable": 0, "n_pass": 0,
                "n_missing_output": 0, "n_incomplete_pair": 0, "n_unlabeled": 0})
            counts["n_defined"] += 1
            if len(members) != 2:
                counts["n_incomplete_pair"] += 1
                continue
            predictions = [by_row[m["sample_id"]] for m in members]
            if any(row["status"] != "ok" or row.get("prediction") is None for row in predictions):
                counts["n_missing_output"] += 1
                continue
            values = [_value(row["prediction"], target) for row in predictions]
            if any(value is None for value in values):
                counts["n_missing_output"] += 1
                continue
            if relation == "match_gold":
                expected = [_gold(m, target) for m in members]
                if any(value is None for value in expected):
                    counts["n_unlabeled"] += 1
                    continue
                passed = all(value == truth for value, truth in zip(values, expected))
            else:
                passed = _equal(*values)
            counts["n_evaluable"] += 1
            counts["n_pass"] += bool(passed)
    for mechanism in result.values():
        for counts in mechanism.values():
            n = counts["n_evaluable"]
            counts["rate"] = counts["n_pass"] / n if n else None
            counts["coverage"] = n / counts["n_defined"]
    return result
