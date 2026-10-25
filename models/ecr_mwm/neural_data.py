"""P1-only, label-free world/person features and train-only text vocabulary.

Objective observations never become mental features. Event delivery and the
hypothesis's current understanding remain distinct from semantic acceptance.
"""
from collections import Counter
import re

MAX_STEPS = 12
SPECIAL = ('<pad>', '<unk>')
EVENT_TYPES = (
    'goal_start', 'goal_abandoned', 'step_started', 'step_completed',
    'step_attempted', 'interruption_started', 'interruption_ended',
    'return_to_task', 'person_action', 'person_statement', 'commitment_expressed',
    'task_cancelled', 'task_completed_by_other', 'notification_sent',
    'resource_available', 'resource_missing', 'task_completed',
)
SOURCES = ('direct_observation', 'person_report', 'third_party_report', 'notification',
           'backend_record', 'sensor_log', 'inference', 'other')
ACTORS = ('person', 'colleague', 'customer', 'manager', 'system', 'environment', 'other')
CERTAINTIES = ('CERTAIN', 'PROBABLE', 'UNCERTAIN')
SEMANTICS = ('none', 'cancellation', 'completion_by_other', 'resource_missing',
             'resource_available', 'commitment', 'abandonment', 'interruption', 'nested_task_state')
INTERPRETATIONS = ('none', 'accurate', 'defer', 'complete', 'unresolved')
COMPREHENSION = ('UNDERSTOOD', 'MISUNDERSTOOD', 'NOT_UNDERSTOOD', 'UNCERTAIN',
                 'NOT_APPLICABLE', 'not_structurally_labeled')
ACCESS = ('ACCESSED', 'NOT_ACCESSED', 'UNCERTAIN')
VALIDITY = ('VALID', 'CANCELLED', 'FULFILLED', 'UNKNOWN')
FEASIBILITY = ('READY', 'BLOCKED', 'UNKNOWN')
BELIEF = ('BELIEVES_VALID', 'BELIEVES_INVALID', 'UNRESOLVED', 'UNKNOWN')
COMMITMENT = ('ACTIVE', 'SUSPENDED', 'ABANDONED', 'COMPLETED', 'UNKNOWN')
CURRENT_UNDERSTANDING = ('UNDERSTOOD', 'MISUNDERSTOOD', 'NOT_UNDERSTOOD', 'UNKNOWN')
WORLD_DIM = len(EVENT_TYPES) + len(SOURCES) + len(CERTAINTIES) + len(ACTORS) + MAX_STEPS + 1 + 3
PERSON_DIM = (len(EVENT_TYPES) + MAX_STEPS + 1 + 3 + len(SEMANTICS) + len(INTERPRETATIONS)
              + len(COMPREHENSION) + len(ACCESS) + 3 + len(EVENT_TYPES))
MENTAL_DIM = len(BELIEF) + len(COMMITMENT) + MAX_STEPS + 2 + 5 + len(CURRENT_UNDERSTANDING) + 1
STATE_DIM = MENTAL_DIM + len(VALIDITY) + len(FEASIBILITY) + 1


def load_records(root):
    from models.ecr_mwm.p1_data import load_records as load_p1
    return load_p1(root)


def text_tokens(text):
    return re.findall(r"\w+|[^\w\s]", (text or '').casefold(), flags=re.UNICODE)


def build_vocabulary(examples, maximum=6000):
    if maximum < len(SPECIAL): raise ValueError('VOCABULARY_BUDGET_TOO_SMALL')
    counts = Counter()
    for example in examples:
        if example['split'] != 'train': continue
        inputs = example['input']
        counts.update(text_tokens(inputs.get('goal_text', '')))
        for graph in inputs['observer_graphs'].values():
            for step in graph['steps']: counts.update(text_tokens(step))
        for event in inputs['events']:
            counts.update(text_tokens(event['world'].get('description', '')))
            counts.update(text_tokens(event.get('available_text', '')))
            if event['person']:
                counts.update(text_tokens(event['person'].get('description', '')))
    words = sorted((word for word in counts if word not in SPECIAL),
                   key=lambda word: (-counts[word], word))
    return list(SPECIAL) + words[:maximum-len(SPECIAL)]


