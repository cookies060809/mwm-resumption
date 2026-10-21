# 给 C：多源数据训练包 v1.0.1

本包可直接读取训练，但它不是“六变量齐全的真实人物 P1”。用户同意公开合成/仿真辅助数据与真实行为分开使用。本包进一步明确：六变量主训练数据为本次新生成的受控 P0 增广，而不是公开来源原本就有的标签。

## 文件与训练顺序

| 目录 | 训练 / 开发 / 测试条数 | 用途 |
|---|---:|---|
| `p0_NEW_controlled_augmentation` | 936 / 312 / 312 | 六变量输出和脚本行为的接口训练、诊断 |
| `tomi_auxiliary` | 5994 / 5994 / 5994 | 官方位置/信念 QA；每个集合其中 1998 条还有规则推导的 A 标签 |
| `casas_real_proxy` | 84 / 33 / 34 | 真实人类的活动返回代理预测，所有六变量监督掩码均为 0 |

每个目录均有结构化 `train.jsonl`、`dev.jsonl`、`test.jsonl`，以及标准 instruction/input/output 三列的对应 `_sft.jsonl`。

先用 P0 训练与检查状态更新模块，再把 ToMi 当独立辅助任务；CASAS 应使用独立的 60 秒活动返回头。不要把“60 秒返回原活动”与“3 个决策机会内恢复未完成目标”混作同一标签或同一个评测结果。辅助任务效果改善不保证六变量联合推断改善。

本包没有给出模型权重，也没有训练或验证 EC-JMF 的实际效果。JSON 转换和验证只需 CPU 与 Python 标准库；C 选择的模型是否能在笔记本训练取决于模型规模。

## 六变量到底覆盖到哪里

| 变量 | 本包直接监督 | 公共来源带来的辅助能力与边界 |
|---|---|---|
| V | 新 P0 中的 VALID/CANCELLED/FULFILLED | ToMi 的事实位置回答不是目标有效性标签 |
| F | 新 P0 中的 READY/BLOCKED | 没有把动作成功或失败直接当作整个目标可行性 |
| A | 新 P0；ToMi 第一阶问题中最后一次物品移动的接触状态 | ToMi 的接触按其场景中的进入/离开、同室观察规则推导，不是真人测量 |
| B | 新 P0 中 BELIEVES_VALID/BELIEVES_INVALID | ToMi 原始答案保留为位置/信念 QA，不改名为 B；UNRESOLVED 暂无直接监督 |
| C | 新 P0 中 ACTIVE/SUSPENDED/ABANDONED/COMPLETED | 没有现成真实人类 C 金标；当前目标类别不等于承诺状态 |
| Q | 新 P0 三步任务中的主观步骤或 NOT_APPLICABLE | 没有现成真实人类主观恢复步骤金标 |

未知真值用 `null` 和 `state_loss_mask=0`。不要将所有缺标项训练成 UNKNOWN 类，也不要用模型猜测补成真实标签。P0 接触不确定的 120 条样本中 B/C/Q 均不监督。详细每类数量见 stats.json。

上传对齐修订（2026-10-21）：已知他人完成的场景依照主仓库现有 P04-A 约定，使用 `B=BELIEVES_VALID, C=COMPLETED, Q=NOT_APPLICABLE`；不再把“已完成”映射成取消信念。完成与取消由相应世界/承诺状态区分。这一修订为 v1.0.1，条数和划分不变。

## P0 是如何得到的

从公开 ToMi 的原始 train/val/test 中取 72/24/24 个不同故事背景作为种子。每个背景追加一个独立的新记录处理任务，使用固定三步依赖和 13 个受控版本：取消知晓/未知晓、他人完成知晓/未知晓、工具可用/阻塞、明确保持/放弃、不同完成进度、接触但误解、接触不确定、以及中断前 ACTIVE 前缀。共 1560 条。

任务新增事件和全部六变量标签由本地确定性脚本产生，并公开 POLICY。它们都是 NEW_controlled_P0_augmentation；ToMi 原作者没有标注这些新增任务。这里的“C 真值”是脚本状态，不是测得的人类心理承诺。

这些 120 个种子共享同一种三步任务及相同增广模板，不能称为 120 个独立任务模板。开发/测试只隔离故事背景，不是模板外泛化测试；当前 P0 主要用于接口与机制诊断，不能用它单独证明现实预测能力或算法优越性。所有对比方法必须获得同样的输入、任务图和脚本策略。

