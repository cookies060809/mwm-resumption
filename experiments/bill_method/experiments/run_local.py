"""Local P0-only warm-start diagnostics. Never writes to the source repository."""
from __future__ import annotations
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE.parents[1]
RESULTS = BASE / 'results'
sys.path.insert(0, str(SOURCE))

import torch
from torch import nn
from torch.nn import functional as F
from models.ecr_mwm.neural_model import NeuralECJMF, Batch
from models.ecr_mwm.neural_training import reload_model, seed_everything, loss_terms, total_loss
from models.ecr_mwm.neural_data import load_records, STATE_DIM
from models.ecr_mwm.neural_metrics import evaluate as native_evaluate
from integration.a_neural_output import normalize_neural_output
from mwm_eval.p0 import prepare_dataset
from mwm_eval.metrics import evaluate as public_evaluate
from mwm_eval.schema import validate_prediction

CHECKPOINT = SOURCE / 'results/p0/a_neural_v03_v3/a0_seed0.pt'
DATA = SOURCE / 'data/p0/v0.3/p0_samples.json'
CONFIG_PATH = SOURCE / 'configs/a_neural_p0_v03_aligned.json'
BASE_CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def freeze_protocol():
    protocol = {
        'name': 'P0 local warm-start context residual diagnostic v1',
        'created_date': '2026-10-22',
        'source_commit': '87a660b67be19dbd374b4709f7509f94871f9848',
        'source_archive_sha256': '48e583d17ea965817f4cea0f4ee60e2264eb20d59ad258c8d2dc4ca9d58bba21',
        'base_checkpoint_sha256': sha(CHECKPOINT),
        'data_sha256': sha(DATA), 'original_config_sha256': sha(CONFIG_PATH),
        'variants': ['original_frozen', 'head_continue', 'visible_context', 'visible_context_balanced'],
        'seeds': {'original_frozen':[0], 'head_continue':[0], 'visible_context':[0,1,2,3,4], 'visible_context_balanced':[0,1,2,3,4]},
        'epochs': 40, 'learning_rate': 0.01, 'weight_decay': 0.0001,
        'gradient_clip': 5.0, 'hidden_dim': 24, 'residual_bound': 2.0, 'dropout': 0.1,
        'base_parameters': 'freeze all base parameters, except original resume_head in head_continue control',
        'loss': 'original state NLL + resume BCE + conditional step NLL + 0.05*(event consistency + invariance); balanced variant changes only train resume BCE weights by train mechanism inverse frequency',
        'selection': 'minimum unweighted original dev state NLL + T1 BCE + T2 NLL; earliest tie; compare method mean dev loss to original; canonical seed0, never best test seed',
        'test_policy': 'train and select all runs before opening test predictions; one terminal evaluation of all predefined runs; historical P0 test is already exposed, not a fresh blind holdout',
        'stress': ['consistent identifier renaming', '10 invisible semantic no-op events', '30 invisible semantic no-op events'],
        'scope': 'structured scripted P0 only; no human generalization or world-model-paper reproduction claim',
        'hardware': {'python': platform.python_version(), 'torch': torch.__version__, 'device':'cpu','threads':1,'logical_cpu_count':os.cpu_count()},
    }
    path = RESULTS/'protocol.json'
    if path.exists():
        old=json.loads(path.read_text(encoding='utf-8'))
        if old != protocol:
            raise RuntimeError('Protocol already exists and differs; refuse silent change')
    else:
        write_json(path, protocol)
    return protocol


