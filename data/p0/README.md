# P0 受控诊断集（种子批次）

> **当前规模：** P01–P08，共 8 个故事家族 × A/B = **16 条**；schema `p0-record/v0.1.0`；`annotation.status=draft`。
> **性质：** P0 是人工脚本 + 明确规则的受控诊断数据，**不是真实人类行为证据**。P1 尚未采集。
> **目标规模：** 120 个基础故事家族、240+ 条；当前 16 条是用于冻结接口和跑通管道的种子。

## 1. 文件

| 文件 | 用途 |
|---|---|
| [`p0_samples.json`](p0_samples.json) | 16 条 P0 记录（JSON 数组） |
| [`../../schema/p0_record.schema.json`](../../schema/p0_record.schema.json) | P0 记录 JSON Schema（Draft-07） |
| [`../../scripts/validate_data.py`](../../scripts/validate_data.py) | JSON Schema + 跨字段一致性校验 |
| [`../../scripts/pair_diff_report.py`](../../scripts/pair_diff_report.py) | 逐字段 A/B 差异报告 |
| [`../../scripts/build_p0_seed.py`](../../scripts/build_p0_seed.py) | 可复现构建 16 条种子（会覆盖 `p0_samples.json`） |
| [`../../docs/annotation/annotation_handbook_v0.1.md`](../../docs/annotation/annotation_handbook_v0.1.md) | 标注手册 |
| [`../../docs/annotation/label_quality_plan_v0.1.md`](../../docs/annotation/label_quality_plan_v0.1.md) | 标注质量方案 |
| [`../../docs/annotation/p0_pair_review_table.md`](../../docs/annotation/p0_pair_review_table.md) | 八组对照人工复核表 |

## 2. 加载示例与输入/标签硬边界

```python
import json

records = json.load(open("data/p0/p0_samples.json", encoding="utf-8"))
record = records[0]

events = record["observed_events"]          # 已截断，最后一条就是 cutoff
task_steps = record["task_steps"]
task_dependencies = record["task_dependencies"]
objective_progress = record["completed_steps_at_cutoff"]

state_label = record["state_at_cutoff"]     # 监督标签，不是输入
target = record["p0_expected"]              # P0 脚本目标，不是输入
```

**可以作为模型输入：**

- `observed_events`（截至 cutoff；最后一条必须是 `cutoff_event_id`）
- `task_steps`、`task_dependencies`
- `completed_steps_at_cutoff`（客观进度；应由事件推导）
- `interrupting_task`（嵌套任务的客观状态）
- `goal_id`、`goal_description`、`horizon`、`domain`

**禁止作为模型输入：**

- `state_at_cutoff`、`state_evidence_event_ids`、`state_evidence_by_factor`
- `p0_scripted_policy`、`p0_expected_action`、`p0_expected`
- `p1_observed_resume`、`p1_observed_first_step`、`p1_censoring_status`
- `notes`、`annotation`

> **P07 注意：** `notes` 含截断后的设计结果，只用于说明未来泄漏负对照；任何输入/prompt/特征/训练管道都必须排除 `notes`。

## 3. 16 条样例一览

| Pair | 版本差异（唯一/主要变量） | 检验 | A 预期 | B 预期 |
|---|---|---|---|---|
| P01 取消认知 | 人物是否接触取消通知 | 客观事实 ≠ 人物信念 | 已知取消，不恢复 | 未接触，继续包装 |
| P02 旧目标承诺 | 早前“继续” vs “放弃”；最后 5 个事件相同 | 长期承诺 vs 滑窗 | 恢复 | 不恢复 |
| P03 恢复位置 | 中断前运单是否已打印且人物知情 | 主观未完成步骤 | 从交接恢复 | 从打印恢复 |
| P04 他人代完成 | 人物是否获知同事已完成 | 完成事实与信念分离 | 不重复 | 可能重复 |
| P05 暂时不可执行 | 工具可用 vs 缺失（人物均知情） | 承诺 ≠ 可执行性 | 执行 | 等待工具 |
| P06 嵌套中断 | 嵌套任务在截断时是否完成 | 目标层级与恢复顺序 | 回父目标 | 先完成嵌套任务 |
| P07 未来泄漏 | 截断前输入完全相同；仅截断后设计结果不同 | 不可预知未来 | 预测应相同 | 预测应相同 |
| P08 接触但误解 | 都读到取消通知；一个理解、一个误读为暂缓 | 接触 ≠ 理解 | 停止 | 暂停/等待 |

覆盖情况：`work` 6 条、`collaboration_service` 8 条、`daily_life` 2 条；共 123 条事件。当前 split 均为 `unassigned`（由 schema 外部的数据卡/后续划分管理）。

## 4. 校验

```bash
python scripts/validate_data.py
python scripts/pair_diff_report.py
```

当前结果：

```text
OK: 16 records, 8 A/B pairs; schema and cross-field checks passed.
P07 input identity: PASS
```

校验覆盖：

