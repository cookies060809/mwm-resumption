"""A-local prediction API; C owns the public update/MENTIS protocol mapping."""
from math import exp, expm1, log1p
from time import perf_counter

from models.ec_jmf.core import ExactFilter, ParticleFilter, Posterior, conditional_prediction
from models.ec_jmf.structured import StructuredModel, Mechanisms


class BehaviorHead:
    """Trainable discrete-opportunity hazard and future-step softmax.

    Q is a feature, not the T2 answer. Objective completion masks only future
    progress (research plan 3.4), never the person's current Q or belief.
    These initial coefficients are reference assumptions, not calibrated values.
    """
    def __init__(self, model, parameters=None):
        self.model = model
        self.parameters = {"bias": -1.0, "active": 0.5, "suspended": 0.0,
                           "abandoned": -1.0, "completed": -1.0,
                           "believes_valid": 0.5, "believes_invalid": -0.5,
                           "ready": 0.5, "blocked": -1.0, "nested": -1.0,
                           "waiting": -1.0, "remembered": 0.5,
                           "step_q": 1.0, "step_ready": 0.5,
                           "step_known": 0.0, "step_position": 0.0}
        if parameters:
            if set(parameters) - set(self.parameters):
                raise ValueError("UNKNOWN_HEAD_PARAMETER")
            self.parameters.update(parameters)

    def __call__(self, state, horizon):
        g = state.goal(self.model.target)
        graph = self.model.graphs[g.goal_id]
        candidates = [s for s in graph["steps"] if s not in g.world_done]
        if not candidates:
            return 0.0, {}
        feature = {"bias": 1, "active": g.commitment == "ACTIVE",
                   "suspended": g.commitment == "SUSPENDED",
                   "abandoned": g.commitment == "ABANDONED",
                   "completed": g.commitment == "COMPLETED",
                   "believes_valid": g.belief == "BELIEVES_VALID",
                   "believes_invalid": g.belief == "BELIEVES_INVALID",
                   "ready": g.feasibility == "READY", "blocked": g.feasibility == "BLOCKED",
                   "nested": bool(state.stack), "waiting": g.waiting,
                   "remembered": g.remembered}
        logit = sum(self.parameters[k]*v for k,v in feature.items())
        # log(1-hazard) = -softplus(logit), stable even at extreme logits.
        resume = -expm1(-horizon * (max(0.0, logit)+log1p(exp(-abs(logit)))))
        scores = {}
        for index, step in enumerate(graph["steps"]):
            if step not in candidates:
                continue
            ready = (graph["dependencies"] is not None and
                     set(graph["dependencies"].get(step, ())) <= g.world_done)
            scores[step] = (self.parameters["step_q"]*(step == g.q)
                            + self.parameters["step_ready"]*ready
                            + self.parameters["step_known"]*(step in g.known_steps)
                            + self.parameters["step_position"]*index/max(1,len(graph["steps"])-1))
        highest = max(scores.values())
        scores = {s:exp(v-highest) for s,v in scores.items()}
        total = sum(scores.values())
        return resume, {s:v/total for s,v in scores.items()}


def infer(adapted, *, transition_parameters=None, head_parameters=None,
          mechanisms=Mechanisms(), person_graphs=None, method="exact",
          seed=0, particles=128, recent_events=5, max_states=10000):
    """Already-adapted evidence only. Does not accept raw labels or write files.

    Returned posterior/model are internal Python objects for A training. The
    prediction object is JSON-compatible and has no sample identity or targets.
    A3 explicitly replays only the recent window; it is not full-model forgetting.
    """
    if type(recent_events) is not int or recent_events < 1:
        raise ValueError("INVALID_RECENT_WINDOW")
    start = perf_counter()
    model = StructuredModel(adapted, transition_parameters, mechanisms, person_graphs)
    events = adapted["events"]
    if not mechanisms.persistent_memory:
        events = events[-recent_events:]
    initial = model.initial()
    if method == "exact":
        engine = ExactFilter(max_states=max_states)
        posterior = Posterior((initial,), (1.0,), 1.0)
    elif method == "smc":
        engine = ParticleFilter(n=particles, seed=seed)
        posterior = engine.initialize({initial: 1.0})
    else:
        raise ValueError("UNKNOWN_INFERENCE_METHOD")
    trace = []
    evaluations = 0
    for event in events:
        before = {f:posterior.marginal(lambda s: s.goal(model.target).factor(f))
                  for f in "VFABCQ"}
        prior = dict(zip(posterior.states, posterior.weights)) if method == "exact" else posterior
        posterior = engine.update(prior, model, event)
        evaluations += posterior.transition_evaluations
        after = {f:posterior.marginal(lambda s: s.goal(model.target).factor(f))
                 for f in "VFABCQ"}
        trace.append({"event_id":event["event_id"], "time_minutes":event["time_minutes"],
                      "delivery":event["delivery"].copy(),
                      "person_semantic_used":event["delivery"]["access_evidence"] != "NOT_ACCESSED",
                      "state_before":before, "state_after":after,
                      "hypotheses":len(posterior.states), "ess":posterior.ess,
                      "resampled":posterior.resampled,
                      "action_evidence_role":"conditioned_transition_only"})
    head = BehaviorHead(model, head_parameters)
    pred = conditional_prediction(posterior, head, adapted["horizon"]["value"])
    t3 = {f:posterior.marginal(lambda s: s.goal(model.target).factor(f)) for f in "VFABCQ"}
    evidence = {f:sorted({event for state in posterior.states
                         for factor,event in state.goal(model.target).evidence if factor == f})
                for f in "VFABCQ"}
    comprehension = {}
    event_ids = {entry[0] for state in posterior.states
                 for g in state.goals for entry in g.understanding}
    for event_id in sorted(event_ids):
        comprehension[event_id] = posterior.marginal(
            lambda state: next((entry[2] for g in state.goals for entry in g.understanding
                                if entry[0] == event_id), "NOT_RECEIVED"))
    output = {"api_version":"a-structured/v0.2.0", "cutoff_event_id":adapted["cutoff_event_id"],
              "horizon":adapted["horizon"].copy(),
              "t1_resume_probability":pred["resume_probability"],
              "t2_conditional_step_distribution":pred["conditional_step_probs"],
              "t2_status":pred["step_status"], "t3_state_distributions":t3,
              "state_evidence":evidence, "evidence_trace":trace,
              "auxiliary_comprehension_distributions":comprehension,
              "uncertainty":{"calibrated":False, "hypotheses":len(posterior.states),
                             "access_scope":"latest salient event; C/B key-event mapping pending",
                             "person_graph_supplied":bool(person_graphs)},
              "cost":{"tokens":0,"latency_ms":(perf_counter()-start)*1000,
                      "transition_evaluations":evaluations,"compute":"cpu"}}
    return {"prediction":output, "posterior":posterior, "model":model}
