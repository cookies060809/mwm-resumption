"""Small train-only multinomial NB state baseline; no dependencies or GPU.

This checks a real fit/predict path. It is not EC-JMF and does not validate mental
state inference. Q predictions are restricted to the current task's steps.
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from build import FACTORS

ROOT = Path(__file__).resolve().parent


def load(split):
    return [r for r in map(json.loads, (ROOT / (split + '.jsonl')).read_text(encoding='utf-8').splitlines())
            if r['task'] == 'state_inference']


def tokens(row):
    text = json.dumps(row['input'], ensure_ascii=False).lower()
    return Counter(re.findall(r'[a-z_]+|[\u4e00-\u9fff]', text))


def main():
    train = load('train')
    models = {}
    for f in FACTORS:
        counts, words, vocab = Counter(), defaultdict(Counter), set()
        for r in train:
            if r['state_loss_mask'][f]:
                y, x = r['target'][f], tokens(r)
                counts[y] += 1
                words[y].update(x)
                vocab.update(x)
        assert counts, f
        models[f] = counts, words, len(vocab)
    report = {'model': 'train-only multinomial NB smoke baseline', 'train_rows': len(train), 'evaluation': {}}
    for split in ('dev', 'test'):
        report['evaluation'][split] = {}
        for f, (counts, words, n_vocab) in models.items():
            correct = n = 0
            for r in load(split):
                if not r['state_loss_mask'][f]:
                    continue
                candidates = list(counts) if f != 'Q' else r['input']['task_steps'] + ['NOT_APPLICABLE']
                def score(y):
                    freq = words.get(y, Counter())
                    denom = sum(freq.values()) + n_vocab
                    return math.log((counts[y] + 1) / (sum(counts.values()) + len(candidates))) + sum(
                        c * math.log((freq[w] + 1) / denom) for w, c in tokens(r).items())
                pred = max(candidates, key=score)
                correct += pred == r['target'][f]
                n += 1
            report['evaluation'][split][f] = {'correct': correct, 'n': n}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
