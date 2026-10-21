# P0 v0.3 完整发布版

给 A/C 的正式入口是 **`data/p0/v0.3/p0_samples.json`**。这是可独立读取的 **254 条 / 127 家族 / 1908 事件**数据集。旧路径 `data/p0/p0_samples_v0.3.json` 仍是已经签核的 **14 条补充原稿**，单独读取它只能得到 6/4/4 条。

| 来源 | train | dev | test | 合计 |
|---|---:|---:|---:|---:|
| v0.2 基础批次 | 144 | 48 | 48 | 240 |
| v0.3 不确定性补充 | 6 | 4 | 4 | 14 |
| **v0.3 完整发布版** | **150** | **52** | **52** | **254** |

完整发布版恰好包含两个来源各一次，没有复制扩量、修改标签或重分划分。家族与任务骨架均不跨 train/dev/test；`calibration` 保持 0。沿用来源中的 B 复核记录，A/C 独立盲审与既有信念标签仲裁仍待完成，本次打包没有增加人工签核。

## 文件与使用

- `p0_samples.json`：完整原生 JSON 数组，A 的适配/训练输入从这里读取。
- `splits/{train,dev,test,calibration}.json`：预分割原生数组；空校准集为 `[]`。只把 train 传给训练函数。
- `eval/{inputs,labels}.jsonl`：C 协议导出，共 254 条输入与 254 条标签，按 sample_id 对齐；标签不拼入模型输入。
- `manifest.json`：每条记录来源、来源/产物 SHA256、分割 ID、枚举覆盖、监督数量和检查结果。

**数据发布版本为 `p0-release/v0.3.0`，记录 schema 仍为 `p0-record/v0.2.0`。** 不要把记录的 `schema_version` 改成 v0.3，也不要将完整发布版再次与两个来源拼接，否则会重复计数。

在仓库根目录执行：

```powershell
python scripts/build_p0_release.py --check
python scripts/validate_data.py --file data/p0/v0.3/p0_samples.json
python -m pytest -q
```

重建用 `python scripts/build_p0_release.py`；它只写本发布目录，保留两个已签核来源及抽查表。

## A 接入

A 的 `origin/feat/a-p0-v02-ec-jmf`（已核查 commit `6baa2ddb60957bce7549ffe6db496f4c73b6a02a`）支持该记录 schema。本地旧 `p0_adapter.py` 只支持 v0.1，须在 A 的新版代码中运行下例：

```python
import json
from pathlib import Path
from models.ecr_mwm.training import p0_example
from models.ecr_mwm.structured import infer

train = json.loads(Path("data/p0/v0.3/splits/train.json").read_text(encoding="utf-8"))
examples = [p0_example(record) for record in train]
assert len(examples) == 150
prediction = infer(examples[0].inputs)["prediction"]
```

不切换当前分支也可复现接入检查（读取本机已有的 A Git 引用，不联网）：

```powershell
python scripts/check_p0_release_a.py --a-ref origin/feat/a-p0-v02-ec-jmf
```

2026-10-21 实测：训练样本转换 **254/254**；默认参数精确推理 **254/254**，概率有限且分布归一。完整数据 SHA256：`93ca37e93442495039950c0f8c4c618fee4b8b178cfc52c3269b33cb9f0f7739`。这是兼容检查，没有训练检查点或性能提升结论；本轮未改 A 的算法源码。

## 评价口径

P07 的 30 条输入不可判别样例保留 `indeterminate` / T1 空标签，不能当负例；UNKNOWN 状态按证据掩码。P04 客观已完成后的重复动作不计恢复；P06 嵌套任务下一步不作为原目标 T2。C 导出的布尔 `understood` 合并了 MISUNDERSTOOD 与 NOT_UNDERSTOOD，研究完整 U 区分须读原生数据。

全量枚举覆盖只剩团队决定留空的 calibration；每个 split 的覆盖计数另列于 manifest。罕见不确定性档位仍只有少量样例，尤其测试档位不能声称已经在训练集充分学习。这里交付的是达到既定数量、包含机制诊断补充的完整 P0；真实行为预测、独立盲审、仲裁与统计充分性尚须后续验证。
