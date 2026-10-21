# 标注质量方案 v0.1

**项目：** ECR-MWM
**日期：** 2026-10-20
**Owner：** B
**适用对象：** P0 脚本诊断集、后续 P1 真实行为数据
**配套：** `schema/p0_record.schema.json`、`docs/annotation/annotation_handbook_v1.0.md`、`scripts/validate_data.py`、`scripts/pair_diff_report.py`

---

## 0. 先回答 A 的担心

A 说得对：**标签噪声会直接变成指标上限**。但“标签噪声”要拆成两类，不能用同一套办法处理：

| 数据类型 | 噪声主要来源 | 质量手段 | 能不能用 Cohen's kappa |
|---|---|---|---|
| P0 脚本诊断集 | 脚本设计错误、事件漏写、A/B 对照不干净、未来泄漏 | Schema 校验、证据链、逐字段 diff、人工审计、P07 输入一致性 | 基本不需要；不是人工标注 |
| P1 真实行为数据 | 标注者理解不一致、证据不足、主观推断、标注漂移 | 双人独立标注、校准集、仲裁、逐因子一致性、`UNKNOWN` 规则 | 需要，且要报告 |

**当前 16 条是 P0，不是 P1。** 它的质量目标是“脚本逻辑自洽、对照变量干净、证据链完整”，不是“两个标注者达成一致”。P1 才开始承担人工标注一致性。

---

## 1. 三类标签噪声与本项目的具体风险

### 1.1 定义噪声

标签定义本身有歧义，不同人按不同理解标注。

| 风险 | 例子 | 防线 |
|---|---|---|
| 把客观事实复制成人物信念 | 后台取消 → 直接标 `B=BELIEVES_INVALID` | P01 反例 + 硬约束 1 |
| 把接触当理解 | 人物读了通知 → 直接标 `B=BELIEVES_INVALID` | P08 反例 + 硬约束 2 |
| 把暂停当放弃 | 人物被电话打断 → 标 `C=ABANDONED` | P05 反例 + 硬约束 4 |
| 把主观步骤当客观最优 | 直接用任务图下一个未完成步骤填 `Q` | P04-B 反例 + `Q` 定义 |
| 把未知当删失 | 没观察到结果 → 标 `not_resume` | 硬约束 5 + P1 删失规则 |

### 1.2 执行噪声

定义清楚，但标注过程出错。

| 风险 | 例子 | 防线 |
|---|---|---|
| 漏事件 | 没记录“人物看到工具缺失” | 事件词表 + 关键事件清单 |
| 截断点错误 | `observed_events` 混入 `t` 之后的事件 | 校验器强制 cutoff 是最后一条 |
| 证据错配 | 标签写了，但证据 ID 指向别的事件 | 逐因子证据 + 校验器 |
| 标注者漂移 | 前 50 条一个标准，后 50 条另一个标准 | 校准集 + 定期复核 |
| 单人主观补全 | 没有自述也硬标 `B` | `UNKNOWN` 规则 + 双人标注 |

### 1.3 结构噪声

数据划分或对照设计造成的假象。

| 风险 | 例子 | 防线 |
|---|---|---|
| A/B 对照不干净 | 两版同时改了“是否看到通知”和“工具是否可用” | 逐字段 diff + 人工审计 |
| 未来泄漏 | P07 两版截断前输入不同 | P07 输入一致性自动检查 |
| 家族泄漏 | 同一故事的 A/B 分到训练和测试 | 按 `base_story_id` 分组划分 |
| 模板泄漏 | 测试集只是训练集换词 | 模板外表达 + 未见场景 |
| 标签分布退化 | 90% 都是 `VALID/READY` | 分层覆盖 + 分布报告 |

---

## 2. P0 的质量门（当前批次立即执行）

### Gate 0：Schema 校验

- 100% 记录通过 `schema/p0_record.schema.json`。
- 必填字段、枚举、事件词表、`additionalProperties` 全部强制。
- 命令：`python scripts/validate_data.py`

### Gate 1：证据链

