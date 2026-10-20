"""Runnable, deliberately distinct B0/B1/B4/B5/B6/B7 reference baselines.

Only ``observation`` reaches predict.  These are implementations of the project
baseline definitions, not reproductions of SET-PR, Memory for Goals or SIPS.
B6 fits logistic regression; B7 fits a four-state HMM using Baum-Welch with
optional *training-only* terminal C supervision.  Neither predicts before fit.
All operations use the Python standard library.

Semantic protocol: ``semantic.kind`` names an event. Notification content is
``semantic.value`` (e.g. cancellation), optionally ``interpretation='defer'``.
``semantic.reference_event_id`` can identify the notification's source event.
Interruption events may carry ``interrupting_goal_id`` and demand_level in [0,1].
Numeric time units are inherited from the dataset and must match across splits.
"""

from __future__ import annotations

import math
import random


VERSION = "local-baselines-1.0"
FACTORS = ("V", "F", "A", "B", "C", "Q")
UNKNOWN = {"V": "UNKNOWN", "F": "UNKNOWN", "A": "UNCERTAIN",
           "B": "UNKNOWN", "C": "UNKNOWN", "Q": "UNKNOWN"}


def _events(obs):
    """Reject future events even when this module is used without the validator."""
    events = list(obs.get("events", []))
    cutoff = obs["cutoff"]
    if any(event["time"] > cutoff for event in events):
        raise ValueError("future_event: event time exceeds prediction cutoff")
    return sorted(events, key=lambda event: event["time"])


def _semantic(event):
    value = event.get("semantic") or {}
    return value if isinstance(value, dict) else {}


def _kind(event):
    return _semantic(event).get("kind", event.get("event_type", "other"))


def _access(event):
    access = event.get("person_access_evidence") or {}
    status = str(access.get("status", "UNCERTAIN")).upper()
    if status not in ("ACCESSED", "NOT_ACCESSED", "UNCERTAIN"):
        status = "UNCERTAIN"
    return status, access.get("understood") is True


def _known(event, obs):
    status, understood = _access(event)
    own_action = event.get("actor") == obs["target_person"] and (
        event.get("event_type") == "task_action" or _kind(event) in {
            "goal_started", "goal_suspended", "goal_abandoned", "goal_completed",
            "commitment_resume", "step_completed", "interruption_started",
            "interruption_ended"})
    return own_action or (status == "ACCESSED" and understood)


def _nodes_edges(obs):
    graph = obs.get("task_graph")
    if graph:
        return list(graph.get("nodes", obs.get("task_steps", []))), list(graph.get("edges", []))
    nodes = list(obs.get("task_steps", []))
    return nodes, list(zip(nodes[:-1], nodes[1:]))


def _ancestors(obs, node):
    _, edges = _nodes_edges(obs)
    ancestors, frontier = set(), [node]
    while frontier:
        child = frontier.pop()
        for parent, descendant in edges:
            if descendant == child and parent not in ancestors:
                ancestors.add(parent)
                frontier.append(parent)
    ancestors.discard(node)
    return ancestors


def _candidates(obs, completed):
    nodes, edges = _nodes_edges(obs)
    return [node for node in nodes if node not in completed
            and all(parent in completed for parent, child in edges if child == node)]


def _step(obs, completed, preferred=None):
    candidates = _candidates(obs, completed)
    return preferred if preferred in candidates else (candidates[0] if candidates else None)


def _is_action(event):
    return event.get("event_type") == "task_action" or _kind(event) == "step_completed"


def _is_complete(event):
    return event.get("action_status") == "completed" or _kind(event) == "step_completed"


def _output(label, step, reason, evidence, *, p=None, states=None, metadata=None,
            conditional=None):
    return {"resume_label": label, "resume_step": step if label == "resume" else None,
            "p_resume": p, "conditional_step_probs": conditional,
            "state_probs": states or {}, "evidence_event_ids": list(dict.fromkeys(evidence)),
            "reason": reason, "metadata": metadata or {}}


