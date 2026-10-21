# 工程脚本

## v0.3 完整发布与 A 接入检查

`python scripts/build_p0_release.py` 生成 `data/p0/v0.3/`：254 条完整原生数据、150/52/52 分割、C 协议导出与带来源哈希的 manifest；`--check` 只检查产物是否最新。它保留 v0.2 和旧 v0.3 补充原稿的字节与签核。

`python scripts/check_p0_release_a.py --a-ref origin/feat/a-p0-v02-ec-jmf` 从本机已有的 A Git 引用提取模型到工作区临时目录，不切分支，逐条执行 254 条训练样本转换与默认参数精确推理；返回实际 commit、数据哈希和失败列表。缺少该引用或新训练接口会显式报错。该命令不训练、评测或生成预测文件。说明见 [`data/p0/v0.3/README.md`](../data/p0/v0.3/README.md)。

## `validate_data.py`

校验 P0 两个批次（v0.1 16 条、v0.2 240 条），按记录的 `schema_version` 自动选择 schema：

- 使用 `jsonschema` 对 [`schema/p0_record.schema.json`](../schema/p0_record.schema.json) 与 [`schema/p0_record_v0.2.schema.json`](../schema/p0_record_v0.2.schema.json) 做 Draft-07 结构校验；
- 跨字段检查：cutoff 顺序、证据链、逐因子证据并集、任务依赖、`Q` 与 `C` 一致性、动作/步骤对齐、资源/取消/完成事件与 `V/F` 一致、P07 输入一致性；
- **人物自述里的剩余步数（「还剩N步」）必须等于任务图算出的客观剩余数**（含嵌套任务的剩余数，中文数字与阿拉伯数字都解析）。2026-10-21 加：A/C 盲审抓到 14 条 P01 B 臂整体少 1，而抽查工作表的四个复选项（单变量性 / §1.4 / Gate 5 / 结论）没有任何一项问"文案里的数字能不能由任务图算出来"——这类一致性交给机器，不加人工格子；
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
OK: 14 records, 7 A/B pairs; schema and cross-field checks passed.
```

只校验单个文件：`python scripts/validate_data.py --file data/p0/p0_samples_v0.2.json`。

## `pair_diff_report.py`

逐字段打印每组 A/B 差异，用于人工确认“只改了一个设计变量”；P07 会额外检查截断前输入一致性。

```bash
python scripts/pair_diff_report.py                       # 全部家族的紧凑差异表
python scripts/pair_diff_report.py --full                # 全部家族的逐字段详情
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

## `build_p0_uncertainty.py`

可复现构建 v0.3 不确定性批次：7 家族 / 14 条，专门填 v0.2 里“schema 声明过但一次没用”的 11 个不确定性档位（`V=UNKNOWN`、`F=UNKNOWN`、`A=UNCERTAIN`、`B=UNRESOLVED`、`C=ACTIVE`、`C=UNKNOWN`、事件级 `person_access=UNCERTAIN`、`person_comprehension=NOT_UNDERSTOOD/UNCERTAIN`、`certainty=PROBABLE/UNCERTAIN`），输出 `data/p0/p0_samples_v0.3.json`。

```bash
python scripts/build_p0_uncertainty.py
python scripts/validate_data.py --file data/p0/p0_samples_v0.3.json
python scripts/pair_diff_report.py --file data/p0/p0_samples_v0.3.json --full
```

每条的 `UNKNOWN` 都是脚本设计出来的认识处境，不是标注者没想清楚：校验器强制 `UNKNOWN` 因子不得带证据、非 `UNKNOWN` 因子必须带证据，所以偷懒的标签会直接校验失败（口径见标注手册 §1.4）。

