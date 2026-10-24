# 当前正式模型

本分支的结构化基础模型为 [C可见上下文完整模型](p0/c_visible_context/README.md)，包括完整参数、
来源与复现说明；新训练默认输出 `results/runs/`，仅最终选中模型及一份JSON汇总。
不保留每轮日志、中间checkpoint或重复CSV/图表。

旧A方法/历史训练结果已从当前版本移除，仍在原A分支 `feat/a-p0-v03-neural@dec55fa`，
未改写历史。所有P0结果仅为脚本诊断，不是P1真人预测证据。

公开派生P1试运行见 [准入、受控状态诊断和限制](p1/a_context_public_probe/README.md)：
模型冻结，无P1拟合；T1/T2未评分，单类状态高分及REBOOT接触标签零支持均如实报告。

READY正式两任务适配见 [P1神经续答训练与复现](p1/a_ready_response/README.md)：
保存完整结构化模型与实际训练的文本辅助模块；seed0完成12轮，按dev选择，
只对公开baseline回答做蒸馏一致性诊断，不代表真人恢复或联合信念学习。
