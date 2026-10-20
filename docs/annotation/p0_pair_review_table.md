# P0 八组对照：一页纸人工复核表

> **批次说明（2026-10-20）：** 本表以 8 个手写种子（P01–P08）为例讲读法。v0.2 已把同一套机制扩到 120 个家族 / 240 条，逐对机器预检用 `python scripts/pair_diff_report.py` 全量跑（当前 120/120 通过、15 个 P07 家族输入一致）。下表结论对同机制的所有家族同样适用。

**用途：** 你不需要读完整的 `scripts/pair_diff_report.py` 输出。每对只看三件事：

1. **events**：故事里到底改了什么？
2. **state**：六个状态标签里，哪些跟着变了？
3. **expected**：人物的下一步动作变了吗？

如果“事件差异 → 状态差异 → 动作差异”能一条线解释通，这一对就通过；如果出现设计之外的字段变化，才需要改数据。

---

## 1. 八组总表

| Pair | 唯一/主要差异 | A 版关键状态 | B 版关键状态 | A 预期 | B 预期 | 你要检查什么 |
|---|---|---|---|---|---|---|
| P01 取消认知 | 取消通知是否到达人物（e06） | `A=ACCESSED`，`B=BELIEVES_INVALID`，`C=ABANDONED` | `A=NOT_ACCESSED`，`B=UNKNOWN`，`C=SUSPENDED` | 不恢复 | 继续包装 | `V/F` 必须相同；只有“接触”变 |
| P02 旧目标承诺 | 早前说“继续”还是“放弃”（e03）；最后 5 个事件相同 | `C=SUSPENDED`，`Q=draft_section_3` | `C=ABANDONED`，`Q=NOT_APPLICABLE` | 恢复 | 不恢复 | e04–e08 必须完全相同 |
| P03 恢复位置 | 中断前运单是否已打印（e04） | `Q=handoff_courier` | `Q=print_label` | 从交接恢复 | 从打印恢复 | `F=READY` 两版都成立；B 不是打印机坏了 |
| P04 他人代完成 | 人物是否被告知同事已完成（e05） | `A=ACCESSED`，`C=COMPLETED` | `A=NOT_ACCESSED`，`C=SUSPENDED` | 不重复 | 可能重复 | `V=FULFILLED` 两版相同；只有“知道/不知道”变 |
| P05 暂时不可执行 | 工具可用还是缺失（e05），人物都知情 | `F=READY`，`C=SUSPENDED` | `F=BLOCKED`，`C=SUSPENDED` | 执行 | 等待工具 | `V/C/Q` 必须相同；只有可行性变 |
| P06 嵌套中断 | 嵌套打印机任务是否完成（e07/e08） | 父目标 `C=SUSPENDED`，`Q=analyze_data`；嵌套任务 `COMPLETED` | 父目标 `C=SUSPENDED`，`Q=analyze_data`；嵌套任务 `IN_PROGRESS` | 回父目标 | 先完成嵌套任务 | 父目标的 `C/Q` 必须相同；只变嵌套任务状态 |
| P07 未来泄漏 | **截断前输入完全相同**，只改截断后的设计结果 | 与 B 完全相同 | 与 A 完全相同 | 预测应相同 | 预测应相同 | 事件必须 `(identical)`；`P07 input identity: PASS` |
| P08 接触但误解 | 都读到取消通知；一个理解、一个误读为暂缓（e06） | `A=ACCESSED`，`B=BELIEVES_INVALID`，`C=ABANDONED` | `A=ACCESSED`，`B=BELIEVES_VALID`，`C=SUSPENDED` | 停止 | 暂停/等待 | `A` 两版都必须是 `ACCESSED`；只变“理解” |

> 注意：P08 两版都“不恢复”，但原因不同：A 是知道取消而停止，B 是误读为暂缓而等待。所以动作标签分别是 `do_not_resume` 和 `suspend_or_wait`。

---

## 2. 用 P01 走一遍

原始输出：

```text
state:
  V: CANCELLED | CANCELLED
  F: READY     | READY
  A: ACCESSED  | NOT_ACCESSED   <-- differs
  B: BELIEVES_INVALID | UNKNOWN <-- differs
  C: ABANDONED | SUSPENDED      <-- differs
  Q: NOT_APPLICABLE | pack_item <-- differs
```

读法：

- 左边是 **A 版**，右边是 **B 版**。
- `V/F` 相同：两版的客观事实和可行性一样，都是“订单已取消、工具可用”。
- `A` 不同：A 版人物接触到了取消通知，B 版没有。
- `B` 不同：A 版人物相信订单无效，B 版没有证据判断人物相信什么 → `UNKNOWN`。
- `C` 不同：A 版放弃，B 版只是暂停、仍想做。
- `Q` 不同：A 版没有恢复步骤，B 版认为自己还没包装完。

再看 `events`：

```text
e06.description:
  A = "取消通知显示在人物屏幕上；人物打开并确认取消。"
  B = "取消通知仅进入后台运营队列；工作台无可见或可听提示。"

e06.person_access:
  A = "ACCESSED"
  B = "NOT_ACCESSED"
```

最后看 `expected`：

```text
A: do_not_resume
B: resume_pack_item
```

一条线：

```text
通知到达人物（e06）
→ 接触 A=ACCESSED / NOT_ACCESSED
→ 信念 B=BELIEVES_INVALID / UNKNOWN
→ 承诺 C=ABANDONED / SUSPENDED
→ 动作 不恢复 / 继续包装
```

