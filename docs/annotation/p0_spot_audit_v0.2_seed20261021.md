# P0 抽查包 · p0_samples_v0.2.json

> 生成：`python scripts/audit_packet.py --file data/p0/p0_samples_v0.2.json --records 20 --seed 20261021`。换一个 seed 就是换一批样本，签核表不要复用。
> **本文件不含任何结论。** 每个复选框都必须由人手工打勾；B 之外的第二双眼睛（A/C 盲审）是另一张表，不能靠这里代签。

- 数据 SHA256：`fb58cf749086bab8d08a3074f97ce1cea8f6fd52b1ec844d3682b1c3e12f29ee`
- 抽样：10 对 / 20 条，机制覆盖 8 种（仓库该批次共 120 对 / 240 条）
- 抽样规则：先按机制各取 1 对（机制名排序），不足再随机补齐；`random.Random(20261021)`，与机器和运行次数无关

### P08-S4  ·  comprehension  ·  train

- 事件条数：A 8 / B 8；逐字段差异 4 处
- 状态变化因子：B、C、Q
- 差异字段：description、person_available_semantics、person_comprehension
- 期望动作：`do_not_resume` | `suspend_or_wait`（政策 `act_on_believed_status`）
  - P08-S4-A（A 臂）不确定档位：无；零证据因子：无
  - P08-S4-B（B 臂）不确定档位：e05.person_comprehension=MISUNDERSTOOD；零证据因子：无

- [ ] 只改了一个设计变量，其余差异都是它的必然后果
- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P01-S1  ·  contact_cancellation  ·  test

- 事件条数：A 8 / B 8；逐字段差异 7 处
- 状态变化因子：A、B、C、Q
- 差异字段：description、person_access、person_access_evidence、person_available_semantics、person_comprehension、source
- 期望动作：`do_not_resume` | `resume_check_policy`（政策 `continue_if_no_known_cancellation`）
  - P01-S1-A（A 臂）不确定档位：无；零证据因子：无
  - P01-S1-B（B 臂）不确定档位：B=UNKNOWN；零证据因子：B

- [ ] 只改了一个设计变量，其余差异都是它的必然后果
- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P07-S5  ·  future_leak  ·  dev

- 事件条数：A 6 / B 6；逐字段差异 0 处
- 状态变化因子：无（同输入对照）
- 差异字段：无
- 期望动作：`indeterminate` | `indeterminate`（政策 `resume_if_committed_and_unfinished`）
  - P07-S5-A（A 臂）不确定档位：无；零证据因子：无
  - P07-S5-B（B 臂）不确定档位：无；零证据因子：无

- 机器预检：截断前输入一致性 PASS
- [ ] 期望标签确实是 `indeterminate`，没有偷偷藏一个可判别的点标签
- [ ] 截断后的设计结果只写在 `p0_design.future_outcome`，没有混进 `observed_events`
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P02-W4  ·  long_term_commitment  ·  dev

- 事件条数：A 7 / B 7；逐字段差异 3 处
- 状态变化因子：C、Q
- 差异字段：description、event_type、person_available_semantics
- 期望动作：`resume_scan_copy` | `do_not_resume`（政策 `resume_if_committed_and_unfinished`）
  - P02-W4-A（A 臂）不确定档位：无；零证据因子：无
  - P02-W4-B（B 臂）不确定档位：无；零证据因子：无

- [ ] 只改了一个设计变量，其余差异都是它的必然后果
- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P06  ·  nested_interruption  ·  train

- 事件条数：A 11 / B 10；逐字段差异 4 处
- 状态变化因子：无（同输入对照）
- 差异字段：actor、description、event_id、event_type、goal_id、observer_evidence、person_access_evidence、person_available_semantics、step_id、time、world_effect
- 期望动作：`resume_analyze_data` | `resume_replace_toner`（政策 `finish_nested_task_before_parent`）
  - P06-A（A 臂）不确定档位：无；零证据因子：无
  - P06-B（B 臂）不确定档位：无；零证据因子：无

- [ ] 只改了一个设计变量，其余差异都是它的必然后果
- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P04-S1  ·  other_completion  ·  test

- 事件条数：A 8 / B 8；逐字段差异 8 处
- 状态变化因子：A、C、Q
- 差异字段：description、observer_evidence、person_access、person_access_evidence、person_available_semantics、person_comprehension、source
- 期望动作：`do_not_resume` | `do_not_resume`（政策 `avoid_repeat_if_known_completed`）
  - P04-S1-A（A 臂）不确定档位：无；零证据因子：无
  - P04-S1-B（B 臂）不确定档位：无；零证据因子：无

- [ ] 只改了一个设计变量，其余差异都是它的必然后果
- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P05-S1  ·  resource_availability  ·  test

- 事件条数：A 7 / B 7；逐字段差异 4 处
- 状态变化因子：F
- 差异字段：description、event_type、person_available_semantics、world_effect
- 期望动作：`resume_check_policy` | `wait_for_tool`（政策 `execute_if_ready_else_wait`）
  - P05-S1-A（A 臂）不确定档位：无；零证据因子：无
  - P05-S1-B（B 臂）不确定档位：无；零证据因子：无

- [ ] 只改了一个设计变量，其余差异都是它的必然后果
- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P03-D5  ·  resume_position  ·  train

- 事件条数：A 7 / B 7；逐字段差异 5 处
- 状态变化因子：Q
- 差异字段：description、event_type、observer_evidence、person_access_evidence、world_effect
- 期望动作：`resume_label_boxes` | `resume_pack_boxes`（政策 `resume_at_first_incomplete_known_step`）
  - P03-D5-A（A 臂）不确定档位：无；零证据因子：无
  - P03-D5-B（B 臂）不确定档位：无；零证据因子：无

- [ ] 只改了一个设计变量，其余差异都是它的必然后果
- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P07-W2  ·  future_leak  ·  train

- 事件条数：A 6 / B 6；逐字段差异 0 处
- 状态变化因子：无（同输入对照）
- 差异字段：无
- 期望动作：`indeterminate` | `indeterminate`（政策 `resume_if_committed_and_unfinished`）
  - P07-W2-A（A 臂）不确定档位：无；零证据因子：无
  - P07-W2-B（B 臂）不确定档位：无；零证据因子：无

- 机器预检：截断前输入一致性 PASS
- [ ] 期望标签确实是 `indeterminate`，没有偷偷藏一个可判别的点标签
- [ ] 截断后的设计结果只写在 `p0_design.future_outcome`，没有混进 `observed_events`
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

### P06-S5  ·  nested_interruption  ·  dev

- 事件条数：A 10 / B 10；逐字段差异 11 处
- 状态变化因子：无（同输入对照）
- 差异字段：description、event_type、observer_evidence、person_access_evidence、person_available_semantics、source、step_id、world_effect
- 期望动作：`resume_check_parts` | `resume_replace_part`（政策 `finish_nested_task_before_parent`）
  - P06-S5-A（A 臂）不确定档位：无；零证据因子：无
  - P06-S5-B（B 臂）不确定档位：无；零证据因子：无

- [ ] 只改了一个设计变量，其余差异都是它的必然后果
- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）
- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）
- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿

