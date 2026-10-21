# A 算法接口与 P0 适配说明

A 内部版本：`a-structured/v0.2.0`。B 拥有数据/schema，C 拥有评测、公共协议和 MENTIS 集成；以下入口是可运行的 A 内部 API，不宣称 M1 已三方冻结。

## 输入与版本

`adapt_record(raw) → infer(adapted) → prediction`。正式数据应先通过 B 的完整校验；适配器另外检查所选输入的时序、cutoff、ID、DAG和引用。

- 显式接受 `p0-record/v0.1.0` / `p0-record/v0.2.0`，拒绝未知版本。v0.1 的理解保留 `not_structurally_labeled`；不凭文本补造语义。
- v0.2 `person_comprehension` → `delivery.comprehension`；`person_available_semantics.kind/value/interpretation` → 独立 `semantic`。后者是可能收到的消息内容，须经接触及理解分支才能影响心智。
- 模型白名单排除 `p0_design`、notes、annotation、state_*、p0_scripted_policy、p0_expected*、p1_*；sample_id/variant/base_story_id/split/mechanism仅留在监督/评测外层。事件内部也用白名单。
- `interrupting_task` 只取 task_id、goal_id、parent_goal_id、steps。status_at_cutoff和完成快照不读；嵌套进度从事件重放，缺失依赖保持None。
- 外部混合叙事/source/world_effect留世界审计侧；人物本人动作/陈述单独保留。当前转移不解析自由文本，也不用关键词玩具规则代替语义模型。
- `person_inputs`隔离世界载荷，屏蔽明确未接触的内容，并保留可用语义的目标归属和中断阶段，供严格信息等价检查。它是证据视图，不是“人物已经理解”的断言。
- HH:MM转同日分钟，仅支持正整数决策机会窗口；不捏造日期、获知时刻或P1观察覆盖。

## 状态更新与预测

`models/ec_jmf/structured.py` 的 `StructuredModel` 提供与现有 ExactFilter/ParticleFilter 相同的 `transition` / `log_likelihood` 协议。状态可哈希，世界和心智字段分离：每目标维护V/F、客观完成集合、人物接触信息、事件理解假设、B/C、人物完成集合、步骤记忆、Q、等待状态；全局维护人物动作支持的嵌套任务占用栈。默认最多8个目标、4层占用，超限失败；当前B适配器实际只提供原目标与一个子目标。

动作在条件转移中使用，额外动作似然为0，避免重复计证。未接触的世界变化不能触发人物进度重新推断；不确定接触/理解保留多分支。UNDERSTOOD也不自动等于采信；MISUNDERSTOOD按已给解释更新，NOT_UNDERSTOOD不直接改变信念。分支概率是可训练的参考假设，未训练默认值不是人类心理频率。

保留原目标记忆；插入任务不清空它。返回工作位、结束外部打断不自动成为实际恢复或完成嵌套任务。世界完成与人物完成分别重放，不用world_done删除当前Q。未提供可信 `person_graphs` 时不把观察者图复制为人物已知图；图只能提出“人物可能记得下一步”的潜在假设，同时保留UNKNOWN。若调用者提供人物图，必须另有事前证据。Q仍不是未来T2。

```python
from models.ecr_mwm.p0_adapter import adapt_record
from models.ecr_mwm.structured import infer

run = infer(adapt_record(raw_record), method="exact")
payload = run["prediction"]
# 推断扩展：method="smc", particles=128, seed=0
```

返回prediction、内部posterior和model；只有prediction是对外交接候选JSON。prediction含T1/T2/T3、逐事件前后边际/ESS/重采样、证据ID、辅助理解分布和实测CPU耗时/转移次数；无LLM调用，tokens=0。证据包含观察证据与模型假设的传播，不等于心理真值证明。`uncertainty.calibrated=false`。

- T1：可学习的单机会hazard扩展为 `1-(1-h)^H`，再对联合后验边缘化。
- T2：未来未完成原目标步骤的softmax，使用Q、已知步骤和依赖等特征；不是复制Q。客观已完成步骤不计未来推进（研究计划§3.4），此mask不改心智。`p=Σwr`，`q(k)=Σwr s(k)/p`；p=0时T2=None并有status。
- T3：V/F/A/B/C/Q后验边际。A目前跟踪按输入选出的最近显著事件，不能宣称自动复现B的“对照关键事件”标签规则；这项汇总映射待B/C确认。
- F仅由明确资源证据更新，不从早先完成一个步骤推出所有后续资源READY。未解析人物陈述或未掌握完整任务图时可能保留UNKNOWN/多假设。

