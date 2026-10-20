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

## 数据、标注与文献

| 文档 | 用途 | Owner | 状态 |
|---|---|---|---|
| [annotation/annotation_handbook_v0.1.md](annotation/annotation_handbook_v0.1.md) | 事件、状态标签、证据链、P0/P1 边界与标注 SOP | B | v0.1 草案 |
| [annotation/label_quality_plan_v0.1.md](annotation/label_quality_plan_v0.1.md) | P0 质量门、P1 一致性指标、噪声上限与交接模板 | B | v0.1 |
| [annotation/p0_pair_review_table.md](annotation/p0_pair_review_table.md) | P01–P08 八组 A/B 对照的人工复核表 | B | v0.1 |
| [data/data_card.md](data/data_card.md) | 数据集说明、当前 16 条种子、规模目标与限制 | B | 已更新 |
| [literature/competitor_matrix.md](literature/competitor_matrix.md) | 直接竞争工作与创新边界索引 | B | 初始索引 |

## 写作与核查原则

1. 竞赛材料中的“计划”“目标”“拟实现”必须与“已完成”“已验证”明确分开。
2. 引用论文时优先给出原文链接；二手解读不得写成全文精读结论。
3. 任何性能数字必须能追溯到实验配置、代码 commit 与结果目录。
4. P0 脚本结果与 P1 真实行为结果不得混写。
5. 标注规则变更必须更新手册版本，并在 `schema_version` 或迁移说明中体现。
6. 内部文档与竞赛材料分开：内部计划、未完成风险与团队安排不进入提交材料。
