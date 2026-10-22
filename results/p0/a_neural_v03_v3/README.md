# A 神经 EC-JMF：P0 正式受控诊断

数字由训练入口自动生成。仅为脚本P0，不是真实人物预测性能、心理真值或创新性证明。

协议：`a-neural-p0-v03/v3`；数据：`data/p0/v0.3/p0_samples.json`。
训练源码提交：`5a72b64b3d602a9554e750b22ee8bc46b5a7deb9`；PyTorch `2.11.0+cpu`，CPU。
train/dev/test：150/52/52；每变体20个种子、40轮全批AdamW，统一dev选模。
所有140次均从随机初始化训练，先完成全部dev选择，再统一评价test；未加载旧模型继续训练。
以下为test跨种子均值 ± 样本标准差，仅表示训练随机性，不是人类总体置信区间。

|变体|T1 F1|AUROC|AP|Brier↓|T2条件top1|T3六因子原始对照值|BCQ macro-F1均值|
|---|---|---|---|---|---|---|---|
|A0|0.9091 ± 0.0000|0.9713 ± 0.0077|0.9648 ± 0.0141|0.0736 ± 0.0056|1.0000 ± 0.0000|0.9578 ± 0.0000|0.9156 ± 0.0000|
|A1|0.8293 ± 0.0000|0.9731 ± 0.0000|0.9693 ± 0.0000|0.0976 ± 0.0042|1.0000 ± 0.0000|0.9578 ± 0.0000|0.9156 ± 0.0000|
|A2|0.7727 ± 0.0000|0.9003 ± 0.0175|0.8736 ± 0.0310|0.1454 ± 0.0060|1.0000 ± 0.0000|0.7508 ± 0.0593|0.5016 ± 0.1186|
|A3|0.9011 ± 0.0246|0.9690 ± 0.0042|0.9607 ± 0.0023|0.0703 ± 0.0066|1.0000 ± 0.0000|0.8820 ± 0.0247|0.7641 ± 0.0494|
|A4|0.9091 ± 0.0000|0.9722 ± 0.0068|0.9666 ± 0.0120|0.0737 ± 0.0056|1.0000 ± 0.0000|0.9578 ± 0.0000|0.9156 ± 0.0000|
|A5|0.9091 ± 0.0000|0.9713 ± 0.0077|0.9648 ± 0.0141|0.0736 ± 0.0056|0.5650 ± 0.4977|0.9578 ± 0.0000|0.9156 ± 0.0000|
|A6|0.8971 ± 0.0292|0.9695 ± 0.0013|0.9658 ± 0.0015|0.0886 ± 0.0070|1.0000 ± 0.0000|0.9029 ± 0.0171|0.8059 ± 0.0342|

本轮T3.A焦点映射未完全确认；六因子值包含该代理，仅作原始对照，不是已对齐B口径的完整成绩。T2是条件分布评分，不是C的端到端输出步骤准确率。

每seed有效T1=46、T2=20；T3逐因子有效数：V=51、F=52、A=52、B=49、C=51、Q=52。

## 结构零支持（跨种子均值）

|变体|V|F|A|B|C|Q|
|---|---|---|---|---|---|---|
|A0|0.00|0.00|0.00|0.00|0.00|0.00|
|A1|0.00|0.00|0.00|0.00|0.00|0.00|
|A2|0.00|0.00|0.00|0.00|0.00|0.00|
|A3|0.00|0.00|0.00|10.00|12.00|16.00|
|A4|0.00|0.00|0.00|0.00|0.00|0.00|
|A5|0.00|0.00|0.00|0.00|0.00|0.00|
|A6|0.00|0.00|0.00|0.00|0.00|0.00|

完成140次，失败0次；选中epoch范围40–40。不据此宣称预算最优。
完整逐因子/逐机制指标、有效n、零支持、每seed选中epoch、重载误差及配对seed差均在同目录 `report.json`。

## 从头复现

