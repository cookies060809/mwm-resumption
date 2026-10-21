# 可用外部数据集核查（P1 之前的替代与补充）

> **Owner：** B（数据与认知机制）｜**版本：** v0.1｜**日期：** 2026-10-21
> **用途：** 判断能否在 P1 自采之前，用公开数据支撑 T1/T2 或恢复代价的外部验证；同时给 A/C 一份可引用的边界说明。
> **原则：** 只记录能核实到字段级的内容。凡未亲自下载统计的，标注「依据官方 schema」，不写成已验证。

## 0. 结论

**没有可以直接替代 P1 的公开数据。** 但有两个能派生出真实可用的信号，按优先级：

| 优先级 | 数据集 | T1（是否恢复） | T2（恢复步骤） | A（可及性） | 关键优势 | 主要限制 |
|---|---|---|---|---|---|---|
| **1** | **HoloAssist** | **不可用**（98.8% 都是恢复，负例仅 92 个） | **可用**（3,929 例有明确恢复点） | **可用**（清洗后 3,944 vs 1,135，配平 1,135/侧） | A 因子的真实行为证据；标注 117 MB 免申请直连 | 是 *error-recovery*，不是 *interruption-resumption*；有转写泄漏风险 |
| **2** | **InteRead** | **不可用**（中断后 100% 继续读） | 部分（恢复到哪个词） | 无 | **唯一原生标注 interruption + resumption lag**；ICC 0.916 | T1 无变异；恢复是连续时间不是离散步骤 |
| 3 | Assembly101 | 弱 | 可用（`correction` 段） | 无 | 顺序错误 + 纠正 | CC BY-NC + HF gated，全量 3.89 TB |
| 4 | Ego4D Goal-Step | 不能 | 能（goals→steps→substeps） | 无 | 标注 MIT 许可、免申请 | 无中断、无恢复 |
| — | RFM-HRI | 不能 | 不能 | 不能 | 仅 Related Work 对照 | 标签是机器人恢复策略偏好 |

**实测后必须修正的一个预期：** HoloAssist 看起来"有正例也有负例"，实际正负比是 **7,113 : 92**（77:1）。直接把 T1 建成二分类会得到 98.8% 的朴素基线，没有区分力。它的价值在 **A 因子**与 **T2**，不在 T1。

**对竞赛的直接含义：** 三层证据各自负责一件事，不要混用——

| 要证明的东西 | 用哪份数据 |
|---|---|
| T1 的对照可判别性 | P0（240 条，A/B 严格对照） |
| **A 因子的真实行为效应** | **HoloAssist（被言语纠正 vs 自主纠正）** |
| 恢复有代价、不是二值 | InteRead（resumption lag，2.81 s 均值） |
| T2 步骤级可行性 | HoloAssist（3,929 例）+ P0 |

派生数据必须显式标为 derived，不能暗示自采。

## 1. HoloAssist（首选）

**来源：** Wang, Kwon, Rad 等，*HoloAssist: an Egocentric Human Interaction Dataset for Interactive AI Assistants in the Real World*，ICCV 2023，Microsoft Research。

| 项目 | 内容 |
|---|---|
| 规模 | 169 小时；2,221 会话；350 组 instructor–performer 配对 |
| 场景 | 维修与操作（打印机、相机、咖啡机、Switch、宜家家具、电路等 11 类） |
| 许可 | **CDLA-Permissive-2.0**（宽松，允许商用与再分发，需署名） |
| 标注文件 | `data-annotation-trainval-v1_1.json`，**117,011,015 bytes**，直连可下 |
| 是否需要申请 | **不需要**。`https://hl2data.z5.web.core.windows.net/holoassist-data-release/data-annotation-trainval-v1_1.json` |
| 视频 | 184 GB（pitch shift）/ 145 GB（压缩）——**标注级实验不需要下载视频** |
| 划分 | `data-splits-v1_2.zip`（官方 train/val/test） |

