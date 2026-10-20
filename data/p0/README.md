# P0 受控诊断集

> **当前规模：** `p0-record/v0.2.0`，15 个任务骨架 × 8 个受控机制 = **120 个故事家族 × A/B = 240 条**、1789 个事件；`annotation.status=reviewed`（B 已完成人工复核）。
> **性质：** P0 是人工脚本 + 明确规则的受控诊断数据，**不是真实人类行为证据**。P1 尚未采集。
> **v0.1 种子：** `p0_samples.json` 保留 16 条冻结版本，供 A 的现有适配器与回归测试使用；v0.2 是新的正式批次。

## 1. 文件

| 文件 | 用途 |
|---|---|
| [`p0_samples_v0.2.json`](p0_samples_v0.2.json) | 240 条 v0.2 记录（当前正式批次） |
| [`p0_samples.json`](p0_samples.json) | 16 条 v0.1 冻结种子（A 适配器 `p0-record/v0.1.0` 仍读此文件） |
| [`../../schema/p0_record_v0.2.schema.json`](../../schema/p0_record_v0.2.schema.json) | v0.2 JSON Schema（Draft-07），含 `split`/`mechanism`/事件级 `U`/`p0_design` |
| [`../../schema/p0_record.schema.json`](../../schema/p0_record.schema.json) | v0.1 schema（冻结） |
| [`../../scripts/build_p0_v02.py`](../../scripts/build_p0_v02.py) | 可复现构建 240 条（种子升级 + 112 家族生成） |
| [`../../scripts/build_p0_seed.py`](../../scripts/build_p0_seed.py) | 可复现构建 16 条 v0.1 种子 |
| [`../../scripts/validate_data.py`](../../scripts/validate_data.py) | 两个批次的 Schema + 跨字段一致性校验 |
| [`../../scripts/pair_diff_report.py`](../../scripts/pair_diff_report.py) | 逐字段 A/B 差异报告（`--full --pair P01-W2` 看单对） |
| [`../../docs/annotation/annotation_handbook_v1.0.md`](../../docs/annotation/annotation_handbook_v1.0.md) | 标注手册 v1.0 |
| [`../../docs/annotation/label_quality_plan_v0.1.md`](../../docs/annotation/label_quality_plan_v0.1.md) | 标注质量方案 |
| [`../../docs/annotation/p0_pair_review_table.md`](../../docs/annotation/p0_pair_review_table.md) | 复核表与机器预检结果 |

## 2. 加载示例与输入/标签硬边界

```python
import json

records = json.load(open("data/p0/p0_samples_v0.2.json", encoding="utf-8"))
record = records[0]

events = record["observed_events"]          # 已截断，最后一条就是 cutoff
state_label = record["state_at_cutoff"]     # 监督标签，不是输入
target = record["p0_expected"]              # 脚本目标，不是输入
design = record["p0_design"]                # 设计簿记，绝不是输入
```

**可以作为模型输入：** `observed_events`（截至 cutoff）、`task_steps`、`task_dependencies`、`interrupting_task`、`goal_id`、`goal_description`、`horizon`、`domain`。`split` 只用于划分，不进模型。

**禁止作为模型输入：** `state_at_cutoff`、`state_evidence_*`、`p0_scripted_policy`、`p0_expected_*`、`p0_design`（含 `future_outcome`）、`p1_*`、`notes`、`annotation`、`sample_id`/`variant`/`base_story_id`。

> **A 适配器口径（已对齐）：** A 不读 `completed_steps_at_cutoff`（改用事件重放），也不把 `interrupting_task.status_at_cutoff` 写进心智；v0.2 的 `p0_design` 同样不进入任何输入。

## 3. 八个受控机制