class ContextHazard(nn.Module):
    def __init__(self, base_head, hidden=24, bound=2.0, dropout=0.1):
        super().__init__()
        self.base_head=base_head
        self.attention=nn.Linear(hidden,1,bias=False)
        self.residual=nn.Sequential(nn.Linear(STATE_DIM+hidden*2,hidden),nn.Tanh(),nn.Dropout(dropout),nn.Linear(hidden,1))
        nn.init.zeros_(self.residual[-1].weight)
        nn.init.zeros_(self.residual[-1].bias)
        self.bound=bound
        self.context=None
        self.records=None

    def set_context(self, proposals, memories, batch):
        mask=batch.valid & batch.visible
        scores=self.attention(proposals).squeeze(-1).masked_fill(~mask,-1e9)
        weights=scores.softmax(-1)*mask
        weights=weights/weights.sum(-1,keepdim=True).clamp_min(1e-12)
        pooled=(proposals*weights[...,None]).sum(1)
        self.context=torch.cat((pooled,memories[:,-1]),-1)
        self.records=batch.state_record

    def forward(self, features):
        if self.context is None:
            raise RuntimeError('Context must be set by the same forward call')
        extra=self.context[self.records]
        delta=self.bound*torch.tanh(self.residual(torch.cat((features,extra),-1)))
        return self.base_head(features)+delta


class ContextECJMF(NeuralECJMF):
    def encode(self,batch):
        world,proposals,memories=super().encode(batch)
        self.resume_head.set_context(proposals,memories,batch)
        return world,proposals,memories


def make_model(kind,seed):
    seed_everything(seed,1)
    baseline=reload_model(CHECKPOINT.read_bytes())
    for p in baseline.parameters():p.requires_grad_(False)
    if kind in ('original_frozen','head_continue'):
        if kind=='head_continue':
            for p in baseline.resume_head.parameters():p.requires_grad_(True)
        return baseline
    model=ContextECJMF('A0',24,BASE_CONFIG['semantic_contract'])
    model.load_state_dict(baseline.state_dict(),strict=True)
    for p in model.parameters():p.requires_grad_(False)
    model.resume_head=ContextHazard(model.resume_head)
    model.eval()
    return model


def train_weights(batch):
    groups={}
    for row,e in enumerate(batch.examples):
        if e['target']['resume'] is not None:groups.setdefault(e['mechanism'],[]).append(row)
    out=torch.zeros(batch.n)
    for indices in groups.values():out[indices]=1/len(indices)
    out=out/out[out>0].mean()
    return out


def loss(output,batch,balanced=False,selection=False):
    terms=loss_terms(output,batch)
    if balanced and not selection:
        _,_,rr,ry,_,_=batch.loss_indices
        w=train_weights(batch)[rr]
        terms['resume']=(F.binary_cross_entropy(output['p'][rr].clamp(1e-7,1-1e-7),ry,reduction='none')*w).sum()/w.sum()
    return total_loss(terms,'A0',BASE_CONFIG,selection=selection),terms


def save_model(model,kind,seed,epoch,path):
    torch.save({'format':'c-local-context-diagnostic/v1','kind':kind,'seed':seed,'epoch':epoch,
                'base_checkpoint_sha256':sha(CHECKPOINT), 'state_dict':model.state_dict()},path)


def load_model(path):
    checkpoint=torch.load(path,map_location='cpu',weights_only=True)
    assert checkpoint['base_checkpoint_sha256']==sha(CHECKPOINT)
    m=make_model(checkpoint['kind'],checkpoint['seed'])
    m.load_state_dict(checkpoint['state_dict'],strict=True);m.eval()
    return m


@torch.no_grad()
def dev_score(model,dev):
    model.eval()
    output=model(dev)
    value,_=loss(output,dev,selection=True)
    return float(value)


