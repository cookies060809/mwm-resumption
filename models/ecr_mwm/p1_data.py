"""Pure-P1 input/target separation and conversation-consistent split mapping.

The READY response rows supply ONLY the IHBench grouping. No state rows, P0
weights, future responses, annotations or target fields enter model inputs.
"""
import json
from pathlib import Path

from models.ecr_mwm.p1_adapter import adapt_native


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line.strip()]


def response_groups(root):
    groups = {}
    for split in ('train', 'dev', 'test'):
        for row in read_jsonl(Path(root) / 'data/training_ready/v1' / (split + '.jsonl')):
            if row['task'] != 'interruption_response':
                continue
            group = row['group_id'].removeprefix('ihbench:')
            if group in groups and groups[group] != split:
                raise ValueError('READY_CONVERSATION_SPLIT_CONFLICT')
            groups[group] = split
    return groups


def native_window(row):
    unit = row['observation_horizon']['unit']
    if row['source_dataset'] == 'IHBench':
        if unit not in ('single_response', 'assistant_turn'):
            raise ValueError('UNKNOWN_IHBENCH_WINDOW')
        planned = 1 if unit == 'single_response' else 4
    elif row['source_dataset'] == 'REBOOT':
        if unit != 'episode_tail': raise ValueError('UNKNOWN_REBOOT_WINDOW')
        planned = None  # A future episode-end frame count is not an input.
    else:
        if unit != 'not_observable': raise ValueError('UNKNOWN_SPEC_WINDOW')
        unit, planned = 'unobserved', None
    return {'kind': unit, 'planned': planned}


def load_records(root):
    root = Path(root)
    mapping = response_groups(root)
    rows = read_jsonl(root / 'data/p1/public_derived/processed/p1_combined.jsonl')
    examples, seen, groups = [], set(), {}
    for row in rows:
        identity = row['sample_id']
        if identity in seen: raise ValueError('P1_DUPLICATE_SAMPLE_ID')
        seen.add(identity)
        source, group = row['source_dataset'], row['split_group_id']
        if source == 'IHBench':
            if group not in mapping: raise ValueError('P1_MISSING_READY_CONVERSATION')
            split = mapping[group]
        else:
            split = 'dev' if row['split'] == 'val' else row['split']
        if split not in ('train', 'dev', 'test'): raise ValueError('P1_UNKNOWN_SPLIT')
        key = source, group
        if key in groups and groups[key] != split: raise ValueError('P1_GROUP_SPLIT_CONFLICT')
        groups[key] = split
        window = native_window(row)
        inputs = {k: row[k] for k in ('goal_text', 'task_steps', 'observed_events', 'cutoff_event_id')}
        adapted = adapt_native(inputs, window)
        resume = row['p1_observed_resume'] if row['resume_loss_mask'] == 1 else None
        if resume is not None and not isinstance(resume, bool):
            raise ValueError('P1_NON_BOOLEAN_RESUME')
        if resume is not None and (not row['eligible_for_resume_eval'] or row['p1_censoring_status'] == 'censored'):
            raise ValueError('P1_INVALID_RESUME_MASK')
        step = row['p1_resume_step'] if row['step_loss_mask'] == 1 and resume is True else None
        if step is not None and step not in row['task_steps']:
            raise ValueError('P1_INVALID_RESUME_STEP')
        # Withdrawn mental/state fields remain excluded even if stale masks exist.
        states = {}
        if row['state_loss_mask'].get('V') == 1:
            validity = row['state_at_cutoff']['V']
            if validity in ('VALID', 'CANCELLED', 'FULFILLED'):
                states['V'] = validity
        examples.append({'id': identity, 'split': split, 'source': source,
                         'window_kind': window['kind'], 'group': group,
                         'label_origin': row.get('label_origin', {}),
                         'input': adapted,
                         'target': {'resume': resume, 'step': step, 'states': states,
                                    'steps': list(row['task_steps'])}})
    return examples
