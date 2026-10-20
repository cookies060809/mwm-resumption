# 数据目录

> **当前：** P0 v0.2 共 120 家族 / 240 条已入库并通过校验（另有 16 条 v0.1 冻结种子供 A 的现有适配器使用）；P1 真实行为数据尚未采集，默认不入库。

## 目录

```text
data/
├── p0/
│   ├── README.md
│   ├── p0_samples.json        # 16 条 v0.1 冻结种子
│   ├── p0_samples_v0.2.json   # 240 条 v0.2 正式批次
│   └── p0_samples_v0.3.json   # 14 条不确定性候选批次（draft，未验收）
└── p1/
    └── README.md              # P1 访问、伦理与未来 schema 说明
```

## P0 与 P1

| | P0 | P1 |
|---|---|---|
| 来源 | 人工脚本 + 明确规则 | 经许可的真实连续行为/任务日志 |
| 标签 | 脚本期望 + 人工核查 | 独立证据 + 双人标注 |
| 用途 | 管道、泄漏、对照逻辑、状态一致性 | 真实恢复行为预测 |
| 能否声称真实人类预测 | **否** | 仅在证据与样本充分时 |
| 是否入库 | 是（P0 种子） | 否（受限位置） |

## P0 种子批次

- 规模：120 个家族 × A/B = 240 条（15 个任务骨架 × 8 个受控机制），1831 个事件。
- Schema：`schema/p0_record.schema.json`（`p0-record/v0.1.0`）。
- 标注状态：`draft`；尚未完成 B 人工复核与 A/C 盲审。
- 领域：`work` 6 条、`collaboration_service` 8 条、`daily_life` 2 条。
- 当前 split：已完成，按任务骨架做 60/20/20（72/24/24 家族），同一骨架与同一家族都不跨集合。
- 输入/标签边界、机制表、划分与已知问题见 [data/p0/README.md](p0/README.md)。

## 校验与对照审计

```bash
python scripts/validate_data.py
python scripts/pair_diff_report.py
python -m pytest
```

- `validate_data.py`：JSON Schema + 跨字段一致性（cutoff 顺序、证据链、动作/步骤对齐、P07 输入一致性）。
- `pair_diff_report.py`：逐字段打印 A/B 差异，用于人工确认“只改一个设计变量”。
- P0 的 `notes` 含 P07 截断后设计说明，**不得进入模型输入**。

## 数据变更规则

1. 同一 `base_story_id` 的 A/B 变体必须放在同一 PR、同一 split。
2. 新增/修改样例必须通过 schema、跨字段校验与 A/B diff。
3. `cutoff_event_id` 必须是最后一条事件；禁止未来事件进入 `observed_events`。
4. 非 `UNKNOWN` 标签必须有逐因子证据；`state_evidence_event_ids` 必须是逐因子证据的按序并集。
5. P1 原始数据、可识别个人信息、未脱敏日志和受限材料**不得提交**。
6. P0 脚本标签与 P1 真实标签必须分开统计与表述。

详见 [标注手册](../docs/annotation/annotation_handbook_v1.0.md)、[质量方案](../docs/annotation/label_quality_plan_v0.1.md) 与 [数据卡](../docs/data/data_card.md)。
