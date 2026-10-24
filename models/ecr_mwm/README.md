# 完整可见上下文 EC-JMF

本分支采用 C `Bill_method@291e94a` 的 `visible_context`。
`context_residual.py` 提供完整模型，`neural_model.py`提供必要批处理/私有骨干，
`neural_training.py`提供40轮残差训练、开发集选模、自包含保存重载和T1/T2/T3推理。
模型与训练配置为 `results/p0/c_visible_context/model.pt`、`configs/a_context_p0_v03.json`。

[完整获取、使用、复现和证据边界](../../results/p0/c_visible_context/README.md)；
[正式接口](../../docs/internal/a/A_INTERFACES.md)；
[算法决策和长期认识约束](../../docs/internal/a/A_ALGORITHM_DECISIONS.md)。

当前仅一种完整模型；旧模型文件、中央差分/独立SMC入口、旧配置和历史结果已移出。
原A分支与main不变。骨干是新模型的必要组成，冻结残差训练不是从零训练整个网络。
P0为脚本诊断，不代表真实人物预测效果。


## P1 READY 适配

`ready_data.py`、`ready_model.py`和`ready_training.py`接入B正式ready-v1.0的两任务格式。
六状态保留冻结Context模型，新增attention-GRU文本辅助模块实际训练/生成IHBench公开续答。
推理只读取task/input；对话答案不当心智或恢复真值。上下文截断、OOV及实际效果见
[READY正式结果](../../results/p1/a_ready_response/README.md)与[接口](../../docs/internal/a/A_INTERFACES.md)。
