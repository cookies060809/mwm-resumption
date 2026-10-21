# 直接竞争工作索引

> **状态：初始索引，非全文精读结论。** 本表用于组织 B 的文献核查工作，不替代原文阅读。
> 研究方案提到的三份核查底稿 `competitors.md`、`core_papers.md`、`mwm_audit.md` 尚未加入仓库，需 B 补齐后再更新“核查状态”列。
> 原则：不能宣称“首次提出概率滤波/信念更新/目标暂停恢复”；创新只能落在本项目明确实现并可消融的差异上。

| # | 研究 / 年份 | 原文 | 已有贡献 | 本项目不能再宣称 | 本项目需实现的差异 | 核查状态 |
|---|---|---|---|---|---|---|
| 1 | MWM / MENTIS，2026 | [arXiv](https://arxiv.org/abs/2607.27201) · [代码](https://github.com/mental-world/Mentis) | 物理—心智联合状态、第一人称观察、动作条件化转移 | “首次在世界模型加入目标/意图” | 跨时刻联合状态信念、认知访问控制、恢复点追踪 | 待核查 |
| 2 | Memory for Goals，2002 | [原文](https://www.interruptions.net/literature/Altmann-CogSci02.pdf) | 目标激活、干扰、联想线索与恢复 | “首次设计意图衰减/恢复” | 将认知线索作为状态更新约束/特征 | 待核查 |
| 3 | Timecourse of Recovery，2007 | [原文](https://link.springer.com/content/pdf/10.3758/BF03193094.pdf) | 中断后多次反应的恢复时间过程 | “首次研究恢复时间过程” | 恢复事件 + 恢复步骤的联合预测；多步轨迹为后续 | 待核查 |
| 4 | Suspending and Resuming Tasks in BDI，2008 | [AAMAS](https://www.ifaamas.org/Proceedings/aamas08/proceedings/pdf/paper/AAMAS08_0056.pdf) | 目标暂停、重新考虑条件、计划恢复 | “首次设计 active/suspended/cancelled” | 从外部观察推断隐藏状态，而非代理管理自身目标 | 待核查 |
| 5 | Monk et al.，2008 | [原文](https://interruptions.net/literature/Monk-JEPA08.pdf) | 中断时长、负荷与恢复成本 | 把时长/负荷当新变量 | 作为强对照与分层因素 | 待核查 |
| 6 | Bayesian Theory of Mind，2011 | [原文](https://aiweb.cs.washington.edu/research/projects/aiweb/media/papers/cogsci2011.pdf) | POMDP 下信念—愿望联合归因 | 仅凭“联合贝叶斯后验”主张创新 | 认知可达性门控 + 承诺/进度联合滤波 | 待核查 |
| 7 | What Makes Interruptions Disruptive?，2015 | [作者全文](https://www.jelmerborst.nl/pubs/CHI_Interruptions.pdf) | 问题状态瓶颈、认知检索与恢复代价 | “首次发现中间状态重要” | 显式恢复步骤与任务图一致性 | 待核查 |
| 8 | Dynamic Goal Recognition，2017 | [原文](https://cdn.aaai.org/ocs/ws/ws0409/15222-68440-1-PB.pdf) | 滑窗目标识别、目标切换、旧任务恢复案例 | “首次识别目标切换与恢复” | 保留被暂挂目标，区分取消/完成/不可执行/未获知 | 待核查 |
| 9 | SIPS，2020 | [NeurIPS](https://proceedings.neurips.cc/paper/2020/file/df3aebc649f9e3b674eeb790a4da224e-Paper.pdf) | 目标/计划后验、粒子滤波与重规划 | “首次概率化推断目标” | 学习信息通道 + 承诺 + 恢复步骤的联合转移 | 待核查 |
| 10 | Multi-Agent Intention Recognition，2023 | [IJCAI](https://www.ijcai.org/proceedings/2023/0011.pdf) | 多目标识别与意图调度 | 把多目标跟踪单独当创新 | 单人物跨中断的认知状态与恢复点 | 待核查 |
| 11 | Human Goal Recognition as Bayesian Inference，2024 | [AAMAS](https://aamas.csc.liv.ac.uk/Proceedings/aamas2024/pdfs/p2066.pdf) | 动作、时间、目标可达性 | 把“目标可行性”当新变量 | 区分客观可行性与人物认知到的可行性 | 待核查 |
| 12 | EgoToM，2025 | [arXiv](https://arxiv.org/abs/2503.22152) | 第一人称目标、信念与下一动作基准 | 把第一人称 ToM 基准当本项目贡献 | 跨中断恢复点任务与联合状态滤波 | 待核查 |
| 13 | INSIGHT，AAAI 2026 | [arXiv v2](https://arxiv.org/pdf/2508.01742v2) | HOI + 显式意图 + GRPO 长时程动作预测 | “首次利用意图增强动作预测” | 恢复事件与恢复步骤的专门任务 | 待核查 |
| 14 | MWCRL，AAAI 2026 | [AAAI](https://ojs.aaai.org/index.php/AAAI/article/download/37162/41124) | 原始/打乱动作序列对比增强心智推理 | “首次时序反事实推理” | 受控改变信息接触/可达性，而非乱序 | 待核查 |
| 15 | GDGR / AURA，2026 | [arXiv v2](https://arxiv.org/pdf/2505.09737v2) | 动态目标集合、跨问题/域自适应 | 把动态目标集合当本项目创新 | 同一轨迹内的暂挂—恢复与恢复位置 | 待核查 |
| 16 | GODR，2026 | [arXiv](https://arxiv.org/abs/2606.23797) | 对话运行时目标生命周期、恢复契约、失效规则 | “首次设计恢复契约/恢复点” | 由不完整外部证据推断人物主观状态 | 待核查 |
| 17 | Assistance Without Interruption，2026 | [arXiv](https://arxiv.org/abs/2605.01368) | 非打扰式辅助时机与动作排序 | 把辅助时机决策等同于自主恢复预测 | 预测人物中断后的自主恢复与步骤 | 待核查 |
| 18 | RFM-HRI，2026（ACM MM '25 投稿版） | [arXiv](https://arxiv.org/abs/2603.05641) · [HTML](https://arxiv.org/html/2603.05641v1) | 医疗场景机器人通信失败（speech/timing/comprehension/search）下的多模态用户反应数据集：41 人 / 214 试次，发布 AU、头姿、gaze、Whisper 转写、SAM 三维评分与**机器人恢复策略偏好** | “首次提供失败—恢复的公开多模态数据”；“首次研究恢复偏好” | 人物**自身**任务是否恢复、恢复到第几步；认知可达性与状态信念建模 | 已读（HTML 全文） |
| 19 | REPAIR-Bench，2026 | [arXiv](https://arxiv.org/abs/2606.29937) | 基于 RFM-HRI 的三任务基准：失败时刻检测、失败类型分类、用户偏好恢复策略预测（HRNN + SLM/QLoRA） | 把“失败检测 + 恢复策略选择”当本项目任务 | 同一轨迹内的暂挂—恢复与恢复点位置；对象是人物而非机器人 | 已读（HTML 摘要与数据集节） |

## HRI 失败恢复数据（2026）：能否替代 P1

**结论：不能。** 这一族工作与 ECR-MWM 在**预测对象**上相反，可用于相关工作对照与讨论，不可作为 P1 的替代、预训练来源或 T1/T2 外部验证集。

| 维度 | ECR-MWM（本项目） | RFM-HRI / REPAIR-Bench |
|---|---|---|
| 被预测者 | **人物**（外部观察者推断人物状态） | **机器人**（系统选择该说什么/做什么） |
| 中断来源 | 人物原任务被外部事件打断 | 机器人自身通信失败 |
| 目标变量 | T1 是否恢复、T2 恢复步骤、T3 六因子状态 | 失败类型、失败时刻、**用户希望机器人怎么恢复** |
| 标签来源 | 事件流重放 + 脚本策略（P0）/ 真实行为（P1） | 事后问卷自评 + 研究者标注 |
| 步骤级标签 | 有（`task_steps` + `completed_steps_at_cutoff`） | **无**（只有 trial 级失败类型与偏好） |
| 状态信念 | 有（V/F/A/B/C/Q） | 无（只有 SAM 的 valence/arousal/perceived control） |

**三个必须写清、否则会被判撞车的点：**

1. **`comprehension` 方向相反。** RFM-HRI 的 comprehension failure 是**机器人没听懂人**；我们的 P08 是**人误解了机器人/系统**。同名反义，Related Work 必须显式区分句子，不能只写“同样研究理解失败”。
2. **没有恢复步骤标签。** 它的“recovery”是机器人恢复策略的*偏好*（言语/非言语/多模态，34 类自由文本），不是人物推进到第几步。因此 T2 上无法建立任何映射。
3. **不能当“真实数据”救场。** 竞赛要求可核查的真实数据，RFM-HRI 虽是真人数据，但**任务与标签都不对齐**，用它充数等于虚假对齐，比只用 P0 更危险。

**可用的正当用途（三条）：**

- 相关工作与差异化论证：HRI 侧已有“失败→反应→恢复偏好”的数据与基准，但缺“人物自身目标是否恢复”的观测，正好证明本项目的空缺真实存在。
- 动机与讨论：其结论（失败显著降低 perceived control、困惑→挫败随时间累积）可支撑“恢复预测为何必须以人物认知状态为条件”，引用时注明是自评量表结论，不是行为标签。
- 未来工作的外部效度方向：若把 ECR-MWM 迁到 HRI 场景，RFM-HRI 是当前唯一公开候选；届时要补的正是 T1/T2 标签。

**获取状态（2026-10-21 核查）：** 论文声称 "publicly available" 且 "will be made publicly available"，但**未给出下载链接、仓库地址或正式 DOI**（DOI 为占位符 `10.1145/XXXXXXX.XXXXXXX`）；arXiv 页面的 CC BY 4.0 是**论文**许可，不是数据集许可。数据集仅发布派生特征与转写，**不含原始视频与音频**。按 IRB 惯例此类医疗场景人数据通常需签数据使用协议，实际入口需邮件询问通讯作者（`yb344@cornell.edu`）。**当前不下载，理由见上：标签不对齐。**

## 全文未获取的记录

- Steyvers、Mayer、Ayoub（CogSci 2025）：仅见[机构库摘要](https://repositories.cdlib.org/uc/item/8082r6kc)，**不得**列为已完成全文精读。
- Steyvers & Mayer 的另一篇 [arXiv 论文](https://arxiv.org/abs/2508.01837) 不能冒充三作者稿。

## B 的阅读优先级

1. MWM / MENTIS：状态定义、动作条件化转移、公开实现边界。
2. Memory for Goals / Timecourse / Borst / Monk：目标激活、恢复代价、时长与负荷对照。
3. BDI 2008 / GODR 2026：生命周期、恢复契约与规则基线的能力边界。
4. 2017 滑窗 / SIPS / 2024 goal solvability：目标识别、粒子滤波、可行性。
5. INSIGHT / MWCRL / EgoToM：意图、时序对比与第一人称评估，明确迁移性比较边界。
6. GDGR/AURA、Assistance Without Interruption：确认任务设定差异。
7. RFM-HRI / REPAIR-Bench：**优先级低但必须写一句**——它们是唯一公开的“失败—恢复”多模态数据，评审很可能会问“为什么不直接用”。答案已在上节表格，写进 Related Work 的“邻近但不同”段即可，不必精读全部结果表。

## 核查记录规范

每篇论文至少记录：

- 原文链接、版本/日期、阅读范围（全文/部分/仅摘要）；
- 任务设定、输入输出、状态定义；
- 使用的数据、基线、指标；
- 公开实现及 commit；
- 与本项目相同点、差异点、不能被占用的声明；
- 可复现性缺口与不能外推的结论。

核查结论写入 `docs/literature/` 下的独立笔记，并在本表更新状态。
