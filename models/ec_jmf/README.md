# EC-JMF

**Epistemically Constrained Joint Mental-State Filter**（拟议算法名，非已发表方法）。

> Owner：A。状态：已接入通用精确/SMC数值内核，具体心智状态转移及公共包装未实现，M1尚待三方评审。低层数值接口与下列公共草案的层次区别见 [A接口](../../docs/internal/a/A_INTERFACES.md)。

## 核心命题

给定外部事件 `e_t`、证据来源、人物可接触线索与上一时刻后验 `b_{t-1}`，输出当前联合后验 `b_t`；随后预测 `H` 内是否恢复及首个恢复步骤。目标是**分离**客观世界状态与人物主观状态，而不是把外部事实直接改写为人物信念。

## 状态

- `W_t = (V_t, F_t, P_t^world)`：客观目标有效性、可行性、世界任务进度；
- `M_t = (B_t, C_t, Q_t)`：人物主观信念、目标承诺、主观恢复步骤；
- `A_t`：接触证据；`U_t`：接触后是否理解/采信的内部辅助潜变量；
- `D_t`：交付/接触证据；`E_t^world`：客观事件证据；
- `O_t^{act}`：截至 `t` 的可观察行动。

## 转移分解（拟实现）

```text
T(z_t, u_t | z_{t-1}, e_t, D_t, G)
= T^W(V_t, F_t | V_{t-1}, F_{t-1}, E_t^world)
· T^AU(A_t, U_t | A_{t-1}, D_t, h_t)
· T^B(B_t | B_{t-1}, U_t, e_t^person)
· T^C(C_t | C_{t-1}, B_t, Q_{t-1}, ξ_t^person)
· T^Q(Q_t | Q_{t-1}, C_t, B_t, G_t^person)
```

约束：`e_t^person`、`ξ_t^person`、`G_t^person` 只能使用人物当时可获得的信息。客观 `F_t` 可用于预测动作物理可完成性，但不能直接写入人物信念或承诺。

## 统一接口（M1 待冻结）

```python
updated = filter.update(
    prior_belief=previous_state_particles,
    world_event=event_record,
    delivery_evidence=person_access_record,
    observed_person_action=action_until_cutoff,
    task_graph=task_graph,
    timestamp=event_time,
)
# updated.particles
# updated.weights
# updated.marginal_state_probs
# updated.evidence_trace
# updated.candidate_resume_prob
# updated.conditional_step_probs
```

## 推断与训练边界

- 小状态空间先用精确枚举/HMM 校验数值正确性；
- 再用 SMC（起始参考 `N=64/128`），记录 ESS、重采样与粒子耗尽；
- 粒子重采样通常不可直接微分。首版采用“子模块监督训练 + 推断时 SMC”，不得声称已完成端到端可微粒子训练；
- 输出头从过滤后的联合后验产生，而不是从答案文本直接产生。

## 必须实现的机制

- **M1 信息可达性门控**：接触/理解不确定时做概率混合，不强制认为知道；
- **M2 承诺—进度一致更新**：保留历史未完成目标与任务依赖；插入任务不自动清空旧目标；
- **M3 反事实一致性**：信息等价对照不应改变人物心智后验；人物信息变化对照应产生合理差异。

## 最小消融

无信息可达性门控 / 无联合承诺—进度更新 / 无可学习门控（规则替代）/ 无反事实约束 / 无恢复位置辅助任务 / 独立估计 B/C/Q。完整清单见研究方案第 5.12、9.3 节。

## 当前状态

- [ ] 接口评审
- [ ] S0 精确滤波原型
- [ ] S1 转移子模块训练
- [ ] S2 联合行为训练
- [ ] S3 约束与消融
- [ ] S4 SMC 与校准
