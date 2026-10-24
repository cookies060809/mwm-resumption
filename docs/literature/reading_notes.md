# 文献精读笔记（2026-10-24）

> Owner：B。性质：内部核查记录，不直接作为提交材料。
> **阅读等级说明：** 本文件的“已读”指机器辅助通读全文文本（PDF/HTML），并逐节核对了方法、实验与局限；
> **不是**人工逐段精读。提交前由 B 本人抽查关键数字与表述，再升级为“已读（人工复核）”。
> 未读的论文仍按 [competitors.md](competitors.md) 的等级标注，不得引用其具体结论。

## 0. 本轮实际处理的论文

| 编号 | 论文 | 来源 | 本轮读到什么 |
|---|---|---|---|
| R1 | EchoChain | arXiv 2604.16456 | 全文（引言/失败分类/框架/结果/局限） |
| R2 | DuplexLedger | arXiv 2610.27581 | 全文（任务形式化/监督/结果/失败分析/结论） |
| R3 | Beyond LLMs: A Mental World Model Framework (MMEA) | arXiv 2610.23722 | 全文（摘要/相关工作/架构/实验/结论） |
| R4 | Mental World Modeling (MWM/MENTIS) | arXiv 2607.27201 | 全文（框架/核心定义/MENTIS 实现/评测/瓶颈） |
| R5 | GODR | arXiv 2606.23797 | 全文（动机/目标生命周期/操作模型/BDI 关系） |
| R6 | Suspending and Resuming Tasks in BDI Agents | AAMAS 2008 | 全文（暂停条件/承诺因素/机制） |
| R7 | Dynamic Goal Recognition Using Windowed Action Sequences | AAAI-17 Workshop | 全文（窗口策略/实验/结论） |
| R8 | Online Bayesian Goal Inference (SIPS) | NeurIPS 2020 | 全文（模型/在线推断/实验/局限） |
| R9 | SymbolicToM belief tracker | ACL 2023 | 全文（方法/实验/局限） |
| R10 | Memory for Goals | Cognitive Science 2002 | 仅二手引用（由 R4/R8/R9 及检索片段转引，未读原文） |
| R11 | Spatial memory guides task resumption | Visual Cognition 2008 | 仅元数据（题名/DOI 已核实） |
| R12 | Speed–accuracy trade-offs in task resumption | JEP Applied 2013 | 仅元数据 |

## 1. 逐篇笔记

### R1 EchoChain（2026，arXiv）

- 作者/机构：Smit Nautambhai Modi, Gandharv Mahajan, Marc Wetter, Randall Welles（Applied Machine Learning Research / Labelbox）。
- 问题：实时语音助手在用户**插话**时必须改写正在生成的任务状态；现有基准多为半双工、按轮次评测。
- 方法：受控全双工基准。场景种子 → planner-simulator 生成用户话语与 barge-in → 预合成语音 → 固定偏移注入打断 → 四个闭源实时语音模型。
- 评测：200 段被打断对话；两个指标——MPR（整段对话全部 rubric 通过的比例）、MCP（单条 rubric 通过比例）。
- 结果：四个模型 MPR 全部 **< 50%**。
- 失败分类：Contextual Inertia（口头承认但不改内容）、Interruption Amnesia（忘记打断前的约束）、Objective Displacement（目标被替换）。
- 局限：只覆盖“生成中注入任务相关信息”的打断；固定偏移而非人类判断；闭源模型；不评声学维度。
- 与本项目关系：**最接近的“中断后状态更新”评测**，但预测对象是语音助手自身状态，不是外部观察者推断人物状态；标签是 rubric，不是六因子。
- 不能宣称：首次做中断后状态更新评测、首次提出中断失败分类。

### R2 DuplexLedger（2026，arXiv）

- 作者/机构：Yuxuan Li 等（NTU / PKU / BJUT / Xidian / Melbourne 等）。
- 问题：全双工语音 agent 在边说边听时，必须决定哪些事件写入、修订或忽略持久记忆。
- 方法：把会话形式化为事件流 `E=(e1..eT)`，记忆项带 `active/superseded` 状态；事件级操作 `WRITE/UPDATE/IGNORE/RETAIN`；1,094 个中英双语会话；证据对齐的语音问答。
- 结果：五个系统没有一个同时占优；最好的 latest-value 准确率 25.50% 但 final-state 覆盖仅 1.06%；最好的 final-state 覆盖只有 2.01%；提出 ACT-Mem（事件控制器 + 版本化 ledger + 类型化检索），在 219 个留出会话上把 latest-value 准确率从 4.11% 提到 8.68%，但打断停止变慢。
- 局限（从结论与失败分析）：交互与记忆分离评测；参考状态由构造生成；系统均为语音 agent。
- 与本项目关系：**事件级“写入/修订/忽略”与我们的 A/B/C 证据更新同构**；但它是 agent 自己的记忆，不是观察者对人物的信念。
- 不能宣称：首次做事件级记忆更新基准、首次提出 “retain/ignore” 语义。

