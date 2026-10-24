"""B READY-v1.0 input contract, train-only vocabulary and masked state input.

Targets/messages and group identifiers are never consulted by model input encoding.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from models.ec_jmf.constraints import validate_graph
from models.ecr_mwm.p0_adapter import minutes

SPECIAL = ['<pad>', '<unk>', '<bos>', '<eos>', '<system>', '<user>', '<assistant>', '<sep>']


def tokens(text):
    return re.findall(r"\w+|[^\w\s]", text.casefold(), flags=re.UNICODE)


def source_tokens(inputs, policy):
    system = tokens(inputs['system'])
    head, tail = policy['system_head'], policy['system_tail']
    kept = system if len(system)<=head+tail else system[:head]+system[-tail:]
    messages=inputs['history']
    if not messages or messages[-1]['role']!='user':
        raise ValueError('RESPONSE_INPUT_MUST_END_AT_USER_INTERRUPTION')
    encoded=[]
    for message in messages:
        if message['role'] not in ('user','assistant'): raise ValueError('INVALID_HISTORY_ROLE')
        encoded.append(['<'+message['role']+'>']+tokens(message['content'])+['<sep>'])
    # Keep the latest interruption in full; truncate only older context, with roles.
    recent=list(encoded[-1]); remaining=max(0,policy['history_tail']-len(recent))
    for previous in reversed(encoded[:-1]):
        if remaining<3: break
        take=previous if len(previous)<=remaining else [previous[0]]+previous[-(remaining-1):]
        recent=take+recent; remaining-=len(take)
    history_count=sum(len(x) for x in encoded)
    return ['<system>']+kept+['<sep>']+recent, {
        'system_tokens':len(system),'system_kept':len(kept),
        'history_tokens':history_count,'history_kept':len(recent),
        'system_truncated':len(kept)<len(system),'history_truncated':len(recent)<history_count,
        'latest_user_tokens':len(encoded[-1]),'latest_user_kept':len(encoded[-1])}


def vocabulary(train_rows, policy, maximum):
    counts=Counter()
    for row in train_rows:
        if row['task']=='interruption_response':
            counts.update(source_tokens(row['input'],policy)[0])
            counts.update(tokens(row['target']))
    words=sorted((w for w in counts if w not in SPECIAL), key=lambda w:(-counts[w],w))
    return SPECIAL+words[:maximum-len(SPECIAL)]


def load_bundle(root):
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf8'))
    data={}; seen=set(); groups={}
    for split in ('train','dev','test'):
        path=root/(split+'.jsonl')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['files'][path.name]['sha256']:
            raise ValueError('READY_RELEASE_CHANGED')
        rows=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
        for row in rows:
            if row['id'] in seen or row['split']!=split: raise ValueError('READY_ID_OR_SPLIT_MISMATCH')
            seen.add(row['id'])
            if row['group_id'] in groups and groups[row['group_id']]!=split: raise ValueError('READY_GROUP_LEAK')
            groups[row['group_id']]=split
            if row['task']=='interruption_response':
                if set(row['input'])!={'system','history'} or any(row['state_loss_mask'].values()):
                    raise ValueError('RESPONSE_INPUT_OR_STATE_MASK_MISMATCH')
                if not isinstance(row['target'],str): raise ValueError('INVALID_RESPONSE_TARGET')
            elif row['task']=='state_inference':
                if row['state_loss_mask']!={f:int(f in row['target']) for f in 'VFABCQ'}:
                    raise ValueError('READY_STATE_MASK_MISMATCH')
            else: raise ValueError('UNKNOWN_READY_TASK')
        data[split]=rows
    return data


def state_input(inputs):
    """Canonicalize only supplied events; missing parents/graphs stay unknown.

    READY omits P0 horizon and full interrupting_task. H=1 is a computation-only
    placeholder for T3; the READY state API never exposes T1/T2.
    """
    events=inputs['observed_events']; steps=deepcopy(inputs['task_steps'])
    if not events or events[-1]['event_id']!=inputs['cutoff_event_id']: raise ValueError('READY_CUTOFF_NOT_LAST')
    candidates={e['goal_id'] for e in events if e['step_id'] in steps and e['goal_id'] is not None}
    if len(candidates)==1: goal=next(iter(candidates))
    elif not candidates:
        starts=[e['goal_id'] for e in events if e['event_type']=='goal_start' and e['goal_id']]
        if not starts: raise ValueError('READY_MAIN_GOAL_NOT_IDENTIFIABLE')
        goal=starts[0]
    else: raise ValueError('READY_AMBIGUOUS_MAIN_GOAL')
    dependencies={s:[] for s in steps}
    for edge in inputs['task_dependencies']: dependencies[edge['after']].append(edge['before'])
    validate_graph(steps,dependencies)
    graphs={goal:{'steps':steps,'dependencies':dependencies}}
    for event in events:
        child=event['goal_id']
        if child is not None and child!=goal:
            graph=graphs.setdefault(child,{'steps':[],'dependencies':None,'steps_complete':False})
            if event['step_id'] and event['step_id'] not in graph['steps']: graph['steps'].append(event['step_id'])
    mapped=[]; seen=set(); previous=-1
    for event in events:
        now=minutes(event['time'])
        if now<previous or event['event_id'] in seen: raise ValueError('READY_UNORDERED_OR_DUPLICATE_EVENT')
        previous=now;seen.add(event['event_id'])
        if event['goal_id'] and event['step_id'] and event['step_id'] not in graphs[event['goal_id']]['steps']:
            raise ValueError('READY_EVENT_STEP_UNKNOWN')
        own=event['actor']=='person'
        access=event['person_access']
        if own and access!='ACCESSED': raise ValueError('READY_SELF_ACCESS_MISMATCH')
        semantic={k:deepcopy(event['person_available_semantics'][k]) for k in ('kind','value','interpretation')
                  if k in event['person_available_semantics']}
        world={k:deepcopy(event[k]) for k in ('actor','event_type','goal_id','step_id','world_effect',
               'observer_evidence','person_access_evidence','source','certainty','description')}
        mapped.append({'event_id':event['event_id'],'time_minutes':now,'world':world,
                       'person':{k:deepcopy(event[k]) for k in ('event_type','goal_id','step_id','description')} if own else None,
                       'delivery':{'access_evidence':access,'comprehension':event['person_comprehension']},'semantic':semantic})
    return {'adapter_version':'a-ready-state/v1','schema_version':'ready-state-input/v1',
            'goal_id':goal,'horizon':{'type':'decision_opportunities','value':1},
            'cutoff_event_id':events[-1]['event_id'],'cutoff_minutes':previous,
            'observer_graphs':graphs,'events':mapped}
