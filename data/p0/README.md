# P0 受控诊断集

> **v0.3 完整发布版（新增统一入口）：** [`v0.3/p0_samples.json`](v0.3/p0_samples.json) 包含基础 240 条和补充 14 条，共 **254 条 / 127 家族**，train/dev/test = **150/52/52**；接入说明和实测结果见 [`v0.3/README.md`](v0.3/README.md)。本页下文分别描述两个历史来源批次；旧 `p0_samples_v0.3.json` 仅为 14 条补充原稿，不是完整训练集。完整发布版保留两批来源逐条内容与签核，使用时勿再次拼接来源。

> **当前规模：** `p0-record/v0.2.0`，15 个任务骨架 × 8 个受控机制 = **120 个故事家族 × A/B = 240 条**、1831 个事件；`annotation.status=reviewed`（B 已完成人工复核）。
> **不确定性补量批次：** `p0_samples_v0.3.json` 是 7 家族 / 14 条，用于填 v0.2 里 11 个“声明过但没用过”的不确定性档位；B 于 2026-10-21 逐对复核并把 [`p0_spot_audit_v0.3_all7.md`](../../docs/annotation/p0_spot_audit_v0.3_all7.md) 的 28 个复选框全部勾为通过，`status=reviewed`。草稿由 Qoder 生成、签核署名 B（与 v0.2 同一惯例），A/C 盲审仍未做。
> **性质：** P0 是人工脚本 + 明确规则的受控诊断数据，**不是真实人类行为证据**。P1 尚未采集。
> **v0.1 种子：** `p0_samples.json` 保留 16 条冻结版本，供 A 的现有适配器与回归测试使用；v0.2 是新的正式批次。

## 1. 文件

| 文件 | 用途 |
|---|---|
| [`p0_samples_v0.2.json`](p0_samples_v0.2.json) | 240 条 v0.2 记录（当前正式批次） |
| [`p0_samples_v0.3.json`](p0_samples_v0.3.json) | 14 条不确定性批次（`reviewed`，B 2026-10-21 签核） |
| [`p0_samples.json`](p0_samples.json) | 16 条 v0.1 冻结种子（A 适配器 `p0-record/v0.1.0` 仍读此文件） |
| [`../../schema/p0_record_v0.2.schema.json`](../../schema/p0_record_v0.2.schema.json) | v0.2 JSON Schema（Draft-07），含 `split`/`mechanism`/事件级 `U`/`p0_design` |
| [`../../schema/p0_record.schema.json`](../../schema/p0_record.schema.json) | v0.1 schema（冻结） |
| [`../../scripts/build_p0_v02.py`](../../scripts/build_p0_v02.py) | 可复现构建 240 条（种子升级 + 112 家族生成） |
| [`../../scripts/build_p0_uncertainty.py`](../../scripts/build_p0_uncertainty.py) | 可复现构建 v0.3 不确定性批次（7 家族） |
| [`../../scripts/build_p0_seed.py`](../../scripts/build_p0_seed.py) | 可复现构建 16 条 v0.1 种子 |
| [`../../scripts/validate_data.py`](../../scripts/validate_data.py) | 三个批次的 Schema + 跨字段一致性校验 |
| [`../../scripts/pair_diff_report.py`](../../scripts/pair_diff_report.py) | 逐字段 A/B 差异报告（`--pair P01-W2` 看单对，`--full` 看全部对） |
| [`../../scripts/audit_packet.py`](../../scripts/audit_packet.py) | 生成可复现的人工抽查包（固定 seed，机制各 1 对再按哈希排序补齐，签核框留空；已签核的表默认拒绝覆盖，需 `--force`） |
| [`../../scripts/export_eval_format.py`](../../scripts/export_eval_format.py) | 转成 C 的 `inputs.jsonl` / `labels.jsonl`（协议 `c-evaluation-draft-1`） |
| [`eval_v0.2/`](eval_v0.2/) | 已导出的评测格式：`inputs.jsonl`、`labels.jsonl`、`MAPPING.md` |
| [`../../docs/annotation/annotation_handbook_v1.0.md`](../../docs/annotation/annotation_handbook_v1.0.md) | 标注手册 v1.0 |
| [`../../docs/annotation/label_quality_plan_v0.1.md`](../../docs/annotation/label_quality_plan_v0.1.md) | 标注质量方案 |
| [`../../docs/annotation/p0_pair_review_table.md`](../../docs/annotation/p0_pair_review_table.md) | 复核表与机器预检结果 |
| [`../../docs/annotation/p0_spot_audit_v0.2_seed20261021.md`](../../docs/annotation/p0_spot_audit_v0.2_seed20261021.md) | v0.2 抽查包（10 对 / 20 条，39 个复选框已由 B 于 2026-10-21 全部勾为通过） |
| [`../../docs/annotation/p0_spot_audit_v0.3_all7.md`](../../docs/annotation/p0_spot_audit_v0.3_all7.md) | v0.3 全批抽查包（7 对 / 14 条，28 个复选框已全部勾为通过） |

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

