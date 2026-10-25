# P1-only EC-JMF

当前主线仅使用公开派生 P1，从随机初始化训练 EC-JMF 本体。不是冻结 P0 骨干，也不使用旧 checkpoint 或历史 Git 对象。历史原/C模型及独立续答结果不代表本轮实验。

`p1_adapter.py`、`p1_data.py` 隔离截止前事件与监督，统一 IH 的 READY conversation 分组；`neural_data.py` 构建 train-only 词表及世界/人物分离特征；`neural_model.py` 配合结构状态与分相联合滤波，将可学习文本/事件门传播为后验，再预测原生窗口恢复概率与条件步骤。步骤上限12，未知依赖不假设已可行，缺失子任务关系不编造。当前 U、人物信息、信念、承诺、人物进度与世界事实分开表示。

```text
python -m pip install -r requirements-neural.txt
python -m models.ecr_mwm.p1_training --config configs/a_ec_jmf_p1.json
python -m models.ecr_mwm.p1_training --predict results/p1/ec_jmf/model.pt --split test --source IHBench --limit 3
```

从仓库根目录运行。配置规定 A0–A6、40轮和固定20个评估种子；实际执行数量及训练结果以完成后的报告为准。开发检查的单种子不能称20种子实验。入口负责读取、真实梯度训练、dev选模、完整模型保存与独立重载、T1/T2和受监督 V 评测。所有 dev 选择完成后才做 test；测试语料历史已暴露，属于重复诊断。

正式产物约定为 `results/p1/ec_jmf/{model.pt,report.json,README.md}`；未生成前不宣称结果已交付，不保留每轮日志或中间检查点。A1取消信息门、A2因子化、A3短记忆、A4去时间因果事件一致性、A5去步骤损失、A6规则门，均作用于当前 EC-JMF 训练路径；不是七次独立续答重复分数。

IH 恢复/步骤是启发式弱监督，单回复和助手轮次窗口分报；REBOOT episode-tail 恢复全为正，未来终点长度不作输入；InterruptBench 只训 V。没有 P1 B/C/Q/U 金标，潜变量输出不等于已验证的理解或信念。源模型/机器人数据不是人类效果证据，规则结构也不是已验证自由文本语义。

[正式内部接口](../../docs/internal/a/A_INTERFACES.md)与[算法决策及长期认识约束](../../docs/internal/a/A_ALGORITHM_DECISIONS.md)说明输入边界、模型责任和结论范围。历史 P0、READY 回答蒸馏及原/C对照保持历史身份，不能混入当前 P1-only 成绩。

## 用户自行运行

以下命令在仓库根目录执行，使用本机已核验的 CPU PyTorch 环境：

```powershell
Set-Location 'D:\Personal\projects\mwm-resumption'
$py = 'D:\myProgram\Anaconda3\python.exe'
& $py -B -m models.ecr_mwm.p1_training --config configs/a_ec_jmf_p1.json --validate
& $py -u -B -m models.ecr_mwm.p1_training --config configs/a_ec_jmf_p1.json --output results/p1/ec_jmf
& $py -B -m models.ecr_mwm.p1_training --predict results/p1/ec_jmf/model.pt --split test --source IHBench --limit 3
```

`--validate` 只做入口和小批量梯度检查，不能代表正式实验完成。正式命令不加 `--seed`，执行 A0–A6 × 20种子 × 40轮；`--seed 0` 仅执行七个变体各一个种子，仍各40轮，不是快速冒烟测试。已有输出目录会拒绝覆盖；重新从头跑可把 `--output` 换成尚不存在的新目录。

固定参数：AdamW，学习率0.003，batch16，权重衰减0.0001，梯度裁剪5，一致性系数0.05，hidden24，文本 embedding32，词表上限6000（当前train实际4432），最多12步，CPU单线程，torch2.11.0；正式评估种子0–19。各变体配对初始化、批次和预算，按相同开发集损失选模，全部选模后再统一test。

修正明确 resume 语义后的140次正式训练尚未完成，没有本轮正式测试成绩。先前修正前跑过的训练不纳入正式汇总。A0首个声明种子完成40轮、开发集选模和重载检查后保存唯一最终 model.pt；其他模型候选仅在内存。全部训练与测试完成后才生成 report.json 和结果 README.md，单独出现 model.pt 不代表消融已完成。当前不支持中断续训。
