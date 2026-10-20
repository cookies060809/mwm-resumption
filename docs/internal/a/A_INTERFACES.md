# A 算法接口与 P0 适配说明

迁移日期：2026-10-20。A 的原暂定接口已按共享仓库实际 `p0-record/v0.1.0` 适配。B 继续拥有 schema/数据，C 继续拥有评测与 MENTIS 集成；本文件是 A 提案，不宣称 M1 已三方冻结。

## 层次与实际实现

`B P0 → B schema/跨字段校验 → A adapt_record → 世界/交付/人物本人证据 → 待实现的认知转移 → 通用滤波 → 待实现的公共预测包装 → C评测`。

已有的公共草案 `update(prior_belief, world_event, delivery_evidence, observed_person_action, task_graph, timestamp)` 见模型 README。新 `core.py` 仅提供低层 `ExactFilter.update(prior, model, event)` / `ParticleFilter.update(particles, model, event)`，不能直接替代公共包装。

低层 model 协议：`transition(state,event)` 给出前态条件下归一的 `(hashable_state, probability)` 可迭代分支；`log_likelihood(state,event)` 给出只计一次的实际观测 log 似然，无观测时0。SMC使用bootstrap proposal，换proposal须补T/q权重修正。精确聚合和似然归一用log空间；仍受浮点精度和预算限制。

`Posterior` 提供 states/weights、投影marginal、重采样前ESS、是否重采样和转移评估次数。它不是六因子状态类；具体增广状态、状态投影、证据轨迹和可学习转移尚待实现。

## B → A：尊重实际 schema

|正式数据字段|A接收/映射|边界|
|---|---|---|
|schema_version|仅 `p0-record/v0.1.0`|不接受本地 `0.1-provisional` 为正式数据|
|observed_events/cutoff_event_id|全部保留顺序，末事件必须为cutoff|时序非递减，唯一ID，合法goal/step；不自动截掉违规事件|
|time|HH:MM转同日分钟|无日期/observed_at，不能验证跨日或晚到证据；不捏造获知时间|
|task_steps/task_dependencies|observer_graphs，依赖DAG验证|不是人物已知图；嵌套图缺依赖时保持None，不能默认为无依赖|
|interrupting_task|仅身份、父目标、steps进入观察者图|不把cutoff状态快照写进心智|
|actor=person事件|本人动作/陈述的type/goal/step/description可作为人物证据|不把本人陈述当客观世界真值|
|外部事件|原记录仅进入world审计通道|混合description/source/world_effect不直送人物编码器|
|person_access|独立delivery.access_evidence|逐事件，不推出理解，不替代记录级A标签|
|person_access_evidence|保存在world审计记录|不自动作为人物语义；需审计解析器提取可信内容|
|其他外部已接触文本|待独立语义解析|当前保守隔离会损失消息内容，不能称完整认知推断|

输入白名单不含 sample_id/variant/base_story_id、notes、annotation、state_at_cutoff、state_evidence_*、p0_scripted_policy/expected* 和全部P1标签。身份只在诊断/评测外层使用。completed_steps_at_cutoff不作为本适配器输入，而在诊断侧核对事件重放结果。

`adapt_record`只验证选中的输入结构；正式数据接入前须先运行B的完整schema和跨字段验证。该安排使监督/备注扰动不会影响模型输入。适配对象是可变拷贝；调用方不得把world重新拼回person_inputs。可信扩展model仍需信息边界审查，通用内核本身不能阻止恶意hook读世界。

## 进度与监督

`replay_completion_evidence` 累积客观step_completed；明确整目标 `task_completed_by_other` 在世界侧展开该目标步骤。`self_completion_evidence`仅本人完成动作的证据下界，不是完整人物主观已知进度。外部消息即使已接触，也不在此自动扩展为理解或COMPLETED。P04-B可在客观已完成时仍有待恢复主观步骤，禁止用世界完成集合mask它。

`scripted_targets`只在评测侧读P0目标。原目标resume=true且first_step属于原图时T2可用；P06-B的replace_toner属于嵌套下一动作，保留审计但T2遮蔽。Q与未来首步分离。P1 first_step当前16条均缺键，非显式null；不因此修改B数据或凭空生成标签。

P1后续须另定schema与删失：已观察窗口内恢复可用正例，未恢复且完整覆盖窗口才可用负例，其余遮蔽；状态逐因子按证据遮蔽。当前P0脚本目标不是P1观测，不能以not_collected推断负例。

## A → C：明确未实现的包装

`conditional_prediction`已实现 `p=Σw r`、`q(k)=Σw r s(k)/p`。低层helper的 `resume_probability`对应公共 `t1_resume_probability`，`conditional_step_probs`对应`t2_conditional_step_distribution`；p=0返回None并附原因。共享草案对null的序列化需后续三方确认，暂不擅改正式定义。具体行为head未实现，不产生虚假p/q。

六维`t3_state_distributions`、evidence_trace、输入/模型/配置hash、cost、MENTIS适配仍待公共包装实现。未知成本用null，实际无LLM调用时tokens为0；不把估算填写为实测。

## 错误和验证

未知版本/窗口、时序或cutoff错误、重复ID、悬空图/step、环均显式失败。核中负/非有限概率、未归一转移、全零似然、非法预算和超限也显式失败，禁止退回均匀后验或不恢复标签。

运行 `python scripts/validate_data.py`、`python scripts/pair_diff_report.py`、`python scripts/check_a_p0.py`、`python -m pytest`。本次只检验真实draft P0的输入、证据与协议适用性，不代表AU/B/C/Q训练或真实行为预测已完成。
