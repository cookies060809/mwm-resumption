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
P1：按团队2026-10-23决定仅采用公开派生数据，不再规划真人采集。新P1与P0的窗口、
任务语义及六因子掩码仍需对齐，不能将agent/机器人/规格数据写成真人效果。

旧A独立模型/参考训练/历史结果已移出当前分支，仍可在原A分支查看。
B的 `scripts/check_p0_release_a.py` 是历史Git-ref参考模型检查器，保留原样，
只应用于旧A历史引用；当前模型应使用本文件的新加载/预测入口。


## 公开派生 P1 的冻结模型试运行

`p1_adapter.adapt_input` 只接受交付input白名单，未提供的依赖保留None，未提供的理解/消息语义不猜。
背景接触可能属于用户而非助手，保守隔离；>8步、无步骤及无法忠实表达的自身全目标完成明确拒绝。
`python -m models.ecr_mwm.p1_evaluation --config configs/a_p1_public_probe.json` 复现准入和受控状态诊断。
固定H=1仅保证状态探针运行，不与P1回答轮次/帧窗口硬换算，因此不评分T1/T2。
只按真实state_loss_mask分源/actor/截断类型比较T3；回溯规则标签不当主观真值。
可用范围、零支持失败和单类高分限制见 `results/p1/a_context_public_probe/README.md`。
推荐ready-v1.0中的六变量记录仍是旧P0；下面的READY适配已为续答任务增加独立神经文本模块，不把它当新的P1六状态真值。


## READY-v1.0 正式两任务适配（2026-10-24）

遵循B `data/p1/public_derived/READY.md` 推荐的 `data/training_ready/v1`，读取其冻结分组与掩码。
内部模型格式 `a-ready-ec-jmf/v1`，完整保存Context、文本模块、train-only词表、编码配置与选模元数据。

```python
from pathlib import Path
from models.ecr_mwm.ready_model import reload_model
model = reload_model(Path('results/p1/a_ready_response/model.pt').read_bytes())
outputs = model.predict('interruption_response', [input_only_system_history])
# outputs[0]['response']，state_distributions/T1/T2均为None
states = model.predict('state_inference', [input_only_ready_state])
# states[0]['state_distributions']，不虚构缺失窗口的T1/T2
```

推理不读取record的target、messages、id或group。`messages`含末尾训练答案，只是B提供的训练视图。
续答来自公开GPT-4o Audio参考回答：仅其train用于优化、dev token NLL选模，最后test自由生成；
对话六状态mask全0，不推导人物信念/理解或恢复标签。system/history均是B声明可见的助手输入。
文本模块是独立辅助编码器/解码器，不将其混合表示写进结构化世界/人物状态；不宣称已完成文本信念更新。

state输入缺schema/horizon/完整interrupting_task，`ready_data.state_input`从显式事件识别主goal、
保留已见子目标图。缺失父子关系和未见步骤不猜，部分子图不会被宣布整体完成；原完整图默认行为不变。
H=1仅用于内部T3计算，不是P1窗口换算。READY的254条P0未重复拼接或重新训练。

响应采用train词表、role标记、attention-GRU生成。很长system仅保留头尾各96tokens，旧history预算320，
最新user打断完整保留；目标不截断。未知词与上下文截断量必须披露，NLL/PPL按UNK投影，
exact/token F1对完整参考token计算。生成用BOS开始、EOS结束，不使用参考答案作为decoder前缀。

复现入口：`python -m models.ecr_mwm.ready_training --config configs/a_ready_p1.json`。
正式实际结果以 `results/p1/a_ready_response/README.md` 与report.json为准，不能用可运行性代替续答质量。
C若接入此辅助任务应使用上述task路由/response字段；不把response转成p_resume、T1/T2或六状态分数。
