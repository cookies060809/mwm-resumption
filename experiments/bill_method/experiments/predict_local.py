"""Load a local checkpoint and predict P0 records without training or network calls."""
import argparse
import copy
import json
import sys
import run_local as r

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--method',choices=['original_frozen','head_continue','visible_context','visible_context_balanced'],default='visible_context')
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--split',choices=['train','dev','test'],default='dev')
    parser.add_argument('--limit',type=int,default=3)
    parser.add_argument('--sample-id')
    args=parser.parse_args()
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    examples=[e for e in r.load_records(r.DATA) if e['split']==args.split]
    if args.sample_id:examples=[e for e in examples if e['id']==args.sample_id]
    if args.limit<1:parser.error('--limit must be positive')
    examples=examples[:args.limit]
    if not examples:parser.error('No matching records in requested split')
    model=r.load_model(r.RESULTS/args.method/f'seed_{args.seed}'/'checkpoint.pt')
    # The prediction batch intentionally contains only input, never target/family/mechanism.
    batch=r.Batch([{'input':copy.deepcopy(e['input'])} for e in examples],'A0',r.BASE_CONFIG['semantic_contract'])
    native=model.predict(batch,evidence=True)
    records,_=r.prepare_dataset(json.loads(r.DATA.read_text(encoding='utf-8')))
    by_id={record['sample_id']:record for record in records}
    for e,p in zip(examples,native):
        result=r.normalize_neural_output(p,by_id[e['id']]['observation'])
        r.validate_prediction(result,by_id[e['id']]['observation'])
        print(json.dumps({'sample_id':e['id'],'method':args.method,'seed':args.seed,
                          'p_resume':result['p_resume'],'resume_label':result['resume_label'],
                          'resume_step':result['resume_step']},ensure_ascii=False))

if __name__=='__main__':main()
