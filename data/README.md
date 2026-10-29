# 数据交付与消费契约（A/C 入口）

> 版本：`data-release/v1`（2026-10-24）。机器可读清单：[RELEASE.json](RELEASE.json)。
> 校验：`python scripts/release_manifest.py`。清单不过 = 文档、计数或哈希已漂移，先修再跑实验。
>
> **真人 P1 记录：0。** 2026-10-23 团队决定不做真人采集与标注，P1 以公开数据派生交付
> （见 [p1/README.md](p1/README.md)）。任何材料不得写成"预测真实人类恢复"。

## 1. 三件交付，各管一件事

| 交付 | 路径 | 规模 | 用途 | 不能用来 |
|---|---|---|---|---|
| **P0 v0.4** | `data/p0/v0.4/`（v0.3 冻结保留） | 254 条 / 127 家族 / 1,908 事件 | 六变量 `V/F/A/B/C/Q` 监督、T1/T2/T3 评测、受控对照诊断 | 声称真实人类心理或外部效度 |
| **ready-v1.1** | `data/training_ready/v1/` | 438/123/121 | 直接训练：P0 六变量掩码 + IHBench 中断续答蒸馏 + SFT 文件 | 把 IHBench 回答当六变量标签 |
| **P1 public_derived** | `data/p1/public_derived/` | 2,863 条（3 源） | 恢复/不恢复评测（`eval/` 842 条）、V 维诊断 | 六变量联合监督金标 |

### 按任务选入口

| 你要做的事 | 读这个 | 关键约束 |
|---|---|---|
| 训练 EC-JMF 六变量模块 | `training_ready/v1/train.jsonl`，`task=="state_inference"` | 只在 `state_loss_mask[f]==1` 上算损失；未知标签已从 target 省略 |
| 训练对话辅助模块 / SFT | `task=="interruption_response"` 或 `*_sft.jsonl` | 目标是上游已发布模型回答，不是人类行为 |
| 做 T1/T2/T3 评测 | `p0/v0.4/splits/test.json` 或 `p0/v0.4/eval/{inputs,labels}.jsonl` | 只读 test；P07 的 `indeterminate` 不是负例 |
| 做恢复预测评测（P1） | `p1/public_derived/eval/{inputs,labels}.jsonl` | 842 条已观测样本；1,951 条删失不得当负例；必须分源报告 |
| 做状态预测切点分析 | P1 原生 `processed/p1_combined.jsonl` 中 `resume_loss_mask=0` 的行 | 这些行的恢复/完成动作在可见历史内，不能当盲测 |
| 查标签为什么是 UNKNOWN | `state_withdrawn`（P1 原生行）或 `state_evidence_by_factor`（P0） | 撤回值只作审计，不得改回金标 |

## 2. 六变量监督矩阵（实测值）

| 因子 | P0 v0.4 | P1 public_derived | 说明 |
|---|---:|---:|---|
| V | 253/254 | 2,863/2,863 | P1 的 IHBench 856 条恒 `VALID`；非平凡档位在 InterruptBench（612 `CANCELLED`）与 REBOOT（15 `FULFILLED`） |
| F | 253/254 | 57/2,863 | P1 只有 REBOOT `READY`，`BLOCKED` 已撤回 |
| A | 254/254 | 72/2,863 | P1 只有 REBOOT `ACCESSED`，`NOT_ACCESSED` 已撤回 |
| B | 250/254 | 72/2,863 | P1 只有 REBOOT `BELIEVES_VALID`；`BELIEVES_INVALID`/`UNRESOLVED` 已撤回 |
| C | 253/254 | 988/2,863 | P1 的 IHBench 856 条恒 `SUSPENDED`；`ABANDONED` 已撤回 |
| Q | 254/254 | 15/2,863 | P1 只有 15 条 `NOT_APPLICABLE`，**具体步骤 0** |

**结论：六变量主监督只有 P0。** P1 能支撑的是恢复标签（786 正 / 126 负 / 1,951 删失）和 V 维，
不是信念—承诺联合监督。行为级"不恢复"负例只有 126 条且全部来自 IHBench 文本 agent，
这是数据上限，不是模型缺陷；禁止把删失行改标为负例。

## 3. 划分与校准

| 层 | train | dev / val | calibration | test |
|---|---|---|---|---|
| P0 v0.4 | 150 | 52（dev） | 空（团队决定） | 52 |
| P1 原生 | 1,996 | 499（val） | — | 368 |
| P1 评测视图 | 603 | 177（val→dev） | 0 | 62 |

