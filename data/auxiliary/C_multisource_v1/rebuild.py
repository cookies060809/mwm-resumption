"""Prepare source-separated auxiliary data and explicitly NEW controlled P0 augmentation.

No model-generated gold labels. No claim of a fully annotated real-human P1.
"""
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGED = ROOT.name == 'C_multisource_v1'
TOMI = ROOT / ('sources/tomi' if PACKAGED else 'aux_sources/tomi/existing_data/tomi_balanced_story_types')
CASAS = ROOT / ('sources/casas_proxy' if PACKAGED else 'c_training_proxy')
OUT = ROOT if PACKAGED else ROOT / 'C_multisource_v1'
FACTORS = ['V', 'F', 'A', 'B', 'C', 'Q']

def digest(x):
    return hashlib.sha256(x.encode('utf-8')).hexdigest()[:20]

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def parse_tomi(split, suffix):
    path = TOMI / f'fb_all_{suffix}.txt'
    traces = (TOMI / f'fb_all_{suffix}.trace').read_text().splitlines()
    history, records = [], []
    for raw in path.read_text().splitlines():
        n, text = raw.split(' ', 1)
        if n == '1':
            history = []
        if '\t' in text:
            question, answer, _ = text.split('\t')
            # Hash facts only: all questions about a story remain in the same group.
            story_key = digest('\n'.join(history))
            records.append({'story_key': story_key, 'story': list(history),
                'question': question, 'answer': answer, 'split': split,
                'source_file': path.name, 'trace': traces[len(records)]})
        else:
            history.append(text)
    assert len(records) == len(traces)
    return records

def access_label(story, person):
    """Deterministic ToMi room-co-presence rule for the LAST object-move event."""
    locations, last = {}, None
    for i, text in enumerate(story):
        m = re.fullmatch(r'(\w+) entered the (\w+)\.', text)
        if m:
            locations[m[1]] = m[2]
        m = re.fullmatch(r'(\w+) exited the (\w+)\.', text)
        if m:
            locations[m[1]] = None
        m = re.fullmatch(r'(\w+) moved the (\w+) to the (\w+)\.', text)
        if m:
            if person == m[1]:
                last = ('ACCESSED', i+1)
            elif m[1] in locations and person in locations and locations[m[1]]:
                last = ('ACCESSED' if locations[person] == locations[m[1]] else 'NOT_ACCESSED', i+1)
            else:
                last = None
    return last

def base_record(sample_id, group, split, role, input_value, source):
    return {'sample_id': sample_id, 'group_id': group, 'split': split,
        'data_role': role, 'input': input_value,
        'state_targets': {k: None for k in FACTORS},
        'state_loss_mask': {k: 0 for k in FACTORS},
        'state_evidence_event_ids': {}, 'auxiliary_targets': {},
        'provenance': source}

def tomi_record(r, i):
    events = [{'event_id': f'e{j+1}', 'time': j+1, 'text': text}
              for j, text in enumerate(r['story'])]
    record = base_record(f'tomi-{r["split"]}-{i}', r['story_key'], r['split'],
        'public_synthetic_auxiliary', {'events': events, 'cutoff_time': len(events),
        'question': r['question'], 'task_id': 'tomi_qa_with_optional_access'},
        {'source': 'https://github.com/facebookresearch/ToMi',
         'source_file': r['source_file'], 'trace': r['trace'],
         'label_kind': 'official_QA_plus_rule_derived_access',
         'is_real_human_behavior': False})
    record['auxiliary_targets']['tomi_answer'] = r['answer']
    # Location belief is deliberately NOT relabelled as BELIEVES_VALID/INVALID.
    match = re.fullmatch(r'Where will (\w+) look for the (\w+)\?', r['question'])
    if match:
        inferred = access_label(r['story'], match[1])
        if inferred:
            label, evidence = inferred
            record['input']['target_person'] = match[1]
            record['input']['key_event_id'] = f'e{evidence}'
            record['state_targets']['A'] = label
            record['state_loss_mask']['A'] = 1
            # Earlier room entry/exit events are required to establish access.
            record['state_evidence_event_ids']['A'] = [e['event_id'] for e in events[:evidence]]
    return record

POLICY = ('P0 scripted policy: maintain the current task while interrupted. On a correctly '
          'understood cancellation abandon it; on a correctly understood completion regard it '
          'as completed. Without such evidence retain the prior belief. Explicitly abandoning '
          'also ends commitment. A blocked resource prevents execution without ending commitment. '
          'Respect an explicitly stated decision to wait. Otherwise, after the interruption, '
          'attempt the first subjectively unfinished step.')