## 监督、训练与消融

`scripted_targets`只在模型外读脚本目标。indeterminate + null + undefined_reason=indistinguishable_inputs遮蔽T1/T2，保留原因；不把None转False。只有resume=true且未来首步在原图且未客观完成时启用v0.2的T2。P04他人完成后的重复不算恢复，P06嵌套下一动作保留审计但不是原目标T2。v0.1维持旧语义和旧兼容检查，不用新口径重写种子标签。

`models/ecr_mwm/training.py`：

```python
from models.ecr_mwm.training import p0_example, fit
examples = [p0_example(r) for r in records if r["split"] == "train"]
state_fit = fit(examples, stage="state", epochs=1, seed=0)
joint_fit = fit(examples, stage="joint", epochs=1, seed=0,
                transition_parameters=state_fit["transition_parameters"])
# 返回参数与损失历史到内存；调用者决定正式检查点/运行记录的保存。
```

这是无新增依赖的小状态精确参考训练器：中央差分梯度下降，固定结构语义，学习转移门控/采信、承诺分支、步骤记忆与行为头系数。计算成本为每参数每轮两次目标计算，尚无神经文本编码器、可扩展自动微分或可微SMC。不用算法规则捏造事件级心理标签；state阶段用有证据的cutoff状态监督转移。输入U在当前P0是结构化证据，不把它当独立理解预测成绩。

损失包含逐因子有证据且非UNKNOWN的state NLL、T1 BCE、条件T2 NLL、严格信息等价的联合(B,C,Q) JS、隐蔽世界干预的knowledge JS、主观完成/终止与Q冲突代价。各项按实际可用数归一；零支持标签以固定概率下限计算并单独计入unsupported_state_targets，不能声称该参数化能拟合所有标签。配对须调用者确认同心智先验/无旁路线索，并通过输入视图与图等价检查；不因机制名相同自动配对，不约束世界或T1必须相同。A0结构约束可使JS/冲突项恒零，不能据此宣称约束训练有效。

只允许同一数据层的train样本进入fit；开发/测试/校准由外部管理。P0训练要求reviewed/adjudicated；v0.3现已reviewed，本轮神经主实验不合并该小批。`observed_targets`预备P1删失掩码：已观测恢复可用正例，未恢复且窗口不完整遮蔽；原始P1字段映射和可靠状态证据仍待B/C。P0监督与P1真实行为不混合。

`ABLATIONS`提供A0及A1去接触/理解门控、A2去B→C与终止C→Q耦合、A3最近窗口替代持久记忆、A4去一致性项、A5去步骤辅助损失、A6固定参考门控。A2不是完整独立BCQ基线，A3不是学到的遗忘机制；A7等量历史和完整对比实验归C，尚未执行。

## 与 C 待确认的具体交接

已只读核对 `origin/Bill` 的C草案与 `integration/a_output_adapter.py`，未修改/合并C文件。

1. 输入仍有损：C的understood=false合并MISUNDERSTOOD与NOT_UNDERSTOOD；A需要保留完整U及误解解释，需决定扩展原U还是显式无损还原。不能默默把false统一当误解。
2. C observation目前只有原目标图；嵌套目标身份/父目标/完整steps如何传入尚需定稿。不能靠cutoff快照补心智，也不能按原目标goal_id制造假子任务。
3. A内部infer接受版本化适配输入；C的predict(observation)、fit(train_pairs)、spec/availability、公共update(prior_belief,...)及stdin/stdout命令包装由双方冻结后对接。本轮未替换C的B10入口。
4. A输出字段与C现有normalize_a_output基本相合，仍需C确认p=0的T2=None、A关键事件汇总、逐因子证据/辅助U字段如何保留、阈值/概率覆盖、预算和错误处理。内部posterior/model不送C JSON。
5. C文档记录的MENTIS候选SHA是7c6ea55e007a64233c3a0f987b6d229476f3fdf6；本轮未核验官方checkout。正式锁定版本、模型/命令/seed控制、调用预算与等量上下文对照仍需C完成，不能称已接入或复现。
6. P1仍需B的授权数据/schema/时间与删失证据，以及C的人物/任务族划分、独立校准集、公平基线/预算。真实效果、校准和泛化结论尚不可得。


