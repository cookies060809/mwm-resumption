# ECR-MWM 标注手册 v0.1（草案）

> **状态：草案，未经过双人标注与仲裁验证。** Owner：B。日期：2026-10-20。
> 对应 schema：`schema/annotation.schema.json` v0.1.0。配套方案：研究方案第 3–5、8 节。
> 本手册定义“如何把事件历史与状态标签写成可检验的数据”，不主张这些标签等于真实心理测量。

---

## 1. 目的与适用范围

本手册用于构建 ECR-MWM 的 P0 受控诊断集与 P1 真实行为集，支持：

- **T1**：预测中断后 `H` 个决策机会内是否恢复原目标；
- **T2**：在恢复发生时，预测首个恢复步骤；
- **T3**：输出 `V/F/A/B/C/Q` 状态标签分布及证据引用。

首版边界：**单个人物、主要目标明确、多步执行过程、可能含插入任务、结构化文本事件**。视觉识别、目标发现、机器人控制不在 v0.1 标注范围内。

---

## 2. 基本单位与时间截断

### 2.1 样例（sample）

一条样例 = 一个基础故事 `base_story_id` + 一个变体 `variant_id` + 一个预测截断点 `cutoff_event_id`。

- `sample_id` 采用 `<base_story_id>-<variant_id>`，例如 `P01-A`。
- 最小对照对由同一 `base_story_id` 的至少两个变体组成，`pair_id` 相同。
- 同族变体必须整体进入同一个 split；禁止把 A/B 拆到训练与测试两侧。

### 2.2 预测时刻 `t`

- `cutoff_event_id` 必须是 `observed_events` 中的事件。
- 所有输入证据的时间必须 `<= t`；`t` 之后的真实结果只能进入 `p1_observation` 或评价标签，**不得**进入 `observed_events`。
- `horizon` 默认 `{"type": "decision_opportunities", "value": 3}`；多窗口实验在配置中声明，不修改既有标签含义。

### 2.3 时间格式

- 优先使用 ISO 8601（含日期与时区），例如 `2026-10-20T10:05:00+08:00`。
- P0 单日脚本可使用 `HH:MM` 或 `HH:MM:SS`，但同一 `base_story_id` 内必须一致。
- `time` 是场景内时间，不等同于真实采集时间；真实时间预测必须有可靠时间戳与删失建模。

---

## 3. 事件记录

### 3.1 字段

| 字段 | 含义 | 规则 |
|---|---|---|
| `event_id` | 样例内唯一事件 ID | 建议 `e01`、`e02`；变体中同一角色事件尽量复用 ID |
| `time` | 场景时间 | 见 2.3 |
| `actor` | 事件主体 | 人物 ID、系统 ID 或 `background` |
| `event_type` | 受控事件类型 | 见 3.3；新增需改 schema 并评审 |
| `goal_id` | 相关目标 | 无目标时 `null`，但字段必须存在 |
| `step_id` | 相关任务步骤 | 无步骤时 `null`，必须在任务图中存在 |
| `world_effect` | 对客观世界/任务状态的改变 | 结构化对象；不允许只写叙事性长文本 |
| `observer_evidence` | 观察者为何能看到此事件 | 来源、记录方式或可核查描述；可为 `null` |
| `person_access` | 人物接触该事件的证据标签 | `ACCESSED / NOT_ACCESSED / UNCERTAIN / NOT_APPLICABLE` |
| `person_access_evidence` | 支持接触判断的证据 | 可为 `null`；不得从客观发生直接推断接触 |
| `source` | 事件来源 | `BACKGROUND_SYSTEM / SENSOR / PERSON_STATEMENT / OBSERVER_NOTE / SCRIPT / OTHER` |
| `certainty` | 标注者对事件记录的确定性 | `HIGH / MEDIUM / LOW / UNKNOWN` |

### 3.2 原子性

- 一条事件只记录一个可判断的状态变化。不要用一条事件同时表示“核对地址完成 + 开始包装 + 接到电话”。
- 复合叙事必须拆成多条事件；不能拆分时，在 `note` 中说明并降低 `certainty`。
- 事件顺序优先按时间；同一时间戳的事件必须在 `note` 中给出因果或并列关系。

