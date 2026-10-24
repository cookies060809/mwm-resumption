# READY P1 实际适配与文本续答训练

按B正式ready-v1.0两任务交付接入：既有P0六状态 + IHBench公开baseline回答蒸馏。
当前不是仅格式检查：已训练神经文本编码/注意力GRU解码器，完成dev选择、保存重载及无teacher-forcing生成。
它不生成新的恢复或信念真值，不代表真人恢复预测。

## 本次真实执行

正式12轮预算在test评分前固定；较早40轮尝试仅运行train/dev，停止后未产生正式结果。
运行seed：[0]，每seed 12轮；保留预指定首个seed，不按test挑选。
响应train/dev/test=288/71/69，对话组31/7/7。
seed0 dev NLL：初始7.9722，选中epoch12，最低4.3626。
保存重载最大误差0.0；C结构化模型权重保持不变。

|test指标（公开回答蒸馏一致性）|值|
|---|---:|
|样本/独立对话|69/7|
|token NLL（UNK投影）|4.6630|
|perplexity（UNK投影）|105.9562|
|casefold token exact match|0.0000|
|unigram token F1|0.2308|
|EOS结束率|0.9710|
|参考答案词表外token率|0.0453|

这些是已发布GPT-4o Audio回答的模仿指标，不是回答正确性、任务成功率或T1/T2恢复预测指标。
小模型从随机初始化训练，没有预训练语言知识；低分/泛化不足应如实解释，不以训练损失下降冒充实用效果。
源公开语料在此前状态诊断中已被检查，故不称全新盲测。

## 输入编码、任务隔离与限制

train-only词表2901；角色编码，system头/尾各96tokens、较旧history预算320，最新用户打断完整保留。
test system截断69/69行，history截断48/69行；完整统计见report.json。
system很长，本模型没有完整理解整个知识库。答案不截断；NLL/PPL基于未知词映射为UNK后的词表，
同时报告OOV；生成的exact match/token F1则与完整原参考token比较，不把参考未知词抹掉。
推理仅读task/input；messages含训练答案，绝不送编码器。文本辅助模块不写入世界/人物理解、信念或承诺。
READY六状态输入缺完整horizon和interrupting_task；从显式事件识别主goal和已见子目标，
未见步骤/父子关系保留未知。部分子图不能被宣布完整完成；不根据target或id补来源标签。
六状态路由仅输出T3，未定义T1/T2；原P0完整输入入口继续支持已有T1/T2。
对话行六状态mask全部0，未把回答文本改成六变量标签；P0数量未与原数据重复拼接。
当前是任务分离的辅助生成适配，不是联合训练文本理解/信念更新。B/C仍需定义真正的公共在线语义接口。

## 复现与推理

```bash
python -m pip install -r requirements-dev.txt -r requirements-neural.txt
python -m models.ecr_mwm.ready_training --config configs/a_ready_p1.json
python -m models.ecr_mwm.ready_training --predict results/p1/a_ready_response/model.pt --data data/training_ready/v1/test.jsonl --limit 3
```

运行器拒绝覆盖已有输出；重跑时在配置副本修改output。默认seed0，--all-seeds才展开固定0–19，
本次未声称已完成20seed。只保留一个含完整Context+词表+文本模块的model.pt、report.json和本文。
训练/生成不需要外部API、GPU或新的文本依赖，没有中间checkpoint或每轮日志文件。
state_test仅为原P0测试数据重用，逐因子mask与适配边界见report.json，不能称P1六状态成绩。
