# ECR-MWM · P1 结构化评测集（公开数据重组）v1.5.1

从公开、许可证可核查、**带已有标注**的数据集重组出符合 P1 Schema 的结构化 JSONL。
无原始采集、无人类受试者环节、无模型生成标签。

> **本包的定位（2026-10-23 入库时确认；同日团队决策不再真人采集与标注，本包即 P1 数据交付）：**
> 三源公开数据派生的辅助任务数据集。三源主体分别是语音 agent 文本、网页 agent 任务/中断规格、
> 双臂机器人装配 episode，**没有一条是"真实人物在原目标被打断后是否恢复"的直接观测**。
> 六变量里 `B/C/Q/F/A` 的取值来自规则映射，不构成对应真值：缺证据处应按 `UNKNOWN` + 损失遮蔽处理，
> 不得当作联合监督金标。逐源可用范围与不可声称项见 `docs/dataset_card.md`。

## 交付摘要

| | |
|---|---|
| 样本 | **2,863** 行（`processed/p1_combined.jsonl`，10.2 MB） |
| 源（要求 ≥2） | **3 个**：IHBench 856（含 428 条 baseline 行为者）· InterruptBench 1,815 · REBOOT 192 |
| 任务书「IHBench 或 REBOOT 至少一个成功」 | ✅ **两者都成功** |
| `p1_observed_resume` | true **786** / false **126** / **null 1,951**（censored） |
| `llm_inferred` 标签 | **0** 条 |
| 枚举档位覆盖（按 C 协议档位） | V 3/4、F 2/3、A 2/4、B 2/4、C 4/5、censoring 3/3、`event_type` 6/6；**Q 没有任何具体步骤**。撤回后为 0 的档位：`F=BLOCKED`、`A=NOT_ACCESSED`、`A=UNCERTAIN`、`B=UNRESOLVED`、`B=BELIEVES_INVALID`、`C=ABANDONED` |
| 校验 | draft-07 + 跨字段 + 泄漏 + 溯源：**0 violations / 2 warnings**（2 条 `observed_resume` 但步骤无法归因，见下文）|
| `raw/` 体积 | 构建时本机 **5.04 MB**（要求 <500 MB；IHBench 音频 214 MB、REBOOT 轨迹与视频、IndustReal 视频包均未下载）。**Git 只跟踪其中的溯源清单**（5 个文件，45 KB），上游标注正文按 `.gitignore` 排除 |

> **"不恢复"监督上限（2026-10-23 记录）：** 126 条 observed_not_resume **全部来自 IHBench**（REBOOT/InterruptBench 均无），
> 且真人采集已 descope。因此"不恢复"类别在当前公开数据上只有这一个来源，识别率上限受其规模约束；
> 模型"不恢复"召回为 0 属于数据属性，不应作为模型缺陷反复迭代，也不得把 1,951 条删失样本改标为不恢复来补负样本。

## 目录

```
data/p1/public_derived/
├── raw/{IHBench,InterruptBench,REBOOT}/     仅入库 _manifest.json / _upstream_blobs.json 等溯源审计
│                                            （URL / sha256 / 字节数）；上游标注正文由 run_pipeline.sh
│                                            的 fetch 步骤就地下载，不入 Git
├── processed/{ihbench,reboot,interruptbench,p1_combined}.jsonl
├── eval/{inputs,labels}.jsonl                C 协议视图（842 条盲测恢复样本），由 export_eval_view.py 生成
├── scripts/convert_{ihbench,reboot,interruptbench}.py   merge_and_validate.py   export_eval_view.py  …
├── docs/{source_manifest,dataset_card,llm_validation_log,schema,transformation_notes,
│         coverage_report,raw_inventory}.md  validation_*.txt  CHECKSUMS.sha256  schema.json
├── run_pipeline.sh
└── README.md
```

`industreal.jsonl` 不存在：该源被判定跳过（原因见 docs/source_manifest.md §2.3），不产出占位文件。

## 读数据前必须知道的四件事

1. **null 不是 false。** `p1_observed_resume=null` + `p1_censoring_status="censored"` 表示窗口未覆盖；
   `false` 才表示观察到未恢复（126 条，全部来自 IHBench 的内容级判定）。
2. **三源主体不同模态**：IHBench＝语音 agent 文本、InterruptBench＝网页 agent 的任务/中断规格、
   REBOOT＝双臂机器人装配 episode。`dataset_card.md` 逐源写明限定，跨源聚合指标必须同时分源报告。
