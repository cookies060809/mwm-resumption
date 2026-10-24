# 状态标签标注手册 v1.0

**项目：** ECR-MWM（认知可达性约束的动态心智世界模型）
**文档版本：** v1.0.3｜2026-10-21（升版依据：A/C 盲审回条实测——补 §2.3 的 P0 `READY` 可判定口径、§11.1 第 14 条记录待 A 表态的信念维缺口、修 v0.2 P01 B 臂自述步数并给 `validate_data.py` 加回归检查；v1.0.1 补 §1.4 未知档位判据，v1.0.2 记录 v0.3 签核通过）
**Owner：** B（数据与认知机制）
**状态：** 已冻结事件契约与六因子定义；P0 标注状态 `reviewed`，A/C 盲审与仲裁未完成
**配套文件：** `schema/p0_record_v0.2.schema.json`、`data/p0/p0_samples_v0.2.json`、`data/p0/p0_samples_v0.3.json`（`reviewed`）、`scripts/validate_data.py`、`scripts/pair_diff_report.py`、`scripts/audit_packet.py`、`scripts/build_p0_v02.py`、`scripts/build_p0_uncertainty.py`、抽查签核表 [`p0_spot_audit_v0.2_seed20261021.md`](p0_spot_audit_v0.2_seed20261021.md) / [`p0_spot_audit_v0.3_all7.md`](p0_spot_audit_v0.3_all7.md)

> **先读这一句：** P0 是脚本化的受控诊断数据，标签是“按脚本规则应出现的状态”，不是真实人类心理测量。P1 原计划为真实行为数据；2026-10-23 决策后不再做真人采集，P1 改为公开数据派生包，六变量中只有 V 全量有效，其余规则映射值已按 `state_withdrawn` 撤回。没有证据的 `B/C/Q` 仍必须标 `UNKNOWN` 或遮蔽，不得用猜测补齐。

> **竞赛阶段说明（2026-10-24）：**
> - 当前 P0 发布版为 `p0-record/v0.2.0` 记录、`p0-release/v0.4.0` 打包（v0.3 + 14 条 B 标签仲裁），127 个家族 × A/B = 254 条（150/52/52），B 已完成人工复核（`annotation.status=reviewed`）；A/C 盲审与独立仲裁尚未完成，不得写成 `adjudicated`。
> - P1 为公开数据派生包（`data/p1/public_derived/`，2,863 条，真人记录 0）。竞赛方案中只能写作“公开数据派生的辅助任务评测”，不得写真实人类恢复预测；P0 标签也不得用于声称真实人类恢复能力。
> - 对外材料（技术方案/PPT/视频）不得出现学校名称、Logo、指导教师信息；提交要求见 [`competition/README.md`](../../competition/README.md)。

---

## 1. 状态模型与记录边界

### 1.1 联合状态

每条记录在截断时刻 `t` 标注联合状态：

```text
Z_t = (V_t, F_t, A_t, B_t, C_t, Q_t)
```

其中：

- `V/F` 是**世界/任务状态**，原则上可由后台记录、工具状态、任务图等独立证据确定；
- `A` 是**人物对关键事件的接触证据**，不是人物“知道了”的断言；
- `B/C/Q` 是**待推断的人物认知、承诺与主观进度**，只能由人物可获得的证据支持。

不要把六者统称为六个“真实心理变量”。`V` 和 `F` 是客观侧，`B/C/Q` 是主观侧，`A` 是连接两侧的证据门控。

### 1.2 输入、标签与仅设计字段

| 类别 | 字段 | 是否可作为模型输入 |
|---|---|---|
| 事件输入 | `observed_events`（截至 `cutoff_event_id`） | 是 |
| 任务图 | `task_steps`、`task_dependencies` | 是 |
| 客观进度 | `completed_steps_at_cutoff` | 是；应能由事件推导，不能包含人物主观进度 |
| 嵌套任务 | `interrupting_task` | 是；状态必须是观察者可核验的客观状态 |
| 状态标签 | `state_at_cutoff` | 否，预测目标 |
| 证据标注 | `state_evidence_*` | 否，监督/审计用 |
| P0 脚本标签 | `p0_scripted_policy`、`p0_expected_action`、`p0_expected` | 否，P0 诊断目标 |
| P1 行为标签 | `p1_observed_resume`、`p1_observed_first_step`、`p1_censoring_status` | 否，评价目标 |
| 设计说明 | `notes`、`annotation` | 否，人工审计用 |

**硬边界：** `observed_events` 的最后一条必须就是 `cutoff_event_id`。任何 `t` 之后的事件、结果或标签都不能进入输入。P07 的 `notes` 含截断后设计结果，仅用于说明泄漏负对照，绝不能作为模型输入。

### 1.3 P0 与 P1

| | P0 受控诊断 | P1 真实行为 |
|---|---|---|
| 来源 | 人工脚本 + 明确规则 | 经许可的真实连续行为/任务日志 |
| 标签性质 | 脚本规则决定的真值；可写 `UNKNOWN`/`UNCERTAIN`，但必须是脚本刻意让人物缺证据的结果（判据见 1.4） | 有证据的观察标注，缺证据的 `B/C/Q` 只能 `UNKNOWN` 或遮蔽 |
| 用途 | 管道、泄漏、对照逻辑、状态一致性 | 公开数据派生的恢复行为评测、V 维诊断、按源校准 |
| 结论口径 | 只能报告协议/逻辑结果 | 只能报告公开数据派生结论，不得写真实人类恢复预测 |
| 当前状态 | 127 家族 / 254 条（v0.3 发布版），`status=reviewed` | 2,863 条公开派生；无真人记录；六变量仅 V 全量有效，其余已撤回 |

### 1.4 P0 里未知档位的合法性判据

P0 的标签确实"可完全确定"，但**确定的对象是脚本设定，不是世界的模糊性**。同一个 `UNKNOWN` 有两种相反的来源，只有前一种合法：

