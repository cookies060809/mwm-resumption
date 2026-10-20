# C 系统联调数据卡（integration_fixture）

这 72 条记录是 **C 的工程验收样例**：验证输入隔离、基线训练、状态输出、评测、删失排除和结果保存。它们由脚本创建，**不是 B 已交付的正式 P0 数据，也不是 P1 真实行为数据**。任何分数只能说明系统在这些脚本上的运行情况，不能用于算法有效性、真实人类行为预测或论文性能主张。

`inputs.jsonl` 只放预测时刻可提供的信息；`labels.jsonl` 单独放脚本设定的截止状态和未来窗口答案。所有数据都标记 `purpose=synthetic_integration_fixture`、`dataset_layer=integration_fixture`。`source` 和 `annotation_source` 明确标注人工脚本来源。六个状态因子的 gold 是脚本设定，既不是实际心理测量，也不是模型算法产生的人类心理真值。

## 数量与划分

| 划分 | 数量 | domain | 内容 |
| --- | ---: | --- | --- |
| train | 18 | office | 八组 A/B 对 + censored 1 条 + unknown 1 条 |
| dev | 18 | daily | 同上 |
| calibration | 18 | daily | 同上；独立保留给校准流程接口 |
| test | 18 | service | 同上 |
| 总计 | 72 | 三个域标签 | 64 条二元脚本结果，4 条删失，4 条未知 |

每一划分有 10 个独立 `base_story_id`；同族 A/B 不跨划分。人物 ID 和 `task_family` ID 也按划分隔离。**四个划分复用了相同的八个脚本模板和固定步骤图**；域标签与人物/任务 ID 的变化不形成新的行为证据。不得把 ID 不重合或 office→service 的工程切片结果称为跨人物、跨模板或跨域泛化实证。正式实验必须由 B 提供内容独立、经过复核的真实划分。

## 八组脚本与需要验证的性质

| 场景 | A/B 变化 | 脚本的未来窗口设定 |
| --- | --- | --- |
| P01 | 客观同样已取消；通知被理解/未获知 | A 不恢复；B 推进客观未完成的 prepare |
| P02 | 早期承诺继续/明确放弃；最后五条事件完全相同 | A 恢复；B 不恢复 |
| P03 | print 已完成/仍在进行，前置 verify 和 prepare 都有完成证据 | A 从 handover 恢复；B 从 print 恢复 |
| P04 | 同事已经完成所有步骤；人物获知/未获知 | 两者均不计 T1 恢复，主观 B/C/Q 不同 |
| P05 | 工具已恢复/仍受阻，人物都知晓且保留目标 | A 恢复；B 不恢复，B 的 C 仍为 SUSPENDED |
| P06 | 原任务→紧急插入任务→电话，电话结束后插入任务已完成/仍在进行 | A 返回原任务；B 在窗口内先处理插入任务 |
| P07 | 输入完全相同，仅保存在 gold 的未来行为不同 | A 恢复；B 不恢复；要求方法预测分布相同 |
| P08 | 同一通知都接触到；正确理解取消/明确误读为暂缓 | 两者未来均不恢复；B 分别 INVALID / UNRESOLVED |

P04 按研究计划 §3.4 的“推进尚未完成步骤”解释：同事已客观完成任务后，未获知者即使重复旧动作，也不自动算作 T1 恢复。这组工程样例演示 **主观想继续、重复动作与推进客观未完成步骤的区别**。研究计划场景表中“未获知则可能重复推进”的具体正式标签口径，仍须由 A/B 统一；此处不为正式研究样本作决定。规则方法若预测恢复，工程验收会如实记录其错误，不修改 gold 让基线全对。

P07 的 A/B 截止状态和整个 observation 完全相同。未来脚本答案不同属于不可区分输入的预期测试，任何确定性方法都不能同时猜中这两条二元答案。不能把答案编码到人物、任务、事件 ID 或观察文本中；本组的 A/B 只出现在不会传给 `predict` 的记录元信息和 gold 中。

所有输入事件都在数值时间 20 或以前；所有窗口都是未来 **3 个决策机会**。数值时间是合成脚本的统一时间单位，不能解释为实验测得的秒数、时长或人类认知恢复延迟。脚本未记录真实参与者或真实未来行动。

## 语义与证据

- `semantic.kind` 表达结构化事件，例如 `goal_started`、`goal_suspended`、`step_completed`、`cancellation`、`resource_blocked`。
- `notification_understood` 的 `value` 指消息内容，`reference_event_id` 指向较早的世界事件。事件标签不代替接触和理解证据；方法仍须读取 `person_access_evidence`。P08 的误读记录同时有 `understood=false` 与 `interpretation=defer`。
- `interruption_started/ended` 可用 `interrupting_goal_id` 标记插入活动；嵌套目标有 `parent_goal_id`。
- 每项非 UNKNOWN 的截止状态都有 `state_evidence`，证据 ID 必须来自截止前输入。证据表示脚本支持关系，不表示做过双人标注或一致性审查。
- P01/P04/P08 使用 `pair_relation=different_belief`、`pair_factor=B`；P07 使用 `same_prediction`。其他组由 `base_story_id` 保留 A/B 配对，未强行套用不匹配的关系。
- `known_cancelled` 和 `forbidden_belief` 只放在 gold 的 `constraint_checks`，供评价非法恢复及知识泄漏。

## 重建与验收

在项目根目录运行 `py tools/build_integration_fixtures.py`，会确定性生成本目录两个 JSONL 文件，并打印数量和内容哈希。可通过 `--output-dir` 指定临时目录。生成器写入前执行统一协议校验。

验收覆盖：72 条数量与分层、同族隔离、人物/任务 ID 隔离、共享模板披露、P02 五事件窗口相同、P07 全输入相同、状态不由未来反推、非未知状态的证据引用、无未来输入、删失/未知排除所需标签，以及数据和 gold 分开。

正式交接给 B 后，需要另行完成：来源与许可、独立故事扩展、正式脚本政策、双人标注与仲裁、真实行为证据、任务定义边界、内容级分组划分。这里没有声称完成这些研究任务。
