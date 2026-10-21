"""Reproducible neural P0 training, dev selection, reload and locked evaluation.

Run: python -m models.ecr_mwm.neural_training --config configs/a_neural_p0.json
No per-epoch logs/intermediate files. Only the formal report, reproduction README
and A0 seed-0 selected checkpoint are persisted. P0 is scripted, not human data.
"""
import argparse
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
from time import perf_counter

import torch
from torch.nn import functional as F

from models.ec_jmf.neural_filter import LABELS,OFFSETS
from models.ecr_mwm.neural_data import load_records
from models.ecr_mwm.neural_model import Batch,NeuralECJMF
from models.ecr_mwm.neural_metrics import evaluate,aggregate
from models.ecr_mwm.p0_adapter import adapt_record

ROOT=Path(__file__).resolve().parents[2]


def seed_everything(seed,threads=1):
    random.seed(seed);torch.manual_seed(seed)
    torch.set_num_threads(threads);torch.use_deterministic_algorithms(True)


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


def total_loss(terms,variant,config,selection=False):
    # Every model uses the SAME dev criterion, including A5's untrained step head.
    loss=terms['state']+terms['resume']
    if selection or variant!='A5': loss=loss+terms['step']
    if not selection and variant!='A4':
        loss=loss+config['consistency_weight']*(terms['event_consistency']+terms['invariance'])
    return loss


def checkpoint_bytes(model,config,seed,epoch):
    buffer=io.BytesIO()
    torch.save({'format':('a-neural-ec-jmf/v1' if model.semantic_contract=='legacy-v1' else 'a-neural-ec-jmf/v2'),
                'semantic_contract':model.semantic_contract,'variant':model.variant,'hidden_dim':model.hidden,
                'seed':seed,'selected_epoch':epoch,'config':config,
                'state_dict':{k:v.detach().cpu().clone() for k,v in model.state_dict().items()}},buffer)
    return buffer.getvalue()


def reload_model(payload):
    checkpoint=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    if checkpoint['format']=='a-neural-ec-jmf/v1': contract='legacy-v1'
    elif checkpoint['format']=='a-neural-ec-jmf/v2': contract=checkpoint['semantic_contract']
    else: raise ValueError('UNKNOWN_CHECKPOINT_FORMAT')
    model=NeuralECJMF(checkpoint['variant'],checkpoint['hidden_dim'],contract)
    model.load_state_dict(checkpoint['state_dict'],strict=True);model.eval()
    return model


def fit_one(train,dev,variant,seed,config):
    seed_everything(seed,config['threads'])
    model=NeuralECJMF(variant,config['hidden_dim'],config.get('semantic_contract','legacy-v1'))
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                               lr=config['learning_rate'],weight_decay=config['weight_decay'])
    best_loss=float('inf');best_state=None;best_epoch=None;first_audit=None
    for epoch in range(1,config['epochs']+1):
        model.train();optimizer.zero_grad(set_to_none=True)
        output=model(train);terms=loss_terms(output,train);loss=total_loss(terms,variant,config)
        if not torch.isfinite(loss): raise ValueError('NONFINITE_TRAINING_LOSS')
        loss.backward()
        if epoch==1:
            first_audit={'nonzero_gradient_parameters':sum(p.numel() for p in model.parameters()
                          if p.grad is not None and float(p.grad.abs().sum())>1e-12),
                         'loss_terms':{k:float(v.detach()) for k,v in terms.items()},
                         'event_regularizers':len(train.regularizers),'equivalent_pairs':len(train.info_pairs)}
        torch.nn.utils.clip_grad_norm_(model.parameters(),config['gradient_clip'])
        optimizer.step()
        model.eval()
        with torch.no_grad():
            validation=float(total_loss(loss_terms(model(dev),dev),variant,config,selection=True))
        if validation<best_loss:
            best_loss,best_epoch=validation,epoch
            best_state={k:v.detach().clone() for k,v in model.state_dict().items()}
    model.load_state_dict(best_state)
    payload=checkpoint_bytes(model,config,seed,best_epoch)
    # Actual torch serialization + strict weights-only reload for EVERY run.
    restored=reload_model(payload)
    with torch.no_grad():
        a,b=model(dev),restored(dev)
        discrepancy=max(float((a[key]-b[key]).abs().max()) for key in ('p','q','factors'))
    if discrepancy!=0: raise ValueError('CHECKPOINT_RELOAD_MISMATCH')
    return payload,{'seed':seed,'selected_epoch':best_epoch,'dev_selection_loss':best_loss,
                    'epochs_executed':config['epochs'],'reload_max_abs_error':discrepancy,
                    'parameter_count':sum(p.numel() for p in model.parameters()),
                    'first_epoch_audit':first_audit}


