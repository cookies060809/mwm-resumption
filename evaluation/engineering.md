# 本地基线与评测工程

本模块提供六种本地方法、统一指标、外部适配和离线复现工具。当前仅以 `integration_fixture` 工程样例验证流程，不提供正式 P0/P1 主结果，也不代表 EC-JMF 已实现或已验证。

## 运行

Python 3.10+；本地方法与工程测试使用标准库。仓库全套测试还需安装 `requirements-dev.txt`。

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate_data.py
python -m pytest
python run_full_check.py
```

Windows 可双击 `开始完整自检.cmd`。只运行实验及展示：

```bash
python run_evaluation.py
python tools/build_dashboard.py
```

默认使用种子 0/1/2，外部模型关闭。未配置方法标记 unavailable，指标不伪造为零。真实执行错误使入口非零退出；全部方法不可用时退出码为 2。

## 代码与适用范围

| 位置 | 内容 |
| --- | --- |
| `mwm_eval/local_baselines.py` | B0/B1/B4/B5 规则与记忆方法；B6 逻辑回归、B7 HMM |
| `mwm_eval/schema.py` | 输入/gold 分离、截止、DAG、证据、JSON 和概率检查 |
| `mwm_eval/metrics.py` | T1/T2/T3、AUROC/AP、Brier/ECE、约束、成对诊断、覆盖率 |
| `mwm_eval/calibration.py` | 独立校准划分温度缩放；保持图门控结构零 |
| `mwm_eval/statistics.py` | 按 base_story_id 的配对簇 Bootstrap |
| `mwm_eval/engine.py` | 训练/校准/测试隔离、分组统计、实际输入哈希、错误/成本日志 |
| `mwm_eval/external.py` | B2/B3 HTTP 与 B8/B9/B10/结构化 MENTIS 子进程协议 |
| `integration/mentis_adapter.py` | 调用官方 MentisEngine 的任务适配；不含官方算法源码 |
| `tools/` | 工程样例重建、离线演示/CSV、可校验工程打包 |

B1 是五事件窗参考实现；B6 采用激活/线索等特征；B7 是普通 HMM。它们不声称严格复现 SET-PR、原心理学模型或 SIPS。HMM 潜态只有全部获得证据锚定时才发布语义 C 分布；步骤分布为规则候选的点质量，不能视作学习到的步骤不确定性。

## 数据边界

`data/integration/` 有72条脚本工程样例，train/dev/calibration/test 各18条，生成规则见 `tools/build_integration_fixtures.py`。故事/人物/任务族 ID 按划分隔离，但各划分共享生成模板，不能据此声称跨域泛化。未知与删失从对应任务评分中明确排除；P1不完整窗口的未恢复记录不作为已证实负例。

仓库已有16条 `p0-record/v0.1.0` P0草案。它们尚未映射进本引擎，保持原数据、schema与标注不变。对齐需确认事件词表、时间/窗口、逐因子证据、成对关系和独立划分，不自动把已有 P0 `notes` 或未来脚本结果注入模型输入。工程 schema 不能代替该语义审核。

## 输出与复现

`results/full_run/` 由运行生成：report.md、summary.json、manifest.json、status.json、predictions.jsonl、calibration_predictions.jsonl、comparisons.json、stress.json、error_cases.json；展示工具再生成 demo.html 和 metrics.csv。结果均被 Git 忽略。

manifest 保存代码、输入、标签及配置 SHA256 与环境；逐样例日志保存实际输入事件与哈希。失败样本有记录，已知失败 token 账目保留，未知账目/GPU/费用使用 null。固定种子只对本地随机过程受控；外部默认仅重复运行，声明支持后才转发 seed，仍不保证服务端确定性。

`run_full_check.py` 在临时目录重跑六种本地方法，比较324条测试预测、状态和输入指纹；比较不含耗时和时间戳。`results/verification/` 保存测试、实验、展示、复现与打包日志。此复现仅验证同输入/源码/环境中的一致性，不是独立样本量或算法优势证明。

`stress.json` 仅为中性事件长度敏感性，不能替代完整中断层数/任务数/缺失证据扫参。Bootstrap 只用首种子按故事簇配对，不把多种子当额外人物；小型工程集区间不支持论文显著性结论。

## 外部模型与消融

复制 `configs/external.example.json` 到被忽略的个人配置，配置环境变量并显式加 `--enable-external` 才启用真实调用。密钥不写入仓库。B8/B9使用另行安装的官方 checkout；真实端点、官方运行与 A 模型均不能由本机协议测试替代。B9字符摘要尚未完成严格 token 等量控制。

`configs/ablation_matrix.json` 仅登记 A0–A7 等待交付项；null不是模型实现。完整核心算法、训练检查点、正式数据、预算公平性及主实验仍需实际交付和运行。外部接口说明见 `schema/模型交接协议.md`，官方版本与差异见 `integration/mentis_public_audit.md`。