def fit_run(kind,seed,train,dev,protocol):
    model=make_model(kind,seed)
    folder=RESULTS/kind/f'seed_{seed}'
    folder.mkdir(parents=True,exist_ok=False)
    initial=dev_score(model,dev)
    baseline=make_model('original_frozen',0)
    with torch.no_grad():
        reference=baseline(dev);new=model(dev)
        initial_error=max(float((reference[k]-new[k]).abs().max()) for k in ('p','q','factors'))
    if initial_error!=0:raise RuntimeError('New method must start exactly at original predictions')
    seed_everything(seed,1)
    trainable=[p for p in model.parameters() if p.requires_grad]
    original_state={k:v.detach().clone() for k,v in model.state_dict().items()}
    history=[];start=time.perf_counter()
    best_loss=initial;best_epoch=0;best_state=copy.deepcopy(model.state_dict())
    if trainable:
        opt=torch.optim.AdamW(trainable,lr=protocol['learning_rate'],weight_decay=protocol['weight_decay'])
        for epoch in range(1,protocol['epochs']+1):
            model.train();opt.zero_grad(set_to_none=True)
            output=model(train);total,terms=loss(output,train,balanced=kind.endswith('_balanced'))
            if not torch.isfinite(total):raise RuntimeError('Nonfinite training objective')
            total.backward()
            grad_count=sum(p.numel() for p in trainable if p.grad is not None and p.grad.abs().sum()>0)
            torch.nn.utils.clip_grad_norm_(trainable,protocol['gradient_clip']);opt.step()
            current=dev_score(model,dev)
            history.append({'epoch':epoch,'train_loss':float(total.detach()),'dev_loss':current,
                            'train_resume_loss':float(terms['resume'].detach()),'train_state_loss':float(terms['state'].detach()),
                            'train_step_loss':float(terms['step'].detach()),'nonzero_gradient_parameter_elements':int(grad_count)})
            if current<best_loss:
                best_loss=current;best_epoch=epoch;best_state=copy.deepcopy(model.state_dict())
        model.load_state_dict(best_state)
    model.eval()
    frozen_names=[n for n,p in model.named_parameters() if not p.requires_grad]
    if any(not torch.equal(model.state_dict()[n],original_state[n]) for n in frozen_names):
        raise RuntimeError('Frozen original parameters changed')
    path=folder/'checkpoint.pt';save_model(model,kind,seed,best_epoch,path)
    restored=load_model(path)
    with torch.no_grad():
        a,b=model(dev),restored(dev)
        reload_error=max(float((a[k]-b[k]).abs().max()) for k in ('p','q','factors'))
    if reload_error!=0:raise RuntimeError('Saved checkpoint did not reproduce predictions')
    if history:
        with (folder/'history.csv').open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=list(history[0]));writer.writeheader();writer.writerows(history)
    result={'kind':kind,'seed':seed,'selected_epoch':best_epoch,'initial_dev_loss':initial,'dev_selection_loss':best_loss,
            'parameter_count':sum(p.numel() for p in model.parameters()),'trainable_parameters':sum(p.numel() for p in trainable),
            'initial_prediction_max_error':initial_error,'reload_max_error':reload_error,'frozen_parameters_unchanged':True,
            'seconds':time.perf_counter()-start,'checkpoint':str(path.relative_to(BASE)), 'checkpoint_sha256':sha(path)}
    write_json(folder/'training.json',result)
    print('TRAINED',kind,seed,'epoch',best_epoch,'dev',round(best_loss,6),flush=True)
    return result


def evaluate_run(run,examples,records,gold):
    model=load_model(BASE/run['checkpoint'])
    test=Batch([{'input':copy.deepcopy(e['input'])} for e in examples],'A0',BASE_CONFIG['semantic_contract'])
    start=time.perf_counter();native=model.predict(test,evidence=True);seconds=time.perf_counter()-start
    rows=[]
    for record,pred in zip(records,native):
        prediction=normalize_neural_output(pred,record['observation']);validate_prediction(prediction,record['observation'])
        rows.append({'sample_id':record['sample_id'],'status':'ok','prediction':prediction})
    public=public_evaluate(rows,gold,records)
    native_metrics=native_evaluate(native,[e['target'] for e in examples])
    summary={'kind':run['kind'],'seed':run['seed'],'dev_selection_loss':run['dev_selection_loss'],'selected_epoch':run['selected_epoch'],
             't1_accuracy':public['t1']['accuracy'],'t1_f1':public['t1']['resume_f1'],
             'fp':public['t1']['confusion_valid_predictions']['fp'],'fn':public['t1']['confusion_valid_predictions']['fn'],
             'auroc':public['t1']['probability']['auroc'],'brier':public['t1']['probability']['brier'],
             't2_emitted_top1':public['t2']['top1_accuracy'],'t2_conditional_top1':native_metrics['t2']['top1'],
             'inference_seconds':seconds,'n_t1':public['t1']['n_eligible'],'n_t2':public['t2']['n_eligible']}
    folder=BASE/run['checkpoint'];folder=folder.parent
    write_json(folder/'evaluation.json',{'summary':summary,'C_metrics':public,'A_native_metrics':native_metrics})
    with (folder/'predictions.jsonl').open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    return summary,native


