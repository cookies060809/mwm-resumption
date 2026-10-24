"""Finite, evidence-constrained EC-JMF transition model (A internal API).

Structured semantics are inputs, never annotations or free-text keyword rules.
Branch weights are model assumptions until trained; UNKNOWN is an epistemic
placeholder, not a claim that the person is consciously undecided.
"""
from dataclasses import dataclass, replace
from math import exp

from models.ec_jmf.constraints import validate_graph


def sigmoid(value):
    return 1 / (1 + exp(-max(-40.0, min(40.0, value))))


def resolve_person_event_goal(event, graphs, target, semantic_contract):
    """Only explicit event targets identify a goal; retain null scope in traces.

    A single modeled goal does not prove an unlinked message refers to it.
    """
    goal = event['world']['goal_id']
    return goal if goal in graphs else None


@dataclass(frozen=True)
class Mechanisms:
    access_gate: bool = True
    comprehension_gate: bool = True
    joint_progress: bool = True
    persistent_memory: bool = True
    learned_gates: bool = True
    consistency_loss: bool = True
    step_loss: bool = True


@dataclass(frozen=True)
class GoalState:
    goal_id: str
    validity: str = "UNKNOWN"
    feasibility: str = "UNKNOWN"
    world_done: frozenset = frozenset()
    available: tuple = ()  # received (event_id, kind, value, interpretation)
    understanding: tuple = ()  # (event_id, observed_U, hypothesis_U)
    belief: str = "UNKNOWN"
    commitment: str = "UNKNOWN"
    person_done: frozenset = frozenset()
    known_steps: frozenset = frozenset()
    q: str = "UNKNOWN"
    remembered: bool = False
    waiting: bool = False
    access: str = "UNCERTAIN"
    access_event: str | None = None
    evidence: tuple = ()  # (factor, event_id), supporting current/historical updates

    def factor(self, factor):
        return {"V": self.validity, "F": self.feasibility, "A": self.access,
                "B": self.belief, "C": self.commitment, "Q": self.q}[factor]


@dataclass(frozen=True)
class JointState:
    goals: tuple
    stack: tuple = ()  # person-observed active nested tasks, not cutoff snapshots

    def goal(self, goal_id):
        return next(g for g in self.goals if g.goal_id == goal_id)


def changed(goal, event_id, **values):
    factors = {"validity": "V", "feasibility": "F", "belief": "B",
               "commitment": "C", "q": "Q", "access": "A"}
    evidence = list(goal.evidence)
    for key, value in values.items():
        if key in factors and value not in ("UNKNOWN", "UNCERTAIN"):
            entry = (factors[key], event_id)
            if entry not in evidence:
                evidence.append(entry)
    return replace(goal, evidence=tuple(evidence), **values)


