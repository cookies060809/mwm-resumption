# 当前正式模型与实验

本比较分支恢复原A正式神经模型，使用固定旧v3参数进行P1续答适配训练；
C模型及既有P1结果作为固定对照。没有恢复中央差分/SMC、玩具材料或重复历史结果目录。

- [原A与C的P1配对训练、历史消融及复现](p1/a_original_comparison/README.md)。
- [已完成C分支P1训练](p1/a_ready_response/README.md)：seed0、12轮。
- [C结构化基础模型及原始来源](p0/c_visible_context/README.md)：该页为当时集成的历史记录。
- [此前公开派生P1的冻结状态探针](p1/a_context_public_probe/README.md)：没有P1拟合，T1/T2未评分。

当前P1续答不消费结构状态，不能从响应指标宣称原/C结构模型优劣。
READY六状态仍来自P0；历史P0消融和C模块warm-start结果均单独标注，不冒充P1训练。
正式交付每组仅保留最终模型、报告与复现说明；没有日志、中间checkpoint或CSV/图表副本。
原A分支及main未修改，历史未改写。