- 每个非 `UNKNOWN` 标签至少一个证据事件。
- `B=UNKNOWN` 不带正证据。
- 证据事件必须存在于 `observed_events`，且 `<= cutoff`。
- `state_evidence_event_ids` 必须等于逐因子证据的按序并集。

### Gate 2：A/B 对照隔离

- 逐字段 diff，确认每对只改设计规定的那一个变量。
- P07-A/B 截断前输入必须完全一致。
- 命令：`python scripts/pair_diff_report.py`
- 人工看 diff 报告，重点确认：
  - 没有多改一个“顺手”的字段；
  - 没有把 `B/C/Q` 的差异直接写成事件差异；
  - P06 的嵌套任务状态差异没有污染父目标标签。

### Gate 3：人工审计

- 当前 16 条：B 100% 审计。
- 后续每批：B 100% 看 diff 报告 + 随机抽 20% 逐条读事件。
- 审计只看四件事：
  1. 事件是否足以支持标签；
  2. 有没有“人物不可能知道”的信息被写进 `B`；
  3. A/B 差异是否只有设计变量；
  4. `Q` 和 `expected.first_step` 是否混淆了主观/客观。

### Gate 4：第二人盲审

- 当前批次请 A 或 C 盲审 8 条（每对抽 1 条），只给事件和任务图，不给标签。
- 让第二人独立标 `V/F/A/B/C/Q`，与 B 的标签比对。
- P0 不要求高 kappa，但第二人能发现“定义歧义”和“事件不足”。
- 发现分歧 → 改手册/改事件，不是强行说服对方。

### Gate 5：脚本策略一致性

- `p0_expected_action` 必须能由 `p0_scripted_policy` + 当前状态推出。
- 检查反例：
  - P01-A：已知取消却恢复？错。
  - P05-B：工具缺失却执行？错。
  - P06-B：嵌套任务未完成却回父目标？错。
  - P07：两版输入相同却预测不同？错。

### Gate 6：版本冻结与变更记录

- 每批数据带 `schema_version`、`annotation.status`、日期、变更说明。
- Schema 一改，旧数据必须重跑校验；不能“新 Schema 套旧数据”。
- 交接给 A 的批次必须是冻结版本，不能一边训练一边改字段。

---

## 3. P1 的质量体系（真实数据阶段）

### 3.1 标注前

1. **标注者培训：** 用 P0 样例做练习，确保理解 `V/F/A/B/C/Q` 的分离。
2. **校准集：** 先标 30–50 条，双人独立标，计算一致性；不达标不进全量。
3. **冻结手册：** 校准后冻结 v1.0；后续改动必须版本化并重标受影响样本。
4. **盲标：** 第一轮标注者互不看对方结果，也不看模型预测。

### 3.2 标注中

1. **双人独立标注：** `V/F/A` 和可观察步骤建议 100% 双标；`B/C/Q` 至少对高风险样本双标。
2. **证据逐条记录：** 每个非 `UNKNOWN` 标签写证据事件 ID。
3. **`UNKNOWN` 优先：** 没有自述、明确行动或可核查间接证据时，不硬标 `B/C/Q`。
4. **分歧不讨论：** 第一轮结束后再进入仲裁，避免互相污染。
5. **抽样复核：** 每周随机抽 10% 已标样本，由第三人复核，监控漂移。

### 3.3 标注后

1. **仲裁：** 第三人根据手册和证据裁决；记录裁决理由；无法裁决的标 `UNKNOWN` 或移出训练集。
2. **一致性统计：** 逐因子报告 agreement 和 kappa/alpha，不只报总体。
3. **错误分析：** 抽样看分歧样本，归类为“定义问题/事件不足/标注者疏忽/真实歧义”。
4. **噪声上限：** 用双人一致的高置信子集估计 noise ceiling，告诉 A“这个标签上人类能到多少”。
5. **数据卡：** 记录 n、双标比例、一致性、`UNKNOWN` 比例、删失比例、已知限制。

### 3.4 一致性指标与建议阈值

> 阈值不是法律，是行动触发器。类别不均衡时，percent agreement 会虚高，必须同时看 kappa/alpha。

