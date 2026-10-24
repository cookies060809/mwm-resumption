# Dataset card — P1 结构化评测集（ECR-MWM）

## 一句话定义

从**公开数据集的已有标注**重组出的结构化评测样本：给定中断发生时刻的事件序列，判断目标状态
（`state_at_cutoff`）与是否恢复执行（`p1_observed_resume`）。

**本数据集不是从零采集的真实人类行为日志。** 没有任何原始采集、人类受试者环节或伦理审批事项；
所有标签来自已发布数据集的已有标注字段（rubric、episode 标注、任务/中断规格、phase 边界与恢复帧号），
经转换脚本中编号列出的确定性规则映射得到；无证据处写 `UNKNOWN` / `NOT_APPLICABLE` / `null`。

## 规模

| 项 | 值 |
|---|---|
| 样本总数 | **2,863**（`processed/p1_combined.jsonl`） |
| 源 | IHBench 856（428 episode 行为者 + 428 baseline 行为者）· InterruptBench 1,815 · REBOOT 192 |
| `p1_censoring_status` | observed_resume **786** / observed_not_resume **126** / censored **1,951** |
| `p1_observed_resume` | true 786 · false 126 · **null 1,951** |
| 状态取值覆盖（撤回后生效值） | V{VALID 2236, CANCELLED 612, FULFILLED 15}、F{READY 57, UNKNOWN 2806}、A{ACCESSED 72, UNKNOWN 2791}、B{BELIEVES_VALID 72, UNKNOWN 2791}、C{SUSPENDED 856, ACTIVE 117, COMPLETED 15, UNKNOWN 1875}、Q{NOT_APPLICABLE 15, UNKNOWN 2848}（具体步骤 **0**） |
| 状态撤回 | 2,863/2,863 行带 `state_withdrawn`：F 2,806 / A 2,791 / B 2,791 / C 1,875 / Q 2,848 / `p1_observed_resume` 2 行被降为 `UNKNOWN` 或移除，逐条记录规则号与理由（详见 README「状态撤回」） |
| 评测视图 | `eval/{inputs,labels}.jsonl`：842 条盲测恢复样本，C 协议 `c-evaluation-draft-1` 实测通过；train/dev/test = 603/177/62 |
| `llm_inferred` 标签 | **0** 条（见 [llm_validation_log.md](llm_validation_log.md)） |
| 校验 | draft-07 + 跨字段 + 泄漏 + 溯源检查：**0 violations / 2 warnings**（2 条恢复样本的阶段无法归因，`p1_resume_step` 留 null）|

## 主体与模态声明（务必先读，防止跨源误用）

| 源 | 主体 | 模态 | 必须知道的限定 |
|---|---|---|---|
| **IHBench**（856） | **语音助手 agent**（两个行为者：对话内的 assistant + 数据集自带的 GPT-4o Audio 参照回答）| 合成但经人工校验的双通道对话**文本**（音频未下载） | P1 适配自 IHBench 的 **Agent 恢复标注**，用于验证字段映射与流水线，**不代表人类恢复行为**。`p1_observed_resume=true` 指助手在中断后把被截断的工作流步骤继续下去，不是人的动作恢复 |
| **InterruptBench**（1,815） | **LLM 网页 agent** | 任务/中断**规格**文本（自然语言 intent + updates） | 该源只标注「中断应如何改变目标」，**不含任何 agent 实际后续行为记录** → 全部 `censored`、`p1_observed_resume=null`、`task_steps=[]`。它的可用价值只剩 **V 维**：612 条 `V=CANCELLED`；`B/C/Q/F/A` 已全部撤回，不再提供错误信念监督 |
| **REBOOT**（192） | **双臂机器人 + 人类操作员示教** | 精密装配 episode 的 phase 边界与失败/恢复帧号（纯 JSON meta；轨迹与视频未下载） | P1 适配自 REBOOT 的 **meta 标注**，任务为五 phase 精密装配序列，**不是人类日常任务中断**；用于补充恢复步骤的结构化标签。恢复标签来自人工标注的 `recovery_started_at_frame`，属真实观测 |

三源主体不同 → **任何跨源合并指标都必须同时分源报告**；`task_steps` 只在 IHBench 与 REBOOT 上有定义，
且撤回后**没有任何一条具体 `Q` 步骤标签**（15 条 `NOT_APPLICABLE` 全部来自 REBOOT 完成点）。

## 使用限制

1. **再分发限制**：InterruptBench 分片许可证不明确（详见 [source_manifest.md](source_manifest.md) §2.4）→
   该分片**仅限内部评测**；IHBench（CC-BY-4.0）与 REBOOT（Apache-2.0）可署名再分发。
2. **无视听线索**：IHBench 的 214 MB 音频列、REBOOT 的 `data/`+`videos/` 均未下载。
   依赖打断时刻、时长、韵律或视觉观测的评测无法在此数据集上进行。
3. **null ≠ false**：`p1_observed_resume=null` 表示「未观察到（窗口未覆盖）」，聚合时不可当作失败。
4. **REBOOT 标注存在源侧不一致**：60 条中 **46 条** `failure.originating_phase` 与「失败帧落在哪个 phase 区间」
   不符（偏移 +1 ×22、+2 ×22、−1 ×1、越界值 21 ×1），另有 1 条 phase 边界非单调。转换器不使用该字段定 step_id，
   而由 `induced_at_frame` + `phase_boundaries` 推导（规则 B4/B13/B14），受影响行进入构建日志；3 条降为 `censored`。
   **这是源数据属性，未被「修正」**，引用 REBOOT 标签时应知悉。
