# P0 输入与证据契约检查

适用版本：`p0-record/v0.1.0` 的 P01–P08 种子批次；功能代码基线 `bb5c40c`。检查只验证数据读取、适配、证据重放与隔离，不调用滤波核进行认知或行为预测。

## 方法与结果

先执行仓库 schema/跨字段校验，再白名单映射真实 P0。HH:MM 按同日顺序检查；本人完成证据与客观进度分开；标签、备注和身份扰动只作用于内存副本，不改数据。P06-B 的嵌套下一动作不计作原目标条件 T2。

|检查|结果（2026-10-20）|
|---|---|
|实际数据|16条、8家族、123事件；全draft、未划分|
|schema/跨字段校验|16/16通过|
|A/B差异报告|8组，P07输入一致性PASS|
|P0契约诊断|13/13通过|
|pytest|12/12通过（原有4项、新增8项）|
|完成事件重放与客观快照|16/16一致|
|原目标T2监督资格|9条；P06-B遮蔽|

对照覆盖：P01/P04接触差异、P02长期历史、P03完成进度、P04世界与本人证据分离、P05世界资源差异、P06父子目标与T2范围、P07禁止字段隔离、P08相同接触下的本人陈述差异。保留信息差异不等于已正确推断人物信念或理解。

数据SHA256：`d6a8ec78404aed1577d8fce0d667b98caef6deb15d9039fff465d79d35227189`。
Schema SHA256：`46c3659f11b34a86fa1a5739ad4104c0bed554a38e9d44f52eb599ae35c77689`。

## 复现与维护

```bash
python -m pip install -r requirements-dev.txt
python -B scripts/validate_data.py
python -B scripts/pair_diff_report.py
python -B scripts/check_a_p0.py
python -B -m pytest -p no:cacheprovider
```

验证环境：Python3.13.7、pytest8.3.4、jsonschema4.26.0；未另跑CI的Python3.11。诊断CLI向标准输出打印代码commit、源码/数据/schema哈希及逐样本检查，不提交生成输出。

长期保留 `scripts/check_a_p0.py`（命令入口）、`models/ecr_mwm/p0_diagnostics.py`（诊断逻辑）和 `tests/test_a_p0_contract.py`（回归断言）。它们使用仓库真实P0，不是本地旧玩具测试。当前依赖P01–P08标识与种子计数16/123、可选字段状态；扩批或schema变化时，需结合B数据版本显式复核这些预期，保留核心泄漏、时间/图和T2语义检查。它们不是任意未来数据集的通用准入器，也不替代C评测或B人工复核。校验不运行会覆盖数据的种子构建脚本。

## 结论边界

当前数据适合输入与证据契约回归；缺少UNCERTAIN接触和完整状态覆盖。P1尚未采集：resume为null、censoring为not_collected，16条均缺可选first_step键，不能当显式null或负例。

外部消息语义未解析，ACCESSED不推出理解；无独立获知时间、日期或跨日证据。人物任务图/未知进度、可学习AU/B/C/Q、行为头及公共预测包装仍待实现。未验证真实人类恢复预测、概率校准、泛化或基线优势。接口与后续依赖见 [A接口](A_INTERFACES.md)，算法选择及数据划分约束见 [算法决策](A_ALGORITHM_DECISIONS.md)。
