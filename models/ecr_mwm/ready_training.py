"""Actual READY P1 response training, dev selection, generation and task routing.

Only one selected final model and one compact report are retained. No API calls,
P1 pseudo-belief labels, per-epoch files or intermediate checkpoints.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import torch

from models.ecr_mwm.neural_training import seed_everything
from models.ecr_mwm.neural_model import Batch
from models.ecr_mwm.neural_metrics import evaluate as state_evaluate, aggregate
from models.ecr_mwm.ready_data import load_bundle, vocabulary, tokens, source_tokens, state_input
from models.ecr_mwm.ready_model import ReadyModel, checkpoint_bytes, reload_model, token_f1

ROOT=Path(__file__).resolve().parents[2]


def batches(rows,size):
    for start in range(0,len(rows),size): yield rows[start:start+size]


@torch.no_grad()
def response_nll(model, rows):
    model.eval(); total=count=0
    for chunk in batches(rows,model.config['batch_size']):
        value,n=model.loss_sum(chunk);total+=float(value);count+=n
    return total/count


def coverage(model, rows):
    stats=Counter();targets=unknown=0
    for row in rows:
        _,info=source_tokens(row['input'],model.config['encoding']);stats.update(info)
        reference=tokens(row['target']);targets+=len(reference)
        unknown+=sum(w not in model.index for w in reference)
    return {**dict(stats),'rows':len(rows),'target_tokens':targets,'target_unknown_tokens':unknown,
            'target_OOV_rate':unknown/targets,'target_truncated_rows':0}


def fit(train,dev,context,words,config,seed,response_initialization=None):
    seed_everything(seed,config['threads'])
    model=ReadyModel(context['architecture'],words,config)
    model.context.load_state_dict(context['state_dict'],strict=True)
    if response_initialization is not None:
        weights,rng_state=response_initialization
        model.response.load_state_dict(weights,strict=True)
        torch.set_rng_state(rng_state)
    frozen={k:v.detach().clone() for k,v in model.context.state_dict().items()}
    initial=response_nll(model,dev)
    best_loss,best_epoch,best=initial,0,deepcopy(model.state_dict())
    optimizer=torch.optim.AdamW(model.response.parameters(),lr=config['learning_rate'],weight_decay=config['weight_decay'])
    first_loss=None;last_loss=None;gradient_elements=0
    for epoch in range(1,config['epochs']+1):
        model.train();order=torch.randperm(len(train)).tolist(); total=count=0
        for begin in range(0,len(order),config['batch_size']):
            chunk=[train[i] for i in order[begin:begin+config['batch_size']]]
            optimizer.zero_grad(set_to_none=True)
            value,n=model.loss_sum(chunk);objective=value/n
            if not torch.isfinite(objective): raise ValueError('NONFINITE_RESPONSE_TRAINING_LOSS')
            objective.backward()
            if epoch==1 and begin==0:
                gradient_elements=sum(int(p.grad.ne(0).sum()) for p in model.response.parameters() if p.grad is not None)
            torch.nn.utils.clip_grad_norm_(model.response.parameters(),config['gradient_clip'])
            optimizer.step();total+=float(value.detach());count+=n
        if epoch==1: first_loss=total/count
        last_loss=total/count
        current=response_nll(model,dev)
        if current<best_loss: best_loss,best_epoch,best=current,epoch,deepcopy(model.state_dict())
        if epoch==1 or epoch%10==0:
            print(f'Response seed {seed}: epoch {epoch}/{config["epochs"]}, train NLL {last_loss:.4f}, dev {current:.4f}',flush=True)
    model.load_state_dict(best);model.eval()
    if any(not torch.equal(value,model.context.state_dict()[name]) for name,value in frozen.items()):
        raise ValueError('FROZEN_CONTEXT_CHANGED')
    metadata={'seed':seed,'epochs_executed':config['epochs'],'selected_epoch':best_epoch,
              'initial_dev_token_nll':initial,'selected_dev_token_nll':best_loss,
              'first_epoch_training_token_nll':first_loss,'last_epoch_training_token_nll':last_loss,
              'first_batch_nonzero_gradient_elements':gradient_elements,'frozen_context_unchanged':True}
    payload=checkpoint_bytes(model,metadata);restored=reload_model(payload)
    with torch.no_grad():
        source,previous,_=model.training_batch(dev[:2])
        error=float((model.response(source,previous)-restored.response(source,previous)).abs().max())
    if error!=0: raise ValueError('READY_RESPONSE_RELOAD_MISMATCH')
    metadata['reload_max_abs_error']=error
    return payload,metadata


@torch.no_grad()
def response_metrics(model, rows):
    nll=response_nll(model,rows)
    exact=f1=eos=0
    for chunk in batches(rows,model.config['batch_size']):
        results=model.predict('interruption_response',[r['input'] for r in chunk])
        for row,pred in zip(chunk,results):
            ref=tokens(row['target']); exact+=pred['tokens']==ref
            f1+=token_f1(pred['tokens'],ref);eos+=pred['ended_with_eos']
    return {'n':len(rows),'independent_conversations':len({r['group_id'] for r in rows}),
            'token_nll_UNK_projection':nll,'perplexity_UNK_projection':math.exp(nll),
            'casefold_token_exact_match':exact/len(rows),'unigram_token_f1':f1/len(rows),
            'ended_with_EOS':eos/len(rows),'coverage':coverage(model,rows)}


@torch.no_grad()
def state_metrics(model, rows):
    predictions=[]
    for chunk in batches(rows,16):
        predictions.extend(model.context.predict(Batch([{'input':state_input(r['input'])} for r in chunk])))
    targets=[{'resume':None,'step':None,'states':{f:r['target'][f] for f in 'VFABCQ' if r['state_loss_mask'][f]},
              'steps':r['input']['task_steps']} for r in rows]
    return {'n':len(rows),'scope':'previously exposed P0 state task, not new P1 ground truth',
            't3':state_evaluate(predictions,targets)['t3'],
            'partial_nested_graph_rows':sum(len(state_input(r['input'])['observer_graphs'])>1 for r in rows),
            'missing_parent_policy':'observed child graph retained, parent and unobserved steps unknown; no inferred occupancy stack'}


def write_readme(report,path):
    canonical=report['runs'][0];test=canonical['response_test'];cov=test['coverage']
    config=report['config']
    lines=['# READY P1 实际适配与文本续答训练','',
           '按B正式ready-v1.0两任务交付接入：既有P0六状态 + IHBench公开baseline回答蒸馏。',
           '当前不是仅格式检查：已训练神经文本编码/注意力GRU解码器，完成dev选择、保存重载及无teacher-forcing生成。',
           '它不生成新的恢复或信念真值，不代表真人恢复预测。','',
           '## 本次真实执行','',
           '正式12轮预算在test评分前固定；较早40轮尝试仅运行train/dev，停止后未产生正式结果。',
           f"运行seed：{report['executed_seeds']}，每seed {config['epochs']}轮；保留预指定首个seed，不按test挑选。",
           f"响应train/dev/test={report['response_counts']['train']}/{report['response_counts']['dev']}/{report['response_counts']['test']}，对话组31/7/7。",
           f"seed0 dev NLL：初始{canonical['initial_dev_token_nll']:.4f}，选中epoch{canonical['selected_epoch']}，最低{canonical['selected_dev_token_nll']:.4f}。",
           f"保存重载最大误差{canonical['reload_max_abs_error']}；C结构化模型权重保持不变。",'',
           '|test指标（公开回答蒸馏一致性）|值|','|---|---:|',
           f"|样本/独立对话|{test['n']}/{test['independent_conversations']}|",
           f"|token NLL（UNK投影）|{test['token_nll_UNK_projection']:.4f}|",
           f"|perplexity（UNK投影）|{test['perplexity_UNK_projection']:.4f}|",
           f"|casefold token exact match|{test['casefold_token_exact_match']:.4f}|",
           f"|unigram token F1|{test['unigram_token_f1']:.4f}|",
           f"|EOS结束率|{test['ended_with_EOS']:.4f}|",
           f"|参考答案词表外token率|{cov['target_OOV_rate']:.4f}|",'',
           '这些是已发布GPT-4o Audio回答的模仿指标，不是回答正确性、任务成功率或T1/T2恢复预测指标。',
           '小模型从随机初始化训练，没有预训练语言知识；低分/泛化不足应如实解释，不以训练损失下降冒充实用效果。',
           '源公开语料在此前状态诊断中已被检查，故不称全新盲测。','',
           '## 输入编码、任务隔离与限制','',
           f"train-only词表{report['vocabulary_size']}；角色编码，system头/尾各96tokens、较旧history预算320，最新用户打断完整保留。",
           f"test system截断{cov['system_truncated']}/{cov['rows']}行，history截断{cov['history_truncated']}/{cov['rows']}行；完整统计见report.json。",
           'system很长，本模型没有完整理解整个知识库。答案不截断；NLL/PPL基于未知词映射为UNK后的词表，',
           '同时报告OOV；生成的exact match/token F1则与完整原参考token比较，不把参考未知词抹掉。',
           '推理仅读task/input；messages含训练答案，绝不送编码器。文本辅助模块不写入世界/人物理解、信念或承诺。',
           'READY六状态输入缺完整horizon和interrupting_task；从显式事件识别主goal和已见子目标，',
           '未见步骤/父子关系保留未知。部分子图不能被宣布完整完成；不根据target或id补来源标签。',
           '六状态路由仅输出T3，未定义T1/T2；原P0完整输入入口继续支持已有T1/T2。',
           '对话行六状态mask全部0，未把回答文本改成六变量标签；P0数量未与原数据重复拼接。',
           '当前是任务分离的辅助生成适配，不是联合训练文本理解/信念更新。B/C仍需定义真正的公共在线语义接口。','',
           '## 复现与推理','', '```bash',
           'python -m pip install -r requirements-dev.txt -r requirements-neural.txt',
           'python -m models.ecr_mwm.ready_training --config configs/a_ready_p1.json',
           'python -m models.ecr_mwm.ready_training --predict results/p1/a_ready_response/model.pt --data data/training_ready/v1/test.jsonl --limit 3',
           '```','',
           '运行器拒绝覆盖已有输出；重跑时在配置副本修改output。默认seed0，--all-seeds才展开固定0–19，',
           '本次未声称已完成20seed。只保留一个含完整Context+词表+文本模块的model.pt、report.json和本文。',
           '训练/生成不需要外部API、GPU或新的文本依赖，没有中间checkpoint或每轮日志文件。',
           'state_test仅为原P0测试数据重用，逐因子mask与适配边界见report.json，不能称P1六状态成绩。']
    path.write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')


def run(config_path,all_seeds=False):
    config=json.loads(config_path.read_text(encoding='utf8'))
    if config['evaluation_seeds']!=list(range(20)): raise ValueError('FIXED_SEED_CONVENTION_REQUIRED')
    output=ROOT/config['output']
    if output.exists(): raise ValueError('OUTPUT_EXISTS: choose a new output')
    data_path=ROOT/config['data'];context_path=ROOT/config['context_checkpoint']
    if hashlib.sha256((data_path/'manifest.json').read_bytes()).hexdigest()!=config['manifest_sha256']:
        raise ValueError('READY_MANIFEST_CHANGED')
    if hashlib.sha256(context_path.read_bytes()).hexdigest()!=config['context_checkpoint_sha256']:
        raise ValueError('CONTEXT_CHECKPOINT_CHANGED')
    data=load_bundle(data_path)
    response={s:[r for r in rr if r['task']=='interruption_response'] for s,rr in data.items()}
    states={s:[r for r in rr if r['task']=='state_inference'] for s,rr in data.items()}
    # Validate train/dev state mapping before any test inference.
    for s in ('train','dev'):
        for row in states[s]: state_input(row['input'])
    words=vocabulary(data['train'],config['encoding'],config['vocab_size'])
    context=torch.load(io.BytesIO(context_path.read_bytes()),map_location='cpu',weights_only=True)
    torch.set_num_threads(config['threads'])
    selected=[];runs=[];start=perf_counter()
    seeds=config['evaluation_seeds'] if all_seeds else [config['seed']]
    for seed in seeds:
        payload,metadata=fit(response['train'],response['dev'],context,words,config,seed)
        selected.append(payload);runs.append(metadata)
    print('All response train/dev selections fixed; terminal test NLL and free generation.',flush=True)
    for payload,row in zip(selected,runs):
        model=reload_model(payload)
        row['response_test']=response_metrics(model,response['test'])
    model=reload_model(selected[0])
    report={'protocol':config['protocol'],'config':config,'executed_seeds':seeds,
            'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'])),
            'environment':{'python':sys.version,'torch':str(torch.__version__),'device':'cpu','threads':config['threads']},
            'response_counts':{s:len(r) for s,r in response.items()},'state_counts':{s:len(r) for s,r in states.items()},
            'vocabulary_size':len(words),'runs':runs,
            'model_sha256':hashlib.sha256(selected[0]).hexdigest(),
            'state_test':state_metrics(model,states['test']),
            'coverage':{s:coverage(model,r) for s,r in response.items()},
            'parameter_count':sum(p.numel() for p in model.parameters()),
            'trainable_parameter_count':sum(p.numel() for p in model.response.parameters()),
            'seconds':perf_counter()-start,'P1_behavior_truth_created':False,'P0_retrained':False,
            'scope':'P1 published-response distillation, P0 frozen-state routing; not human recovery or joint belief-learning performance'}
    if all_seeds: report['response_test_cross_seed']=aggregate([r['response_test'] for r in runs])
    output.mkdir(parents=True)
    (output/'model.pt').write_bytes(selected[0])
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    write_readme(report,output/'README.md')
    print('Response test:',runs[0]['response_test'],flush=True)
    print('Formal READY model:',output,flush=True)


def predict_file(checkpoint,data,limit):
    model=reload_model(checkpoint.read_bytes())
    raw=data.read_text(encoding='utf8')
    records=json.loads(raw) if data.suffix=='.json' else [json.loads(line) for line in raw.splitlines() if line.strip()]
    if isinstance(records,dict): records=[records]
    for row in records[:limit]:
        prediction=model.predict(row['task'],[row['input']])[0]
        print(json.dumps(prediction,ensure_ascii=False,allow_nan=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/a_ready_p1.json')
    parser.add_argument('--all-seeds',action='store_true')
    parser.add_argument('--predict',type=Path)
    parser.add_argument('--data',type=Path)
    parser.add_argument('--limit',type=int,default=3)
    args=parser.parse_args();torch.set_num_threads(1)
    if args.predict:
        if not args.data or args.limit<1: parser.error('--predict requires --data and positive --limit')
        predict_file(args.predict,args.data,args.limit)
    else: run(args.config.resolve(),args.all_seeds)


if __name__ == '__main__':
    raise SystemExit('Retired mixed/frozen-model entry. Use python -m models.ecr_mwm.p1_training for native P1 EC-JMF training and --predict inference. Historical response-only results are not EC-JMF ablations.')