3. **`task_steps`/`Q` 只有 IHBench 与 REBOOT 有**：InterruptBench 发布内容不含步骤级标注
   （`interrupt_at_pct` 是运行时动作序列的百分比，序列需跑 agent 才存在）→ `task_steps=[]`、`Q=UNKNOWN`。
4. **InterruptBench 分片不可对外再分发**：仓库根目录无 LICENSE，唯一 MIT 文本版权行属上游
   VisualWebArena 作者 → 标记 `used_with_caveat`，仅限内部评测。IHBench（CC-BY-4.0）与
   REBOOT（Apache-2.0）可署名再分发。

## 复现

```bash
bash run_pipeline.sh                  # fetch -> convert each source -> merge + validate -> reports
python scripts/export_eval_view.py    # 由 processed/p1_combined.jsonl 生成 eval/ 与 MAPPING.md
python scripts/checksums.py           # 重算 docs/CHECKSUMS.sha256
```

**入库后 `raw/` 只有溯源清单，没有上游标注正文。** 新克隆的仓库无法离线重建：必须先跑 fetch 步骤
（或按 `docs/source_manifest.md` 记录的 URL 与 sha256 手工取回），`processed/*.jsonl` 才能重新生成。
本仓库里已提交的 `processed/*.jsonl` 是这几次抓取的产物，其哈希逐条记在 `docs/CHECKSUMS.sha256`。

依赖 Python 3.12 + `pyarrow`、`pandas`、`jsonschema`。CPU-only，构建步骤完全确定性（无随机、无外部 API 调用）：
两次独立抓取 `bosonai/IHBench` 文本列得到相同 sha256 `612b6d09…`；`processed/*.jsonl` 可重复生成。
网络步骤依赖上游可用性（本机事实记录在 `docs/source_manifest.md` §0）。

## 六标签覆盖矩阵（v1.5.1 生效值，2,863 条）

下表是**撤回后实际交付的监督**，不是规则映射的原始产出；每个数字都能由 `processed/p1_combined.jsonl`
的 `state_at_cutoff` 与 `state_withdrawn` 直接复核，`export_eval_view.py` 只导出恢复评测视图，不改这些标签。

| 字段 | 有监督行数 | 取值 | 来源 | 被撤回 |
|---|---:|---|---|---:|
| V | 2,863（100%） | VALID 2236 / CANCELLED 612 / FULFILLED 15 | CANCELLED=InterruptBench 撤回声明；FULFILLED=REBOOT 明示完成 | 0 |
| F | 57（2.0%） | READY 57 / UNKNOWN 2806 | 只有 REBOOT | 2,806 |
| A | 72（2.5%） | ACCESSED 72 | 只有 REBOOT | 2,791 |
| B | 72（2.5%） | BELIEVES_VALID 72 | 只有 REBOOT | 2,791 |
| C | 988（34.5%） | SUSPENDED 856 / ACTIVE 117 / COMPLETED 15 | IHBench 恒 SUSPENDED；REBOOT 贡献其余 | 1,875 |
| Q | 15（0.5%） | NOT_APPLICABLE 15；**具体步骤 0** | 只有 REBOOT 完成点 | 2,848 |
| censoring | 2,863（100%） | observed_resume **786** / observed_not_resume **126** / censored **1,951** | 负例=IHBench（episode 行为者 11 + baseline 行为者 115） | 2 |
| event_type | — | start_goal 2863 / background_fact 27702 / progress 12204 / interruption 3793 / resume 70 / completion 15 | resume、completion=REBOOT | 0 |

**关键读数：** 除 V 外，F/A/B 只有 REBOOT 的 57/72/72 行（2,863 行里的 2.0%–2.5%），C 的 988 行里有 856 行来自 IHBench 的恒 `SUSPENDED`。Q 没有任何具体步骤，因此**不能在这份数据上评 T2**；F/A/B/C 也**不能当联合监督金标**。

### 状态撤回（`state_withdrawn`，2,863/2,863 行）

2026-10-23 修订把不可由上游标注直接支撑的规则映射值撤成 `UNKNOWN`，并在每行 `state_withdrawn` 里留下因子、原值与规则号：

