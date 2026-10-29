# P0 v0.4 仲裁发布版

给 A/C 的正式入口是 **`data/p0/v0.4/p0_samples.json`**：254 条 / 127 家族 / 1,908 事件，
划分仍为 **150/52/52**，记录 schema 仍为 `p0-record/v0.2.0`。**v0.3 冻结保留**，
本版是它之上的 B 侧标签仲裁，不重写历史。

## 改了什么

只有 **14 条** `contact_cancellation` 的 B 臂标签：

| 项 | v0.3 | v0.4 |
|---|---|---|
| `state_at_cutoff.B` | `UNKNOWN` | `BELIEVES_VALID` |
| `state_evidence_by_factor.B` | `[]` | `["e06"]` |
| 事件、划分、预期动作、其他因子 | — | 不变 |

依据：手册 §2.5 判定顺序第 2 条——人物在未接触取消通知后明确说
"还剩三步，回来接着弄"，这是明确的继续表达，应判 `BELIEVES_VALID`；
此前把它留作 `UNKNOWN` 与同一批数据里 215 条 `BELIEVES_VALID` 的取值规则不一致。
这 14 条的 A 臂仍是 `B=BELIEVES_INVALID`，接触—信念的对照因此更干净。

**未改动：** `P01-B`（只有 `return_to_task`，返回动作本身不构成信念证据）、
`P01-W6-A/B`、`P08-S7-B`（取消后无任何事件，`UNKNOWN` 合法）。

## P02 "放弃后开始步骤"的仲裁

14 条 P02 B 臂在显式放弃（"先不做了，别再安排"）之后仍有 `step_started`。
B 的裁决是**维持 `C=ABANDONED` 与 `not_resume`**：手册 §2.6 的判定顺序里，
明确的放弃陈述优先于其后的一般性步骤动作；只有新的承诺表达
（`commitment_expressed` 或明确的继续陈述）才重新打开目标。该规则已写入手册 §2.6。
A 按"终止 + 重新承诺两假设"处理这两条路径，与本次裁决一致。

## 使用

- A：`p0_samples.json` 或 `splits/`；`B` 掩码现在对上述 14 条为 1。**v0.3 上的训练/评测结果作废，需重跑。**
- C：`eval/{inputs,labels}.jsonl`，254/254；标签的 `B` 值随之更新。
- `data/training_ready/v1` 已按 v0.4 重建（`sources/p0.json` 已替换），A/C 直接读训练包即可。
- 不要把 v0.4 与 v0.3 或其他批次拼接。

## 校验

```bash
python scripts/validate_data.py --file data/p0/v0.4/p0_samples.json
python scripts/build_p0_v04.py --check
python scripts/release_manifest.py
```

A/C 独立盲审与仲裁仍未完成，`annotation.status` 仍为 `reviewed`，不得写成 `adjudicated`。