def _onehot(value, vocabulary):
    return [float(value == item) for item in vocabulary]


def _position(goal, step, graphs):
    steps = graphs[goal]['steps'] if goal in graphs else ()
    if len(steps) > MAX_STEPS: raise ValueError('NEURAL_STEP_BUDGET_EXCEEDED')
    return steps.index(step) if step in steps else MAX_STEPS


def _role(goal, target, graphs):
    return 0 if goal == target else 1 if goal in graphs else 2


def event_features(adapted, leak=False, semantic_contract='p1-ec-jmf/v1'):
    worlds, persons, visible = [], [], []
    graphs, target = adapted['observer_graphs'], adapted['goal_id']
    for event in adapted['events']:
        world, delivery, own = event['world'], event['delivery'], event['person']
        position = _position(world['goal_id'], world['step_id'], graphs)
        role = _role(world['goal_id'], target, graphs)
        worlds.append(_onehot(world['event_type'], EVENT_TYPES)
                      + _onehot(world['source'], SOURCES) + _onehot(world['certainty'], CERTAINTIES)
                      + _onehot(world['actor'], ACTORS) + _onehot(position, range(MAX_STEPS + 1))
                      + _onehot(role, range(3)))
        accessible = delivery['access_evidence'] != 'NOT_ACCESSED'
        available = bool(own) or (accessible and bool(event.get('available_text'))) or leak
        visible.append(available)
        if not available:
            persons.append([0.0] * PERSON_DIM)
            continue
        semantic = event['semantic'] if accessible or leak else {'kind': 'none'}
        has_semantic = semantic['kind'] != 'none'
        own_position = _position(own['goal_id'], own['step_id'], graphs) if own else MAX_STEPS
        person_role = (_role(own['goal_id'], target, graphs) if own else
                       role if has_semantic else 2)
        phase = 0
        if own and own['event_type'] in ('interruption_started', 'interruption_ended'):
            phase = 1 if own['event_type'] == 'interruption_started' else 2
        elif has_semantic and semantic['kind'] == 'interruption':
            phase = 1
        persons.append(_onehot(own['event_type'] if own else None, EVENT_TYPES)
                       + _onehot(own_position, range(MAX_STEPS + 1)) + _onehot(person_role, range(3))
                       + _onehot(semantic['kind'], SEMANTICS)
                       + _onehot(semantic.get('interpretation', 'none'), INTERPRETATIONS)
                       + _onehot(delivery['comprehension'], COMPREHENSION)
                       + _onehot(delivery['access_evidence'], ACCESS) + _onehot(phase, range(3))
                       + _onehot(world['event_type'] if leak else None, EVENT_TYPES))
    return worlds, persons, visible


def state_features(state, target, graphs, mental_only=False):
    goal = state.goal(target)
    steps = graphs[target]['steps']
    if len(steps) > MAX_STEPS: raise ValueError('NEURAL_STEP_BUDGET_EXCEEDED')
    q = steps.index(goal.q) if goal.q in steps else MAX_STEPS + 1 if goal.q == 'NOT_APPLICABLE' else MAX_STEPS
    denominator = max(1, len(steps))
    understanding = goal.understanding[-1][-1] if goal.understanding else 'UNKNOWN'
    if understanding not in CURRENT_UNDERSTANDING: understanding = 'UNKNOWN'
    mental = (_onehot(goal.belief, BELIEF) + _onehot(goal.commitment, COMMITMENT)
              + _onehot(q, range(MAX_STEPS + 2))
              + [float(goal.remembered), float(goal.waiting), len(goal.person_done)/denominator,
                 len(goal.known_steps)/denominator, len(state.stack)/4.0]
              + _onehot(understanding, CURRENT_UNDERSTANDING) + [float(bool(goal.available))])
    if mental_only: return mental
    return mental + _onehot(goal.validity, VALIDITY) + _onehot(goal.feasibility, FEASIBILITY) + [len(goal.world_done)/denominator]
