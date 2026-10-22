# A 神经 EC-JMF：P0 正式受控诊断

> 历史结果：随后已确认P02“局部动作强制重承诺”和P04“完成误当撤销”及物理中断/活动相位的A侧语义偏差。数字与模型保留供复现，不作为b-p0-v03/v3纠偏后的成绩；见 `docs/internal/a/A_INTERFACES.md`。

数字由训练入口自动生成。仅为脚本P0，不是真实人物预测性能、心理真值或创新性证明。

协议：`a-neural-p0-v03/v1`；数据：`data/p0/v0.3/p0_samples.json`。
训练源码提交：`9e01a3390fef239f4f091523d09bfd0f39830cc9`；PyTorch `2.11.0+cpu`，CPU。
train/dev/test：150/52/52；每变体20个种子、40轮全批AdamW，统一dev选模。
所有140次均从随机初始化训练，先完成全部dev选择，再统一评价test；未加载旧模型继续训练。
以下为test跨种子均值 ± 样本标准差，仅表示训练随机性，不是人类总体置信区间。

|变体|T1 F1|AUROC|AP|Brier↓|T2 top1|T3六因子macro-F1均值|BCQ macro-F1均值|
|---|---|---|---|---|---|---|---|
|A0|0.8156 ± 0.0404|0.9194 ± 0.0142|0.8988 ± 0.0193|0.1143 ± 0.0081|1.0000 ± 0.0000|0.9176 ± 0.0000|0.8352 ± 0.0000|
|A1|0.7619 ± 0.0000|0.9073 ± 0.0056|0.8873 ± 0.0093|0.1308 ± 0.0043|1.0000 ± 0.0000|0.9170 ± 0.0000|0.8340 ± 0.0000|
|A2|0.7727 ± 0.0000|0.8944 ± 0.0213|0.8597 ± 0.0355|0.1478 ± 0.0083|1.0000 ± 0.0000|0.7400 ± 0.0669|0.4800 ± 0.1338|
|A3|0.8279 ± 0.0339|0.9309 ± 0.0137|0.9157 ± 0.0188|0.1109 ± 0.0073|1.0000 ± 0.0000|0.8271 ± 0.0000|0.6542 ± 0.0000|
|A4|0.8156 ± 0.0404|0.9145 ± 0.0063|0.8911 ± 0.0060|0.1146 ± 0.0082|1.0000 ± 0.0000|0.9176 ± 0.0000|0.8352 ± 0.0000|
|A5|0.8156 ± 0.0404|0.9194 ± 0.0142|0.8988 ± 0.0197|0.1144 ± 0.0081|0.6000 ± 0.4891|0.9176 ± 0.0000|0.8352 ± 0.0000|
|A6|0.7990 ± 0.0421|0.9209 ± 0.0065|0.8787 ± 0.0126|0.1172 ± 0.0090|1.0000 ± 0.0000|0.8522 ± 0.0000|0.7045 ± 0.0000|

每seed有效T1=46、T2=20；T3逐因子有效数：V=51、F=52、A=52、B=49、C=51、Q=52。

## 结构零支持（跨种子均值）

|变体|V|F|A|B|C|Q|
|---|---|---|---|---|---|---|
|A0|0.00|0.00|0.00|0.00|5.00|3.00|
|A1|0.00|0.00|0.00|0.00|6.00|3.00|
|A2|0.00|0.00|0.00|0.00|0.00|0.00|
|A3|0.00|0.00|0.00|13.00|17.00|19.00|
|A4|0.00|0.00|0.00|0.00|5.00|3.00|
|A5|0.00|0.00|0.00|0.00|5.00|3.00|
|A6|0.00|0.00|0.00|3.00|5.00|3.00|

完成140次，失败0次；选中epoch范围40–40。不据此宣称预算最优。
完整逐因子/逐机制指标、有效n、零支持、每seed选中epoch、重载误差及配对seed差均在同目录 `report.json`。

## 从头复现

```powershell
python -m pip install -r requirements-dev.txt -r requirements-neural.txt
python -m models.ecr_mwm.neural_training --config configs/a_neural_p0_v03.json
python -m models.ecr_mwm.neural_training --predict results/p0/a_neural_v03_v1/a0_seed0.pt --data data/p0/v0.3/p0_samples.json
```