### 1.1 标签结构（决定能否派生）

四类标注段，均为 `{id, label, start, end, type:"range", attributes}`：

| 段类型 | 关键属性 | 对本项目的用处 |
|---|---|---|
| `Narration` | `Long-form description`（整段视频一句话概括，含"自我纠正或被指导者纠正"的描述） | 会话级上下文 |
| `Conversation` | `Conversation Purpose`（含 `Correct the wrong action`）、`Transcription`、`Transcription Confidence` | **A 因子的来源**：人物是否收到了言语纠正 |
| `Fine grained action` | `Action Correctness`、`Incorrect Action Explanation`、`Incorrect Action Corrected by`、`Verb/Adjective/Noun/adverbial` | **T1/T2 与步骤序列的主来源** |
| `Coarse grained action` | `Action sentence`、`Verb/Adjective/Noun` | 目标层级 |

`Action Correctness` 的五个取值（**以下为实测值，与官方 README 文字不完全一致**）：

```
Correct Action                                      141,691   94.9%
Wrong Action, corrected by instructor verbally        4,052    2.7%   ← 有外部言语提示后恢复
Wrong Action, corrected by student                    3,061    2.1%   ← 无外部提示，自主发现并恢复
otherwise                                               357    0.2%
Wrong Action, not corrected                              92    0.1%   ← 严格负例
```

> **踩坑记录：** 官方 README 写的是 `Wrong action, corrected by performer`，实际字段值是 **`Wrong Action, corrected by student`**（`Action` 大写 A、`student` 而非 `performer`）。按文档字符串过滤会得到 0 条。同理 `Conversation Purpose` 实际是小写连字符形式 `instructor-start-conversation_correct the wrong action`（3,019 条），不是 README 里的 `Correct the wrong action`。**任何按字面量匹配的代码都必须用实测值。**

### 1.1b 实测统计（2026-10-21，trainval v1.1 全量）

| 指标 | 数值 |
|---|---|
| 会话数 | **1,758**（官方称 2,221，差额在 test 部分，本文件为 trainval） |
| 任务类型 | 20 类；最多 `setup switch` 143、`setup camera` 135、`setup gopro` 134 |
| 标注段总数 | 1,758 Narration / 32,392 Conversation / 12,542 Coarse / **149,253 Fine grained action** |
| 错误案例合计 | **7,205**（4,052 + 3,061 + 92） |
| **T1 正负比** | **7,113 : 92 ≈ 77 : 1**（朴素全猜"恢复"= 98.7%） |
| 被言语纠正案例中，±40 s 内有对话 | 4,046 / 4,052 = **99.9%** |
| 其中转写非空且可读 | 4,045 / 4,052 = **99.8%** |
| 错误后同动作再次出现且正确（可定 T2 恢复点） | 3,929 / 7,205 = **54.5%** |
| **A 对照：access 严格组**（窗口内出现 `correct the wrong action`） | **3,944** / 4,052 |
| **A 对照：self 干净组**（窗口内**无任何**指导者发言） | **1,135** / 3,061 |
| 可配平对照量 | **每侧 1,135，共 2,270** |

**三条解读：**

1. **T1 不可用。** 77:1 的不平衡来自数据采集本身——指导者在场，几乎每个错误都会被纠正。降采样正例可以让训练可行，但负例只有 92 个，做不出可用的测试集。**不要用它做 T1。**
2. **A 因子可用，但必须先清洗。** 未清洗的 `corrected by student` 组里有 **62.9%** 处在指导者发言窗口内，直接当成"自主发现"是把"被提示"误记成"自己发现"。清洗后 3,944 vs 1,135，配平后每侧 1,135 例 —— 不够大，但做一次 A 的单因素对比够了。
3. **T2 可用但只覆盖一半。** 54.5% 的错误后能定位到"同动作重做且正确"的恢复点。剩下 45.5% 不能当负例——其中多数是用别的动作绕过去完成了目标，需要人工抽检后才能定性。

