# 分支整合与 A 模型验收

## 整合来源

| 分支 / 提交 | 与原 Bill 的差异 | 处理 |
|---|---|---|
| `main` / `f74b9ce` | B 的抽审签核、v0.3 升为 reviewed、公开数据审计，以及 P01 通知步骤数修正 | 合入；240 条主批次采用 B 修正版，14 条补充单独运行 |
| `qiqi` / `7079990` | B 数据签核；已包含在 main | 由 main 一次合入，不重复覆盖 |
| `feat/a-ec-jmf-p0-adapter` / `075fa99` | 较早的 A 数值内核与旧适配器 | 原 Bill 已包含 |
| `feat/a-p0-v02-ec-jmf` / `6baa2dd` | 新结构化转移、完整 U、精确/SMC、T1/T2/T3、参考训练器和机制开关 | 已合入并实现 C 侧可运行训练、评测和检查点 |

此次只写 Bill。A 的算法源码保留原实现，B 的数据、标签和 split 保留原文件；未提交个人汇报、密钥或第三方原始记录。仓库中的团队技术接口与 B 签核表来自对应分支，不是 C 代签。

整合期间 B 又在 main 提交 `1fb1e70`，将 P01 文本中的“剩余三步”修正为“剩余两步”，并增加独立校验。现已同步其生成器、导出、复核注记和测试；主批次修正版 SHA256 为 `3ca55cc51d50b8f38eed48053d78b8232b0708b4cfd71e1eeb6f6275321729ab`，不混用旧数据指纹。

## A 实际交付范围

`models/ec_jmf/structured.py` 是有限状态的结构化转移模型；`models/ecr_mwm/structured.py` 输出 T1 恢复概率、T2 条件步骤分布和 T3 状态分布；`training.py` 通过中央差分训练转移与行为头。无新增机器学习框架依赖，不是神经文本模型或可微粒子训练。A 本轮未上传已训练权重；C 的整合入口实际从 train 生成可复现检查点。

旧 README 没有同步新实现，现已更新。MENTIS、神经文本编码器、真人 P1、独立 BCQ 与等量历史对照仍未完成；不能仅凭“模型代码已上传”宣称这些已经完成。

## 无损输入与公平比较

`c-p0-v02-adapter/1.1.0` 在所有 P0 方法共用的 observation 中新增严格校验的 `structured_evidence`。它只含截止证据，保留 MISUNDERSTOOD 与 NOT_UNDERSTOOD 的区别、误解解释以及嵌套目标身份/观察者图。A 白名单往返和 C 投影必须同时一致，拒绝监督字段、未来事件或不同历史。B1 两份历史一起截为最近五条。观察者图不复制为人物知识，未知人物图继续保持未知。

B10 由 C 的 `integration/a_model.py` 调用 A 原实现；只在 train 上 state/joint 各训练一轮，固定学习率 0.05、阈值 0.5，未依据测试结果调参。B10_REFERENCE 使用 A 默认未训练参数；六种原有基线不改规则。P07 完全相同输入才用于训练侧等价约束，不因机制名相同自动配对。

每个种子保存训练输入/监督哈希、参数、初末损失和检查点哈希；记录实际 CPU 时间、转移次数和证据轨迹。此模型不调用 LLM，token 数为实测零；不能把缺失的 LLM 结果也记零。校准维持三档方案，未从 train/dev 切样本，概率保持未校准。

A2/A5 的精确边缘分布偶有 `1.0000000000000002` 一类浮点舍入。C 只在越界及总和偏差均不超过 `1e-12` 时裁剪并归一化，逐次记录修复位置与幅度；其他非法分布仍报错。这是数值兼容处理，不是概率校准。中性事件填充压力测试仍仅针对六种原有基线，不含 A。

## 重跑

```bash
python -m pip install -r requirements-dev.txt
python scripts/run_p0_evaluation.py --profile integrated
python scripts/check_p0_reproducibility.py --results-dir results/p0_integrated
python scripts/export_evaluation_snapshot.py --results-dir results/p0_integrated --output evaluation/p0_integrated_results.json
```