| 因子 | 规则 | 撤回行数 | 理由（原文摘录） |
|---|---|---:|---|
| F | T5（InterruptBench） | 1,815 | scoring oracle 证明存在可检验终态，不等于 cutoff 时资源/权限已就绪 |
| A | T6（InterruptBench） | 1,815 | 发布的是任务规格，没有执行日志能证明行动者收到或处理了注入消息 |
| B | T7（InterruptBench） | 1,815 | 无标注报告行动者信念；原值由中断类型或事后恢复反推 |
| C | T8（InterruptBench） | 1,815 | 撤回需求是用户动作，不等于 agent 放弃承诺 |
| Q | T9（InterruptBench） | 1,815 | 源不提供步骤分解 |
| F/A/B/Q | R5/R3/R6/R2-R8（IHBench） | 856 各 | 对话文本只支持恢复行为判定，不支持 cutoff 时的资源/接触/信念/步骤状态 |
| Q | B11（REBOOT） | 177 | 该截断点没有可评的下一步 |
| F | B7（REBOOT） | 135 | `recovery−induced` 不是 cutoff 时资源就绪证据 |
| A/B | B8/B9（REBOOT） | 120 各 | 无逐帧证据证明行动者接触或相信目标有效 |
| C | B10（REBOOT） | 60 | 无承诺状态标注 |
| `p1_observed_resume` | B12（REBOOT） | 2 | 原标签硬编码，覆盖窗口内没有恢复事件 |

`V` 没有任何一行被撤回。撤回是**有记录的降级**，不是缺数据；分析时按 `state_loss_mask` 遮蔽，不要把 `UNKNOWN` 当负例，也不要改回 `state_withdrawn.claimed` 重当金标。

## 怎么切这份数据（三个正交轴）

1. **按源**：`source_dataset`。注意三源主体与粒度不同（IHBench 语音 agent 文本 / InterruptBench 网页 agent 规格 / REBOOT 机器人 episode）。
2. **按行为者**：`base_story_id` 以 `@baseline` 结尾 = IHBench 发布数据自带的 GPT-4o Audio 参照回答；
   同一 `(conversation, cutoff)` 的两条样本 **`state_at_cutoff` 完全相同**、仅恢复标签可能不同
   （154 个截断点上两行为者不一致）。做盲测恢复评测时任选一个行为者，不要混在同一个指标里。
3. **按截断点类型**：`cutoff_event_id` ∈ {`u##`(IHBench 中断) , `p##`/`f01_fail`/`r01_rec`/`d01_done`(REBOOT) , `i##_场景`(InterruptBench)}。
   - **盲测恢复**：`_fail`、IHBench `u##`（恢复动作在截断之后，已从 `observed_events` 移除）
   - **状态预测**：`_rec`/`_done`/`p##`（恢复或完成动作本身即截断点，标签在可见历史里）
   - **不可用**：`p1_censoring_status="censored"` 的 1,951 条（`p1_observed_resume=null`）应作保留集/弃权指标，不计入恢复准确率

## 给 C 的评测视图（`eval/`）

`python scripts/export_eval_view.py` 只导出 `resume_loss_mask=1` 的 **842 条**盲测恢复样本
（IHBench 785 + REBOOT 57），写成 C 的 `c-evaluation-draft-1` 格式：

| 文件 | 内容 |
|---|---|
| `eval/inputs.jsonl` | 8 个协议字段 + `observation`；`purpose="public_derived_p1"` |
| `eval/labels.jsonl` | `resume_label` / `resume_step` / `state_labels`（只有 V）/ `state_evidence` / `window_complete=true` |
| `eval/MAPPING.md` | 逐字段映射、被排除的 1,951 条删失与 70 条状态预测样本、时间与 horizon 的口径 |

- 已用 C 的 `mwm_eval/schema.py`（`origin/Bill`）实测通过：842 条、`dataset_layer=P1`、train/dev/test = 603/177/62。
- **不要**在这个视图上算 T3：`F/A/B/C/Q` 已撤回，只有 V 带证据；P1 的 T3 结论只能来自原生 `state_at_cutoff` 并显式说明撤回。
- **不要**把 `val` 当 test：导出时映射为 `dev`，`test` 保持封存。
- 1,815 条 InterruptBench 因 `task_steps=[]` 无法通过 C 协议的"步骤非空"约束，未进入视图；它们全部是 `censored`，只可能用于 V 维评测，需要 C 先扩展协议。

## §5 自检清单