### 1.1c 一个必须防的标签泄漏

清洗后出现新的结构性差异：**`access` 组有转写，`self` 组没有**（因为干净的定义就是"窗口内无指导者发言"）。于是"输入里有没有文本"直接等于标签，任何模型都能用这个特征拿到接近满分。

**三条防护，缺一不可：**

1. 输入侧对两组一致处理——要么都只给动作序列 + 物体状态，要么把转写作为**单独消融项**（有文本 / 无文本）分别报告，不能混在一个模型里。
2. 评测报告必须给出"有文本 vs 无文本"两组数字，差值才是 A 的真实效应。
3. 抽检时专门看 self 组：确认这些案例里人物确实只能靠观察发现（而不是指导者刚说完话但被 40 s 窗口漏掉）。

> 这类泄漏和 P0 的 P06 问题是同一类：**标签从输入里可读出**。P0 里我们靠"嵌套状态须由事件推断"解决，这里要靠"两组输入通道对齐"解决。

### 1.2 派生规则（建议实现，仅限 A 与 T2）

| 本项目字段 | 派生方式 | 实测可行性 |
|---|---|---|
| `task_steps` | 同一 `Coarse grained action` 下的 `Fine grained action` 序列，按 `Verb+Noun` 归一化为 step id | 高（149,253 段可用） |
| `cutoff` | 某个 `Wrong Action` 段的 `end` 时刻 | 高 |
| `observed_events` | 截断前的 action 段 + 对应时刻的 `Conversation` 转写 | 高（转写覆盖 99.8%） |
| **A（可及性）** | `corrected by instructor verbally` **且**窗口内出现 `correct the wrong action` → `ACCESSED`（3,944 例）；`corrected by student` **且**窗口内无任何指导者发言 → 外部消息未介入（1,135 例） | **中**（清洗后可用，须防 §1.1c 泄漏） |
| **T2 `first_step`** | 错误之后第一个同 `Verb+Noun` 且 `Correct Action` 的 step id | **中**（覆盖 54.5%） |
| **T1 `resume`** | — | **不实现**，理由见 §1.1b 第 1 条 |
| **B（信念）** | 仅粗代理：`not corrected` 且后续继续推进 → 人物相信自己是对的（仅 92 例） | **低**，不得当监督信号 |

**建议的最小可用实验（而不是全量派生）：**

1. 只取 `corrected by instructor verbally` 与 `corrected by student` 两组，作为 A 的对照实验；
2. 控制任务类型与 `Verb+Noun` 分布后配对抽样（建议每侧 300–500 例），避免把"任务难度差异"误读成"A 的效应"；
3. 用 3,929 例中的一部分做 T2 的步骤级评测；
4. 全程不碰 T1。

**必须做的人工抽检：** 随机抽 50 例（每组 25），确认 ① 错误段结束时刻确实可以当作中断点；② 恢复点确实是"重做同一动作"；③ `corrected by student` 的案例里确实没有指导者插话。抽检结论写进数据卡。

### 1.3 必须写进论文的限制

- 这是 **error-recovery（做错→纠正）**，不是 **interruption-resumption（被别的事打断→回来继续）**。两者共享"目标未完成—回到原任务"的结构，但触发源不同，不能声称等价。
- 无中文，无中文场景。
- 无人物主观状态的原生标注，V/F/A/B/C/Q 全靠派生，**只有 A 有可用的行为代理**。
- 派生标签必须做人工抽检（建议 50 例）后才能进实验；抽检结论要写进数据卡。

## 2. InteRead（唯一原生 interruption + resumption）

**来源：** Zermiani, Dhar, Sood, Kögel, Bulling, Wirzberger，*InteRead: An Eye Tracking Dataset of Interrupted Reading*，LREC-COLING 2024，University of Stuttgart。

