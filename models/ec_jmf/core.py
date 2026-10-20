"""Finite joint filtering and bootstrap SMC with an identical model protocol.

States must be hashable. Model.transition(state, event) returns a normalized
finite distribution. Model.log_likelihood(state, event) counts evidence once.
No learned transition or human-behavior claim is supplied by this module.
"""
from dataclasses import dataclass
from math import exp, fsum, isfinite, log, log1p
from random import Random


def distribution(items):
    result = {}
    for state, probability in items:
        if not isfinite(probability) or probability < 0:
            raise ValueError("INVALID_PROBABILITY")
        if probability:
            result[state] = result.get(state, 0.0) + probability
    total = fsum(result.values())
    if not result or abs(total - 1.0) > 1e-10:
        raise ValueError("DISTRIBUTION_NOT_NORMALIZED")
    return {state: value / total for state, value in result.items()}


def normalize_logs(values):
    if any(v != v or v == float('inf') for v in values):
        raise ValueError("INVALID_LOG_LIKELIHOOD")
    highest = max(values, default=float('-inf'))
    if highest == float('-inf'):
        raise ValueError("ZERO_LIKELIHOOD")
    unscaled = [exp(value - highest) for value in values]
    total = fsum(unscaled)
    return tuple(value / total for value in unscaled)


def log_likelihood(model, state, event):
    value = model.log_likelihood(state, event)
    if value != value or value == float('inf'):
        raise ValueError("INVALID_LOG_LIKELIHOOD")
    return value


def log_add(a, b):
    if a == float('-inf'):
        return b
    if b == float('-inf'):
        return a
    high, low = max(a, b), min(a, b)
    return high + log1p(exp(low-high))


def positive_int(value):
    return type(value) is int and value >= 1


@dataclass(frozen=True)
class Posterior:
    states: tuple
    weights: tuple
    ess: float
    resampled: bool = False
    transition_evaluations: int = 0

    def marginal(self, projection=lambda state: state):
        result = {}
        for state, weight in zip(self.states, self.weights):
            key = projection(state)
            result[key] = result.get(key, 0.0) + weight
        return result


class ExactFilter:
    def __init__(self, max_states=10000, max_transitions=1000000):
        if not positive_int(max_states) or not positive_int(max_transitions):
            raise ValueError("INVALID_BUDGET")
        self.max_states, self.max_transitions = max_states, max_transitions

    def update(self, prior, model, event):
        prior = distribution(prior.items())
        if len(prior) > self.max_states:
            raise ValueError("STATE_BUDGET_EXCEEDED")
        propagated, evaluations = {}, 0
        for previous, weight in prior.items():
            branches = []
            for branch in model.transition(previous, event):
                evaluations += 1
                if evaluations > self.max_transitions:
                    raise ValueError("TRANSITION_BUDGET_EXCEEDED")
                branches.append(branch)
            for state, probability in distribution(branches).items():
                propagated[state] = log_add(propagated.get(state, float('-inf')),
                                            log(weight) + log(probability))
                if len(propagated) > self.max_states:
                    raise ValueError("STATE_BUDGET_EXCEEDED")
        states = tuple(propagated)
        weights = normalize_logs([propagated[s] + log_likelihood(model, s, event)
                                  for s in states])
        return Posterior(states, weights, 1 / fsum(w*w for w in weights),
                         transition_evaluations=evaluations)


def draw(rng, probabilities):
    threshold, cumulative = rng.random(), 0.0
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if threshold < cumulative:
            return index
    return len(probabilities) - 1


def systematic_indices(rng, weights):
    n = len(weights)
    start, index, cumulative = rng.random() / n, 0, weights[0]
    result = []
    for j in range(n):
        threshold = start + j / n
        while threshold >= cumulative and index < n - 1:
            index += 1
            cumulative += weights[index]
        result.append(index)
    return result


class ParticleFilter:
    def __init__(self, n=128, seed=0, ess_fraction=0.5, max_branches=10000):
        if not positive_int(n):
            raise ValueError("INVALID_PARTICLE_COUNT")
        if (type(ess_fraction) not in (int, float) or not isfinite(ess_fraction)
                or not 0 < ess_fraction <= 1 or not positive_int(max_branches)):
            raise ValueError("INVALID_PARTICLE_CONFIG")
        self.n, self.rng = n, Random(seed)
        self.ess_fraction, self.max_branches = ess_fraction, max_branches

    def initialize(self, prior):
        prior = distribution(prior.items())
        states, probabilities = tuple(prior), tuple(prior.values())
        return Posterior(tuple(states[draw(self.rng, probabilities)] for _ in range(self.n)),
                         (1 / self.n,) * self.n, float(self.n))

    def update(self, prior, model, event):
        if len(prior.states) != self.n or len(prior.weights) != self.n:
            raise ValueError("PARTICLE_COUNT_MISMATCH")
        # Validate weights without aggregating repeated particle states.
        distribution(enumerate(prior.weights))
        candidates, logs, evaluations = [], [], 0
        for state, weight in zip(prior.states, prior.weights):
            branches = []
            for branch in model.transition(state, event):
                if len(branches) >= self.max_branches:
                    raise ValueError("BRANCH_BUDGET_EXCEEDED")
                branches.append(branch)
                evaluations += 1
            branches = distribution(branches)
            keys, probabilities = tuple(branches), tuple(branches.values())
            new_state = keys[draw(self.rng, probabilities)]
            candidates.append(new_state)
            logs.append((log(weight) if weight else float('-inf'))
                        + log_likelihood(model, new_state, event))
        weights = normalize_logs(logs)
        ess = 1 / fsum(w*w for w in weights)
        resampled = ess < self.ess_fraction * self.n
        if resampled:
            candidates = [candidates[j] for j in systematic_indices(self.rng, weights)]
            weights = (1 / self.n,) * self.n
        # ESS is measured before resampling, to expose degeneracy.
        return Posterior(tuple(candidates), weights, ess, resampled, evaluations)


def conditional_prediction(posterior, head, horizon):
    """head(z,H) -> (P(resume|z,H), P(first step|resume,z,H))."""
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1:
        raise ValueError("INVALID_HORIZON")
    if len(posterior.states) != len(posterior.weights):
        raise ValueError("POSTERIOR_LENGTH_MISMATCH")
    distribution(enumerate(posterior.weights))
    mass, steps = [], {}
    for state, weight in zip(posterior.states, posterior.weights):
        resume, step_probs = head(state, horizon)
        if not isfinite(resume) or not 0 <= resume <= 1:
            raise ValueError("INVALID_RESUME_PROBABILITY")
        mass.append(weight * resume)
        if resume == 0:
            continue
        for step, probability in distribution(step_probs.items()).items():
            steps[step] = steps.get(step, 0.0) + weight * resume * probability
    probability = fsum(mass)
    return {"resume_probability": probability,
            "conditional_step_probs": ({k: v / probability for k, v in steps.items()}
                                       if probability else None),
            "step_status": "undefined_zero_resume" if probability == 0 else
                           "low_resume_mass" if probability < 1e-6 else "conditional"}
