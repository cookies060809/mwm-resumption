# B 岗：三方对齐后的分工与待确认项

日期：2026-10-20｜Owner：B｜性质：内部协作记录，不作为竞赛提交材料

## 0. 事实基础

- A 分支 `origin/feat/a-ec-jmf-p0-adapter`（commit `45d31ec`）：`A_INTERFACES.md` 明确“A 的原暂定接口已按共享仓库实际 `p0-record/v0.1.0` 适配”“B 继续拥有 schema/数据”。即 **B 的 schema 已成为正式输入版本**，接口确认这一项对 B 已清。
- A 的适配器 `models/ecr_mwm/p0_adapter.py` 只读：`schema_version`、`task_steps`、`task_dependencies`、`observed_events`、`cutoff_event_id`、`horizon`、`goal_id`、`interrupting_task`（仅身份/父目标/steps）、`person_access`、`actor`。人物侧收到的是 `delivery.access_evidence` + 本人陈述，**外部消息内容不进人物输入**，`comprehension` 恒为 `not_structurally_labeled`。
- A 的回归测试 `tests/test_a_p0_contract.py` 断言：16 条、123 事件、P01–P08、`p1_first_step` 缺键、P06-B 的 T2 遮蔽、P04-B 的 `fill_form` 在世界完成集但不在本人完成集。
- C 分支 `origin/Bill`（commit `01c3ef3`）：新增 `schema/模型交接协议.md`（`c-evaluation-draft-1`）与 72 条 `data/integration/*.jsonl` 合成夹具，自述“不是 B 已交付的正式 P0 数据”，并要求“正式实验必须由 B 提供内容独立、经过复核的真实划分”。C 的协议已自带 `split`、`purpose`、`task_graph{nodes,edges}`、数值时间、`person_access_evidence{status,understood}`、`resume_label/resume_step`。
- C 在协议中主动标注：P04 的 T1 口径“仍须由 A/B 统一”。

## 1. 三类分工

| 类别 | 事项 | 状态 |
|---|---|---|
| 我可以直接补 | 文档口径修正、机器预检、审计工作表、v0.2 迁移草案、映射脚本骨架 | 部分已在本分支完成 |
| 只能你本人做 | 16 条人工审计签字、P04 口径决策、盲审组织、112 家族场景设计、文献精读、P1 伦理决策 | 未开始 |
| 需要 A（含 C）确认 | P04 T1 口径、v0.2 字段定名、扩量版本策略、输入白名单降级、C 协议映射、字段名冲突 | 未开始，阻塞扩量 |

## 1.1 状态更新（2026-10-20 夜，P0 v0.2 已交付）

| 事项 | 状态 |
|---|---|
| P0 扩到 120 家族 / 240 条 | 完成：`data/p0/p0_samples_v0.2.json`，由 `scripts/build_p0_v02.py` 可复现生成 |
| schema v0.2（`split`/`mechanism`/`U`/`person_available_semantics`/`p0_design`） | 完成：`schema/p0_record_v0.2.schema.json`，v0.1 冻结不动 |
| 划分 60/20/20 | 完成：72/24/24，按 `base_story_id` 分层、每机制 9/3/3 |
| B 人工复核 | 完成：240/240，`annotation.status=reviewed` |
| P04 T1 口径 | 已按方案 §3.4 落地（15 个 `other_completion` 家族一致） |
| P07 不可判别输入 | 已改为 `indeterminate`，`future_outcome` 只存 `p0_design` |
| 校验与测试 | `validate_data.py` 16/16 + 240/240；`tests/` 12 项断言全过 |
| 文档 | 手册升 v1.0、数据卡 v0.3、schema/README、根 README、ROADMAP 已同步 |
| A/C 盲审 | **仍未做**（只能由 A/C 执行） |
| A 适配 v0.2 | **仍未做**，A 现有适配器只认 `p0-record/v0.1.0` |
| C 字段映射 | **仍未确认**（`person_access_evidence` 同名异型） |
| 三份文献底稿 | **仍未做**（需真人精读） |