`run_full_check.py` 仍使用 72 条工程样例，只验收六种基线和外部接口的未连接状态；其中 B10 显示 unavailable 不代表 A 源码缺失。A 的包装限定脚本 P0，使用上面的 `--profile integrated` 入口运行。

正式主批次为 240 条、train/dev/test=144/48/48；八种方法 × 20 种子 × 48 测试记录，共 7680 条预测。复现时重新训练，核对全部非耗时预测与检查点哈希，保留证据时间和实际概率。原六基线入口仍保留。

## 本轮结果

主批次 T1 可评分 42 条，T2 可评分 18 条；其余记录仍预测并保留掩码。下表为固定 20 种子的均值；当前参考训练器仅打乱梯度坐标计算顺序，采用精确全批次同时更新，重复种子的结果相同，不能作为额外的独立实验样本。

| 方法 | T1 准确率 | 恢复类 F1 | T2 步骤准确率 | 未校准 Brier |
|---|---:|---:|---:|---:|
| B4 目标日志记忆 | 0.7857 | 0.7692 | 0.8333 | 未输出概率 |
| B10_REFERENCE：A 默认参数 | 0.5714 | 0.6667 | 1.0000 | 0.1842 |
| B10：A 两阶段参考训练 | 0.5714 | 0.6667 | 1.0000 | 0.1793 |

seed=0 的 state 训练损失由 4.70043846 降至 4.70031200，joint 损失由 5.55240421 降至 5.53019883。训练确实改变参数与概率，但未提高本轮 T1 硬决策准确率；步骤成绩与恢复决策成绩的分母不同。不能将步骤得分写成整体恢复预测准确率。

共享快照仅含汇总、输入/代码哈希和检查点指纹；逐样例预测与参数文件在本地结果目录，可由命令重新生成：

- [主批次八方法结果](p0_integrated_results.json)
- [原六基线结果](p0_v02_results.json)
- [14 条独立补充批次](p0_supplement_results.json)
- [A1–A6 单种子机制诊断](p0_ablation_smoke_results.json)

本地验收涵盖全部 159 项 pytest、独立工程自检、7680 条主批次预测与训练检查点复现、640 条补充批次预测复现，以及 288 条机制诊断预测复现。另实际检查 A 的 SMC 八机制推断入口，主结果仍固定使用精确推断。CI 执行全测试、六基线 20 种子复现和 A 的 seed=0 训练复现。

补充批次独立运行（14 条，train/dev/test=6/4/4），规模只支持接口和不确定性诊断：

```bash
python scripts/run_p0_evaluation.py --profile integrated --data data/p0/p0_samples_v0.3.json --output-dir results/p0_integrated_supplement --suite core
python scripts/check_p0_reproducibility.py --results-dir results/p0_integrated_supplement
```

A1–A6 的真实机制开关用下面入口做 seed=0 冒烟诊断，不作为完整 20 种子消融或显著性结果：

```bash
python scripts/run_p0_evaluation.py --profile integrated --methods A1,A2,A3,A4,A5,A6 --seeds 0 --output-dir results/p0_ablations --suite core
```

A2 只移除指定耦合，不是完整独立 BCQ；A3 是最近五事件而不是学到的遗忘；A4 约束在某些参数化下本来就可能恒零。不能因为一次得分相同就声称机制无效。A7 与等容量 HMM/SMC 仍待交付。

## 数据审计对齐

B 新审计将 HoloAssist 限定为错误纠正/步骤恢复的候选来源，不作 T1 主评测；C 的 26 条候选继续是未审记录，不自动进入 P1。RFM-HRI 的公开代码仓库确实可读，C 已缓存固定 commit 并审计 25 个样本；这更新了 B 文档“无下载入口”的可用性判断，但没有补出人物恢复或当时 B/C/Q 真值。RFM 不进本轮训练和主评测，原始转录、问卷和参与者 ID 不入 Git。

本轮仍是脚本 P0 参考实验。测试只有三个任务骨架，重复种子不增加独立人物数；A 因子“最近显著事件”与 B“关键对照事件”的汇总语义尚需共同确认。状态分数仅作映射诊断，不支持真实心理状态或泛化结论。
