# 原A模型的P1配对训练与C模型对照

本分支以 `feat/a-p0-v03-neural@dec55faa` 的正式v3原模型为P1训练对象；
保留 C `Bill_method@291e94a` 的 `visible_context` 作为固定对照。
`context_residual.py` 提供C对照，`neural_model.py`恢复原NeuralECJMF及A0–A6批处理，
`neural_training.py`提供40轮残差训练、开发集选模、自包含保存重载和T1/T2/T3推理。
模型与训练配置为 `results/p0/c_visible_context/model.pt`、`configs/a_context_p0_v03.json`。

[完整获取、使用、复现和证据边界](../../results/p0/c_visible_context/README.md)；
[正式接口](../../docs/internal/a/A_INTERFACES.md)；
[算法决策和长期认识约束](../../docs/internal/a/A_ALGORITHM_DECISIONS.md)。

原模型恢复的是正式神经模型及机制消融，没有恢复中央差分、独立SMC或旧玩具材料。
原A分支与main不变。骨干是新模型的必要组成，冻结残差训练不是从零训练整个网络。
P0为脚本诊断，不代表真实人物预测效果。


## P1 READY 适配

`ready_data.py`、`ready_model.py`和`ready_training.py`接入B正式ready-v1.0的两任务格式。
`ready_model.py`按配置选择冻结原NeuralECJMF或Context模型；attention-GRU文本辅助模块
实际训练/生成IHBench公开续答，不把回答当人物状态真值。
推理只读取task/input；对话答案不当心智或恢复真值。上下文截断、OOV及实际效果见
[READY正式结果](../../results/p1/a_ready_response/README.md)与[接口](../../docs/internal/a/A_INTERFACES.md)。

## 本分支配对实验

`python -m models.ecr_mwm.p1_comparison --config configs/a_original_p1_comparison.json`
从原分支固定Git提交读取正式v3参数，使用与已完成C分支相同的响应初始化/批次随机序列，
实际进行12轮seed0训练、dev选模、保存重载及最终生成评分。
[正式比较、机制可识别性及复现](../../results/p1/a_original_comparison/README.md)。
A1–A6已恢复，但P1响应路径不消费结构状态，不能据其响应指标判断这些机制优劣；
历史20种子P0消融与本次P1结果分开标注。
