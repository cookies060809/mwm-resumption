"""Paired P1 retraining of the original A model; no fabricated state supervision.

Preserves the previous C-branch response initialization and minibatch RNG,
so unrelated constructor RNG consumption cannot masquerade as an improvement.
"""
import argparse
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
from time import perf_counter

import torch

from models.ecr_mwm.neural_model import Batch, NeuralECJMF
from models.ecr_mwm.neural_training import seed_everything
from models.ecr_mwm.ready_data import load_bundle, vocabulary, state_input
from models.ecr_mwm.ready_model import ReadyModel, checkpoint_bytes, reload_model
from models.ecr_mwm.ready_training import fit, response_metrics, state_metrics

ROOT=Path(__file__).resolve().parents[2]


def git_bytes(ref,path):
    return subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)


def historical_context(config):
    rows=csv.DictReader(io.StringIO(git_bytes(config['context_reference_ref'],config['context_reference_summary']).decode('utf-8-sig')))
    return [{k:(v if k in ('method','name') else (float(v) if v else None)) for k,v in row.items()} for row in rows]


def write_readme(report,path):
    test=report['original_run']['response_test'];ref=report['reference_run']['response_test']
    lines=['# Original A / C-context: paired READY P1 comparison','',
           '原模型来自 feat/a-p0-v03-neural@dec55faa 的正式 v3 A0；改进版对照来自',
           'feat/a-p1-public-derived-eval@80b2982。原模型在本分支实际重训了续答模块；结构模型冻结。',
           '两个分支都没有用对话回答伪造六状态或恢复标签。','',
           '## 配对训练和实际结果','',
           '相同 train/dev/test=288/71/69、31/7/7 对话组、seed0、12轮、AdamW、词表与编码、',
           'dev NLL选择、指标和mask。响应头初始化与批次RNG严格匹配C分支，避免构造器参数量混杂。',
           '仅执行一个种子，没有跨种子稳定性结论；本次为已暴露语料上的重复诊断。','',
           '|P1公开参考回答蒸馏指标|原A|C改进版|','|---|---:|---:|']
    for key in ('token_nll_UNK_projection','perplexity_UNK_projection','casefold_token_exact_match','unigram_token_f1','ended_with_EOS'):
        lines.append(f"|{key}|{test[key]:.6f}|{ref[key]:.6f}|")
    lines += ['',f"原A选中epoch {report['original_run']['selected_epoch']}，dev NLL {report['original_run']['selected_dev_token_nll']:.6f}。",
              f"响应模块最终参数逐项相同：{report['paired_response_weights_identical']}；保存重载误差为0。",
              '上下文截断、OOV及完整计数见report.json与上一分支正式报告；最新用户打断完整保留。',
              '这不是回答正确性/任务成功率，完全匹配率为0，不能称为实用续答效果。','',
              '## 能否判断谁更好','',
              '不能。当前响应损失和生成完全不消费结构化模型，C改进仅作用于恢复hazard；',
              'READY的P1没有该hazard可用的T1/T2监督，对话六状态mask全0。',
              '配对训练后续答参数与分数相同，证明当前任务/连接不能识别该改进，并不证明两种结构模型普遍等效。',
              'READY六状态52条test来自旧P0，不能称P1状态成绩；两模型T3相同也不检验hazard的优点。','',
              '## A1–A6机制消融','',
              '已恢复原模型完整机制源码，并对七个变体执行最小加载/状态前向检查。',
              'P1续答中消融不在损失或生成路径上：仅共享已实际训练的响应模块，逐变体验证dev响应logit不变。',
              '没有把七次重复相同续答训练充当机制消融；A4/A5是训练损失消融，此处结构损失均未启用。',
              '本轮没有重训七个结构模型；其P1机制效果全部为不可识别。',
              '下表保留旧分支正式P0消融的20种子结果，明确不是本轮P1训练，也不是新盲测。','',
              '|历史P0变体|T1 F1|T2 top1|BCQ macro-F1|','|---|---:|---:|---:|']
    for name,summary in report['historical_P0_ablation'].items():
        vals=[summary[k] for k in ('t1_f1','t2_top1','bcq_macro_f1')]
        lines.append('|'+name+'|'+'|'.join(f"{v['mean']:.4f} ± {v['sample_sd']:.4f}" for v in vals)+'|')
    lines += ['', '### C历史P0方法对照（不是P1消融）','',
              '|方法|warm-start次数|T1 F1|Brier|','|---|---:|---:|---:|']
    for row in report.get('historical_C_P0_controls',[]):
        lines.append(f"|{row['method']}|{int(row['n_warm_start_runs'])}|{row['t1_f1_mean']:.4f}|{row['brier_mean']:.5f}|")
    lines += ['', 'C上下文/平衡变体为固定原seed0骨干上的5次模块训练；原A表为20次全模型训练，',
              '不能把两种seed标准差直接当成同一统计设计。C原头续训也达到相同硬判断水平，',
              '旧P0提升不能全归因于上下文结构，更不能外推至本P1任务。',
              '', '## 复现','', '```bash',
              'git fetch origin feat/a-p0-v03-neural Bill_method',
              'python -m pip install -r requirements-dev.txt -r requirements-neural.txt',
              'python -m models.ecr_mwm.p1_comparison --config configs/a_original_p1_comparison.json',
              'python -m models.ecr_mwm.ready_training --predict results/p1/a_original_comparison/model.pt --data data/training_ready/v1/dev.jsonl --limit 3',
              '```','',
              '拒绝覆盖已有输出；重跑仅在配置副本修改output。旧P0参数从固定Git提交读取，',
              '最终model.pt自包含原A参数、已训练响应模块、词表与配置，独立推理不读取旧Git对象。',
              '只保留最终模型、本文和report.json；没有日志或中间checkpoint。',
              '需要B/C提供可比恢复监督、窗口/步骤与公共接口，或另行明确联合文本-结构训练任务，',
              '现有P1任务无法识别该机制；本轮不编造监督，也不假定恢复已取消的真人采集。']
    path.write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')