| 因子 | 指标 | 建议目标 | 低于目标怎么办 |
|---|---|---|---|
| `V` | Cohen's κ / Krippendorff's α | ≥ 0.70 | 0.60–0.70 人工复核；<0.60 改定义/重标校准集 |
| `F` | 同上 | ≥ 0.70 | 同上 |
| `A` | 同上 | ≥ 0.70 | 同上 |
| `C` | 同上 | ≥ 0.60 | 0.50–0.60 复核；<0.50 改手册 |
| `B` | 同上 | ≥ 0.60 | 主观性强，允许较低；低置信样本掩码/加权 |
| `Q` | 同上 + 步骤准确率 | ≥ 0.60 | 检查任务图/主观进度定义 |
| 事件抽取 | 事件类型/step 的 agreement | ≥ 0.80 | 补事件词表、补关键事件清单 |

**报告原则：**

- 报告 `n`、双标比例、每个因子的分布、`UNKNOWN` 比例。
- 不要只报一个总体 kappa 掩盖某个因子的低一致性。
- 低一致性不是“标注者不行”，往往是“定义不够可操作”或“证据不足”。

### 3.5 双标比例与成本

不必 100% 全量双标。按风险分层：

- **100% 双标：** 校准集、gold set、所有 `B/C/Q` 非 `UNKNOWN` 样本、所有边界案例。
- **20–30% 随机双标：** 常规 `V/F/A` 和可观察步骤，用于估计整体一致性。
- **100% 第三人复核：** 仲裁样本、低置信样本、模型错误集中的样本。
- **AI 预标注：** 只能做初稿，必须由人复核；AI 不能作为 P1 的唯一标注者。

---

## 4. 给 A / C 的质量报告

这一页由脚本从数据实算，不要手填数字：

```bash
python scripts/p0_quality_report.py
```

它对 `validate_data.DATA_FILES` 里的每个文件（v0.1 的 16 条、v0.2 的 240 条与 v0.3 的 14 条候选）输出规模、校验结果、证据覆盖、悬空引用、cutoff 完整性、P07 输入一致性、域/划分分布、SHA256，以及**逐枚举的"schema 声明过 vs 数据用过"对照**；最后一段会把同一 `schema_version` 的批次合并统计，这样"某个取值仍没人用"不会被"它只在一个文件里为 0"这种单文件口径掩盖。

两条口径要记住：

- `human_audit` 直接读 `annotation.status`，没人签就永远不会变成 240/240；`B` 自审完成的 `reviewed` 不等于 `adjudicated`。
- `second_reviewer`（A/C 盲审）没有数据字段可依据，脚本恒为 `not recorded`，只能由 A/C 本人声明后另行记录。**任何人不得替他人勾选。**

### v0.2 的覆盖度短板（2026-10-20 实测）

240 条 / 120 家族 / 1831 事件全部通过校验，但 schema 声明的取值里有 **12 个一次都没出现过**。其中 11 个几乎全是承载不确定性的取值，另外 1 个是 C 的交接协议要求的 `calibration` 划分：

| 字段 | 声明的取值 | 数据里为 0 的 |
|---|---|---|
| `state.A` | ACCESSED / NOT_ACCESSED / UNCERTAIN | **UNCERTAIN** |
| `event.person_access` | 同上 | **UNCERTAIN**（1797 / 34 / 0） |
| `event.person_comprehension` | UNDERSTOOD / MISUNDERSTOOD / NOT_UNDERSTOOD / UNCERTAIN / NOT_APPLICABLE | **NOT_UNDERSTOOD、UNCERTAIN** |
| `event.certainty` | CERTAIN / PROBABLE / UNCERTAIN | **PROBABLE、UNCERTAIN**（1831 条全是 CERTAIN） |
| `state.V`、`state.F` | 各含 UNKNOWN | **UNKNOWN** |
| `state.B` | 含 UNRESOLVED | **UNRESOLVED** |
| `state.C` | 含 ACTIVE、UNKNOWN | **ACTIVE、UNKNOWN** |
| `split` | train / dev / calibration / test | **calibration**（144 / 48 / 0 / 48） |

