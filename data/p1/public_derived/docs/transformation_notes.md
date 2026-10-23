# P1 转换说明（ECR-MWM）

本文记录 `processed/p1_combined.jsonl` 每条标签的来源。规则的可执行定义在
[convert_ihbench.py](../scripts/convert_ihbench.py) 与
[convert_interruptbench.py](../scripts/convert_interruptbench.py) 的 docstring（编号 R\* / T\* 与本文一致），
一致性检查在 [merge_and_validate.py](../scripts/merge_and_validate.py)，
字段语义边界在 [schema.md](schema.md)。

## 0. 交付物

| 路径 | 内容 |
|---|---|
| `raw/IHBench/` | `conversations_text.json`（45 行文本列）、`baseline_text.json`（428 行）、`dataset_card.md`、`_manifest.json`（URL、sha256、**真实传输字节数**、未下载的音频字节数） |
| `raw/InterruptBench/` | 与上游同构的 `Eval/` 子树（46 个文本/JSON 文件）+ `_manifest.json` + `_upstream_blobs.json`（逐文件 git blob sha）+ `_upstream_tree_subset.json` |
| `processed/ihbench.jsonl` | 428 条 |
| `processed/interruptbench.jsonl` | 1,815 条 |
| `processed/p1_combined.jsonl` | 2,243 条，按 `sample_id` 排序 |
| `docs/schema.json` / `docs/schema.md` | draft-07 机器定义 / 语义边界说明 |
| `docs/{source_manifest,dataset_card,coverage_report,raw_inventory,llm_validation_log}.md`、`docs/validation_report.txt`、`docs/CHECKSUMS.sha256` | 审计文档 |

复现：`bash run_pipeline.sh`。

## 1. 溯源纪律

- `observed_events[].source` 只出现两种取值：`original_annotation`（直接取自原始字段）与
  `rule_mapping`（由本文列出的确定性规则从原始字段推出）。`llm_inferred` = **0 条**，
  因此没有 P2 补标，也没有需要抽检的模型生成标签（见 [llm_validation_log.md](llm_validation_log.md)）。
- 原始标注缺失时写 `UNKNOWN` / `NOT_APPLICABLE` / `null`，不做补齐。
- `p1_observed_resume`：观察到恢复 → `true`；窗口覆盖完整但未恢复 → `false`；
  **窗口未覆盖且未观察到恢复 → `null` + `p1_censoring_status="censored"`**（v1.1 修正，`null` 不等于 `false`）。
- `evidence_trace` 只引用本 sample 内的 event，且当任一状态字段非 UNKNOWN 时必须包含截断事件（校验器强制）。

## 2. IHBench（arXiv:2606.19595，`bosonai/IHBench`，CC-BY-4.0）

45 段语音工作流对话、617 轮、**428 个中断点**，每点带 TF rubric 与 RQ rubrics，
`knowledge_base.stages[]` 给出状态机步骤。每个中断点产出 1 条 P1 样本。
主体是**语音助手 agent**，不是人类操作者。

| P1 字段 | 来源 | 规则 |
|---|---|---|
| `base_story_id` | `conversation_id` | 直接复制 |
| `goal_id` | `domain.id` + `goal` | `slug(goal)` 作稳定 id |
| `task_steps` | `knowledge_base.stages[].name` | **R1** 按标注顺序 `stage_{ii}_{slug(name)}`（218 个不同步骤） |
| `observed_events` | 逐轮 transcript / interruption_type + 背景信息 | 止于截断事件；截断后的延续**不进入**输入，只记在 `fields_used`，防止标签泄漏 |
| `event_type` | `user_turn_{t}_interruption_type` | 非空 → `interruption`；其余轮 → `progress`；首条 assistant 轮 → `start_goal`；已知/隐藏信息 → `background_fact` |
| `step_id` / `Q` | stage 与话语的词元重合 | **R2** 最佳重合 ≥3 且与次优差 ≥2 才接受；否则继承更早已归因阶段（工作流单调）；完全无法归因 → `UNKNOWN` |
| `A` / `person_access` | `assistant_turn_{t}_original` 非空 | **R3** 话语被截断 ⟹ 系统检测到插入 onset ⟹ `ACCESSED`（428/428）。已知信息用标注字段 `is_user_already_aware`；隐藏信息默认 `NOT_ACCESSED`，除非其 value 文本出现在截断前的用户话语中 |
| `V` | rubric 全量扫描 | **R4** 恒 `VALID`：0/428 条 TF rubric 标注目标撤回或达成。IHBench 结构性地不提供 `CANCELLED`/`FULFILLED` |
| `F` | `turn_{t}_tf_rubric` | **R5** 存在可执行的下一步标注 → `READY`，否则 `UNKNOWN` |
| `B` | 中断类型 | **R6** `{filler, impatient, normal}` → `BELIEVES_VALID`；`{correction, topic_switch, pushback}` → `UNRESOLVED`。B 只从「截断前可见历史」推得，**不从 V 复制** |
| `C` | **R3** | **R7** 恒 `SUSPENDED`：截断点定义即话语执行中被打断，暂挂但仍打算继续，不是 `ABANDONED` |
| `p1_observed_resume` | **R8 内容级判定**（v1.1 重写） | `withheld` = `assistant_turn_{t}_original` 减去已播报前缀 = 用户没听到的残余内容；观察窗口 = 其后 ≤4 条 assistant 轮。判定恢复需满足其一：**(a)** 某轮与 `withheld` 重合 ≥3 个实义词（把被截断的步骤内容说出来）；**(b)** 某轮归因到**更晚**阶段（工作流确实推进）。满足 → `true`/`observed_resume`（346 条）；窗口覆盖 ≥2 轮但两条都不满足 → `false`/`observed_not_resume`（**23 条**）；剩余窗口 < 2 轮且未观察到恢复 → `null`/`censored`（59 条）。按语义边界，仅「重新谈起目标」「回到原句/原阶段」不算恢复 |
| `p1_resume_step` | 满足 R8 的那一轮所属阶段 | **R9** 按 R2 归因，否则 `null`；非 `observed_resume` 时必为 `null` |

**R10 第二行为者（v1.5）**：`baseline.parquet` 的 428 条 GPT-4o Audio 回答与中断点 **1:1 对齐**
（`turn == (interrupting_user_message_index+1)/2` 已校验，无空响应）。每条被复制成一条独立样本：
`base_story_id` = `{conversation_id}@baseline`，`observed_events`/`state_at_cutoff`/`evidence_trace` 与
episode 版本**逐字段相等**（状态只依赖截断前历史），仅恢复标签按其单响应窗口重算：
重述被截断残余内容 ≥3 实词，或被 R2 归因到更晚阶段 → `true`；否则 `false`（单响应即该行为者的完整可观察行为，
故此行为者无 `censored`）。结果：baseline 行为者 true 313 / false **115**，与 episode 行为者在 154 个截断点上分歧。
`original_annotation_ref.file` 改为 `baseline.parquet`，`fields_used` 去掉截断后轮次、加
`response`/`interrupting_user_message_index`/`turn`。

未使用：`user_turn_{t}_audio`（214 MB 音频列，一次都没下载）、`system_message`、
`user_intent.reaction_profile/description/emotion`、`baseline.parquet`（428 条 GPT-4o Audio 参照回答，
属于另一个 agent 的行为，不能当作本 episode 的恢复观测）。

## 3. InterruptBench（arXiv:2604.00892，`HenryPengZou/InterruptBench`）

WebArena-Lite 165 任务 × 6 个场景文件，每任务标注 `intent`、真正下达给 agent 的
`transformed_initial_intent`、逐条 `updates[]`；`raw/3mixed.json` 额外带 per-update `updates_type`。
每个 update 产出 1 条 P1 样本，共 1,815 条。主体同样是 **LLM agent**。