| mechanism | 家族数 | 唯一变化 | A 预期 | B 预期 |
|---|---:|---|---|---|
| `contact_cancellation` | 15 | 取消通知是否到达人物 | 不恢复 | 继续推进 |
| `long_term_commitment` | 15 | 早前承诺还是明确放弃 | 恢复 | 不恢复 |
| `resume_position` | 15 | 关键步骤是否完成且人物知情 | 从下一步恢复 | 从该步恢复 |
| `other_completion` | 15 | 是否获知他人已完成 | 不重复 | 可能重复（不计恢复） |
| `resource_availability` | 15 | 必要条件可用或缺失（均知情） | 执行 | 等待条件 |
| `nested_interruption` | 15 | 嵌套任务是否完成 | 回父目标 | 先完成嵌套 |
| `future_leak` | 15 | 截断前输入相同，仅截断后结果不同 | 无点标签 | 无点标签，分布须相同 |
| `comprehension` | 15 | 都接触取消信息，一个理解一个误读 | 停止 | 暂停等待 |

种子 P01–P08 分别属于上述八个机制，保留在 v0.2 中；其余 112 个家族由 15 个任务骨架（5 work / 5 collaboration_service / 5 daily_life）× 机制生成，家族之间任务、实体、单号独立。

## 4. 划分

| split | 家族数 | 说明 |
|---|---:|---|
| train | 72 | 每个机制 9 个家族 |
| dev | 24 | 每个机制 3 个家族 |
| test | 24 | 每个机制 3 个家族 |

按 `base_story_id` 分层，同族 A/B 必在同一 split；`split` 是家族级字段，校验器会检查同族一致性。校准集暂不单列，C 需要时从 dev 再切。

## 5. 校验

```bash
python scripts/validate_data.py
python scripts/pair_diff_report.py
python scripts/pair_diff_report.py --full --pair P04
```

当前结果：

```text
OK: 16 records, 8 A/B pairs; schema and cross-field checks passed.
OK: 240 records, 120 A/B pairs; schema and cross-field checks passed.
P07 identity failures: 0
```

校验覆盖（在 v0.1 基础上新增）：

- `split` 家族级一致、`mechanism` 合法；
- `person_comprehension` 与 `person_access` 一致；`MISUNDERSTOOD` 必须配非 `accurate` 的 `interpretation`；
- `indeterminate` 动作只能出现在 `p0_design.undefined_target=true` 且 `undefined_reason` 明确的记录；
- 15 个 `future_leak` 家族截断前逐字段相同（排除 `sample_id`/`variant`/`notes`）；
- `UNKNOWN` 不携带正证据；非 `UNKNOWN` 至少一条证据；平铺证据等于逐因子证据并集；
- `completed_steps_at_cutoff` 必须能由事件重放出来（A 的诊断侧同样会检查）。

## 6. 当前质量状态

| 检查项 | 结果 |
|---|---|
| Schema 校验（v0.1 / v0.2） | 16/16、240/240 |
| 证据覆盖率（非 `UNKNOWN`） | 240/240 |
| cutoff 无未来事件 | 240/240 |
| A/B 对照隔离 | 120/120（逐字段 diff，事件条数已对齐） |
| P07 输入一致性 | 15/15 PASS |
| B 人工复核 | 240/240，`status=reviewed` |
| A/C 盲审 | 未完成（每机制抽 1 条，共 8 条） |
| P1 双人标注一致性 | 尚未采集，N/A |

## 7. 已知边界与待确认项

1. **这是 P0 脚本数据，不是人类数据。** 不能报告真实恢复预测能力；P1 全部为 `null`。
2. **句式是模板化的。** 家族之间的任务/实体独立，但同一机制内的句式复用，表达多样性有限，不能当作自然语言鲁棒性证据。
3. **P04 口径已按方案 §3.4 统一。** 客观已完成的重复动作不计 T1/T2，`resume_within_horizon=false`、`first_step=null`，主观滞后只放在 `Q`；因此 15 个 `other_completion` 家族在 T1 上没有 A/B 对比，只在 `B/C/Q` 上有。
4. **P07 改为 `indeterminate`。** 两版截断前输入完全相同，不存在可判别的点标签；截断后的设计结果放在 `p0_design.future_outcome`，永不进入输入。
5. **A 适配器只认 `p0-record/v0.1.0`。** 传入 v0.2 会显式 `UNSUPPORTED_SCHEMA_VERSION`；A 加版本分支前，v0.2 不能直接当训练输入。
6. **字段名冲突未解决。** B 的 `person_access_evidence` 是自由文本，C 的同名字段是 `{status, understood}` 对象，合并前必须改名或做映射。
7. **时间仍是 `HH:MM`**，不含日期；P1 需要 ISO 8601 与删失字段。
8. **`F` 没有 `NOT_APPLICABLE`。** 目标已 `FULFILLED/CANCELLED` 时，有明确资源证据才标 `READY/BLOCKED`，否则 `UNKNOWN`。
9. **P06 的 T2 会被 A 遮蔽。** `replace_part` 属嵌套任务，`scripted_targets` 判 `t2_mask=false`，只作审计。
10. **扩量不要再改本文件。** 任何字段变化都要新增 schema 版本与新数据文件，并同步通知 A 更新哈希与回归预期。

