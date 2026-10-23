# 给 A/C：可直接使用的训练集 ready-v1.0

**推荐从本目录开始训练。无需下载、人工标注或审批，读取检查和小型基线只需 Python 标准库。**

这是一个统一格式的两任务训练包：项目正式 P0 提供六变量脚本监督，IHBench 已发布的 GPT-4o Audio 回答提供中断后续答蒸馏监督。没有用词重叠生成恢复真值，也没有把机器人停顿当成信念标签。真人 P1 记录为 **0**（2026-10-23 决策：项目不做真人采集与标注，P1 以公开数据集交付）；对外口径是公开数据派生的辅助任务，不涉及真人恢复预测。

## 直接开始

在仓库根目录运行（Windows/macOS/Linux 相同）：

```text
python data/training_ready/v1/check.py
python data/training_ready/v1/train_cpu.py
```

第一条检查来源哈希、冻结划分、输入/目标分离和离线精确重建；第二条实际拟合一个六变量朴素贝叶斯基线，并在 dev/test 输出正确数与样本数。无需 GPU、API Key 或 pip 安装。这是接入基线，不是 EC-JMF，也不提供算法效果优越的结论。

## 文件与数量

| 文件 | 六变量 P0 | 中断后续答 | 合计 |
|---|---:|---:|---:|
| train.jsonl | 150 | 288 | 438 |
| dev.jsonl | 52 | 71 | 123 |
| test.jsonl | 52 | 69 | 121 |

每行包含 `task/input/target/state_loss_mask/messages`，另带溯源与划分字段。

- **训练 EC-JMF 六变量模块：** 选择 `task == state_inference`，只把 `input` 传入模型，对 `state_loss_mask[f] == 1` 的因子计算损失。Q 按当前 `task_steps` 加 `NOT_APPLICABLE` 做候选预测。
- **训练对话辅助模块：** 选择 `task == interruption_response`。`target` 是上游已发布模型回答；它不是最优答案保证，也不是人的实际行为。六变量掩码全部为 0。
- **做语言模型 SFT：** 同名 `train_sft.jsonl/dev_sft.jsonl/test_sft.jsonl` 只包含标准 `messages` 列。输入是最后一个 assistant 消息之前的全部消息，目标是最后一个 assistant 消息。建议只对最后一个 assistant 消息计算训练损失。
- 两任务分别采样、分别报告指标；六变量主训练优先使用 P0，辅助任务可选。结构化模型不要把对话回答拼成六变量标签。
- 只能对 train 拟合参数；dev 调参；test 最后评测。不要把本包 P0 与 `data/p0/v0.3` 再拼接，二者是同一批数据。

最小读取示例：

```python
import json
from pathlib import Path

path = Path('data/training_ready/v1/train.jsonl')
rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
state_rows = [r for r in rows if r['task'] == 'state_inference']
inputs = [r['input'] for r in state_rows]
targets = [r['target'] for r in state_rows]
masks = [r['state_loss_mask'] for r in state_rows]
assert len(state_rows) == 150
```

## 输入与监督边界

P0 仅保留目标描述、步骤/依赖、截止事件和截断前事件；排除 notes、设计变量、机制名、标注者、预期行为、状态答案和证据标签索引。监督是已有 P0 脚本预期，继承原有人工复核状态；不声称本次完成了独立双人盲审。

IHBench 输入仅包含操作系统提示、目标/知识库和截至用户打断的已交付话语。没有使用 user_intent、未说出的原句尾部、未来对话或评分 rubric。只采用一个目标回答来源（官方 baseline），每个中断点一条，避免把相同前缀配不同窗口目标混算。428 个中断点来自 45 个合成对话；按完整 conversation 冻结为 31/7/7 个组，属于本项目自定义划分，不能再称原完整官方测试集上的未见评测。

P0 沿用正式版 150/52/52 的划分，127 个故事家族全部保持分组。未知真值从 target 中省略并设置 mask=0。`messages` 包含末尾训练答案，只供训练读取；推理时必须去掉最后一个 assistant 消息。

## 来源、许可、复现

- P0：本仓库 `data/p0/v0.3/p0_samples.json`，254 条。冻结副本 `sources/p0.json`；不新增对该项目数据的对外许可授权。
- IHBench：Salimi 等，*IHBench: Evaluating Post-Interruption Recovery in Voice Agents with Structured Workflows*，2026，https://huggingface.co/datasets/bosonai/IHBench ，https://arxiv.org/abs/2606.19595 。数据许可 CC BY 4.0：https://creativecommons.org/licenses/by/4.0/ 。保留上游卡 `sources/dataset_card.md` 和抓取清单 `sources/upstream_manifest.json`。
- 本次改动：抽取文本列、按原对话分组、把已发布回答映射为续答目标、统一接口；没有生成新的人工或模型标签。未含音频、真人原始日志、InterruptBench 或 REBOOT。
- 冻结的文本来源随包提供，`manifest.json` 记录输入/输出 SHA256。`python data/training_ready/v1/build.py` 可离线重建 JSONL；不依赖上游 main 后续变化。
- 本包是可训练的数据交付，也是 P1 的最终数据形态（2026-10-23 决策：无真人采集）；六变量监督数量和标签真实性不能由辅助对话数量替代。

审查日期：2026-10-23。检查和 CPU 基线实测记录见 `validation.txt`、`cpu_smoke.json`。