| P1 字段 | 来源 | 规则 |
|---|---|---|
| `base_story_id` | `task_id` | **T1** `wa_lite_task_{id:03d}` |
| `goal_id` | `transformed_initial_intent` + 已发生 updates | **T2** 按 `MULTI_INTERRUPT.md`「把已发生的中断累积进 intent」 |
| `task_steps` | — | **空数组**：源数据无步骤级标注（`interrupt_at_pct` 是运行时动作序列的百分比，仓库不含该序列） |
| `event_type` | `updates[]` / 任务配置 | `start_goal` + 每条 `interruption` + `background_fact`（环境配置；以及**对 agent 保密**的 `eval` oracle） |
| `person_access` / `A` | 注入机制 | **T6**（v1.1 按任务书 §2.4 修订）中断消息由 harness 直接注入 agent 观测流 → `ACCESSED`；起始目标上下文（`start_url`/`require_login`）也在 agent 自身配置中 → `ACCESSED`；`eval` oracle 标注存在但对 agent 保密 → `NOT_ACCESSED`。**只主张暴露，不主张理解** |
| `V` | `updates_type`（3mixed，`original_annotation`）／场景文件名族（其余 5 个，`rule_mapping`） | **T3/T4** `retraction` → `CANCELLED`；`addition`/`modification` → `VALID`。文件名族与 `updates_type` 的言语模式一致（`ignore/don't worry about` = retraction、`I only need` = addition、`I meant X, not Y` = modification），并与论文三类型 addition/revision/retraction 对应 |
| `F` | `eval.eval_types` + `reference_answers`/`reference_url`/`program_html` | **T5** 存在可检验终态 → `READY`（1,309），否则 `UNKNOWN`（506） |
| `B` | 截断前历史 | **T7** `BELIEVES_VALID`，与 V 独立。612 条 retraction 因此构成 `V=CANCELLED` + `B=BELIEVES_VALID` 的错误信念样本 |
| `C` | 中断类型 | **T8**（v1.1 按任务书 §2.4 修订）addition→`ACTIVE`(553)、modification/revision→`SUSPENDED`(650)、retraction→`ABANDONED`(612) |
| `Q` | — | **T9** `UNKNOWN`（无步骤标注） |
| `p1_*` | — | **T10**（v1.1 修正）`null` / `null` / `"censored"`：发布内容不含任何 run 记录，恢复与否**不可观察**；写 `false` 会把「无证据」当成「证据表明未恢复」 |

许可证：仓库根目录无 LICENSE（GitHub `license=null`），唯一 MIT 文本在 `Eval/LICENSE` 且版权行为上游
VisualWebArena 作者。详见 [source_manifest.md](source_manifest.md) §1.2 的 `included_with_caveat`。

## 3.5 REBOOT（`REBOOT26/sample_recovery-demonstration`，Apache-2.0）**v1.3 扩到 4 类截断点**

episode 标注给出五 phase 名称与帧边界 τ0..τ5、`episode_type`、`failure.{originating_phase, failure_mode,
induced_at_frame, recovery_started_at_frame, language_description}`。60 段 episode → **192 条 P1**
（pre 60 / fail 60 / rec 57 / done 15）。截断点类型编码在 `cutoff_event_id` 里，
便于按「盲测恢复预测」与「状态预测」切片。

| 截断点 | 语义 | 本数据集贡献的档位 |
|---|---|---|
| `p##`（失败前最后一个 phase progress） | 关键事件尚不在覆盖历史内 | **A=`NOT_ACCESSED`**、`C=ACTIVE`、`F=READY` |
| `f01_fail`（`induced_at_frame`） | 盲测恢复样本：恢复事件在更晚处且被隐藏 | **F=`BLOCKED`**（标注 `recovery−induced>0` 即源自己给出的不可执行区间）、`C=SUSPENDED` |
| `r01_rec`（`recovery_started_at_frame`） | 恢复与截断点重合，属状态样本 | **`event_type=resume`**、`C=ACTIVE`、`F=READY` |
| `d01_done`（τ5，**仅当** `language_description` 明示完成且无否定词：15/60） | 目标已达成 | **V=`FULFILLED`**、**C=`COMPLETED`**、**`event_type=completion`**、**Q=`NOT_APPLICABLE`** |

**规则 B15（`B=BELIEVES_INVALID` 的唯一来源）**：`failure_mode="freeze"` 描述的是**行为者停止动作**，
而同一行的 `language_description`（"…complete object insertion and release object"）与 `episode_type="recovery"`
断言该目标可完成，`recovery_started_at_frame > induced_at_frame` 给出被冻结的区间。
「对仍有效的目标停止动作」是信念的行为证据 → `B=BELIEVES_INVALID` 而 `V` 保持 `VALID`；
两标签取自**不同标注字段**，因此不是被禁止的 V→B 复制。其余失败模式（misalignment/slip/jamming/
premature_release/delayed_start…）描述工件或抓取状态，**不触发** B15 —— 故本档 n=1。
命中样本：`rbt_16mm-cylinder-install_ep52_f01_fail`。

