# A v3 语义修订的 C 接入核验

已将 main `dec55fa` 整合到 Bill。模型语义源码来自 `5a72b64`，训练配置为 `configs/a_neural_p0_v03_aligned.json`，协议 `b-p0-v03/v3`。B 数据、标签、split 与 C 评分口径均未修改，旧数值参考及旧神经结果保持历史记录。

## 改动与必要性

本轮确实改变模型转移规则及参数化：他人完成与取消分开；放弃后局部动作以可学习门保留重新投入/仍终止两种解释；本人物理中断不依赖消息理解；承诺与活动相位分开；模糊返回/准备保留多种可能。未关联目标的消息保留未归属证据，不编造其目标。

尚缺 B 输入侧统一焦点事件、消息目标关联、下一步资源映射。T3.A 仍是代理诊断，包含它的六因子总分不能当成已完全对齐的成绩。结构零支持减少不等于所有语义问题已解决。

## C 独立核验的范围

读取 A 上传的 `results/p0/a_neural_v03_v3/a0_seed0.pt`，验证完整 B v0.3 文件哈希与 150/52/52 划分，推理只传 input、无 target/样本身份，逐条执行 C 输出校验。52 条预测无失败，重新加载模型的预测完全一致，A 内部指标与其原 seed0 报告完全一致。

| 指标 | C 核验结果 |
|---|---:|
| T1 恢复判断准确率 | 42/46 = 91.30% |
| T1 恢复类 F1 | 0.9091 |
| C 实际输出步骤准确率 | 20/20 = 100% |

其余 6 条 T1 UNKNOWN 保持排除。B4 在同一数据上的既有成绩为 36/46 = 78.26%；本次代表 checkpoint 高 13.04 个百分点。旧神经主模型 20 种子平均 82.50%，不能把本次单 checkpoint 与旧均值差直接解释成修复的因果收益。A 已交付新版 140 次训练报告，C 本轮只做其 seed0 checkpoint 独立推理核验，并未独立重跑新版全部训练。

这是基于既有诊断修订语义后的重复评测，测试集已暴露；不是新盲测或真人效果证明。新门也改变了初始化及参数化，不能声称涨分全部来自单个修复。匿名结果、数据/模型哈希及 A 的 20 种子自报摘要见 [neural_v03_aligned_checkpoint_check.json](neural_v03_aligned_checkpoint_check.json)。

## 接入与复现

C 训练入口新增 `--config`，将配置中的 semantic_contract 同步传到 train/dev/test Batch，并检查新版数据哈希与 split 数量；旧入口默认 legacy-v1 以保留旧协议。不得仅加载新版权重而继续使用旧 Batch。

```bash
python scripts/check_aligned_neural_checkpoint.py
# 以下为独立完整重训命令，本轮尚未执行：
python scripts/run_neural_p0_evaluation.py --config configs/a_neural_p0_v03_aligned.json --output-dir results/c_neural_v03_aligned
```

新增检查覆盖 v3 实际反向传播及序列化、拒绝错误 Batch 协议、交付 checkpoint 的无标签公共评分，完整 171 项测试通过。另以完整 150/52/52 划分完成 A0 seed0 单轮训练入口冒烟检查（含代表重训、模型重载与六种本地对照），只验证接入，不将其当成40轮正式成绩。后续优先与 B 确认剩余事件归属和焦点口径，并准备未参与修订的新测试数据。
