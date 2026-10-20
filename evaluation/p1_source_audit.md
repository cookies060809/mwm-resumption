# HoloAssist 与 RFM-HRI 来源审计

本轮只完成公开源可读性、证据类型与候选提取检查，尚无可评分的正式 P1。两个来源使用统一的截止与证据协议、分别保留来源和评价；不能把不同数据集的不同人物拼成同一段心智轨迹。

## HoloAssist

来源：[官方项目](https://holoassist.github.io/)。官方提供动作、对话、错误纠正和多模态记录，也包含眼动；并非只有 RFM-HRI 提供眼动。发布方说明采用 CDLA-Permissive-2.0，具体使用继续保留来源与许可记录。

脚本从 117,011,015 字节的标注文件读取有限前缀，检查前 30 个完整会话。它不是完整数据下载或随机代表性样本。30 会话中有 108 条错误动作，其中 71 条具有可解析的显式纠正事件引用。按每会话最多两条、固定 30 秒未来窗口选出 26 个候选，覆盖 15 个会话、6 类任务；23 个窗口完整，3 个不完整。

候选仅靠显式纠正引用关联，缺失引用不按“最近一句话”猜测。模型输入仅含 cutoff 前已结束的动作与对话，剔除整段 Narration、事后正确性/纠正者标签及未来动作。说过一句话不等于人物已经听懂。未来动作单独用于人工审核；当前恢复标签和 B/C/Q 均为 unknown，不自动转成心智真值。

下一步需 B 审核：是否存在真正的任务中断、原目标和步骤依赖是什么、后续动作是否推进原目标；未完整的未恢复窗口不能标为负例。只有审核与分组划分完成，才能导出正式 P1 并评分。

## RFM-HRI

来源：[官方数据仓库](https://github.com/Cornell-Tech-AIRLab/crashcart-rfmhri-dataset)，[论文](https://arxiv.org/html/2603.05641v1)。审计固定公开 commit，按五类结果各取词典序前五个样本，共 25 个；这是证据检查样本，不是主实验划分。

读取 metadata、带秒级时间段的 transcript、MediaPipe gaze CSV 与事后 survey。眼动表含帧编号和左右眼方向，抽查的 metadata 没有显式 FPS；尚未建立与场景物体的注视映射，不能据此直接标“人物看到了某物”。问卷提供试次后的情绪与机器人纠正偏好，其中有 Top-3 选择题，不能当作动作当时 B/C/Q 的确定真值。

本轮未在公开仓库树中找到独立 LICENSE/许可条款文件，应补充核对论文或作者的具体复用与再分发条件。第三方原始文件保持本地忽略；仅提交匿名聚合数量与来源 commit。

## 重跑与输出

```bash
python scripts/audit_p1_sources.py
python scripts/build_holoassist_candidates.py
python scripts/export_evaluation_snapshot.py --include-source-audit
```

首条需要网络并使用本地缓存。原始缓存位于被忽略的 `data/external/raw/`，详细审计和待审候选在被忽略的 `results/p1_audit/`。提交的 [p1_source_inventory.json](p1_source_inventory.json) 只含聚合统计、来源和局限，不含参与者 ID、原对话、问卷回答或候选原文。
