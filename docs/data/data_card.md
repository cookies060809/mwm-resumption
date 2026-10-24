# 数据卡

> **状态：P0 v0.3 发布版（254 条）与 ready-v1.0 已入库；P1 以公开数据派生交付，真人记录为 0。**
> B 人工复核完成（`annotation.status=reviewed`），A/C 盲审与仲裁未做（不是 `adjudicated`）。
> 2026-10-23 团队决定不再进行真人 P1 采集与标注；P1 交付为三源公开数据派生包
> `data/p1/public_derived/`（2,863 条）与训练包 `data/training_ready/v1/`。
> 竞赛提交阶段：P0 只能写作受控脚本诊断，P1 只能写作公开数据派生的辅助任务评测，二者都不得写成真实人类恢复预测。
> Owner：B。版本：v0.4（2026-10-24；A/C 入口与机器可读清单见 [`data/README.md`](../../data/README.md) 与 [`data/RELEASE.json`](../../data/RELEASE.json)）。

## 1. 数据集概述

| 项目 | 内容 |
|---|---|
| 数据集名称 | ECR-MWM Task Interruption & Resumption Dataset |
| 任务 | 外部观察者预测中断后是否恢复原目标（T1）、恢复步骤（T2）、状态信念（T3） |
| 语言 | 中文为主；P1 公开源为英文 |
| 模态 | 结构化文本事件；P1 无音频/视频，只有文本与元数据 |
| 版本 | P0 `p0-record/v0.2.0`（254 条发布版 `p0-release/v0.3.0`）+ 冻结种子 `v0.1.0`（16 条）；P1 `p1-public-derived/v1.5.1`（2,863 条） |
| 访问方式 | P0 / ready-v1 内部研发用；P1 公开派生包内部评测（InterruptBench 分片仅内部，不可再分发） |

## 2. P0：受控协议诊断集

**用途**：测试信息泄漏、因果因素敏感性、目标状态一致性与成对逻辑；**不能**用于声称预测真实人类心理。

| 项目 | 当前 / 计划 |
|---|---|
| 基础故事家族 | **127 个**（v0.2 的 120 个 + v0.3 的 7 个不确定性家族） |
| 每个家族变体 | A/B 各 1 条最小对照（127 + 127） |
| 总量 | **254 条、1,908 条事件**（`data/p0/v0.3/p0_samples.json`） |
| 领域 | `work` 86 条、`collaboration_service` 88 条、`daily_life` 80 条（记录数） |
| 分层因素 | 8 个受控机制：contact_cancellation 36、comprehension 34、long_term_commitment 32、resource_availability 32、resume_position 30、other_completion 30、nested_interruption 30、future_leak 30 |
| 划分 | train 150 / dev 52 / test 52 / calibration 0；按家族分层，同一骨架与同族 A/B 均不跨集合 |
| 标签来源 | 明确脚本策略 + B 人工复核 |
| 标注状态 | `reviewed`；A/C 盲审（每机制 1 条）与仲裁待完成 |
| 校验 | `python scripts/build_p0_release.py --check` 与 `python scripts/validate_data.py --file data/p0/v0.3/p0_samples.json`：254/254 通过 |

### P0 必含场景

P01 取消认知、P02 旧目标承诺、P03 恢复位置、P04 他人代完成、P05 暂时不可执行、P06 嵌套中断、P07 未来泄漏负对照、P08 接触但误解。定义见研究方案第 8.2 节；v0.2 中对应 8 个 `mechanism` 各 15 个家族，v0.3 追加 7 个不确定性家族。

## 3. P1：公开数据派生评测集（无真人记录）

**用途**：只评估"中断后是否恢复/恢复哪一步"的公开行为标注，以及 V 维目标有效性；
**不能**支撑六变量联合监督，也不能写成真实人类恢复预测。

| 项目 | 当前交付 / 边界 |
|---|---|
| 决策 | 2026-10-23 团队决定不再进行真人 P1 采集与标注；原"双人标注、受控采集"方案废止 |
| 来源 | IHBench 856（语音 agent 文本）· InterruptBench 1,815（网页 agent 任务/中断规格）· REBOOT 192（双臂机器人 episode meta） |
| 规模 | 2,863 条；`split` = 1,996/499/368（270 个组不跨 split） |
| 恢复标签 | `observed_resume` 786 / `observed_not_resume` 126 / `censored` 1,951（`null` 不是 `false`） |
| 六变量 | 只有 V 全量有效；F/A/B/C/Q 的规则映射值已按 `state_withdrawn` 撤回，有效行数为 57/72/72/988/15，Q 无具体步骤 |
| 评测视图 | `data/p1/public_derived/eval/`：842 条盲测恢复样本（train/dev/test = 603/177/62），C 协议实测通过 |
| 隐私 | 不含真人视频/音频/屏幕记录；上游标注正文不入库，只保留溯源清单与派生 JSONL |
| 许可 | IHBench CC-BY-4.0；REBOOT Apache-2.0；**InterruptBench 许可未确认，仅限内部评测** |
| 当前状态 | 已交付 `p1-public-derived/v1.5.1`；公开派生包，不是真人行为证据 |

