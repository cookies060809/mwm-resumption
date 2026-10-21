"""A's small-state reference training, losses and mechanism switches.

No CLI, artifacts, data rewrite, C protocol mapping, or SMC differentiation.
Central differences optimize the EXACT finite model, deliberately prioritizing
an inspectable numerical reference over scalable neural training. Parameters and
metrics are returned in memory. P0 is only scripted protocol supervision.
"""
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite, log
from random import Random

from models.ec_jmf.constraints import supervision_masks
from models.ec_jmf.structured import StructuredModel, Mechanisms
from models.ecr_mwm.p0_adapter import adapt_record, scripted_targets, person_inputs, SCHEMA_V02
from models.ecr_mwm.structured import infer, BehaviorHead


@dataclass
class TrainingExample:
    inputs: dict
    targets: dict
    layer: str
    split: str
    group: str  # audit metadata only, never sent to the model


def p0_example(record):
    if record["schema_version"] != SCHEMA_V02:
        raise ValueError("TRAINING_REQUIRES_P0_V02")
    if record["annotation"]["status"] not in ("reviewed", "adjudicated"):
        raise ValueError("UNREVIEWED_TRAINING_RECORD")
    inputs = adapt_record(record)
    scripted = scripted_targets(record)
    ids = {e["event_id"] for e in inputs["events"]}
    states = {}
    for factor in "VFABCQ":
        label = record["state_at_cutoff"][factor]
        evidence = record["state_evidence_by_factor"][factor]
        if not set(evidence) <= ids:
            raise ValueError("STATE_EVIDENCE_OUTSIDE_CUTOFF")
        # UNKNOWN is observer ignorance, not a supervised psychological class.
        # UNCERTAIN/UNRESOLVED may be evidenced labels and remain supervised.
        if label != "UNKNOWN" and evidence:
            states[factor] = label
    return TrainingExample(inputs, {"resume":scripted["p0_resume"],
                           "resume_mask":scripted["t1_mask"],
                           "step":scripted["t2_original_goal_step"],
                           "step_mask":scripted["t2_mask"], "states":states},
                           "P0", record["split"], record["base_story_id"])


def observed_targets(resume, window_complete, step=None, states=None):
    """P1-ready target masking only; B/C must still define the raw P1 mapping.

    states is an externally adjudicated, evidenced factor->label mapping.
    This function does not infer reliability from P0-style annotations.
    """
    masks = supervision_masks(resume, window_complete, step)
    return {"resume":resume, "resume_mask":masks["resume"], "step":step,
            "step_mask":masks["step"], "states":dict(states or {})}


def nll(probability):
    return -log(max(1e-12, probability))


def js(left, right):
    result = 0.0
    for key in set(left) | set(right):
        a,b = left.get(key,0.0),right.get(key,0.0)
        m = (a+b)/2
        if a:
            result += a*log(a/m)/2
        if b:
            result += b*log(b/m)/2
    return result


def mental_distribution(run):
    target = run["model"].target
    return run["posterior"].marginal(
        lambda s:(s.goal(target).belief,s.goal(target).commitment,s.goal(target).q))


def semantic_penalty(run):
    target, penalty = run["model"].target, 0.0
    for state,w in zip(run["posterior"].states,run["posterior"].weights):
        g = state.goal(target)
        conflict = (g.q in g.person_done or
                    (g.commitment in ("COMPLETED","ABANDONED") and g.q != "NOT_APPLICABLE"))
        penalty += w*conflict
    return penalty


def information_pair(left, right):
    """Caller must additionally attest equal mental priors/no hidden side cues.

    This checks the representable boundary, not real-world causal sufficiency.
    Goal identities/graphs must match, so unrelated tasks cannot become pairs.
    """
    return (left["goal_id"] == right["goal_id"] and
            left["observer_graphs"] == right["observer_graphs"] and
            person_inputs(left) == person_inputs(right))


