# 评测目录

Owner：C。状态：骨架，尚无评测代码与结果。

## 任务与指标

| 任务 | 输出 | 主指标 |
|---|---|---|
| T1 恢复事件 | `P(resume within H)` | Resume F1、AUROC、AUPRC、Brier、ECE |
| T2 恢复步骤 | `P(Q*=k | resume)` | Step Accuracy、Top-k Accuracy |
| T3 状态信念 | `V/F/A/B/C/Q` 分布 | Macro-F1、Balanced Accuracy、证据一致性 |
| 约束 | 非法恢复/知识泄漏 | Invalid Resume Rate、Knowledge Leakage Rate |
| 成对诊断 | 应改变/应不变 | Pairwise Consistency |
| 效率 | 成本 | tokens、latency、GPU/CPU、内存 |

所有指标同时报告 `n`、分层条件、置信区间与逐样例输出。

## 实验

- **E1** P0 受控一致性：P01–P08 及扩展对照对；状态准确率、关键对照差异、未来泄漏、步骤正确率、错误类型。
- **E2** P1 真实恢复预测：是否恢复、恢复位置、概率校准；明确删失处理。
- **E3** 复杂度与长度：随事件长度、中断层数、任务数、缺失证据变化测准确度与成本。
- **E4** 跨域/跨人物泛化：按人物与任务族划分，禁止同族变体随机打散。
- **E5** 与 MENTIS 集成：原始、等量记忆、ECR-MWM 三方公平比较。

## 消融

A0 完整 ECR-MWM；A1 去信息可达性门控；A2 去承诺—进度联合更新；A3 去持久目标记忆；A4 去一致性损失；A5 去恢复位置辅助任务；A6 规则门控替代可学习门控；A7 仅增加等量历史摘要/提示 tokens。

每项消融必须报告输入与推理预算，并检查两类样例：客观相同、人物知晓不同；历史相同、后续不同。

## 校准与删失

- 校准使用独立验证集温度缩放或类似方法，同时报告 Brier/ECE；样本不足时不得声称校准可靠。
- P1 固定窗口二分类：未覆盖完整窗口且未出现恢复的样本剔除，并报告删失比例；若利用这些样本，使用离散时间 hazard/生存似然并记录风险暴露时间。
- P0 脚本标签与 P1 真实标签分别报告，不得混算。

## 结果格式（约定）

```text
results/<run_id>/
├── config.yaml
├── run.json          # commit, seed, data version/hash, environment, cost
├── metrics.json
├── predictions.jsonl
├── per_sample/
└── failures.md
```

结果目录由脚本生成；`results/README.md` 记录当前可用的运行。禁止手工修改数字或把未运行结果写入。

## 泄漏检查

- `observed_events` 只含 `t` 之前事件；
- 同一 `base_story_id` 的变体不跨 split；
- P07 负对照在 `t` 的输入与状态标签一致；
- 评测代码不得读取未来标签构造输入；
- 训练/调参/测试严格分离，规则与提示变体也报告调参过程。
