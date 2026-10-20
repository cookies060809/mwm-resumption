# ECR-MWM / EC-JMF

**面向任务中断与恢复预测的认知可达性约束动态心智世界模型**

*Epistemically Constrained Dynamic Mental World Modeling for Task Interruption and Resumption Prediction*

> **参赛信息**：第八届全球校园人工智能算法精英大赛 · 算法创新赛 · 赛题 1「算法模型创新」
> **官方页面**：[aicomp.cn/tracks/tracks-2/3788.html](https://www.aicomp.cn/tracks/tracks-2/3788.html)
> **仓库状态：V0.4 P0 v0.2 全量批次（2026-10-20）**　〔本次变更说明见 [docs/internal/HANDOFF_2026-10-20_P0_v0.2.md](docs/internal/HANDOFF_2026-10-20_P0_v0.2.md)〕
> 当前已有研究方案、P0 v0.2 schema、标注手册 v1.0 与 120 家族 / 240 条 P0 数据（B 复核完成）；算法、基线、实验结果、技术方案 PDF、演示视频与答辩 PPT 均未完成。`results/` 中不得出现未经真实实验产生的数字。

## 一句话定义

研究**外部观察者**如何在连续、部分可观测的事件历史中，同时追踪：现实目标是否有效、人物知道什么、人物是否仍承诺原目标、任务进度与可恢复位置；据此预测人物在中断后**是否恢复原任务、恢复哪个步骤**。

- **ECR-MWM**：完整研究系统。
- **EC-JMF**：核心可训练、可调用、可比较、可消融的联合心智状态滤波器（拟议算法名，非已发表方法）。

## 竞赛交付入口

| 材料 | 仓库位置 | 状态 |
|---|---|---|
| 竞赛说明、评分映射、提交材料清单 | [competition/README.md](competition/README.md) | 已建立 |
| 技术方案（官方大纲，Markdown 工作稿） | [competition/technical_report.md](competition/technical_report.md) | 骨架/草稿 |
| 答辩 PPT 提纲 | [competition/defense_outline.md](competition/defense_outline.md) | 提纲 |
| 3–5 分钟演示视频脚本 | [competition/demo_script.md](competition/demo_script.md) | 脚本 |
| 提交检查清单与命名规范 | [competition/submission_checklist.md](competition/submission_checklist.md) | 检查表 |
| 内部研究方案（**不作为提交材料**） | [docs/internal/research_plan/](docs/internal/research_plan/MWM_Research_Plan_V1_1_EC-JMF.md) | V1.1 |
| 内部十周路线图（**不作为提交材料**） | [docs/internal/ROADMAP.md](docs/internal/ROADMAP.md) | 草案 |

竞赛最终提交需要：作品名称（≤20 字）、作品简介（≤300 字）、技术方案 PDF（≤10MB）、3–5 分钟 MP4、答辩 PPT PDF、佐证材料 PDF、代码/大材料链接。所有材料中不得出现学校名称、Logo、指导教师信息。

## 当前进度

- [x] 仓库结构、协作规范与 CI
- [x] P0 schema `p0-record/v0.1.0` 与 P01–P08 共 16 条种子数据
- [x] P0 v0.2 扩展至 120 家族 / 240 条（8 机制 × 15 骨架），含 `split` 与事件级理解字段
- [x] 数据校验、A/B diff、可复现构建脚本与标注质量方案
- [x] B 对 240 条完成人工复核（`annotation.status=reviewed`）
- [ ] A/C 盲审 8 条（每机制 1 条）并仲裁至 `adjudicated`
- [x] 竞赛材料骨架、评分映射与提交清单
- [ ] 核心算法 EC-JMF 最小实现
- [ ] B0–B9 基线与评测框架
- [ ] 真实实验数据与主结果、消融、校准
- [ ] 技术方案 PDF、答辩 PPT、演示视频
- [ ] 提交前合规与复现审查

当前 P0 批次：120 个家族 × A/B = 240 条、1789 条事件；`work` 80 条、`collaboration_service` 84 条、`daily_life` 76 条；`split` 为 72/24/24；`annotation.status=reviewed`。另有 16 条 v0.1 冻结种子供 A 的现有适配器使用。

## 仓库结构

```text
.
├── competition/            # 竞赛材料：技术方案、答辩、演示、提交清单
├── docs/
│   ├── internal/           # 内部研究方案与路线图（不作为提交材料）
│   ├── annotation/         # 标注手册
│   ├── data/               # 数据卡
│   └── literature/         # 竞品矩阵与原文索引
├── schema/                 # P0 记录 JSON Schema（p0-record/v0.1.0）
├── data/
│   ├── p0/                 # 16 条 P0 种子与说明
│   └── p1/                 # P1 合规说明（尚未采集，默认不入库）
├── models/
│   ├── ec_jmf/             # 联合后验更新核心算法契约
│   └── ecr_mwm/            # 端到端包装与 T1/T2/T3 接口
├── baselines/              # B0–B9 基线与公平比较
├── integration/            # MENTIS 接口与版本适配
├── evaluation/             # 指标、消融、校准、泄漏检查
├── configs/                # 模型与推理预算配置
├── results/                # 逐样例预测、成本、种子、聚合结果（生成物）
├── scripts/                # 数据校验、A/B diff、可复现构建
├── tests/                  # schema / 数据 / 评测单测
└── .github/                # CI、Issue/PR 模板
```

## 快速开始

```bash
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash
python -m pip install -r requirements-dev.txt
python scripts/validate_data.py
python scripts/pair_diff_report.py
python -m pytest
```

## 数据与证据边界

1. **P0 与 P1 严格分离。** 当前 P0 为 16 条脚本诊断种子，不能用于声称预测真实人类心理；P1 才对应经许可的真实连续行为证据，目前尚未采集。
2. **P1 原始数据默认不入库。** 只允许提交经批准的元数据或脱敏派生结果；禁止提交可识别个人的视频、音频、屏幕录制或原始日志。
3. **人物能否获知事件必须有独立证据字段。** 不允许把客观世界事实直接复制为人物信念。
4. **禁止未来泄漏。** 预测时刻 `t` 之后的标签、事件或测试集信息不得进入 `observed_events`。
5. **不虚构结果。** 任何准确率、优势或新颖性结论必须来自可复现实验；P0 脚本结果不得写成真实人类恢复预测能力。
6. **竞赛材料合规。** 所有对外材料不得出现学校名称、Logo、指导教师信息；引用他人技术/数据需标注并取得合法授权。

详见 [competition/README.md](competition/README.md)、[P0 数据说明](data/p0/README.md)、[标注手册](docs/annotation/annotation_handbook_v1.0.md)、[质量方案](docs/annotation/label_quality_plan_v0.1.md) 与 [data/README.md](data/README.md)。

## 团队角色

| 角色 | 职责 | 主要目录 |
|---|---|---|
| **A** | 算法与理论：形式化、EC-JMF、训练、消融；技术方案主笔 | `models/`, `configs/`, `competition/technical_report.md` |
| **B** | 数据与认知机制：schema、标注手册、P0/P1、文献核查 | `data/`, `schema/`, `docs/annotation/`, `docs/literature/` |
| **C** | 系统与实验：基线、评测、MENTIS 集成、结果、视频与提交包 | `baselines/`, `evaluation/`, `integration/`, `results/`, `competition/` |

协作方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 重要边界

本项目是**研发方案与拟提交的技术贡献**，不是已完成的实证论文。所有“拟提出”“目标贡献”均指待实现成果；在真实实验完成前，不宣称性能提升、SOTA 或“首次提出”。具体口径见内部研究方案第 2、5.13、11 节。

## 许可证与访问

仓库当前为私有开发状态，尚未选择开源许可证。公开、竞赛提交或论文附录发布前，由团队共同决定许可证与数据许可范围。