| 合法 | 非法 |
|---|---|
| **设计出来的认知处境**：脚本安排人物收不到通知、收到矛盾通知或只有间接线索，于是"人物此刻没有稳定信念"本身就是真值。 | **标注者没有判定**：B 自己没决定该写什么，拿 `UNKNOWN` 当空格填。 |
| **事件证据本身模糊**：投递回执缺失或不完整，用 `person_access=UNCERTAIN`、`certainty=PROBABLE/UNCERTAIN` 如实记录证据强度。 | **为了填满字段而猜**：违反 2.3 末段“不要为了填满字段而猜”，也污染 `p0_expected`。 |

唯一可操作的判据：**能不能指名 cutoff 之前缺的是哪一条证据。**

- 能 → 合法。`state_evidence_by_factor` 对应因子留空列表（如 P01-B 的 `"B": []`），并在 `notes` 写明缺什么、为什么人物无法判定。
- 不能 → 非法。回去改脚本或补事件，不许留 `UNKNOWN`。

配套纪律：未知档位不得连带把 `Q` 也写成 `UNKNOWN`，除非脚本确实没给人物任何步骤线索（见 2.7）；`p0_expected` 可以要求模型输出低置信度，但不能要求它"正确答案是不知道"之外的东西。

> 这条判据也是 P0 不确定性的价值来源：如果所有事实都是 `CERTAIN`、所有接触都成功，滤波器在 P0 上学不到"该犹豫时犹豫"，评测会退化成"永远自信"的平凡解。v0.2 的 1831 个事件确实全是 `CERTAIN`，11 个不确定性档位一次都没出现（见 §11.1 第 13 条）。补的那一批是 `data/p0/p0_samples_v0.3.json`（7 家族 / 14 条，`scripts/build_p0_uncertainty.py` 可复现生成），把 11 档各覆盖至少一次；B 于 2026-10-21 逐对复核，[`p0_spot_audit_v0.3_all7.md`](p0_spot_audit_v0.3_all7.md) 的 28 个复选框全部勾为通过，批次随之升 `reviewed`。**这条判据第一次成批检验的结论是“可判”**，但打勾的仍是 B 自己的眼睛，A/C 盲审是另一张表。

---

## 2. 六个状态因子

### 2.1 总表

| 字段 | 含义 | 枚举 | 允许的正证据 | 禁止的推断 |
|---|---|---|---|---|
| `V` 客观目标有效性 | 目标在世界上是否仍然有效 | `VALID / CANCELLED / FULFILLED / UNKNOWN` | 后台状态、任务记录、物理结果、独立第三方确认 | 人物说“取消”不能直接改 `V`；人物不知道也不能改 `V` |
| `F` 当前客观执行可行性 | 继续执行所需条件是否允许 | `READY / BLOCKED / UNKNOWN` | 工具、资源、权限、依赖步骤状态 | 不能从 `V=VALID` 推出 `F=READY`；不能从人物意愿推出可行性 |
| `A` 对关键事件的接触证据 | 人物是否接收到关键信息 | `ACCESSED / NOT_ACCESSED / UNCERTAIN` | 已读/听见/看见/操作/投递与接收记录 | 接触不等于理解；`ACCESSED` 不能推出正确信念 |
| `B` 人物主观信念 | 人物认为目标是否仍有效 | `BELIEVES_VALID / BELIEVES_INVALID / UNRESOLVED / UNKNOWN` | 自述、明确行动、可核查的推断 | 不能从 `V` 复制；不能从“没行动”推断 |
| `C` 原目标承诺 | 人物对原目标的承诺状态 | `ACTIVE / SUSPENDED / ABANDONED / COMPLETED / UNKNOWN` | 明确承诺/放弃/完成陈述，持续行动，目标记忆 | 暂停不等于放弃；暂时不行动不等于 `ABANDONED` |
| `Q` 主观恢复步骤 | 人物认为的第一个未完成步骤 | `step_id / UNKNOWN / NOT_APPLICABLE` | 人物自述、已完成的步骤知识、可观察操作 | 不等于客观最优下一步；可以指向客观上已完成的步骤 |

### 2.2 `V`：客观目标有效性

**判定顺序：**

1. 找 `task_cancelled`、`task_completed_by_other`、后台任务状态、物理结果等独立证据。
2. 有取消记录且目标仍是同一 `goal_id` → `CANCELLED`。
3. 有完成记录（包括他人代完成）→ `FULFILLED`。
4. 有目标创建/激活记录且无取消/完成记录 → `VALID`。
5. 证据不足或来源冲突 → `UNKNOWN`。

**注意：**

- `V=FULFILLED` 表示客观任务已完成，不表示人物知道。P04-B 中 `V=FULFILLED` 而人物仍以为要做。
- `V=CANCELLED` 表示客观目标无效，不表示人物放弃。P01-B 中 `V=CANCELLED` 而人物不知情并继续包装。
- 人物说“取消吧”是 `C/B` 的证据，不是 `V` 的证据；除非同时有后台/任务记录。

### 2.3 `F`：当前客观执行可行性

**判定顺序：**

1. 找出继续执行所需的条件：工具、材料、权限、设备、前置步骤。
2. 有任一必要条件缺失且无法绕过 → `BLOCKED`。
3. 所有必要条件可用 → `READY`。
4. 证据不足 → `UNKNOWN`。

**注意：**

- `V=VALID, F=BLOCKED` 完全合法（P05-B）。
- `F` 是客观可行性，不是人物认为的可行性。人物可能不知道工具缺失；此时 `F=BLOCKED`、`A=NOT_ACCESSED`，`B` 仍可能 `BELIEVES_VALID`。
- 目标已 `FULFILLED/CANCELLED` 时，`F` 没有“继续执行”的自然含义。v0.1 约定：若资源状态有明确证据，仍可标 `READY/BLOCKED`；否则标 `UNKNOWN`。不要为了填满字段而猜。
- **P0 里 `READY` 的可判定口径（2026-10-21 补，回应 A/C 盲审"READY 证据是否充分"）：** `READY` = cutoff 前**不存在**作用于原目标 `step_id` 的 `resource_missing` 事件，且**至少一条必要条件的状态可见**（前置步骤完成、`resource_available` 事件、或设备回执正常的完成事件）。实测三批次 270 条：252 条 `READY` 无一空证据，其中 162 条靠"前置步骤已完成"、22 条另有 `resource_available`；17 条 `BLOCKED` 全部由专门的 `resource_missing` 事件支撑；28 条含"出故障"字样的 `READY` 记录里，故障主体一律是打断任务本身（`actor=manager` 的 `person_action`），不挂原目标步骤、也不计入 `F` 证据，所以 `READY` 没有被任何在脚本内的事件矛盾。P0 的世界是脚本写出来的，"脚本没安排阻碍"可核验，不等同于 §2.1 禁止的"从 `V=VALID` 推 `READY`"；需要更强正面证据时补 `resource_available` 事件，不要靠人物意愿推。