| 项目 | 内容 |
|---|---|
| 规模 | 50 名被试；28 页英文小说；5,247 tokens |
| 中断设计 | 在 6 个页面的预定「目标词」处**自动触发**灰色对话框，强制 60 秒内回答观点问题 |
| 恢复标签 | **人工标注 resumption time**：`resumption_times_per_page.csv`（每人约 6 次）、`resumption_times_per_subject.csv` |
| 标注一致性 | **ICC = 0.916**（人工标注可靠性高，这是它的强项） |
| 其他数据 | fixation / saccade / regression（含 `interruption phase` 字段）、pre/post 认知分数、人口学 |
| 许可 | CC BY-NC-SA 4.0；OSF 公开（`https://osf.io/8wxfe/`），需同意许可条款 |
| 主要结论 | 平均恢复延迟 2.81 s（0.95–8.29 s）；中断后阅读时间从 22.33 s 升到 37.05 s |

### 2.1 能做什么、不能做什么

- **不能做 T1**：中断结束后被试必然继续阅读（任务要求），**没有"不恢复"的负例**，T1 恒为 `resume`，无区分力。
- **能做**：恢复**代价/延迟**的外部验证（把 `resumption_lag` 当作"恢复难度"的连续真值）；个体差异建模（50 人 + 认知分数）；"回到哪个位置"的弱 T2（回扫落点）。
- **对本项目的价值**：它是文献里少数把 resumption 当**因变量**测量并公开的数据。可用来支撑"恢复不是二值、而是有代价的过程"这一动机，也可作为 `T3` 中"主观进度滞后"的间接佐证。
- **限制**：单任务（阅读）、实验室、英文、无跨中断的多次恢复。

## 3. Assembly101（补充：顺序错误与纠正）

- 513 小时 / 53 人 / 101 个可拆装玩具车 / 12 视角；100K+ coarse、1M+ fine-grained action 段。
- **mistake detection 标注**（独立仓库 `assembly-101/assembly101-mistake-detection`）：标签为 `correct` / `mistake`（`wrong order`、`previous one is mistake`、`shouldn't have happened`、`wrong position`）/ **`correction`**。
- `correction` 段直接对应"恢复动作"；`wrong order` 对应"步骤顺序错误"，比 HoloAssist 更接近本项目 `task_dependencies` 的结构。
- 许可 CC BY-NC 4.0，HuggingFace gated（登录 + 同意条款 + 分享联系方式）；全量 3.89 TB，标注可用 `--include` 单独拉。
- **限制**：同 HoloAssist，是 error-correction；gated 与非商用许可在竞赛提交时要在数据来源里写清。

## 4. Ego4D Goal-Step（辅助：任务层级定义）

- NeurIPS 2023 D&B；goals → steps → substeps 三级嵌套，含 `is_continued`（该步骤是否从更早片段延续）。
- **标注为 MIT 许可，免申请**（视频需签 Ego4D 协议，中国大陆不在拒绝名单内）。
- 用途：给 `task_steps`/`task_dependencies` 的层级定义提供已发表的口径；`is_continued` 可作为"跨中断续接"的概念对照，但它表示的是视频分段续接，不是人物恢复。
- **无中断、无恢复标签**，不能做 T1/T2。

## 5. RFM-HRI（仅 Related Work，不作数据源）

结论见 [`../literature/competitor_matrix.md`](../literature/competitor_matrix.md) 的「HRI 失败恢复数据（2026）：能否替代 P1」一节。要点：

- 标签是**机器人恢复策略偏好**（问卷自评）+ 失败类型 + SAM 三维评分，**没有人物是否恢复、恢复到第几步**。
- 论文只承诺 "will be made publicly available"，**未给下载入口**，DOI 为占位符，需邮件询问作者。
- 不下载、不申请、不作训练或验证数据。

### 5.1 关于「RFM-HRI 是唯一给到可及性+信念证据的」这一说法

**不成立，需纠正两处：**