def score(model,batch):
    return evaluate(model.predict(batch),[e['target'] for e in batch.examples])


def summary_values(metrics):
    factors=[metrics['t3'][f]['macro_f1'] for f in 'VFABCQ' if metrics['t3'][f]['macro_f1'] is not None]
    mental=[metrics['t3'][f]['macro_f1'] for f in 'BCQ' if metrics['t3'][f]['macro_f1'] is not None]
    return {'t1_f1':metrics['t1']['f1'],'t1_auroc':metrics['t1']['auroc'],
            't1_ap':metrics['t1']['ap'],'t1_brier':metrics['t1']['brier'],
            't2_top1':metrics['t2']['top1'], 't3_macro_f1':sum(factors)/len(factors),
            'bcq_macro_f1':sum(mental)/len(mental)}


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit():
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def write_readme(report,path):
    def cell(item):
        return f"{item['mean']:.4f} ± {item['sample_sd']:.4f}" if item['mean'] is not None else 'undefined'
    config=report['config'];counts=report['data']['primary']['counts']
    lines=['# A 神经 EC-JMF：P0 正式受控诊断','',
           '数字由训练入口自动生成。仅为脚本P0，不是真实人物预测性能、心理真值或创新性证明。','',
           f"协议：`{report['protocol']}`；数据：`{config['data']}`。",
           f"训练源码提交：`{report['code_commit']}`；PyTorch `{report['environment']['torch']}`，CPU。",
           f"train/dev/test：{counts['train']}/{counts['dev']}/{counts['test']}；每变体20个种子、{config['epochs']}轮全批AdamW，统一dev选模。",
           '所有140次均从随机初始化训练，先完成全部dev选择，再统一评价test；未加载旧模型继续训练。',
           '以下为test跨种子均值 ± 样本标准差，仅表示训练随机性，不是人类总体置信区间。','',
           '|变体|T1 F1|AUROC|AP|Brier↓|T2条件top1|T3六因子原始对照值|BCQ macro-F1均值|',
           '|---|---|---|---|---|---|---|---|']
    for variant in config['variants']:
        stats=report['variants'][variant]['summary']
        lines.append('|'+variant+'|'+'|'.join(cell(stats[k]) for k in
                     ('t1_f1','t1_auroc','t1_ap','t1_brier','t2_top1','t3_macro_f1','bcq_macro_f1'))+'|')
    if config.get('evaluation_scope'):
        lines += ['', '本轮T3.A焦点映射未完全确认；六因子值包含该代理，仅作原始对照，不是已对齐B口径的完整成绩。T2是条件分布评分，不是C的端到端输出步骤准确率。']
    a0=report['variants']['A0']['runs'][0]['test']
    lines += ['',f"每seed有效T1={a0['t1']['n']}、T2={a0['t2']['n']}；T3逐因子有效数："+
              '、'.join(f"{f}={a0['t3'][f]['n']}" for f in 'VFABCQ')+'。',
              '', '## 结构零支持（跨种子均值）','',
              '|变体|V|F|A|B|C|Q|','|---|---|---|---|---|---|---|']
    for variant in config['variants']:
        metrics=report['variants'][variant]['test']['t3']
        lines.append('|'+variant+'|'+'|'.join(f"{metrics[f]['zero_support']['mean']:.2f}" for f in 'VFABCQ')+'|')
    epochs=[r['selected_epoch'] for v in report['variants'].values() for r in v['runs']]
    lines += ['',f"完成{report['completed_runs']}次，失败{report['failed_runs']}次；选中epoch范围{min(epochs)}–{max(epochs)}。不据此宣称预算最优。",
              '完整逐因子/逐机制指标、有效n、零支持、每seed选中epoch、重载误差及配对seed差均在同目录 `report.json`。',
              '', '## 从头复现','', '```powershell',
              'python -m pip install -r requirements-dev.txt -r requirements-neural.txt',
              f"python -m models.ecr_mwm.neural_training --config {report['config_path']}",
              f"python -m models.ecr_mwm.neural_training --predict {config['output']}/a0_seed0.pt --data {config['data']}",
              '```','',
              '实际解释器为 `D:/myProgram/Anaconda3/python.exe`（已有PyTorch），未向仓库安装依赖目录。',
              '每次均真实save/load到内存并校验T1/T2/T3；仅保留预指定A0 seed0的最终选中模型，不按test挑选seed。',
              '预测命令只向stdout输出T1/T2/T3及新模型自身的逐事件证据轨迹，不需要监督标签。','',
              '## 预先固定的协议与边界','',
              'T1阈值0.5、ECE10等宽箱，indeterminate/null不作负例；T2仅恢复为true且首步属于原目标、未客观完成；T3仅非UNKNOWN且有cutoff有效证据，逐因子计数。Q按图内位置池化。T2缺失计错，零支持标签不丢弃；无双类别AUROC为null。',
              '训练state NLL概率下限1e-8，评价NLL下限1e-12，沿用旧流程；饱和损失不能修复结构零支持。',
              'A1取消接触/理解门控；A2独立BCQ；A3仅保留最近5事件人物记忆并完整重放世界；A4移除事件软对齐及严格等价JS；A5去步骤训练损失但仍评价；A6固定结构门控而保留公共可学习世界先验/行为头。',
              '世界事实、人物可得信息、理解、信念、承诺和进度仍由原结构核区分；仅A1故意作为信息门控负对照。网络不读取自由文本或身份，U为给定结构化证据。',
              '参数总数相同；first_epoch_audit.nonzero_gradient_parameters统计具有非零梯度的参数张量所含元素总数，不是逐元素非零梯度计数。未宣称消融有效参数量完全相等。',
              '严格等价JS可由结构保证为零；A4实际可训练差异主要是事件软对齐，不代表研究计划全部认识损失。',
              'UNKNOWN争议保留掩码；有限结构支持、自由文本解析和误解表示仍有覆盖限制。B仲裁、C公共接口/MENTIS、公平评测及P1校准/泛化尚未完成。']
    if config.get('test_exposure'): lines += ['',config['test_exposure']]
    lines += ['']+config.get('limitations',[])
    if report['data']['supplement']:
        lines += ['',f"独立补充：{report['data']['supplement']['n']}条，仅冻结模型诊断，未参与训练或选模。"]
    lines += ['', '仅保存一份JSON汇总、一份复现说明和一个最终模型；不保存140份日志或中间检查点。']
    path.write_text('\n'.join(lines)+'\n',encoding='utf8')