### 2.4 `A`：对关键事件的接触证据

**关键事件**由当前对照设计决定：P01/P04/P08 是取消/完成通知，P03 是打印完成状态，P05 是工具状态，P06 是嵌套任务完成状态，P07 是中断/返回事件。`A` 必须按“关键事件”标注，不是对全部事件取平均。

**判定顺序：**

1. 该事件是否被投递到人物可接触的通道（屏幕、声音、现场、操作反馈）？
2. 是否有接收证据（已读、点击确认、复述、当场操作）？
3. 有投递且有接收 → `ACCESSED`。
4. 有明确证据表明无通道/未投递/未接收 → `NOT_ACCESSED`。
5. 通道或接收不确定 → `UNCERTAIN`。

**注意：**

- `A=ACCESSED` 只说明“接触到了”，不说明“理解了”。P08-B 中人物读了取消通知但误读为暂缓，仍是 `ACCESSED`。
- `A=NOT_ACCESSED` 不必然推出 `B=UNKNOWN`：人物可能通过间接线索推断。P01-B 没有直接通知，但也没有间接线索，所以 `B=UNKNOWN`。
- 事件级 `person_access` 是逐事件的投递/接收标注；记录级 `state_at_cutoff.A` 是关键事件的汇总判断。两者不能互相替代。

### 2.5 `B`：人物主观信念

**判定顺序：**

1. 只使用人物可获得的证据：自述、明确行动、人物看到的通知、可听/可见线索。
2. 有明确“仍然有效/继续”的表达 → `BELIEVES_VALID`。
3. 有明确“无效/取消/不做了”的表达 → `BELIEVES_INVALID`。
4. 人物收到冲突信息且尚未形成稳定判断 → `UNRESOLVED`。
5. 没有足够证据 → `UNKNOWN`。

**`UNRESOLVED` 与 `UNKNOWN` 的区别：**

- `UNRESOLVED`：有证据表明人物正处于冲突/未决状态（例如两条矛盾通知都看到了）。
- `UNKNOWN`：标注者没有证据判断人物相信什么。**不要把“标注者不知道”写成 `UNRESOLVED`。**

**注意：**

- 不能从 `V` 复制 `B`。P01-B 是核心反例：`V=CANCELLED`、`B=UNKNOWN`。
- 不能从 `C` 反推 `B`。人物可以相信目标有效但主动放弃（P02-B），也可以相信目标无效但尚未明确承诺状态。
- 人物说“暂缓”通常表示 `BELIEVES_VALID` + `C=SUSPENDED`，不是 `BELIEVES_INVALID`（P08-B）。
- 明确的继续陈述（如“回来接着弄”）按第 2 条判 `BELIEVES_VALID`，即使人物没有接触取消通知；单纯的 `return_to_task` 不构成信念证据。2026-10-24 据此把 14 条 `contact_cancellation` B 臂从 `UNKNOWN` 升为 `BELIEVES_VALID`（证据 e06，P0 v0.4）；`P01-B` 只有返回动作，维持 `UNKNOWN`。

### 2.6 `C`：原目标承诺

**判定顺序：**

1. 有明确完成陈述/完成动作且人物知道 → `COMPLETED`。
2. 有明确放弃陈述或等价决定 → `ABANDONED`。
3. 正在推进，或刚被中断但仍表达继续意图 → `ACTIVE` / `SUSPENDED`。
4. 没有证据 → `UNKNOWN`。

**时序优先规则（2026-10-24 仲裁）：** 显式放弃陈述优先于其后的一般性 `step_started`/`step_attempted`；后者不自动构成重新承诺。只有新的 `commitment_expressed` 或明确的继续陈述才重新打开目标。P02 的 14 条 B 臂据此维持 `C=ABANDONED`、`not_resume`。

**`ACTIVE` 与 `SUSPENDED`：**

- `ACTIVE`：截至 `t` 仍在推进原目标，没有被中断/搁置。
- `SUSPENDED`：原目标被中断或主动搁置，但人物仍意图继续。
- 在跨中断任务中，截断点通常落在 `SUSPENDED`；但 P01-A 的 `ABANDONED`、P04-A 的 `COMPLETED` 也合法。

**注意：**

- `C=SUSPENDED` 不说明 `H` 内一定恢复。P05-B 中 `C=SUSPENDED` 但 `F=BLOCKED`，脚本预期等待。
- “暂时没行动”不等于 `ABANDONED`；必须有明确放弃证据。
- `C=COMPLETED` 是人物认为完成；`V=FULFILLED` 是客观完成。P04-A 二者一致，P04-B 二者分离。

### 2.7 `Q`：主观恢复步骤

`Q` 是人物认为的“下一个尚未完成的原目标步骤”，不是客观最优步骤，也不是未来实际恢复步骤。

**判定顺序：**

1. 人物知道哪些步骤已完成？
2. 按任务依赖，人物认为的第一个未完成步骤是什么？
3. 如果人物认为原目标已无必要（`C=ABANDONED/COMPLETED`）→ `NOT_APPLICABLE`。
4. 如果无法判断人物掌握的进度 → `UNKNOWN`。

**注意：**

- `Q` 可以指向客观上已完成的步骤。P04-B 中 `fill_form` 客观已完成，但人物不知道，`Q=fill_form`，这是合法的“主观进度滞后”。
- `Q` 不等于 T2 的未来实际恢复步骤 `Q*`。T2 是评价标签，不能从 `Q` 直接复制。
- P06-B 的 `Q=analyze_data` 指**原目标**的恢复步骤；嵌套任务 `fix_printer` 的下一步是 `replace_toner`，记录在 `interrupting_task` 中，不写进 `Q`。
- `Q=NOT_APPLICABLE` 需要证据（例如人物确认取消/完成）；不能因为“不知道下一步”就填 `NOT_APPLICABLE`，那应填 `UNKNOWN`。