def _point_states(summary, step):
    values = {factor: summary.get(factor, UNKNOWN[factor]) for factor in FACTORS}
    values["Q"] = step or ("NOT_APPLICABLE" if summary.get("C") in {
        "ABANDONED", "COMPLETED"} else "UNKNOWN")
    return {factor: {value: 1.0} for factor, value in values.items()}


class _Base:
    def __init__(self, seed=0):
        self.seed = seed
        self.training_samples = 0

    def fit(self, train_pairs):
        # Rule methods accept the common interface without reading the gold.
        self.training_samples = len(train_pairs)
        return self

    def _metadata(self, probability_kind="none", **extra):
        return {"model_version": VERSION, "seed": self.seed,
                "training_samples": self.training_samples,
                "probability_kind": probability_kind, **extra}

    def spec(self):
        return {"method_id": self.method_id, "model_version": VERSION,
                "implementation": type(self).__name__, "trainable": False,
                "probability_kind": "none", "strict_reproduction": False,
                "training_samples": self.training_samples, "fit_state": "rules_ready",
                "limitations": self.limitations}


class RecencyBaseline(_Base):
    """Latest own action and graph successor; optionally only five events."""

    def __init__(self, seed=0, window=None):
        super().__init__(seed)
        self.window = window
        self.method_id = "B1" if window == 5 else "B0"
        self.limitations = (
            "Latest-action heuristic; no cancellation, belief, or persistent-goal reasoning. "
            "Observed legal actions imply completed graph ancestors. "
            + ("B1 uses a fixed five-event window and is not SET-PR reproduction."
               if window else "B0 searches the complete available history for the latest action."))

    def predict(self, obs):
        events = _events(obs)
        if self.window:
            events = events[-self.window:]
        latest = next((event for event in reversed(events)
                       if event.get("actor") == obs["target_person"] and _is_action(event)), None)
        evidence, step = [], None
        if latest is None:
            reason = "No recognizable own task action in the retained history."
        elif latest.get("goal_id") != obs["goal_id"]:
            evidence = [latest["event_id"]]
            reason = "The most recent own task action belongs to another goal."
        else:
            evidence = [latest["event_id"]]
            observed_step = latest.get("step_id") or _semantic(latest).get("step_id")
            completed = _ancestors(obs, observed_step)
            if _is_complete(latest):
                completed.add(observed_step)
            step = _step(obs, completed, None if _is_complete(latest) else observed_step)
            reason = "Map the latest own action to an unfinished graph-legal step."
        return _output("resume" if step else "not_resume", step, reason, evidence,
                       metadata=self._metadata(history_window=self.window,
                                               limitations=self.limitations))