### 3.3 受控事件类型（v0.1）

`goal_started`、`goal_resumed`、`goal_completed`、`goal_cancelled`、`goal_suspended`、`goal_abandoned`、`step_started`、`step_completed`、`step_failed`、`interruption_started`、`interruption_ended`、`notification_queued`、`notification_delivered`、`notification_accessed`、`notification_acknowledged`、`person_action`、`person_statement`、`environment_change`、`other`。

约定：

- `notification_queued` / `notification_delivered` 表示系统侧送达状态，不等于人物接触；人物接触必须另记 `notification_accessed` 或提供独立证据。
- `goal_cancelled` 是客观目标失效事件，不自动改变人物信念；人物是否知道由 `person_access` 与后续状态标注决定。
- `person_statement` 可用于表达承诺、放弃、误解等主观信息，但必须给出可核查语句或记录来源。
- 使用 `other` 时必须在 `note` 中说明，并在下一次 schema 评审中决定是否纳入词表。

### 3.4 接触证据

- `ACCESSED`：有直接证据表明人物看到/听到/读出/操作了该事件（例如打开通知并确认）。
- `NOT_ACCESSED`：有证据表明事件只在后台队列、人物未看到，且没有其他可见线索。
- `UNCERTAIN`：证据不足或来源冲突；不能强行归为前两者。
- `NOT_APPLICABLE`：该事件不涉及人物接触判断（例如纯后台状态快照）。

`ACCESSED` 只表示接触，不自动表示理解或采信；理解/误解必须由 `B` 与 `C` 的证据支持。

---

## 4. 状态标签

联合状态 `Z_t = (V_t, F_t, A_t, B_t, C_t, Q_t)`。其中 **V、F 是客观世界/任务状态；A 是接触证据；B、C、Q 是待推断的人物认知/意图/进度状态**。六者不是六个同质的“真实心理变量”。

| 字段 | 标签 | 严格含义 | 需要的证据 |
|---|---|---|---|
| `V` 客观目标有效性 | `VALID / CANCELLED / FULFILLED / UNKNOWN` | 目标在世界中是否仍有效、已取消或已完成 | 后台记录、独立事实、任务结果；不依赖人物是否知道 |
| `F` 客观执行可行性 | `READY / BLOCKED / UNKNOWN` | 工具、资源、权限、依赖步骤是否允许继续 | 物理/系统证据；“有效”可以同时“受阻” |
| `A` 接触证据 | `ACCESSED / NOT_ACCESSED / UNCERTAIN` | 人物是否接触到关键事件的可观察证据 | 已读/听见/看见/操作记录；接触不等于理解 |
| `B` 人物主观信念 | `BELIEVES_VALID / BELIEVES_INVALID / UNRESOLVED / UNKNOWN` | 人物认为目标是否仍有效 | 自述、明确行动或脚本中可核查信息；**不可直接从 V 复制** |
| `C` 原目标承诺 | `ACTIVE / SUSPENDED / ABANDONED / COMPLETED / UNKNOWN` | 人物是否仍在推进、暂挂仍想继续、明确放弃、认为已完成 | 明确陈述/行动/脚本策略；暂未行动不等于放弃 |
| `Q` 主观恢复步骤 | `step_id / UNKNOWN / NOT_APPLICABLE` | 人物认为的下一个未完成步骤 | 人物对步骤完成状态的掌握 + 任务图；可与客观最优步骤不同 |

### 4.1 标签判定顺序

