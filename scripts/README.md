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

## `p0_quality_report.py`

从数据实算交接给 A / C 的一页质量报告，对应 `docs/annotation/label_quality_plan_v0.1.md` §4。对 `validate_data.DATA_FILES` 里的每个批次输出规模、校验结果、证据覆盖、悬空引用、cutoff 完整性、P07 输入一致性、域/划分分布和文件 SHA256，并列出 **schema 声明过但数据里一次没用到的枚举取值**。

```bash
python scripts/p0_quality_report.py
```

`human_audit` 读 `annotation.status`，人工复核签完自动变化；`second_reviewer` 无数据依据，恒为 `not recorded`，只能由 A/C 本人声明后另行记录。报告数字不得手工改写，也不得由 B 代 A/C 勾选。

未使用的枚举取值不是装饰：v0.2 有 12 个，其中 11 个是 `UNCERTAIN` / `UNKNOWN` / `PROBABLE` 这类不确定性档位，第 12 个是 `split.calibration`（C 的交接协议要求四档划分，数据只落了三档）。批次可以达标 240 条而机制覆盖仍为空，这个检查就是用来暴露这件事的。检查范围覆盖记录级 `domain` / `split` / `mechanism`、六因子状态和事件级枚举。

## `export_eval_format.py`

把 P0 v0.2 转成 C 的评测协议（`c-evaluation-draft-1`）：`data/p0/eval_v0.2/inputs.jsonl`、`labels.jsonl`，并把映射规则写到同目录 `MAPPING.md`。

```bash
python scripts/export_eval_format.py
```

关键映射：`HH:MM` → 同日分钟、`task_dependencies` → `task_graph.edges`、`person_access` + `person_comprehension` → `{status, understood}`、`indeterminate` → `resume_label=unknown`、`purpose=scripted_p0`。输出经 C 的 `mwm_eval.schema.validate_dataset` 验证通过；`task_family` 在 split 之间零重叠（骨架级划分）。

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

## A 的实际 P0 输入契约检查

`python scripts/check_a_p0.py` 在B校验后检查实际P0的读取、映射、事件完成证据和信息隔离；输出JSON到标准输出，不写数据或生成预测。它不调用认知模型，不替代C评测，细节见 [检查报告](../docs/internal/a/A_P0_CHECK_REPORT.md)。
