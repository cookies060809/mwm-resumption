# 本地上下文残差实验代码审查

审查日期：2026-10-22。对象：`experiments/run_local.py`。本审查只读检查实验实现，执行核验仅使用原固定分割的 150 条 train、52 条 dev；没有计算 test 预测、读取 test 结果或据 test 选择方法。原 Bill 仓库及原 checkpoint 未修改。本记录不重复压力变换检查，也不对完整实验的最终 test 分数作独立认证。

## 结论

未发现阻断本轮受控诊断的标签泄漏、不可见人物事件进入注意力池化、冻结失效、初始预测不一致或 T1/T2 计分混淆问题。实验属于在同一个原 A0 v3 checkpoint 上增加 T1 行为上下文残差的 warm-start 诊断。

## 实际执行核验

对 `visible_context` 与 `visible_context_balanced` 两个分支分别执行以下检查：以 seed 1 初始化、用全 train 做一次 AdamW 参数更新，然后在 dev 比较；原参照为固定 A0 v3 checkpoint。该一步更新只用于验证数据流和参数冻结，没有保存模型或选择训练预算。

|核验项|visible_context|visible_context_balanced|
|---|---:|---:|
|零初始化后与原模型的 p/q/factors 最大绝对差|0|0|
|把 invisible/padding proposals 改为 12345 后，上下文向量最大绝对差|0|0|
|一步更新后，含监督字段的 dev Batch 与仅 input 的 dev Batch 预测最大绝对差|0|0|
|一步更新后，全部冻结参数最大绝对差|0|0|
|一步更新后，T3 因子分布相对原模型最大绝对差|0|0|

实际可训练参数仅为：

```text
resume_head.attention.weight
resume_head.residual.0.weight
resume_head.residual.0.bias
resume_head.residual.3.weight
resume_head.residual.3.bias
```

没有原 GRU、状态门网络、原 resume_head 或原 step_head 参数进入两个新分支的优化器。

## 代码路径检查

1. **输入与监督分离。** `ContextHazard.set_context` 使用编码 proposal、memory、`batch.valid & batch.visible` 和状态所属记录索引，不访问 target、状态监督或期望行为。机制字段只在 balanced 分支的 train BCE 权重中使用；未知恢复标签仅用于训练有效项掩码。
2. **不可见信息屏蔽。** 注意力分数先屏蔽 invalid/invisible 位置，softmax 后再次乘 mask 并归一化。人物输入仍由原模型的可见性与记忆写入门控制。未添加 world memory 到人物上下文支路。
3. **冻结与零初始化。** 原模型参数全部冻结，再加入新注意力和 residual 网络；residual 最后线性层权重与偏置均为零。`fit_run` 验证初始化 p/q/factors 与原 checkpoint 严格一致，并在选中状态载入后检查冻结参数逐项相等。
4. **训练随机性。** `fit_run` 在初始化一致性检查之后重新调用 `seed_everything(seed, 1)`，因此参照模型构造消耗随机数不会把所有 run 的训练 dropout 强制重置成同一个种子轨迹。
5. **dev 选模。** 以 epoch 0 原模型行为作为候选，后续只接受更低的未加权原 dev 目标；并列保留较早轮次。所有预定义 run 训练完后按平均 dev loss 选方法，canonical seed 固定为 0。该流程在 test 推理前写出选择结果，未用 test 选择 seed 或 checkpoint。
6. **T1/T2 输出。** 新模块只替换 hazard logit 的计算，原 horizon 变换、无可用候选约束和步骤候选 mask 继续使用。C 适配器的恢复判断阈值为 0.5；`t2_emitted_top1` 经 C 公共评价器计算，错误的“不恢复”会造成缺失步骤并计错；`t2_conditional_top1` 经 A 原评价器计算条件步骤分布。两者分别命名、分别输出。
7. **保存与重载。** 保存格式包含来源 checkpoint 哈希、方法、seed、epoch 和 state_dict；加载时验证来源哈希并严格载入权重。训练函数包含保存／重载后的 dev 输出一致性检查。审查的一步更新核验没有调用磁盘保存路径。

## 解释边界

- 原损失表达式仍保留，但骨干和状态过滤参数冻结后，state NLL、事件一致性与信息等价项对新参数是常数。这轮训练主要改变 T1 hazard；每个状态的恢复概率还会影响 T2 条件混合，因此 T2 有可能间接变化。不得把它表述为重新学习或提升了 BCQ 状态估计。
- 可见 proposal 包含“信息可得但尚未理解”或“接触不确定”的显式证据。新行为支路可以利用这些观察线索预测恢复，但不把它们写入或改写原 T3 心智状态。它形成了结构过滤之外的行为预测通道，这是一项需要说明的设计取舍。
- T3 完全不变符合冻结设计，并不构成新方法改善心智解释的证据。
- 本轮从同一个已训练 checkpoint 起步。多个新分支 seed 描述新增模块初始化与 dropout 的变动，不等价于多个独立从头训练的原模型。
- 原 head 继续训练对照能够检查额外优化预算的影响；若它与新模块的硬判断分数相同，应同时报告概率指标，不应把共同的硬判断提升全部归因于新增上下文模块。
- 所有数据仍为 P0 结构化脚本。代码正确和 dev 改善不等于真实人物泛化；压力测试也不能替代真实数据验证。
