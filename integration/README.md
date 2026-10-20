# MENTIS 集成

Owner：C（版本适配与公平对照）；A 提供 ECR-MWM 接口。状态：官方入口已核查，`mentis_adapter.py` 与统一 HTTP/子进程协议已通过本机测试；官方环境、真实调用与核心模型集成仍待完成。详见 [核查记录](mentis_public_audit.md)。

## 目标

把 EC-JMF/ECR-MWM 接入公开版 MENTIS 的状态解析、转移与决策环节，同时保留可解释的对照变体，避免把“额外上下文”的收益误归因于新算法。

## 版本锁定

- 官方代码：[mental-world/Mentis](https://github.com/mental-world/Mentis)
- 必须记录：commit、分支/tag、模型配置、依赖版本、调用预算、输入/输出样例。
- 论文区分“公开实现复现”与“无法公开重现的 oracle 分析”；不得把自造标签冒充官方 gold。

## 三类集成

| 变体 | 说明 | 目的 |
|---|---|---|
| MENTIS-original | 发布版，不加入新状态更新器 | 相对基线 |
| MENTIS-memory | 输入同长度摘要与目标日志 | 排除“上下文更多” |
| ECR-MWM | 联合状态 + 认知可达性门控 + 恢复预测 | 待提交方法 |

## 接口字段（草案）

```text
session_id
goal_id
event_log
state_belief
evidence_trace
candidate_resume_prob
conditional_step_probs
```

- `event_log` 只含 `t` 之前的事件；
- `state_belief` 保存后验/粒子与边际，不保存未来标签；
- `evidence_trace` 支持逐样例解释与错误分析；
- 所有调用记录 prompt tokens、输出 tokens、时延、算力与失败类型。

## 公平性检查

- 相同输入信息、截止点与候选输出；
- 相同基座与采样设置；
- 相同评价切片；
- 记录各变体的接口开销，不把集成层成本隐藏；
- 任何性能声明都必须有可复现运行与消融支持。

## 当前状态

`a_output_adapter.py` 已支持 A 草案中的 `t1_resume_probability / t2_conditional_step_distribution / t3_state_distributions / evidence_trace / cost` 到 C 输出的显式转换。B10 子进程配置需选择 `output_format="a-t123-draft-1"`，默认配置仍关闭。阈值固定为 0.5，条件步骤取 argmax；`P(resume)=0` 时条件步骤分布必须为 null。缺失输出、不合法分布和截止外证据会拒绝，状态和成本不补造。

A 当前交付的是 v0.1 输入适配与数值滤波基础，尚无 v0.2 完整 T1/T2/T3 预测包装。`scripts/check_a_p0.py` 验证其 13 项现有契约；`tests/test_a_output_adapter.py` 验证输出运输与转换。两类检查都不代表真实模型效果或完整 EC-JMF 已实现。

- [ ] 拉取并锁定 MENTIS 版本
- [ ] 复现官方示例
- [x] 建立并本机测试统一输入输出适配层
- [ ] 三类变体公平对照
- [ ] 成本与失败案例记录
