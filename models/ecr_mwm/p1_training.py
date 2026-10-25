"""P1-only EC-JMF training, dev selection, independent reload and ablations.

No P0 files, pretrained state weights or historical Git objects are read.
All model selections finish before the previously exposed test split is scored.
"""
import argparse
import gc
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import io
import json
from math import log
from pathlib import Path
import random
import sys
from time import perf_counter

import torch
from torch.nn import functional as F

from models.ec_jmf.neural_filter import LABELS, OFFSETS
from models.ecr_mwm.neural_data import build_vocabulary
from models.ecr_mwm.neural_metrics import aggregate, evaluate
from models.ecr_mwm.neural_model import Batch, NeuralECJMF
from models.ecr_mwm.p1_data import load_records

ROOT = Path(__file__).resolve().parents[2]
FORMAT = 'a-p1-ec-jmf/v1'
CONTRACT = 'p1-ec-jmf/v1'


def seed_everything(seed, threads=1):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)


def loss_terms(output, batch):
    # Supervision indices are compiled outside forward and never model input.
    if not hasattr(batch, '_supervision'):
        sr, sc, rr, ry, qr, qc = [], [], [], [], [], []
        for row, example in enumerate(batch.examples):
            target = example['target']
            for factor, label in target['states'].items():
                if factor != 'V':
                    raise ValueError('P1_STATE_SUPERVISION_MUST_BE_VALIDITY_ONLY')
                sr.append(row)
                sc.append(OFFSETS[factor][0] + LABELS[factor].index(label))
            if target['resume'] is not None:
                rr.append(row); ry.append(float(target['resume']))
            if target['step'] is not None:
                qr.append(row); qc.append(target['steps'].index(target['step']))
        batch._supervision = (torch.tensor(sr, dtype=torch.long), torch.tensor(sc, dtype=torch.long),
                              torch.tensor(rr, dtype=torch.long), torch.tensor(ry, dtype=torch.float32),
                              torch.tensor(qr, dtype=torch.long), torch.tensor(qc, dtype=torch.long))
    sr, sc, rr, ry, qr, qc = batch._supervision
    zero = output['p'].sum() * 0
    return {'state': -output['factors'][sr, sc].clamp_min(1e-8).log().mean() if len(sr) else zero,
            'state_count': len(sr),
            'resume': F.binary_cross_entropy(output['p'][rr].clamp(1e-7, 1-1e-7), ry) if len(rr) else zero,
            'resume_count': len(rr),
            'step': -output['q'][qr, qc].clamp_min(1e-8).log().mean() if len(qr) else zero,
            'step_count': len(qr),
            'consistency': output['consistency'], 'invariance': output['invariance']}


def training_loss(terms, config, variant):
    result = terms['state'] + terms['resume']
    if variant != 'A5':
        result = result + terms['step']
    if variant != 'A4':
        result = result + config['consistency_weight'] * (terms['consistency'] + terms['invariance'])
    return result


def make_batch(examples, variant, vocabulary):
    return Batch(examples, variant, semantic_contract=CONTRACT, vocabulary=vocabulary)


def grouped(examples):
    groups = defaultdict(list)
    for example in examples:
        groups[example['source'] + '/' + example['window_kind']].append(example)
    return dict(sorted(groups.items()))


def chunks(rows, size):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


@torch.no_grad()
def selection_loss(model, dev_batches):
    """Equal source/window groups, with task losses averaged by eligible rows."""
    model.eval()
    scores = []
    for batches in dev_batches.values():
        sums = Counter()
        counts = Counter()
        for batch in batches:
            terms = loss_terms(model(batch), batch)
            for name in ('state', 'resume', 'step'):
                count = terms[name + '_count']
                sums[name] += float(terms[name]) * count
                counts[name] += count
        if any(counts.values()):
            scores.append(sum(sums[name] / count for name, count in counts.items() if count))
    if not scores:
        raise ValueError('NO_DEV_SELECTION_TASKS')
    return sum(scores) / len(scores)


