"""Train, select, save, reload and predict the complete context-residual EC-JMF.

Default training replays C's 40-epoch residual training on its frozen backbone.
No old model/checkpoint, central differences, C evaluator or API call is needed.
"""
import argparse
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter

import torch
from torch.nn import functional as F

from models.ec_jmf.neural_filter import LABELS, OFFSETS
from models.ecr_mwm.neural_model import Batch
from models.ecr_mwm.context_residual import ContextECJMF, FORMAT, initialize_context
from models.ecr_mwm.neural_data import load_records
from models.ecr_mwm.neural_metrics import evaluate, aggregate
from models.ecr_mwm.p0_adapter import adapt_record

ROOT = Path(__file__).resolve().parents[2]


def seed_everything(seed, threads=1):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)


def loss_terms(output,batch):
    # Compile supervision indices once; never expose them to the model forward.
    if not hasattr(batch,'loss_indices'):
        sr,sc,rr,ry,qr,qc=[],[],[],[],[],[]
        for row,example in enumerate(batch.examples):
            target=example['target']
            for factor,label in target['states'].items():
                if factor=='Q' and label in target['steps']: label=f"k{target['steps'].index(label)}"
                sr.append(row);sc.append(OFFSETS[factor][0]+LABELS[factor].index(label))
            if target['resume'] is not None: rr.append(row);ry.append(float(target['resume']))
            if target['step'] is not None: qr.append(row);qc.append(target['steps'].index(target['step']))
        batch.loss_indices=(torch.tensor(sr,dtype=torch.long),torch.tensor(sc,dtype=torch.long),
                            torch.tensor(rr,dtype=torch.long),torch.tensor(ry,dtype=torch.float32),
                            torch.tensor(qr,dtype=torch.long),torch.tensor(qc,dtype=torch.long))
    sr,sc,rr,ry,qr,qc=batch.loss_indices
    zero=output['p'].sum()*0
    return {'state':-output['factors'][sr,sc].clamp_min(1e-8).log().mean() if len(sr) else zero,
            'resume':F.binary_cross_entropy(output['p'][rr].clamp(1e-7,1-1e-7),ry) if len(rr) else zero,
            'step':-output['q'][qr,qc].clamp_min(1e-8).log().mean() if len(qr) else zero,
            'event_consistency':output['consistency'], 'invariance':output['invariance']}


def total_loss(terms, config, selection=False):
    value = terms['state'] + terms['resume'] + terms['step']
    if not selection:
        value = value + config['consistency_weight'] * (terms['event_consistency'] + terms['invariance'])
    return value