class StructuredModel:
    """Conditional structured reference kernel shared by exact and SMC filters.

    Observed actions are conditioned on in transition; log_likelihood is zero:
    the same action is never multiplied in a second time. No text encoder yet.
    person_graphs must be separately evidenced knowledge, not observer metadata.
    """
    def __init__(self, adapted, parameters=None, mechanisms=Mechanisms(),
                 person_graphs=None, max_goals=8, max_depth=4, semantic_contract="legacy-v1"):
        if semantic_contract not in ("legacy-v1", "b-p0-v03/v2", "b-p0-v03/v3"):
            raise ValueError("UNKNOWN_SEMANTIC_CONTRACT")
        self.semantic_contract = semantic_contract
        self.graphs = adapted["observer_graphs"]
        self.target = adapted["goal_id"]
        self.mechanisms = mechanisms
        self.max_depth = max_depth
        if len(self.graphs) > max_goals:
            raise ValueError("GOAL_BUDGET_EXCEEDED")
        self.person_graphs = person_graphs or {}
        for goal, graph in self.person_graphs.items():
            if goal not in self.graphs:
                raise ValueError("UNKNOWN_PERSON_GRAPH")
            validate_graph(graph["steps"], graph["dependencies"])
            if not set(graph["steps"]) <= set(self.graphs[goal]["steps"]):
                raise ValueError("UNKNOWN_PERSON_STEP")
        # Logits, not empirically established human frequencies.
        self.parameters = {"access_uncertain": 0.0, "understanding_uncertain": 0.0,
                           "accept_message": 1.0, "invalid_abandon": 0.0,
                           "action_validity": 0.0, "world_uncertain": 0.0, "recall_next": 0.0}
        if self.semantic_contract == "b-p0-v03/v2":
            self.parameters["recommit_goal"] = 0.0
        elif self.semantic_contract == "b-p0-v03/v3":
            self.parameters["reengage_goal"] = 0.0
        if parameters:
            if set(parameters) - set(self.parameters):
                raise ValueError("UNKNOWN_TRANSITION_PARAMETER")
            self.parameters.update(parameters)

    def chance(self, name):
        if not self.mechanisms.learned_gates:
            return {"accept_message": 1.0, "action_validity": 0.5,
                    "invalid_abandon": 0.5}.get(name, 0.5)
        return sigmoid(self.parameters[name])

    def initial(self):
        goals = []
        for goal in self.graphs:
            known = frozenset(self.person_graphs.get(goal, {}).get("steps", ()))
            goals.append(GoalState(goal, known_steps=known))
        return JointState(tuple(goals))

    def progress(self, goal, event_id):
        if (self.mechanisms.joint_progress and
                goal.commitment in ("COMPLETED", "ABANDONED")):
            return [(changed(goal, event_id, q="NOT_APPLICABLE"), 1.0)]
        if goal.q in goal.known_steps - goal.person_done:
            return [(goal, 1.0)]
        graph = self.person_graphs.get(goal.goal_id)
        if graph:
            ready = [step for step in graph["steps"] if step not in goal.person_done
                     and set(graph["dependencies"].get(step, ())) <= goal.person_done]
            if ready:
                return [(changed(goal, event_id, q=step), 1 / len(ready)) for step in ready]
            if set(graph["steps"]) <= goal.person_done:
                return [(changed(goal, event_id, q="NOT_APPLICABLE",
                                 commitment="COMPLETED"), 1.0)]
        # A completed step does not prove the person knows the observer's successor.
        graph = self.graphs[goal.goal_id]
        if goal.remembered and graph["dependencies"] is not None and goal.person_done:
            candidates = [step for step in graph["steps"] if step not in goal.person_done
                          and set(graph["dependencies"].get(step, ())) <= goal.person_done]
            if candidates:
                # Observer graph proposes hypotheses about remembered successors;
                # it is NOT copied into the person's known graph. Keep UNKNOWN.
                p = self.chance("recall_next")
                return [(replace(goal, q=step, known_steps=goal.known_steps | {step}),
                         p/len(candidates)) for step in candidates] + [
                             (replace(goal, q="UNKNOWN"), 1-p)]
        return [(replace(goal, q="UNKNOWN"), 1.0)]

    def world_update(self, goal, event):
        world = event["world"]
        kind, step = world["event_type"], world["step_id"]
        values = {}
        if kind == "goal_start" and world["source"] != "person_report":
            values["validity"] = "VALID"
        elif kind == "task_cancelled" and world["source"] != "person_report":
            values["validity"] = "CANCELLED"
        elif kind == "task_completed_by_other" and world["source"] != "person_report":
            values.update(validity="FULFILLED", world_done=frozenset(self.graphs[goal.goal_id]["steps"]))
        elif kind == "step_completed" and step and world["source"] != "person_report":
            done = goal.world_done | {step}
            values["world_done"] = done
            if (self.graphs[goal.goal_id].get("steps_complete", True) and
                    set(self.graphs[goal.goal_id]["steps"]) <= done):
                values["validity"] = "FULFILLED"
        elif kind in ("resource_available", "resource_missing") and world["source"] != "person_report":
            values["feasibility"] = "READY" if kind == "resource_available" else "BLOCKED"
        # No inference F=READY merely from an earlier completed step.
        return changed(goal, event["event_id"], **values)

    def semantic_update(self, goal, event, understood):
        semantic, event_id = event["semantic"], event["event_id"]
        kind = semantic["kind"]
        interpretation = semantic.get("interpretation", "none")
        if not self.mechanisms.comprehension_gate:
            understood, interpretation = True, "accurate"
        if not understood or kind in ("none", "interruption", "nested_task_state"):
            return [(goal, 1.0)]
        values = {}
        if interpretation == "unresolved":
            values["belief"] = "UNRESOLVED"
        elif interpretation == "defer":
            values.update(belief="BELIEVES_VALID", waiting=True)
            if self.mechanisms.joint_progress:
                values["commitment"] = "SUSPENDED"
        elif interpretation == "complete" or kind == "completion_by_other":
            # B P0: confirmed fulfillment is distinct from cancellation.
            completed_belief = ("BELIEVES_VALID" if self.semantic_contract in ("b-p0-v03/v2", "b-p0-v03/v3")
                                and kind == "completion_by_other" else "BELIEVES_INVALID")
            values.update(belief=completed_belief,
                          person_done=frozenset(self.graphs[goal.goal_id]["steps"]),
                          known_steps=frozenset(self.graphs[goal.goal_id]["steps"]))
            if self.mechanisms.joint_progress:
                values["commitment"] = "COMPLETED"
        elif kind == "cancellation":
            values["belief"] = "BELIEVES_INVALID"
        elif kind == "commitment":
            phase = (goal.commitment if self.semantic_contract == "b-p0-v03/v3"
                     and goal.commitment in ("ACTIVE", "SUSPENDED") else "SUSPENDED")
            values.update(commitment=phase, waiting=False, remembered=True)
        elif kind == "abandonment":
            values["commitment"] = "ABANDONED"
        accepted = changed(goal, event_id, **values)
        if (accepted.belief == "BELIEVES_INVALID" and kind == "cancellation"
                and self.mechanisms.joint_progress):
            p = self.chance("invalid_abandon")
            outcomes = [(changed(accepted, event_id, commitment="ABANDONED"), p),
                        (accepted, 1-p)]
        elif (self.semantic_contract == "b-p0-v03/v3" and kind == "commitment"
              and goal.commitment not in ("ACTIVE", "SUSPENDED")):
            p = self.chance("reengage_goal")
            outcomes = [(changed(accepted, event_id, commitment="ACTIVE"), p), (accepted, 1-p)]
        else:
            outcomes = [(accepted, 1.0)]
        # Understanding is distinct from adopting the message as a belief.
        p = self.chance("accept_message")
        return [(g, w*p) for g,w in outcomes] + [(goal, 1-p)]

    def person_update(self, goal, event):
        event_id, own = event["event_id"], event["person"]
        if not own:
            return [(goal, 1.0)]
        kind, step = own["event_type"], own["step_id"]
        values = {"remembered": True}
        if kind == "goal_start":
            values["commitment"] = "ACTIVE"
        elif kind in ("step_started", "step_attempted", "step_completed"):
            values["known_steps"] = goal.known_steps | {step}
            if kind == "step_completed":
                values["person_done"] = goal.person_done | {step}
            else:
                values["q"] = step
            values["commitment"] = "ACTIVE"
        elif kind == "goal_abandoned":
            values["commitment"] = "ABANDONED"
        elif kind == "commitment_expressed":
            phase = (goal.commitment if self.semantic_contract == "b-p0-v03/v3"
                     and goal.commitment in ("ACTIVE", "SUSPENDED") else "SUSPENDED")
            values.update(commitment=phase, waiting=False)
        elif (self.semantic_contract == "b-p0-v03/v3" and kind == "interruption_started"
              and goal.commitment == "ACTIVE"):
            # Own physical interruption is evidence even when message U is N/A.
            values["commitment"] = "SUSPENDED"
        # Unparsed statements are evidence in the trace, never keyword rules.
        updated = changed(goal, event_id, **values)
        outcomes = [(updated, 1.0)]
        if (self.semantic_contract in ("b-p0-v03/v2", "b-p0-v03/v3") and
                kind in ("step_started", "step_attempted") and
                goal.commitment in ("ABANDONED", "COMPLETED")):
            # A local action is not certain renewed commitment to the whole goal.
            # Both interpretations remain possible; no label or story ID is read.
            p = self.chance("recommit_goal" if self.semantic_contract == "b-p0-v03/v2" else "reengage_goal")
            retained = changed(updated, event_id, commitment=goal.commitment, q="NOT_APPLICABLE")
            outcomes = [(retained, 1-p), (updated, p)]
        elif (self.semantic_contract == "b-p0-v03/v3" and kind == "commitment_expressed"
              and goal.commitment not in ("ACTIVE", "SUSPENDED")):
            p = self.chance("reengage_goal")
            outcomes = [(changed(updated, event_id, commitment="ACTIVE"), p), (updated, 1-p)]
        elif (self.semantic_contract == "b-p0-v03/v3" and kind in ("return_to_task", "person_action")
              and goal.commitment == "SUSPENDED" and not goal.waiting):
            # Returning/preparing can support activity; it does not prove it.
            p = self.chance("reengage_goal")
            outcomes = [(updated, 1-p), (changed(updated, event_id, commitment="ACTIVE"), p)]
        if kind in ("goal_start", "step_started", "step_attempted") and goal.belief == "UNKNOWN":
            p = self.chance("action_validity")
            return [(changed(state, event_id, belief="BELIEVES_VALID"), w*p)
                    for state,w in outcomes] + [(state,w*(1-p)) for state,w in outcomes]
        return outcomes

    def transition(self, state, event):
        goal_id = resolve_person_event_goal(event, self.graphs, self.target, self.semantic_contract)
        if goal_id not in self.graphs:
            return [(state, 1.0)]
        prior = state.goal(goal_id)
        world = self.world_update(prior, event)
        certainty = event["world"]["certainty"]
        pw = 1.0 if certainty == "CERTAIN" else self.chance("world_uncertain")
        world_branches = [(world, pw), (prior, 1-pw)] if world != prior else [(prior, 1.0)]
        access = event["delivery"]["access_evidence"]
        pa = (1.0 if access == "ACCESSED" else 0.0 if access == "NOT_ACCESSED"
              else self.chance("access_uncertain"))
        if not self.mechanisms.access_gate:
            pa = 1.0
        u = event["delivery"]["comprehension"]
        uncertain_u = u in ("UNCERTAIN", "not_structurally_labeled") or (
            access == "UNCERTAIN" and u == "NOT_APPLICABLE")
        pu = (1.0 if u in ("UNDERSTOOD", "MISUNDERSTOOD") else
              self.chance("understanding_uncertain") if uncertain_u else 0.0)
        semantic = event["semantic"]
        kind = semantic["kind"]
        # Salient access evidence is tracked separately from later unrelated returns.
        salient = kind in ("cancellation", "completion_by_other", "resource_available",
                            "resource_missing", "nested_task_state")
        if not salient and prior.access_event is None:
            salient = event["world"]["event_type"] in ("step_completed", "interruption_started")
        branches = []
        for g, pw in world_branches:
            if not pw:
                continue
            if salient:
                g = changed(g, event["event_id"], access=access, access_event=event["event_id"])
            for received, wa in ((False, 1-pa), (True, pa)):
                if not wa:
                    continue
                accessed = g
                if received and kind != "none":
                    item = (event["event_id"], kind, semantic.get("value"), semantic.get("interpretation"))
                    accessed = replace(g, available=g.available+(item,))
                if received and kind == "interruption" and event["world"]["event_type"] == "interruption_started":
                    if accessed.commitment == "ACTIVE":
                        accessed = changed(accessed, event["event_id"], commitment="SUSPENDED")
                meanings = []
                if received:
                    for understood, wu in ((False, 1-pu), (True, pu)):
                        if wu:
                            meaning = accessed
                            if kind not in ("none", "interruption", "nested_task_state"):
                                hypothesis = ("UNDERSTOOD" if understood else "NOT_UNDERSTOOD") if uncertain_u else u
                                meaning = replace(accessed, understanding=accessed.understanding+(
                                    (event["event_id"], u, hypothesis),))
                            meanings.extend((s, w*wu) for s,w in self.semantic_update(meaning, event, understood))
                else:
                    meanings = [(accessed, 1.0)]
                for meaning, wm in meanings:
                    for personal, wp in self.person_update(meaning, event):
                        needs_progress = (personal.person_done != prior.person_done or
                                          personal.commitment != prior.commitment or personal.q != prior.q)
                        progress = self.progress(personal, event["event_id"]) if needs_progress else [(personal, 1.0)]
                        for progressed, wq in progress:
                            stack = state.stack
                            parent = self.graphs[goal_id].get("parent_goal_id")
                            if parent and event["person"] and event["person"]["event_type"] in (
                                    "goal_start", "step_started", "step_completed", "step_attempted"):
                                if goal_id not in stack:
                                    stack += (goal_id,)
                                if len(stack) > self.max_depth:
                                    raise ValueError("INTERRUPTION_DEPTH_EXCEEDED")
                                if set(self.graphs[goal_id]["steps"]) <= progressed.person_done:
                                    stack = tuple(g for g in stack if g != goal_id)
                            goals = tuple(progressed if s.goal_id == goal_id else s for s in state.goals)
                            branches.append((JointState(goals, stack), pw*wa*wm*wp*wq))
        return branches

    @staticmethod
    def log_likelihood(state, event):
        return 0.0
