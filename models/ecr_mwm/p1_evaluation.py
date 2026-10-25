"""Frozen-model P1 admission and masked structural-state diagnostic.

No P1 training, text-label generation, test selection or recovery-window metric.
Run: python -m models.ecr_mwm.p1_evaluation --config configs/a_p1_public_probe.json
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft7Validator
import torch

from models.ecr_mwm.neural_model import Batch
from models.ecr_mwm.neural_training import reload_model
from models.ecr_mwm.neural_metrics import evaluate
from models.ecr_mwm.p1_adapter import adapt_input

ROOT = Path(__file__).resolve().parents[2]
FACTORS = 'VFABCQ'
INPUT_KEYS = ('goal_text', 'task_steps', 'observed_events')
EVENT_KEYS = ('event_id', 'event_type', 'step_id', 'actor', 'text', 'position', 'person_access', 'source')


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def input_view(record):
    return {'goal_text': record['goal_text'], 'task_steps': record['task_steps'],
            'observed_events': [{k: e.get(k) for k in EVENT_KEYS} for e in record['observed_events']]}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(rows, config):
    validator = Draft7Validator(json.loads((ROOT / config['schema']).read_text(encoding='utf8')))
    ids, groups, by_id = set(), {}, {}
    for row in rows:
        validator.validate(row)
        sid = row['sample_id']
        if sid in ids: raise ValueError('P1_DUPLICATE_SAMPLE')
        ids.add(sid); by_id[sid] = row
        key = row['source_dataset'], row['split_group_id']
        if key in groups and groups[key] != row['split']: raise ValueError('P1_GROUP_CROSSES_SPLITS')
        groups[key] = row['split']
        events = row['observed_events']
        if not events or events[-1]['event_id'] != row['cutoff_event_id']: raise ValueError('P1_CUTOFF_NOT_LAST')
        if len({e['event_id'] for e in events}) != len(events): raise ValueError('P1_EVENT_IDS_NOT_UNIQUE')
        positions = [e['position'] for e in events if e.get('position') is not None]
        if len({p['unit'] for p in positions}) > 1: raise ValueError('P1_MIXED_POSITION_UNITS')
        values = [p['value'] for p in positions]
        if values != sorted(values): raise ValueError('P1_UNORDERED_HISTORY')
        for factor in FACTORS:
            active = row['state_loss_mask'][factor]
            if active != int(row['state_at_cutoff'][factor] != 'UNKNOWN'): raise ValueError('P1_STATE_MASK_MISMATCH')
            if active and not row['label_origin'][factor]: raise ValueError('P1_STATE_WITHOUT_LABEL_ORIGIN')
        if row['p1_censoring_status'] == 'censored' and row['p1_observed_resume'] is not None:
            raise ValueError('P1_CENSORED_NOT_NULL')
        if row['resume_loss_mask'] and (not row['eligible_for_resume_eval'] or
                row['cutoff_kind'] != 'interruption' or row['p1_observed_resume'] is None):
            raise ValueError('P1_INVALID_RECOVERY_MASK')
        if row['resume_loss_mask']:
            cutoff_position = events[-1].get('position')
            outcome = row['outcome_time']
            if (not cutoff_position or not outcome or outcome['unit'] != cutoff_position['unit']
                    or outcome['value'] <= cutoff_position['value']
                    or outcome.get('event_id') in {e['event_id'] for e in events}):
                raise ValueError('P1_OUTCOME_NOT_STRICTLY_AFTER_CUTOFF')
        if row['step_loss_mask'] and (not row['resume_loss_mask'] or
                row['p1_observed_resume'] is not True or row['p1_resume_step'] not in row['task_steps']):
            raise ValueError('P1_INVALID_STEP_MASK')
    # Read the delivered input-only view, never regenerate B's files.
    manifest = json.loads((ROOT / config['aux_view'] / 'manifest.json').read_text(encoding='utf8'))
    exported = set()
    for name, meta in manifest['files'].items():
        path = ROOT / config['aux_view'] / name
        if sha(path) != meta['sha256']: raise ValueError('P1_AUX_HASH_CHANGED')
        items = read_rows(path)
        if len(items) != meta['rows']: raise ValueError('P1_AUX_COUNT_CHANGED')
        for item in items:
            sid = item['supervision']['sample_id']
            if sid in exported: raise ValueError('P1_AUX_DUPLICATE_SAMPLE')
            exported.add(sid)
            if item['input'] != input_view(by_id[sid]): raise ValueError('P1_AUX_INPUT_MISMATCH')
            if set(item['input']) & set(item['supervision']): raise ValueError('P1_INPUT_SUPERVISION_OVERLAP')
    if exported != ids: raise ValueError('P1_AUX_COVERAGE_MISMATCH')
    return {'schema_rows': len(rows), 'unique_ids': len(ids), 'group_units': len(groups),
            'group_split_violations': 0, 'aux_projection_rows': len(exported), 'aux_files': len(manifest['files'])}


def source_summary(rows):
    return {'rows': len(rows), 'splits': dict(Counter(r['split'] for r in rows)),
            'groups_per_split': {s: len({r['split_group_id'] for r in rows if r['split']==s}) for s in ('train','val','test')},
            'cutoffs': dict(Counter(r['cutoff_kind'] for r in rows)),
            'state_mask_counts': {f: sum(r['state_loss_mask'][f] for r in rows) for f in FACTORS},
            'recovery_mask_count': sum(r['resume_loss_mask'] for r in rows),
            'step_mask_count': sum(r['step_loss_mask'] for r in rows),
            'censored_count': sum(r['p1_observed_resume'] is None for r in rows)}


def target(row):
    # Evaluate supported state annotations only. Recovery is intentionally undefined.
    return {'resume': None, 'step': None, 'steps': row['task_steps'],
            'states': {f: row['state_at_cutoff'][f] for f in FACTORS if row['state_loss_mask'][f]}}


def state_metrics(rows, predictions):
    result = evaluate([predictions[r['sample_id']] for r in rows], [target(r) for r in rows])['t3']
    return {'n_rows': len(rows), 'independent_groups': len({r['split_group_id'] for r in rows}),
            'gold_classes': {f: dict(Counter(r['state_at_cutoff'][f] for r in rows if r['state_loss_mask'][f])) for f in FACTORS},
            'predicted_classes': {f: dict(Counter(max(predictions[r['sample_id']]['t3'][f],
                  key=predictions[r['sample_id']]['t3'][f].get) for r in rows if r['state_loss_mask'][f])) for f in FACTORS},
            't3': result}


def write_readme(report, path):
    lines = ['# A 新模型：公开派生 P1 准入与受控状态诊断', '',
             f"分支 `{report['branch']}`；A模型基线3828635，合入main `{report['config']['source_main']}`。",
             '模型冻结，无P1拟合、调参、选模或校准。P1包含agent/规格/机器人，不是真人恢复行为。', '',
             '## 数据与输入准入', '',
             '|源|总数|可保守映射|test可映射|test独立组|', '|---|---:|---:|---:|---:|']
    for source, info in report['sources'].items():
        admitted = info['admission']
        lines.append(f"|{source}|{info['data']['rows']}|{admitted['compatible']}|{admitted['test_compatible']}|{info.get('test',{}).get('independent_groups',0)}|")
    lines += ['', '逐源test排除原因：' + '；'.join(src+': '+str(info['admission']['test_excluded']) for src,info in report['sources'].items()) + '。',
              '全部mask覆盖和数据哈希见同目录report.json。空步骤不补虚拟任务、超8步不截断；',
              '自身全目标completion无法用旧事件词表忠实表达，拒绝而不冒充他人完成。未提供依赖图时保留None。',
              '只取交付input白名单；目标/事件自由文本不被当前模型理解。IH背景access可能表示用户知情，',
              '故背景内容全部留世界侧；外部事件的接触/理解保留不确定，不从observer注释补造UNDERSTOOD。', '',
              '## 冻结test的主要状态对照', '',
              '|源|因子|n|准确率|macro-F1|零支持|', '|---|---|---:|---:|---:|---:|']
    for source, info in report['sources'].items():
        for f in 'VC':
            m = info.get('test',{}).get('t3',{}).get(f)
            if m and m['n']:
                lines.append(f"|{source}|{f}|{m['n']}|{m['accuracy']:.4f}|{m['macro_f1']:.4f}|{m['zero_support']}|")
    access = report['sources'].get('REBOOT',{}).get('test',{}).get('t3',{}).get('A')
    if access and access['n']:
        lines += ['', f"明确失败：REBOOT恢复截断点的A标签n={access['n']}，accuracy={access['accuracy']:.4f}，"
                  f"zero_support={access['zero_support']}。当前事件显著性A代理与该包从恢复行为确定接触的焦点不相同，"
                  '该桥接未覆盖这些标签，不把它们隐藏或移出分母。']
    lines += ['', 'V/C是受限映射下的注释一致性诊断，不是跨域恢复预测有效性证明。',
              'F/A/B/Q次级规则/回溯状态对照、逐actor/截断类型结果及类别分布见report.json；不合成六因子总分。',
              '可映射IH test只剩1个对话组：V全VALID、C全SUSPENDED；REBOOT的V全VALID、C全ACTIVE。',
              '常量标签上的高分不体现区分能力；无监督或零可映射样本的指标留空。', '',
              '## 不计算的成绩与已查明的问题', '',
              'C新增上下文残差主要影响T1，T3骨干冻结；本次T1不能可靠评分，因此没有评价新模型相较旧模型的收益。',
              'T1/T2均不评分：P0的decision opportunities与P1的assistant_turn/single_response/episode_tail没有可信换算；',
              '不把未来covered、outcome_time或episode长度输入hazard。固定H=1只让状态探针可运行，不是P1校准窗口。',
              '任务依赖、理解和消息语义未完成对齐，T2还缺原目标未完成步骤的可靠映射。',
              'REBOOT只有恢复正例，且recovery/completion截断本身已含结果，不可混入盲恢复预测。',
              'IH两个行为者共用前缀而标签不同，分别报告；aux test仅3个对话组，不能作稳定泛化结论。', '',
              'main的READY.md推荐ready-v1.0：其中254条state_inference就是既有P0（非新P1），',
              '428条IHBench是已发布baseline的续答蒸馏文本，当前T1/T2/T3模型无文本生成输出；不伪造续答成绩。',
              'ready包现有check.py离线重建与来源/分组/掩码检查已通过；aux REBOOT train现有掩码检查通过。',
              '公开派生README/dataset_card仍混有v1.5旧断言，实际p1-0.2以state_loss_mask和撤回记录为准。',
              '原merge_and_validate.py及转换器导入不存在的split_for（p1_common.py现为split_map/apply_splits），',
              '原校验/重建入口阻塞；本轮未改B文件，独立执行JSON schema、分组、cutoff、mask与aux投影/哈希核验。', '',
              '## 实际检查与复现', '',
              f"数据准入检查 {report['validation']['schema_rows']} 条通过；train输入smoke、隐藏背景扰动和监督隔离通过。",
              '仅使用改进后的完整模型；不恢复旧方法、不更新权重，不新建永久测试或临时日志。', '',
              '```bash', 'python -m models.ecr_mwm.p1_evaluation --config configs/a_p1_public_probe.json', '```', '',
              '结果仅保留一份report.json和本文；未推送或合并main。', '',
              '后续可做：B修复交付脚本及更新数据说明；A/C明确事件语义、actor接触、任务图与窗口映射，',
              '再在训练/开发集实现和选择真正P1适配。真人采集已按团队2026-10-23决策取消，不再把它列为待采集条件。']
    path.write_text('\n'.join(lines)+'\n', encoding='utf8')


def run(config_path):
    config = json.loads(config_path.read_text(encoding='utf8'))
    if config['evaluation_split'] != 'test' or config['t1_evaluation'] or config['t2_evaluation']:
        raise ValueError('FROZEN_STATE_PROBE_PROTOCOL_REQUIRED')
    model_path, data_path = ROOT/config['model'], ROOT/config['data']
    if sha(model_path) != config['expected_model_sha256'] or sha(data_path) != config['expected_data_sha256']:
        raise ValueError('FROZEN_INPUT_CHANGED')
    torch.set_num_threads(1)
    rows = read_rows(data_path)
    validation = validate(rows, config)
    model = reload_model(model_path.read_bytes())
    compatible, reasons = {}, {}
    for row in rows:
        try: compatible[row['sample_id']] = adapt_input(input_view(row), config['probe_opportunities'])
        except ValueError as exc: reasons[row['sample_id']] = str(exc)
    # Smoke only train inputs before the terminal test pass. No labels are fed.
    smoke = [r for r in rows if r['split']=='train' and r['sample_id'] in compatible]
    smoke = [next(r for r in smoke if r['source_dataset']==src) for src in sorted({r['source_dataset'] for r in smoke})]
    for row in smoke:
        view = input_view(row)
        perturbed = deepcopy(view)
        for event in perturbed['observed_events']:
            if event['event_type']=='background_fact':
                event['text'] = 'hidden perturbation'
                event['person_access'] = 'ACCESSED' if event['person_access']=='NOT_ACCESSED' else 'NOT_ACCESSED'
        perturbed['state_at_cutoff'] = {'B':'BELIEVES_INVALID'}
        left, right = adapt_input(view), adapt_input(perturbed)
        if left != right: raise ValueError('P1_HIDDEN_OR_SUPERVISION_INPUT_LEAK')
        out = model.predict(Batch([{'input':left}]), evidence=True)[0]
        if not out['evidence_trace'] or not 0 <= out['t1'] <= 1: raise ValueError('P1_SMOKE_FAILED')
    test = [r for r in rows if r['split']=='test' and r['sample_id'] in compatible]
    predictions = {}
    for start in range(0,len(test),32):
        chunk = test[start:start+32]
        native = model.predict(Batch([{'input':compatible[r['sample_id']]} for r in chunk]))
        predictions.update({r['sample_id']:p for r,p in zip(chunk,native)})
    report = {'protocol': config['protocol'], 'config': config,
              'branch': subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
              'code_commit': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'working_tree_dirty': bool(subprocess.check_output(['git','status','--porcelain'])),
              'environment': {'python':sys.version,'torch':str(torch.__version__),'device':'cpu','threads':1},
              'validation': validation, 'train_smoke_rows':len(smoke), 'sources':{},
              'T1_metrics':None,'T2_metrics':None,'P1_training':False,
              'scope':'Frozen-model masked state agreement under a conservative lossy bridge; not recovery prediction or human performance'}
    for source in sorted({r['source_dataset'] for r in rows}):
        source_rows = [r for r in rows if r['source_dataset']==source]
        admitted = [r for r in source_rows if r['sample_id'] in compatible]
        tested = [r for r in admitted if r['split']=='test']
        info = {'data':source_summary(source_rows),
                'admission': {'compatible':len(admitted), 'test_compatible':len(tested),
                              'excluded':dict(Counter(reasons[r['sample_id']] for r in source_rows if r['sample_id'] in reasons)),
                              'test_excluded':dict(Counter(reasons[r['sample_id']] for r in source_rows if r['split']=='test' and r['sample_id'] in reasons))}}
        if tested:
            info['test'] = state_metrics(tested,predictions)
            groups = defaultdict(list)
            for row in tested:
                actor = row['actor_id'].rsplit(':',1)[-1]
                groups[(actor,row['cutoff_kind'])].append(row)
            info['test_by_actor_cutoff'] = {actor+'/'+kind:state_metrics(rr,predictions) for (actor,kind),rr in sorted(groups.items())}
        report['sources'][source] = info
    output = ROOT/config['output']; output.mkdir(parents=True,exist_ok=True)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    write_readme(report,output/'README.md')
    for source,info in report['sources'].items():
        print(source, 'mapped',info['admission']['compatible'],'test',info['admission']['test_compatible'],
              'V/C', {f:info.get('test',{}).get('t3',{}).get(f) for f in 'VC'})
    print('Formal state diagnostics:',output)


if __name__ == '__main__':
    raise SystemExit('Retired mixed/frozen-model entry. Use python -m models.ecr_mwm.p1_training for native P1 EC-JMF training and --predict inference. Historical response-only results are not EC-JMF ablations.')
