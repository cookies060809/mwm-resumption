# A 新模型：公开派生 P1 准入与受控状态诊断

分支 `feat/a-p1-public-derived-eval`；A模型基线3828635，合入main `87d5eb4`。
模型冻结，无P1拟合、调参、选模或校准。P1包含agent/规格/机器人，不是真人恢复行为。

## 数据与输入准入

|源|总数|可保守映射|test可映射|test独立组|
|---|---:|---:|---:|---:|
|IHBench|856|494|10|1|
|InterruptBench|1815|0|0|0|
|REBOOT|192|177|33|11|

逐源test排除原因：IHBench: {'P1_STEP_BUDGET_EXCEEDED': 48}；InterruptBench: {'P1_NO_TASK_STEPS': 275}；REBOOT: {'P1_GOAL_COMPLETION_NOT_REPRESENTABLE': 2}。
全部mask覆盖和数据哈希见同目录report.json。空步骤不补虚拟任务、超8步不截断；
自身全目标completion无法用旧事件词表忠实表达，拒绝而不冒充他人完成。未提供依赖图时保留None。
只取交付input白名单；目标/事件自由文本不被当前模型理解。IH背景access可能表示用户知情，
故背景内容全部留世界侧；外部事件的接触/理解保留不确定，不从observer注释补造UNDERSTOOD。

## 冻结test的主要状态对照

|源|因子|n|准确率|macro-F1|零支持|
|---|---|---:|---:|---:|---:|
|IHBench|V|10|1.0000|1.0000|0|
|IHBench|C|10|1.0000|1.0000|0|
|REBOOT|V|33|1.0000|1.0000|0|
|REBOOT|C|22|1.0000|1.0000|0|

明确失败：REBOOT恢复截断点的A标签n=11，accuracy=0.0000，zero_support=11。当前事件显著性A代理与该包从恢复行为确定接触的焦点不相同，该桥接未覆盖这些标签，不把它们隐藏或移出分母。

V/C是受限映射下的注释一致性诊断，不是跨域恢复预测有效性证明。
F/A/B/Q次级规则/回溯状态对照、逐actor/截断类型结果及类别分布见report.json；不合成六因子总分。
可映射IH test只剩1个对话组：V全VALID、C全SUSPENDED；REBOOT的V全VALID、C全ACTIVE。
常量标签上的高分不体现区分能力；无监督或零可映射样本的指标留空。

## 不计算的成绩与已查明的问题

C新增上下文残差主要影响T1，T3骨干冻结；本次T1不能可靠评分，因此没有评价新模型相较旧模型的收益。

T1/T2均不评分：P0的decision opportunities与P1的assistant_turn/single_response/episode_tail没有可信换算；
不把未来covered、outcome_time或episode长度输入hazard。固定H=1只让状态探针可运行，不是P1校准窗口。
任务依赖、理解和消息语义未完成对齐，T2还缺原目标未完成步骤的可靠映射。
REBOOT只有恢复正例，且recovery/completion截断本身已含结果，不可混入盲恢复预测。
IH两个行为者共用前缀而标签不同，分别报告；aux test仅3个对话组，不能作稳定泛化结论。

main的READY.md推荐ready-v1.0：其中254条state_inference就是既有P0（非新P1），
428条IHBench是已发布baseline的续答蒸馏文本，当前T1/T2/T3模型无文本生成输出；不伪造续答成绩。
ready包现有check.py离线重建与来源/分组/掩码检查已通过；aux REBOOT train现有掩码检查通过。
公开派生README/dataset_card仍混有v1.5旧断言，实际p1-0.2以state_loss_mask和撤回记录为准。
原merge_and_validate.py及转换器导入不存在的split_for（p1_common.py现为split_map/apply_splits），
原校验/重建入口阻塞；本轮未改B文件，独立执行JSON schema、分组、cutoff、mask与aux投影/哈希核验。

## 实际检查与复现

数据准入检查 2863 条通过；train输入smoke、隐藏背景扰动和监督隔离通过。
仅使用改进后的完整模型；不恢复旧方法、不更新权重，不新建永久测试或临时日志。

```bash
python -m models.ecr_mwm.p1_evaluation --config configs/a_p1_public_probe.json
```

结果仅保留一份report.json和本文；未推送或合并main。

后续可做：B修复交付脚本及更新数据说明；A/C明确事件语义、actor接触、任务图与窗口映射，
再在训练/开发集实现和选择真正P1适配。真人采集已按团队2026-10-23决策取消，不再把它列为待采集条件。
