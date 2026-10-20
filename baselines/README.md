# 基线目录

Owner：C。状态：**六种本地基线已实现；真实 LLM/MENTIS 及正式 P0 比较待完成。** 当前实现统一放在 `mwm_eval/`；下面的分目录树保留为目标组织约定。

## 必须比较的基线

| ID | 基线 | 作用 | 状态 |
|---|---|---|---|
| B0 | 最近动作/最近目标（Recency） | 排除“只看最近事件也够用” | 本地可运行 |
| B1 | 固定 5 事件窗口 | 对应 2017 动态目标识别方向 | 本地可运行；非 SET-PR 严格复现 |
| B2 | 完整历史直接预测（Full History LLM） | 最关键的信息量对照 | HTTP 接口已测；真实运行待完成 |
| B3 | 完整历史 + 结构化 Prompt | 排除字段格式化/提示工程收益 | HTTP 接口已测；真实运行待完成 |
| B4 | 持久目标记忆 | 排除“只增加长期记忆”即可解决 | 本地可运行 |
| B5 | BDI 规则生命周期 | 排除 active/suspended 等普通工程收益 | 本地可运行 |
| B6 | 激活/线索/时长基线 | 排除认知记忆简单模型收益 | 训练型逻辑回归可运行；非原认知模型复现 |
| B7 | 简化贝叶斯目标跟踪 | 排除普通 HMM/粒子近似收益 | 普通 HMM 可运行；非 SIPS |
| B8 | 官方公开版 MENTIS | 相对选定 MWM 基线的增量 | 适配接口已测；官方运行待完成 |
| B9 | 等量历史/记忆增强 MENTIS | 排除上下文变多的收益 | 预备接口；严格 token 等量待完成 |
| B10 | **ECR-MWM（完整方法）** | 待提交主模型 | 未实现 |

## 公平比较六项规定

1. 相同任务定义、P0/P1 划分、截止时刻与关键事件可见性。
2. 同基座语言模型与尽量相同采样设置；记录 prompt tokens、总推理 tokens、时延、算力与成本。
3. 按 `base_story_id` 与人物/任务族分组；同族变体禁止跨训练与测试。
4. 规则/结构化算法报告参数与开发集调参过程，防止 test leakage。
5. 报告置信区间、逐样例预测、失败类型与重要性消融。
6. 若 MENTIS 论文的 oracle 中间标注未发布，不得用自造标签冒充其 gold 或声称复制其 oracle 实验。

## 目录约定

```text
baselines/
├── b0_recency/
├── b1_window5/
├── b2_full_history/
├── b3_structured_prompt/
├── b4_persistent_memory/
├── b5_bdi_rules/
├── b6_activation_cue/
├── b7_bayes_tracking/
├── b8_mentis_official/
├── b9_mentis_memory/
└── b10_ecr_mwm/          # 指向 models/ecr_mwm 的统一入口
```

每个基线目录至少包含：运行入口、配置、依赖版本、输入输出说明、成本记录与已知差异。不得用几行提示词冒充对 INSIGHT/MWCRL/SIPS 等工作的严格复现。

## 运行结果

实现入口为 `mwm_eval/local_baselines.py` 与 `mwm_eval/external.py`，统一运行 `python run_evaluation.py`。当前默认数据仅为工程样例，完整说明见 [评测工程说明](../evaluation/engineering.md)。

结果写入 `results/`，包含配置快照、commit、seed、逐样例预测、聚合指标与成本。禁止手工填写数字。