def stress_evaluate(run,examples,clean):
    from stress_transforms import transform_example
    model=load_model(BASE/run['checkpoint'])
    output=[]
    for kind,level in [('rename_ids',1),('invisible_noops',10),('invisible_noops',30)]:
        transformed=[transform_example(e,kind,level) for e in examples]
        batch=Batch([{'input':copy.deepcopy(e['input'])} for e in transformed],'A0',BASE_CONFIG['semantic_contract'])
        native=model.predict(batch)
        eligible=[i for i,e in enumerate(examples) if e['target']['resume'] is not None]
        correct=sum((native[i]['t1']>=0.5)==examples[i]['target']['resume'] for i in eligible)
        flips=sum((native[i]['t1']>=0.5)!=(clean[i]['t1']>=0.5) for i in eligible)
        deltas=[abs(a['t1']-b['t1']) for a,b in zip(native,clean)]
        output.append({'method':run['kind'],'seed':run['seed'],'transform':kind,'level':level,
                       't1_accuracy':correct/len(eligible),'decision_flips':flips,'n_eligible':len(eligible),
                       'mean_abs_probability_change':statistics.mean(deltas),'max_abs_probability_change':max(deltas)})
    return output


def main():
    protocol=freeze_protocol()
    seed_everything(0,1)
    all_examples=load_records(DATA)
    train_examples=[e for e in all_examples if e['split']=='train']
    dev_examples=[e for e in all_examples if e['split']=='dev']
    train=Batch(train_examples,'A0',BASE_CONFIG['semantic_contract'])
    dev=Batch(dev_examples,'A0',BASE_CONFIG['semantic_contract'])
    runs=[]
    for kind in protocol['variants']:
        for seed in protocol['seeds'][kind]:runs.append(fit_run(kind,seed,train,dev,protocol))
    methods={kind:statistics.mean(r['dev_selection_loss'] for r in runs if r['kind']==kind) for kind in protocol['variants']}
    selection={'method_mean_dev_loss':methods,'selected_method':min(methods,key=methods.get),'canonical_seed':0,
               'selection_completed_before_test_evaluation':True}
    write_json(RESULTS/'dev_selection.json',selection)
    print('DEV_SELECTION_LOCKED',selection['selected_method'],flush=True)
    # Terminal test phase: no architecture, loss, or selection change below this line.
    test_examples=[e for e in all_examples if e['split']=='test']
    raw=json.loads(DATA.read_text(encoding='utf-8'));records,golds=prepare_dataset(raw)
    records=[r for r in records if r['split']=='test'];gold_map={g['sample_id']:g for g in golds};g=[gold_map[r['sample_id']] for r in records]
    if [r['sample_id'] for r in records]!=[e['id'] for e in test_examples]:raise RuntimeError('Test order mismatch')
    summaries=[];stress=[]
    for run in runs:
        result,native=evaluate_run(run,test_examples,records,g);summaries.append(result)
        stress.extend(stress_evaluate(run,test_examples,native))
        print('EVALUATED',run['kind'],run['seed'],result['t1_accuracy'],result['fp'],result['fn'],flush=True)
    for name,rows in [('comparison.csv',summaries),('stress.csv',stress)]:
        with (RESULTS/name).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write_json(RESULTS/'run_manifest.json',{'protocol':protocol,'selection':selection,'runs':runs,'comparison':summaries,'stress':stress})
    print('ALL_LOCAL_RUNS_COMPLETE',flush=True)


if __name__=='__main__':main()