规则要点：`step_id`/`Q` 一律由帧号落在哪个 τ 区间**推导**（B4），不使用 `originating_phase`；
`V`/`B`/`C` 只在标注支撑处取值；无恢复帧可用的行降级为 `UNKNOWN`/`censored`。
**源侧缺陷（不修复，计入构建日志）**：`originating_phase` 与帧推导不符 31 条、越界（值 21）14 条、
`recovery ≤ induced` 3 条（含 gap −309）、τ 非单调/不闭合 1 条。

## 4. 已知局限

1. **恢复负例只有 IHBench 的 23 条**（R8 内容级判定）。InterruptBench 全部 `censored`（无 run 记录）；
   REBOOT 样例仓 60 段全是 `episode_type="recovery"`，标注里没有「失败后未恢复」的 episode，因此也不产负例。
2. **`B=BELIEVES_INVALID` 仍为 0，且没有合规补法**（详见 llm_validation_log.md）：三个源都不标注
   「人物认为目标已失效」。测试过一条窄规则（用户明示拒绝 + rubric 要求改道），428 条中命中 3 条，
   但这 3 条在**目标层面**用户仍要继续（只是改参数/改渠道），标成 BELIEVES_INVALID 会与你给的 B 定义冲突。
   要真补上它，需要 REBOOT 主仓里 policy 自行中止仍有效任务的 rollout 标注（`REBOOT26/datasets`，未授权 401），
   或 IndustReal 的错误/放弃标注（4TU 本机不可达），或一次真正的 P2 LLM 补标 + 人工抽检。
3. **IHBench 的 `V`/`C` 为常量**（`VALID`/`SUSPENDED`），由 R4/R7 定义决定；区分度集中在
   `Q`、背景事实的 `NOT_ACCESSED`、`B`（225/203）与 censoring。
4. **InterruptBench 无步骤粒度**：适合考察 `V`/`B`/`C` 的撤回推理，不适合考察 `Q`。
5. **不含声学与视觉线索**：IHBench 音频列未下载；REBOOT 的 `data/`（逐帧轨迹）与 `videos/` 未下载，
   因此无法做基于视觉观测或力/位信号的恢复判定。
6. **R2 的阶段归因是启发式**：阈值（≥3 词重合、领先次优 ≥2）写在脚本常量里，
   不达阈值即回退或 `UNKNOWN`，不做人工兜底猜测。

## 5. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-10-22 | 初版 2,243 条：IHBench 恢复判定为「episode 是否延续」，censored 时 `p1_observed_resume=false`；InterruptBench `A=UNCERTAIN`、`C=ACTIVE` |
| v1.1 | 2026-10-22 | 按补充任务书：① censored → `null`；② IHBench 改**内容级**恢复判定（补全被截断内容 / 阶段推进），产出 23 条真实 `observed_not_resume`；③ InterruptBench `A=ACCESSED`、`C` 按 addition/modification/retraction 映射 `ACTIVE/SUSPENDED/ABANDONED`；④ 校验器新增 censoring↔标签一致性、`C=ABANDONED` 与恢复的矛盾检查、`B` 疑似从 `V` 复制的报警；⑤ 目录重构为 `p1_dataset/`，脚本改名 `convert_*.py` / `merge_and_validate.py`，新增 `dataset_card.md`、`schema.md`、`llm_validation_log.md` |
| v1.2 | 2026-10-22 | 新增 REBOOT 源（60 条）：五 phase 步骤、人工标注恢复帧号 → 真实 `observed_resume`；记录源侧 `originating_phase` 不一致 46/60、τ 非单调 1 条；org 扫描确认仅 1/38 仓带 `meta/phase.json` |
| v1.3 | 2026-10-23 | REBOOT 扩为 4 类截断点（60→192 条），补上 `V=FULFILLED`/`C=COMPLETED`/`F=BLOCKED`/`A=NOT_ACCESSED`/`event_type=resume|completion`/`Q=NOT_APPLICABLE`；合计 2,435 条；唯余 `B=BELIEVES_INVALID` 无合规来源，已给出验证过程与解锁路径 |
| v1.4 | 2026-10-23 | 新增规则 B15（REBOOT freeze → `B=BELIEVES_INVALID`，1 条）；IHBench 撤回类窄规则 3+2 条候选逐条否决、baseline 428 条无言语放弃，检索过程留档 llm_validation_log.md |
| v1.5 | 2026-10-23 | 规则 R10：`baseline.parquet` 作第二行为者（IHBench 428→856，`observed_not_resume` 23→138，两行为者 154 处分歧），总数 2,863；2 条诚实告警（阶段不可归因）|