---

### 2.8 `U`：事件级理解（v0.2 新增）

`U` 不是记录级第七个互斥标签，而是**逐事件**填在 `person_comprehension` 上，专门承载“接触之后有没有读懂”。

| 取值 | 含义 | 使用条件 |
|---|---|---|
| `UNDERSTOOD` | 有证据表明人物正确理解了消息内容 | `person_access=ACCESSED`，且有人物复述/正确行动等证据 |
| `MISUNDERSTOOD` | 接触到了，但理解偏离（如把取消读成暂缓） | `ACCESSED`，且 `person_available_semantics.interpretation` 为 `defer/complete/unresolved` |
| `NOT_UNDERSTOOD` | 接触但未形成理解（未读完、看不懂） | `ACCESSED`，无理解证据 |
| `UNCERTAIN` | 理解状态不确定 | `ACCESSED` |
| `NOT_APPLICABLE` | 该事件不含消息内容，或人物未接触 | `person_access != ACCESSED`，或事件本身无信息内容 |

配套字段 `person_available_semantics` 记录**人物可能获得的语义**（`kind`/`value`/`interpretation`），与世界真值分开：世界侧仍由 `world_effect` 与事件类型表达。

**三方对应关系（合并时按此映射，不各写一套）：**

| 本项目 | A 适配器 | C 评测协议 |
|---|---|---|
| `event.person_comprehension` | `delivery.comprehension`（当前占位 `not_structurally_labeled`） | `person_access_evidence.understood`（true/false/null） |
| `event.person_available_semantics` | 待接入人物侧编码 | `semantic.kind` / `semantic.value` / `interpretation` |

**硬约束：** `person_access != ACCESSED` 时 `person_comprehension` 必须是 `NOT_APPLICABLE`；`MISUNDERSTOOD` 必须配非 `accurate` 的 `interpretation`。两条都由 `validate_data.py` 强制。

## 3. 六条硬性标注约束

1. **客观与主观分离：** `V=CANCELLED` 不推出 `B=BELIEVES_INVALID`。P01 是强制反例。
2. **接触与理解分离：** `A=ACCESSED` 不自动推出人物正确理解通知；需要额外证据。P08 是强制反例。
3. **有效与可执行分离：** `V=VALID, F=BLOCKED` 完全合法。P05-B 是强制正例。
4. **状态与行为分离：** `C=SUSPENDED` 不说明未来 `H` 内一定恢复。P05-B 是强制反例。
5. **未知与删失分离：** `UNKNOWN` 是当前证据不足；`censored` 是实际后续行为观察不足。两者不能互换。
6. **证据链强制保存：** 每个非 `UNKNOWN` 标签必须对应一个或多个 `evidence_event_ids`；不允许用 `t` 之后的结果反推 `t` 时刻的人物信念。

---

## 4. 事件字段与词表

### 4.1 事件字段

每条事件必须包含以下字段（`schema/p0_record.schema.json` 已强制）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | string | 记录内唯一，格式 `e01`…`e999` |
| `time` | `HH:MM` | P0 本地时间；P1 后续扩展 ISO 8601 |
| `actor` | enum | `person / colleague / customer / manager / system / environment / other` |
| `event_type` | enum | 见 4.2 词表 |
| `goal_id` | string/null | 事件影响的 goal；嵌套任务事件可填嵌套 goal |
| `step_id` | string/null | 关联任务步骤；非步骤事件填 null |
| `person_access` | enum | 该事件对人物的投递/接收：`ACCESSED / NOT_ACCESSED / UNCERTAIN` |
| `person_comprehension` | enum | v0.2 事件级理解：`UNDERSTOOD / MISUNDERSTOOD / NOT_UNDERSTOOD / UNCERTAIN / NOT_APPLICABLE`，规则见 2.8 |
| `person_available_semantics` | object | v0.2 人物可获得的语义：`kind`（cancellation / completion_by_other / resource_* / commitment / abandonment / interruption / nested_task_state / none）、`value`、`interpretation`（none / accurate / defer / complete / unresolved） |
| `world_effect` | string/null | 客观世界/任务状态变化，自由文本但需可核验 |
| `observer_evidence` | string/null | 观察者凭什么知道该事件 |
| `person_access_evidence` | string/null | 人物凭什么接触/未接触该事件 |
| `source` | enum | `direct_observation / person_report / third_party_report / notification / backend_record / sensor_log / inference / other` |
| `certainty` | enum | `CERTAIN / PROBABLE / UNCERTAIN` |
| `description` | string | 人类可读描述 |

### 4.2 合法事件类型（v0.1）

| 事件类型 | 用途 |
|---|---|
| `goal_start` | 目标开始/被激活 |
| `goal_abandoned` | 人物明确放弃目标 |
| `step_started` | 开始某一步 |
| `step_completed` | 完成某一步 |
| `step_attempted` | 尝试但未完成；`world_effect` 必须说明未完成 |
| `interruption_started` | 中断开始 |
| `interruption_ended` | 中断结束 |
| `return_to_task` | 人物回到任务点 |
| `person_action` | 其他人物的可观察动作（坐下、打开电脑等） |
| `person_statement` | 人物自述/解释；是 `B/C` 的重要证据 |
| `commitment_expressed` | 人物明确表达继续承诺 |
| `task_cancelled` | 客观任务被取消（后台/客户/系统） |
| `task_completed_by_other` | 他人代完成主任务 |
| `notification_sent` | 通知投递；`person_access` 区分是否到达人物 |
| `resource_available` | 工具/资源可用 |
| `resource_missing` | 工具/资源缺失 |

**扩展规则：** v0.1 不接受未登记的事件类型。新增类型必须先更新 Schema、本手册和校验器，再进入数据。不要用 `person_action` 偷懒承载所有语义；关键区别（接触、取消、完成、资源）必须用专门类型或明确字段表达。

### 4.3 `person_access` 的语义

