"""Run real external baselines with per-record durable logs and bounded concurrency.

Reuses C input handling, validation, failure policy and metrics. Existing rows,
including failures, are never silently retried or selected by their test score.
"""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mwm_eval.engine import predict_rows, dump_json, _cost
from mwm_eval.external import make_external_baselines
from mwm_eval.metrics import evaluate
from mwm_eval.p0 import prepare_dataset
from mwm_eval.schema import canonical_hash, file_hash, validate_dataset, audit_groups
from scripts.run_p0_evaluation import require_accepted_batch
from scripts.validate_data import validate_records


def run(config_path, output, methods, workers, reuse_successes_from=None, max_new_records=None, max_new_tokens=None):
    data = ROOT / 'data/p0/v0.3/p0_samples.json'
    raw = json.loads(data.read_text(encoding='utf-8'))
    if validate_records(raw): raise ValueError('INVALID_DATA')
    require_accepted_batch(raw)
    records, golds = prepare_dataset(raw)
    validation = validate_dataset(records,golds)
    groups = audit_groups(records)
    for key in ('base_story_id','person_id','task_family'):
        if any(groups[key]['pairwise_overlap'].values()): raise ValueError('SPLIT_LEAKAGE')
    test = [r for r in records if r['split']=='test']
    gold_by_id = {g['sample_id']:g for g in golds}
    gold = [gold_by_id[r['sample_id']] for r in test]
    config = json.loads(config_path.read_text(encoding='utf-8'))
    config['run_seed'] = 0
    registry = make_external_baselines(config)
    output.mkdir(parents=True,exist_ok=True)
    fingerprint = {'data_sha256':file_hash(data),'config_sha256':file_hash(config_path),
                   'methods':methods,'test_ids':[r['sample_id'] for r in test],
                   'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                   'source_sha256':{p:file_hash(ROOT/p) for p in ('mwm_eval/external.py','integration/mentis_adapter.py',
                                                                 'scripts/run_external_resumable.py')}}
    path = output/'fingerprint.json'
    if reuse_successes_from:
        prior=json.loads((reuse_successes_from/'fingerprint.json').read_text(encoding='utf-8'))
        if any(prior[k]!=fingerprint[k] for k in ('data_sha256','config_sha256','test_ids')):
            raise ValueError('RECOVERY_PROTOCOL_MISMATCH')
        fingerprint['transport_recovery_source']={'path':str(reuse_successes_from),
            'predictions_sha256':file_hash(reuse_successes_from/'predictions.jsonl'),
            'policy':'Reuse valid outputs; retry transport failures only, no score selection.'}
    if path.exists() and json.loads(path.read_text(encoding='utf-8')) != fingerprint:
        raise ValueError('RESUME_FINGERPRINT_MISMATCH')
    dump_json(path,fingerprint)
    log = output/'predictions.jsonl'
    if reuse_successes_from and not log.exists():
        previous=[json.loads(x) for x in (reuse_successes_from/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
        relevant=[r for r in previous if r['method_id'] in methods]
        for row in relevant:
            if row['status']=='ok':continue
            envelope=json.loads(row['failure_metadata']['raw_output'])
            detail=envelope['metadata']['official_result']
            if detail.get('error_type') not in {'APIStatusError','RateLimitError','BranchExecutionError'}:
                raise ValueError('NONTRANSPORT_FAILURE_CANNOT_BE_RECOVERED')
            if not any(code in detail.get('error_message','') for code in ('402','429')):
                raise ValueError('NONTRANSPORT_FAILURE_CANNOT_BE_RECOVERED')
        log.write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n'
                              for r in relevant if r['status']=='ok'),encoding='utf-8')
    cached = [json.loads(x) for x in log.read_text(encoding='utf-8').splitlines()] if log.exists() else []
    keys = {(r['method_id'],r['sample_id']) for r in cached}
    if len(keys)!=len(cached): raise ValueError('DUPLICATE_CACHE_ROWS')
    rows = list(cached)
    reused_keys=set()
    if reuse_successes_from:
        previous=[json.loads(x) for x in (reuse_successes_from/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
        reused_keys={(r['method_id'],r['sample_id']) for r in previous if r['status']=='ok'}
    def charged_tokens():
        return sum((r.get('usage') or {}).get('total_tokens',0) or 0 for r in rows
                   if (r['method_id'],r['sample_id']) not in reused_keys)
    new_count=0
    def persist(row,stream):
        nonlocal new_count
        stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush()
        rows.append(row);new_count+=1
        count=sum(r['method_id']==row['method_id'] for r in rows)
        print(f'{row["method_id"]}: {count}/{len(test)} {row["status"]}; new known tokens={charged_tokens()}',flush=True)
        if row['status']!='ok':
            detail=row.get('failure_metadata',{}).get('raw_output','')
            if '402' in detail and ('Insufficient Balance' in detail or 'Error code: 402' in detail):
                raise RuntimeError('API402_CIRCUIT_OPEN: log saved; no next sample will be called')
    for name in methods:
        method = registry[name]
        available = method.availability()
        if not available['available']: raise ValueError(name+': '+available['reason'])
        pending = [r for r in test if (name,r['sample_id']) not in keys]
        if max_new_records is not None:pending=pending[:max(0,max_new_records-new_count)]
        print(f'{name}: {len(pending)} pending, workers={workers}',flush=True)
        if workers==1:
            with log.open('a',encoding='utf-8') as stream:
                for record in pending:
                    if max_new_tokens is not None and charged_tokens()>=max_new_tokens:
                        print('TOKEN_BUDGET_REACHED; log saved',flush=True);break
                    persist(predict_rows(method,[record],0)[0],stream)
            continue
        if max_new_tokens is not None:
            raise ValueError('TOKEN_BUDGET_REQUIRES_WORKERS_1')
        with log.open('a',encoding='utf-8') as stream, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_record = {pool.submit(predict_rows,method,[r],0):r for r in pending}
            done = sum(r['method_id']==name for r in cached)
            for future in concurrent.futures.as_completed(future_to_record):
                row = future.result()[0]
                stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush()
                rows.append(row);done+=1
                print(f'{name}: {done}/{len(test)} {row["status"]}',flush=True)
    runs=[]
    if len(rows)!=len(test)*len(methods):
        dump_json(output/'progress.json',{'completed_rows':len(rows),'planned_rows':len(test)*len(methods),
                                        'new_known_tokens':charged_tokens(),'max_new_tokens':max_new_tokens})
        print('Partial run saved; no full-test summary published',flush=True)
        return
    for name in methods:
        selected = [r for r in rows if r['method_id']==name]
        runs.append({'method_id':name,'seed':0,'metrics':evaluate(selected,gold,test),
                     'cost':_cost(selected),'spec':registry[name].spec()})
    result={'scope':'Real API single pass on previously exposed scripted P0; not new blind testing',
            'fingerprint':fingerprint,'validation':validation,'group_audit':groups,'runs':runs,
            'limits':['No independent calibration; no reproducible provider seed.',
                      'Same per-call cap is not equal total inference budget for a multi-call pipeline.',
                      'B9 character-capped memory does not establish token-budget equality.',
                      'Upstream errors and missing results count as failures; failed calls may lack complete usage.']}
    dump_json(output/'summary.json',result)
    print('Completed '+str(output/'summary.json'),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--methods',default='B8,B9')
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--reuse-successes-from',type=Path)
    parser.add_argument('--max-new-records',type=int)
    parser.add_argument('--max-new-tokens',type=int)
    args=parser.parse_args()
    if not 1<=args.workers<=8: raise ValueError('WORKERS_1_TO_8')
    run(args.config,args.output_dir,args.methods.split(','),args.workers,args.reuse_successes_from,
        args.max_new_records,args.max_new_tokens)