def run(config_path):
    config=json.loads(config_path.read_text(encoding='utf8'))
    output=ROOT/config['output']
    if output.exists(): raise ValueError('OUTPUT_EXISTS: choose a new output')
    reference_payload=(ROOT/config['reference_model']).read_bytes()
    if hashlib.sha256(reference_payload).hexdigest()!=config['reference_model_sha256']:
        raise ValueError('REFERENCE_MODEL_CHANGED')
    reference_report=json.loads((ROOT/config['reference_report']).read_text(encoding='utf8'))
    reference_run=reference_report['runs'][0]
    for name in ('seed','epochs','batch_size','learning_rate','weight_decay','gradient_clip','threads','architecture','encoding','max_generated_tokens','vocab_size'):
        if config[name]!=reference_report['config'][name]: raise ValueError('UNPAIRED_SETTING: '+name)
    if reference_report['executed_seeds']!=[config['seed']]: raise ValueError('REFERENCE_SEED_MISMATCH')
    data_path=ROOT/config['data']
    if hashlib.sha256((data_path/'manifest.json').read_bytes()).hexdigest()!=config['manifest_sha256']:
        raise ValueError('READY_MANIFEST_CHANGED')
    data=load_bundle(data_path)
    responses={s:[r for r in rr if r['task']=='interruption_response'] for s,rr in data.items()}
    states={s:[r for r in rr if r['task']=='state_inference'] for s,rr in data.items()}
    for split in ('train','dev'):
        for row in states[split]: state_input(row['input'])
    words=vocabulary(data['train'],config['encoding'],config['vocab_size'])
    old_payload=git_bytes(config['original_ref'],config['original_checkpoint'])
    if hashlib.sha256(old_payload).hexdigest()!=config['original_checkpoint_sha256']:
        raise ValueError('ORIGINAL_MODEL_CHANGED')
    old=torch.load(io.BytesIO(old_payload),map_location='cpu',weights_only=True)
    if old['format']!='a-neural-ec-jmf/v2' or old['semantic_contract']!='b-p0-v03/v3' or old['variant']!='A0':
        raise ValueError('ORIGINAL_FORMAL_V3_REQUIRED')
    original={'architecture':{'hidden':old['hidden_dim'],'semantic_contract':old['semantic_contract']},'state_dict':old['state_dict']}
    context=torch.load(io.BytesIO((ROOT/config['context_checkpoint']).read_bytes()),map_location='cpu',weights_only=True)
    # Reproduce the original C run initialization, including its constructor RNG.
    seed_everything(config['seed'],config['threads'])
    ref_config=reference_report['config']
    initial=ReadyModel(context['architecture'],words,ref_config)
    initialization=(deepcopy(initial.response.state_dict()),torch.get_rng_state().clone())
    del initial
    start=perf_counter()
    payload,metadata=fit(responses['train'],responses['dev'],original,words,config,config['seed'],initialization)
    if metadata['initial_dev_token_nll']!=reference_run['initial_dev_token_nll']:
        raise ValueError('RESPONSE_INITIALIZATION_MISMATCH')
    model=reload_model(payload);reference=reload_model(reference_payload)
    same=all(torch.equal(v,reference.response.state_dict()[k]) for k,v in model.response.state_dict().items())
    print('Original train/dev selection fixed; terminal paired P1 evaluation.',flush=True)
    metadata['response_test']=response_metrics(model,responses['test'])
    original_states=state_metrics(model,states['test'])
    probe=[r['input'] for r in states['dev'][:2]]
    response_probe=responses['dev'][:2]
    with torch.no_grad():
        source,previous,_=model.training_batch(response_probe)
        logits=model.response(source,previous)
        invariant={}
        original_context=model.context
        for variant in [f'A{i}' for i in range(7)]:
            mechanism=NeuralECJMF(variant,old['hidden_dim'],old['semantic_contract'])
            mechanism.load_state_dict(old['state_dict'],strict=True);mechanism.eval()
            mechanism.predict(Batch([{'input':state_input(x)} for x in probe],variant,old['semantic_contract']))
            model.context=mechanism
            error=float((model.response(source,previous)-logits).abs().max())
            invariant[variant]={'dev_response_logit_max_abs_delta':error,'state_forward_check':True,
                                'P1_structural_retraining':False,'P1_mechanism_effect':'not identifiable'}
        model.context=original_context
        deltas=[]
        for rows in [states['test'][i:i+16] for i in range(0,len(states['test']),16)]:
            inputs=[r['input'] for r in rows]
            a=model.predict('state_inference',inputs);b=reference.predict('state_inference',inputs)
            deltas.extend(abs(v-bb['state_distributions'][f][k]) for aa,bb in zip(a,b)
                          for f,d in aa['state_distributions'].items() for k,v in d.items())
    history=json.loads(git_bytes(config['original_ref'],config['original_report']))
    report={'protocol':config['protocol'],'config':config,
            'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
            'torch':str(torch.__version__),'executed_seeds':[config['seed']],
            'original_run':metadata,'reference_run':reference_run,
            'paired_response_weights_identical':same,
            'response_metric_differences':{k:metadata['response_test'][k]-reference_run['response_test'][k]
                                          for k in ('token_nll_UNK_projection','perplexity_UNK_projection','casefold_token_exact_match','unigram_token_f1','ended_with_EOS')},
            'original_state_test_P0_only':original_states,'max_T3_original_reference_delta_P0_only':max(deltas),
            'ablation_checks':invariant,'historical_P0_scope':'existing original-branch P0 v3 results, 20 seeds, 40 epochs; not P1 retraining',
            'historical_P0_ablation':{name:row['summary'] for name,row in history['variants'].items()},
            'historical_C_P0_controls':historical_context(config),
            'model_sha256':hashlib.sha256(payload).hexdigest(),'elapsed_seconds':perf_counter()-start,
            'conclusion':'P1 response task does not identify original vs C structural improvement; no winner justified',
            'P1_behavior_or_state_truth_created':False}
    output.mkdir(parents=True)
    (output/'model.pt').write_bytes(payload)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    write_readme(report,output/'README.md')
    print('Paired response weights identical:',same,flush=True)
    print('Original P1 response metrics:',metadata['response_test'],flush=True)
    print('Formal comparison outputs:',output,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/a_original_p1_comparison.json')
    args=parser.parse_args();run(args.config.resolve())


if __name__=='__main__': main()
