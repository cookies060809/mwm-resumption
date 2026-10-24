# Original A / C-context: paired READY P1 comparison

原模型来自 feat/a-p0-v03-neural@dec55faa 的正式 v3 A0；改进版对照来自
feat/a-p1-public-derived-eval@80b2982。原模型在本分支实际重训了续答模块；结构模型冻结。
两个分支都没有用对话回答伪造六状态或恢复标签。

## 配对训练和实际结果

相同 train/dev/test=288/71/69、31/7/7 对话组、seed0、12轮、AdamW、词表与编码、
dev NLL选择、指标和mask。响应头初始化与批次RNG严格匹配C分支，避免构造器参数量混杂。
仅执行一个种子，没有跨种子稳定性结论；本次为已暴露语料上的重复诊断。

|P1公开参考回答蒸馏指标|原A|C改进版|
|---|---:|---:|
|token_nll_UNK_projection|4.663026|4.663026|
|perplexity_UNK_projection|105.956215|105.956215|
|casefold_token_exact_match|0.000000|0.000000|
|unigram_token_f1|0.230831|0.230831|
|ended_with_EOS|0.971014|0.971014|

原A选中epoch 12，dev NLL 4.362643。
响应模块最终参数逐项相同：True；保存重载误差为0。
上下文截断、OOV及完整计数见report.json与上一分支正式报告；最新用户打断完整保留。
这不是回答正确性/任务成功率，完全匹配率为0，不能称为实用续答效果。

## 能否判断谁更好

不能。当前响应损失和生成完全不消费结构化模型，C改进仅作用于恢复hazard；
READY的P1没有该hazard可用的T1/T2监督，对话六状态mask全0。
配对训练后续答参数与分数相同，证明当前任务/连接不能识别该改进，并不证明两种结构模型普遍等效。
READY六状态52条test来自旧P0，不能称P1状态成绩；两模型T3相同也不检验hazard的优点。

## A1–A6机制消融

已恢复原模型完整机制源码，并对七个变体执行最小加载/状态前向检查。
P1续答中消融不在损失或生成路径上：仅共享已实际训练的响应模块，逐变体验证dev响应logit不变。
没有把七次重复相同续答训练充当机制消融；A4/A5是训练损失消融，此处结构损失均未启用。
本轮没有重训七个结构模型；其P1机制效果全部为不可识别。
下表保留旧分支正式P0消融的20种子结果，明确不是本轮P1训练，也不是新盲测。

|历史P0变体|T1 F1|T2 top1|BCQ macro-F1|
|---|---:|---:|---:|
|A0|0.9091 ± 0.0000|1.0000 ± 0.0000|0.9156 ± 0.0000|
|A1|0.8293 ± 0.0000|1.0000 ± 0.0000|0.9156 ± 0.0000|
|A2|0.7727 ± 0.0000|1.0000 ± 0.0000|0.5016 ± 0.1186|
|A3|0.9011 ± 0.0246|1.0000 ± 0.0000|0.7641 ± 0.0494|
|A4|0.9091 ± 0.0000|1.0000 ± 0.0000|0.9156 ± 0.0000|
|A5|0.9091 ± 0.0000|0.5650 ± 0.4977|0.9156 ± 0.0000|
|A6|0.8971 ± 0.0292|1.0000 ± 0.0000|0.8059 ± 0.0342|

### C历史P0方法对照（不是P1消融）

|方法|warm-start次数|T1 F1|Brier|
|---|---:|---:|---:|
|original_frozen|1|0.9091|0.07456|
|head_continue|1|0.9756|0.02817|
|visible_context|5|0.9756|0.02738|
|visible_context_balanced|5|0.9705|0.02734|

C上下文/平衡变体为固定原seed0骨干上的5次模块训练；原A表为20次全模型训练，
不能把两种seed标准差直接当成同一统计设计。C原头续训也达到相同硬判断水平，
旧P0提升不能全归因于上下文结构，更不能外推至本P1任务。

## 复现

```bash
git fetch origin feat/a-p0-v03-neural Bill_method
python -m pip install -r requirements-dev.txt -r requirements-neural.txt
python -m models.ecr_mwm.p1_comparison --config configs/a_original_p1_comparison.json
python -m models.ecr_mwm.ready_training --predict results/p1/a_original_comparison/model.pt --data data/training_ready/v1/dev.jsonl --limit 3
```

拒绝覆盖已有输出；重跑仅在配置副本修改output。旧P0参数从固定Git提交读取，
最终model.pt自包含原A参数、已训练响应模块、词表与配置，独立推理不读取旧Git对象。
只保留最终模型、本文和report.json；没有日志或中间checkpoint。
需要B/C提供可比恢复监督、窗口/步骤与公共接口，或另行明确联合文本-结构训练任务，
现有P1任务无法识别该机制；本轮不编造监督，也不假定恢复已取消的真人采集。