## 1.2 状态更新（2026-10-21，不确定性候选批次）

| 事项 | 状态 |
|---|---|
| 11 个空不确定性档位 | 已由 `data/p0/p0_samples_v0.3.json`（7 家族 / 14 条 / 77 事件）覆盖；`human_audit: 0/14`，`draft`，**未验收** |
| `split.calibration` | 仍为 0——要 C 先定校准协议，B 不单方面补档 |
| 合并枚举覆盖检查 | `p0_quality_report.py` 增加"同一 schema 批次合并"段落；`tests/` 新增 2 项断言（共 24 项） |
| 手册 §1.4 未知档位判据 | 已写入 v1.0.1；v0.3 是这条判据第一次成批落地 |
| A 是否读到 v0.3 | **不能**，A 仍只认 `p0-record/v0.1.0`；v0.3 复核完成前也不该送 |
| 「A 只读 v0.1」这条 | 2026-10-21 起由 A 自己在 `A_ALGORITHM_DECISIONS.md` 记为"v0.2 已入库但尚未接入 A 适配器"，不再只是 B 的推测；接入后的验收归 A |
| v0.3 与 v0.2 惯例对齐 | 已按 v0.2 实数据改齐：政策与机制 1:1、误解/未理解臂统一 `suspend_or_wait`、`V=UNKNOWN` 那对不再写 `indeterminate`、`BELIEVES_VALID` 可由 `goal_start` 取证 |
| v0.3 需要你拍板的三点 | ① P01-W8-A「世界事实未定但仍有点标签」；② P01-S6 两臂动作同为 `do_not_resume`；③ 7 对里 4 对 A/B 事件条数不等。逐条写在 `label_quality_plan` §4 v0.3 小节 |

## 2. 我可以直接补的（已做 / 待做）

**已在本分支完成：**

| 文件 | 改动 |
|---|---|
| `docs/annotation/annotation_handbook_v1.0.md` | 新增 §12“与 A 适配器的接口对齐”；§11.1 增补待定问题 9–11（U 字段缺失、P04 口径冲突、与 C 的字段名冲突） |
| `data/p0/README.md` | 修正 §7 中 P03 的不准确表述（`completed_steps_at_cutoff` 也随 e04 派生变化）；§6 增补第 11、12 条（P04 标签待定、A 回归测试钉住本批规模） |
| `docs/annotation/p0_pair_review_table.md` | 新增 §5“机器预检结果”，逐对给出事件差异字段、状态变化、预检结论与“你只需亲自判断的点” |

**我可以继续做（等你点头）：**

1. `scripts/export_eval_format.py`：P0 → C 协议映射（`HH:MM`→同日分钟、`task_dependencies`→`task_graph.edges`、按 `base_story_id` 划 60/20/20、`purpose=scripted_p0`、`resume_label/resume_step` 含 P06-B 遮蔽）。依赖第 4 节第 5 条 C 的映射确认。
2. `scripts/set_annotation_status.py`：批量把 `annotation.status` 从 `draft` 改 `reviewed`/`adjudicated`，避免手改 16 条出错。
3. schema v0.2 草案：新增 `split`、事件级 `person_comprehension`、`person_available_semantics`（人物可获得的语义），全部以“新增文件 + 版本号”方式落地，不动现有 16 条。
4. 质量交接页：从 `validate_data.py` 输出自动生成 `label_quality_plan` §4 的一页纸报告。
5. 文献底稿骨架：`competitors.md`/`core_papers.md`/`mwm_audit.md` 的字段模板（阅读范围、公开实现、可比性边界），内容留“待核实”。

## 3. 只能你本人做的事（手把手）