`split.calibration` 为空不只是覆盖率问题：C 的 `schema/模型交接协议.md` 要求每条记录带 train/dev/calibration/test 四档，当前 240 条只给出三档，锁版本前必须和 C 确认是补划档还是改协议。

这正是 A 在 `A_P0_CHECK_REPORT.md` 里点名的"缺少 UNCERTAIN 接触和完整状态覆盖"。**规模目标达成 ≠ 机制覆盖达成**：滤波器在这份数据上学不到"接触不确定""理解不可判定""证据只是大概"这几档，而它们恰好是本项目要建模的东西。下一批的靶子按这张表补，不要再按家族数凑量。

v0.1 的 16 条是冻结基线，短板相同（`A.UNCERTAIN`、`person_access.UNCERTAIN`、`F.UNKNOWN` 为 0），保留不动。

### v0.3 批次补上 11 个不确定性档位（2026-10-21 实测）

`scripts/build_p0_uncertainty.py` 生成 7 个新家族 / 14 条 / 77 事件（`data/p0/p0_samples_v0.3.json`，仍用 `p0-record/v0.2.0`），逐档实测：

| 档位 | v0.2 | + v0.3 | 由哪个家族承载 |
|---|---:|---:|---|
| `state.A.UNCERTAIN` | 0 | 1 | P01-W6-A（投递无回执） |
| `event.person_access.UNCERTAIN` | 0 | 1 | 同上 |
| `event.certainty.UNCERTAIN` | 0 | 2 | P01-W6-A、P01-W8-A |
| `event.certainty.PROBABLE` | 0 | 1 | P01-S6-A（主管口头转述） |
| `state.B.UNRESOLVED` | 0 | 1 | P01-S6-A（两条矛盾通知未调和） |
| `state.F.UNKNOWN` | 0 | 1 | P05-D6-A（设备状态不可观察） |
| `event.person_comprehension.NOT_UNDERSTOOD` | 0 | 1 | P08-W7-B（收到但没看懂） |
| `event.person_comprehension.UNCERTAIN` | 0 | 4 | P08-S7-B、P01-W6-B、P01-S6-A、P01-W8-A |
| `state.C.ACTIVE` | 0 | 1 | P02-D7-A（承诺 + 保护材料的持续行动） |
| `state.C.UNKNOWN` | 0 | 1 | P02-D7-B（无承诺也无放弃的证据） |
| `state.V.UNKNOWN` | 0 | 1 | P01-W8-A（只有一条未确认的转述，世界事实未定；仍有点标签） |

合并两个批次后，`p0_quality_report.py` 的"声明过但从未使用"只剩 **1 个：`record.split.calibration`**，那仍是 C 的协议决定，不由 B 单方面补。

**这一批已验收：** B 于 2026-10-21 逐对复核 [`p0_spot_audit_v0.3_all7.md`](p0_spot_audit_v0.3_all7.md)（7 对 / 28 个复选框，结论全部"通过"），`annotation.status` 升 `reviewed`。这些 `UNKNOWN` 是脚本设计的认识处境，"设计得是否真的可判"由 §1.4 那条判据（能否指名 cutoff 之前缺的是哪一条证据）第一次成批检验，结论是可判。**签核的仍是 B 自己**，A/C 盲审没做，所以它进不了 `adjudicated`，也不能对外宣称双人复核。

标签口径全部按 v0.2 已有惯例写，没有为这批新造规则：`p0_scripted_policy` 与机制 1:1（受 Gate 5 约束，`p0_expected_action` 必须能由政策 + 状态推出），理解不到位的一臂与 v0.2 的 15 个误解臂同为 `suspend_or_wait`，`indeterminate` 仍只给输入不可区分的家族。三处由 B 在复核时明确认可（2026-10-21）：