- `ACCESSED`：该事件被投递到人物可接触通道，且有接收证据（看到、听到、操作、确认）。
- `NOT_ACCESSED`：有证据表明未投递，或人物没有接收到。
- `UNCERTAIN`：投递/接收不确定。

人物自己执行/陈述的事件，`person_access=ACCESSED`（人物知道自己的动作/陈述）。后台事件不能因为“数据库里有”就写成 `ACCESSED`。

---

## 5. 证据链规则

1. **逐因子证据：** `state_evidence_by_factor` 必须为 `V/F/A/B/C/Q` 各给一个事件 ID 数组。
2. **非未知必须有证据：** 除 `UNKNOWN` 外，每个标签至少一个证据事件。
3. **`UNKNOWN` 不携带正证据：** `B=UNKNOWN` 时 `B` 的证据数组应为空；如果有证据表明人物处于冲突，应标 `UNRESOLVED`，不是 `UNKNOWN`。
4. **`NOT_APPLICABLE` 需要证据：** P01-A 的 `Q=NOT_APPLICABLE` 由“人物确认取消”的 e06 支持；不能无证据填。
5. **平铺证据字段：** `state_evidence_event_ids` 是所有逐因子证据的去重并按事件顺序排列的并集；校验器会检查它是否一致。
6. **时间边界：** 所有证据事件必须 `<= cutoff`，且必须是 `observed_events` 中的事件。
7. **未来泄漏：** 禁止用 `t` 之后的事件支持 `t` 时刻标签。P07 是专门检查这一点的负对照。

---

## 6. P0 脚本策略与受控机制

### 6.1 脚本策略词表

| 策略 | 含义 |
|---|---|
| `continue_if_no_known_cancellation` | 若人物不知道取消，则继续原任务 |
| `resume_if_committed_and_unfinished` | 若人物仍承诺且任务未完成，则恢复 |
| `resume_at_first_incomplete_known_step` | 从人物已知的第一个未完成步骤恢复 |
| `avoid_repeat_if_known_completed` | 若人物知道已完成，则避免重复 |
| `execute_if_ready_else_wait` | 条件允许则执行，否则保持目标并等待 |
| `finish_nested_task_before_parent` | 先完成未完成的嵌套任务，再回父目标 |
| `act_on_believed_status` | 按人物主观理解的状态行动 |

脚本策略是 P0 的“人物规则”，不是真实人类行为定律。P0 的 `p0_expected_action` 必须与策略一致。

### 6.2 八个受控机制

v0.2 把八组对照升级为八个 `mechanism`，每个家族都要声明自己属于哪一个。

| mechanism | 唯一变化 | 关键检验 | A 预期 | B 预期 |
|---|---|---|---|---|
| `contact_cancellation`（P01） | 人物是否接触取消通知 | 客观事实 ≠ 人物信念 | 已知取消，不恢复 | 未接触，继续推进 |
| `long_term_commitment`（P02） | 早前“继续”还是“放弃” | 长期承诺 vs 滑窗 | 恢复 | 不恢复 |
| `resume_position`（P03） | 中断前关键步骤是否完成且人物知情 | 主观未完成步骤 | 从下一步恢复 | 从该步恢复 |
| `other_completion`（P04） | 人物是否获知他人已完成 | 完成事实与信念分离 | 不重复 | 可能重复（不计恢复） |
| `resource_availability`（P05） | 必要条件可用或缺失（人物均知情） | 承诺 ≠ 可执行性 | 执行 | 等待条件 |
| `nested_interruption`（P06） | 嵌套任务在截断时是否完成 | 目标层级与恢复顺序 | 回父目标 | 先完成嵌套任务 |
| `future_leak`（P07） | 截断前输入相同，仅截断后设计结果不同 | 不可预知未来 | 无点标签（`indeterminate`） | 同左，分布必须相同 |
| `comprehension`（P08） | 都接触到取消信息，一个理解、一个误读 | 接触 ≠ 理解 | 停止 | 暂停/等待 |

### 6.3 v0.2 批次结构（120 家族 / 240 条）

| 维度 | 取值 |
|---|---|
| 规模 | 15 个任务骨架 × 8 个机制 = 120 个 `base_story_id`，每个家族 A/B 两条，共 240 条、1831 个事件 |
| 领域 | 5 个 work / 5 个 collaboration_service / 5 个 daily_life 骨架，按机制轮换使用，家族级覆盖接近均衡（约 38–42 个/域） |
| 划分 | 按**任务骨架**分层（同一骨架不跨 split）：每个机制 9 train / 3 dev / 3 test，共 72 / 24 / 24；同族 A/B 必在同一 split |
| 种子 | P01–P08 为手写种子，保留在 v0.2 中并补齐新字段；其余 112 个家族由 `scripts/build_p0_v02.py` 按骨架 + 机制生成 |
| 生成边界 | 家族之间任务、实体、编号独立；**句式按机制模板复用**，表达多样性有限，属已知限制，不能当作自然语言多样性证据 |

**P0 数据的正确用法：** 只用于管道、泄漏、对照逻辑和状态一致性诊断；不能把 P0 的 `p0_expected_action` 当作真实人类恢复标签，也不能用 P0 结果宣称真实预测能力。

---

## 7. 常见易错示例

