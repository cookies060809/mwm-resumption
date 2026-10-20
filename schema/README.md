# Schema 说明

> 版本：v0.1.0（2026-10-20）。Owner：B。状态：草案，待 M1 三方评审。

## 文件

| 文件 | 作用 |
|---|---|
| `events.schema.json` | 单条原子事件；受控事件类型、来源、接触证据 |
| `task_graph.schema.json` | 目标的任务步骤图 `G=(K,D)` |
| `state.schema.json` | 联合状态 `V/F/A/B/C/Q` 的标签词表 |
| `annotation.schema.json` | 一条 P0 或 P1 样例记录；引用上述 schema |

## 关键约定

1. **P0 与 P1 记录互斥**：一条记录必须且只能包含 `p0_expectation` 或 `p1_observation` 之一。
2. **证据字段独立**：`person_access` 与 `person_access_evidence` 不得由客观世界事件自动推断。
3. **Q 是主观步骤**：取值为任务图中的 `step_id`、`UNKNOWN` 或 `NOT_APPLICABLE`；语义见标注手册。
4. **成对记录**：通过 `counterfactual_pair` 双向引用；同族变体必须同 split。
5. **P1 不入库**：`data/p1/` 仅保留 README 与模板；真实数据存放在批准的受限位置。
6. **版本化**：`schema_version` 写入每条记录。破坏性变更提升主版本并附迁移说明。

## 校验

```bash
python scripts/validate_data.py
python -m pytest
```

校验器检查：

- JSON Schema 结构与枚举；
- 事件 ID 唯一、`cutoff_event_id` 存在；
- 状态证据 ID 均属于已观察事件；
- `Q` / 预期恢复步骤 / 实际恢复步骤均指向合法步骤；
- 观察事件时间不晚于截断事件（可解析时）；
- 成对样例双向引用、同族同 pair、变体不同。

## 修改流程

1. 开 Issue（`data_issue.yml` 或任务模板）说明动机与影响范围。
2. 修改 schema、示例与标注手册，保持三者一致。
3. 更新 `schema_version` 与变更说明；旧数据需要迁移或标注版本。
4. PR 由 B 主责、A/C 至少一人评审。
5. CI 通过后才能合并。

## 尚未纳入 v0.1

- 逐标注者投票与逐因子置信度结构（用于直接计算 IAA）；
- 多人物、多目标主键；
- 多模态证据引用；
- 固定时间窗口与连续时间 hazard 字段；
- 数据集级 manifest / 划分文件 schema。

这些扩展在真实需求出现后再加入，避免提前固化不稳定的数据结构。