def checkpoint_bytes(model, config, words, seed, epoch):
    buffer = io.BytesIO()
    torch.save({'format': FORMAT,
                'architecture': {'variant': model.variant, 'hidden': config['hidden'],
                                 'semantic_contract': CONTRACT, 'vocabulary_size': len(words)},
                'vocabulary': words, 'config': config, 'seed': seed, 'selected_epoch': epoch,
                'state_dict': {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}}, buffer)
    return buffer.getvalue()


def reload_model(payload):
    checkpoint = torch.load(io.BytesIO(payload), map_location='cpu', weights_only=True)
    if checkpoint['format'] != FORMAT:
        raise ValueError('P1_ECJMF_CHECKPOINT_REQUIRED')
    model = NeuralECJMF(**checkpoint['architecture'])
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    model.eval()
    return model, checkpoint['vocabulary']


def prepare_batches(parts, words, variant, config):
    order = list(range(len(parts['train'])))
    random.Random(config['seed'] + 104729).shuffle(order)
    order.sort(key=lambda index: len(parts['train'][index]['input']['events']))
    train_batches=[]
    for number,indices in enumerate(chunks(order,config['batch_size']),1):
        train_batches.append(make_batch([parts['train'][index] for index in indices],variant,words))
        if number%25==0: print(f'Compiled {variant} train batches {number}',flush=True)
    dev_batches = {key: [make_batch(chunk, variant, words) for chunk in chunks(sorted(rows, key=lambda row: len(row['input']['events'])), config['batch_size'])]
                   for key, rows in grouped(parts['dev']).items()}
    return train_batches, dev_batches


def fit_one(parts, words, variant, seed, config, prepared=None):
    started = perf_counter()
    seed_everything(seed, config['threads'])
    model = NeuralECJMF(variant, hidden=config['hidden'], semantic_contract=CONTRACT,
                       vocabulary_size=len(words))
    train_batches, dev_batches = prepared if prepared is not None else prepare_batches(parts, words, variant, config)
    initial = selection_loss(model, dev_batches)
    best_loss, best_epoch, best_state = initial, 0, deepcopy(model.state_dict())
    optimizer = torch.optim.AdamW(model.parameters(), lr=config['learning_rate'],
                                 weight_decay=config['weight_decay'])
    # Fixed seed0 tie-shuffled length buckets are shared by variants/seeds; batch
    # order is paired across variants and independent of model initialization.
    order_rng = random.Random(seed + 104729)
    gradient_parameters = set()
    regularizer_batches = 0
    for epoch in range(1, config['epochs'] + 1):
        order = list(range(len(train_batches)))
        order_rng.shuffle(order)
        model.train()
        for batch_index in order:
            batch = train_batches[batch_index]
            optimizer.zero_grad(set_to_none=True)
            terms = loss_terms(model(batch), batch)
            objective = training_loss(terms, config, variant)
            if not torch.isfinite(objective):
                raise ValueError('NONFINITE_TRAINING_LOSS')
            objective.backward()
            if epoch == 1:
                gradient_parameters.update(name.split('.')[0] for name, parameter in model.named_parameters()
                                           if parameter.grad is not None and bool(parameter.grad.ne(0).any()))
                regularizer_batches += int(float(terms['consistency'].detach()) != 0)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config['gradient_clip'])
            optimizer.step()
        current = selection_loss(model, dev_batches)
        if current < best_loss:
            best_loss, best_epoch, best_state = current, epoch, deepcopy(model.state_dict())
        if epoch == 1 or epoch % 10 == 0 or epoch == config['epochs']:
            print(f'{variant} seed {seed} epoch {epoch}/{config["epochs"]} dev {current:.6f} elapsed {perf_counter()-started:.1f}s', flush=True)
    model.load_state_dict(best_state)
    model.eval()
    payload = checkpoint_bytes(model, config, words, seed, best_epoch)
    restored, restored_words = reload_model(payload)
    probe = next(iter(dev_batches.values()))[0]
    with torch.no_grad():
        before, after = model(probe), restored(probe)
        error = max(float((before[key] - after[key]).abs().max()) for key in ('p', 'q', 'factors'))
    if error != 0 or restored_words != words:
        raise ValueError('CHECKPOINT_RELOAD_MISMATCH')
    return payload, {'variant': variant, 'seed': seed, 'selected_epoch': best_epoch,
                     'epochs_executed': config['epochs'], 'initial_dev_loss': initial,
                     'dev_selection_loss': best_loss, 'reload_max_abs_error': error,
                     'parameter_count': sum(parameter.numel() for parameter in model.parameters()),
                     'nonzero_gradient_modules_first_epoch': sorted(gradient_parameters),
                     'training_selection_seconds': perf_counter()-started,
                     'nonzero_consistency_batches_first_epoch': regularizer_batches}