## 4. 标注与证据

- 事件字段、状态标签和硬性约束见 [标注手册](../annotation/annotation_handbook_v1.0.md)；质量门见 [质量方案](../annotation/label_quality_plan_v0.1.md)。
- 每条记录保存 `state_evidence_by_factor` 与平铺的 `state_evidence_event_ids`；P1 的未来观察证据不得进入预测输入。
- P0 的 B 复核记录与 A/B 对照可追溯；P1 没有人工标注，规则映射值撤回后以 `state_loss_mask` 遮蔽损失。
- P0 脚本标签与 P1 公开派生标签分表保存、分表报告；P0 的 `p0_expected` 不是真实行为标签。
- 当前 P0 数据：`data/p0/v0.3/p0_samples.json`（发布版；`data/p0/p0_samples.json` 是 16 条冻结种子）；
  A/B 逐字段审计：`python scripts/pair_diff_report.py`。
- P1 的规则映射值撤回后，有效监督以 `state_loss_mask` 为准；`state_withdrawn` 保存原值与规则号，
  只用于审计，不得当金标或改回。

## 5. 已知限制

1. 首版仅结构化文本事件，不覆盖视觉识别、目标发现与机器人控制。
2. P0 是脚本化诊断数据，外部效度有限；254 条来自 15 个任务骨架 × 8 个机制，同机制句式模板化，不能代表真实语言分布或自然行为分布。
3. 领域覆盖接近均衡（work 86 / collaboration_service 88 / daily_life 80），但每个领域只有 5 个任务骨架，域内多样性仍有限。
4. P1 的恢复行为归因可能存在歧义；无法辨认时记 `UNKNOWN`，不得强行标注。
5. 真实时间预测需要可靠时间戳与删失建模；P1 没有时间戳，评测视图的 `time` 是事件序号。
6. 跨人物/跨任务泛化需要按人物与任务族划分；随机打散会造成泄漏。
7. A 的适配器接受 `p0-record/v0.1.0`/`v0.2.0`，v0.3 记录按 v0.2.0 读取；C 的 `c-evaluation-draft-1` 导出已生成，
   布尔 `understood` 仍合并 MISUNDERSTOOD/NOT_UNDERSTOOD，完整 U 区分须读原生记录。
8. **v0.2 批次在 2026-10-21 就地修正过一次内容**：A/C 盲审抓到 14 条 P01 B 臂人物自述的剩余步数比任务图少 1，`data/p0/p0_samples_v0.2.json` 的 SHA256 由 `fb58cf74…` 变为 `3ca55cc5…`（只有这 14 句 `description` 变化，标签/事件条数/划分未变），`validate_data.py` 同步加了自述步数一致性检查。按旧哈希留档的下游需要重取。
9. **一个已知的标签口径分歧尚未解决、且不在 B 单方面权限内**：19 条 `B=UNKNOWN` 里 16 条在关键事件之后仍存在未计入 B 证据的人物陈述或返回行动，与标注手册 §2.5 的判定顺序冲突（详见手册 §11.1 第 14 条）。A 已表示认可按 §2.5 逐条仲裁，但数据仍保持原样；引用这批数据做信念维结论时要带上这一条。
10. **P1 六变量监督已被撤回**：F/A/B/C/Q 的规则映射值按 T5–T9、R2–R8、B7–B12 撤为 `UNKNOWN`
    （有效行数 57/72/72/988/15，Q 无具体步骤）。P1 只能支撑恢复标签与 V 维，不能当六变量金标。
11. **"不恢复"负例上限 126 条且全部来自 IHBench 文本 agent**（其中 115 条是数据集自带的 GPT-4o Audio 参照回答）。
    真人采集已 descope，没有第二来源；负例召回低是数据属性，禁止把 1,951 条删失改标为负例。
12. **P0 的 254 条只有 B 自审**（`reviewed`），没有 A/C 盲审与仲裁（`adjudicated`）；对外不得写成双人复核。

## 6. 许可与伦理

- P0 与 ready-v1 的 P0 部分是项目自建数据，仅用于内部研发与竞赛准备；正式开放前由团队确定许可证。
- P1 派生包的许可随源：IHBench CC-BY-4.0（需署名）、REBOOT Apache-2.0（需署名）、
  **InterruptBench 许可未确认，仅限内部评测**。任何对外发布、竞赛分发或转公开前，必须剔除 InterruptBench 分片或解决许可。
- 已无真人数据，因此不再涉及知情同意与伦理审批；但对外材料仍不得出现可识别个人信息。
- 任何对外发布需说明数据来源、上游版本、转换规则、标注者状态（P0 为 B 自审）与已知限制。

## 7. 维护

| 角色 | 职责 |
|---|---|
| B | 数据卡、标注手册、schema、划分与质量复核 |
| A | 审查状态标签可训练性与接口一致性 |
| C | 审查评测可用性、泄漏检查与结果可复现性 |

数据卡随每个正式数据版本更新，并在 PR 中记录变更摘要。
