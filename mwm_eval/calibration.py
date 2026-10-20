"""单独校准集的温度缩放。小型合成集仅用于验证实现。"""

import copy
import math


def _scaled(probability, temperature):
    clipped = min(1 - 1e-9, max(1e-9, probability))
    logit = math.log(clipped / (1 - clipped)) / temperature
    return 1 / (1 + math.exp(-max(-700, min(700, logit))))


def _structural_zero(prediction):
    """A graph-exhaustion gate is a hard zero, not an extreme model logit."""
    metadata = prediction.get("metadata", {})
    return (prediction.get("p_resume") == 0.0 and isinstance(metadata, dict)
            and metadata.get("graph_gate_applied") is True)


def fit_temperature(rows, golds):
    truth = {gold["sample_id"]: gold for gold in golds}
    pairs = []
    n_probability = n_structural_zero = 0
    for row in rows:
        gold = truth[row["sample_id"]]
        if gold["resume_label"] not in {"resume", "not_resume"}:
            continue
        if gold["dataset_layer"] == "P1" and not gold["window_complete"] and gold["resume_label"] != "resume":
            continue
        pred = row.get("prediction") if row["status"] == "ok" else None
        if pred and pred["p_resume"] is not None:
            n_probability += 1
            if _structural_zero(pred):
                # A temperature cannot alter a hard graph constraint. These
                # records remain in evaluation but do not select temperature.
                n_structural_zero += 1
                continue
            pairs.append((pred["p_resume"], int(gold["resume_label"] == "resume")))
    scope = {
        "n_eligible_probability": n_probability,
        "n_excluded_structural_zero": n_structural_zero,
        "structural_zero_policy": "graph-gated zeros are excluded from temperature fitting and preserved during application; evaluation denominator unchanged",
    }
    if not pairs:
        return {"applicable": False, "temperature": None, "n": 0, **scope,
                "reason": ("all eligible probability predictions are graph-gated structural zeros"
                           if n_structural_zero else "no eligible probability predictions in calibration split")}
    if len({label for _, label in pairs}) < 2:
        return {"applicable": False, "temperature": None, "n": len(pairs), **scope,
                "reason": "non-structural calibration predictions must contain both classes"}
    temperatures = (1.0, 0.5, 0.75, 1.5, 2.0, 3.0, 5.0)

    def loss(temperature):
        total = 0.0
        for probability, label in pairs:
            clipped = min(1-1e-9, max(1e-9, probability))
            logit = math.log(clipped/(1-clipped))/temperature
            total += max(logit, 0) + math.log1p(math.exp(-abs(logit))) - label*logit
        return total / len(pairs)

    temperature = min(temperatures, key=loss)
    return {"applicable": True, "temperature": temperature, "n": len(pairs), **scope,
            "selection": "minimum binary NLL on calibration split only; ties prefer T=1",
            "candidates": list(temperatures), "nll_before": loss(1.0), "nll_after": loss(temperature),
            "limitation": "small calibration samples do not establish reliable real-world calibration"}


def apply_temperature(rows, calibration):
    result = copy.deepcopy(rows)
    if not calibration["applicable"]:
        return result
    for row in result:
        prediction = row.get("prediction")
        if row["status"] == "ok" and prediction and prediction["p_resume"] is not None:
            raw = prediction["p_resume"]
            prediction["metadata"]["calibration"] = {
                "raw_p_resume": raw, "temperature": calibration["temperature"],
                "n_calibration": calibration["n"], "split": "calibration",
                "structural_zero_preserved": _structural_zero(prediction),
            }
            prediction["p_resume"] = 0.0 if _structural_zero(prediction) else _scaled(raw, calibration["temperature"])
    return result