VARIANTS = [
    ('cancel_unseen', 'CANCELLED', 'READY', 'NOT_ACCESSED', 'normal', 1),
    ('cancel_seen', 'CANCELLED', 'READY', 'ACCESSED', 'normal', 1),
    ('fulfilled_unseen', 'FULFILLED', 'READY', 'NOT_ACCESSED', 'normal', 1),
    ('fulfilled_seen', 'FULFILLED', 'READY', 'ACCESSED', 'normal', 1),
    ('tool_blocked', 'VALID', 'BLOCKED', 'ACCESSED', 'normal', 1),
    ('tool_ready', 'VALID', 'READY', 'ACCESSED', 'normal', 1),
    ('explicit_keep', 'VALID', 'READY', 'ACCESSED', 'normal', 1),
    ('explicit_abandon', 'VALID', 'READY', 'ACCESSED', 'abandon', 1),
    ('progress_advanced', 'VALID', 'READY', 'ACCESSED', 'normal', 2),
    ('progress_not_advanced', 'VALID', 'READY', 'ACCESSED', 'normal', 1),
    ('cancel_misunderstood', 'CANCELLED', 'READY', 'ACCESSED', 'misunderstood', 1),
    ('cancel_access_uncertain', 'CANCELLED', 'READY', 'UNCERTAIN', 'uncertain', 1),
]

