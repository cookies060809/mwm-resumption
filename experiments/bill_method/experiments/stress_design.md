# 固定 P0 上下文压力测试 v1

本文件说明 `stress_transforms.py` 的固定变换。原实验使用独立副本；本分支打包后从仓库根目录加载同一原始实现和数据，不修改它们。这些测试检查符号命名不变性、不可见无关记录干扰与长输入稳定性；不代表真实人物、真实视频或跨数据集泛化性能。

## API

```python
renamed = transform_example(example, "rename_ids", 1)
long10 = transform_example(example, "invisible_noops", 10)
long30 = transform_example(example, "invisible_noops", 30)
```

输入是 `models.ecr_mwm.neural_data.load_records()` 产生的单条 example。返回深拷贝，保留样本 ID、family、split、mechanism 便于配对。变换只根据 input 和指定 level 决定；重命名的输出标签随后按既定符号映射同步。变换不会根据正负标签、错误样本或预测概率选择处理方式。

## 1. 一致重命名

按原 observer_graphs 顺序、各图原 steps 顺序、原 events 顺序，生成确定的 goal/step/event 新 ID。同步图依赖、父目标、事件世界与人物 payload 中的引用、cutoff ID；semantic.value 若恰为当前目标的步骤 ID、目标 ID 或事件 ID，也同步替换。自由文本不改写，task_id 不改写，模型不消费这些自由文本及 task_id。

候选步骤索引、图拓扑、时间、horizon、事件顺序、事件类型、接触与理解状态均不改变。target.steps、target.step、target.states.Q 按原目标的映射同步，UNKNOWN/NOT_APPLICABLE 等非步骤符号保留。对于当前以位置编码且不读自由文本或原始 ID 的 A0，这应产生相同的数值特征与预测；输出分布的步骤键需按重命名后的目标比较。

## 2. 插入 10／30 个不可见空记录

空记录均为 `goal_id=None`、`step_id=None`、`person=None`、`world_effect=None`、`semantic.kind=none`、`NOT_ACCESSED`、`NOT_APPLICABLE`。按固定轮转规则分布于原事件间隙，时间等于对应前一原事件时间；原事件不重排、不删减、不改时间。首事件及末尾 cutoff 事件不变，horizon 和 cutoff_minutes 不变。事件 ID 唯一。

已核对 `models/ec_jmf/structured.py`：`resolve_person_event_goal` 只接受显式且位于图内的目标；`StructuredModel.transition` 对无法解析的 null 目标直接返回 `[(state, 1.0)]`。因此对当前 A0 的状态转移拓扑，空记录产生恒等边，不改变支持的终态，也不会写入人物记忆。不可见人物特征为全零，visible/carry 均为 false。

世界 GRU 仍接收这些记录，后续依赖世界编码的门概率可能因此变化。这里检验的是无任务语义变化时神经系统是否仍稳定；不能事先要求所有神经概率严格相同。A3 的“最后 5 个事件”窗口依赖长度，可能被人为挤压；本保证针对 A0，不用该压力结果解释 A3 本身是否错误。

## 固定评价与边界

- 本版本变换在 test 评价前冻结；仅在 train 上检查实现语义与维度。
- 原始样本与其压力版本保留同一 split。train 的增强不能进入 dev/test；test 派生版本仅用于冻结后配对报告。
- 报告原样本到压力版本的 T1 概率绝对差、判断翻转率、T1 指标变化、T3 分布最大差；重命名需对齐步骤键。
- 压力样本是派生视图，不能叠加当作新增独立数据量，也不能提升“真实数据样本数”。
- 不改变 T2 正确答案难度，不声称该压力测试解决 T2 高饱和问题。
- 空记录只适用于当前显式结构语义；若后续模型学习了自由文本、真实时间间隔或引入额外副作用，应重新审计变换。

## 实现检查结果（仅 train）

在 working_copy 的 150 条 train 样本上，以原 A0 v3 seed0 checkpoint、PyTorch 2.14.0+cpu、单线程执行。未用 test 选择变换或检查阈值。源 examples 在所有操作后与深拷贝逐字段相等。

|固定变换|T1 概率最大绝对差|T2 概率最大绝对差|T3 分布最大绝对差|恒等边逐条检查数|
|---|---:|---:|---:|---:|
|一致重命名|0|0|0|不适用|
|插入 10 个空记录|5.96e-8|0|5.96e-8|16,279|
|插入 30 个空记录|5.96e-8|1.19e-7|2.38e-7|50,583|

三种变换的结构终态特征和因子向量均保持完全相同。两个空记录版本的原始终态对象也完全相同；新增边逐条满足旧状态索引等于新状态索引、概率系数为 1。此处约 1e-7 的差异属于浮点运算量级，不能宣称为性能退化或改进。
