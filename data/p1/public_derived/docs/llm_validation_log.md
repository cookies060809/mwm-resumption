# LLM 补标日志（P2 层）

## 结论

**本次交付没有任何 P2 层补标。** 全部 2,243 条样本的标签来自 P0（原始标注直接映射）与 P1（转换脚本注释中的
确定性规则），P3（`UNKNOWN` / `NOT_APPLICABLE` / `null`）用于无证据处。

| 指标 | 值 |
|---|---|
| `event.source == "llm_inferred"` 的事件数 | **0** |
| 带 `confidence` / `evidence_quote` 的字段数 | **0** |
| 人工抽检样本数 | **0**（没有 P2 标签可抽检） |
| 由 LLM 生成的 `p1_observed_resume` 值 | **0** |

## 为什么没有做 P2

任务书 §3 把 B（主观信念）与 C（承诺状态）列为 P2 候选：「当只有事件文本、没有显式承诺标签时」。
本交付里 B 与 C 都能落在更高层级上，因此按优先级 P0 > P1 > P2 > P3 不必动用 P2：

- **IHBench**：`user_turn_{t}_interruption_type` 是数据集自带的六分类标注，C 的 `SUSPENDED` 由
  「话语被截断」这一标注事实（`assistant_turn_{t}_original` 非空，428/428）直接成立（R3/R7）；
  B 由该标注类型按 R6 分组得到。两者都是 P1 规则，不是文本臆测。
- **InterruptBench**：`updates_type`（`raw/3mixed.json`）是逐条人工标注，其余场景文件的类型标签来自
  作者自己的场景命名并与 `updates_type` 的言语模式一致（T3）。C 采用任务书 §2.4 规定的映射
  （addition→ACTIVE、modification/revision→SUSPENDED、retraction→ABANDONED），属于项目规定而非模型推断。

需要说明的取舍：把 B 做得「更精细」的唯一途径是让模型逐条阅读对话文本再猜信念值。那会引入 428 次没有标注依据的
主观判断，而任务书同时规定「绝不让 LLM 编一个看起来合理的值而不留痕迹」并要求 ≥10% 人工抽检——本环境没有可供
抽检的人工标注方，因此**宁可保留规则粒度与 `UNRESOLVED` 这类保守取值，也不制造看似精确的标签**。

## `B=BELIEVES_INVALID`：从「无合规来源」到「找到 1 条」的检索记录

初判为不可补，复核后**推翻**——关键澄清：`B=BELIEVES_INVALID` 不需要是「错误信念」，
「行为者在目标仍有效时把它当作无效」这一**行为证据**就足以支撑，且不能由 V 复制得来。

走过的检索（含否定结果，避免重复劳动）：

1. **IHBench 目标级撤回**：428 个中断点上跑两组窄规则。
   - 「用户明示拒绝 ∧ rubric 要求改道」命中 3 条（`skip the birthday` / `not that one, send … instead` /
     `i do not want to be recorded`）；
   - 「用户取消 ∧ rubric 尊重取消」命中 2 条（`i changed my mind` / `nothing else`）。
   逐条读文本后**全部否掉**：这些都是在**限缩做法**（改邮箱、不念有效期、不录音），目标本身要继续 →
   目标层面 `V=VALID` 且 `B=BELIEVES_VALID`，标成 BELIEVES_INVALID 会违背 B 的字段定义。
2. **IHBench `baseline.parquet`（428 条 GPT-4o 实际回答）**：搜行为者的**言语式**放弃 →
   1/428 命中且为正则误报（"…may I proceed with…"，是在继续）→ 不能证信念。
   但同一批数据已按规则 **R10** 作为**第二行为者**独立成样（v1.5），用 R8 的内容级判据给出
   true 313 / false **115**，把 `observed_not_resume` 从 23 提到 138 —— 这是恢复负例的增量，
   不是信念档位的增量。
