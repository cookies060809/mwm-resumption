# 数据目录

> 当前仓库只有 P01 最小对照示例和 P1 模板，没有真实 P1 数据。

## 目录

```text
data/
├── p0/                 # 受控脚本诊断集
│   └── examples/work/  # P01-A / P01-B 示例
└── p1/
    ├── templates/      # 记录模板（可提交）
    └── README.md       # 访问与伦理规则
```

## P0 与 P1

| | P0 | P1 |
|---|---|---|
| 来源 | 人工脚本 + 明确规则 | 经许可的真实连续行为/任务日志 |
| 标签 | 脚本期望 + 人工核查 | 独立证据 + 双人标注 |
| 用途 | 协议诊断、泄漏测试、逻辑一致性 | 真实恢复行为预测 |
| 能否声称真实人类预测 | **否** | 仅在证据与样本充分时 |
| 是否入库 | 是（公开/内部） | 否（受限位置） |

## 命名

- `base_story_id`：基础故事家族，例如 `P01`。
- `variant_id`：最小对照变体，例如 `A`、`B`。
- `sample_id`：`<base_story_id>-<variant_id>`，例如 `P01-A`。
- 同一 `base_story_id` 的所有变体必须同属一个 split，禁止跨训练/测试。

## 校验

```bash
python scripts/validate_data.py
python -m pytest
```

校验器会检查 schema、事件引用、证据 ID、步骤合法性、时间截断与成对互引。

## 数据变更

1. 开 Issue 说明新增/修改的家族、受控变化与预期标签。
2. 同族变体放在同一 PR。
3. 通过校验与 B 评审；涉及标签语义时更新标注手册版本。
4. P1 只提交元数据、模板或批准派生结果；原始材料不进入 Git。

详见 [标注手册](../docs/annotation/annotation_handbook_v0.1.md) 与 [数据卡](../docs/data/data_card.md)。