1. **先标 V/F**：只使用独立于人物心智的客观证据。
2. **再标 A**：只判断接触证据，不推断理解。
3. **再标 B**：仅使用人物可获得的直接证据与间接线索；若没有证据，`B` 应为 `UNKNOWN` 或 `UNRESOLVED`，不能因为 `V` 改变就改变 `B`。
4. **再标 C**：查看历史承诺、人物陈述、当前行动与脚本策略。`C=SUSPENDED` 表示暂挂但仍意图继续；`C=ABANDONED` 需要明确放弃证据或脚本明确规定。
5. **最后标 Q**：基于人物认为已完成的步骤与任务依赖，给出下一个未完成步骤；无法确定时用 `UNKNOWN`。
6. 任何一步证据不足，保留 `UNKNOWN`，不得用其他因子的标签补全。

### 4.2 `Q` 的特殊规则

- `Q` 是**主观**的：人物可能不知道某步骤已完成，或认为某步骤未完成而实际已完成。
- 当 `C=ABANDONED` 或 `C=COMPLETED` 时，若人物不再有恢复意图，`Q=NOT_APPLICABLE`。
- 当 `C=ACTIVE/SUSPENDED` 但无法确定人物认为的下一步，`Q=UNKNOWN`。
- `Q` 不得直接等于“客观最优下一步”；必须有关于人物掌握步骤状态的证据。
- 恢复步骤评价只对“确实发生恢复且步骤可辨认”的样例计算，不对未恢复样例填 `Q` 作为未来标签。

### 4.3 未知与删失

- `UNKNOWN`：在截断时刻证据不足，无法确定状态。
- `censored` / `right_censored`：截断后的行为窗口没有被完整观察，不能判定“未恢复”。
- 二者不得互换。P1 首版固定窗口二分类时，若窗口未覆盖完整且未观察到恢复，应剔除或使用生存/hazard 模型，并报告删失比例。

---

## 5. 六条硬性约束

1. **客观与主观分离**：`V=CANCELLED` 不推出 `B=BELIEVES_INVALID`。
2. **接触与理解分离**：`A=ACCESSED` 不自动推出人物正确理解通知；理解需要额外证据。
3. **有效与可执行分离**：`V=VALID, F=BLOCKED` 完全合法。
4. **状态与行为分离**：`C=SUSPENDED` 不说明未来 `H` 内一定恢复；`C=ABANDONED` 也不等于未来绝无可能重新考虑，只是当前证据下的承诺状态。
5. **未知与删失分离**：`UNKNOWN` 是证据不足；`right_censored` 是观察不足。
6. **证据链强制保存**：每个非 `UNKNOWN` 标签都应能对应一个或多个 `evidence_event_ids`、脚本策略或已批准标注证据；禁止用未来结果反推时刻 `t` 的信念。

### 5.1 关于脚本标签

P0 允许使用脚本人物规则生成标签，但必须：

- 在 `provenance.status` 标注为 `draft/reviewed`，并在 `p0_expectation.scripted_policy` 写明策略；
- 在 `notes` 中声明“脚本标签，不是真实人类心理”；
- 不得把脚本标签与 P1 真实标签合并统计；
- 不得用脚本策略替代对现实人物的证据要求。

例如 P01-A 中 `C=ABANDONED` 是脚本人物在确认取消后的设定状态，不是“只要 `B=BELIEVES_INVALID` 就必然放弃”的通用规则。

---

## 6. 成对样例标注

### 6.1 类型 I：不可见世界变更（信息等价）

- 两条样例的外部世界事实不同，但人物初始假设、截至 `t` 的全部可获得信息和可观察行动相同；
- 隐藏事件不得产生任何人物可察觉的后果；
- 人物心智后验 `(B,C,Q)` 在受控条件下应相同；
- 客观 `V/F` 可以不同，不要求客观状态后验相同。

标注时必须记录：

- `counterfactual_pair.paired_sample_id`；
- `controlled_change`：唯一或主要变化；
- `information_equivalence: true`；
- 共享的观察事件与人物可获得信息清单（在 `notes` 中）。

### 6.2 类型 II：人物信息变化（应有辨识）

- 世界事实和其他条件相同；
- 人物收到/理解一条可信消息 vs 没有获知；
- 应按标注证据产生合理的 `B/C/Q` 差异，但不强制行动标签必然改变；
- `information_equivalence: false`。

### 6.3 未来泄漏负对照（P07）

