"""Translate A's T1/T2/T3 output and repair only boundary roundoff."""

import copy
import math

from mwm_eval.schema import validate_prediction


ROUNDING_TOLERANCE = 1e-12


def _repair_distribution(distribution, path, repairs):
    if not isinstance(distribution, dict) or not distribution:
        return distribution  # Canonical validation reports malformed outputs.
    values = list(distribution.values())
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in values):
        return distribution
    if all(0 <= v <= 1 for v in values):
        return distribution
    if (any(v < -ROUNDING_TOLERANCE or v > 1 + ROUNDING_TOLERANCE for v in values)
            or abs(math.fsum(values) - 1) > ROUNDING_TOLERANCE):
        return distribution
    clipped = {key: min(1.0, max(0.0, value)) for key, value in distribution.items()}
    total = math.fsum(clipped.values())
    repaired = {key: value / total for key, value in clipped.items()}
    repairs.append({"path": path,
                    "max_absolute_change": max(abs(repaired[k] - distribution[k]) for k in repaired)})
    return repaired


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
    repairs = []
    probability = payload["t1_resume_probability"]
    if (not isinstance(probability, bool) and isinstance(probability, (int, float))
            and math.isfinite(probability) and not 0 <= probability <= 1
            and -ROUNDING_TOLERANCE <= probability <= 1 + ROUNDING_TOLERANCE):
        clipped = min(1.0, max(0.0, probability))
        repairs.append({"path": "p_resume", "max_absolute_change": abs(clipped - probability)})
        probability = clipped
    if (isinstance(probability, bool) or not isinstance(probability, (int, float))
            or not math.isfinite(probability) or not 0 <= probability <= 1):
        raise ValueError("A T1 probability must be finite and in [0,1]")
    conditional = copy.deepcopy(payload["t2_conditional_step_distribution"])
    if conditional is not None and (not isinstance(conditional, dict) or not conditional):
        raise ValueError("A conditional distribution must be a nonempty object or null")
    if probability == 0 and conditional is not None:
        raise ValueError("conditional recovery step is undefined when P(resume)=0")
    conditional = _repair_distribution(conditional, "conditional_step_probs", repairs)
    states = copy.deepcopy(payload["t3_state_distributions"])
    if isinstance(states, dict):
        states = {factor: _repair_distribution(dist, "state_probs." + factor, repairs)
                  for factor, dist in states.items()}
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
        "state_probs": states,
        "evidence_event_ids": list(dict.fromkeys(evidence)),
        "reason": "A T1/T2/T3 output; fixed threshold and conditional step argmax applied by C.",
        "metadata": {"adapter": "a-t123-to-c/1.1.0", "decision_threshold": threshold,
                     "a_cost": copy.deepcopy(payload["cost"]),
                     "a_uncertainty": copy.deepcopy(payload.get("uncertainty")),
                     "a_state_evidence": copy.deepcopy(payload.get("state_evidence")),
                     "a_evidence_trace": copy.deepcopy(trace),
                     "a_auxiliary_comprehension": copy.deepcopy(payload.get("auxiliary_comprehension_distributions")),
                     "a_t2_status": payload.get("t2_status"),
                     "verification_scope": "output_contract_only"}}
    if repairs:
        prediction["metadata"]["numerical_roundoff_repairs"] = {
            "tolerance": ROUNDING_TOLERANCE, "changes": repairs, "calibration": False}
    validate_prediction(prediction, observation)
    if conditional and label == "resume":
        prediction["resume_step"] = max(sorted(conditional), key=conditional.get)
    return prediction