1. P01-W8-A 的 `V=UNKNOWN` **不等于**没有点标签——政策看的是"有没有已知取消"，答案是没有，所以期望动作是 `resume_build_summary`。若把它写成 `indeterminate`，就是把"世界事实未定"和"标签未定"混成一件事。
2. P01-S6 两臂期望动作同为 `do_not_resume`：这对操控的是信念是否调和（`UNRESOLVED` vs `BELIEVES_INVALID`），动作维度刻意保持常量。v0.2 的对照对里两臂动作总是相反的，这是第一批动作不反转的对。
3. 7 对里有 4 对（P01-S6 / P05-D6 / P02-D7 / P08-S7）A/B 事件条数不等。v0.2 把条数对齐是机器预检的前提，但这里操控变量本身就是"多/少一条证据事件"，补中性事件反而会污染 `pair_diff_report.py` 的读数。

口径与 A 对齐：A 在 2026-10-21 写入 `docs/internal/a/A_ALGORITHM_DECISIONS.md` 的"长期约束"段把 `UNRESOLVED` 定义为"有证据表明人物暂时无法判断"、`UNKNOWN` 定义为"观察者缺乏足够证据"，本批按这个区分写——P01-S6-A 的 `B=UNRESOLVED` 有人物自述"到底是撤还是不撤"撑着，P01-W6 的 `B=UNKNOWN` 一条证据都没有；A 的例二（收到但误解通知、信念仍可维持有效）对应 P08-W7-B。A 同一段还确认了"v0.2 已入库但尚未接入 A 适配器"，这条以前是 B 单方面的推测，现在是 A 自己记的决定，接入验收由 A 侧推进。

P1 阶段再加：

```text
double_annotated: n / N (%)
per_factor_agreement: V=..., F=..., A=..., B=..., C=..., Q=...
per_factor_kappa/alpha: ...
adjudication_rate: ...
unknown_rate: ...
censored_rate: ...
gold_set_accuracy: ...
label_distribution: ...
known_issues: ...
```

---

## 5. A 应该怎么用这些质量信息

1. **P0 只做逻辑/泄漏诊断。** 不要把 P0 指标写成真实人类预测能力；不要把 P0 的 `p0_expected_action` 当 P1 行为标签。
2. **P1 训练时区分置信度。** 高置信子集用于主评估；低置信/`UNKNOWN` 样本做掩码或降权，不要硬训。
3. **报告 noise ceiling。** 如果人类一致性只有 0.7，模型在测试集上 0.95 的准确率很可能是在拟合标注噪声或泄漏。
4. **要求按因子报告。** 不要只看总体 resume F1；`C`、`Q`、`A` 的低质量会被总体指标掩盖。
5. **保留逐样例证据。** 模型错时，B 能回溯是标签错、证据不足，还是模型错。

---

## 6. 可直接回复 A 的话术

> A，你说得对，标签噪声会直接压住指标上限。我的质量策略分两层：
>
> 1. **P0 是脚本数据，噪声主要不是标注者分歧，而是脚本设计/事件不全/未来泄漏。** 当前 16 条已经过了 Schema、证据链、cutoff、P07 输入一致性校验；我再用逐字段 A/B diff 做一遍对照审计，并把审计结果随数据一起给你。P0 的指标只用于逻辑/泄漏诊断，不作为真实人类预测能力。
> 2. **P1 才是人工标注噪声的主战场。** 我会做标注者培训 + 校准集 + 双人独立标注 + 第三人仲裁；逐因子报告 agreement 和 Cohen's κ/Krippendorff's α，而不是只报总体。没有证据的 `B/C/Q` 保持 `UNKNOWN`，不硬标；同时给你 noise ceiling，避免你追一个超过人类一致性的指标。
> 3. **低置信标签的用法你定：** 可以做 mask、降权，或只在高置信子集上评估。需要我在 Schema 里加 `label_confidence`/`adjudication` 字段的话，我先出 v0.2 草案，不直接改现有数据。
> 4. **请你先确认 Schema 接口**（`task_dependencies`、`completed_steps_at_cutoff`、`p0_expected` 等扩展）。确认后我再批量扩 P0，避免字段一改全部返工。

---

## 7. 当前批次状态与下一步

### 已完成

