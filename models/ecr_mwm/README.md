# ECR-MWM

完整研究系统的端到端包装。Owner：A；集成验证：C。状态：未实现。

## 范围

- 调用 `models/ec_jmf` 维护联合状态后验；
- 生成 T1/T2/T3 输出与证据引用；
- 提供与 MENTIS 的适配接口；
- 汇总成本、不确定性、失败案例与可复现元数据。

## 输出契约（草案）

```json
{
  "sample_id": "P01-B",
  "cutoff_event_id": "e05",
  "horizon": {"type": "decision_opportunities", "value": 3},
  "t1_resume_probability": 0.0,
  "t2_conditional_step_distribution": {"step_id": 0.0},
  "t3_state_distributions": {
    "V": {}, "F": {}, "A": {}, "B": {}, "C": {}, "Q": {}
  },
  "evidence_trace": [],
  "uncertainty": {},
  "cost": {"tokens": 0, "latency_ms": 0, "compute": "cpu"}
}
```

规则：

- `t2` 必须在“未来确实恢复”条件下求分布；恢复概率很低时标注适用范围与不确定性。
- `t3` 不得伪造确定标签；未知时输出分布或 `UNKNOWN`。
- 每个预测必须能回溯到输入事件与证据；不得引用 `t` 之后的行动。
- 成本字段必须由真实运行记录填写，不能预估后写成实测。

## 集成变体

1. 原始发布版 MENTIS；
2. 等量历史/记忆增强 MENTIS（排除“上下文更多”解释）；
3. ECR-MWM（联合状态 + 可达性约束 + 恢复预测）。

三者在相同输入、相同基座、可比预算下比较；具体版本与调用方式见 `integration/README.md`。

## 当前状态

- [ ] 接口冻结
- [ ] 端到端最小可运行版本
- [ ] T1/T2/T3 输出校验
- [ ] MENTIS 集成
- [ ] 成本与失败案例记录
