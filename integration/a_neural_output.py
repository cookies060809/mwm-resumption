"""Map A's neural outputs to C without exposing supervision to inference."""
from integration.a_output_adapter import normalize_a_output


def normalize_neural_output(prediction, observation):
    return normalize_a_output({
        "t1_resume_probability": prediction["t1"],
        "t2_conditional_step_distribution": prediction["t2"],
        "t3_state_distributions": prediction["t3"],
        "evidence_trace": prediction["evidence_trace"],
        "cost": {"tokens": 0, "latency_ms": None},
    }, observation, threshold=0.5)