- 16 条 P0 记录通过 Schema + 跨字段校验。
- v0.2 批次 240 条 / 120 家族 / 1831 事件通过 Schema + 跨字段校验，`mechanism` 八档全覆盖，`split` 只落了三档（`calibration` 为空）。
- 逐字段 A/B diff 报告已生成；P07 输入一致性 PASS。
- 六因子定义、证据规则、易错点已写入标注手册。

### 待完成

- [x] **抽查 B 的自审结论。** [`p0_spot_audit_v0.2_seed20261021.md`](p0_spot_audit_v0.2_seed20261021.md)（10 对 / 20 条，机制各 1 对 + `sha256("20261021:家族名")` 排序补齐，39 个复选框）已由 B 于 2026-10-21 全部勾为通过。**这仍然只是 B 的自审**，不是第二双眼睛；对外表述只能是"B 复核 + B 抽查签核"，A/C 盲审见下一项。要换样本用 `python scripts/audit_packet.py --seed <新值> --out <新文件>`，旧签核不复用。
- [x] **复核 v0.3 的 7 对不确定性批次并升到 `reviewed`（2026-10-21 完成）。** 11 个"声明过但从未出现"的档位（`A.UNCERTAIN`、`person_access.UNCERTAIN`、`person_comprehension.{NOT_UNDERSTOOD,UNCERTAIN}`、`certainty.{PROBABLE,UNCERTAIN}`、`V/F.UNKNOWN`、`B.UNRESOLVED`、`C.{ACTIVE,UNKNOWN}`）已由 `scripts/build_p0_uncertainty.py` 覆盖。全批 7 对的签核表 [`p0_spot_audit_v0.3_all7.md`](p0_spot_audit_v0.3_all7.md) 的 28 个复选框已全部勾为通过，上面那三点也逐条认可，批次升 `reviewed`（`annotator_id=B`、`reviewed_at=2026-10-21`）。这是 A 点名的缺口，现已关闭，下一步换成 A/C 盲审。
- [ ] **和 C 定 `split.calibration`。** C 的交接协议要四档，v0.2 只给了 train/dev/test；要么按家族重划出一档 calibration，要么由 C 改协议。锁版本前必须三方确认，B 不单方面改字段。
- [ ] A/C 盲审 8 条（A、C 各 4 条，每机制抽 1 条），只给事件与任务图，记录分歧。
- [ ] 根据分歧改手册/事件，不强行说服。
- [x] `annotation.status` 从 `draft` 改为 `reviewed`（v0.2 已改，B 自审；v0.1 的 16 条保持 `draft`，作为 A 适配器的冻结基线）。
- [x] 随数据给 A / C 一页质量报告（`python scripts/p0_quality_report.py`，实算，不手填）。
- [x] 批量扩到 120 家族 / 240 条（v0.2 已交付；A 的 v0.2 适配器与 schema 确认仍待完成）。

### P1 启动前

- [ ] 确定数据许可与伦理流程。
- [ ] 写 P1 标注手册增补版（时间戳、删失、视频/日志证据）。
- [ ] 建 30–50 条校准集。
- [ ] 计算首轮一致性；不达标不扩量。

---

## 8. 需要团队确认的决策

1. **P1 双标预算：** `V/F/A` 全量双标，还是 20–30% 抽样？`B/C/Q` 是否全量双标？
2. **一致性阈值：** 采用本文建议，还是团队另定？低于阈值时是重标、降权，还是移出训练集？
3. **`UNKNOWN` 的处理：** 掩码、单列未知类，还是只用于评估？
4. **Schema v0.2：** 是否增加逐因子 `label_confidence`、`adjudication`、`annotator_id`？这会增加标注成本，但能让 A 做置信度加权。
5. **P0 的用途：** 只做诊断，还是也参与状态模块的预训练？如果参与，必须明确不能报告真实人类预测能力。

---

## 9. 一句话总结

**P0 的质量靠“设计干净 + 证据完整 + 逐字段 diff”；P1 的质量靠“双人独立 + 仲裁 + 逐因子一致性 + 噪声上限”。** B 不承诺“标签绝对无噪声”，但承诺“噪声可见、可度量、可追溯，并且不把 P0 的干净误当成 P1 的真实”。