- 两条样例在 `t` 之前的输入完全一致，只改变 `t` 之后发生的真实结果；
- `state_at_cutoff` 与 `observed_events` 必须一致；
- 预测分布应相同，但未来标签可以不同；
- 若模型在 `t` 的预测因未来标签不同而变化，判为泄漏或实现错误。

### 6.4 成对一致性检查

- 同一 `base_story_id`、同一 `pair_id`；
- `variant_id` 不同；
- 除受控变化外，任务图、截止点、时长、环境、步骤完成状态保持一致，或在 `notes` 中逐项说明差异；
- 双向 `paired_sample_id` 必须互相指向。

---

## 7. P0 脚本集

### 7.1 必含场景

| Pair | 主要检验 | 核心变化 |
|---|---|---|
| P01 取消认知 | 客观事实 ≠ 人物信念 | 人物是否接触并确认取消通知 |
| P02 旧目标承诺 | 长期承诺 vs 滑窗 | 早前“稍后继续” vs “任务撤销” |
| P03 恢复位置 | 未完成步骤指针 | 中断前是否完成打印运单 |
| P04 他人代完成 | 完成事实与信念分离 | 人物是否被告知同事已完成 |
| P05 暂时不可执行 | 承诺 ≠ 可执行性 | 工具已恢复 vs 仍缺失且人物可见 |
| P06 嵌套中断 | 目标层级与恢复顺序 | 插入任务是否完成 |
| P07 未来泄漏负对照 | 不可预知未来 | 仅改变 `t` 之后的真实结果 |
| P08 接触但误解 | 接触 ≠ 理解 | 已读且正确理解 vs 看过但误读为暂缓 |

### 7.2 P0 标注要求

- 每个 pair 至少 2 个变体，仅改变一个受控因素；
- 明确写出 `p0_expectation.scripted_policy`、`expected_resume`、`expected_resume_step` 与理由；
- 预期行为必须由脚本规则推出，不得把研究者对真实人物的猜测写成 P0 结论；
- P0 结果只能报告受控协议诊断，不得写成真实人类恢复预测能力；
- P0 覆盖三个领域（工作办公、日常生活、协作/服务）与分层因素时，在数据卡中更新覆盖表。

---

## 8. P1 真实行为集

### 8.1 恢复的操作性定义

人物先前确实开始过 `g`；中断期间停止推进 `g` 并转向其他活动；在 `t` 之后的观察窗口内，首次出现**可归属于 `g` 的、推动尚未完成步骤的实际行为**，记录 `resume=1`。

以下情形不自动算作行为恢复：

- 仅再次谈起该目标；
- 返回原地点但没有推进步骤；
- 心里仍想做但没有可观察行动；
- 行动归属于插入任务或无关任务。

无法辨认时记 `UNKNOWN`，并说明证据缺口。

### 8.2 标注要求

- 至少两名独立标注者标注 `V/F/A` 与可观察步骤；
- `B/C/Q` 只有在自述、明确行动或可验证证据支持时才标注；否则保持 `UNKNOWN` 并遮蔽损失；
- 记录 `p1_observation.observed_resume`、`resume_step`、`censoring_status`、观察窗口与证据事件 ID；
- 真实恢复步骤必须是“未来实际恢复时执行的首个原目标相关且尚未完成的步骤”；
- 不提交原始视频/音频/屏幕记录；只提交批准元数据或脱敏派生结果；
- 不把 P0 脚本期望复制为 P1 实际结果。

### 8.3 伦理与许可

- 采集前完成知情同意、隐私审查与数据最小化；
- 明确用途、保存期限、访问权限与撤回机制；
- 对外发布前移除可识别个人信息，并说明采集时间、场景与限制；
- 许可不明确的材料不得入库。

---

## 9. 标注流程与一致性

### 9.1 流程

