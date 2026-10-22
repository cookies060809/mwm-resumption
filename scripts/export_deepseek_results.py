"""Verify real external outputs and publish aggregate results without credentials/raw text."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mwm_eval.metrics import evaluate
from mwm_eval.p0 import prepare_dataset
from mwm_eval.schema import canonical_hash,file_hash


def main():
    data=ROOT/'data/p0/v0.3/p0_samples.json'
    records,golds=prepare_dataset(json.loads(data.read_text(encoding='utf-8')))
    test=[r for r in records if r['split']=='test']
    lookup={r['sample_id']:r for r in test}
    by_gold={g['sample_id']:g for g in golds}
    gold=[by_gold[r['sample_id']] for r in test]
    runs=[]; artifacts=[]; all_rows=[]
    for folder in ('c_neural_deepseek_b2b3_contract_v2','c_neural_deepseek_mentis','c_neural_deepseek_b9_recovery','c_neural_deepseek_b9_resumed'):
        root=ROOT/'results'/folder
        summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
        rows=[json.loads(x) for x in (root/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
        for run in summary['runs']:
            selected=[r for r in rows if r['method_id']==run['method_id']]
            if len(selected)!=len(test) or {r['sample_id'] for r in selected}!=set(lookup):
                raise ValueError('MISSING_OR_DUPLICATE_TEST_ROWS')
            for row in selected:
                obs=lookup[row['sample_id']]['observation']
                if row['input_hash']!=canonical_hash(obs) or row['source_input_hash']!=canonical_hash(obs):
                    raise ValueError('INPUT_HASH_MISMATCH')
            if evaluate(selected,gold,test)!=run['metrics']:
                raise ValueError('RECOMPUTED_METRICS_MISMATCH')
            if folder in ('c_neural_deepseek_mentis','c_neural_deepseek_b9_recovery') and run['method_id']=='B9':
                run['superseded_by_transport_recovery']=True
            else:
                runs.append(run)
        artifacts.append({'path':str(root.relative_to(ROOT)).replace('\\','/'),
                          'predictions_sha256':file_hash(root/'predictions.jsonl'),
                          'summary_sha256':file_hash(root/'summary.json'),
                          'fingerprint':summary['fingerprint']})
        all_rows.extend(rows)
    failed_root=ROOT/'results/c_neural_deepseek_b2b3'
    initial=json.loads((failed_root/'summary.json').read_text(encoding='utf-8'))
    initial_rows=[json.loads(x) for x in (failed_root/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    all_rows.extend(initial_rows)
    # Recovery reuses successful original rows without new API calls.
    all_rows=list({canonical_hash(row):row for row in all_rows}.values())
    prompt=completion=hit=miss=0;unknown_usage=0;upstream_calls=0
    for row in all_rows:
        usage=row.get('usage')
        if not isinstance(usage,dict):unknown_usage+=1;continue
        prompt+=usage.get('prompt_tokens',0) or 0
        completion+=usage.get('completion_tokens',0) or 0
        hit+=usage.get('prompt_cache_hit_tokens',0) or 0
        miss+=usage.get('prompt_cache_miss_tokens',0) or 0
        metadata=(row.get('prediction') or {}).get('metadata',{})
        calls=metadata.get('llm_calls',0) or 0
        if not calls and row.get('failure_metadata',{}).get('raw_output'):
            try:calls=json.loads(row['failure_metadata']['raw_output']).get('metadata',{}).get('llm_calls',0) or 0
            except (ValueError,TypeError):pass
        upstream_calls+=calls
    # Official Flash pricing checked 2026-10-22. Bounds cover off-peak/peak;
    # unknown hit/miss input tokens use cache-hit lower/cache-miss upper rates.
    unspecified=max(0,prompt-hit-miss)
    low=((hit+unspecified)*.003+miss*.15+completion*.6)/1_000_000
    high=(hit*.006+(miss+unspecified)*.3+completion*1.2)/1_000_000
    output={'scope':'Single real DeepSeek pass per method on exposed scripted B P0 v0.3',
            'data_sha256':file_hash(data),'model':'deepseek-flash','thinking_mode':'disabled',
            'temperature':0,'per_call_max_output_tokens':4096,'runs':runs,'verified_artifacts':artifacts,
            'initial_protocol_failure':{'reason':'Missing state-label vocabulary in legacy prompt; all 104 requests retained, not scored as final protocol.',
                'runs':[{k:r[k] for k in ('method_id','counts','cost')} for r in initial['runs']],
                'predictions_sha256':file_hash(failed_root/'predictions.jsonl')},
            'accounting_all_attempts':{'sample_requests':len(all_rows),'prompt_tokens':prompt,
                'completion_tokens':completion,'total_tokens':prompt+completion,'unknown_usage_records':unknown_usage,
                'mentis_reported_llm_calls':upstream_calls,'estimated_usd_range':[low,high],
                'actual_invoice_usd':None,'pricing_source':'https://api-docs.deepseek.com/quick_start/pricing/',
                'note':'Estimate from reported usage, not account invoice; upstream failed calls can underreport usage.'},
            'limitations':['B3 contract failures count wrong in accuracy; F1 withheld with eligible failures.',
                'B9 recovery retries only HTTP402/429 transport failures; valid originals are reused without extra calls. Incomplete API coverage is not an algorithm-quality score.',
                'No calibration, independent blind holdout, human data or reproducible API seed.',
                'MENTIS is adapted to project MCQ; B9 duplicates mechanical goal memory.',
                'Identical per-call token caps do not establish total-token equality; no budget-matched superiority claim.',
                'Shared label vocabulary was fixed before rerunning every B2/B3 sample; no answer tuning or selective retry.',
                'Local model, direct LLM and multi-call MENTIS consume different computation.']}
    target=ROOT/'evaluation/deepseek_p0_results.json'
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(target)
    for run in runs:
        m=run['metrics']
        print(run['method_id'],m['t1']['accuracy'],m['t1']['resume_f1'],m['t2']['top1_accuracy'],m['counts']['n_failure'])
    print(json.dumps(output['accounting_all_attempts'],ensure_ascii=False))


if __name__=='__main__':main()