实际解释器为 `D:/myProgram/Anaconda3/python.exe`（已有PyTorch），未向仓库安装依赖目录。
每次均真实save/load到内存并校验T1/T2/T3；仅保留预指定A0 seed0的最终选中模型，不按test挑选seed。
预测命令只向stdout输出T1/T2/T3及新模型自身的逐事件证据轨迹，不需要监督标签。

## 预先固定的协议与边界

T1阈值0.5、ECE10等宽箱，indeterminate/null不作负例；T2仅恢复为true且首步属于原目标、未客观完成；T3仅非UNKNOWN且有cutoff有效证据，逐因子计数。Q按图内位置池化。T2缺失计错，零支持标签不丢弃；无双类别AUROC为null。
训练state NLL概率下限1e-8，评价NLL下限1e-12，沿用旧流程；饱和损失不能修复结构零支持。
A1取消接触/理解门控；A2独立BCQ；A3仅保留最近5事件人物记忆并完整重放世界；A4移除事件软对齐及严格等价JS；A5去步骤训练损失但仍评价；A6固定结构门控而保留公共可学习世界先验/行为头。
世界事实、人物可得信息、理解、信念、承诺和进度仍由原结构核区分；仅A1故意作为信息门控负对照。网络不读取自由文本或身份，U为给定结构化证据。
参数总数相同；first_epoch_audit.nonzero_gradient_parameters统计具有非零梯度的参数张量所含元素总数，不是逐元素非零梯度计数。未宣称消融有效参数量完全相等。
严格等价JS可由结构保证为零；A4实际可训练差异主要是事件软对齐，不代表研究计划全部认识损失。
UNKNOWN争议保留掩码；有限结构支持、自由文本解析和误解表示仍有覆盖限制。B仲裁、C公共接口/MENTIS、公平评测及P1校准/泛化尚未完成。

All 52 scripted test records were previously used in v0.2/supplement diagnostics; repeated evaluation, not a new blind holdout

Structured semantics and U remain provided evidence, not learned text understanding.
Known finite-state support gaps are retained; zero-support targets remain in metrics, never silently masked.
This run does not tune transition rules or metric masks using prior or current test results.
Only six additional train records and four additional dev/test records; no human performance or statistical sufficiency claim.

仅保存一份JSON汇总、一份复现说明和一个最终模型；不保存140份日志或中间检查点。

## 交付复核与结果解读

发布包与schema/跨字段校验通过；七个变体的train/dev有限损失与反向传播检查通过。140次保存重载的最大误差均为0；另外从头重复A0 seed0的150条训练、52条dev选模，选中epoch及全部模型张量逐位一致。保存模型亦通过不含监督标签输入的T1/T2/T3与证据轨迹检查。该额外复现检查不作为第141个正式实验样本，未重复推理test。

A3的T1 F1高于A0但T3较低；A4与A0的F1/T3相同，AUROC/AP略低。A0不在所有指标最优，本轮也未证实A4所对应损失带来稳定优势。多数变体T2在20条有效脚本样本上已饱和，不能据此证明真实恢复步骤预测能力。T3标准差为0只表示20个种子下离散预测指标相同，不代表概率分布没有变化。

A0的C零支持5条，分布为long_term_commitment 4条、contact_cancellation 1条；Q零支持3条均在long_term_commitment。它们保留在有效分母和NLL中。已有的放弃后重新行动、commitment_expressed及未由semantic.kind触发的中断等结构覆盖边界尚未修复；需后续明确事件/标签口径并重新冻结修订协议，不能解释成神经训练已完整解决这些状态。B标注、C模块和公开schema本轮均未修改。

本轮仅重跑A0–A6的既有机制实现，未扩大为完整研究计划的全部消融。现有C公共接口/MENTIS评测与P1真实行为、独立校准和泛化结论仍待完成。52条test均有既往诊断暴露，不把此次固定协议重训称为新独立盲测，也不将v0.2与v0.3聚合差异归因为数据扩充的因果收益。