| # | 项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 每个 source_dataset 的许可证已记录且允许再分发 | **PASS（1 项例外）** | IHBench `cc-by-4.0`、REBOOT `license:apache-2.0`（38/38 仓）明确；**InterruptBench 不明确**，按任务书应跳过，本交付保留为 `used_with_caveat` 并禁止对外再分发；2026-10-23 已决定仓库保持私有、仅内部评测，对外发布前必须剔除该分片或解决许可，见 `docs/source_manifest.md` §2.4 |
| 2 | 未下载视频/音频大文件；`raw/` < 500 MB | **PASS** | 构建时 `raw/` = 5,041,196 B；IHBench 音频列 214,161,509 B 未请求（65 次 Range 共传输 2,255,700 B）；REBOOT 只取 `meta/`（68,537 B），`data/`、`videos/` 未请求；IndustReal 因需视频整包而跳过。入库的是这些抓取行为的清单，不是抓到的文件 |
| 3 | 每条记录含 `sample_id`/`source_dataset`/`base_story_id`/`observed_events`/`p1_observed_resume`/`p1_censoring_status` | **PASS** | schema `required` 全列 + `additionalProperties:false`；`validation_report.txt` = 2,863 条 0 violations |
| 4 | 每个非 UNKNOWN 字段有 `evidence_trace` 或 `original_annotation_ref` 支撑 | **PASS** 校验器强制「非 UNKNOWN ⇒ trace 必含截断事件」且 trace id 必须存在；逐样本 `fields_used` 列出实际读取的原始字段名 |
| 5 | LLM 补标带 confidence/evidence_quote，且 ≥10% 人工抽检 | **N/A（未使用 P2）** | `llm_inferred` = 0 事件；`docs/llm_validation_log.md` 记录了为什么不需要 P2、以及启用时的模板/抽样/校验流程。**人工抽检未执行**（没有可抽检的模型标签），此点不得当作已完成 |
| 6 | `dataset_card.md` 写明「不是从零采集的真实人类行为日志」 | **PASS** | 原文首段；另逐源写明 IHBench＝Agent 恢复标注、REBOOT＝机器人装配 meta、IndustReal/InterruptBench 限定 |
| 7 | 脚本可在此 CPU 环境重跑得到相同结果 | **PASS（网络步骤除外）** | 构建脚本无随机、无外部 API；抓取审计与 sha256 落盘于 `raw/*/_manifest.json` 与 `docs/CHECKSUMS.sha256`；两次抓取 IHBench 文本列哈希一致 |
| 8 | `p1_combined.jsonl` 至少 2 个 source_dataset | **PASS** | 3 个（IHBench/InterruptBench/REBOOT）；`merge_and_validate.py --require-min-sources 2` 通过 |
| 9 | 是否存在把 IHBench 的 `p1_observed_resume` 说成「人类行为」的描述 | **PASS（无此类描述）** | 全部文档一致表述为语音助手 agent 的恢复行为；REBOOT 才涉及人类操作员示教，且已单独声明 |

## 已知缺口（如实列出）

- **恢复负例只有 126 条**，且全部来自 IHBench 的文本 agent 域。REBOOT 样例仓 60 段全是
  `episode_type="recovery"`，不含「失败后未恢复」episode；完整标注在 `REBOOT26/datasets`，未授权返回 **401**。
- **REBOOT 源侧标注自相矛盾**：46/60 条 `failure.originating_phase` 与失败帧所处 phase 不符（+1/+2 偏移、
  1 条值 21 越界），1 条 τ 非单调。转换器不使用该字段定步骤，改由帧号推导，并把不一致计入构建日志与文档。
- **REBOOT 覆盖率**：org 内 38 个仓只有 1 个带 `meta/phase.json`（全量扫描 with=1 / without=37 / unreachable=0）。
- **IndustReal 无法核验**：`data.4tu.nl` 本机连接失败，数据集许可证、可单独下载的 CSV、标注体积均无法确认 → 跳过。
- **划分已冻结，按组切。** 记录顶层 30 个字段，含 `split`（train/val/test = 1,996/499/368）与
  `split_group_id`（270 组）。同一组不跨 split；`base_story_id` 也不跨 split。C 协议视图把 `val` 映射为
  `dev`（603/177/62），`test` 保持封存。`@baseline` 派生行仍挂在带后缀的 `base_story_id` 上，
  但它们与对应的 episode 行同组，所以按 `split_group_id` 或 `split` 切分都不会泄漏。
- **事件无可用时间戳。** `observed_events` 的字段是 `event_id/event_type/step_id/person_access/source/actor/text/position`，
  其中 `position` 大量为 `null` 或是嵌套对象，不能当统一时间轴。C 评测视图因此用事件序号作 `time`，
  "结果事件晚于截断点"只能靠序号约定，无法用墙钟独立核验。
- **`B=BELIEVES_INVALID` 现在为 0 条。** v1.4 曾用 REBOOT `failure_mode="freeze"` 得到 1 条（规则 B15），
  但 2026-10-23 修订按 B9 把该源全部 120 条 B 值撤回，这条也一并作废。其余失败模式描述工件/抓取状态，
  不触发信念规则。批量补齐需 REBOOT 主仓（`REBOOT26/datasets`，未授权 401）里
  「policy 中止 + expert demo 证明可完成」的 rollout 标注。IHBench 侧已穷举检索并否决（见 llm_validation_log.md）。
