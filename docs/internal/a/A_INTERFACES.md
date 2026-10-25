# A：P1-only EC-JMF 内部接口

内部数据合同为 `p1-ec-jmf/v1`，保存格式为 `a-p1-ec-jmf/v1`。B 维护源数据/schema，C 维护公共评测/MENTIS；本文是 A 内部接口，不宣称公共 update 或 MENTIS 已三方冻结。当前主线不读取 P0、旧权重或旧 Git 对象。

## 数据与输入隔离

`p1_data.load_records(repository_root)` 读取实际 `processed/p1_combined.jsonl`，并且只用 READY `interruption_response` 记录建立 IH 对话分组；不会加载 READY 中 P0 记录作为训练样本。所有 IH actor 和窗口统一 conversation 分组，train/dev/test 为31/7/7组；REBOOT 保持 episode 分组，InterruptBench 为任务规格组。

每条训练 example 外层含 `id/split/source/window_kind/group/label_origin/input/target`；只有 `input` 进模型。目标为 `resume/step/states/steps`：恢复只取 mask=1，步骤只取 mask=1 且 gold 恢复为真；状态只接纳有监督 V。撤回的 F/A/B/C/Q 不进入损失。ID、分组、标签来源、未来结果和标签证据不能变成输入特征。

`p1_adapter.adapt_native(inputs, window)` 输出：

- `schema_version/adapter_version='p1-ec-jmf/v1'`，`goal_id='goal'`，原文目标与 `observer_graphs`；步骤不超过12，依赖未知保留 None，规格任务允许空图。
- `events` 截止于 `cutoff_event_id`，每项分别有 `world/person/delivery/semantic`、`available_text`、原始位置和 `native_kind/native_actor`。
- `world.description` 是实际事件文本；`person` 仅表示自身动作。`available_text` 可包含已交付外部话语，不把用户话语伪装成人物自身动作。
- `window` 为 `single_response/planned=1`、`assistant_turn/planned=4`、`episode_tail/planned=None` 或 `unobserved/planned=None`。原始帧/轮次位置不伪装分钟；不输入未来 episode 终点计算的时长。

IH 背景接触位属于用户，背景保守仅进世界；已交付用户话语可接触但理解不明。环境故障未见接收证据时保留不确定。`task_completed` 表示自身全目标完成，不能伪装他人完成。适配不读未来回复、rubric、withheld tail、state 答案或监督证据索引。

## 模型与训练 API

```python
from pathlib import Path
from models.ecr_mwm.p1_data import load_records
from models.ecr_mwm.neural_data import build_vocabulary
from models.ecr_mwm.neural_model import Batch
from models.ecr_mwm.p1_training import reload_model

examples = load_records('.')
model, vocabulary = reload_model(Path('results/p1/ec_jmf/model.pt').read_bytes())
batch = Batch(examples[:2], model.variant, semantic_contract='p1-ec-jmf/v1', vocabulary=vocabulary)
predictions = model.predict(batch, evidence=True)
```

上例要求正式模型已经生成；不是完成证明。推理实际前向只读取 example 的 `input`，训练目标在前向外构建监督索引。词表仅以 train 输入文本拟合，pad0/unk1，世界/人物词袋和 GRU 参数隔离。世界文本进入世界门，人物可得文本进入人物门，不能共享含后台事实的编码。

每事件四相依次处理世界、接触/理解、信念接受、人物动作。`JointState`/`StructuredModel`/`PackedTopology` 保留联合后验及各相位条件；最多12步，当前理解充分统计及人物可得信息与 B/C/Q 分开。有界中断栈结构保留，但 P1 没有子任务身份/父目标关系，本轮不编造嵌套图。

完整训练入口：

```text
python -m models.ecr_mwm.p1_training --config configs/a_ec_jmf_p1.json
python -m models.ecr_mwm.p1_training --predict results/p1/ec_jmf/model.pt --split test --source IHBench --limit 3
```

配置的正式协议为 A0–A6、40轮、seed0–19；`--seed` 是单种子运行，不能当20种子证据。所有参数从随机初始化，通过真实 PyTorch 自动微分与 AdamW 更新。开发集按来源/窗口等权的有效 V NLL、恢复 BCE 和条件步骤 NLL选模，包含初始化、最早并列优先；所有选模完成才评分 test。历史测试已暴露，不称新盲测。

最终模型保存架构、全权重、词表、配置与选模元数据；独立重载不依赖历史对象。正式输出只保留 `results/p1/ec_jmf/{model.pt,report.json,README.md}`，不以配置存在证明正式实验已完成。

## 输出、消融与结论范围

`predict` 返回 `t1/t2/t3/understanding/window/state_supervision_scope/latent_state_warning`；空步骤规格任务没有可定义的 T1/T2。T1 是源窗口内恢复代理概率；T2 是恢复条件下的步骤分布，零质量未定义。T3 是 V/F/A/B/C/Q 边际，understanding 单独给 U；只有 mask 开启的 V 有直接 P1 状态监督，其他因子是潜变量诊断。

`evidence=True` 增加逐事件状态传播轨迹；它说明模型如何传播条件状态，不等于自然语言推理正确或人类信念真值。相应指标按来源/窗口分报，不能混合 P0；IH 弱监督、REBOOT 只有正恢复标签，不能泛化为人类预测。

A1 取消接触/理解门，A2 因子化 B/C/Q，A3 最近5个人物事件，A4 去掉时间因果事件一致性，A5 去掉步骤损失但保留头，A6 固定转移门。事件一致性用动作前状态预测下一已观测人物动作及已有步骤，不重复乘进后验，不伪造 B/C/Q 金标。执行报告应记录真实有效监督和梯度路径，未训练的变体不得写成已有结果。

C 接入仍需明确：原生窗口类型、空图 V-only 路由、U 与潜变量监督范围、条件 T2 缺失处理、逐事件轨迹及公共 update/MENTIS 版本。A 内部 API 不擅改 C 的字段或协议。B 若要支持理解/信念或嵌套任务的直接评测，需要提供对应可追踪标注和主体/父目标关联；本轮不为此虚构字段。

## 历史说明

原 P0、C frozen-context、READY 独立续答与原/C配对报告属于先前实验。独立续答模块未消费结构状态，其相同分数不能检验结构消融；历史 checkpoint/训练入口不属于当前 P1-only 复现链，不应按旧文档调用当前已修改的主模型代码。

明确恢复事件与普通进度分开：REBOOT 截止前已经观察到的 `resume` 支持重新进入 ACTIVE 并更新当前步骤，即使先前潜状态为放弃或完成；普通 progress 不自动解除终止承诺。该转移不强制改写信念为 BELIEVES_VALID，也不把被屏蔽的恢复窗口样例作为未来恢复监督。
