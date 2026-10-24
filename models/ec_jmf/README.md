# 原A及上下文对照的结构化滤波组件

`structured.py`保留世界事实、人物可得信息、理解、信念、承诺与进度的分离；
`neural_filter.py`用PyTorch在有限支持上精确边缘化；`constraints.py`检查任务图等契约。
本比较分支恢复原神经模型A1–A6拓扑机制，保留READY部分子图保护；
不提供旧float精确/SMC部署或中央差分训练。

长期信息约束与限制见 [算法决策](../../docs/internal/a/A_ALGORITHM_DECISIONS.md)，
使用入口见 [完整模型说明](../ecr_mwm/README.md)。
