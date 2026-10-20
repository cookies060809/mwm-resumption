"""Translate A's proposed T1/T2/T3 output without implementing A's model."""

import copy
import math

from mwm_eval.schema import validate_prediction


def normalize_a_output(payload, observation, threshold=0.5):
    if not isinstance(payload, dict):
        raise ValueError("A output must be an object")
    needed = {"t1_resume_probability", "t2_conditional_step_distribution",
              "t3_state_distributions", "evidence_trace", "cost"}
    if not needed <= set(payload):
        raise ValueError("A prediction wrapper has not supplied T1/T2/T3, evidence and cost")
    if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold) or not 0 < threshold < 1):
        raise ValueError("decision threshold must be finite and strictly between 0 and 1")
    probability = payload["t1_resume_probability"]
    if (isinstance(probability, bool) or not isinstance(probability, (int, float))
            or not math.isfinite(probability) or not 0 <= probability <= 1):
        raise ValueError("A T1 probability must be finite and in [0,1]")
    conditional = copy.deepcopy(payload["t2_conditional_step_distribution"])
    if conditional is not None and (not isinstance(conditional, dict) or not conditional):
        raise ValueError("A conditional distribution must be a nonempty object or null")
    if probability == 0 and conditional is not None:
        raise ValueError("conditional recovery step is undefined when P(resume)=0")
    trace = payload["evidence_trace"]
    if not isinstance(trace, list):
        raise ValueError("A evidence_trace must be a list")
    evidence = []
    for entry in trace:
        if isinstance(entry, str):
            evidence.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("event_id"), str):
            evidence.append(entry["event_id"])
        elif isinstance(entry, dict) and isinstance(entry.get("evidence_event_ids"), list):
            evidence.extend(entry["evidence_event_ids"])
        else:
            raise ValueError("A evidence must explicitly reference event IDs")
    if not isinstance(payload["cost"], dict):
        raise ValueError("A cost must be an object; unknown values remain null")
    label = "resume" if probability >= threshold else "not_resume"
    if any(not isinstance(event_id, str) for event_id in evidence):
        raise ValueError("A evidence IDs must be strings")
    prediction = {
        "resume_label": label, "resume_step": None, "p_resume": probability,
        "conditional_step_probs": conditional,
        "state_probs": copy.deepcopy(payload["t3_state_distributions"]),
        "evidence_event_ids": list(dict.fromkeys(evidence)),
        "reason": "A T1/T2/T3 output; fixed threshold and conditional step argmax applied by C.",
        "metadata": {"adapter": "a-t123-to-c/1.0.0", "decision_threshold": threshold,
                     "a_cost": copy.deepcopy(payload["cost"]),
                     "a_uncertainty": copy.deepcopy(payload.get("uncertainty")),
                     "verification_scope": "output_contract_only"}}
    validate_prediction(prediction, observation)
    if conditional and label == "resume":
        prediction["resume_step"] = max(sorted(conditional), key=conditional.get)
    return prediction