def p0_records(seed):
    # Existing public stories supply the participant names/background. All task events
    # and six-factor labels below are NEW deterministic controlled augmentation.
    names = re.findall(r'^(\w+) entered', '\n'.join(seed['story']), re.M)
    person = names[0] if names else 'Participant'
    family = 'aug-' + seed['story_key']
    steps = ['verify_record', 'write_record', 'submit_record']
    background = [{'event_id': f'bg{j+1}', 'time': j+1, 'text': t,
                   'source': 'public_ToMi_background'} for j, t in enumerate(seed['story'])]
    t0 = len(background)
    for variant, validity, feasible, access, mode, done in VARIANTS:
        events = list(background)
        def add(event_type, text, **extra):
            event = {'event_id': f'task{len(events)-len(background)+1}', 'time': len(events)+1,
                     'event_type': event_type, 'text': text, 'source': 'NEW_controlled_P0_augmentation', **extra}
            events.append(event)
            return event['event_id']
        start = add('goal_started', f'{person} begins preparing a new record: verify, write, then submit. '
                    'The task is valid and the required tools are ready. The person knows this.',
                    actor=person, goal_id=family)
        progress = add('progress_known', f'{person} has completed and checked steps {steps[:done]}; '
                       f'the next unfinished step known to the person is {steps[done]}.', actor=person)
        interrupted = add('interruption_started', f'{person} stops this task to answer an unrelated call '
                          'and explicitly says the original task will be continued later.', actor=person)
        if mode == 'abandon':
            abandon = add('explicit_abandon', f'{person} explicitly decides to abandon the original task.', actor=person)
        key = add('external_task_update', f'The task registry now has objective status {validity}; '
                  f'objective execution resources are {feasible}.',
                  world_effect={'V': validity, 'F': feasible},
                  person_access_evidence=access)
        understood = None
        if access == 'ACCESSED':
            if mode == 'misunderstood':
                text = f'{person} reads the cancellation notice but explicitly interprets it as '
                text += 'a temporary pause: the person still believes the goal valid and intends to wait.'
            else:
                text = f'{person} reads and correctly understands this task update.'
            understood = add('access_and_understanding', text, actor=person)
        elif access == 'NOT_ACCESSED':
            add('no_access_evidence', f'The update is only in a private backend; {person} has no access '
                'and receives no indirect cue.', actor='observer')
        else:
            add('uncertain_access', 'The log cannot establish whether the person saw or understood the update.', actor='observer')
        end = add('interruption_ended', f'{person} ends the unrelated call; predict before any subsequent action.', actor=person)
        belief, commitment, q = 'BELIEVES_VALID', 'SUSPENDED', steps[done]
        if mode == 'abandon':
            commitment, q = 'ABANDONED', 'NOT_APPLICABLE'
        if access == 'ACCESSED' and mode != 'misunderstood':
            if validity == 'CANCELLED':
                belief, commitment, q = 'BELIEVES_INVALID', 'ABANDONED', 'NOT_APPLICABLE'
            if validity == 'FULFILLED':
                # Match the project's P04-A convention: completion is represented by C;
                # a legitimately fulfilled goal is not treated as a cancellation belief.
                belief, commitment, q = 'BELIEVES_VALID', 'COMPLETED', 'NOT_APPLICABLE'
        targets = dict(V=validity, F=feasible, A=access, B=belief, C=commitment, Q=q)
        record = base_record(f'{family}-{variant}', family, seed['split'],
            'NEW_controlled_P0_augmentation', {'task_id': 'six_factor_state_and_scripted_behavior',
            'goal_id': family, 'target_person': person,
            'task_steps': steps, 'task_dependencies': [[steps[0], steps[1]], [steps[1], steps[2]]],
            'events': events, 'cutoff_time': events[-1]['time'], 'key_event_id': key,
            'scripted_policy': POLICY},
            {'source': 'NEW deterministic augmentation of public ToMi background',
             'upstream': 'https://github.com/facebookresearch/ToMi',
             'upstream_story_group': seed['story_key'], 'scenario': variant,
             'label_kind': 'scripted_simulation_NOT_human_gold',
             'is_real_human_behavior': False})
        record['state_targets'] = targets
        record['state_loss_mask'] = {k: 1 for k in FACTORS}
        record['state_evidence_event_ids'] = {
            'V': [key], 'F': [key], 'A': [key, events[-2]['event_id']],
            'B': [start, key] + ([understood] if understood else []),
            'C': [interrupted, key] + ([understood] if understood else []) + ([abandon] if mode == 'abandon' else []),
            'Q': [progress, key] + ([understood] if understood else []) + ([abandon] if mode == 'abandon' else [])}
        if mode == 'uncertain':
            for k in ('B', 'C', 'Q'):
                record['state_targets'][k] = None
                record['state_loss_mask'][k] = 0
                record['state_evidence_event_ids'].pop(k)
        else:
            if mode == 'misunderstood':
                record['auxiliary_targets']['p0_expected_action'] = 'wait_under_explicit_misreading_policy'
                record['auxiliary_targets']['p0_resume_within_3_opportunities'] = 0
            elif validity == 'FULFILLED' and access == 'NOT_ACCESSED':
                # Repeating a completed task is not necessarily resuming an unfinished step.
                record['auxiliary_targets']['p0_expected_action'] = 'attempt_redundant_step'
            else:
                resume = commitment == 'SUSPENDED' and feasible == 'READY'
                record['auxiliary_targets']['p0_resume_within_3_opportunities'] = int(resume)
                record['auxiliary_targets']['p0_expected_action'] = f'perform_{q}' if resume else 'do_not_advance_original_task'
                if resume:
                    record['auxiliary_targets']['p0_resume_step'] = q
        yield record
    # A prefix before interruption covers ACTIVE without future evidence.
    events = list(background) + [{'event_id': 'task1', 'time': t0+1,
        'event_type': 'goal_started', 'text': f'{person} begins verifying a new record. No step is yet complete. '
        'The person knows the goal valid, has the tools ready and is actively performing verify_record.',
        'source': 'NEW_controlled_P0_augmentation'}]
    r = base_record(f'{family}-active_prefix', family, seed['split'], 'NEW_controlled_P0_augmentation',
        {'task_id': 'six_factor_state_only', 'goal_id': family, 'target_person': person,
         'task_steps': steps, 'events': events, 'cutoff_time': t0+1, 'key_event_id': 'task1', 'scripted_policy': POLICY},
        {'source': 'NEW deterministic augmentation of public ToMi background',
         'upstream_story_group': seed['story_key'], 'scenario': 'active_prefix',
         'label_kind': 'scripted_simulation_NOT_human_gold', 'is_real_human_behavior': False})
    r['state_targets'] = dict(V='VALID', F='READY', A='ACCESSED', B='BELIEVES_VALID', C='ACTIVE', Q='verify_record')
    r['state_loss_mask'] = {k: 1 for k in FACTORS}
    r['state_evidence_event_ids'] = {k: ['task1'] for k in FACTORS}
    yield r

def casas_records(split):
    for raw in (CASAS / f'{split}.jsonl').read_text().splitlines():
        x = json.loads(raw)
        r = base_record(x['sample_id'], 'casas-'+x['input']['participant_id'], split,
            'real_human_activity_return_proxy', dict(x['input'], task_id='activity_return_60s_proxy'),
            dict(x['provenance'], is_real_human_behavior=True))
        r['auxiliary_targets']['activity_return_within_60s'] = x['labels']['activity_return']['60']['y']
        yield r

