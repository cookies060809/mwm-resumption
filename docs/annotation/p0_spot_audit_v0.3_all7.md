# P0 抽查包 · p0_samples_v0.3.json

> 生成：`python scripts/audit_packet.py --file data/p0/p0_samples_v0.3.json --records 14 --seed 20261021`。换一个 seed 就是换一批样本，签核表不要复用。
> **签核：B 于 2026-10-21 逐对复核本表 7 对，结论全部为「通过」，无「需改」项。** 勾选与结论行由 Qoder 按 B 的确认转录，转录前的空白版见 commit 15ce711；B 之外的第二双眼睛（A/C 盲审）是另一张表，本表不能替它代签。

- 数据 SHA256：`8dfba39ba7d0b3b2779e141038460c5abd7e2c77d804f8b8d94500849ef712e8`（签核时点；与空白版相比只有 `annotation` 块从 draft 升到 reviewed）
- 抽样：7 对 / 14 条，机制覆盖 4 种（仓库该批次共 7 对 / 14 条）
- 抽样规则：先按机制各取 1 对（机制名排序），不足再按 `sha256("20261021:家族名")` 排序补齐；与机器、Python 版本、运行次数都无关

### P08-W7  ·  comprehension  ·  dev

- 事件条数：A 6 / B 6；逐字段差异 5 处
- 状态变化因子：B、C、Q
- 差异字段：description、person_access_evidence、person_available_semantics、person_comprehension、step_id
- 期望动作：`do_not_resume` | `suspend_or_wait`（政策 `act_on_believed_status`）
  - P08-W7-A（A 臂）不确定档位：无；零证据因子：无
  - P08-W7-B（B 臂）不确定档位：e04.person_comprehension=NOT_UNDERSTOOD；零证据因子：无

- [x] 只改了一个设计变量，其余差异都是它的必然后果
- [x] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [x] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [x] 结论：通过 / 需改（写样本号与字段）：**通过**（B · 2026-10-21）

### P01-W6  ·  contact_cancellation  ·  train

- 事件条数：A 5 / B 5；逐字段差异 5 处
- 状态变化因子：A
- 差异字段：certainty、description、person_access、person_access_evidence、person_comprehension
- 期望动作：`resume_fill_expense_form` | `do_not_resume`（政策 `continue_if_no_known_cancellation`）
  - P01-W6-A（A 臂）不确定档位：A=UNCERTAIN、B=UNKNOWN、e05.person_access=UNCERTAIN、e05.certainty=UNCERTAIN；零证据因子：B
  - P01-W6-B（B 臂）不确定档位：B=UNKNOWN、e05.person_comprehension=UNCERTAIN；零证据因子：B

- [x] 只改了一个设计变量，其余差异都是它的必然后果
- [x] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [x] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [x] 结论：通过 / 需改（写样本号与字段）：**通过**（B · 2026-10-21）

### P02-D7  ·  long_term_commitment  ·  test

- 事件条数：A 7 / B 5；逐字段差异 6 处
- 状态变化因子：C
- 差异字段：description、event_type、observer_evidence、step_id
- 期望动作：`resume_assemble_frame` | `do_not_resume`（政策 `resume_if_committed_and_unfinished`）
  - P02-D7-A（A 臂）不确定档位：无；零证据因子：无
  - P02-D7-B（B 臂）不确定档位：C=UNKNOWN；零证据因子：C

- [x] 只改了一个设计变量，其余差异都是它的必然后果
- [x] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [x] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [x] 结论：通过 / 需改（写样本号与字段）：**通过**（B · 2026-10-21）

### P05-D6  ·  resource_availability  ·  train

- 事件条数：A 5 / B 6；逐字段差异 1 处
- 状态变化因子：F
- 差异字段：无
- 期望动作：`wait_for_tool` | `wait_for_tool`（政策 `execute_if_ready_else_wait`）
  - P05-D6-A（A 臂）不确定档位：F=UNKNOWN；零证据因子：F
  - P05-D6-B（B 臂）不确定档位：无；零证据因子：无

- [x] 只改了一个设计变量，其余差异都是它的必然后果
- [x] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [x] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [x] 结论：通过 / 需改（写样本号与字段）：**通过**（B · 2026-10-21）

### P08-S7  ·  comprehension  ·  dev

- 事件条数：A 6 / B 5；逐字段差异 5 处
- 状态变化因子：B、C、Q
- 差异字段：observer_evidence、person_access_evidence、person_available_semantics、person_comprehension
- 期望动作：`do_not_resume` | `suspend_or_wait`（政策 `act_on_believed_status`）
  - P08-S7-A（A 臂）不确定档位：无；零证据因子：无
  - P08-S7-B（B 臂）不确定档位：B=UNKNOWN、e05.person_comprehension=UNCERTAIN；零证据因子：B

- [x] 只改了一个设计变量，其余差异都是它的必然后果
- [x] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [x] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [x] 结论：通过 / 需改（写样本号与字段）：**通过**（B · 2026-10-21）

### P01-W8  ·  contact_cancellation  ·  test

- 事件条数：A 5 / B 5；逐字段差异 12 处
- 状态变化因子：V
- 差异字段：actor、certainty、description、event_type、goal_id、observer_evidence、person_access_evidence、person_available_semantics、person_comprehension、source、world_effect
- 期望动作：`resume_build_summary` | `do_not_resume`（政策 `continue_if_no_known_cancellation`）
  - P01-W8-A（A 臂）不确定档位：V=UNKNOWN、e04.person_comprehension=UNCERTAIN、e04.certainty=UNCERTAIN；零证据因子：V
  - P01-W8-B（B 臂）不确定档位：e04.person_comprehension=MISUNDERSTOOD；零证据因子：无

- [x] 只改了一个设计变量，其余差异都是它的必然后果
- [x] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [x] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [x] 结论：通过 / 需改（写样本号与字段）：**通过**（B · 2026-10-21）

### P01-S6  ·  contact_cancellation  ·  train

- 事件条数：A 6 / B 5；逐字段差异 12 处
- 状态变化因子：B
- 差异字段：actor、certainty、description、event_type、person_access_evidence、person_available_semantics、person_comprehension、source、step_id、time、world_effect
- 期望动作：`do_not_resume` | `do_not_resume`（政策 `continue_if_no_known_cancellation`）
  - P01-S6-A（A 臂）不确定档位：B=UNRESOLVED、e05.person_comprehension=UNCERTAIN、e05.certainty=PROBABLE；零证据因子：无
  - P01-S6-B（B 臂）不确定档位：无；零证据因子：无

- [x] 只改了一个设计变量，其余差异都是它的必然后果
- [x] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [x] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [x] 结论：通过 / 需改（写样本号与字段）：**通过**（B · 2026-10-21）