def _summary(obs, cognitive):
    """Persistent evidence rules, with an optional explicit accessibility gate."""
    summary = dict(UNKNOWN)
    summary.update(completed=set(), preferred=None, evidence=[], known_resource="UNKNOWN",
                   goals={}, interruptions=[])
    target = obs["goal_id"]
    for event in _events(obs):
        kind, semantic = _kind(event), _semantic(event)
        goal = event.get("goal_id")
        own = event.get("actor") == obs["target_person"]
        accepted = not cognitive or _known(event, obs)
        if own and accepted and goal:
            if kind == "goal_started":
                summary["goals"][goal] = "ACTIVE"
            elif kind == "goal_suspended":
                summary["goals"][goal] = "SUSPENDED"
            elif kind in ("goal_completed", "goal_abandoned"):
                summary["goals"][goal] = "COMPLETED" if kind == "goal_completed" else "ABANDONED"
            elif _is_action(event):
                summary["goals"][goal] = "ACTIVE"
        if kind == "interruption_started" and accepted:
            inserted = semantic.get("interrupting_goal_id")
            if inserted:
                summary["interruptions"].append(inserted)
        elif kind == "interruption_ended" and accepted:
            inserted = semantic.get("interrupting_goal_id")
            if inserted in summary["interruptions"]:
                summary["interruptions"].remove(inserted)
                summary["goals"][inserted] = "COMPLETED"
        if goal != target:
            continue
        summary["evidence"].append(event["event_id"])
        if kind in {"cancellation", "fulfillment", "goal_completed", "resource_blocked",
                    "resource_ready", "notification_understood"}:
            summary["A"] = _access(event)[0]
        effect = event.get("world_effect")
        if isinstance(effect, dict):
            if effect.get("V") in ("VALID", "CANCELLED", "FULFILLED", "UNKNOWN"):
                summary["V"] = effect["V"]
            if effect.get("F") in ("READY", "BLOCKED", "UNKNOWN"):
                summary["F"] = effect["F"]
        if kind == "goal_started":
            summary["V"] = "VALID"
        elif kind == "cancellation":
            summary["V"] = "CANCELLED"
        elif kind in ("fulfillment", "goal_completed"):
            summary["V"] = "FULFILLED"
        elif kind == "resource_blocked":
            summary["F"] = "BLOCKED"
        elif kind == "resource_ready":
            summary["F"] = "READY"
        # No person-state update is made from inaccessible objective facts in B5.
        if not accepted:
            # An explicitly recorded misreading can support suspension, not invalidity.
            if (_access(event)[0] == "ACCESSED"
                    and semantic.get("interpretation") == "defer"):
                summary["B"], summary["C"] = "UNRESOLVED", "SUSPENDED"
            continue
        content = semantic.get("value") if kind == "notification_understood" else kind
        if content == "cancellation":
            summary["B"], summary["C"] = "BELIEVES_INVALID", "ABANDONED"
        elif content in ("fulfillment", "goal_completed"):
            summary["B"], summary["C"] = "BELIEVES_INVALID", "COMPLETED"
        elif content == "resource_blocked":
            summary["known_resource"] = "BLOCKED"
        elif content == "resource_ready":
            summary["known_resource"] = "READY"
        if kind == "notification_understood" and semantic.get("belief") in {
                "BELIEVES_VALID", "BELIEVES_INVALID", "UNRESOLVED"}:
            summary["B"] = semantic["belief"]
        if kind == "goal_started":
            summary["B"], summary["C"] = "BELIEVES_VALID", "ACTIVE"
        elif kind in ("goal_suspended", "commitment_resume", "interruption_started"):
            summary["C"] = "SUSPENDED"
        elif kind == "goal_abandoned":
            summary["C"] = "ABANDONED"
        if _is_action(event):
            step = event.get("step_id") or semantic.get("step_id")
            if _is_complete(event):
                summary["completed"].add(step)
            else:
                summary["preferred"] = step
            if own:
                summary["C"] = "ACTIVE"
                if summary["B"] == "UNKNOWN":
                    summary["B"] = "BELIEVES_VALID"
    return summary


class PersistentMemoryBaseline(_Base):
    method_id = "B4"
    limitations = ("Persistent goal/progress memory copies observed world changes into its "
                   "decision without cognitive accessibility gating; this is its intended ablation.")

    def predict(self, obs):
        summary = _summary(obs, cognitive=False)
        step = _step(obs, summary["completed"], summary["preferred"])
        can_resume = (step is not None and summary["C"] not in {"ABANDONED", "COMPLETED"}
                      and summary["V"] not in {"CANCELLED", "FULFILLED"}
                      and summary["F"] != "BLOCKED" and summary["C"] != "UNKNOWN")
        return _output("resume" if can_resume else "not_resume", step,
                       "Persistent target-goal and completed-step memory; world facts are ungated.",
                       summary["evidence"], states=_point_states(summary, step),
                       metadata=self._metadata(limitations=self.limitations))


