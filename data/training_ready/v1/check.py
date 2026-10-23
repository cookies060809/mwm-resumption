"""Verify hashes, group isolation, masks and exact reconstruction from source."""
import hashlib
import json
import tempfile
from pathlib import Path
import build

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    for name, sha in manifest['sources'].items():
        assert hashlib.sha256((ROOT / 'sources' / name).read_bytes()).hexdigest() == sha, name
    ids, group_split, totals = set(), {}, {}
    for split in ('train', 'dev', 'test'):
        path = ROOT / (split + '.jsonl')
        rows = [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()]
        sft = [json.loads(l) for l in (ROOT / (split + '_sft.jsonl')).read_text(encoding='utf-8').splitlines()]
        assert len(rows) == len(sft)
        for r, chat in zip(rows, sft):
            assert r['split'] == split and r['id'] not in ids
            ids.add(r['id'])
            assert group_split.setdefault(r['group_id'], split) == split
            assert chat == {'messages': r['messages']}
            assert r['messages'][-1]['role'] == 'assistant'
            if r['task'] == 'state_inference':
                assert set(r['input']) == {'goal_description', 'task_steps', 'task_dependencies', 'observed_events', 'cutoff_event_id'}
                assert r['input']['observed_events'][-1]['event_id'] == r['input']['cutoff_event_id']
                assert r['state_loss_mask'] == {f: int(f in r['target']) for f in build.FACTORS}
                if 'Q' in r['target']:
                    assert r['target']['Q'] in r['input']['task_steps'] + ['NOT_APPLICABLE']
                assert json.loads(r['messages'][-1]['content']) == r['target']
            else:
                assert r['task'] == 'interruption_response'
                assert not any(r['state_loss_mask'].values())
                assert r['input']['history'][-1]['role'] == 'user'
                assert r['messages'][-1]['content'] == r['target']
        totals[split] = len(rows)
    for name, item in manifest['files'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == item['sha256'], name
    # Rebuild to a temporary directory, proving exact transcript/cutoff selection
    # against pinned sources without overwriting the release being checked.
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        build.ROOT = Path(tmp)
        shutil.copytree(ROOT / 'sources', build.ROOT / 'sources')
        build.build()
        for name in list(manifest['files']) + ['manifest.json']:
            assert (ROOT / name).read_bytes() == (build.ROOT / name).read_bytes(), name
    print('PASS: source hashes, deterministic rebuild, grouped splits, cutoff histories, targets and masks', totals)


if __name__ == '__main__':
    main()