### R3 MMEA / Mental World Model（2026，arXiv）

- 作者：Qingshi Wang（Bristol）、Huiqi Tong（Stanford）。
- 主张：LLM/ToM 主要从语言推断心理状态，缺少主观世界构建、认知—心理交互、动态演化与历史依赖的统一机制；提出 MWM 与 MMEA。
- 方法：分层信息流（感知 → 认知 → 心理计算 → 预测）；在 DynToM 与 RecToM 上评测；DynToM 1,420 题、总计 1,820 题。
- 结果（论文自报）：DynToM **96.48%**、RecToM **94.00%**，优于其对比的通用 LLM。
- 局限（论文自述与结构）：仍是**语言/行为线索**驱动的心理状态推断；评测为选择题式基准；不提供外部观察者的任务恢复步骤预测；未发布可核查代码（本仓库未找到）。
- 与本项目关系：直接占用 “Mental World Model” 术语与框架；必须引用并区分。
- 不能宣称：首次提出 mental world model、首次做心理状态演化建模。

### R4 MWM / MENTIS（2026，arXiv）

- 作者：Hao Fei（Oxford）、Yiran Zhao（NUS）；项目页 `mental-world.github.io`；代码 `mental-world/Mentis`（MIT，2026-10-24 核实）。
- 主张：世界模型不能只回答物理问题；需要联合物理—心智状态，并按每个 agent 的部分观测建模。
- 框架：目标观测 `o_t` 是对全局状态的第一人称渲染；状态含物理组件（实体/属性/关系/环境）与心智组件（信念/注意/目标/意图/情绪/偏好/关系/规范/氛围）。
- 实现：MENTIS 将状态表示为可校验 JSON；状态解析 → 观测生成（信息过滤）→ 动作分解 → 耦合状态转移。
- 评测：Menti-Bench（文本/图像序列/带声视频三种模态；含联合状态、目标观测、动作与转移标注）；8 个 LLM 世界模型；necessity ladder S0–S6；完整 MWM 的 F1 **90.7**，人类参照 **98.5**；oracle 干预显示**转移模拟**是最大单点瓶颈（gold transition +3.5 F1）。
- 局限：Menti-Bench 规模小、以选择题/短故事为主；不涉及“中断后是否恢复/恢复哪一步”；状态解析依赖 LLM。
- 与本项目关系：最直接的世界模型先例；我们的差异必须落在**外部观察者 + 六因子 + 恢复步骤**，不能落在“联合物理—心智状态”本身。
- 不能宣称：首次把心智状态加入世界模型、首次做可检查的世界模型实现。

### R5 GODR（2026，arXiv）

- 作者：Mariano Garralda-Barrio（独立研究者）。
- 问题：图/多 agent 编排框架解决了执行连续性，但不解决多个相互依赖目标的**目标连续性**。
- 贡献：提出 Goal-Oriented Dialogue Runtime（GODR）作为框架无关的架构层；目标结构是有向图 `Gt=(Vt,Et)`，关系含 `parent/depends_on/blocks/supersedes/resumes/invalidates`；目标生命周期、恢复契约、失效关系显式化为运行时对象；含 goal-complexity taxonomy（GC-4 示例）。
- 与 BDI：GODR 与 BDI 兼容但更窄——只做对话目标连续性的系统工程，不要求完整 BDI agent 模型。
- 局限：概念/架构论文，没有人物状态数据集与实证评测；恢复契约是运行时设计，不是观察者推断。
- 与本项目关系：最接近“恢复契约/目标生命周期”的工程侧工作；必须引用并区分预测对象。
- 不能宣称：首次设计恢复契约、首次提出目标生命周期。

### R6 BDI 2008（AAMAS）

- 作者：John Thangarajah, James Harland, David Morley, Neil Yorke-Smith（RMIT / SRI）。
- 问题：BDI agent 如何在动态环境中暂停/重新考虑/恢复任务。
- 机制：任务（目标/计划/原子动作）可暂停并附**重新考虑条件**（reconsideration condition）；条件为真时进入下一轮慎思，可选择恢复、继续暂停、终止或做其他元动作。
- 承诺因素：效用、优先级、截止期、预计成本/资源、其他目标的依赖（内部/外部）、目标间正负交互、已投入努力、预计成功概率。
- 实现：CAN 语言；默认 suspend/resume 机制（自顶向下暂停父子任务）；计划库变换、目标展开转移、选择性重新激活子目标。
- 局限：agent 管理自身目标；没有“外部观察者从事件流推断隐藏状态”的设定；没有真实数据评测。
- 与本项目关系：`ACTIVE/SUSPENDED/ABANDONED` 与“重新考虑条件”的概念来源；我们的差异是**推断**而非**管理**。
- 不能宣称：首次设计暂停/恢复生命周期、首次提出重新考虑条件。

### R7 Windowed Goal Recognition（AAAI-17 Workshop）

