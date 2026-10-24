# P0 v0.4 盲审协议（A/C）

## 目的

检验 P0 v0.4 的六因子标签与恢复标签能否被独立读者从**同一份证据**复现。
这是找定义歧义，不是考核一致性；分歧照实记录，不改数据去迁就。

## 你会拿到什么

- `blind_review_v0.4_packet.md`：8 条样本（每机制 1 条），只有目标、任务图、窗口、截断事件与截断前事件。
- `blind_review_v0.4_returns_A.csv` / `_C.csv`：各自填写一份。

**不会给你**：`state_at_cutoff`、`p0_expected`、`p0_scripted_policy`、机制名、家族 ID、B 的备注、证据索引。
不要打开 `blind_review_v0.4_key.json`（B 专用），也不要互相商量答案。

## 怎么填

每行一个盲审样本，列包括 `V F A B C Q resume_label resume_step evidence_event_ids notes`。

合法值：
- `V`：VALID / CANCELLED / FULFILLED / UNKNOWN
- `F`：READY / BLOCKED / UNKNOWN
- `A`：ACCESSED / NOT_ACCESSED / UNCERTAIN / UNKNOWN
- `B`：BELIEVES_VALID / BELIEVES_INVALID / UNRESOLVED / UNKNOWN
- `C`：ACTIVE / SUSPENDED / ABANDONED / COMPLETED / UNKNOWN
- `Q`：task_steps 中的步骤 ID / UNKNOWN / NOT_APPLICABLE
- `resume_label`：resume / not_resume / unknown
- `resume_step`：task_steps 中的步骤 ID，或留空

- `evidence_event_ids`：写你判定所依据的事件 ID，按因子写成 `V:e05; B:e06` 这种形式；没有证据写 `UNKNOWN` 或留空。
- `resume_label`：`resume` / `not_resume` / `unknown`；`unknown` 用于输入本身不可判别。
- `resume_step`：只有 `resume` 时填一个 `task_steps` 里的步骤，否则留空。
- `notes`：写歧义点或你不确定的定义，不要写“猜”。

规则依据：[标注手册](../annotation/annotation_handbook_v1.0.md) §2.2–§2.7。
时间预算：每条 10–15 分钟，共约 1.5 小时。

## 返回

把 CSV 发回 B，文件名保持 `blind_review_v0.4_returns_A.csv` / `_C.csv`。
B 运行 `python scripts/compare_blind_review.py` 生成一致性报告与分歧清单；
分歧由 A/B/C 三方仲裁，`annotation.status` 只有在仲裁记录落盘后才升 `adjudicated`。

## 纪律

- 不查 B 的标签，不看 `data/p0/v0.4/p0_samples.json` 里的同一 `sample_id`。
- 不修改 CSV 的列名或盲审 ID。
- 不确定就写 `UNKNOWN` 并在 `notes` 说明缺哪条证据；不要为了“看起来一致”而猜。
