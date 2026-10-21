"""Build an explicitly limited activity-return proxy, NOT the plan's full P1."""
import csv
import hashlib
import json
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'casas' / 'raw' / 'adl_interweave'
OUT = ROOT / 'c_training_proxy'
SOURCE = 'https://zenodo.org/records/15713190'

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def build():
    OUT.mkdir(exist_ok=True)
    files = sorted(RAW.glob('*.interwoven.csv'))
    subjects = [f.name.split('.')[0] for f in files]
    rng = random.Random(42)
    rng.shuffle(subjects)
    split = {s: ('train' if i < 12 else 'dev' if i < 16 else 'test')
             for i, s in enumerate(subjects)}
    records = []
    qc = Counter()
    manifest = []
    for file in files:
        subject = file.name.split('.')[0]
        manifest.append({'file': file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
        rows = []
        with file.open(newline='', encoding='utf-8-sig') as stream:
            for line, raw in enumerate(csv.reader(stream), 1):
                qc['raw_events'] += 1
                time_text = raw[1]
                if ':' not in time_text:
                    time_text = time_text.replace('.', ':', 2)
                    qc['normalized_dot_separated_times'] += 1
                stamp = datetime.fromisoformat(raw[0] + 'T' + time_text)
                # Multiple activity columns denote overlapping/ambiguous events.
                labels = [x.strip() for x in raw[4:] if x.strip()]
                clean = len(labels) == 1 and labels[0] in set('12345678')
                if not clean:
                    qc['ambiguous_or_unlabelled_events'] += 1
                rows.append({'time': stamp, 'line': line, 'sensor': raw[2],
                             'value': raw[3], 'label': labels[0] if clean else None})
        rows.sort(key=lambda x: (x['time'], x['line']))
        # Do not infer an order between simultaneous events with conflicting labels.
        groups = {}
        for row in rows:
            groups.setdefault(row['time'], []).append(row)
        for batch in groups.values():
            labs = {r['label'] for r in batch}
            if None in labs or len(labs) != 1:
                for r in batch:
                    r['label'] = None
        for i in range(1, len(rows)):
            previous, current = rows[i-1], rows[i]
            if (previous['label'] is None or current['label'] is None
                    or current['label'] == previous['label']
                    or current['time'] == previous['time']):
                continue
            cutoff = current['time']
            target = previous['label']
            # Include all simultaneous events at cutoff; no future annotation is input.
            history = [r for r in rows[:i+1] if r['time'] <= cutoff][-64:]
            label_results = {}
            for horizon in (60, 180):
                future = [r for r in rows if 0 < (r['time']-cutoff).total_seconds() <= horizon]
                # Conservative exclusion: do not label windows with ambiguous activity assignments.
                ambiguous = any(r['label'] is None for r in future)
                returned = next((r for r in future if r['label'] == target), None)
                complete = (rows[-1]['time'] - cutoff).total_seconds() >= horizon
                status = ('excluded_ambiguous' if ambiguous else 'return' if returned
                          else 'no_return_within_window' if complete else 'censored')
                label_results[str(horizon)] = {'status': status,
                    'y': 1 if status == 'return' else 0 if status == 'no_return_within_window' else None,
                    'evidence_source_line': returned['line'] if returned and not ambiguous else None}
            sample_id = f'casas-{subject}-line{current["line"]}'
            records.append({'sample_id': sample_id, 'split': split[subject],
                'input': {'participant_id': subject, 'target_activity_id': target,
                    'cutoff_time': cutoff.isoformat(),
                    'past_activity_labels_are_oracle_annotations': True,
                    'events': [{'source_line': r['line'], 'time': r['time'].isoformat(),
                        'sensor': r['sensor'], 'value': r['value'],
                        'annotated_activity_id': r['label']} for r in history]},
                'labels': {'activity_return': label_results,
                    'p1_resume': None, 'p1_resume_step': None,
                    'V': 'UNKNOWN', 'F': 'UNKNOWN', 'A': 'UNCERTAIN',
                    'B': 'UNKNOWN', 'C': 'UNKNOWN', 'Q': 'UNKNOWN'},
                'provenance': {'source_url': SOURCE, 'source_file': file.name,
                    'label_type': 'deterministic_activity_return_proxy',
                    'task_completion_not_observed': True}})
    # Outcome-stratified GROUP split, fixed before fitting any model. Keep each person intact.
    positive_subjects = sorted({r['input']['participant_id'] for r in records
        if r['labels']['activity_return']['60']['y'] == 1})
    negative_subjects = sorted(set(subjects) - set(positive_subjects))
    rng = random.Random(42)
    rng.shuffle(positive_subjects)
    rng.shuffle(negative_subjects)
    split = {}
    for pool in (positive_subjects, negative_subjects):
        n_dev = max(1, round(len(pool) * .2))
        for i, s in enumerate(pool):
            split[s] = 'dev' if i < n_dev else 'test' if i < 2*n_dev else 'train'
    for r in records:
        r['split'] = split[r['input']['participant_id']]
    assert len({r['sample_id'] for r in records}) == len(records)
    for r in records:
        assert all(e['time'] <= r['input']['cutoff_time'] for e in r['input']['events'])
    stats = {'task': 'activity_return_proxy_NOT_full_P1', 'seed': 42,
        'source_files': len(files), 'subjects': len(subjects), 'qc': dict(qc),
        'split_method': 'fixed-seed subject-level split stratified by any positive 60s activity return',
        'switch_candidates': len(records), 'splits': {}}
    for name in ('train', 'dev', 'test'):
        candidates = [r for r in records if r['split'] == name]
        usable = [r for r in candidates if r['labels']['activity_return']['60']['y'] is not None]
        with (OUT / f'{name}.jsonl').open('w', encoding='utf-8') as f:
            for r in usable:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        stats['splits'][name] = {'subjects': sorted(s for s in subjects if split[s] == name),
            'usable_60s': len(usable),
            'positive_60s': sum(r['labels']['activity_return']['60']['y'] for r in usable),
            'statuses_60s': dict(Counter(r['labels']['activity_return']['60']['status'] for r in candidates))}
    with (OUT / 'all_candidates.jsonl').open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    dump(OUT / 'stats.json', stats)
    dump(OUT / 'source_manifest.json', manifest)
    print(json.dumps(stats, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    build()
