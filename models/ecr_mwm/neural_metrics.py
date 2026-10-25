"""Predeclared source-window metrics, independent of C's public evaluator.

T1 uses threshold 0.5 and ten equal-width ECE bins. T3 macro metrics average
only classes occurring in gold for that factor; UNKNOWN targets are omitted by
the caller. Q step identifiers are scored as within-record positions. None
means mathematically undefined, never a dropped prediction or a zero score.
"""
from math import log
from statistics import mean, stdev


_EPS = 1e-12
_FACTORS = "VFABCQ"


def _argmax(probabilities):
    # Stable insertion-order tie break, also used for top-k.
    return max(probabilities, key=probabilities.get) if probabilities else None


def _nll(probability):
    return -log(max(_EPS, probability))


def _auc(rows):
    positive = [p for p, y in rows if y]
    negative = [p for p, y in rows if not y]
    if not positive or not negative:
        return None
    return sum((a > b) + 0.5 * (a == b) for a in positive for b in negative) / (len(positive) * len(negative))


def _average_precision(rows):
    positives = sum(y for _, y in rows)
    if not positives:
        return None
    # Group tied scores: arbitrary input order cannot change average precision.
    groups = {}
    for score, label in rows:
        total, hits = groups.get(score, (0, 0))
        groups[score] = (total + 1, hits + int(label))
    seen = hits = 0
    result = 0.0
    for score in sorted(groups, reverse=True):
        count, correct = groups[score]
        seen += count
        hits += correct
        result += correct / positives * hits / seen
    return result


def _classification(gold, predicted):
    labels = sorted(set(gold))
    f1s, recalls = [], []
    for label in labels:
        tp = sum(a == label and b == label for a, b in zip(gold, predicted))
        fp = sum(a != label and b == label for a, b in zip(gold, predicted))
        fn = sum(a == label and b != label for a, b in zip(gold, predicted))
        f1s.append(2 * tp / (2 * tp + fp + fn))
        recalls.append(tp / (tp + fn))
    return {"accuracy": mean(a == b for a, b in zip(gold, predicted)) if gold else None,
            "macro_f1": mean(f1s) if f1s else None,
            "balanced_accuracy": mean(recalls) if recalls else None}


def _q_label(label, steps):
    return "k" + str(steps.index(label)) if label in steps else label


def evaluate(predictions, targets):
    """Score all eligible targets; missing T2/T3 outputs count as errors.

    Targets are external supervision, never model input. ``step`` must already
    be masked to a valid original-goal T2 target, and ``states`` must contain
    only evidence-supported, non-UNKNOWN factors. Counts remain explicit.
    """
    if len(predictions) != len(targets):
        raise ValueError("PREDICTION_TARGET_LENGTH_MISMATCH")
    rows = [(float(p["t1"]), t["resume"]) for p, t in zip(predictions, targets)
            if t["resume"] is not None]
    n = len(rows)
    tp = sum(score >= 0.5 and label for score, label in rows)
    fp = sum(score >= 0.5 and not label for score, label in rows)
    fn = sum(score < 0.5 and label for score, label in rows)
    bins = [[] for _ in range(10)]
    for score, label in rows:
        bins[min(9, int(score * 10))].append((score, label))
    t1 = {"n": n,
          "accuracy": mean((score >= 0.5) == label for score, label in rows) if n else None,
          "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else (0.0 if n else None),
          "auroc": _auc(rows), "ap": _average_precision(rows),
          "brier": mean((score - label) ** 2 for score, label in rows) if n else None,
          "ece10": sum(len(b) / n * abs(mean(p for p, _ in b) - mean(y for _, y in b))
                       for b in bins if b) if n else None}
    top1, top3, losses, missing = [], [], [], 0
    for prediction, target in zip(predictions, targets):
        label = target["step"]
        if label is None:
            continue
        distribution = prediction["t2"] or {}
        ranked = sorted(distribution, key=distribution.get, reverse=True)
        missing += not bool(distribution)
        top1.append(bool(ranked) and ranked[0] == label)
        top3.append(label in ranked[:3])
        losses.append(_nll(distribution.get(label, 0.0)))
    t2 = {"n": len(losses), "missing": missing,
          "top1": mean(top1) if losses else None,
          "top3": mean(top3) if losses else None,
          "nll": mean(losses) if losses else None}
    t3 = {}
    for factor in _FACTORS:
        gold, guesses, losses, zero = [], [], [], 0
        for prediction, target in zip(predictions, targets):
            if factor not in target["states"]:
                continue
            label = target["states"][factor]
            distribution = prediction["t3"].get(factor, {})
            if factor == "Q":
                label = _q_label(label, target["steps"])
                distribution = {_q_label(k, target["steps"]): value for k, value in distribution.items()}
            probability = distribution.get(label, 0.0)
            zero += probability <= 0.0
            gold.append(label)
            guesses.append(_argmax(distribution))
            losses.append(_nll(probability))
        t3[factor] = {**_classification(gold, guesses), "n": len(gold),
                      "nll": mean(losses) if losses else None, "zero_support": zero}
    return {"t1": t1, "t2": t2, "t3": t3}


def aggregate(seed_metrics):
    """Aggregate corresponding numeric leaves, including count leaves.

    ``sample_sd`` is the sample standard deviation over available seeds; it is
    undefined for fewer than two values. None leaves are ignored with n shown.
    Count means are mean per-seed counts, not a pooled sample denominator.
    """
    def combine(values):
        mappings = [value for value in values if isinstance(value, dict)]
        if mappings:
            keys = dict.fromkeys(key for value in mappings for key in value)
            return {key: combine([value.get(key) for value in mappings]) for key in keys}
        numbers = [float(value) for value in values
                   if isinstance(value, (int, float)) and not isinstance(value, bool)]
        return {"mean": mean(numbers) if numbers else None,
                "sample_sd": stdev(numbers) if len(numbers) > 1 else None,
                "n": len(numbers)}
    return combine(list(seed_metrics))
