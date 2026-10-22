"""Independently score A's delivered v3 checkpoint using C's unchanged protocol.

This verifies a single supplied checkpoint, not a new 20-seed training run.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration.a_neural_output import normalize_neural_output
from models.ecr_mwm.neural_data import load_records
from models.ecr_mwm.neural_metrics import evaluate as a_evaluate
from models.ecr_mwm.neural_model import Batch
from models.ecr_mwm.neural_training import reload_model, seed_everything
from mwm_eval.metrics import evaluate
from mwm_eval.p0 import prepare_dataset
from mwm_eval.schema import file_hash, validate_prediction
from scripts.validate_data import validate_records


def check():
    config_path = ROOT / 'configs/a_neural_p0_v03_aligned.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    data = ROOT / config['data']
    if file_hash(data) != config['expected_data_sha256']:
        raise ValueError('DATA_RELEASE_CHANGED')
    raw = json.loads(data.read_text(encoding='utf-8'))
    if validate_records(raw):
        raise ValueError('INVALID_B_DATA')
    counts = {s:sum(r['split'] == s for r in raw) for s in ('train','dev','test')}
    if counts != config['expected_counts']:
        raise ValueError('DATA_SPLIT_COUNTS_CHANGED')
    records, golds = prepare_dataset(raw)
    test = [r for r in records if r['split'] == 'test']
    gold_by_id = {g['sample_id']:g for g in golds}
    gold = [gold_by_id[r['sample_id']] for r in test]
    checkpoint = ROOT / config['output'] / 'a0_seed0.pt'
    payload = checkpoint.read_bytes()
    seed_everything(0, config['threads'])
    model = reload_model(payload)
    if model.semantic_contract != config['semantic_contract']:
        raise ValueError('CHECKPOINT_CONTRACT_MISMATCH')
    # Targets and sample identity are deliberately absent from inference.
    batch = Batch([{'input':copy.deepcopy(r['observation']['structured_evidence'])} for r in test],
                  model.variant, model.semantic_contract)
    native = model.predict(batch, evidence=True)
    if native != reload_model(payload).predict(batch, evidence=True):
        raise ValueError('RELOAD_PREDICTION_MISMATCH')
    rows = []
    for record, pred in zip(test, native):
        public = normalize_neural_output(pred, record['observation'])
        validate_prediction(public, record['observation'])
        rows.append({'sample_id':record['sample_id'], 'status':'ok', 'prediction':public})
    metrics = evaluate(rows, gold, test)
    examples = [e for e in load_records(data) if e['split'] == 'test']
    internal = a_evaluate(native, [e['target'] for e in examples])
    supplied = json.loads((ROOT / config['output'] / 'report.json').read_text(encoding='utf-8'))
    expected = next(r['test'] for r in supplied['variants']['A0']['runs'] if r['seed'] == 0)
    if internal != expected:
        raise ValueError('A_SUPPLIED_METRICS_MISMATCH')
    if abs(metrics['t1']['accuracy'] - internal['t1']['accuracy']) > 1e-10:
        raise ValueError('A_C_ACCURACY_MISMATCH')
    return {'scope':'C inference verification of supplied A0 seed0 v3 checkpoint; no independent retraining',
            'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'data_sha256':file_hash(data), 'checkpoint_sha256':file_hash(checkpoint),
            'config_sha256':file_hash(config_path), 'semantic_contract':model.semantic_contract,
            'verification':{'reload_exact':True,'label_free_inference':True,'A_seed0_metrics_exact':True},
            'C_metrics':metrics,'A_internal_metrics':internal,
            'A_supplied_20_seed_summary':supplied['variants']['A0']['summary'],
            'evaluation_scope':config['evaluation_scope'],
            'limitations':config['limitations']}


if __name__ == '__main__':
    result = check()
    out = ROOT / 'evaluation/neural_v03_aligned_checkpoint_check.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n',encoding='utf-8')
    print(out)
    print(json.dumps({'T1':result['C_metrics']['t1']['accuracy'],
                      'F1':result['C_metrics']['t1']['resume_f1'],
                      'C_T2':result['C_metrics']['t2']['top1_accuracy']}, indent=2))
