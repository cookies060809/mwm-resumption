"""Data safety/semantics checks. Does not train or evaluate a model."""
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent
factors = ('V','F','A','B','C','Q')
label_map = json.loads((root/'state_label_map.json').read_text())
seen, groups, counts, p0, real_y = set(), {}, {}, {}, Counter()
for source in ('tomi_auxiliary','p0_NEW_controlled_augmentation','casas_real_proxy'):
    counts[source] = {}
    for split in ('train','dev','test'):
        rows = [json.loads(line) for line in (root/source/f'{split}.jsonl').read_text(encoding='utf-8').splitlines()]
        sft = [json.loads(line) for line in (root/source/f'{split}_sft.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(rows) == len(sft)
        counts[source][split] = len(rows)
        for r, export in zip(rows,sft):
            assert r['sample_id'] not in seen
            seen.add(r['sample_id'])
            g = r['provenance'].get('upstream_story_group',r['group_id'])
            assert groups.setdefault(g,split) == split
            assert json.loads(export['input']) == r['input']
            assert json.loads(export['output']) == {'state':{k:r['state_targets'][k] for k in factors if r['state_loss_mask'][k]},
                                                    'auxiliary':r['auxiliary_targets']}
            for key in ('state_targets','auxiliary_targets','provenance','sample_id'):
                assert key not in r['input']
            event_ids = {e.get('event_id') for e in r['input']['events']}
            for k in factors:
                mask, target = r['state_loss_mask'][k], r['state_targets'][k]
                assert (mask == 0 and target is None) or (mask == 1 and target in label_map[k])
                if mask:
                    assert r['state_evidence_event_ids'][k]
                    assert set(r['state_evidence_event_ids'][k]) <= event_ids
            assert all(e['time'] <= r['input']['cutoff_time'] for e in r['input']['events'])
            if source == 'tomi_auxiliary':
                assert all(r['state_loss_mask'][k] == 0 for k in ('V','F','B','C','Q'))
            elif source == 'casas_real_proxy':
                assert not any(r['state_loss_mask'].values())
                assert r['provenance']['is_real_human_behavior'] is True
                real_y[split,str(r['auxiliary_targets']['activity_return_within_60s'])] += 1
            else:
                assert r['provenance']['is_real_human_behavior'] is False
                p0.setdefault(r['group_id'],{})[r['provenance']['scenario']] = r

for family, variants in p0.items():
    state = lambda name:variants[name]['state_targets']
    assert state('cancel_unseen')['V'] == state('cancel_seen')['V'] == 'CANCELLED'
    assert state('cancel_unseen')['B'] == 'BELIEVES_VALID'
    assert state('cancel_seen')['B'] == 'BELIEVES_INVALID'
    assert state('tool_blocked')['V'] == 'VALID'
    assert state('tool_blocked')['C'] == 'SUSPENDED'
    assert state('tool_blocked')['F'] == 'BLOCKED'
    assert state('fulfilled_seen')['C'] == 'COMPLETED'
    assert state('fulfilled_seen')['B'] == 'BELIEVES_VALID'
    assert state('fulfilled_unseen')['C'] == 'SUSPENDED'
    assert state('progress_advanced')['Q'] == 'submit_record'
    assert state('progress_not_advanced')['Q'] == 'write_record'
    assert state('cancel_misunderstood')['A'] == 'ACCESSED'
    assert state('cancel_misunderstood')['B'] == 'BELIEVES_VALID'
    assert state('active_prefix')['C'] == 'ACTIVE'
    assert all(variants['cancel_access_uncertain']['state_loss_mask'][k] == 0 for k in ('B','C','Q'))

assert len(p0) == 120
assert all(real_y[s,'0'] and real_y[s,'1'] for s in ('train','dev','test'))
print(json.dumps({'validation':'PASS','counts':counts,'p0_seed_groups':len(p0),
                  'total_records':len(seen),'model_trained':False},indent=2))