- 同家族 / 同 `split_group_id` 不跨 split；P0 按 `base_story_id`，P1 按 270 个 `split_group_id`。
- 只允许 train 拟合参数；**test 不得用于调参或选模**。
- P0 的 dev 是 A 的选模集。C 若在 P0 上做校准，必须显式声明与选模重叠，或改用 P1 val。
- P0 `calibration` 为空是决策，不是缺口；不要为了"看起来完整"补档。

## 4. P0 记录与 C 协议

- P0 记录 schema 为 `p0-record/v0.2.0`；发布版本 `p0-release/v0.4.0` 是打包版本，不是新 schema。
- A 的适配器接受 `v0.1.0`/`v0.2.0`，拒绝未知版本；v0.4 记录按 v0.2.0 读取。
- C 的 `c-evaluation-draft-1` 导出在 `p0/v0.4/eval/`（254 输入 + 254 标签，按 `sample_id` 对齐）。
- P1 评测视图在 `p1/public_derived/eval/`，已用 C 分支 `mwm_eval/schema.py` 实测通过。
- 布尔 `understood` 合并了 MISUNDERSTOOD 与 NOT_UNDERSTOOD；要完整 U 区分，读原生记录。
- T3 逐因子证据口径见 [docs/data/t3_evidence_mapping.md](../docs/data/t3_evidence_mapping.md)：以 `state_evidence_by_factor` 为金标准，A 的显著事件只作诊断比较。

## 5. 禁止事项（会直接毁掉实验）

1. **不要把 P0 与 P1 混在一个指标里。** `dataset_layer` 校验会拒绝，文档也不允许。
2. **不要把 P1 删失当负例。** `null` 不是 `false`；1,951 条 `censored` 只作弃权/保留集。
3. **不要把 `state_withdrawn.claimed` 当金标。** 撤回是 2026-10-23 的结论，有规则号与理由。
4. **不要把 ready-v1 的 P0 子集与 `data/p0/v0.4` 再拼接。** 两者是同一批 254 条。
5. **不要用 test 调参。** 包括提示词、阈值和规则变体。

## 6. 许可与合规

| 数据 | 许可 | 边界 |
|---|---|---|
| P0 v0.4 / ready-v1 的 P0 部分 | 项目自建 | 仓库私有；对外声明时写明"脚本诊断数据" |
| IHBench | CC-BY-4.0 | 可署名再分发；含 GPT-4o Audio 参照回答 |
| REBOOT | Apache-2.0（源清单记录） | 可署名再分发；只用了 meta，不含视频/轨迹 |
| InterruptBench | **未确认** | 仅限内部评测；任何对外发布/竞赛分发前必须剔除或解决许可 |

竞赛规则要求：引用他人数据必须标注来源与许可；不得虚构结果；对外材料不得出现学校/Logo/指导教师信息。
本仓库保持私有且仅内部训练使用，是 InterruptBench 分片当前唯一合规的前提。

## 7. 复现校验（提交前必跑）

```bash
python scripts/validate_data.py
python scripts/validate_data.py --file data/p0/v0.4/p0_samples.json
python scripts/build_p0_release.py --check
python scripts/build_p0_v04.py --check
python data/training_ready/v1/check.py
python data/training_ready/v1/train_cpu.py
python data/p1/public_derived/scripts/checksums.py    # 重算后 git diff 应为空
python data/p1/public_derived/scripts/export_eval_view.py
python scripts/release_manifest.py
```

最后一条会重算三件交付的行数、划分、掩码、哈希与文档计数；任何漂移都会非零退出。

## 8. 已知边界

- P0 v0.4 只做了 B 侧一项标签仲裁（14 条 `B` 由 `UNKNOWN` 升 `BELIEVES_VALID`），**没有** A/C 盲审与独立仲裁（`adjudicated`）。
- v0.3 已冻结为历史版本；任何在 v0.3 或 ready-v1.0 上训练/评测的结果作废，需在 v0.4 / ready-v1.1 上重跑。
- P1 的 1,815 条 InterruptBench 因 `task_steps=[]` 无法进入 C 协议；只可能用于 V 维，需 C 先扩展协议。
- P1 没有时间戳；评测视图的 `time` 是事件序号，`horizon` 来自源侧 planned 单位（轮次/帧），与 P0 的决策机会不可直接比较。
- 负例只有 126 条且来自单一源；按源报告是硬要求，跨源合并只允许作为补充。
