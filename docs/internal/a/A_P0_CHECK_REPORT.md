# A 迁移与实际 P0 适用性检查

日期：2026-10-20。共享基线：`c62b1563ab6fbd3d91279ad8a63a4cc857f90c0e`；A分支：`feat/a-ec-jmf-p0-adapter`。fetch和远程refs查询已成功，确认该main为执行时最新基线，未合入Bill/qiqi分支。接口仍为提案，未替代B定义或团队人工审签。

## 迁移内容与取舍

迁入通用精确/SMC内核、包入口、选取的DAG/监督mask helper、精简独立配置、适配后A接口、正式算法/风险决策和迁移/六轮记录。另为共享实际P0新增adapter、诊断CLI及8项契约回归测试。

未迁源tests、diagnose_smc、合成故事/玩具转移、toy诊断输出/性能表、临时生成结果、完整本地暂定stream协议、旧执行/验收稿及原计划副本。源目录保持原内容；本次新增迁移计划/审查记录留作本地最终记录。

## 数据事实

实际 `data/p0/p0_samples.json` 是JSON数组，16条、8家族、123事件，schema `p0-record/v0.1.0`，全draft，未划分。领域collaboration_service8/work6/daily_life2。P1 resume全null、censoring全not_collected；16条均缺可选first_step键，非显式null。

数据 SHA256：`d6a8ec78404aed1577d8fce0d667b98caef6deb15d9039fff465d79d35227189`；schema SHA256：`46c3659f11b34a86fa1a5739ad4104c0bed554a38e9d44f52eb599ae35c77689`。

V VALID10/CANCELLED4/FULFILLED2，F READY15/BLOCKED1，A ACCESSED14/NOT_ACCESSED2，B VALID13/INVALID2/UNKNOWN1，C SUSPENDED12/ABANDONED3/COMPLETED1。没有UNCERTAIN接触或所有枚举覆盖；不能把schema可表达状态当已验证分布。

## 方法与可复现入口

使用仓库实际P0，先B schema/跨字段验证，再白名单映射；时间按同日HH:MM检查，不伪造获知时间。进度以实际step_completed及整目标代完成事件重放，与客观cutoff快照核对；本人完成证据仅下界，不推断理解或心智真值。标签/备注/身份扰动仅在内存副本完成，不写回数据。

```bash
python -m pip install -r requirements-dev.txt
python -B scripts/validate_data.py
python -B scripts/pair_diff_report.py
python -B scripts/check_a_p0.py
python -B -m pytest -p no:cacheprovider
```

本次使用Python3.13.7、pytest8.3.4，jsonschema4.26.0安装于临时隔离目录，经进程PYTHONPATH使用，未改全局环境。命令中的`-B`及禁cache避免工作树生成物。CI的Python3.11未在本机另跑，代码使用兼容语法，正式CI仍待平台执行。

诊断CLI打印JSON（不提交生成输出），含代码基线commit、adapter/诊断源码SHA256、数据/schema哈希、逐样本检查和未支持项。提交后重跑同一命令即可绑定实际代码commit；本报告数字为真实运行的工程计数，不是性能实验。

## 检查结果

首次检查：B校验16/16通过；pair diff包含8组，P07 PASS；pytest共12项通过（仓库原4项+新8项）；实际P0适配16/16、123事件保留，客观完成证据与cutoff快照16/16一致，禁止字段与隐藏世界文本扰动不改变规定输入通道。原目标T2监督资格9条。

|对照|本次检查和边界|
|---|---|
|P01|保留通知接触差异；隐藏取消不进入人物内容；未实现取消语义理解预测|
|P02|末5事件相同，完整历史保留早前承诺/放弃差异|
|P03|打印完成/未完成的本人动作证据和进度差异保留|
|P04|代完成的世界进度不复制为本人完成证据，保留通知接触差异；不自动认定知情理解|
|P05|世界resource_available/missing差异保留；人物可见工具语义尚需独立解析，当前不宣称正确预测等待|
|P06|父子目标与完成集合分离；B版嵌套first_step不作为原目标条件T2|
|P07|屏蔽身份与notes后模型输入完全一致；不是预测概率相同的已训练模型实验|
|P08|接触证据相同，本人陈述差异保留；不自动把已读当正确理解|

补充显式P01/P04接触和P05资源保留检查后已复跑：最终13/13诊断断言通过；pytest仍为12/12通过，B数据校验与pair diff通过。

## 结论及未支持项

当前P0适用于所迁方案的读取、适配、时间/图/证据隔离和对照信息保留诊断。它尚不足以验证完整EC-JMF：无已训练AU/B/C/Q或行为头、外部消息语义未解析、人物图与未知进度未建模、无获知时刻/跨日数据、无P1或独立划分/校准/泛化实验。通用滤波核不是认知模型；本次不以玩具核跑P0伪造恢复预测、状态准确率或优势。

下一步由B复核证据文本/补结构化可达内容和理解监督，A实现具体增广状态与可学习核/公共包装，C提供公平评测与MENTIS适配；合并前按CONTRIBUTING由非作者B/C评审。没有修改schema/data、标注状态或竞赛材料。

## 最终验收

最终复跑命令均exit 0；12项pytest、13项P0契约诊断通过。core源/目标SHA256一致：`d62d4afde24527d515fdf2938d0a88942e29f4bc853c6b2d4f29f927a42ba328`。adapter SHA256 `b7137a64ee0534e80c6fcfb7969e60bf05dedb62e1954a78652bb2aeb7d0567a`，diagnostics SHA256 `264dc5b80d347cf5ed97fdd49fec2e308fd1abf7e1d626ff5223eedad12f70c8`。独立代码复审未发现阻断问题，但不替代B/C团队成员评审。参考配置仅声明预算，未加载为训练运行器。

审核范围为明确白名单；不提交raw诊断JSON、旧toy结果、源tests或临时依赖。B数据/schema哈希不变，未改C主责模块或main。提交前检查`git diff --cached --check`与完整暂存diff；提交/推送状态以Git命令实际结果为准。
