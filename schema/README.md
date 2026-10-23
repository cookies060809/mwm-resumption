# Schema 说明

> **当前规范：** `p0_record_v0.2.schema.json`（Draft-07，`p0-record/v0.2.0`），对应当前 240 条 P0 批次（120 家族）。
> **冻结版本：** `p0_record.schema.json`（`p0-record/v0.1.0`，16 条种子）——A 的现有适配器仍读它，不要修改。
> **Owner：** B。**状态：** v0.2 已冻结并由 B 复核（`reviewed`）；A 需加版本分支，C 需确认字段映射。
> P1 真实人类数据尚未采集；P1 schema 已有第一版（见 §7），放在派生包内而不是本目录，**不要直接把 P0 schema 当作真实行为数据 schema**。

## 1. 文件

| 文件 | 作用 |
|---|---|
| [`p0_record_v0.2.schema.json`](p0_record_v0.2.schema.json) | **当前规范**：在 v0.1 基础上新增 `split`、`mechanism`、事件级 `person_comprehension` / `person_available_semantics`、`p0_design`、`indeterminate` 动作 |
| [`p0_record.schema.json`](p0_record.schema.json) | 冻结的 v0.1 结构（16 条种子，A 适配器当前版本） |

此前仓库中的 `events.schema.json`、`task_graph.schema.json`、`state.schema.json`、`annotation.schema.json` 是更早的草案，已由本文件取代；历史版本可在 Git 历史中查看。

## 2. P0 记录结构

| 字段组 | 字段 | 说明 |
|---|---|---|
| 样本 | `schema_version`、`sample_id`、`base_story_id`、`variant`、`domain` | `sample_id = base_story_id-variant`；当前 `variant` 为 A/B |
| 目标 | `goal_id`、`goal_description`、`horizon` | `horizon` 当前为 3 个决策机会 |
| 任务图 | `task_steps`、`task_dependencies`、`completed_steps_at_cutoff` | 客观步骤与依赖；完成步骤必须是步骤子集 |
| 事件流 | `observed_events` | 截至 cutoff 的原子事件；最后一条必须是 `cutoff_event_id` |
| 状态 | `state_at_cutoff` | `V/F/A/B/C/Q` 标签 |
| 证据 | `state_evidence_event_ids`、`state_evidence_by_factor` | 平铺并集 + 逐因子证据 |
| P0 目标 | `p0_scripted_policy`、`p0_expected_action`、`p0_expected` | 脚本策略与 T1/T2 期望；不是人类标签 |
| P1 占位 | `p1_observed_resume`、`p1_observed_first_step`、`p1_censoring_status` | 当前全部为 `null` / `not_collected` |
| 中断 | `interruption`、`interrupting_task` | 可选；嵌套任务的客观状态 |
| 审计 | `annotation`、`notes` | `annotation.status` 为 draft/reviewed/adjudicated；`notes` 不进入模型 |

## 3. 事件契约

每条事件包含：

```text
event_id, time, actor, event_type, goal_id, step_id,
person_access, world_effect, observer_evidence,
person_access_evidence, source, certainty, description
```

事件类型 v0.1：

```text
goal_start, goal_abandoned, step_started, step_completed, step_attempted,
interruption_started, interruption_ended, return_to_task,
person_action, person_statement, commitment_expressed,
task_cancelled, task_completed_by_other, notification_sent,
resource_available, resource_missing
```

关键语义：

- `person_access` 是**逐事件**的投递/接收标注，不是对人物理解的断言；
- 人物本人执行/陈述的事件必须为 `ACCESSED`；
- 后台事件不能因为“数据库里有”就写成 `ACCESSED`；
- 新增事件类型必须同时更新 schema、标注手册、校验器与数据，不允许用 `person_action` 偷懒承载所有语义。

## 4. 状态标签

- `V`：`VALID / CANCELLED / FULFILLED / UNKNOWN`
- `F`：`READY / BLOCKED / UNKNOWN`
- `A`：`ACCESSED / NOT_ACCESSED / UNCERTAIN`
- `B`：`BELIEVES_VALID / BELIEVES_INVALID / UNRESOLVED / UNKNOWN`
- `C`：`ACTIVE / SUSPENDED / ABANDONED / COMPLETED / UNKNOWN`
- `Q`：任务步骤 ID / `UNKNOWN` / `NOT_APPLICABLE`

