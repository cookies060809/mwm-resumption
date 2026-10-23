# P1 Schema 与字段语义边界

机器可读定义：[docs/schema.json](schema.json)（draft-07，`additionalProperties: false`）。
本文只写**语义边界**，因为校验器能查格式，查不出把 V 抄进 B 这类越界。

## 样本结构

一行一个 JSON 对象：

```
sample_id, source_dataset, base_story_id, goal_id, task_steps[],
observed_events[{event_id, event_type, step_id, person_access, source}],
cutoff_event_id, state_at_cutoff{V,F,A,B,C,Q},
p1_observed_resume, p1_resume_step, p1_censoring_status,
evidence_trace[], original_annotation_ref{file, fields_used[]}
```

`sample_id` = `{source_abbr}_{base_story_id}_{cutoff_event_id}`，缩写：ihb / rbt / ind / ib。

## 六个状态变量的边界

| | 含义 | 属于 | 禁止的推法 | 本数据集如何取值 |
|---|---|---|---|---|
| **V** | 目标的**客观**有效性：是否已被取消 / 已完成 | 世界状态 | 与「人物是否知道」混谈 | IHBench 恒 `VALID`（0/428 rubric 标注撤回或达成）；InterruptBench 按标注类型：retraction→`CANCELLED`，addition/modification→`VALID` |
| **B** | 人物的**主观信念**（对目标是否仍成立的确信） | 心智状态 | **不能从 V 复制**；V=CANCELLED 不自动 = `BELIEVES_INVALID` | 由「截断前可见历史」推得：两源均 `BELIEVES_VALID`；IHBench 中与在执行计划冲突的三类中断（correction / topic_switch / pushback）记 `UNRESOLVED`。校验器对「V=CANCELLED 的样本 100% 也是 B=BELIEVES_INVALID」报警，即防抄写 |
| **A** | 人物对**关键事件**的接触证据 | 感知/暴露 | `ACCESSED` ≠ 理解、≠ 采纳 | IHBench：话语被截断（`assistant_turn_{t}_original` 非空，428/428）⟹ 系统检测到插入 onset ⟹ `ACCESSED`。InterruptBench：中断消息由 harness 注入 agent 观测流 ⟹ `ACCESSED`（仅主张暴露）。被保密的已知/隐藏信息与 `eval` oracle 以 `background_fact` + `NOT_ACCESSED` 表达 |
| **C** | **承诺/任务控制状态** | 执行状态 | `SUSPENDED` = 暂挂但仍打算继续，**不等于** `ABANDONED` | IHBench 恒 `SUSPENDED`（截断点定义即话语执行中被打断）；InterruptBench 按规定映射 addition→`ACTIVE`、modification/revision→`SUSPENDED`、retraction→`ABANDONED` |
| **Q** | 人物**主观**的恢复步骤 | 心智/计划 | 不等于客观最优步骤 | IHBench：由 R2 词法归因得到「被截断话语所处阶段」，作为 agent 自认要继续的步骤（428 条中 426 条给出具体阶段，2 条 `UNKNOWN`）；InterruptBench 无步骤标注 → `UNKNOWN` |
| **p1_observed_resume** | **确实观察到**的行为恢复 | 观测 | 「再次谈起目标」「回到原地点/原句」不算恢复 | IHBench R8 内容级判定：窗口内某轮助手话语 (a) 与被截断未说的残余内容重合 ≥3 个实义词，或 (b) 归因到更晚阶段（工作流推进）。满足→`true`；窗口覆盖充分但两条都不满足→`false`；窗口未覆盖且未观察到恢复→`null` + `censored` |

## censoring 三态

| `p1_censoring_status` | `p1_observed_resume` | `p1_resume_step` | 语义 |
|---|---|---|---|
| `observed_resume` | `true` | 恢复所落阶段，无法归因则 `null` | episode 覆盖了恢复动作且判定成立 |
| `observed_not_resume` | `false` | `null` | episode 覆盖了完整观察窗口，窗口内既无残余内容补全也无阶段推进 |
| `censored` | **`null`** | `null` | 窗口未覆盖完整**且**未观察到恢复。`null` 不是 `false`：聚合时不可把未观察当失败 |

censoring 的触发条件是「两者同时」：短窗口里若确实看到恢复，仍记 `observed_resume`。

## 溯源分级（任务书 §3）

| 级别 | 方法 | 本数据集实际使用 |
|---|---|---|
| P0 | 原始标注直接映射 | `event.source=original_annotation`（21,645 个事件） |
| P1 | 规则映射（规则写进转换脚本注释） | `event.source=rule_mapping`（5,148 个事件），规则编号 R1–R9 / T1–T10 |
| P2 | LLM 辅助推断（须带 `confidence` + `evidence_quote`，且 ≥10% 人工抽检） | **未使用**，`llm_inferred`=0；见 [llm_validation_log.md](llm_validation_log.md) |
| P3 | 保留 `UNKNOWN` / `NOT_APPLICABLE` / `null` | F=UNKNOWN 506、Q=UNKNOWN 1,817、resume=null 1,874 等 |

## 泄漏控制

`observed_events` 必须**止于截断事件**：恢复动作是标签，出现在输入里就等于泄漏。
`merge_and_validate.py` 对此是硬错误（`observed_events contains events after the cutoff`）。
被读取过的截断后轮次只记录在 `original_annotation_ref.fields_used`，不进入 `observed_events`。

## evidence_trace 的范围

`evidence_trace` 只支撑 `state_at_cutoff` 的非 UNKNOWN 字段，且必须包含截断事件本身
（校验器强制）。恢复标签的证据是「标注引用 + 规则」，不是 `evidence_trace`——因为它依赖被刻意隐藏的截断后文本。
