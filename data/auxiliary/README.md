# 多源辅助训练数据（单独格式，待 A/C 评审）

本目录是新增的辅助训练交接包，不替换 `data/p0/` 的正式批次，也不修改现有项目输入/输出契约。

入口：[给 C 的读取说明](C_multisource_v1/README_C.md)。

| 来源 | 训练 / 开发 / 测试 | 使用边界 |
|---|---:|---|
| 新生成的受控 P0 增广 | 936 / 312 / 312 | 脚本监督六变量；不是公开数据原有的六变量标签，也不是真人金标 |
| ToMi 官方公开合成问答 | 5994 / 5994 / 5994 | 信念/事实 QA 辅助任务；每个划分另有 1998 条规则推导的 A 标签 |
| CASAS 公开真实活动派生代理 | 84 / 33 / 34 | 60 秒活动返回；六变量掩码均为 0；不是完整 P1 |

当前质量状态为 **脚本生成 / 自动校验通过、未人工复核、A/C 接口评审待做**。尚未训练模型；无性能或现实预测能力结论。ToMi 的位置信念不改写成 B 的目标有效性，活动返回不改写成正式任务恢复，客观下一步也不冒充主观 Q。

此包采用独立的 `state_targets` / `state_loss_mask` / `auxiliary_targets` 格式。项目原 `scripts/validate_data.py` 仍只验证其既有协议；本包由以下单独入口校验：

```bash
python data/auxiliary/C_multisource_v1/verify_bundle.py
```

自包含重建：

```bash
python data/auxiliary/C_multisource_v1/rebuild.py
python data/auxiliary/C_multisource_v1/verify_bundle.py
```

只将记录的 `input` 送入模型。`sample_id`、`provenance`、标签和标签证据不得作为特征。SFT 版以 `_sft.jsonl` 结尾；C 若使用固定六头网络，应按监督掩码分别计算损失。

来源、修改说明与许可边界详见包内 README 和 licenses。仓库当前为私有协作仓库；本次上传不表示 CASAS 派生结果的对外再发布许可已核实，不应直接将整个目录开放或作为已完成 P1 提交。