这条线能解释通，P01 就通过。

---

## 3. 几个容易误读的地方

### 3.1 `evidence` 里的两个 A

```text
A: A=['e06']  B=['e05', 'e06']
```

第一个 `A:` 是**因子名**（接触），后面的 `A=` 是 **A 版**，`B=` 是 **B 版**。意思是：

- 因子 `A`（接触）：A 版引用 `e06`；B 版引用 `e05` 和 `e06`。

同理：

```text
B: A=['e06']  B=[]
```

第一个 `B:` 是**因子名**（信念），不是 B 版。意思是：

- 因子 `B`（信念）：A 版引用 `e06`；B 版没有任何正证据 → 所以 `B=UNKNOWN`。

**空列表不是漏写，是“没有证据”的正确表示。**

### 3.2 为什么 P03/P05/P06 的 `evidence` 是空的

因为两版的标签引用了同一批证据，没有差异。比如 P05 两版都引用 `e05` 来支持 `F`，只是 `e05` 的内容从“工具在”变成“工具缺失”，所以 `evidence` 行不打印，但 `F` 和 `expected` 会变。

### 3.3 P06-B 为什么 `resume_within_horizon=false`，但 `first_step=replace_toner`

- `resume_within_horizon` 指**原目标**（报告 R7）在 H 内是否恢复 → B 版先修打印机，所以是 `false`。
- `first_step` 指人物的**下一个动作** → 先修打印机的 `replace_toner`。
- 这不是矛盾，是“原目标没恢复，但在做嵌套任务”。

### 3.4 P07 为什么全是 `(identical)`

P07 就是故意让两版截断前输入完全一样，只在设计说明里写“截断后一个恢复、一个不恢复”。模型在截断点的预测必须一样；如果不一样，说明它偷看了未来或受了 `sample_id` 影响。

---

## 4. 你的 3 分钟复核动作

对每一对，按顺序问：

1. `events` 里改的是不是设计规定的那一个变量？
2. `state` 里变的标签，是不是这个变量应该影响的？
3. `expected` 的动作，是不是能从 `state` 和脚本策略推出来？
4. 有没有出现设计之外的字段变化？

四问都过 → 这一对通过。

---

## 5. 机器预检结果（B 人工复核前，2026-10-20）

> 已跑：`validate_data.py`（16/16 通过）、`pair_diff_report.py`（8 对）、逐字段事件比对。下表只覆盖**结构与单变量性**，不能替代你对“人物是否可能知道”的判断。

| Pair | 事件差异（逐字段比对） | 随之变化的状态 | 期望动作 | 预检结论 | 你只需亲自判断 |
|---|---|---|---|---|---|
| P01 | 仅 e06 的 4 个字段（`description`/`person_access`/`person_access_evidence`/`world_effect`） | A、B、C、Q | 不恢复 / 继续包装 | 单变量干净 | 「仅进后台队列」是否有独立证据；B 版 `B=UNKNOWN` 是否成立 |
| P02 | 仅 e03 的 3 个字段（`description`/`event_type`/`world_effect`）；e04–e08 逐字段相同 | C、Q | 恢复 / 不恢复 | 单变量干净 | “放弃”是否应读作 `ABANDONED` 而非 `BELIEVES_INVALID` |
| P03 | e04 的 3 个字段，另 `completed_steps_at_cutoff` 派生不同（A 含 `print_label`） | Q | 从交接 / 从打印 | 干净（派生差异须在清单写明） | B 版 `F=READY` 是否有资源证据支持 |
| P04 | 仅 e05 的 3 个字段 | A、C、Q | 不重复 / 重复 `fill_form` | 干净，但**标签口径存疑** | 全部步骤已客观完成，T1 是否应改为 `not_resume`（与方案 §3.4 冲突） |
| P05 | 仅 e05 的 4 个字段（含 `person_access_evidence`） | F | 执行 / 等待工具 | 单变量干净 | 两版 `A` 都是 `ACCESSED`（人物均知情）是否成立 |
| P06 | e07–e10 重排；事件数 11 vs 10（B 版无 `e08`）；cutoff 同为 09:41 | 六因子全同（差异只在 `interrupting_task`） | 回父目标 / 先完成嵌套 | 结构可接受，T2 已被 A 遮蔽 | 嵌套状态是否应由事件推断；P06 是否仍算 T1/T2 对照 |
| P07 | 无差异（`(identical)`） | 无 | 两版相同 | 输入一致性 PASS | 截断后“一个恢复一个不恢复”只写在 `notes`，是否够用 |
| P08 | 仅 e06 的 `description` 与 `world_effect` | B、C、Q | 不恢复 / 暂停等待 | 干净，但“理解”无结构化字段 | 是否在 v0.2 增结构化理解字段以承载误读 |

**两处必须在复核时定性的问题：**
1. P04-B 的 `resume_within_horizon=true` 与方案 §3.4 的“尚未完成步骤”定义冲突（C 的夹具按 `not_resume` 处理）。
2. P06 的六因子完全相同，A/B 的差异只存在于 `interrupting_task`，而该字段被 A 排除在人物输入外；本对照实际测的是“能否从事件看出嵌套任务未完成”。

## 6. 一句话

**不要从 `state` 开始读，从最下面的 `events` 开始读。**
事件是“因”，状态是“果”，expected 是“人物按脚本会怎么做”。因果能对上，数据就是干净的。