| 易错写法 | 正确写法 | 原因 |
|---|---|---|
| `V=CANCELLED` 所以 `B=BELIEVES_INVALID` | P01-B：`V=CANCELLED, B=UNKNOWN` | 客观事实不等于人物知道 |
| `A=ACCESSED` 所以 `B=BELIEVES_INVALID` | P08-B：`A=ACCESSED, B=BELIEVES_VALID, C=SUSPENDED` | 接触不等于正确理解 |
| `V=VALID` 所以 `F=READY` | P05-B：`V=VALID, F=BLOCKED` | 有效不等于可执行 |
| `C=SUSPENDED` 所以 `H` 内会恢复 | P05-B：`C=SUSPENDED` 但预期等待 | 承诺状态不等于行为 |
| `V=FULFILLED` 所以 `C=COMPLETED` | P04-B：`V=FULFILLED, C=SUSPENDED` | 客观完成不等于人物知道 |
| `Q` 填客观最优下一步 | P04-B：`Q=fill_form`（客观已完成） | `Q` 是主观进度，允许滞后 |
| 把 `UNKNOWN` 当 `censored` | 未知用 `UNKNOWN`，删失用 `p1_censoring_status` | 两者语义不同 |
| `A=NOT_ACCESSED` 所以 `B=UNKNOWN` | 若有间接线索，`B` 仍可更新 | 未接触直接通知不等于没有推断渠道 |
| `C=ABANDONED` 所以 `B=BELIEVES_INVALID` | P02-B：`B=BELIEVES_VALID, C=ABANDONED` | 放弃是承诺决定，不等于认为目标无效 |
| 人物说“暂缓”就标 `V=CANCELLED` | P08-B：`V=CANCELLED, B=BELIEVES_VALID` | 人物措辞不是客观任务状态 |
| `Q=NOT_APPLICABLE` 当成“不知道” | 不知道填 `Q=UNKNOWN` | `NOT_APPLICABLE` 表示恢复步骤不适用，需要证据 |

---

## 8. P1 真实数据标注流程（后续执行）

1. **冻结截断点：** 先确定 `t`，导出 `observed_events`，删除 `t` 之后的全部事件；`cutoff_event_id` 必须是最后一条。
2. **双人独立标注：** 至少两名标注者独立标 `V/F/A` 和可观察步骤；`B/C/Q` 只有在有自述、明确行动或可核查间接证据时才标，否则 `UNKNOWN`。
3. **先客观后主观：** 先确定 `V/F`，再根据人物可接触证据确定 `A`，最后标 `B/C/Q`。禁止从 `V` 直接复制 `B`。
4. **证据逐条记录：** 每个非未知标签写证据事件 ID；证据不足写 `UNKNOWN`，不要用“常识”补。
5. **一致性统计：** 报告每个因子的标注者一致性（如 Cohen's kappa）、分歧、仲裁结果和手册版本。
6. **删失处理：** 未来窗口未完整观察且未出现恢复事件 → `right_censored`，不能记为 `not_resume`；恢复行为由独立证据确认。
7. **P1 行为标签：** `p1_observed_resume` 只在完整观察窗口且有独立行为证据时填布尔值；`p1_observed_first_step` 只在确已恢复且步骤可辨认时填。
8. **隐私与许可：** 只使用经许可的数据；去除可识别信息；记录数据来源和使用边界。

---

## 9. 单条记录标注决策顺序（SOP）

1. 确认 `base_story_id`、`variant`、`goal_id`、`cutoff_event_id`。
2. 检查事件时间有序、cutoff 是最后一条、无未来事件。
3. 标 `V`：只找客观任务证据。
4. 标 `F`：只找工具/资源/权限/依赖证据。
5. 标 `A`：围绕“关键事件”找投递与接收证据。
6. 标 `B`：只用人物可获得的证据；区分 `UNRESOLVED` 与 `UNKNOWN`。
7. 标 `C`：找承诺/放弃/完成证据；不要从行为缺席推断放弃。
8. 标 `Q`：按人物已知进度和任务依赖；允许与客观进度不一致。
9. 填 `state_evidence_by_factor`，再生成平铺证据并集。
10. 填 `p0_expected_*` 或 P1 行为标签。
11. 运行 `python scripts/validate_data.py`（P0）或等价校验（P1）；逐对审计使用 `python scripts/pair_diff_report.py`。
12. 另一名标注者复核；分歧进入仲裁并记录。

---

## 10. 交付前质检清单

- [ ] `cutoff_event_id` 是 `observed_events` 最后一条，且没有截断后事件。
- [ ] 每个非 `UNKNOWN` 标签都有证据；`UNKNOWN` 没有正证据。
- [ ] `state_evidence_event_ids` 等于逐因子证据的按序并集。
- [ ] `Q` 是任务图中的步骤，或 `UNKNOWN/NOT_APPLICABLE`。
- [ ] `completed_steps_at_cutoff` 是 `task_steps` 的子集。
- [ ] `p0_expected_action` 与 `p0_expected.first_step` 一致。
- [ ] A/B 对的差异只有设计规定的那一个变量，并在 `notes` 中写明。
- [ ] P07-A/B 的截断前输入完全一致。
- [ ] P0 的 `p1_observed_resume=null`、`p1_censoring_status=not_collected`。
- [ ] JSON 通过 Schema 和跨字段校验（`python scripts/validate_data.py`）。
- [ ] v0.2 专属：`split` 为家族级、每机制 9/3/3；`person_comprehension` 与 `person_access` 一致；P07 家族 `undefined_target=true` 且 `action=indeterminate`。
- [ ] `annotation.status` 从 `draft` 改为 `reviewed`（B 复核完成）；盲审与仲裁后才可 `adjudicated`。
- [ ] 抽查包已逐对人工打勾（`python scripts/audit_packet.py --seed <固定值>` 生成）。签核表入库时必须全空，勾由人打；没打勾就写 `reviewed` 等于伪造复核。

> 具体的质量门、P1 双人标注一致性指标、噪声上限和给 A 的质量报告模板见 [`label_quality_plan_v0.1.md`](label_quality_plan_v0.1.md)。

---

## 11. 版本、待定问题与变更记录

### 11.1 待定问题（v0.1）