| split | 家族数 | 说明（骨架级隔离） |
|---|---:|---|
| train | 72 | 每个机制 9 个家族 |
| dev | 24 | 每个机制 3 个家族 |
| test | 24 | 每个机制 3 个家族 |

按**任务骨架**分层：同一骨架不跨 split，避免模型记住任务而不是机制；同族 A/B 必在同一 split，`split` 是家族级字段。每机制仍为 9/3/3。校准集暂不单列，C 需要时从 dev 再切。

v0.3 批次引入 7 个新骨架（`W6/S6/D6/W7/S7/D7/W8`），与 v0.2 的骨架零重叠，按家族分为 train 3 / dev 2 / test 2；`split.calibration` 依旧为 0，等 C 定校准协议再分配。

## 5. 校验

```bash
python scripts/validate_data.py
python scripts/pair_diff_report.py
python scripts/pair_diff_report.py --full            # 全部家族的逐字段详情
python scripts/pair_diff_report.py --pair P04        # 单对逐字段详情
python scripts/export_eval_format.py          # 生成 data/p0/eval_v0.2/*.jsonl
python scripts/audit_packet.py --records 20 --seed 20261021   # 人工抽查包（签核框留空）
```

当前结果：

```text
OK: 16 records, 8 A/B pairs; schema and cross-field checks passed.
OK: 240 records, 120 A/B pairs; schema and cross-field checks passed.
OK: 14 records, 7 A/B pairs; schema and cross-field checks passed.
P07 identity failures: 0
```

校验覆盖（在 v0.1 基础上新增）：

- `split` 家族级一致、`mechanism` 合法；
- `person_comprehension` 与 `person_access` 一致；`MISUNDERSTOOD` 必须配非 `accurate` 的 `interpretation`；
- `indeterminate` 动作只能出现在 `p0_design.undefined_target=true` 且 `undefined_reason` 明确的记录；
- 15 个 `future_leak` 家族截断前逐字段相同（排除 `sample_id`/`variant`/`notes`）；
- `UNKNOWN` 不携带正证据；非 `UNKNOWN` 至少一条证据；平铺证据等于逐因子证据并集；
- 人物自述里的剩余步数（「还剩N步」）必须等于任务图算出的客观剩余步数（含嵌套任务的剩余数）；2026-10-21 新增，起因是 A/C 盲审抓到 P01 B 臂整体错 1；
- `completed_steps_at_cutoff` 必须能由事件重放出来（A 的诊断侧同样会检查）。

## 6. 当前质量状态

| 检查项 | 结果 |
|---|---|
| Schema 校验（v0.1 / v0.2 / v0.3） | 16/16、240/240、14/14 |
| 证据覆盖率（非 `UNKNOWN`） | 240/240（v0.3 另 14/14） |
| cutoff 无未来事件 | 240/240（v0.3 另 14/14） |
| A/B 对照隔离 | 120/120（逐字段 diff，事件条数已对齐）；v0.3：7/7 无意外漂移，但 4 对条数刻意不等（操控变量就是一条证据事件） |
| P07 输入一致性 | 15/15 PASS |
| 枚举覆盖（v0.2 + v0.3 合并） | 仅剩 `split.calibration` 未使用 |
| 自述步数一致性 | 三批次含步数的人物自述 14 条，全部等于任务图剩余步数（2026-10-21 修正后由校验强制） |
| B 人工复核 | v0.2：240/240，`status=reviewed`；v0.3：14/14，`status=reviewed`（2026-10-21） |
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
10. **扩量不要再改本文件。** 任何字段变化都要新增 schema 版本与新数据文件，并同步通知 A 更新哈希与回归预期。批次内的**取值/文案修正**（不动字段、不动标签语义）可以就地重建，但必须三件事同时做：更新本节 SHA256 并写明旧哈希、通知 A/C 重跑、在已签核的抽查包上追加带日期的勘误行而不是重新生成（重生成会抹掉人的复选框，`audit_packet.py` 已拒绝）。
11. **`contact_cancellation` B 臂的 `B=UNKNOWN` 待 A 表态。** 手册 §11.1 第 14 条：19 条 `B=UNKNOWN` 里 16 条（v0.2 的 P01-B + 14 个 B 臂 + v0.1 的 P01-B）在取消事件之后仍有人物陈述/返回行动未计入 B 证据，与 §2.5 第 1–2 条判定顺序冲突；另 3 条（v0.3 的 P01-W6-A/B、P08-S7-B）实测关键事件后人物无任何事件，`UNKNOWN` 合法。改标会动 A 的信念维监督信号且含 v0.1 冻结基线，**B 不单方面改，A 点头前这批标签保持原样**。

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

数据文件 SHA256：`3ca55cc51d50b8f38eed48053d78b8232b0708b4cfd71e1eeb6f6275321729ab`（LF；`sha256sum data/p0/p0_samples_v0.2.json` 可复核）。