## 神经训练与复现（a-neural-p0/v1）

正式入口 `python -m models.ecr_mwm.neural_training --config configs/a_neural_p0.json`，独立依赖 `requirements-neural.txt` 固定PyTorch 2.11.0。世界/人物GRU隔离，神经网络输出接触/理解/采信、承诺与记忆等命名门控，PyTorch在现有有限状态支持上精确边缘化并自动微分；旧中央差分与float精确/SMC核保留作参考，不冒充神经训练。F初始分布是独立可学习的世界先验。

主批为最新修正v0.2（144/48/48），v0.3现已reviewed，仅作冻结模型补充诊断。预先固定A0–A6、种子0–19、40轮全批AdamW、统一dev masked state+T1+T2 NLL选模规则；所有选模结束才评价test。T1阈值0.5/ECE10，T2条件掩码，T3非UNKNOWN且有cutoff证据；Q按图内位置评分。完整协议在配置，正式生成产物集中于 `results/p0/a_neural_v1/`。

A2使用独立BCQ后验而非旧局部开关；A3丢弃人物近5事件以前记忆但保留世界重放；A4去实际事件语义软对齐和严格信息等价联合JS；A5去训练步骤损失而仍评价；A6固定结构转移门控，但保留共同可学习世界先验/行为头。严格等价JS可能由结构保证为零，不能宣称验证全部认识损失。模型只编码结构化类别，不学习自然语言解析，输入U不是理解识别成绩。

每次选中模型均实际torch.save/load并检查T1/T2/T3一致，仅保留预指定A0 seed0的最终模型。`--predict <checkpoint> --data <P0 JSON>`从输入白名单预测并导出新模型自己的逐事件后验/理解证据轨迹，不读取监督作为特征。公共C update/MENTIS接口未替换。

对于B手册的16条信念争议，A建议将“愿意继续”首先视为C证据，除非明确表达目标有效性，否则不足以确定B；现阶段保持UNKNOWN掩码，不自行改B数据，需B/C共同统一手册和仲裁。真实P1行为、独立校准及公平MENTIS比较仍待交付。


## B P0 v0.3语义纠偏：b-p0-v03/v2

本轮按B反馈修正两处，不宣称所有文本或关键事件语义均已解决：

- **P04完成与取消分开。** 对收到、理解且采信的`completion_by_other`，按B的P0操作性约定更新`B=BELIEVES_VALID`、`C=COMPLETED`及主观完成集合；Q由完成约束归为`NOT_APPLICABLE`。这里VALID不表示仍需执行，也不表示完成与有效在一般逻辑中等价。取消消息仍走`BELIEVES_INVALID`；其他`interpretation=complete`误解不顺带改标。
- **P02动作与重新承诺分开。** 已`ABANDONED/COMPLETED`后观察到孤立`step_started/step_attempted`，不再强制覆盖整个目标的承诺。用`recommit_goal`门保留“终止仍成立、Q不适用”及“已重新承诺、ACTIVE及相应步骤”两种假设。A6固定该门为0.5，A2仍由独立BCQ头表示状态，其余按原消融训练。事件本身确实发生，分支不把它删掉或改成别的动作。

事件标签冲突并未因模型支持扩大而自动仲裁：原数据中14条“放弃后开始步骤”的序列仍需B明确事件措辞与目标层承诺含义。A不改B的数据/schema/标注，不按样本ID或gold状态修补，也不删除这14条监督或修改评价掩码。自由文本、自述、物理中断与null goal作用域，以及A关键事件汇总仍有已披露覆盖限制。

新入口为`configs/a_neural_p0_v03_aligned.json`，数据仍为完整254条、150/52/52。语义修正来自已暴露的诊断冲突，是事后修订，不称新盲测；各20种子/40轮、dev选择、指标和掩码沿用。结果单独写`results/p0/a_neural_v03_v2/`，未重跑前不得把旧分数称为修正后成绩。

旧配置默认`legacy-v1`、旧v1 checkpoint严格加载9门网络并重现原拓扑；新版checkpoint为`a-neural-ec-jmf/v2`，显式保存`b-p0-v03/v2`并加载10门网络。Batch/模型契约不符时拒绝执行，预测CLI从checkpoint恢复契约。旧参考推断默认仍为历史语义，不替换C公共接口。新增门改变参数化和随机初始化序列，不将新旧分数差归为语义修复的独立因果收益。