5. **REBOOT 覆盖有限**：org `REBOOT26` 的 38 个仓中只有 1 个（样例仓）带 `meta/phase.json`；
   项目页链接的主仓 `REBOOT26/datasets`（应为 2,160 段 / 18 任务的完整标注）未授权返回 401。
6. **"不恢复"监督上限**：126 条 `observed_not_resume` 全部来自 IHBench（11 条 episode 行为者 + 115 条
   GPT-4o Audio 参照回答），真人采集已于 2026-10-23 descope。模型"不恢复"召回低属于数据上限，
   不得把 1,951 条删失样本改标为负例来补。恢复评测只使用 `eval/` 的 842 条。
7. **六变量只剩 V 可用**：`state_withdrawn` 落地后，F/A/B/C/Q 的有效监督为 57/72/72/988/15 行，
   其中 Q 无权具体步骤。**不要**把这份数据当六变量联合监督金标；六变量主监督在 `data/p0/v0.3` 与
   `data/training_ready/v1`。

## 引用

- IHBench — arXiv:2606.19595；`bosonai/IHBench`（CC-BY-4.0）；`boson-ai/ihbench`（Apache-2.0）。
- InterruptBench — arXiv:2604.00892；`HenryPengZou/InterruptBench`；底层 WebArena / WebArena-Lite（MIT）。
- REBOOT — *REBOOT: From Failure to Recovery — A Dataset and Benchmark for Precision Assembly*（Ofori-Ampofo,
  Ebrahimi Kahou, Thekinen, 2026）；`REBOOT26/sample_recovery-demonstration`（HF tag Apache-2.0；项目页称 CC-BY-4.0）；
  基于 LeRobot（Apache-2.0）。
- IndustReal（未使用）— arXiv:2310.17323；代码 `TimSchoonbeek/IndustReal`（Apache-2.0）；数据在 `data.4tu.nl`（本环境不可达）。

## 版本

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-10-22 | 初版 2,243 条（IHBench + InterruptBench）；censored 时 `p1_observed_resume=false` |
| v1.1 | 2026-10-22 | 语义边界修订：censored → `null`；IHBench 恢复判定改为内容级（新增 23 条 `observed_not_resume`）；InterruptBench `A=ACCESSED` 且 `C` 按 addition/modification/retraction → ACTIVE/SUSPENDED/ABANDONED；目录重构为 `p1_dataset/` 并补 `dataset_card.md`、`schema.md`、`llm_validation_log.md` |
| v1.2 | 2026-10-22 | 新增 **REBOOT** 源（+60 条，五 phase 步骤与人工标注恢复帧号）；记录 REBOOT 源侧 `originating_phase` 不一致与「仅 1/38 仓带标注」的可用性上限 |
| v1.3 | 2026-10-23 | REBOOT 扩为 4 类截断点（60→192 条），补齐 `V=FULFILLED`/`C=COMPLETED`/`F=BLOCKED`/`A=NOT_ACCESSED`/`resume`+`completion` 事件/`Q=NOT_APPLICABLE`；总数 2,435。`B=BELIEVES_INVALID` 经检索确认无合规来源，调查过程见 `llm_validation_log.md` |
| v1.4 | 2026-10-23 | 复核后推翻「B 档不可补」的结论：REBOOT `failure_mode="freeze"` 提供 1 条 `B=BELIEVES_INVALID`（规则 B15，行为证据、与 V 取自不同标注字段）；`docs/llm_validation_log.md` 改写为完整检索记录（IHBench 窄规则 3+2 条全部否决、baseline 428 条 0 命中）|
| v1.5 | 2026-10-23 | 加入 `baseline.parquet` 作为**同截断点的第二行为者**（规则 R10）：IHBench 428→856 条，`observed_not_resume` 23→138；两行为者 `state_at_cutoff` 逐条相等、恢复标签 154 处分歧；总数 2,863。这是修订前的 build 口径 |
| v1.5.1 | 2026-10-23（文档 2026-10-24） | **状态撤回修订 + 评测视图**：F/A/B/C/Q 的规则映射值按 T5–T9、R2–R8、B7–B12 撤为 `UNKNOWN`，逐行写 `state_withdrawn`（F 2,806 / A 2,791 / B 2,791 / C 1,875 / Q 2,848）；2 条无恢复事件的 `p1_observed_resume` 按 B12 退回 `censored`，正式交付计数为 786/126/1,951。新增 `split`/`split_group_id`（270 组，不跨 split）与 `eval/` 842 条 C 协议视图。数据行数与字段结构不变，但**标签语义以本版为准** |

**入库说明（2026-10-23 入库，2026-10-24 修订）：** 本包从仓库根 `p1_dataset/` 整体迁至 `data/p1/public_derived/`。
Git 只跟踪溯源清单，`raw/` 里的上游标注正文不入库，因此新克隆需要先跑 fetch 步骤才能重建。
入库同时把本包定位为**三源辅助任务候选集**，不等同于研究方案中的正式 P1（真实人物跨中断恢复观测）。
2026-10-23 的修订把站不住的规则映射标称值撤回，只保留有逐行证据的 V 与少量 REBOOT 的 F/A/B/C；
缺证据处应遮蔽损失而不是当金标使用。v1.5 条目里的 788/138/1,937 是修订前 build 的数字，已不适用。