- JSON Schema 结构、枚举、pattern、必填、`additionalProperties`；
- `cutoff_event_id` 必须是最后一条事件，事件时间非递减；
- 证据引用必须存在；非 `UNKNOWN` 标签必须有逐因子证据；`UNKNOWN` 不携带正证据；
- `state_evidence_event_ids` 等于逐因子证据的按序并集；
- `Q` 必须是任务步骤或 `UNKNOWN/NOT_APPLICABLE`；`C=ABANDONED/COMPLETED` 与 `Q=NOT_APPLICABLE` 一致；
- `p0_expected_action` 与 `p0_expected.first_step` 一致；
- P0 的 `p1_observed_resume` / `p1_observed_first_step` 均为 `null`；
- P07-A/B 截断前输入完全一致。

## 5. 当前质量状态

| 检查项 | 结果 |
|---|---|
| Schema 校验 | 16/16 |
| 证据覆盖率（非 `UNKNOWN`） | 16/16 |
| cutoff 无未来事件 | 16/16 |
| A/B 对照隔离 | 8/8（自动 diff 通过，人工审计待完成） |
| P07 输入一致性 | PASS |
| B 人工审计 | 待完成 |
| A/C 第二人盲审 | 待完成 |
| P1 双人标注一致性 | 尚未采集，N/A |

## 6. 已知边界与待确认项

1. **这是 P0 脚本数据，不是人类数据。** 不能用于报告真实恢复预测能力；P1 全部为 `null`。
2. **仅 16 条。** 目标 240+；当前种子先解锁数据加载、状态更新与对照诊断管道。
3. **Schema v0.1 扩展字段需 A 确认接口：** `task_dependencies`、`completed_steps_at_cutoff`、`state_evidence_by_factor`、`p0_expected`、`annotation`。如果 A 的接口暂时只认核心字段，可先用 `state_at_cutoff` + `p0_expected_action` 跑通。
4. **`F` 没有 `NOT_APPLICABLE`。** 目标已 `FULFILLED/CANCELLED` 时，有明确资源证据可标 `READY/BLOCKED`，否则 `UNKNOWN`。
5. **`Q` 是主观步骤，允许滞后。** P04-B 的 `Q=fill_form` 客观上已完成，这是有意设计。
6. **P06-B 的 `p0_expected_action` 指向嵌套任务**，但 `resume_within_horizon=false` 指原目标未恢复；两者不矛盾。
7. **P07 的 `notes` 含截断后结果。** 只做设计说明，禁止进入模型输入。
8. **时间格式 P0 用 `HH:MM`**；P1 需要 ISO 8601/时区，届时需要独立 P1 schema。
9. **标注状态是 `draft`。** B 完成人工逻辑复核后改 `reviewed`；双人标注/仲裁后再改 `adjudicated`。
10. **领域覆盖不均衡。** `daily_life` 目前只有 P05；扩增时优先补齐三个领域。

## 7. B 的复核清单

- [ ] P01：A/B 只有 e06 的 `person_access` 与描述不同；A 已确认取消，B 未接触。
- [ ] P02：A/B 只有 e03 不同，e04–e08 完全一致；B 是“放弃”不是“认为目标无效”。
- [ ] P03：A/B 只有 e04 的完成状态不同；B 的打印未执行不是设备故障（`F=READY` 成立）。
- [ ] P04：A/B 只有 e05 的接触不同；B 的 `Q=fill_form` 客观已完成，用于测试主观进度滞后。
- [ ] P05：A/B 只有 e05 的资源状态不同；B 的 `F=BLOCKED` 且人物知情。
- [ ] P06：A 的 e07/e08 完成嵌套任务，B 的 e07 只尝试；e09 嵌套来电对两版都是中性事件。
- [ ] P07：A/B 除 `sample_id/variant/notes` 外完全一致；不要在输入里读 `notes`。
- [ ] P08：A/B 的 e05 都是 `ACCESSED`，差异在 e06 的理解；B 是 `BELIEVES_VALID + SUSPENDED`。
- [ ] 运行 `python scripts/validate_data.py` 与 `python scripts/pair_diff_report.py`。
- [ ] 确认 `annotation.status=draft`，待复核后再改。

## 8. 扩展计划

| 阶段 | 交付 |
|---|---|
| 当前种子 | 16 条，P01–P08；已通过结构与跨字段校验 |
| 下一批 | 补 daily_life / collaboration_service 变体，扩到约 30 条 |
| 批量扩增 | 120 个基础故事家族 / 240+ 条；每批运行校验与 A/B diff |
| 划分 | 按 `base_story_id` 做 60/20/20；同族 A/B 不跨 split |
| 质量 | B 100% 审计 diff；A/C 每对抽 1 条盲审；记录分歧与仲裁 |
| P1 | 另立 schema 与标注流程；当前不纳入竞赛证据 |

> 详细规则见 [标注手册](../../docs/annotation/annotation_handbook_v0.1.md)、[质量方案](../../docs/annotation/label_quality_plan_v0.1.md) 与 [八组复核表](../../docs/annotation/p0_pair_review_table.md)。