1. **`F` 缺少 `NOT_APPLICABLE`：** 目标已 `FULFILLED/CANCELLED` 时，`F` 的语义不自然。当前约定：有明确资源证据可标 `READY/BLOCKED`，否则 `UNKNOWN`。
2. **时间格式：** P0 用本地 `HH:MM`，不含日期；P1 需要 ISO 8601 和时区，Schema v0.2 再扩展。
3. **`Q` 与嵌套任务：** `Q` 只描述原目标；嵌套任务的进度放 `interrupting_task`。P06-B 的 `p0_expected_action` 指向嵌套任务，但 `p0_expected.resume_within_horizon=false` 指原目标，这是有意区分。
4. **P07 的 `notes`：** 含截断后设计结果，仅用于泄漏对照说明；任何模型输入管道必须排除 `notes`。
5. **`p0_expected` 是 v0.1 新增结构：** 文档 4.2 只有字符串 `p0_expected_action`；为支持 T1/T2 监督，v0.1 增加 `resume_within_horizon` 和 `first_step`。需 A 确认接口。
6. **`task_dependencies` 与 `completed_steps_at_cutoff` 是 v0.1 新增字段：** 用于任务图和客观进度；需 A 确认是否按其实现。
7. ~~样本规模不足~~ → **已解决（v0.2）**：120 家族 / 240 条，按 `base_story_id` 分层 72/24/24，同族 A/B 不跨 split。
8. **领域覆盖：** v0.2 已按 5+5+5 个骨架覆盖三领域，家族级每域约 38–42 个；`daily_life` 不再只有一对。
9. ~~缺结构化“理解”字段~~ → **已解决（v0.2）**：新增事件级 `person_comprehension` 与 `person_available_semantics`，见 §2.8；A 需在适配器接入，C 需把 `understood` 映射过来。
10. ~~P04-B 的 T1 口径冲突~~ → **已按研究方案 §3.4 处理（v0.2）**：凡步骤已客观完成的重复动作不计 T1/T2，`resume_within_horizon=false, first_step=null`，主观滞后只体现在 `Q`。该决定已写入 8 个 `other_completion` 机制家族；若 A 另行定口径，需同时改 15 个家族并升版本。
11. **字段名冲突（未解决）：** B 的 `person_access_evidence` 是自由文本，C 的同名字段是 `{status, understood}` 对象。三方合并前必须改名或改类型；建议 C 改名为 `person_access_note`，或在映射层做显式转换。
12. **A 适配器当前只认 `p0-record/v0.1.0`：** 传入 v0.2 会显式报 `UNSUPPORTED_SCHEMA_VERSION`（这是期望行为，不是缺陷）。A 需新增版本分支后，B 才能把 v0.2 作为正式训练输入交付。
13. **11 个不确定性档位已覆盖并验收：** v0.2 的 240 条里 `A=UNCERTAIN`、`V/F=UNKNOWN`、`B=UNRESOLVED`、`C∈{ACTIVE,UNKNOWN}`、事件级 `person_access=UNCERTAIN`、`person_comprehension∈{NOT_UNDERSTOOD,UNCERTAIN}`、`certainty∈{PROBABLE,UNCERTAIN}` 一次都没出现。`data/p0/p0_samples_v0.3.json`（7 家族 / 14 条）按 §1.4 判据各覆盖至少一次，B 已于 2026-10-21 逐对复核并升 `reviewed`，可以交 A/C 盲审。`split.calibration` 仍为空，要 C 先定校准协议。
14. **`contact_cancellation` B 臂的 `B=UNKNOWN` 与 §2.5 冲突（2026-10-21 盲审提出，2026-10-24 已解决）：** 14 条 B 臂按 §2.5 第 2 条升 `BELIEVES_VALID` 并补证据 `e06`，发布为 P0 v0.4；`P01-B`（仅返回动作）与 3 条取消后无事件的记录维持 `UNKNOWN`。以下为原始记录： §2.5 判定顺序第 1 条允许"明确行动"、第 2 条把"仍然有效/继续"的表达判为 `BELIEVES_VALID`，而实测 19 条 `B=UNKNOWN` 里有 **16 条**（v0.2 的 P01-B + 14 个 `contact_cancellation` B 臂 + v0.1 的 P01-B）在取消事件之后仍存在人物陈述或 `return_to_task` 行动、却没有计入 `state_evidence_by_factor.B`。同批次 215 条 `BELIEVES_VALID` 正是拿 `step_started`/人物自述当 B 证据（P08-W1-B 甚至把 e03 与 e06 都计入），只有 P01 B 臂例外。另 3 条（v0.3 的 P01-W6-A/B、P08-S7-B）实测在关键事件之后人物再无任何事件，`UNKNOWN` 合法、不动。出路只有把这 16 条升为 `BELIEVES_VALID` 并补证据引用（改文案以保住 `UNKNOWN` 不可行：§2.6 第 3 步要求 `C=SUSPENDED` 必须有"仍表达继续意图"，删了会连带废掉 C 的证据）。**B 不单方面改：** 这动的是 A 在信念维的监督信号，且含 v0.1 冻结基线里的 1 条；§1.4/§2.4/§2.5 现在还把"P01-B 的 `B=UNKNOWN`"当正面例子讲，改标要同步改这三处。

### 11.2 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.1.0 | 2026-10-20 | 首版：六因子定义、事件词表、证据规则、P01–P08 对照、P0/P1 边界、16 条种子数据 |
| v1.0.0 | 2026-10-20 | 升版冻结：P0 v0.2（120 家族/240 条、`split`、八机制、事件级 `U` 与人物可获得语义）；P04 恢复口径按方案 §3.4 统一；P07 改为 `indeterminate`；B 复核完成（`reviewed`） |
| v1.0.1 | 2026-10-20 | 新增 §1.4「P0 里未知档位的合法性判据」，并把 §1.3 表格里"P0 脚本期望，可完全确定"改写为可判定口径。原写法与 §2.3（允许 `F=UNKNOWN`）以及数据里 15 条 `B=UNKNOWN` 直接冲突，A/C 按字面读会把合法的设计性未知当成违规。2026-10-21 追加：§1.4 末尾与 §11.1 第 13 条记录 v0.3 不确定性批次（14 条），当时为 `draft`、待 B 复核，次日签核通过（见 v1.0.2） |
| v1.0.2 | 2026-10-21 | v0.3 不确定性批次由 `draft` 升 `reviewed`：B 逐对复核 `p0_spot_audit_v0.3_all7.md`（7 对 / 28 框）与 v0.2 抽查 `p0_spot_audit_v0.2_seed20261021.md`（10 对 / 39 框），结论全部通过。签核表改为"已签"状态，`audit_packet.py` 增加拒绝覆盖已签表的闸；§1.4 判据第一次成批检验通过。A/C 盲审与 `split.calibration` 仍未做 |
| v1.0.3 | 2026-10-21 | 回应 A/C 盲审回条的实测结论：① v0.2 P01 B 臂「还剩两步」是错的（模板硬编码了 v0.1 的三步故事，套到 v0.2 的 4 步骨架上整体差 1；带步数的自述 14 条全错），改为与任务图一致的"三步"，并给 `validate_data.py` 加"人物自述步数必须等于客观剩余步数"的跨字段检查 + 正负例测试；② §2.3 补 P0 `READY` 的可判定口径，252 条 READY 零空证据、零被脚本内事件矛盾，属手册缺条款而非数据错；③ §11.1 新增第 14 条，把 16 条 `B=UNKNOWN` 的信念维缺口挂账待 A 表态。v0.2 字节因此变化，新 SHA256 见 `data/p0/README.md` |
| v1.0.4 | 2026-10-24 | 状态口径同步：P0 更新为 v0.3 发布版（254 条 / 127 家族 / 150-52-52，`reviewed` 未 `adjudicated`）；P1 因 2026-10-23 descope 改为公开数据派生包（2,863 条，真人记录 0），六变量只有 V 全量有效，F/A/B/C/Q 的规则映射值已按 `state_withdrawn` 撤回；P1 结论口径从"真实人类恢复预测"改为"公开数据派生辅助任务评测"。标注规则与判据条款未改 |
| v1.0.5 | 2026-10-24 | B 侧仲裁落地：① §11.1 第 14 条关闭——14 条 `contact_cancellation` B 臂按 §2.5 第 2 条升 `BELIEVES_VALID` 并补 `e06`，发布 P0 v0.4；`P01-B` 与 3 条无后续事件记录维持 `UNKNOWN`。② §2.6 增加时序优先规则——显式放弃优先于其后一般步骤动作，P02 的 14 条维持 `C=ABANDONED`。数据只改这 14 个 B 值，其余 240 条逐字节不变；v0.3 冻结 |