def run(config_path):
    config=json.loads(config_path.read_text(encoding='utf8'))
    if config['evaluation_seeds']!=list(range(20)): raise ValueError('FIXED_EVALUATION_SEEDS_REQUIRED')
    if config['variants']!=[f'A{i}' for i in range(7)]: raise ValueError('ALL_ABLATIONS_REQUIRED')
    data=ROOT/config['data'];supplement=ROOT/config['supplement'] if config.get('supplement') else None
    examples=load_records(data);parts={s:[e for e in examples if e['split']==s] for s in ('train','dev','test')}
    if config.get('expected_counts') and {s:len(e) for s,e in parts.items()}!=config['expected_counts']:
        raise ValueError('DATA_SPLIT_COUNTS_CHANGED')
    if config.get('expected_data_sha256') and sha(data)!=config['expected_data_sha256']:
        raise ValueError('DATA_RELEASE_CHANGED')
    seed_everything(config['seed'],config['threads']);start=perf_counter()
    selected={};batches={}
    for variant in config['variants']:
        print(f'{variant}: compile train/dev, {len(parts["train"])}/{len(parts["dev"])} records',flush=True)
        train,dev=(Batch(parts[s],variant,config.get('semantic_contract','legacy-v1')) for s in ('train','dev'))
        batches[variant]=(train,dev)
        selected[variant]=[]
        for seed in config['evaluation_seeds']:
            payload,metadata=fit_one(train,dev,variant,seed,config)
            selected[variant].append((payload,metadata))
            if seed%5==0 or seed==19: print(f'{variant}: selected {seed+1}/20, epoch={metadata["selected_epoch"]}',flush=True)
    training_seconds=perf_counter()-start
    print('All 140 training/dev selections frozen; starting single locked test pass.',flush=True)
    output=ROOT/config['output'];output.mkdir(parents=True,exist_ok=True)
    supplemental=load_records(supplement) if supplement else None
    report={'protocol':config['protocol'],'config':config,'config_path':config_path.relative_to(ROOT).as_posix(),'code_commit':git_commit(),
            'data':{'primary':{'path':config['data'],'sha256':sha(data),'counts':{s:len(e) for s,e in parts.items()}},
                    'supplement':{'path':config['supplement'],'sha256':sha(supplement),'n':len(supplemental)} if supplement else None},
            'environment':{'python':sys.version,'torch':str(torch.__version__),'platform':platform.platform(),
                           'device':'cpu','threads':config['threads'],'tokens':0},
            'training_seconds':training_seconds,'completed_runs':140,'failed_runs':0,'variants':{},'paired_seed_differences':{},
            'limitations':['scripted P0 only','structured inputs; no text understanding learning',
                           'UNKNOWN masks preserve B disputes','no calibration/P1/MENTIS conclusions']}
    for variant in config['variants']:
        test=Batch(parts['test'],variant,config.get('semantic_contract','legacy-v1'))
        transfer=Batch(supplemental,variant,config.get('semantic_contract','legacy-v1')) if supplement else None
        rows=[]
        slices={m:[i for i,e in enumerate(parts['test']) if e['mechanism']==m] for m in sorted({e['mechanism'] for e in parts['test']})}
        mechanism_metrics={m:[] for m in slices}
        for payload,metadata in selected[variant]:
            model=reload_model(payload)
            metadata=deepcopy(metadata)
            predictions=model.predict(test)
            metadata['test']=evaluate(predictions,[e['target'] for e in test.examples])
            if transfer is not None: metadata['supplement']=score(model,transfer)
            for mechanism,indices in slices.items():
                mechanism_metrics[mechanism].append(evaluate([predictions[i] for i in indices],
                                                            [test.examples[i]['target'] for i in indices]))
            metadata['summary']=summary_values(metadata['test']);rows.append(metadata)
        report['variants'][variant]={'runs':rows,'test':aggregate([r['test'] for r in rows]),
                                    'supplement':aggregate([r['supplement'] for r in rows]) if supplement else None,
                                    'summary':aggregate([r['summary'] for r in rows]),
                                    'by_mechanism':{m:aggregate(values) for m,values in mechanism_metrics.items()}}
        print(variant,'locked test',report['variants'][variant]['summary'],flush=True)
    for variant in config['variants'][1:]:
        deltas=[]
        for a,b in zip(report['variants']['A0']['runs'],report['variants'][variant]['runs']):
            deltas.append({k:a['summary'][k]-b['summary'][k] if a['summary'][k] is not None and b['summary'][k] is not None else None for k in a['summary']})
        report['paired_seed_differences'][variant]=aggregate(deltas)
    report['elapsed_seconds']=perf_counter()-start
    # A predetermined representative, never the best test seed/model.
    payload=selected['A0'][0][0];(output/'a0_seed0.pt').write_bytes(payload)
    report['retained_model']={'path':str((output/'a0_seed0.pt').relative_to(ROOT)).replace('\\','/'),
                              'sha256':hashlib.sha256(payload).hexdigest(),'variant':'A0','seed':0,
                              'selected_epoch':selected['A0'][0][1]['selected_epoch']}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    write_readme(report,output/'README.md')
    print('Formal outputs:',output,flush=True)


def predict_file(checkpoint_path,data_path):
    raw=json.loads(data_path.read_text(encoding='utf8'));raw=raw if isinstance(raw,list) else [raw]
    model=reload_model(checkpoint_path.read_bytes())
    examples=[{'input':adapt_record(r)} for r in raw]
    predictions=model.predict(Batch(examples,model.variant,model.semantic_contract),evidence=True)
    for r,p in zip(raw,predictions):
        public={'sample_id':r.get('sample_id'),'semantic_contract':model.semantic_contract,'t1_resume_probability':p['t1'],
                't2_conditional_step_distribution':p['t2'],'t3_state_distributions':p['t3'],
                'evidence_trace':p['evidence_trace'],'calibrated':False}
        print(json.dumps(public,ensure_ascii=False,allow_nan=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/a_neural_p0.json')
    parser.add_argument('--predict',type=Path)
    parser.add_argument('--data',type=Path)
    args=parser.parse_args()
    if args.predict:
        if not args.data: parser.error('--predict requires --data')
        torch.set_num_threads(1);predict_file(args.predict,args.data)
    else: run(args.config.resolve())


if __name__=='__main__': main()