@torch.no_grad()
def prepare_evaluation_batches(examples, variant, words, batch_size):
    return {key: [(chunk, make_batch(chunk, variant, words))
                  for chunk in chunks(sorted(rows, key=lambda row: len(row['input']['events'])), batch_size)]
            for key, rows in grouped(examples).items()}


@torch.no_grad()
def evaluate_model(model, words, examples, batch_size, prepared=None):
    result = {}
    batches = prepared if prepared is not None else prepare_evaluation_batches(examples, model.variant, words, batch_size)
    for key, groups in batches.items():
        rows = [row for chunk, _ in groups for row in chunk]
        predictions = []
        for chunk, batch in groups:
            predictions.extend(model.predict(batch))
        metrics = evaluate(predictions, [row['target'] for row in rows])
        # Hidden B/F/A/C/Q distributions are diagnostics, not state gold.
        metrics['t3'] = {'V': metrics['t3']['V']}
        recovery = [(prediction['t1'], row['target']['resume'])
                    for prediction, row in zip(predictions, rows) if row['target']['resume'] is not None]
        metrics['t1']['bce'] = (sum(-log(max(1e-12, probability if label else 1-probability))
                                   for probability, label in recovery)/len(recovery) if recovery else None)
        metrics['t2']['zero_support'] = sum(
            (prediction['t2'] or {}).get(row['target']['step'], 0.0) <= 0
            for prediction, row in zip(predictions, rows) if row['target']['step'] is not None)
        metrics['groups'] = len({row['group'] for row in rows})
        metrics['rows'] = len(rows)
        metrics['resume_positive'] = sum(row['target']['resume'] is True for row in rows)
        metrics['resume_negative'] = sum(row['target']['resume'] is False for row in rows)
        metrics['label_origins'] = label_origin_counts(rows)
        metrics['t1']['positive_only'] = int(metrics['resume_positive'] > 0 and metrics['resume_negative'] == 0)
        result[key] = metrics
    return result


def label_origin_counts(rows):
    counts = Counter()
    for row in rows:
        eligible = list(row['target']['states'])
        if row['target']['resume'] is not None: eligible.append('resume')
        if row['target']['step'] is not None: eligible.append('resume_step')
        for task in eligible:
            origin = row['label_origin'].get(task)
            if origin:
                name = origin.get('origin', 'unspecified') if isinstance(origin, dict) else str(origin)
                counts[task + ':' + name] += 1
    return dict(counts)