class BDIRuleBaseline(_Base):
    method_id = "B5"
    limitations = ("Evidence-gated BDI rules, not a learned joint cognitive model. "
                   "Predicts continuation from current known prerequisites, without modeling "
                   "future resource repair, deadlines, or stochastic decisions within the horizon.")

    def predict(self, obs):
        summary = _summary(obs, cognitive=True)
        step = _step(obs, summary["completed"], summary["preferred"])
        pending_other = any(goal != obs["goal_id"] and state == "ACTIVE"
                            for goal, state in summary["goals"].items())
        pending_other = pending_other or bool(summary["interruptions"])
        can_resume = (step is not None and summary["C"] in {"ACTIVE", "SUSPENDED"}
                      and summary["B"] != "BELIEVES_INVALID"
                      and summary["known_resource"] != "BLOCKED" and not pending_other)
        return _output("resume" if can_resume else "not_resume", step,
                       "BDI lifecycle and graph prerequisites from explicit person evidence.",
                       summary["evidence"], states=_point_states(summary, step),
                       metadata=self._metadata(limitations=self.limitations,
                                               pending_other_goal=pending_other))


def _sigmoid(value):
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-min(value, 700)))
    exp = math.exp(max(value, -700))
    return exp / (1.0 + exp)


def _eligible_resume_supervision(gold):
    label = gold.get("resume_label")
    return (label in {"resume", "not_resume"}
            and not (gold.get("dataset_layer") == "P1"
                     and gold.get("window_complete") is False and label == "not_resume"))