1. **它不是「可及性」证据。** 它的 `perceived control` 是 SAM 量表里"感到可控"的主观评分，属于情绪维度；本项目的 `A`（person_access）指"某条具体信息是否送达并被人物接触"，是事件级二值/三值标注。两者构念不同，不能互替。
2. **它不是「信念」证据。** 它没有任何关于"人物认为任务处于什么状态"的标注，无法支撑 `B`。
3. **"唯一"也不成立。** HoloAssist 的 `corrected by instructor verbally` vs `corrected by student` 提供了 A 的事件级可观测代理，清洗后 3,944 vs 1,135 例，且有转写作为"人物能获得什么"的文本证据。它同样没有 B，但在 A 上明显强于 RFM-HRI 的 `perceived control` 评分。

**可以直接做一次对照：** RFM-HRI 的 `perceived control` 是**事后**问"你觉得可控吗"，HoloAssist 的 `corrected by` 是**过程内**标"谁发现了错误"。前者是自评情绪，后者是行为归属——后者才是 A 需要的证据类型。

> 结论：那句话如果写进方案或发给 A/C，会在评审或组内讨论中被直接质疑。**不要采用。**

## 6. 处理与标注的责任边界

回答「数据集是不是要我来处理和标注」：**处理和派生是你的活，人工标注只有三处必须人做。**

| 环节 | 谁做 | 说明 |
|---|---|---|
| 许可确认、来源登记 | **B** | 把许可、URL、SHA、下载日期写进数据卡；这是提交材料的必备项 |
| 格式转换（→ 本项目 schema） | **B** | 写 `scripts/` 下的 adapter，与 `export_eval_format.py` 同构 |
| **派生标签（T1/T2/A 代理）** | **B** | 脚本推导，**不需要重新标注原始数据**——这是关键：HoloAssist 的 action / correctness / correction 都是现成的，你做的是映射，不是重标 |
| 派生质量抽检（如 50 例） | **只能人做** | 脚本无法判断"这个恢复点是否合理"，必须人眼确认；结论写进数据卡 |
| 划分（按会话/受试者隔离） | **B** | 与 P0 相同的纪律：同一会话不跨 split |
| 校验与回归测试 | **B** | 扩到 `tests/`，保持 `validate_data.py` 覆盖新批次 |
| P1 自采原始标注 | **只能人做** | 采集 + 双人标注 + 仲裁，不能由脚本或 AI 代签 |
| 双人盲审 / 仲裁 | **只能人做** | 关系 `annotation.status` 从 `reviewed` 升 `adjudicated` |

**一句话：** 公开数据集省掉的是「采集」，不是「处理」。真正省不掉的仍然是 P1 的采集与盲审。

## 7. 建议的下一步

1. **已做：** 可行性实测完成，脚本 `scripts/probe_ext_holoassist.py` 可复现全部数字：

   ```bash
   python scripts/probe_ext_holoassist.py --anno /path/to/anno.json
   python scripts/probe_ext_holoassist.py --anno anno.json --export pairs.jsonl --per-group 1135
   ```

2. **待做：** 50 例人工抽检（两组各 25），重点看 self 组是否真的没有外部提示、错误点是否能当中断点。抽检表可仿 `docs/annotation/p0_pair_review_table.md` 的格式。
3. 抽检通过再写 adapter（`scripts/build_ext_holoassist.py`），产物单独放 `data/external/`，**不并入 P0 的 240 条**，并在 `annotation` 里写 `derived_from=holoassist`。
4. InteRead 仅用于「恢复代价」讨论，不进主实验。
5. 数据卡单列一节「外部派生数据」，写清 derived 字样、许可（CDLA-Permissive-2.0）与清洗规则。
6. **不要**把 HoloAssist 的派生结果表述为「真实人类中断恢复数据」——它是错误纠正数据，准确表述是 "error-correction traces used as a proxy for recovery"。

## 8. 版本

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.1 | 2026-10-21 | 首版：HoloAssist / InteRead / Assembly101 / Ego4D Goal-Step / RFM-HRI 核查，含派生规则与责任边界 |
