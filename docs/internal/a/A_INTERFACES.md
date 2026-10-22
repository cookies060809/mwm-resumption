# A 完整上下文模型接口

当前内部接口为 `a-context-ec-jmf/v1`，不宣称公共M1已三方冻结。
B维护数据/schema，C维护公共评测/MENTIS。本分支只部署 `ContextECJMF`。

## 输入与状态

`adapt_record` 保留 v0.1/v0.2 读取兼容；当前训练使用完整 P0 v0.3发布版，记录schema仍为v0.2。
白名单排除notes、annotation、p0_design、state_*、p0_expected*、p0_scripted_policy和p1_*；
ID、family、split、mechanism仅留监督/审计外层，不进模型特征。
`interrupting_task`仅取身份、父目标和步骤，status_at_cutoff不进人物心智。
理解字段完整保留 UNDERSTOOD / MISUNDERSTOOD / NOT_UNDERSTOOD / UNCERTAIN，
理解不明不转成误解；接触不确定保留概率假设，采信另有门控。

`Batch([{'input': adapt_record(raw)}])` 编译有限状态支持。世界/人物GRU隔离，
状态分别保存世界事实、人物可得信息、理解、B、C、主客观进度、步骤记忆和有界中断结构。
最多8目标、4层中断、8候选步骤；状态超预算明确报错。
原目标记忆不因中断清空，不把观察者图当人物知识，不额外重复计动作似然。

沿用 b-p0-v03/v3：完成与取消分开；终止后孤立动作保留再投入不确定性；
自身物理中断不依赖消息理解；承诺不等于当前活动；未关联消息不猜目标。
P04采信他人完成为BELIEVES_VALID、COMPLETED（有效不代表仍需执行）。

## 完整加载、训练与保存

```python
from pathlib import Path
from models.ecr_mwm.neural_training import reload_model, read_checkpoint, fit_one
from models.ecr_mwm.neural_model import Batch

payload = Path('results/p0/c_visible_context/model.pt').read_bytes()
model = reload_model(payload)  # 全部权重；不查找旧checkpoint
prediction = model.predict(Batch(input_only_examples), evidence=True)
# fit_one(train_batch, dev_batch, seed, config, read_checkpoint(payload))
# -> 自包含checkpoint bytes及开发集选模元数据
```

保存格式携带 architecture、完整state_dict、seed、selected_epoch、config、provenance；
严格加载，未知/旧模型格式拒绝。ContextECJMF是唯一部署模型，私有骨干仅为其实现组件。
训练按C方法冻结骨干，重初始化上下文注意力/残差，真实自动微分40轮、dev选模、保存重载。
不是全骨干从零训练；现有完整权重已包含重建初始冻结骨干所需参数。
`seed`用于一次训练；`--all-seeds`才展开固定0–19。C原实验只有0–4。
默认不做test推理，`--evaluate-test`在所有dev选择后显式计算，不能用于选择模型。
复现命令见 `results/p0/c_visible_context/README.md`。

## 输出和监督口径

- T1：H个机会内恢复概率，阈值0.5；报告F1/AUROC/AP/Brier/ECE10。
- T2：恢复条件下未来未完成原目标步骤分布；它可能随新hazard的状态混合权重变化，
  gold恢复且首步有效才评分，缺失计错。这不是C端到端发出步骤的准确率。
- T3：V/F/A/B/C/Q边际；Q按图内位置。监督只取非UNKNOWN且有cutoff有效证据。
- 证据：逐事件结构化状态轨迹，不解释新增注意力对行为预测的贡献。

indeterminate/null/undefined_reason保留为遮蔽，不转负例；other_completion和嵌套动作
按原目标未来推进定义处理。不按gold证据ID补输入，不为结构零支持删除目标。
当前A焦点映射仍是代理，六因子原始值不作为已对齐B全标签的总体成绩。

## 仍待团队确认

B：模型可读关键事件焦点、消息目标关联和下一步资源条件；自由文本相位及P02事件措辞仲裁。
C：完整理解枚举与嵌套图的无损输入、公共update/MENTIS、T2条件与发出步骤口径、
逐因子证据和A焦点字段、统一阈值/预算/失败处理。此次不改C模块。
P1：合法来源、观察窗口与删失证据、真实行为标签、人物/任务族划分、独立校准集。

旧A独立模型/参考训练/历史结果已移出当前分支，仍可在原A分支查看。
B的 `scripts/check_p0_release_a.py` 是历史Git-ref参考模型检查器，保留原样，
只应用于旧A历史引用；当前模型应使用本文件的新加载/预测入口。