def main():
    OUT.mkdir(exist_ok=True)
    all_tomi = []
    for split, suffix in [('train', 'train'), ('dev', 'val'), ('test', 'test')]:
        all_tomi += parse_tomi(split, suffix)
    # Preserve official splits, but remove earlier-split content duplicated in held-out sets.
    owner = {}
    for split in ('train', 'dev', 'test'):
        for r in all_tomi:
            if r['split'] == split:
                owner[r['story_key']] = split
    kept = [r for r in all_tomi if owner[r['story_key']] == r['split']]
    sources = {'tomi_auxiliary': [tomi_record(r, i) for i, r in enumerate(kept)],
               'casas_real_proxy': [r for split in ('train', 'dev', 'test') for r in casas_records(split)]}
    seeds = {}
    for r in kept:
        seeds.setdefault((r['split'], r['story_key']), r)
    chosen = []
    for split, limit in [('train',72), ('dev',24), ('test',24)]:
        pool = sorted((v for (s, _), v in seeds.items() if s == split), key=lambda r:r['story_key'])
        assert len(pool) >= limit
        chosen.extend(pool[:limit])
    sources['p0_NEW_controlled_augmentation'] = [r for seed in chosen for r in p0_records(seed)]
    stats = {'format_version': '1.0', 'release_version': '1.0.1', 'complete_real_P1_six_factor_gold': False,
        'tomi_official_QA_before_cross_split_dedup': len(all_tomi),
        'tomi_QA_removed_cross_split_duplicate_story': len(all_tomi)-len(kept), 'sources': {}}
    all_ids = set()
    group_splits = {}
    for name, rows in sources.items():
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        source_stats = {}
        for split in ('train', 'dev', 'test'):
            subset = [r for r in rows if r['split'] == split]
            with (folder / f'{split}.jsonl').open('w', encoding='utf-8') as f:
                for r in subset:
                    assert r['sample_id'] not in all_ids
                    all_ids.add(r['sample_id'])
                    group = r['provenance'].get('upstream_story_group', r['group_id'])
                    assert group_splits.setdefault(group, split) == split
                    if r['input']['events'] and isinstance(r['input']['cutoff_time'], (int,float)):
                        assert all(e['time'] <= r['input']['cutoff_time'] for e in r['input']['events'])
                    event_ids = {e.get('event_id') for e in r['input']['events']}
                    for k in FACTORS:
                        assert bool(r['state_loss_mask'][k]) == (r['state_targets'][k] is not None)
                        if r['state_loss_mask'][k]:
                            assert set(r['state_evidence_event_ids'][k]) <= event_ids
                    f.write(json.dumps(r, ensure_ascii=False)+'\n')
            with (folder / f'{split}_sft.jsonl').open('w', encoding='utf-8') as f:
                for r in subset:
                    target = {'state': {k:v for k,v in r['state_targets'].items() if r['state_loss_mask'][k]},
                              'auxiliary': r['auxiliary_targets']}
                    f.write(json.dumps({'instruction': 'Complete the specified task using only input events. '
                        'Return the supervised state fields and/or auxiliary answer as JSON.',
                        'input': json.dumps(r['input'], ensure_ascii=False),
                        'output': json.dumps(target, ensure_ascii=False)}, ensure_ascii=False)+'\n')
            source_stats[split] = {'samples': len(subset), 'groups': len({r['group_id'] for r in subset}),
                'direct_state_supervision': {k:sum(r['state_loss_mask'][k] for r in subset) for k in FACTORS},
                'label_counts': {k:dict(Counter(r['state_targets'][k] for r in subset if r['state_loss_mask'][k])) for k in FACTORS}}
        stats['sources'][name] = source_stats
    licenses = OUT / 'licenses'
    licenses.mkdir(exist_ok=True)
    license_path = ROOT / ('sources/ToMi_LICENSE.txt' if PACKAGED else 'aux_sources/tomi/ToMi-master/LICENSE')
    shutil.copyfile(license_path, licenses/'ToMi_CC_BY_NC_4.txt')
    write_json(OUT/'stats.json', stats)
    write_json(OUT/'source_manifest.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(TOMI.glob('*'))})
    write_json(OUT/'state_label_map.json', {
        'V':['VALID','CANCELLED','FULFILLED','UNKNOWN'], 'F':['READY','BLOCKED','UNKNOWN'],
        'A':['ACCESSED','NOT_ACCESSED','UNCERTAIN'],
        'B':['BELIEVES_VALID','BELIEVES_INVALID','UNRESOLVED','UNKNOWN'],
        'C':['ACTIVE','SUSPENDED','ABANDONED','COMPLETED','UNKNOWN'],
        'Q':['verify_record','write_record','submit_record','NOT_APPLICABLE','UNKNOWN']})
    print(json.dumps({name:{s:{'samples':x['samples'],'masks':x['direct_state_supervision']} for s,x in v.items()}
        for name,v in stats['sources'].items()}, indent=2))

if __name__ == '__main__':
    main()