1. **准备**：B 建任务图、事件流、截止点与成对元数据；C 检查泄漏与评测口径。
2. **独立标注**：两名标注者在不讨论的情况下分别标注状态、证据与 `UNKNOWN`。
3. **汇总**：B 合并为 consensus 记录；分歧逐项列出。
4. **仲裁**：第三方或 B + 一名标注者依据证据裁定；无法裁定保留 `UNKNOWN`。
5. **复核**：A 检查标签可训练性与状态转移一致性；C 检查输入/标签泄漏与评价可用性。
6. **入库**：通过 `python scripts/validate_data.py` 与 PR 评审后合并。

### 9.2 一致性指标

- 两个标注者：按因子报告 Cohen's κ 与原始一致率；
- 多于两个标注者或存在缺失：报告 Krippendorff's α；
- 同时报告样本量、`UNKNOWN` 比例与分歧类型；
- 不预设“合格阈值”；低一致性因子必须复核手册、补充证据或缩小标签适用范围，而不是强制共识。

### 9.3 质量控制

- 每批数据抽查成对样例与未来泄漏负对照；
- 对 `C=ABANDONED`、`Q=NOT_APPLICABLE`、`A=ACCESSED → B` 等高风险标签做二次复核；
- 记录标注手册版本、schema 版本、标注者 ID、仲裁记录与变更日志；
- 任何规则变更都必须经过 PR，并对既有样例做迁移或标注“旧版本”。

---

## 10. 记录结构与命名

### 10.1 文件布局

```text
data/p0/<domain>/<base_story_id>/<variant_id>.json
data/p1/templates/sample_record.template.json
```

- P0 示例目前位于 `data/p0/examples/work/`，正式数据按上述布局扩展。
- P1 真实数据不进入 Git；只保留模板、元数据或批准派生结果。
- 文件名与 `sample_id` 一致，避免同一故事多份副本。

### 10.2 必填元数据

- `schema_version`、`sample_id`、`base_story_id`、`variant_id`、`pair_id`、`domain`、`split`；
- `goal_id`、`cutoff_event_id`、`horizon`、`task_graph`、`observed_events`；
- `state_at_cutoff`、`state_evidence_event_ids`；
- `p0_expectation`（P0）或 `p1_observation`（P1）；
- `counterfactual_pair`（成对样例）；
- `provenance`（手册版本、创建者、时间、评审状态）；
- `access_level`（`public/internal/restricted`）。

### 10.3 版本

- Schema 版本写入每条记录；不兼容变更提升主版本并附迁移说明。
- 手册版本与 schema 版本分开维护；标注规则变化必须同时更新两者或在记录中注明差异。
- 旧样例不得静默重标；保留版本与变更原因。

---

## 11. 提交前检查清单

- [ ] `python scripts/validate_data.py` 通过
- [ ] 事件 ID 在样例内唯一
- [ ] `cutoff_event_id` 存在于 `observed_events`
- [ ] `state_evidence_event_ids` 均为已观察事件
- [ ] `Q` 是合法步骤 ID 或 `UNKNOWN/NOT_APPLICABLE`
- [ ] P0 预期步骤在任务图中
- [ ] 成对样例双向引用、同族同 split
- [ ] 没有 `t` 之后的事件进入输入
- [ ] 没有 P1 原始数据或个人信息
- [ ] P0 脚本标签与 P1 真实标签分开
- [ ] 非 `UNKNOWN` 标签有证据
- [ ] 未写入未经实验支持的结论

---

## 12. 待决问题（v0.2）

1. 是否在 schema 中加入逐标注者投票与逐因子置信度，以直接计算 IAA？
2. 事件类型词表如何扩展到多模态与多人物场景？
3. `C=ABANDONED` 与 `C=SUSPENDED` 在“已知取消但未明确表态”情形下的边界。
4. `C=COMPLETED` 与客观 `V=FULFILLED` 不一致时的 `Q` 规则。
5. 跨日/多时区事件的时间格式与排序。
6. P1 的来源、许可、伦理审批与访问控制方案。
7. 标注工具（表格 / Label Studio / 自建）与审计日志。
8. 双人标注覆盖全部样例还是抽样复核；抽样比例与分层方式。
9. 中文标签展示与英文枚举的映射规范。
