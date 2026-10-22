# 当前模型配置

`a_context_p0_v03.json` 是本分支唯一模型训练配置；对应完整 `visible_context`。
40轮全批AdamW训练新增残差，冻结骨干；dev最低原state+T1+T2损失选模，epoch0可选。

`seed`控制单次训练，默认0；`evaluation_seeds: [0,1,...,19]`是固定重复评估集合，
通过 `--all-seeds` 才展开。不得挑测试表现最好的seed。C原实验的0–4集合另记为
`source_continuation_seeds`，不冒称已有20seed结果。
默认不评价test；显式 `--evaluate-test` 在所有dev选择后执行。
详见 [完整模型复现说明](../results/p0/c_visible_context/README.md)。