## 8. B 复核清单（已完成）

- [x] P01：A/B 只有 e06 的 `person_access` 与描述不同；A 已确认取消，B 未接触。
- [x] P02：A/B 只有 e03 不同，e04–e08 完全一致；B 是“放弃”不是“认为目标无效”。
- [x] P03：A/B 的 e04 完成状态不同，`completed_steps_at_cutoff` 随之派生不同；B 的打印未执行不是设备故障（`F=READY` 成立）。
- [x] P04：A/B 只有 e05 的接触不同；B 的 `Q=fill_form` 客观已完成，用于测试主观进度滞后；T1 已按 §3.4 改为 `do_not_resume`。
- [x] P05：A/B 只有 e05 的资源状态不同；B 的 `F=BLOCKED` 且人物知情。
- [x] P06：A 的 e07/e08 完成嵌套任务，B 的 e07 只尝试；嵌套状态只从事件推断，父目标六因子相同。
- [x] P07：A/B 除 `sample_id/variant/notes` 外完全一致；`p0_design` 与 `notes` 不进入输入。
- [x] P08：A/B 的取消通知都 `ACCESSED`，差异只在 `person_comprehension`（`UNDERSTOOD` / `MISUNDERSTOOD`）。
- [x] 运行 `python scripts/validate_data.py` 与 `python scripts/pair_diff_report.py`。
- [x] `annotation.status` 已由 `draft` 改为 `reviewed`；`adjudicated` 需等 A/C 盲审。

## 9. 交接页（给 A/C 的一页纸）

数据文件 SHA256：`66952f810f6e046b733538491855b5c690a23ca4c49d3550de5fef1d09938214`（LF；`sha256sum data/p0/p0_samples_v0.2.json` 可复核）。

```text
dataset: p0-v0.2.0
n: 240 (120 A/B pairs, 120 families, 1789 events)
schema_pass: 240/240
evidence_coverage: 240/240
cutoff_no_future: 240/240
pair_isolation: 120/120
p07_input_identity: 15/15 PASS
splits: train 72 / dev 24 / test 24 (family-level, stratified by mechanism 9/3/3)
domains: work 80 / collaboration_service 84 / daily_life 76 (records)
human_audit: 240/240 (B, reviewed)
second_reviewer: 0/8 (A/C, pending)
known_ambiguities: person_access_evidence naming collision with C; A adapter v0.1 only
p1_status: not_collected
noise_ceiling: N/A (P0 scripted); P1 TBD
```

## 10. 后续

| 阶段 | 交付 |
|---|---|
| 当前 | 240 条 v0.2，B 复核完成，结构与对照校验通过 |
| 下一步（A/C） | 每机制抽 1 条盲审（8 条）→ 仲裁 → `adjudicated`；A 加 v0.2 适配器分支；C 确认字段映射 |
| P1 | 另立 schema 与标注流程；当前不纳入竞赛证据 |

> 详细规则见 [标注手册 v1.0](../../docs/annotation/annotation_handbook_v1.0.md)、[质量方案](../../docs/annotation/label_quality_plan_v0.1.md) 与 [复核表](../../docs/annotation/p0_pair_review_table.md)。
