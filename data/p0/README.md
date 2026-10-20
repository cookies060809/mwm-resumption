# P0 受控诊断集

**用途**：验证信息泄漏、因果因素敏感性、目标状态一致性与成对逻辑。P0 标签是脚本化标签，**不能**用于声称预测真实人类心理。

## 当前内容

| 文件 | 说明 |
|---|---|
| `examples/work/P01-A.json` | P01 取消认知：人物接触并确认取消 |
| `examples/work/P01-B.json` | P01 取消认知：通知仅在后台队列，人物未获知 |

这两个文件是 schema 与标注流程的示例，状态为 `draft`，尚未经过双人标注与仲裁。

## 正式布局

```text
data/p0/<domain>/<base_story_id>/<variant_id>.json
```

- `domain`：`work`、`daily_life`、`collaboration_service`。
- 每个家族至少 2 个变体；同族同 split。
- 文件名与 `sample_id` 一致。
- P01–P08 原型见研究方案第 8.2 节；扩展家族按同一规则建设。

## 成对样例

- `counterfactual_pair.paired_sample_id` 必须双向指向。
- `controlled_change` 只描述一个主要变化。
- 类型 I（信息等价）应保持人物可获得信息与可观察行动一致；类型 II（人物信息变化）应改变人物接触/理解，而不是客观世界。
- P07 未来泄漏负对照：`t` 之前输入完全一致，仅改变 `t` 之后的真实结果；`state_at_cutoff` 必须一致。

## 标签要求

- 每个非 `UNKNOWN` 状态标签必须有 `state_evidence_event_ids` 或脚本策略支持。
- `V/F` 只使用客观证据；`B/C/Q` 不得从 `V/F` 直接复制。
- P0 的 `p0_expectation` 必须写明脚本策略、预期恢复与预期步骤。
- 脚本标签不得与 P1 真实标签合并统计。

## 建设顺序（建议）

1. P01–P08 各完成一对最小对照，作为标注手册的校准样例。
2. 两人独立标注、仲裁、记录一致性；修订手册到 v1。
3. 扩展到三个领域与分层因素，保持家族级划分。
4. 每批数据通过校验与泄漏检查后合并。

详细规则见 [标注手册](../../docs/annotation/annotation_handbook_v0.1.md)。
