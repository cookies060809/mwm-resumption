# 论文与竞赛材料

Owner：三人共同；各章节主笔如下。状态：提纲，尚未写作。

## 章节提纲

| 章节 | 内容 | 主笔 | 状态 |
|---|---|---|---|
| Abstract | 任务、方法、证据边界 | A + B | 未开始 |
| 1 Introduction | 问题动机、研究问题、贡献 | A | 未开始 |
| 2 Related Work | MWM、BDI、目标识别、SIPS、ToM、时序对比 | B | 未开始 |
| 3 Task & Benchmark | 任务定义、P0/P1、标签、评测协议 | B | 未开始 |
| 4 ECR-MWM | 系统结构、状态因子、接口 | A | 未开始 |
| 5 EC-JMF | 转移分解、可达性门控、SMC、损失 | A | 未开始 |
| 6 Experiments | 基线、数据、预算、实现细节 | C | 未开始 |
| 7 Results | 主结果、消融、校准、效率、失败案例 | C | 未开始 |
| 8 Discussion & Limitations | 外部效度、P0/P1 边界、伦理 | A + B | 未开始 |
| 9 Conclusion | 贡献与未来工作 | 三人 | 未开始 |
| Appendix | 标注手册、schema、复现说明 | B + C | 未开始 |

## 写作纪律

- 区分“拟提出/目标贡献”与“已完成/已验证”。
- 不写“首次提出目标暂停/恢复”“首次把意图加入世界模型”等已被先例覆盖的表述。
- 不写未经实验支持的“性能提升 X%”或“证明 MENTIS 失败”。
- P0 结果只能表述为受控协议诊断；真实人类预测必须基于 P1 证据。
- 引用优先原文；未获取全文的文献只能引用摘要并注明。
- 每个数字对应 `results/<run_id>`，图表由脚本生成。

## 素材

- 研究方案：[../docs/research_plan/MWM_Research_Plan_V1_1_EC-JMF.md](../docs/research_plan/MWM_Research_Plan_V1_1_EC-JMF.md)
- 标注手册：[../docs/annotation/annotation_handbook_v0.1.md](../docs/annotation/annotation_handbook_v0.1.md)
- 数据卡：[../docs/data/data_card.md](../docs/data/data_card.md)
- 竞品矩阵：[../docs/literature/competitor_matrix.md](../docs/literature/competitor_matrix.md)

## 待办

- [ ] 确认目标会议/竞赛模板与页数限制
- [ ] 建立图表清单与数据来源映射
- [ ] 三人交叉核对“已完成/已验证”表述
- [ ] 复现实验附录与代码可用性说明