class ActivationLogisticBaseline(_Base):
    method_id = "B6"
    feature_names = ("recent_activation", "decayed_activation", "cue", "interruption_duration",
                     "interruption_demand", "progress_fraction", "log_horizon")
    limitations = ("Fitted logistic feature baseline inspired by activation, duration and demand; "
                   "not a reproduction of Memory for Goals. Dataset numeric time units must match. "
                   "No belief/commitment inference; step head uses ungated persistent progress.")

    def __init__(self, seed=0, epochs=350, learning_rate=0.12, regularization=0.01):
        super().__init__(seed)
        self.epochs, self.learning_rate, self.regularization = epochs, learning_rate, regularization
        self.weights = None

    def _features(self, obs):
        events = _events(obs)
        cutoff = float(obs["cutoff"])
        actions = [event for event in events if event.get("goal_id") == obs["goal_id"]
                   and event.get("actor") == obs["target_person"] and _is_action(event)]
        deltas = [max(0.0, cutoff - float(event["time"])) for event in actions]
        recent = 1.0 / (1.0 + min(deltas)) if deltas else 0.0
        activation = math.log1p(sum(math.exp(-min(delta, 700) / 10.0) for delta in deltas))
        interruptions = [event for event in events if _kind(event) == "interruption_started"]
        duration, demand = 0.0, 0.0
        if interruptions:
            start = interruptions[-1]
            ends = [event for event in events if _kind(event) == "interruption_ended"
                    and event["time"] >= start["time"]]
            end = ends[-1]["time"] if ends else cutoff
            duration = math.log1p(max(0.0, float(end) - float(start["time"])))
            semantic = _semantic(start)
            demand = float(semantic.get("demand_level", semantic.get("demand", 0.0)))
            demand = min(1.0, max(0.0, demand))
        cue = float(any(_kind(event) == "cue" and event.get("goal_id") == obs["goal_id"]
                        for event in events))
        summary = _summary(obs, cognitive=False)
        nodes, _ = _nodes_edges(obs)
        progress = len(set(nodes) & summary["completed"]) / max(1, len(nodes))
        horizon = math.log1p(max(0, obs.get("horizon", {}).get("value", 1)))
        return [recent, activation, cue, duration, demand, progress, horizon]

    def _standardize(self, row):
        return [1.0] + [(value - mean) / scale
                        for value, mean, scale in zip(row, self.means, self.scales)]

    def fit(self, train_pairs):
        examples = [(self._features(obs), int(gold.get("resume_label") == "resume"))
                    for obs, gold in train_pairs
                    if _eligible_resume_supervision(gold)]
        if not examples:
            raise ValueError("no_train_labels: B6 requires observed binary training labels")
        rows, labels = zip(*examples)
        count = len(rows)
        self.training_samples = count
        self.means = [sum(row[j] for row in rows) / count for j in range(len(rows[0]))]
        self.scales = [max(1e-6, math.sqrt(sum((row[j] - self.means[j]) ** 2
                                             for row in rows) / count))
                       for j in range(len(rows[0]))]
        rows = [self._standardize(row) for row in rows]
        weights = [0.0] * len(rows[0])
        for _ in range(self.epochs):
            gradient = [0.0] * len(weights)
            for row, label in zip(rows, labels):
                residual = _sigmoid(sum(w * x for w, x in zip(weights, row))) - label
                for j, value in enumerate(row):
                    gradient[j] += residual * value / count
            for j in range(len(weights)):
                penalty = self.regularization * weights[j] if j else 0.0
                weights[j] -= self.learning_rate * (gradient[j] + penalty)
        self.weights = weights
        return self

    def spec(self):
        return {**super().spec(), "trainable": True, "probability_kind": "fitted_logistic",
                "fit_state": "fitted" if self.weights is not None else "not_fitted",
                "features": list(self.feature_names), "epochs": self.epochs,
                "learning_rate": self.learning_rate, "regularization": self.regularization,
                "coefficients": list(self.weights) if self.weights is not None else None,
                "standardization_mean": getattr(self, "means", None),
                "standardization_scale": getattr(self, "scales", None)}

    def predict(self, obs):
        if self.weights is None:
            raise RuntimeError("not_fitted: B6.fit(training_pairs) must run before predict")
        row = self._standardize(self._features(obs))
        p = _sigmoid(sum(w * x for w, x in zip(self.weights, row)))
        summary = _summary(obs, cognitive=False)
        step = _step(obs, summary["completed"], summary["preferred"])
        raw_p = p
        p = p if step else 0.0
        return _output("resume" if p >= 0.5 else "not_resume", step,
                       "Train-fitted logistic activation/cue/duration/demand model.",
                       [event["event_id"] for event in _events(obs)], p=p,
                       metadata=self._metadata("fitted_logistic", limitations=self.limitations,
                                               graph_gate_applied=step is None,
                                               raw_p_resume=raw_p,
                                               coefficients=dict(zip(("intercept",) + self.feature_names,
                                                                     self.weights))),
                       conditional={step: 1.0} if step else None)


def _normalize(values):
    total = sum(values)
    return [value / total for value in values] if total else [1.0 / len(values)] * len(values)