def objective(examples, transition_parameters, head_parameters, *, mechanisms=Mechanisms(),
              invariant_pairs=(), knowledge_pairs=(), weights=None, stage="joint"):
    """Masked state/T1/T2 NLL + scoped mental JS + semantic conflict costs.

    Pair entries (i,j) are explicitly caller-certified controls; not inferred from
    mechanism, variant or labels. knowledge_pairs are hidden-world interventions
    with no new person cues; invariant_pairs are other certified equivalents.
    Stage 'state' fits endpoint-supported transitions, not fabricated per-event
    latent targets. Unsupported state labels incur constant floored NLL and are
    separately counted. Hard gate costs can be identically zero in A0.
    """
    if stage not in ("state", "joint"):
        raise ValueError("UNKNOWN_TRAINING_STAGE")
    if not examples:
        raise ValueError("EMPTY_TRAINING_BATCH")
    coefficients = {"state":1.0,"resume":1.0,"step":1.0,
                    "invariance":1.0,"knowledge":1.0,"semantic":0.1}
    if weights:
        if set(weights)-set(coefficients) or any(not isfinite(v) or v < 0 for v in weights.values()):
            raise ValueError("INVALID_LOSS_WEIGHTS")
        coefficients.update(weights)
    sums = {k:0.0 for k in coefficients}
    counts = {k:0 for k in coefficients}
    unsupported = 0
    runs = []
    for example in examples:
        run = infer(example.inputs, transition_parameters=transition_parameters,
                    head_parameters=head_parameters, mechanisms=mechanisms)
        runs.append(run)
        pred,t = run["prediction"],example.targets
        for factor,label in t["states"].items():
            probability = pred["t3_state_distributions"][factor].get(label,0.0)
            unsupported += probability == 0
            sums["state"] += nll(probability)
            counts["state"] += 1
        if stage == "joint" and t["resume_mask"]:
            p = pred["t1_resume_probability"]
            sums["resume"] += nll(p if t["resume"] else 1-p)
            counts["resume"] += 1
        if stage == "joint" and mechanisms.step_loss and t["step_mask"]:
            sums["step"] += nll((pred["t2_conditional_step_distribution"] or {}).get(t["step"],0))
            counts["step"] += 1
        if mechanisms.consistency_loss:
            sums["semantic"] += semantic_penalty(run)
            counts["semantic"] += 1
    if mechanisms.consistency_loss:
        for name,pairs in (("invariance",invariant_pairs),("knowledge",knowledge_pairs)):
            for i,j in pairs:
                if not information_pair(examples[i].inputs,examples[j].inputs):
                    raise ValueError("PAIR_NOT_INFORMATION_EQUIVALENT")
                sums[name] += js(mental_distribution(runs[i]),mental_distribution(runs[j]))
                counts[name] += 1
    terms = {k:sums[k]/max(1,counts[k]) for k in sums}
    return {"loss":sum(coefficients[k]*terms[k] for k in terms), "terms":terms,
            "counts":counts,"unsupported_state_targets":unsupported}


def fit(examples, *, epochs=1, learning_rate=0.05, seed=0, stage="joint",
        mechanisms=Mechanisms(), transition_parameters=None, head_parameters=None,
        invariant_pairs=(), knowledge_pairs=(), weights=None, difference_step=1e-4):
    """Full-batch, central-difference gradient descent on a small exact model.

    All data must be explicit train rows from one layer. No dev/test tuning,
    checkpoint file, calibration or results are performed. Training is slow
    (2 evaluations per scalar); this is NOT the planned scalable neural encoder.
    SMC remains inference-only. Repeated runs/evaluation belong to C.
    """
    if not examples or {x.layer for x in examples} not in ({"P0"},{"P1"}):
        raise ValueError("MIXED_OR_EMPTY_DATA_LAYERS")
    if any(x.split != "train" for x in examples):
        raise ValueError("NON_TRAIN_RECORD")
    if type(epochs) is not int or epochs < 1 or learning_rate <= 0 or difference_step <= 0:
        raise ValueError("INVALID_TRAINING_CONFIG")
    reference = StructuredModel(examples[0].inputs)
    transition = reference.parameters.copy()
    if transition_parameters:
        transition.update(transition_parameters)
    head = BehaviorHead(reference).parameters.copy()
    if head_parameters:
        head.update(head_parameters)
    coordinates = []
    if mechanisms.learned_gates:
        coordinates += [("transition",k) for k in transition]
    if stage == "joint":
        coordinates += [("head",k) for k in head if mechanisms.step_loss or not k.startswith("step_")]
    rng = Random(seed)
    history = []
    def loss():
        return objective(examples,transition,head,mechanisms=mechanisms,
                         invariant_pairs=invariant_pairs,knowledge_pairs=knowledge_pairs,
                         weights=weights,stage=stage)
    initial = loss()
    for _ in range(epochs):
        # Deterministic seeded coordinate order, simultaneous gradient step.
        rng.shuffle(coordinates)
        gradients = []
        for block,key in coordinates:
            params = transition if block == "transition" else head
            original = params[key]
            params[key] = original+difference_step
            plus = loss()["loss"]
            params[key] = original-difference_step
            minus = loss()["loss"]
            params[key] = original
            gradients.append((block,key,(plus-minus)/(2*difference_step)))
        if any(not isfinite(g) for _,_,g in gradients):
            raise ValueError("NONFINITE_GRADIENT")
        for block,key,gradient in gradients:
            params = transition if block == "transition" else head
            params[key] -= learning_rate*gradient
        history.append(loss())
    return {"format":"a-exact-reference-training/v0.2.0", "layer":examples[0].layer,
            "stage":stage,"seed":seed,"mechanisms":vars(mechanisms),
            "transition_parameters":deepcopy(transition),"head_parameters":deepcopy(head),
            "initial":initial,"history":history,
            "limitations":"Exact finite reference; no neural text encoder, SMC gradients or calibration."}