```powershell
python -m pip install -r requirements-dev.txt -r requirements-neural.txt
python -m models.ecr_mwm.neural_training --config configs/a_neural_p0_v03_aligned.json
python -m models.ecr_mwm.neural_training --predict results/p0/a_neural_v03_v3/a0_seed0.pt --data data/p0/v0.3/p0_samples.json
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
Remaining finite-state support gaps are retained; zero-support targets remain in metrics, never silently masked.
Transitions are revised from B contract conflicts exposed by prior diagnostics, then frozen before this rerun; no metric/mask tuning.
Only six additional train records and four additional dev/test records; no human performance or statistical sufficiency claim.
P04: understood and adopted completion_by_other is BELIEVES_VALID under B P0 convention; COMPLETED/Q distinguish completion from cancellation.
P02: an isolated started/attempted step after terminal commitment is uncertain recommitment, represented by a learned gate; original event wording still needs B adjudication.
This is a post-diagnostic semantic revision, not a fresh blind test; masks, data and training budget are unchanged.
Own physical interruptions do not require message comprehension; commitment and activity phase are distinct; ambiguous return/preparation retains both active and suspended hypotheses.
B generator notes define P05-D6 A as own progress-channel access and UNKNOWN F as unobserved dryer state; no universal focal-A selector or next-step resource map is provided as model input.
Record-level A is still an input-salience proxy, not a verified exact B focal-event mapping; F retains an evidence-conditioned prior rather than hard READY from any completed predecessor.
Null-goal messages are retained with unassigned scope in evidence traces; no target is inferred from a single modeled goal. B must supply an input-side message association before exact goal-level semantic updates are reliable.
T3.A and the six-factor aggregate are raw compatibility diagnostics because focal-event input scope is missing; BCQ metrics retain their declared meaning.
T2 top1 evaluates the conditional head; it does not include T1 threshold decisions or claim C end-to-end output accuracy.

仅保存一份JSON汇总、一份复现说明和一个最终模型；不保存140份日志或中间检查点。

## 语义复核结果与剩余问题

已对照B分支`origin/qiqi`的手册、v0.3生成器、认识约束说明和签核提交。P04按B的P0约定区分“完成”与“取消”；P02局部动作保留重新投入与终止仍成立的两种解释；本人物理中断不依赖消息U；承诺与活动相位分开，模糊返回/准备不再硬定ACTIVE。无关联目标的消息显式保留在未归属证据轨迹，不编造目标归属。

A0在本轮test的P02长期承诺和P04他人完成两类中，B/C/Q结构零支持均为0；P04的B macro-F1为1.000。但长期承诺类C macro-F1仅0.619，说明扩大支持不等于承诺判断已正确，更不等于B已经仲裁原始“放弃后又开始步骤”的14条事件措辞。全部目标仍保留在原分母，未删除失败或修改B数据/schema/标签。

A4与A0的T1 F1及BCQ指标相同，A3的Brier较低；不能声称全部机制都带来一致增益。20种子只表示训练随机性；含A代理的六因子值不作为已对齐B定义的正式总成绩。

剩余接口缺口：记录级A究竟以哪条输入事件为焦点、null消息指向何目标、下一步必需资源的可输入映射。B生成器明确P05-D6的A是自身进度通道、F未知是烘干机未观察到；A没有把这些审查用notes、gold证据ID或实验机制送进模型。F继续保留独立分布，不从任一前置完成硬推READY。自由文本中的信念与活动含义尚未完整解析；不称本轮已把全部254条语义完全对齐。

相同数据/掩码/预算下从头训练140次、先dev后test，重载误差均0；另独立从头重复A0 seed0及无标签预测检查，结果见交付验证。旧v1指标/模型保持历史原值并标注已知语义偏差；途中v2在test前停止，无正式产物。新增门改变参数化和初始化，不把新旧指标差解释成单项修复的因果效应。本轮仍非新盲测、真实行为性能或创新性证明。

交付复现已确认：A0 seed0从头重训的选中轮次与全部模型张量逐位一致，无标签预测与证据轨迹检查通过。另已将A旧文档中“继续表述只作C证据”的概括按B手册§2.5纠正；当前冻结数据的UNKNOWN仍不擅改，B需在后续数据版本逐条仲裁补证据。此文档纠偏不改变本轮已冻结的数据、模型或指标。