class BayesianGoalHMMBaseline(_Base):
    """Finite goal-lifecycle HMM with forward-backward EM and terminal supervision."""

    method_id = "B7"
    states = ("ACTIVE", "SUSPENDED", "ABANDONED", "COMPLETED")
    limitations = ("Four lifecycle states for the nominated target goal; a real HMM with EM, "
                   "not SIPS/BToM reproduction or full joint cognition. It does not model planning, "
                   "continuous elapsed time or variable horizons; compare only matched horizons. "
                   "Step head uses ungated persistent progress; no learned step probabilities. "
                   "Semantic C probabilities are emitted only if all four states have nonempty "
                   "training evidence anchors; otherwise only a latent posterior is logged.")

    def __init__(self, seed=0, iterations=18, smoothing=0.25):
        super().__init__(seed)
        self.iterations, self.smoothing = iterations, smoothing
        self.initial = self.transition = self.emission = self.resume_rates = None
        self.anchor_counts = dict.fromkeys(self.states, 0)
        self.resume_training_samples = 0

    def _terminal_anchor(self, obs, gold):
        label = gold.get("state_labels", {}).get("C")
        evidence = gold.get("state_evidence", {}).get("C", [])
        ids = {event["event_id"] for event in _events(obs)}
        if (label in self.states and isinstance(evidence, list) and evidence
                and all(event_id in ids for event_id in evidence)):
            return self.states.index(label)
        return None

    def _symbols(self, obs):
        symbols = []
        for event in _events(obs):
            kind = _kind(event)
            if event.get("goal_id") != obs["goal_id"]:
                symbols.append("OTHER_TASK" if _is_action(event) else "OTHER_EVENT")
                continue
            if _is_action(event):
                kind = "step_completed" if _is_complete(event) else "task_action"
            if kind in {"cancellation", "fulfillment", "notification_understood"}:
                status, understood = _access(event)
                kind += ":" + status + (":understood" if understood else ":unresolved")
                if _kind(event) == "notification_understood":
                    kind += ":" + str(_semantic(event).get("value", "unknown"))
            symbols.append(kind)
        return symbols or ["NO_EVENTS"]

    def _indexes(self, obs):
        return [self.vocabulary.get(symbol, self.vocabulary["<UNK>"])
                for symbol in self._symbols(obs)]

    def _forward_backward(self, sequence, terminal=None):
        n = len(self.states)
        forward = [_normalize([self.initial[state] * self.emission[state][sequence[0]]
                               for state in range(n)])]
        for symbol in sequence[1:]:
            forward.append(_normalize([self.emission[state][symbol]
                                       * sum(forward[-1][previous] * self.transition[previous][state]
                                             for previous in range(n)) for state in range(n)]))
        backward = [[1.0] * n for _ in sequence]
        if terminal is not None:
            backward[-1] = [float(state == terminal) for state in range(n)]
        for index in range(len(sequence) - 2, -1, -1):
            backward[index] = _normalize([
                sum(self.transition[state][following] * self.emission[following][sequence[index + 1]]
                    * backward[index + 1][following] for following in range(n))
                for state in range(n)])
        posterior = [_normalize([a * b for a, b in zip(alpha, beta)])
                     for alpha, beta in zip(forward, backward)]
        return forward, backward, posterior

    def fit(self, train_pairs):
        examples = []
        for obs, gold in train_pairs:
            terminal = self._terminal_anchor(obs, gold)
            if terminal is not None or _eligible_resume_supervision(gold):
                examples.append((obs, gold))
        if not examples or not any(_eligible_resume_supervision(gold) for _, gold in examples):
            raise ValueError("no_train_labels: B7 needs at least one observed resume training label")
        self.training_samples = len(examples)
        self.resume_training_samples = sum(_eligible_resume_supervision(gold) for _, gold in examples)
        self.anchor_counts = dict.fromkeys(self.states, 0)
        alphabet = sorted({symbol for obs, _ in examples for symbol in self._symbols(obs)} | {"<UNK>"})
        self.vocabulary = {symbol: index for index, symbol in enumerate(alphabet)}
        n, m, alpha = len(self.states), len(alphabet), self.smoothing
        rng = random.Random(self.seed)
        self.initial = _normalize([1.0 + rng.random() * 0.05 for _ in range(n)])
        self.transition = [_normalize([3.0 if row == column else 0.6 + rng.random() * 0.05
                                       for column in range(n)]) for row in range(n)]
        self.emission = [_normalize([1.0 + rng.random() * 0.05 for _ in range(m)]) for _ in range(n)]
        sequences = [(self._indexes(obs), self._terminal_anchor(obs, gold), gold)
                     for obs, gold in examples]
        for _sequence, terminal, _gold in sequences:
            if terminal is not None:
                self.anchor_counts[self.states[terminal]] += 1
        for _ in range(self.iterations):
            initial_counts = [alpha] * n
            transition_counts = [[alpha] * n for _ in range(n)]
            emission_counts = [[alpha] * m for _ in range(n)]
            for sequence, terminal, _gold in sequences:
                forward, backward, posterior = self._forward_backward(sequence, terminal)
                for state in range(n):
                    initial_counts[state] += posterior[0][state]
                for index, symbol in enumerate(sequence):
                    for state in range(n):
                        emission_counts[state][symbol] += posterior[index][state]
                for index in range(len(sequence) - 1):
                    joint = [[forward[index][state] * self.transition[state][following]
                              * self.emission[following][sequence[index + 1]]
                              * backward[index + 1][following] for following in range(n)]
                             for state in range(n)]
                    normalizer = sum(sum(row) for row in joint)
                    for state in range(n):
                        for following in range(n):
                            transition_counts[state][following] += joint[state][following] / max(normalizer, 1e-300)
            self.initial = _normalize(initial_counts)
            self.transition = [_normalize(row) for row in transition_counts]
            self.emission = [_normalize(row) for row in emission_counts]
        successes, totals = [alpha] * n, [2 * alpha] * n
        # The resume head uses prediction-time posterior (no terminal-label input).
        for sequence, _terminal, gold in sequences:
            label = gold.get("resume_label")
            if not _eligible_resume_supervision(gold):
                continue
            posterior = self._forward_backward(sequence)[2][-1]
            for state, weight in enumerate(posterior):
                totals[state] += weight
                successes[state] += weight * int(label == "resume")
        self.resume_rates = [a / b for a, b in zip(successes, totals)]
        return self

    def spec(self):
        return {**super().spec(), "trainable": True, "probability_kind": "fitted_hmm",
                "fit_state": "fitted" if self.resume_rates is not None else "not_fitted",
                "states": list(self.states), "em_iterations": self.iterations,
                "dirichlet_smoothing": self.smoothing,
                "initial_state_probs": self.initial, "transition_matrix": self.transition,
                "event_vocabulary": getattr(self, "vocabulary", None),
                "emission_matrix": self.emission, "resume_rates": self.resume_rates,
                "terminal_training_supervision": "optional gold.state_labels.C with nonempty in-input state_evidence.C",
                "terminal_anchor_counts": dict(self.anchor_counts),
                "resume_training_samples": self.resume_training_samples,
                "semantic_state_probs_available": all(count > 0 for count in self.anchor_counts.values())}

    def predict(self, obs):
        if self.resume_rates is None:
            raise RuntimeError("not_fitted: B7.fit(training_pairs) must run before predict")
        posterior = self._forward_backward(self._indexes(obs))[2][-1]
        p = sum(weight * rate for weight, rate in zip(posterior, self.resume_rates))
        summary = _summary(obs, cognitive=False)
        step = _step(obs, summary["completed"], summary["preferred"])
        raw_p = p
        p = p if step else 0.0
        anchored = all(count > 0 for count in self.anchor_counts.values())
        return _output("resume" if p >= 0.5 else "not_resume", step,
                       "HMM forward posterior over target-goal lifecycle, with fitted resume head.",
                       [event["event_id"] for event in _events(obs)], p=p,
                       states={"C": dict(zip(self.states, posterior))} if anchored else {},
                       conditional={step: 1.0} if step else None,
                       metadata=self._metadata("fitted_hmm", limitations=self.limitations,
                                               graph_gate_applied=step is None,
                                               raw_p_resume=raw_p,
                                               latent_posterior=list(posterior),
                                               latent_resume_rates=list(self.resume_rates),
                                               semantic_state_probs_available=anchored,
                                               terminal_anchor_counts=dict(self.anchor_counts),
                                               resume_training_samples=self.resume_training_samples))


def make_local_baselines(seed=0):
    """The six executable, local methods; B6/B7 must be fitted on train only."""
    methods = [RecencyBaseline(seed), RecencyBaseline(seed, window=5),
               PersistentMemoryBaseline(seed), BDIRuleBaseline(seed),
               ActivationLogisticBaseline(seed), BayesianGoalHMMBaseline(seed)]
    return {method.method_id: method for method in methods}