> **仓库迁移说明：** 本手册从 B 岗交付目录迁入主仓库时，仅更新校验/审计脚本路径并补充竞赛边界；16 条数据与标签未改。

---

## 12. 与 A 适配器的接口对齐（2026-10-20）

> 依据：A 分支 `origin/feat/a-ec-jmf-p0-adapter` 的 `docs/internal/a/A_INTERFACES.md`、`models/ecr_mwm/p0_adapter.py`、`tests/test_a_p0_contract.py`。A 已把本 schema 作为正式输入版本 `p0-record/v0.1.0` 接收（“B 继续拥有 schema/数据”）。本节记录“手册承诺”与“适配器实际行为”的差异，避免扩量时按错的边界造数据。

| 主题 | 手册原写法 | A 适配器实际行为 | B 的后续约定 |
|---|---|---|---|
| `completed_steps_at_cutoff` | §1.2 列为允许输入 | 不读该字段；在诊断侧用事件重放核对（`replay_completion_evidence`） | 扩量时保持“可由事件重放出来”，不允许出现重放不出的进度 |
| `interrupting_task.status_at_cutoff` | 列为允许输入 | 只取 `task_id`/`parent_goal_id`/`steps` 建观察者图，**不把嵌套状态快照写进心智** | 不要把嵌套状态当作模型可读信息来设计对照 |
| 外部消息内容 | `description`/`world_effect` 属观察者证据 | 人物侧只拿 `delivery.access_evidence` 与本人陈述；外部消息内容当前**不进入**人物输入，`comprehension` 恒为 `not_structurally_labeled` | v0.2 已提供 `person_comprehension` 与 `person_available_semantics`；A 需加版本分支接入，见 §11.1 第 12 条 |
| P06-B 的 T2 | `first_step=replace_toner` 属嵌套任务 | `scripted_targets` 判 `t2_mask=false`，T2 被遮蔽，只保留审计 | 与 §11.1 第 3 条一致；评测口径按“遮蔽”执行 |
| P1 `first_step` 键 | P0 记录不含该键 | A 区分“缺键”与“显式 null”，记 16/16 缺键 | 不要在 P0 里补 null 键，除非同时升 `schema_version` |
| 脚本目标读取位置 | 只说是“非输入” | 只在评测侧 `scripted_targets` 读 `p0_expected`，T2 要求 `first_step ∈ task_steps` | 改 `p0_expected` 语义时必须通知 A，否则 T2 掩码会静默变化 |

**对 B 的直接含义：** v0.1 的 P0 对照主要靠 `delivery.access_evidence`（A）与本人陈述区分，**“人物看到了什么内容”没有结构化通道**；P04-A（得知同事已完成）与 P08-A（正确理解取消）在人物侧只剩一个 `ACCESSED`。v0.2 已补 `person_comprehension` 与 `person_available_semantics` 两个字段承载该通道（见 §2.8），但 **A 的适配器仍只认 `p0-record/v0.1.0`**，需 A 加版本分支后才能消费；在此之前，v0.2 只作为数据侧交付，不代表 A 已能训练。

## 附录 A：P0 记录字段速查

```text
schema_version                     # v0.2 为 p0-record/v0.2.0
sample_id / base_story_id / variant
split / domain / mechanism         # v0.2：家族级划分与受控机制
goal_id / goal_description
cutoff_event_id / horizon
task_steps / task_dependencies / completed_steps_at_cutoff
observed_events[]                  # 模型输入
  └ person_access / person_comprehension / person_available_semantics
state_at_cutoff{V,F,A,B,C,Q}       # 状态标签
state_evidence_event_ids[]         # 平铺证据
state_evidence_by_factor{V..Q}     # 逐因子证据
p0_scripted_policy                 # 脚本策略
p0_expected_action                 # 下一步动作标签（含 indeterminate）
p0_expected{resume, first_step, undefined_reason, behavior_note}
p0_design{manipulated_factor, paired_variable, undefined_target, future_outcome}
p1_observed_resume / p1_observed_first_step / p1_censoring_status
interruption / interrupting_task   # 可选
annotation / notes                 # 审计，不可作输入（p0_design 同样不可作输入）
```

## 附录 B：标注时最该问的三个问题

1. **这是世界事实，还是人物知道的事实？**（`V/F` vs `B/A`）
2. **人物接触到了吗？接触后理解对了吗？**（`A` vs `B`）
3. **人物还想做吗？现在做得了吗？他知道做到哪了吗？**（`C`、`F`、`Q` 三者分开）
