"""Rebuild the frozen training release, offline, with Python standard library."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FACTORS = ('V', 'F', 'A', 'B', 'C', 'Q')
SYSTEM = 'Infer the supported V/F/A/B/C/Q states at the cutoff. Return a JSON object. Omit unsupported factors. Q must be a task step or NOT_APPLICABLE.'


def read(name):
    return json.loads((ROOT / 'sources' / name).read_text(encoding='utf-8'))


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def build():
    buckets = {s: [] for s in ('train', 'dev', 'test')}
    for r in read('p0.json'):
        inp = {k: r[k] for k in ('goal_description', 'task_steps', 'task_dependencies',
                                  'observed_events', 'cutoff_event_id')}
        target = {f: r['state_at_cutoff'][f] for f in FACTORS
                  if r['state_at_cutoff'][f] not in (None, 'UNKNOWN')}
        buckets[r['split']].append({
            'id': 'p0:' + r['sample_id'], 'task': 'state_inference',
            'group_id': 'p0:' + r['base_story_id'], 'split': r['split'],
            'source': 'project_P0_v0.3', 'label_origin': 'scripted_expectation',
            'input': inp, 'target': target,
            'state_loss_mask': {f: int(f in target) for f in FACTORS},
            'messages': [{'role': 'system', 'content': SYSTEM},
                         {'role': 'user', 'content': json.dumps(inp, ensure_ascii=False)},
                         {'role': 'assistant', 'content': json.dumps(target, ensure_ascii=False)}],
        })
    convs = {r['conversation_id']: r for r in read('conversations_text.json')}
    groups = sorted(convs, key=lambda x: hashlib.sha256(('ready-v1:' + x).encode()).digest())
    splits = {g: ('train' if i < 31 else 'dev' if i < 38 else 'test') for i, g in enumerate(groups)}
    assert len(groups) == 45, 'Unexpected upstream version; do not silently change the frozen split'
    seen = set()
    for b in read('baseline_text.json'):
        cid, t = b['conversation_id'], int(b['turn'])
        assert (cid, t) not in seen
        seen.add((cid, t))
        c = convs[cid]
        assert c[f'user_turn_{t}_interruption_type']
        history = []
        for k in range(1, t + 1):
            for role, field in [('assistant', 'assistant'), ('user', 'user')]:
                value = c.get(f'{field}_turn_{k}_transcript')
                assert isinstance(value, str) and value.strip()
                history.append({'role': role, 'content': value})
        # Only operating instructions and delivered history; never user_intent,
        # full pre-truncation utterances, future turns, rubrics or annotations.
        context = {'goal': c['goal'], 'knowledge_base': c['knowledge_base']}
        system = c['system_message'] + '\n\n' + json.dumps(context, ensure_ascii=False)
        target = b['response']
        assert isinstance(target, str) and target.strip()
        split = splits[cid]
        buckets[split].append({
            'id': f'ihbench:{cid}:{t}', 'task': 'interruption_response',
            'group_id': 'ihbench:' + cid, 'split': split,
            'source': 'IHBench', 'label_origin': 'released_GPT4o_Audio_baseline_response',
            'input': {'system': system, 'history': history}, 'target': target,
            'state_loss_mask': {f: 0 for f in FACTORS},
            'messages': [{'role': 'system', 'content': system}] + history +
                        [{'role': 'assistant', 'content': target}],
        })
    manifest = {'version': 'ready-v1.0', 'purpose': 'P0 state supervision and synthetic dialogue response distillation',
                'human_P1_records': 0, 'sources': {}, 'files': {}, 'groups': {}}
    for p in sorted((ROOT / 'sources').glob('*.json')):
        manifest['sources'][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    for split, rows in buckets.items():
        rows.sort(key=lambda r: r['id'])
        for suffix, values in [('', rows), ('_sft', [{'messages': r['messages']} for r in rows])]:
            path = ROOT / (split + suffix + '.jsonl')
            path.write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values),
                            encoding='utf-8', newline='\n')
            manifest['files'][path.name] = {'rows': len(rows), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest['groups'][split] = sorted({r['group_id'] for r in rows})
        manifest.setdefault('counts', {})[split] = dict(Counter(r['task'] for r in rows))
    write(ROOT / 'manifest.json', manifest)
    print(json.dumps(manifest['counts'], indent=2))


if __name__ == '__main__':
    build()