def run(config_path, seed=None, validate=False, output_override=None):
    config = json.loads(Path(config_path).read_text(encoding='utf8'))
    if output_override is not None:
        config['output'] = str(output_override)
    if config['evaluation_seeds'] != list(range(20)) or config['variants'] != ['A0','A1','A2','A3','A4','A5','A6']:
        raise ValueError('FIXED_ABLATION_PROTOCOL_REQUIRED')
    examples = load_records(ROOT)
    parts = {split: [example for example in examples if example['split'] == split]
             for split in ('train', 'dev', 'test')}
    words = build_vocabulary(parts['train'], maximum=config['vocabulary_size'])
    seed_everything(config['seed'], config['threads'])
    counts = {split: {key: {'rows': len(rows),
                            'groups': len({row['group'] for row in rows}),
                            'resume': sum(row['target']['resume'] is not None for row in rows),
                            'step': sum(row['target']['step'] is not None for row in rows),
                            'V': sum('V' in row['target']['states'] for row in rows)}
                      for key, rows in grouped(values).items()}
              for split, values in parts.items()}
    if validate:
        print(json.dumps({'counts': counts, 'vocabulary_size': len(words)}, ensure_ascii=False, indent=2))
        for variant in config['variants']:
            model = NeuralECJMF(variant, hidden=config['hidden'], semantic_contract=CONTRACT, vocabulary_size=len(words))
            batch = make_batch(parts['train'][:config['batch_size']], variant, words)
            terms = loss_terms(model(batch), batch)
            training_loss(terms, config, variant).backward()
            print(variant, {key: float(value.detach()) for key, value in terms.items() if torch.is_tensor(value)})
        return
    output = ROOT / config['output']
    if output.exists():
        raise ValueError('OUTPUT_ALREADY_EXISTS')
    start = perf_counter()
    seeds = config['evaluation_seeds'] if seed is None else [seed]
    selected, runs = [], []
    for variant in config['variants']:
        print(f'Preparing {variant} train/dev topology',flush=True)
        prepared = prepare_batches(parts, words, variant, config)
        for current_seed in seeds:
            payload, metadata = fit_one(parts, words, variant, current_seed, config, prepared)
            selected.append(payload)
            runs.append(metadata)
            if variant == 'A0' and current_seed == seeds[0]:
                # This is the predeclared final representative after ALL its
                # training epochs and dev selection, not an epoch checkpoint.
                output.mkdir(parents=True)
                (output/'model.pt').write_bytes(payload)
                print('Saved predeclared final A0 model; full comparison remains pending:', output/'model.pt', flush=True)
            print(f'Selected {variant} seed {current_seed} epoch {metadata["selected_epoch"]}, elapsed {metadata["training_selection_seconds"]:.1f}s', flush=True)
        del prepared
        gc.collect()
    # No test model invocation before ALL requested train/dev selections above.
    test_batches = None
    previous_variant = None
    for payload, row in zip(selected, runs):
        model, vocabulary = reload_model(payload)
        if row['variant'] != previous_variant:
            test_batches = prepare_evaluation_batches(parts['test'], row['variant'], vocabulary, config['batch_size'])
            previous_variant = row['variant']
        row['test'] = evaluate_model(model, vocabulary, parts['test'], config['batch_size'], test_batches)
    by_variant = {variant: aggregate([row['test'] for row in runs if row['variant'] == variant])
                  for variant in config['variants']}
    representative = next(payload for payload, row in zip(selected, runs) if row['variant'] == 'A0' and row['seed'] == seeds[0])
    report = {'protocol': config['protocol'], 'config': config, 'counts': counts,
              'environment': {'python': sys.version, 'torch': str(torch.__version__), 'threads': config['threads'], 'device': 'cpu'},
              'vocabulary_size': len(words), 'runs': runs, 'test_cross_seed': by_variant,
              'test_previously_exposed': True, 'full_20_seed_protocol_completed': seed is None,
              'retained_variant': 'A0', 'retained_seed': seeds[0], 'seconds': perf_counter()-start,
              'model_sha256': hashlib.sha256(representative).hexdigest(),
              'batch_policy': config['batch_policy'],
              'data_files': {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
                             for path in ('data/p1/public_derived/processed/p1_combined.jsonl',
                                          'data/training_ready/v1/train.jsonl',
                                          'data/training_ready/v1/dev.jsonl',
                                          'data/training_ready/v1/test.jsonl')},
              'scope': 'P1 only: IH heuristic weak supervision; REBOOT positive-only recovery labels; InterruptBench V only. No human belief accuracy claim.'}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n', encoding='utf8')
    (output/'README.md').write_text(render_readme(report), encoding='utf8')
    print('Saved final model and report:', output, flush=True)