- 作者：David Henri Menager, Dongkyu Choi, Michael W. Floyd, Christine Task, David W. Aha。
- 问题：动态环境中目标可能突然变化；传统目标识别假设静态目标。
- 方法：在现有目标识别器外挂一个**滑窗**，只把当前窗口内的状态-动作序列送入识别器，以检测目标变化；算法无关（以 SET-PR 为底层）。
- 评测：三个域（Autonomous Squad Member、Rovers、Childsnack）；与不设窗口的 SET-PR 对比，报告初始/最终目标检测正确率、检测到变化与真实变化的距离、收敛所需动作数。
- 结论：窗口化能更快、更可靠地检测目标变化；作者明确不声称窗口对所有情况都最优。
- 局限：目标是离散、可枚举；没有“暂停/放弃”状态；没有人物信念。
- 与本项目关系：最接近“目标切换/旧任务恢复”的识别工作；我们的差异是保留被暂挂目标并区分取消/完成/不可执行/未获知。
- 不能宣称：首次识别目标切换与恢复。

### R8 SIPS（NeurIPS 2020）

- 作者：Tan Zhi-Xuan, Jordyn L. Mann, Tom Silver, Joshua B. Tenenbaum, Vikash K. Mansinghka（MIT）。
- 问题：从最优与非最优（含失败）动作序列在线推断目标。
- 方法：PDDL 状态/目标表示；对 boundedly-rational agent 建模；贝叶斯后验 `P(g|o1:t)`；用序贯蒙特卡洛在线近似；重采样与 rejuvenation 管理假设多样性。
- 评测：多个规划域；与基线比较准确率、速度、鲁棒性；定性展示失败/回溯轨迹上的目标推断。
- 局限（论文自述）：只考虑**有限目标集**；目标是最终的、非层级/工具性的；主要考虑确定性转移；动作空间有限。
- 与本项目关系：概率化目标推断的强基线；我们的差异是**六因子状态 + 承诺/进度 + 恢复步骤**，不是单纯目标后验。
- 不能宣称：首次用粒子滤波/贝叶斯做目标推断。

### R9 SymbolicToM（ACL 2023）

- 作者：Melanie Sclar, Sachin Kumar, Peter West, Alane Suhr, Yejin Choi, Yulia Tsvetkov。
- 问题：LLM 开箱即用的 ToM 能力不足；缩放不足以带来符号化信念推理。
- 方法：`SYMBOLICTOM`，解码时插件；从故事逐句构建多角色信念图（含 k 阶嵌套信念）；用 off-the-shelf NLI/OpenIE 抽三元组；不训练、不微调。
- 评测：ToMi 等多角色 false-belief 任务；多种基座模型（Macaw、GPT-3/3.5/4、Flan-T5、LLaMA）；与 zero-shot 及 memory 基线对比。
- 局限（论文自述）：假设故事按时间顺序书写；抽取依赖 off-the-shelf 模型，可能引入错误；主要面向阅读理解式问答。
- 与本项目关系：`B` 维“人物相信什么”的强参照；但它是**故事问答**，不是事件流上的状态滤波，也没有 `C/Q`。
- 不能宣称：首次做多角色信念跟踪、首次把符号结构用于 ToM。

### R10–R12（仅二手/元数据，未读原文）

- R10 Memory for Goals（Altmann & Trafton, 2002）：目标激活—衰减—线索恢复的认知模型。本轮只从 R4/R8/R9 与检索片段转引，**未读原文**；技术方案若要写公式，必须先读原文。
- R11 Spatial memory guides task resumption（2008, Visual Cognition）：题名与 DOI 已核实，摘要未读；只能作“存在该方向”的引用。
- R12 Recovering from an interruption: speed–accuracy trade-offs（2013, JEP Applied）：题名与 DOI 已核实，摘要未读；只能作背景引用。

## 2. 交叉结论（可直接写进 Related Work）

1. **“中断后状态更新”已有专门基准**（EchoChain、DuplexLedger），但对象都是 agent 自身状态/记忆，不是外部观察者对人物六因子的推断。
2. **“心智世界模型”已有框架与实现**（MWM/MENTIS、MMEA），但都不做“中断后是否恢复、恢复到哪一步”的步骤级预测。
3. **“目标生命周期/恢复契约”已有形式化与工程化**（BDI 2008、GODR），但都是从 agent 内部管理目标，不是从外部证据推断。
4. **“信念跟踪”已有强方法**（SymbolicToM、SIPS），但缺少承诺—进度—恢复位置的联合状态。
5. 本项目可主张的差异只能收窄为：**外部观察者 + 认知可达性门控 + V/F/A/B/C/Q 联合滤波 + T1/T2 步骤级恢复预测**的组合；任何单项都不能称“首次”。

## 3. 仍需 B 本人做的核对

- 抽查 R1–R9 的关键数字（本文件已标来源节），确认没有转述误差。
- 读 R10 原文，确认“激活—衰减”公式与线索机制，再决定是否在技术方案里写公式。
- 给 R11/R12 补摘要或全文，否则只保留题名级引用。
- 读完后把本文件与 [competitor_matrix.md](competitor_matrix.md) 的等级同步升级。