生成器沿用 v0.2 的口径，不新造惯例：`p0_scripted_policy` 与机制 1:1 固定（contact_cancellation→`continue_if_no_known_cancellation`，comprehension→`act_on_believed_status`，long_term_commitment→`resume_if_committed_and_unfinished`，resource_availability→`execute_if_ready_else_wait`）；理解不到位的一臂跟 v0.2 的 15 个误解臂一样写 `suspend_or_wait`；`indeterminate` 只留给输入不可区分的家族，所以 `V=UNKNOWN` 的 P01-W8-A 仍有点标签（没有已知取消 → 继续）。B 复核时认可的两处刻意破例：P01-S6 两臂期望动作同为 `do_not_resume`（操控维度是信念是否调和，不是动作），以及 7 对里 4 对（P01-S6 / P05-D6 / P02-D7 / P08-S7）A/B 事件条数不等——v0.2 是条数对齐的，这里刻意不对齐，因为操控变量本身就是"多/少一条证据事件"。

**批次状态是 `reviewed`（B 于 2026-10-21 逐对签核，草稿由本脚本生成、签核署名 B，与 v0.2 同一惯例）**，可以交 A/C 复核；但 A 的适配器仍只认 `p0-record/v0.1.0`，接入前它进不了训练输入。`split.calibration` 仍为空——那要 C 先定校准协议。

## `audit_packet.py`

从任一批次里抽一批**可复现**的人工抽查样本，打印成带空白签核框的工作表：`docs/annotation/p0_spot_audit_v0.2_seed20261021.md`（10 对 / 20 条，8 个机制各 1 对 + 哈希排序补齐，共 39 个框——`future_leak` 那对只有 3 个，它的单变量性由输入一致性预检代劳）与 `docs/annotation/p0_spot_audit_v0.3_all7.md`（v0.3 全批 7 对 / 28 个框）。两张表都已在 2026-10-21 由 B 勾满。每对给出事件条数、逐字段差异数、变化因子、差异字段、期望动作与政策，并把不确定档位和零证据因子挑出来——这三样正是审计人要判的三件事（单变量性、手册 §1.4、Gate 5）。

```bash
python scripts/audit_packet.py --records 20 --seed 20261021
python scripts/audit_packet.py --file data/p0/p0_samples_v0.3.json --records 14 --seed 20261021
```

**生成时脚本不写任何结论**：复选框全空，勾由人打；人打勾后的文件不再由脚本重写，因此它不进 CI 的 `git diff --exit-code`。为防止"重新生成"把签名抹掉，输出文件里已有 `- [x]` 时默认拒绝覆盖（要重审才加 `--force`）。三道闸：改 seed 或抽样规则由 `tests/test_data_validation.py::test_audit_packet_sample_is_pinned` 拦住，签核表的勾选数与结论行由 `::test_spot_audit_packets_carry_bs_signoff` 钉住，拒绝覆盖的行为由 `::test_audit_packet_refuses_to_clobber_a_signed_sheet` 守住。`--seed` 换一批样本，旧的签核不能复用。

## `p0_quality_report.py`

从数据实算交接给 A / C 的一页质量报告，对应 `docs/annotation/label_quality_plan_v0.1.md` §4。对 `validate_data.DATA_FILES` 里的每个批次输出规模、校验结果、证据覆盖、悬空引用、cutoff 完整性、P07 输入一致性、域/划分分布和文件 SHA256，并列出 **schema 声明过但数据里一次没用到的枚举取值**；最后把同一 `schema_version` 的批次合并统计，避免“缺口只存在于单个文件”这种误读。

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

## `probe_ext_holoassist.py`

外部数据可行性探查（**不进主实验，只回答能不能用**）。读 HoloAssist 的 `data-annotation-trainval-v1_1.json`（117 MB，CDLA-Permissive-2.0），输出四组判断依据，并可选导出 A 因子对照样本。

```bash
python scripts/probe_ext_holoassist.py --anno /path/to/anno.json
python scripts/probe_ext_holoassist.py --anno anno.json --export pairs.jsonl --per-group 1135
```

实测结论（2026-10-21）：T1 正负比 77:1 **不可用**；T2 覆盖 54.5%；A 因子清洗后 3,944 vs 1,135。详见 [`docs/data/external_datasets.md`](../docs/data/external_datasets.md)。

注意字段字面量：官方 README 写 `corrected by performer`，实际是 `Wrong Action, corrected by student`；按文档匹配会得到 0 条。

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