def render_readme(report):
    lines = ['# P1-only EC-JMF training and mechanism ablations', '',
             'All state parameters start randomly; no P0 data, weights or Git objects are read.',
             'IH is heuristic weak supervision. REBOOT recovery labels are positive-only; AUROC is undefined.',
             'InterruptBench supplies V only. Other latent-state distributions are not validated state truth.',
             'The test splits were previously exposed and are repeated evaluations, not new blind tests.', '',
             'Reproduce from the repository root:', '', '```powershell',
             'python -m models.ecr_mwm.p1_training --config configs/a_ec_jmf_p1.json',
             'python -m models.ecr_mwm.p1_training --predict "'+str(Path(report.get('config', {}).get('output', 'results/p1/ec_jmf'))/'model.pt')+'" --split test --source IHBench --limit 3',
             '```', '',
             'If the configured results directory already exists, reproduce into a new empty path with `--output results/p1/ec_jmf_reproduction`; existing outputs are never overwritten.',
             'The final representative model is saved immediately after its complete 40-epoch run and dev selection. Full comparison/report completion still requires all declared runs; model.pt alone does not mean the experiment finished.',
             'The seed field controls development checks; evaluation_seeds=0..19 controls the formal experiment.',
             'Fixed seed0 tie-shuffled event-length minibatch grouping is shared across variants and seeds; seed-specific shuffled minibatch order is paired across variants.',
             'All train/dev selections finish before test scoring. Retained checkpoint: A0, first declared seed, never chosen by test.',
             'Full 20-seed protocol completed: '+str(report['full_20_seed_protocol_completed'])+'.', '',
             '| Variant | Source/window | T1 Brier mean ± SD | T2 top1 mean ± SD | V accuracy mean ± SD |',
             '|---|---|---:|---:|---:|']
    def number(leaf):
        if leaf['mean'] is None:
            return 'undefined'
        return f"{leaf['mean']:.4f} ± {leaf['sample_sd']:.4f}" if leaf['sample_sd'] is not None else f"{leaf['mean']:.4f} (single seed)"
    for variant, metrics in report['test_cross_seed'].items():
        for key, group in metrics.items():
            lines.append('| '+ ' | '.join((variant,key,number(group['t1']['brier']),number(group['t2']['top1']),number(group['t3']['V']['accuracy'])))+' |')
    lines += ['', 'Complete per-seed metrics, denominators, zero-support counts, label origins and development selections are in report.json.',
              'T1 metrics measure source-window recovery labels; T2 is conditional step identification; V is labeled objective validity.',
              'Do not interpret these as real-person prediction, belief calibration, or unrestricted text understanding.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'configs/a_ec_jmf_p1.json')
    parser.add_argument('--output', type=Path, help='New output directory; existing directories are never overwritten')
    parser.add_argument('--seed', type=int, help='Development subset; omitted means all 20 formal seeds')
    parser.add_argument('--validate', action='store_true', help='In-memory data and gradient preflight; no outputs')
    parser.add_argument('--predict', type=Path)
    parser.add_argument('--split', choices=('train','dev','test'), default='test')
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--source', choices=('IHBench','REBOOT','InterruptBench'), help='Optional prediction source; InterruptBench has V only')
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.predict:
        model, vocabulary = reload_model(args.predict.read_bytes())
        examples = [example for example in load_records(ROOT) if example['split'] == args.split
                    and (args.source is None or example['source'] == args.source)][:args.limit]
        batch = make_batch(examples, model.variant, vocabulary)
        for example, prediction in zip(examples, model.predict(batch, evidence=True)):
            print(json.dumps({'id': example['id'], 'source': example['source'], 'window_kind': example['window_kind'],
                              'prediction': prediction, 'latent_state_validation': 'unavailable except labeled V'}, ensure_ascii=False, allow_nan=False))
    else:
        run(args.config, args.seed, args.validate, args.output)


if __name__ == '__main__':
    main()
