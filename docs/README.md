# 文档索引

## 竞赛材料（对外提交）

| 文档 | 用途 | Owner | 状态 |
|---|---|---|---|
| [../competition/README.md](../competition/README.md) | 赛道信息、评分映射、提交材料与时间节点 | 三人 | 已建立 |
| [../competition/technical_report.md](../competition/technical_report.md) | 技术方案工作稿（按官方大纲） | A 主笔，B/C 补充 | 骨架/草稿 |
| [../competition/defense_outline.md](../competition/defense_outline.md) | 答辩 PPT 提纲 | A | 提纲 |
| [../competition/demo_script.md](../competition/demo_script.md) | 3–5 分钟演示视频脚本 | C | 脚本 |
| [../competition/submission_checklist.md](../competition/submission_checklist.md) | 提交检查、命名与合规 | C | 检查表 |

## 内部项目文档（不作为提交材料）

| 文档 | 用途 | Owner | 状态 |
|---|---|---|---|
| [internal/research_plan/MWM_Research_Plan_V1_1_EC-JMF.md](internal/research_plan/MWM_Research_Plan_V1_1_EC-JMF.md) | 项目执行基线：任务、算法、协议、分工 | 团队 | V1.1（2026-10-18） |
| [internal/ROADMAP.md](internal/ROADMAP.md) | 十周并行计划、里程碑与竞赛倒排 | 团队 | 草案 |
| [internal/HANDOFF_2026-10-20_P0_v0.2.md](internal/HANDOFF_2026-10-20_P0_v0.2.md) | P0 v0.2 交付说明：给 A/C 的动作、命令、硬约定与已知限制 | B | 已发布 |

## 数据、标注与文献

| 文档 | 用途 | Owner | 状态 |
|---|---|---|---|
| [annotation/annotation_handbook_v1.0.md](annotation/annotation_handbook_v1.0.md) | 事件、状态标签、证据链、事件级理解（U）、八机制、P0/P1 边界与标注 SOP | B | v1.0 已冻结 |
| [annotation/label_quality_plan_v0.1.md](annotation/label_quality_plan_v0.1.md) | P0 质量门、P1 一致性指标、噪声上限与交接模板 | B | v0.1 |
| [annotation/p0_pair_review_table.md](annotation/p0_pair_review_table.md) | P01–P08 复核表与机器预检结果（v0.2 的 120 对按同一方法审计） | B | v1.0 |
| [data/data_card.md](data/data_card.md) | 数据集说明、P0 v0.4（254 条）与 P1 公开派生包、划分与限制 | B | v0.5 |
| [data/external_datasets.md](data/external_datasets.md) | 外部数据集核查：HoloAssist / InteRead / Assembly101 / Ego4D Goal-Step / RFM-HRI，含派生规则与实测数字 | B | v0.1 |
| [data/t3_evidence_mapping.md](data/t3_evidence_mapping.md) | T3 逐因子证据口径（供 A/C 对齐） | B | v1.0 |
| [literature/competitor_matrix.md](literature/competitor_matrix.md) | 直接竞争工作与创新边界索引 | B | 初始索引 |
| [literature/competitors.md](literature/competitors.md) | 竞争工作逐条核查（阅读等级如实标注） | B | 底稿 |
| [literature/core_papers.md](literature/core_papers.md) | 核心理论论文与设计决定映射 | B | 底稿 |
| [literature/mwm_audit.md](literature/mwm_audit.md) | MWM/MENTIS 公开实现与接入边界专项 | B | 底稿（论文全文文本已读）|
| [literature/reading_notes.md](literature/reading_notes.md) | 9 篇全文文本通读笔记（逐篇方法/实验/局限） | B | v1.0 |
| [literature/related_work_draft.md](literature/related_work_draft.md) | 可直接并入技术方案的 Related Work 草稿 | B | 工作稿 |
| [literature/references.bib](literature/references.bib) | 已核实元数据的 BibTeX（正文 9 篇 + 背景 3 篇） | B | v1.0 |

## 写作与核查原则

1. 竞赛材料中的“计划”“目标”“拟实现”必须与“已完成”“已验证”明确分开。
2. 引用论文时优先给出原文链接；二手解读不得写成全文精读结论。
3. 任何性能数字必须能追溯到实验配置、代码 commit 与结果目录。
4. P0 脚本结果与 P1 真实行为结果不得混写。
5. 标注规则变更必须更新手册版本，并在 `schema_version` 或迁移说明中体现。
6. 内部文档与竞赛材料分开：内部计划、未完成风险与团队安排不进入提交材料。
