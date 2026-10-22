"""Recompute v3 format-protocol results and report probability coverage."""
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
    by_gold={r['sample_id']:r for r in golds}
    exports=[];tokens=0
    for split,folder in [('dev','c_neural_deepseek_b3_v3_dev'),('test','c_neural_deepseek_b2b3_contract_v3')]:
        root=ROOT/'results'/folder
        summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
        rows=[json.loads(x) for x in (root/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
        selected=[r for r in records if r['split']==split]
        lookup={r['sample_id']:r for r in selected}
        gold=[by_gold[r['sample_id']] for r in selected]
        for run in summary['runs']:
            method_rows=[r for r in rows if r['method_id']==run['method_id']]
            if len(method_rows)!=len(lookup) or {r['sample_id'] for r in method_rows}!=set(lookup):
                raise ValueError('INCOMPLETE_OR_DUPLICATE_ROWS')
            for row in method_rows:
                expected=canonical_hash(lookup[row['sample_id']]['observation'])
                if row['input_hash']!=expected or row['source_input_hash']!=expected:
                    raise ValueError('INPUT_HASH_MISMATCH')
            if evaluate(method_rows,gold,selected)!=run['metrics']:
                raise ValueError('METRICS_MISMATCH')
            valid=[r['prediction'] for r in method_rows if r['status']=='ok']
            coverage={'valid_outputs':len(valid),'planned_outputs':len(method_rows),
                      'p_resume_present':sum(p.get('p_resume') is not None for p in valid),
                      'conditional_step_probs_present':sum(p.get('conditional_step_probs') is not None for p in valid),
                      'state_factor_distributions_present':{f:sum(f in p.get('state_probs',{}) for p in valid) for f in 'VFABCQ'}}
            exports.append({'split':split,**run,'probability_coverage':coverage})
        tokens+=sum((r.get('usage') or {}).get('total_tokens',0) or 0 for r in rows)
    result={'protocol':'canonical-label-v3','data_sha256':file_hash(data),
            'scope':'Exposed scripted P0 v0.3; shared output-contract clarification, not new blind testing',
            'runs':exports,'new_reported_tokens':tokens,
            'limitations':['Model-reported probabilities, no independent calibration.',
                           'Null probability fields are permitted and coverage is reported explicitly.',
                           'V2 results retained; all B2/B3 test rows rerun, no selective repair.',
                           'Dev used only to check format reliability, not select test answers.']}
    target=ROOT/'evaluation/deepseek_v3_results.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for r in exports:
        print(r['split'],r['method_id'],json.dumps({'t1':r['metrics']['t1'],'t2':r['metrics']['t2'],'coverage':r['probability_coverage']},ensure_ascii=False))
    print('NEW_REPORTED_TOKENS',tokens)


if __name__=='__main__':main()