语义与证据规则见 [标注手册](../docs/annotation/annotation_handbook_v1.0.md)。`V/F` 是客观侧，`A` 是接触证据，`B/C/Q` 是人物主观侧；禁止把客观事实直接复制为人物信念。

## 5. Schema 之外的跨字段校验

由 [`scripts/validate_data.py`](../scripts/validate_data.py) 检查：

- `cutoff_event_id` 是最后一条事件；事件时间非递减；
- 事件 ID 唯一；人物事件为 `ACCESSED`；
- 目标 ID 只属于原目标或嵌套任务；
- 任务依赖与完成步骤引用合法；
- 逐因子证据存在；非 `UNKNOWN` 有证据；`UNKNOWN` 不带正证据；
- 平铺证据 = 逐因子证据的按序并集；
- `Q` 引用合法步骤；`C=ABANDONED/COMPLETED` 与 `Q=NOT_APPLICABLE` 一致；
- `p0_expected_action` 与 `p0_expected.first_step` 一致；
- P0 的 P1 字段保持 `null` / `not_collected`；
- 资源/取消/完成事件与 `V/F` 标签一致；
- P07-A/B 截断前输入完全一致。

A/B 逐字段差异使用 [`scripts/pair_diff_report.py`](../scripts/pair_diff_report.py) 审计。

## 6. 版本与变更流程

1. 开 Issue（`data_issue.yml`）说明动机、影响字段与迁移方式。
2. 修改 schema、16 条数据、校验器、标注手册，保持四者一致。
3. 更新 `schema_version` 与变更说明；旧数据需迁移或明确标记版本。
4. PR 由 B 主责、A/C 至少一人评审；CI 通过后合并。
5. 批量扩增前先冻结接口，避免字段反复变更造成返工。

## 7. P1 schema

**已有第一版：** [`data/p1/public_derived/docs/schema.json`](../data/p1/public_derived/docs/schema.json)（Draft-07，附 [`schema.md`](../data/p1/public_derived/docs/schema.md) 字段说明与 [`merge_and_validate.py`](../data/p1/public_derived/scripts/merge_and_validate.py) 跨字段/泄漏/溯源校验）。它服务于公开数据派生的三源候选集，与 P0 schema 完全分离、不共用记录文件。

真实采集的 P1 还缺以下字段，待采集协议确定后增补：

- ISO 8601 时间戳与时区；
- 观察窗口起止、右删失/hazard 字段；
- 逐标注者投票、仲裁记录、标注者 ID；
- 真实行为证据 ID 与访问级别；
- 不包含可识别个人信息的元数据规范。

## 8. v0.2 变更（2026-10-20）

`p0_record_v0.2.schema.json` 在 v0.1 基础上新增以下字段，`p0-record/v0.1.0` 与 16 条种子保持冻结不动。

| 变更 | 字段 | 作用 | 对下家的影响 |
|---|---|---|---|
| 划分 | `split`（train/dev/calibration/test） | 家族级 60/20/20，同族 A/B 不跨集 | C 的评测协议需要；A 不应把它当输入。P0 实际只落三档——**2026-10-21 C 定案这轮不切 `calibration`（calibration＝0，未切走任何 `base_story_id`）**，枚举值保留给 P1 |
| 机制 | `mechanism`（8 个枚举） | 让家族可按受控机制分层统计与消融 | 报告按机制拆分指标 |
| 理解 | 事件级 `person_comprehension` | 承载 `U`：接触 ≠ 理解 | A 的 `delivery.comprehension` 可接入；C 的 `understood` 可映射 |
| 可用语义 | 事件级 `person_available_semantics` | 人物可能获得的消息内容，与世界真值分离 | 解决“人物侧只有一个 ACCESSED”的信息缺口 |
| 设计簿记 | `p0_design`（含 `future_outcome`） | 记录对照变量与截断后设计结果，**永不进入输入** | A/C 均不得读该字段 |
| 不确定目标 | `p0_expected_action=indeterminate` + `undefined_reason` | P07 这类不可判别输入不强行给点标签 | A 的 `scripted_targets` 需识别该值 |

**版本策略：** 任何字段变化都新增 schema 文件与数据文件、升 `schema_version`，不原地改 240 条；A 的适配器遇未知版本必须显式失败（当前行为正确）。
