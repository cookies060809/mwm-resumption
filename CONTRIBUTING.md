# 协作规范

## 0. 新成员首次设置

1. 仓库 Owner 在 **Settings → Collaborators → Add people** 邀请 A/C 的 GitHub 账号；成员接受邀请。
2. 克隆仓库并安装开发依赖：

   ```bash
   git clone https://github.com/cookies060809/mwm-resumption.git
   cd mwm-resumption
   python -m venv .venv
   source .venv/Scripts/activate    # Windows Git Bash
   python -m pip install -r requirements-dev.txt
   python scripts/validate_data.py
   python -m pytest
   ```

3. 阅读顺序：根目录 `README.md` → `competition/README.md` → `competition/technical_report.md` → `docs/annotation/annotation_handbook_v0.1.md` → `docs/internal/ROADMAP.md`。
4. 首次改动前确认自己的角色与评审人；不要直接推送 `main`。
5. 不提交 P1 原始数据、个人信息、密钥或未经实验支持的结果。

## 1. 角色与评审

| 变更范围 | 主责 | 必须评审 |
|---|---|---|
| `models/`, 算法配置 | A | B 或 C 至少一人 |
| `schema/`, `data/`, 标注手册 | B | A（可训练性）或 C（评测可用性） |
| `baselines/`, `evaluation/`, `integration/` | C | A 或 B 至少一人 |
| `docs/` 中他人主责章节 | 对应章节 owner | 至少一名其他成员 |
| `competition/` 技术方案、PPT、视频、提交清单 | 对应材料主笔 | 至少一名其他成员 + 三人终审 |
| 研究结论、性能数字、对外材料 | 三人共同签字 | A + B + C |

- `main` 分支保持可运行；禁止直接推送未评审的算法、数据或结果变更。
- 每个 PR 至少一名非作者评审。数据与 schema 变更必须由 B 评审；涉及训练接口的变更必须由 A 评审。
- 评审时优先检查：未来泄漏、P0/P1 混用、证据链缺失、预算不公平、结论超出数据支持范围。

## 2. 分支与提交

分支命名：

```text
feat/<area>-<short-desc>      # 新功能，如 feat/ec-jmf-access-gate
data/<pair-or-family-id>      # 数据建设，如 data/p01-p08
exp/<experiment-id>           # 实验，如 exp/e1-p0-consistency
docs/<topic>                  # 文档，如 docs/annotation-handbook-v0.1
comp/<topic>                  # 竞赛材料，如 comp/technical-report
fix/<short-desc>              # 修复
```

提交信息采用 Conventional Commits：

```text
feat(ec-jmf): add access-belief gating prototype
data(p0): add P02 minimal pair
schema: clarify Q label evidence rule
docs: update annotation handbook to v0.1.1
exp(e2): record calibration baseline run
```

## 3. 数据变更规则

1. 同一 `base_story_id` 的 A/B 变体必须放在同一 PR、同一 split，禁止跨训练/测试集合。
2. 新增或修改样例必须通过 `python scripts/validate_data.py`。
3. 每个非 `UNKNOWN` 状态标签必须提供 `evidence_event_ids`、脚本策略或标注证据。
4. P1 原始数据、可识别个人内容、未脱敏日志和受限材料**不得提交**。只提交元数据、模板或经批准派生结果。
5. Schema 变更遵循语义化版本：破坏性变更提升主版本，并在 PR 中附迁移说明；不得静默改变既有标签含义。
6. P0 的脚本标签与 P1 的真实行为标签必须在记录中明确区分，不得合并统计后宣称真实预测能力。

## 4. 结果与实验规则

- 每个结果目录至少包含：`config.yaml` 快照、代码 commit、随机种子、输入数据版本/哈希、逐样例预测、聚合指标、运行时间与成本。
- 禁止手工修改结果文件或把未运行的数字写入 `results/`。
- 报告主结果时必须同时报告 `n`、分层条件、置信区间与失败类型；校准结果需报告 Brier/ECE 及样本量。
- P1 右删失样本不得直接记为 `not_resume`；按方案第 5.9 节剔除或使用生存/hazard 模型，并报告删失比例。
- 任何“优于基线”的结论必须来自相同输入、相同基座、可比推理预算和同一评价切片。

## 5. 竞赛材料规范

- 对外材料统一放在 `competition/`；内部计划与风险记录放在 `docs/internal/`，不进入提交包。
- 技术方案按官方大纲撰写：[technical_report.md](competition/technical_report.md)；最终 PDF ≤10MB。
- 演示视频 MP4，3–5 分钟，≤300MB；答辩 PPT 导出 PDF；佐证材料合并为一个 PDF。
- 所有材料不得出现学校名称、Logo、指导教师信息。
- 所有实验数字必须来自 `results/` 的真实运行，并能由 commit + config + seed 复现。
- P0 脚本结果与 P1 真实行为结果分开表述；没有 P1 时不得声称真实人类预测。
- 提交前按 [submission_checklist.md](competition/submission_checklist.md) 逐项核对，由 A/B/C 三人签字确认。
- 大文件、视频、最终 PDF 不直接提交 Git；放在 `competition/artifacts/`（已忽略）或网盘，并在清单中登记。

## 6. 接口冻结（M1）

W1 结束前冻结以下契约，之后变更需 A/B/C 三方确认：

- 事件字段与合法事件类型；
- 状态因子 `V/F/A/B/C/Q` 的标签与证据规则；
- `EC-JMF.update(...)` 的输入输出；
- T1/T2/T3 预测格式；
- 训练/开发/测试划分字段与泄漏检查口径。

## 7. 安全与隐私

- 不提交密钥、token、`.env`、个人账号凭据。
- 不提交第三方论文 PDF 或受限数据，除非许可明确允许；优先记录 DOI/URL 与核查笔记。
- 发现敏感信息误提交时，立即通知全员并轮换凭据；不要仅用后续提交删除。

## 8. Issue 与 PR

- 任务使用 `.github/ISSUE_TEMPLATE/task.yml`，数据问题使用 `data_issue.yml`。
- PR 必须说明：变更目的、影响范围、验证方式、是否涉及数据/接口变更、是否产生新结论。
- PR 模板中的检查项必须逐项确认。
