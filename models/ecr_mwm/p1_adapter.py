"""Input-only conservative P1 bridge for frozen structural-state probes.

This is not a P1 recovery-time adapter: no source horizon is converted to P0
opportunities, no text semantics are invented, and no supervision is inspected.
"""
from copy import deepcopy
from models.ec_jmf.constraints import validate_graph
from models.ecr_mwm.neural_data import MAX_STEPS

VERSION = 'a-p1-structural-probe/v1'


def adapt_input(inputs, probe_opportunities=1):
    steps = deepcopy(inputs['task_steps'])
    if not steps:
        raise ValueError('P1_NO_TASK_STEPS')
    if len(steps) > MAX_STEPS:
        raise ValueError('P1_STEP_BUDGET_EXCEEDED')
    validate_graph(steps, {})
    if probe_opportunities != 1:
        raise ValueError('FIXED_STRUCTURAL_PROBE_HORIZON_REQUIRED')
    raw_events = inputs['observed_events']
    if not raw_events:
        raise ValueError('P1_EMPTY_HISTORY')
    if len({e['event_id'] for e in raw_events}) != len(raw_events):
        raise ValueError('P1_DUPLICATE_EVENT_ID')
    goal, events = 'p1_goal', []
    for event in raw_events:
        step, kind, actor = event['step_id'], event['event_type'], event['actor']
        if step is not None and step not in steps:
            raise ValueError('P1_UNKNOWN_EVENT_STEP')
        if kind == 'completion':
            # The old vocabulary has completed steps / completion by OTHER, not an
            # observed own whole-goal completion. Do not fabricate completed steps.
            raise ValueError('P1_GOAL_COMPLETION_NOT_REPRESENTABLE')
        own = actor in ('assistant', 'robot')
        if kind == 'start_goal': mapped = 'goal_start'
        elif kind in ('progress', 'resume'): mapped = 'step_started' if own and step else 'person_action'
        elif kind == 'interruption': mapped = 'interruption_started'
        elif kind == 'background_fact': mapped = 'person_statement'
        else: raise ValueError('P1_UNKNOWN_EVENT_TYPE')
        # In IHBench the background access bit describes the USER, not assistant.
        # Keep every background fact out of the modeled actor's information path.
        access = ('NOT_ACCESSED' if kind == 'background_fact' else
                  'ACCESSED' if own else 'UNCERTAIN')
        world = {'actor': 'person' if own else 'environment' if actor in ('environment','workpiece') else 'other',
                 'event_type': mapped, 'goal_id': goal, 'step_id': step,
                 'world_effect': {}, 'observer_evidence': [], 'person_access_evidence': [],
                 'source': 'other', 'certainty': 'CERTAIN', 'description': ''}
        person = ({'event_type': mapped, 'goal_id': goal, 'step_id': step, 'description': ''}
                  if own and kind != 'background_fact' else None)
        events.append({'event_id': event['event_id'], 'time_minutes': None,
                       'source_position': deepcopy(event.get('position')), 'world': world,
                       'person': person,
                       'delivery': {'access_evidence': access,
                                    'comprehension': 'NOT_APPLICABLE' if own or kind=='background_fact' else 'UNCERTAIN'},
                       'semantic': {'kind': 'interruption' if kind=='interruption' else 'none'}})
    return {'adapter_version': VERSION, 'schema_version': 'p1-0.2', 'goal_id': goal,
            'horizon': {'type': 'decision_opportunities', 'value': probe_opportunities},
            'cutoff_event_id': raw_events[-1]['event_id'], 'cutoff_minutes': None,
            'observer_graphs': {goal: {'steps': steps, 'dependencies': None}}, 'events': events}