def checkpoint_bytes(model, config, seed, epoch, provenance=None):
    buffer = io.BytesIO()
    torch.save({'format': FORMAT, 'kind': 'visible_context',
                'architecture': model.architecture, 'seed': seed, 'selected_epoch': epoch,
                'config': config, 'provenance': provenance or {},
                'state_dict': {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}, buffer)
    return buffer.getvalue()


def read_checkpoint(payload):
    checkpoint = torch.load(io.BytesIO(payload), map_location='cpu', weights_only=True)
    if checkpoint['format'] != FORMAT or checkpoint['kind'] != 'visible_context':
        raise ValueError('CONTEXT_MODEL_CHECKPOINT_REQUIRED')
    return checkpoint


def reload_model(payload):
    checkpoint = read_checkpoint(payload)
    model = ContextECJMF(**checkpoint['architecture'])
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    model.eval()
    return model


def fit_one(train, dev, seed, config, source):
    model = initialize_context(source, seed)
    original = {k: v.detach().clone() for k, v in model.state_dict().items()}
    frozen = [name for name, p in model.named_parameters() if not p.requires_grad]
    model.eval()
    with torch.no_grad():
        initial = float(total_loss(loss_terms(model(dev), dev), config, selection=True))
    best_loss, best_epoch, best = initial, 0, deepcopy(model.state_dict())
    seed_everything(seed, config['threads'])
    parameters = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=config['learning_rate'], weight_decay=config['weight_decay'])
    for epoch in range(1, config['epochs'] + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        objective = total_loss(loss_terms(model(train), train), config)
        if not torch.isfinite(objective):
            raise ValueError('NONFINITE_TRAINING_LOSS')
        objective.backward()
        torch.nn.utils.clip_grad_norm_(parameters, config['gradient_clip'])
        optimizer.step()
        model.eval()
        with torch.no_grad():
            current = float(total_loss(loss_terms(model(dev), dev), config, selection=True))
        if current < best_loss:
            best_loss, best_epoch, best = current, epoch, deepcopy(model.state_dict())
    model.load_state_dict(best)
    model.eval()
    if any(not torch.equal(model.state_dict()[name], original[name]) for name in frozen):
        raise ValueError('FROZEN_BACKBONE_CHANGED')
    payload = checkpoint_bytes(model, config, seed, best_epoch, source['provenance'])
    restored = reload_model(payload)
    with torch.no_grad():
        before, after = model(dev), restored(dev)
        error = max(float((before[k] - after[k]).abs().max()) for k in ('p', 'q', 'factors'))
    if error != 0:
        raise ValueError('CHECKPOINT_RELOAD_MISMATCH')
    return payload, {'seed': seed, 'selected_epoch': best_epoch, 'epochs_executed': config['epochs'],
                     'initial_dev_loss': initial, 'dev_selection_loss': best_loss,
                     'reload_max_abs_error': error, 'frozen_parameters_unchanged': True,
                     'parameter_count': sum(p.numel() for p in model.parameters()),
                     'trainable_parameters': sum(p.numel() for p in parameters)}


def run(config_path, all_seeds=False, evaluate_test=False):
    config = json.loads(config_path.read_text(encoding='utf8'))
    if config['evaluation_seeds'] != list(range(20)):
        raise ValueError('FIXED_EVALUATION_SEEDS_REQUIRED')
    data = ROOT / config['data']
    if hashlib.sha256(data.read_bytes()).hexdigest() != config['expected_data_sha256']:
        raise ValueError('DATA_RELEASE_CHANGED')
    examples = load_records(data)
    parts = {s: [e for e in examples if e['split'] == s] for s in ('train', 'dev', 'test')}
    if {s: len(rows) for s, rows in parts.items()} != config['expected_counts']:
        raise ValueError('DATA_SPLIT_COUNTS_CHANGED')
    output = ROOT / config['output']
    if output.exists():
        raise ValueError('OUTPUT_ALREADY_EXISTS: choose a new output directory')
    source_path = ROOT / config['checkpoint']
    source = read_checkpoint(source_path.read_bytes())
    if config['architecture'] != source['architecture']:
        raise ValueError('ARCHITECTURE_MISMATCH: config must match the complete checkpoint')
    seed_everything(config['seed'], config['threads'])
    train, dev = (Batch(parts[s]) for s in ('train', 'dev'))
    seeds = config['evaluation_seeds'] if all_seeds else [config['seed']]
    selected, rows = [], []
    start = perf_counter()
    for seed in seeds:
        payload, metadata = fit_one(train, dev, seed, config, source)
        selected.append(payload)
        rows.append(metadata)
        print(f"Selected context seed {seed}, epoch {metadata['selected_epoch']}", flush=True)
    # No test model call occurs until all requested train/dev selections finish.
    if evaluate_test:
        batch = Batch(parts['test'])
        for payload, row in zip(selected, rows):
            row['test'] = evaluate(reload_model(payload).predict(batch), [e['target'] for e in batch.examples])
    code = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = {'protocol': config['protocol'], 'config': config, 'code_commit': code,
              'working_tree_dirty': bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
              'source_checkpoint_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
              'data_sha256': config['expected_data_sha256'], 'counts': config['expected_counts'],
              'environment': {'python': sys.version, 'torch': str(torch.__version__), 'device': 'cpu', 'threads': config['threads']},
              'runs': rows, 'test_evaluated': evaluate_test, 'seconds': perf_counter() - start,
              'scope': 'Frozen-backbone residual training on scripted P0; no human performance claim',
              'retained_seed': seeds[0]}
    if evaluate_test:
        report['test_cross_seed'] = aggregate([row['test'] for row in rows])
    output.mkdir(parents=True)
    (output / 'model.pt').write_bytes(selected[0])
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print('Saved selected model and compact report:', output)


def predict_file(checkpoint_path, data_path):
    raw = json.loads(data_path.read_text(encoding='utf8'))
    raw = raw if isinstance(raw, list) else [raw]
    model = reload_model(checkpoint_path.read_bytes())
    batch = Batch([{'input': adapt_record(record)} for record in raw])
    for record, prediction in zip(raw, model.predict(batch, evidence=True)):
        print(json.dumps({'sample_id': record.get('sample_id'), 'semantic_contract': model.semantic_contract,
                          't1_resume_probability': prediction['t1'],
                          't2_conditional_step_distribution': prediction['t2'],
                          't3_state_distributions': prediction['t3'],
                          'evidence_trace': prediction['evidence_trace'], 'calibrated': False},
                         ensure_ascii=False, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/a_context_p0_v03.json')
    parser.add_argument('--predict', type=Path)
    parser.add_argument('--data', type=Path)
    parser.add_argument('--all-seeds', action='store_true', help='Train fixed evaluation seeds 0-19; retain first seed')
    parser.add_argument('--evaluate-test', action='store_true', help='Explicitly score already-exposed P0 test after dev selection')
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.predict:
        if not args.data:
            parser.error('--predict requires --data')
        predict_file(args.predict, args.data)
    else:
        run(args.config.resolve(), args.all_seeds, args.evaluate_test)


if __name__ == '__main__':
    main()
