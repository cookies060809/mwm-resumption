# 结果目录

> A侧脚本P0神经训练与机制消融已完成：[v0.3语义修正版与限制](p0/a_neural_v03_v3/README.md)、[历史v0.2训练及冻结补充](p0/a_neural_v1/README.md)。不代表真实人物预测性能。数字均由训练入口生成。

## 规则

1. 结果必须由脚本生成，并绑定配置快照、代码 commit、随机种子与数据版本/哈希。
2. 每个 run 目录至少包含：
   ```text
   results/<run_id>/
   ├── config.yaml
   ├── run.json
   ├── metrics.json
   ├── predictions.jsonl
   ├── per_sample/
   └── failures.md
   ```
3. `run.json` 记录环境、依赖版本、运行时间、token/latency/算力与异常。
4. `predictions.jsonl` 保留逐样例输入 ID、预测、概率、证据引用与标签（标签仅用于评价，不进入模型输入）。
5. 失败案例与异常必须保留，不得只报告成功样例。
6. P0 与 P1 结果分开目录、分开报告；P0 脚本结果不得写成真实人类预测能力。
7. 对外引用结果时注明 run_id、commit 与数据版本；结果不可用时标记为作废，不覆盖历史。

## 命名

```text
results/<phase>/<experiment>/<model>/<run_id>/
# 例：results/p0/e1_consistency/ec_jmf/20261020T160000Z_seed0/
```

`run_id` 建议包含 UTC 时间与 seed；禁止用 `final`、`best` 等无法追溯的命名作为唯一标识。

## 当前运行

| run_id | 实验 | 模型 | 状态 | 备注 |
|---|---|---|---|---|
| a_neural_v1 | P0 v0.2；v0.3冻结补充 | A0–A6 | 140次完成 | [协议、指标、失败边界与复现](p0/a_neural_v1/README.md) |
| a_neural_v03_v1 | 完整P0 v0.3历史训练（已发现语义偏差） | A0–A6 | 历史140次完成 | [固定协议、指标、零支持与复现](p0/a_neural_v03_v1/README.md) |
| a_neural_v03_v3 | 完整P0 v0.3语义修订；A焦点映射仍有限 | A0–A6 | 140次完成 | [修复、剩余缺口与复现](p0/a_neural_v03_v3/README.md) |

## 归档

大型预测文件可按 `.gitignore` 规则不入库；但必须在受限存储中保留，并在 `run.json` 中记录位置与校验和。论文/竞赛使用的聚合结果应可由公开脚本重新生成。

本轮按显式交付要求采用紧凑归档：`report.json`集中绑定配置、代码提交、数据哈希、环境、逐种子指标及失败计数；`README.md`说明复现与失败边界；仅保留预指定`a0_seed0.pt`。不另存逐次日志、预测文件或中间检查点，替代上方通用run目录模板。