“外界已完成但人物不知”的场景仅给冗余尝试的预期，不生成正式 resume 标签：重复已完成工作不自动等同于推进未完成步骤。

## C 的读取与损失

```python
import json
from pathlib import Path
rows = [json.loads(line) for line in Path('p0_NEW_controlled_augmentation/train.jsonl').read_text(encoding='utf-8').splitlines()]
inputs = [r['input'] for r in rows]
targets = [r['state_targets'] for r in rows]
masks = [r['state_loss_mask'] for r in rows]
```

只有 `input` 是模型输入。`provenance` 中包含场景名称，`sample_id` 包含版本后缀，必须防止这些字段成为特征。`state_targets`、`auxiliary_targets`、标签证据引用都只能用于监督和核验，不能拼回 prompt。

六个固定头分别使用 state_label_map.json 的类别，按 mask 计算监督损失。每个头按其有标签的样本数归一化，再组合损失；全无标签的头跳过。Q 应设计成指向输入步骤集合及特殊值的指针/候选分类，不应把本包三个步骤名写死成通用模型的全部步骤。

ToMi 另外输出 `auxiliary_targets.tomi_answer`；CASAS 另外输出 `auxiliary_targets.activity_return_within_60s`。脚本行为标签的键以 `p0_` 开头，不能当作真实 P1 行为。

SFT 版本只输出存在监督的字段。即使采用 SFT，也需保留这三个来源独立采样/统计；不能用巨量 ToMi QA 淹没 P0 和真实行为任务。

## 划分、证据与校验

- ToMi 保留官方 train/val/test，转换为 train/dev/test。同一故事的六种问题归入同一组；如原始跨集合有完全重复的故事，会从较早集合剔除，绝不把原测试内容移动到训练。
- 新 P0 继承 ToMi 背景的集合，同种子全部变体和前缀在同一集合。
- CASAS 保持此前按人物分组、固定 seed 的划分。历史活动编号为人工 oracle 标签，不能声称模型输入只是原始传感器。
- 不把 CASAS 的传感器事件数当作决策机会。连续事件的窗口与缺失处理见 sources/casas_proxy/README_C.md。
- 运行 `python verify_bundle.py` 检查样本唯一性、证据引用、输入时间截断、分组互斥和关键 P0 对照。
- 运行 `python rebuild.py` 可用包内原始 ToMi 和已有 CASAS 转换记录重建数据。CASAS 原始转换另附 build_casas_proxy.py；获取原始压缩包的来源地址写在交接说明中。

## 来源、许可与未采用的数据

ToMi： https://github.com/facebookresearch/ToMi ，论文 Revisiting the Evaluation of Theory of Mind through Question Answering (EMNLP 2019)。本包使用原仓库自带 tomi_balanced_story_types.zip 中已有的官方数据，未运行生成器重新冒充原数据。按 CC BY-NC 4.0 使用，许可原文在 licenses/。派生 ToMi 背景增广需保留该来源署名、非商业条件及新增修改说明。

CASAS： https://zenodo.org/records/15713190 ，Singla, Cook & Schmitter-Edgecombe (2009), Tracking activities in complex settings using smart environment technologies。原始文件实读 20 个交织活动人物记录。网页未明确展示许可名称；本地转换不意味着已核实公开再分发权利。正式公开数据包/竞赛提交前需核对来源使用条款。

InteRead：已下载逐页恢复时延 290 行/50 个不同人物 ID，以及部分处理后注视数据；本版本未转换为训练特征。它只作为后续恢复时延辅助来源，不计入本包的训练条数。

FANToM：官方声明样本仅供评测，因此未加入训练。 https://github.com/skywalker023/fantom

TEACh：有人工对话/动作和仿真任务状态，但其成功动作、下一子目标不能直接替代 F/Q，下载入口本次返回 403；本包不计入其样本。 https://github.com/alexa/teach

VirtualHome：程序与状态图可用于进一步预条件/客观进度辅助训练，但不提供真实人的主观 Q/C；本次 HTTPS 数据下载端点证书名不匹配，未绕过证书检查，本包不含其样本。 https://github.com/xavierpuigf/virtualhome

最终可报告的是“受控 P0 六变量训练 + 公开合成 ToM 辅助训练 + 真实活动返回代理实验”；目前不能报告“真实人类六变量联合监督训练/完整 P1 已建立”。