3. **REBOOT 冻结样本 → ✅ 成立**：`sample_recovery-demonstration` ep52
   `failure_mode="freeze"`，`language_description`=
   "Robot freezing after alignment with goal; **complete object insertion and release object**"，
   `episode_type="recovery"`、`recovery_started_at_frame=570 > induced_at_frame=390`。
   → 机器人**停止动作**（信念的行为证据）⟂ **同一标注断言该目标可完成**（客观 V=VALID）。
   两个标签取自不同标注字段，不构成 V→B 复制。落为规则 **B15**，产出 1 条样本
   `rbt_16mm-cylinder-install_ep52_f01_fail`（V=VALID, F=BLOCKED, B=BELIEVES_INVALID, C=SUSPENDED）。
   其余失败模式（misalignment / slip / jamming / premature_release / delayed_start …）描述的是
   **工件或抓取状态**，不是行为者放弃，因此**不触发** B15 —— 这也是本档只有 1 条的原因。

**现状与定性**：该档已实例化，但**统计上不可用**（n=1）。要把它做成可用类别，只有两条合规路：
a. 申请 REBOOT 主仓 `REBOOT26/datasets`（未授权 401）：其 benchmark 跑的是 policy rollout，
   「policy 中止而 expert demo 证明可完成」的样本按 B15 同一条规则即可批量产出；
   需作者提供的字段：`episode_type`（含 policy rollout）、终止帧与终止原因、failure_mode 词表、
   以及每 task 是否存在成功 expert demo（作可行性标注）。
b. 找带**可行性 oracle** 的公开 agent 轨迹语料（错误判不可行 / over-refusal 类），
   前提是该语料里存在「中断事件」，否则不满足 P1 构念（本轮已排除 SWE-agent 轨迹族：有放弃言语、
   有 gold patch 作可行性，但**无中断事件**）。

## 若后续启用 P2，本文件必须记录的内容

1. **调用格式**（任务书指定模板，逐字使用）：

   ```text
   You are a data annotation assistant. Given the event sequence and task context below,
   infer the person's subjective belief (B) and goal commitment (C). Output ONLY valid JSON:
   {"B": "...", "B_confidence": 0.0-1.0, "B_evidence": "quote from text",
    "C": "...", "C_confidence": 0.0-1.0, "C_evidence": "quote from text"}
   If evidence is insufficient, output "UNKNOWN" and confidence 0.
   Event sequence: {observed_events}
   Task steps: {task_steps}
   ```

2. **落盘位置**：`processed/p1_llm_annotations.jsonl`，每条含 `sample_id`、`field`、`value`、
   `confidence`、`evidence_quote`、`model`、`prompt_hash`、`temperature=0`、`seed`。
3. **合并规则**：`confidence < 0.6` 或 `evidence_quote` 为空 → 丢弃该值并回退 P3（`UNKNOWN`），不写入标签。
   `evidence_quote` 必须能在对应原始标注字段中逐字检索到（由 `merge_and_validate.py` 校验）。
4. **抽检**：按 `source_dataset` 分层随机抽样 ≥10%（`random.seed(20261022)`，抽样清单写入本文件），
   由**人工**逐条判定合理/不合理并记录错误类型（信念越界为 V 的复制、把 `SUSPENDED` 误判为 `ABANDONED`、
   把「重新提及目标」误判为恢复）。人工未参与时，本项必须写「未执行」而不是给结论。
5. **事件级留痕**：任何 P2 结果写回 `observed_events[].source = "llm_inferred"` 并附
   `confidence` + `evidence_quote`（schema 已用 `if/then` 强制这两键存在）。

## 校验器已有的相关保障

`merge_and_validate.py`：
- `source == "llm_inferred"` 而缺 `confidence`/`evidence_quote` → 硬错误；
- 若所有 `V=CANCELLED` 样本都被写成 `B=BELIEVES_INVALID` → 报警「B 疑似从 V 复制」；
- `C=ABANDONED` 且 `p1_observed_resume=true` 之类的矛盾组合 → 报警。
