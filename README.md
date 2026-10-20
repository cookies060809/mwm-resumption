# ECR-MWM / EC-JMF

**面向任务中断与恢复预测的认知可达性约束动态心智世界模型**  
*Epistemically Constrained Dynamic Mental World Modeling for Task Interruption and Resumption Prediction*

> **仓库状态：V0.1 脚手架（2026-10-20）**
>
> 本仓库目前只有研究方案、数据 schema、标注规范草案和 P01 最小对照示例。
> 尚无训练完成的模型，也尚无任何可报告的实验结果。`results/` 中不得出现未经真实实验产生的数字。
> P0 标签是脚本化诊断标签，不代表真实人类心理；P1 真实行为数据尚未采集。

## 一句话定义

研究**外部观察者**如何在连续、部分可观测的事件历史中，同时追踪：现实目标是否有效、人物知道什么、人物是否仍承诺原目标、任务进度与可恢复位置；据此预测人物在中断后**是否恢复原任务、恢复哪个步骤**。

- **ECR-MWM**：完整研究系统。
- **EC-JMF**：核心可训练、可调用、可比较、可消融的联合心智状态滤波器（拟议算法名，非已发表方法）。

正式研究方案见 [docs/research_plan/MWM_Research_Plan_V1_1_EC-JMF.md](docs/research_plan/MWM_Research_Plan_V1_1_EC-JMF.md)。

## 当前进度

- [x] 仓库结构、协作规范与 CI 骨架
- [x] 事件 / 任务图 / 状态 / 标注记录 schema v0.1 草案
- [x] P01 最小对照对示例与 P1 记录模板
- [ ] **M1：任务与接口冻结**（需 A/B/C 三方评审）
- [ ] P0 数据 v1 与标注手册定稿
- [ ] S0 管道校验与 B0–B4 基线
- [ ] EC-JMF 原型与首批实验

完整十周计划见 [docs/project/ROADMAP.md](docs/project/ROADMAP.md)。

## 仓库结构

```text
.
├── docs/                 # 研究方案、标注手册、数据卡、竞品矩阵
├── schema/               # 事件 / 状态 / 任务图 / 标注记录 JSON Schema
├── data/p0/              # P0 对照样例、脚本人物规则与划分
├── data/p1/              # 授权的真实行为数据（默认不入库）
├── models/ec_jmf/        # 联合后验更新、约束与粒子滤波核心算法
├── models/ecr_mwm/       # 端到端模型包装与预测接口
├── baselines/            # B0–B9 强基线与公平比较
├── integration/          # MENTIS 接口与版本适配
├── evaluation/           # 指标、消融、校准、泄漏检查
├── configs/              # 模型与推理预算配置
├── results/              # 逐样例预测、成本、种子、聚合结果（生成物）
├── paper/                # 论文、图表、参考文献、竞赛材料
├── scripts/              # 数据校验等工程脚本
└── tests/                # schema / 数据 / 评测单测
```

## 快速开始

```bash
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash
python -m pip install -r requirements-dev.txt
python scripts/validate_data.py
python -m pytest
```

## 数据与证据边界

1. **P0 与 P1 严格分离。** P0 是人工脚本与明确规则下的协议诊断集，不能用于声称预测真实人类心理；P1 才对应经许可的真实连续行为证据。
2. **P1 原始数据默认不入库。** 只允许提交经批准的元数据、模板或脱敏派生结果；禁止提交可识别个人的视频、音频、屏幕录制或原始日志。
3. **人物能否获知事件必须有独立证据字段。** 不允许把客观世界事实直接复制为人物信念。
4. **禁止未来泄漏。** 预测时刻 `t` 之后的标签、事件或测试集信息不得进入 `observed_events`。
5. **不虚构结果。** 任何准确率、优势或新颖性结论必须来自可复现实验；P0 脚本结果不得写成真实人类恢复预测能力。
6. **证据链强制保存。** 每个非 `UNKNOWN` 的状态标签应能追溯到事件 ID、脚本策略或已批准的标注证据。

详见 [docs/annotation/annotation_handbook_v0.1.md](docs/annotation/annotation_handbook_v0.1.md) 与 [data/README.md](data/README.md)。

## 团队角色

| 角色 | 职责 | 主要目录 |
|---|---|---|
| **A** | 算法与理论负责人：形式化、EC-JMF、训练、消融 | `models/`, `configs/` |
| **B** | 数据与认知机制负责人：schema、标注手册、P0/P1、文献核查 | `data/`, `schema/`, `docs/` |
| **C** | 系统与实验负责人：基线、评测、MENTIS 集成、结果与竞赛包 | `baselines/`, `evaluation/`, `integration/`, `results/` |

协作方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 重要边界

本项目是**研发方案与拟提交的技术贡献**，不是已完成的实证论文。仓库内所有“拟提出”“目标贡献”均指待实现成果；在真实实验完成前，不宣称性能提升、SOTA 或“首次提出”。具体口径见研究方案第 2、5.13、11 节。

## 许可证与访问

仓库当前为私有开发状态，尚未选择开源许可证。公开、竞赛提交或论文附录发布前，由团队共同决定许可证与数据许可范围。