> **2026-10-21 勘误：** 本批次 SHA256 原为 `fb58cf749086bab8d08a3074f97ce1cea8f6fd52b1ec844d3682b1c3e12f29ee`（已签核的抽查包与 `docs/internal/HANDOFF_2026-10-20_P0_v0.2.md` 记的是这一版；A/C 若已按旧哈希留档，需自行更新）。A/C 盲审回条指出 P01 B 臂自述"还剩两步"与任务图的剩余三步不符；实测 14 条含步数的人物自述全部错 1（模板硬编码了 v0.1 的三步故事），已在 `scripts/build_p0_v02.py` 改正并重新生成。**改动只有这 14 句 `description`，六因子标签、事件条数、`p0_expected`、划分全部未变**（`git diff` 可核）；`eval_v0.2/inputs.jsonl` 同步重导，`labels.jsonl` 无变化。`validate_data.py` 新增"人物自述步数必须等于客观剩余步数"的跨字段检查，防止再犯。

```text
dataset: p0-v0.2.0
n: 240 (120 A/B pairs, 120 families, 1831 events)
eval_export: data/p0/eval_v0.2/{inputs,labels}.jsonl (validated with C's mwm_eval.schema)
schema_pass: 240/240
evidence_coverage: 240/240
cutoff_no_future: 240/240
pair_isolation: 120/120
p07_input_identity: 15/15 PASS
splits: train 72 / dev 24 / test 24 families (blueprint-disjoint; 9/3/3 per mechanism)
domains: work 80 / collaboration_service 84 / daily_life 76 (records)
human_audit: 240/240 (B, reviewed)
second_reviewer: 0/8 (A/C, pending)
known_ambiguities: person_access_evidence naming collision with C; A adapter v0.1 only
p1_status: not_collected
noise_ceiling: N/A (P0 scripted); P1 TBD
```

### v0.3 不确定性批次（B 已复核）

数据文件 SHA256：`8dfba39ba7d0b3b2779e141038460c5abd7e2c77d804f8b8d94500849ef712e8`（LF；`sha256sum data/p0/p0_samples_v0.3.json` 可复核）。

```text
dataset: p0-v0.3-uncertainty   # schema 仍是 p0-record/v0.2.0
status: reviewed by B 2026-10-21; A/C blind review still pending
n: 14 (7 A/B pairs, 7 families, 77 events)
purpose: fill the 11 enum values v0.2 declares but never uses
  state.V.UNKNOWN=1  state.F.UNKNOWN=1  state.A.UNCERTAIN=1  state.B.UNRESOLVED=1
  state.C.ACTIVE=1   state.C.UNKNOWN=1  event.person_access.UNCERTAIN=1
  event.person_comprehension.NOT_UNDERSTOOD=1, .UNCERTAIN=4
  event.certainty.PROBABLE=1, .UNCERTAIN=2
schema_pass: 14/14
evidence_coverage: 14/14
cutoff_no_future: 14/14
pair_isolation: 7/7 clean A/B (pair_diff_report --full, no unintended field drift)
paired_event_count_equal: 3/7 - P01-S6 / P05-D6 / P02-D7 / P08-S7 differ by design
policy_by_mechanism: 1:1 as v0.2; unclear-comprehension arms = suspend_or_wait; no indeterminate here
splits: train 3 / dev 2 / test 2 families (blueprints W6 S6 D6 W7 S7 D7 W8, disjoint from v0.2)
enum_gap_remaining: record.split.calibration (needs C's calibration protocol)
human_audit: 14/14 (annotator_id=B, status=reviewed)
self_audit_packet: docs/annotation/p0_spot_audit_v0.3_all7.md (28 boxes, all ticked 通过)
```

## 10. 后续

| 阶段 | 交付 |
|---|---|
| 当前 | 240 条 v0.2 + 14 条 v0.3 不确定性批次，均 `reviewed`（B 自审签核完成） |
| 已完成（B） | [`p0_spot_audit_v0.3_all7.md`](../../docs/annotation/p0_spot_audit_v0.3_all7.md)（7 对 / 28 框）与 [`p0_spot_audit_v0.2_seed20261021.md`](../../docs/annotation/p0_spot_audit_v0.2_seed20261021.md)（10 对 / 39 框）已由 B 于 2026-10-21 全部勾为通过，v0.3 随之升 `reviewed` |
| 下一步（A/C，B 催办） | 每机制抽 1 条盲审（8 条）→ 仲裁 → `adjudicated`；A 加 v0.2/v0.3 适配器分支；C 确认字段映射与 `split.calibration` 协议 |
| P1 | 另立 schema 与标注流程；当前不纳入竞赛证据 |

> 详细规则见 [标注手册 v1.0](../../docs/annotation/annotation_handbook_v1.0.md)、[质量方案](../../docs/annotation/label_quality_plan_v0.1.md) 与 [复核表](../../docs/annotation/p0_pair_review_table.md)。
