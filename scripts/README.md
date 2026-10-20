# 工程脚本

## `validate_data.py`

校验 P0 两个批次（v0.1 16 条、v0.2 240 条），按记录的 `schema_version` 自动选择 schema：

- 使用 `jsonschema` 对 [`schema/p0_record.schema.json`](../schema/p0_record.schema.json) 与 [`schema/p0_record_v0.2.schema.json`](../schema/p0_record_v0.2.schema.json) 做 Draft-07 结构校验；
- 跨字段检查：cutoff 顺序、证据链、逐因子证据并集、任务依赖、`Q` 与 `C` 一致性、动作/步骤对齐、资源/取消/完成事件与 `V/F` 一致、P07 输入一致性；
- v0.2 追加：`split` 家族级一致、`person_comprehension` 与 `person_access` 一致、`MISUNDERSTOOD` 需非 `accurate` 解释、`indeterminate` 动作需 `undefined_target`；
- 输出状态摘要、领域/机制/划分统计与错误列表。

```bash
python scripts/validate_data.py
```

退出码：`0` 全部通过；`1` 存在错误。

当前预期结果：

```text
OK: 16 records, 8 A/B pairs; schema and cross-field checks passed.
OK: 240 records, 120 A/B pairs; schema and cross-field checks passed.
```

只校验单个文件：`python scripts/validate_data.py --file data/p0/p0_samples_v0.2.json`。

## `pair_diff_report.py`

逐字段打印每组 A/B 差异，用于人工确认“只改了一个设计变量”；P07 会额外检查截断前输入一致性。

```bash
python scripts/pair_diff_report.py                       # 全部家族的紧凑差异表
python scripts/pair_diff_report.py --full --pair P04     # 单对逐字段详情
python scripts/pair_diff_report.py --file data/p0/p0_samples.json
```

这是审计辅助，不会替代人工判断，也不会因发现差异而自动失败。默认读 v0.2（若存在），否则读 v0.1。

## `build_p0_v02.py`

可复现构建 120 家族 / 240 条的 v0.2 批次：8 个手写种子升级 + 112 个家族按“任务骨架 × 机制”生成，输出 `data/p0/p0_samples_v0.2.json`。

```bash
python scripts/build_p0_v02.py           # 写文件
python scripts/build_p0_v02.py --check   # 只在内存构建并打印统计
python scripts/validate_data.py          # 构建后必须重跑
```

生成是确定性的；改生成器等于改数据，必须重跑校验、`pair_diff_report.py` 与测试。

## `build_p0_seed.py`

可复现构建当前 16 条 P0 种子，输出 `data/p0/p0_samples.json`。

```bash
python scripts/build_p0_seed.py
git diff -- data/p0/p0_samples.json
```

**警告：** 该脚本会覆盖 `p0_samples.json`。若已手工修订数据，先提交或备份；重新生成后必须运行 `validate_data.py` 并检查 `git diff`，不要把未审查的生成结果直接提交。

## 边界

这些脚本只检查结构、引用与基本逻辑，**不替代**：

- B 的人工逻辑复核与 A/C 盲审；
- P1 的双人标注、仲裁与一致性统计；
- 隐私/许可审查；
- 模型实验的统计与复现检查。

新增校验规则时，同时更新 `schema/README.md`、标注手册与测试。