> **2026-10-21 现状：** 下面 3.1/3.3 是 v0.1 种子与扩量阶段写的，那两件事已经做完（v0.2 已入库、v0.1 保持 `draft` 作为 A 的冻结基线）。现在真正卡住交付的是两张**空白签核表**，都必须由你本人打勾——智能体不会替签：
>
> ```bash
> # ① v0.3 全批 7 对（交 A/C 的前置）
> #    docs/annotation/p0_spot_audit_v0.3_all7.md —— 28 个复选框
> # ② v0.2 抽查 10 对（验证 240/240 reviewed 名副其实）
> #    docs/annotation/p0_spot_audit_v0.2_seed20261021.md —— 38 个复选框
> git pull                              # 拉到最新 qiqi/main 再签，别签旧哈希
> python -B scripts/validate_data.py    # 先确认数据与表头哈希对得上
> ```
>
> 每对四个框依次是：单变量性、§1.4 能否指名缺失证据、Gate 5 期望动作可否推出、结论。要换样本用 `python -B scripts/audit_packet.py --seed <新值>` 重新生成，旧签核不复用。

### 3.1 16 条人工审计（约 1 小时）

```bash
git fetch origin
python -B scripts/validate_data.py          # 应输出 16 records, 8 A/B pairs
python -B scripts/pair_diff_report.py > /tmp/p0_diff.txt
```

对每一对，只看 `docs/annotation/p0_pair_review_table.md` §5 那一行的“你只需亲自判断”格，回答三个问题：

1. 事件里写的内容，人物**有没有可能**知道？（不知道就不能标 `ACCESSED`）
2. 状态差异是否**只由**这一个变量引起？
3. 期望动作与 `p0_scripted_policy` 是否对得上？

四问全过 → 在 `data/p0/README.md` §7 勾掉该条。全部勾完后把 `annotation.status` 改为 `reviewed`（用 2 节第 2 项脚本，别手改）。**注意 P04、P06 两条先别勾**，等第 4 节口径定了再定。

### 3.2 组织盲审（半小时沟通 + 等对方 1 天）

- 每对抽 1 条，共 8 条；只给 `observed_events` + `task_steps` + `task_dependencies`，**不给** `state_at_cutoff`、`p0_expected`、`notes`。
- 请 A 或 C 独立标 `V/F/A/B/C/Q`；分歧记下来，改手册，不改数据去迁就。
- 话术：> 抽 8 条做盲审，只给事件和任务图，不看标签；目的是找定义歧义，不考核一致性。花你 20 分钟。

### 3.3 112 个故事家族的设计（最耗时，2–3 天）

不要靠“换词扩量”，按机制 × 领域做笛卡尔积：

| 机制（源自 P01–P08） | work | collaboration_service | daily_life |
|---|---|---|---|
| 接触/未接触取消 | 3 | 3 | 3 |
| 长期承诺 vs 近期放弃 | 3 | 3 | 3 |
| 恢复位置（主观进度滞后） | 3 | 3 | 3 |
| 他人代完成 | 3 | 3 | 3 |
| 资源受阻 | 3 | 3 | 3 |
| 嵌套中断 | 3 | 3 | 3 |
| 理解/误解 | 3 | 3 | 3 |

每格 3 个内容独立的家族 → 63 个；剩余名额优先补 `daily_life`（当前只有 1 对）。每个家族仍出 A/B 两条，`notes` 写明唯一变量。**写完先用 `validate_data.py` 跑一遍再提交**。

### 3.4 文献精读（5 篇足够撑起 Related Work）

按顺序：MWM/MENTIS → BDI 2008 → 2017 滑窗目标识别 → SIPS 2020 → GODR 2026。每篇按 `competitor_matrix.md` §核查记录规范 写 6 项，**只写真正读到的**；只看到摘要就写“仅摘要”。读完更新矩阵“核查状态”列，再动笔写 Related Work。

### 3.5 P1 伦理与许可（决策，不是写代码）

要定三件事：数据来源（公开许可视频 vs 受控实验）、伦理审批主体、访问控制与撤回机制。这三项定了，P1 schema 才有意义；没定之前 P1 保持“未采集、仅未来工作”的表述。

## 4. 需要 A（含 C）确认的 6 条

| # | 问题 | 建议默认值 | 阻塞什么 |
|---|---|---|---|
| 1 | **P04-B 的 T1 口径**：全部步骤已客观完成，`resume_within_horizon=true` 是否改 `false`（配 `first_step=null`，保留 `Q=fill_form` 作主观滞后诊断）？ | 改为 `not_resume`，与方案 §3.4 和 C 的夹具一致 | 现在 A 的 `scripted_targets` 把它算作有效 T2，**错标已进入 9 条 T2 监督**；不修则主结果带错 |
| 2 | **v0.2 字段定名**：事件级“理解”用 `person_comprehension`（`UNDERSTOOD/MISUNDERSTOOD/...`）还是沿用 C 的 `person_access_evidence.understood`？ | 采用 `person_comprehension`，并把 C 的 `understood` 映射过去 | A 的 `comprehension` 占位、C 的 `understood` 都等这个字段；T^AU 门控无监督 |
| 3 | **“人物可获得的语义”字段**：是否需要结构化 `message_semantics`（如 `kind=cancellation|fulfillment`、`interpretation=defer`）？ | 需要，否则 P04-A/P08-A 人物侧只剩一个 `ACCESSED` | 决定 P0 能否支撑“接触≠理解”的消融 |
| 4 | **扩量版本策略**：新增 `p0_samples_v0.2.json` + `p0-record/v0.2.0`（旧文件冻结），还是原地替换并让 A 改测试？ | 新增文件 + 升版本；A 的适配器遇未知版本会显式报错，不会误读 | A 的 8 项回归钉死 16/123，原地改必炸 |
| 5 | **输入白名单降级**：`completed_steps_at_cutoff` 与 `interrupting_task.status_at_cutoff` 是否从“允许输入”降为“诊断侧”？（A 已经这么做了） | 降级，并在手册写明 | 不改则 C 的基线可读快照，与 A 不公平 |
| 6 | **C 协议映射确认**：`HH:MM`→同日分钟、`task_dependencies{before,after}`→`task_graph.edges`、`purpose=scripted_p0`、`person_id/task_family` 命名规则 | 按上表映射，`purpose=scripted_p0` 与 `synthetic_integration_fixture` 严格区分 | 阻塞 `export_eval_format.py` 与 C 的正式评测 |

**可直接发给 A 的消息：**

> A，你分支上的适配器我看了，schema 按 v0.1.0 接收没问题，B 侧接口确认这项算清。我这边有三件会动到你监督/评测的事，需要你点头：
> 1）P04-B 我这条标错了：三个步骤客观全完成，但 `resume_within_horizon=true`、`first_step=fill_form`。按方案 §3.4“推动尚未完成步骤”应判 `not_resume`，C 的夹具也是这么处理的。我倾向改成 `not_resume + first_step=null`，`Q=fill_form` 保留作主观滞后诊断——但这样 P04 就没有 T1 对比了，只剩 T3。你确认后我改数据并同步哈希，你那边 T2 监督会从 9 条变 8 条。
> 2）你适配器里 `comprehension="not_structurally_labeled"`、C 协议里 `person_access_evidence.understood`，说明“理解”这个字段缺的是我这边。我打算 v0.2 加事件级 `person_comprehension`，同时加一个“人物可获得的语义”字段，否则 P04-A/P08-A 在人物侧只剩一个 ACCESSED，你的 AU 门控没法验。字段名你有偏好吗？
> 3）扩量我会新增 `p0_samples_v0.2.json` 并把 `schema_version` 升 `p0-record/v0.2.0`，不覆盖现有 16 条，避免你的回归测试和哈希失效。你那边收到新版本时是另开适配器分支，还是同一分支加版本分支逻辑？

## 5. 建议顺序

1. 今天：发上面那条消息（P04 是唯一带错标的，越早越好）。
2. 今天：跑一遍 3.1 的前两步命令，把 P01/P02/P03/P05/P07/P08 六条勾掉（P04/P06 留着）。
3. 明天：请 A/C 盲审 8 条；同时我出 v0.2 草案与导出脚本骨架。
4. 第 3–4 天：112 家族设计（你）+ 扩量数据（我按你的场景清单批量生成，你复核）。
5. 第 5 天：手册升 v1.0，`annotation.status` → `adjudicated`，出质量交接页。
6. 文献与 Related Work 并行推进，不要等数据。
