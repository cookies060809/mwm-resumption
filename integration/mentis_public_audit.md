# MENTIS 官方公开实现核查与本项目接入边界

核查日期：**2026-10-19（Asia/Shanghai）**。这是源码和接口核查记录，不是复现成绩。

## 版本和一手来源

论文的[官方主页](https://mental-world.github.io/)链接到 [mental-world/Mentis 官方仓库](https://github.com/mental-world/Mentis)。主页描述的是物理状态与心智状态耦合的六阶段框架；原论文并非只有物理状态，也不是没有目标或意图。

此次网页检索可见的 main 提交历史首项为 **7c6ea55e007a64233c3a0f987b6d229476f3fdf6**，提交日期 2026-08-16，提交内容为 README 图像宽度修改。将它选作本次接入审查的固定版本；不保证网页缓存即远程实时 HEAD。[官方提交页](https://github.com/mental-world/Mentis/commit/7c6ea55e007a64233c3a0f987b6d229476f3fdf6)、[官方提交历史](https://github.com/mental-world/Mentis/commits/main/)。本次成功读取了该 SHA 的 engine.py 和 LICENSE，其他接口同时核对了 main 的公开源码；正式运行前仍须以本地固定 checkout 完整复核。

## 实际代码入口

| 入口 | 核查结果和用途 |
|---|---|
| [`run.py`](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/run.py) | 官方命令为 `predict --input ... --system mentis/direct` 和 `evaluate`。它读取 JSONL 文件，**不支持本项目的 stdin observation → stdout prediction 协议**。 |
| [`mentis/engine.py`](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/mentis/engine.py) | `MentisEngine(settings)`；异步 `run_sample(record, base_dir="")`。`_pipeline` 调用状态解析、观察生成、动作拆解、分支转移、分支打分，再由 `select_action` 决策。 |
| [`mentis/schema.py`](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/mentis/schema.py) | 官方 `Sample` 包含 `sample_id/target_agent/question/options/story`；`options` 为 `option_id/action_description`；`story` 可为文本、图像或视频。官方输出核心为候选选项 ID。 |
| [`mentis/config.py`](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/mentis/config.py) | `Settings` 是 dataclass，`load_settings` 接受可选 YAML。环境默认使用 `OPENAI_API_KEY`；本项目适配器将显式 MWM 环境映射给它，不自动读取 `.env`。 |
| [`mentis/llm.py`](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/mentis/llm.py) | 官方使用 OpenAI Chat Completions，保存 usage 和调用耗时，支持重试与 JSON schema 验证。分支评价分数是价值准则分数。 |

官方配置公开的默认值包括 model `gpt-5.5`、temperature `null`、每次最大输出 16384 tokens、API 重试 3 和 schema 重试 1。这些只是作者配置，不能视为本项目已经调用或已经付费的记录。[官方配置](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/config.yaml)。

依赖声明为 `openai>=1.50`、`pydantic>=2.7`、`PyYAML>=6.0`；视频还涉及 ffmpeg。此次没有安装这些依赖、下载模型/数据或调用付费 API。[官方依赖](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/requirements.txt)。

## 已实现的 C 方接入

`mwm_eval/external.py` 统一暴露 B2、B3、B8、B9、B10、MENTIS_STRUCTURED，每项支持 `fit/predict/spec/availability`。未配置的方法记录 unavailable，不产生虚构预测。

- **B2/B3**：使用 Python 标准库实际发送 OpenAI-compatible Chat Completions 请求。两者使用同一模型、temperature、输出预算和完整截止历史；区别仅为直接提示与结构化阅读提示。训练标签不写入 prompt。
- **B8**：命令适配器执行 `integration/mentis_adapter.py`，该脚本导入指定官方 checkout 的 `MentisEngine` 并实际调用 `run_sample`。它保留官方算法路径；任务输入与输出由本项目适配。
- **B9**：强制与 B8 共用同一命令、工作目录、仓库和 commit，以 `MWM_ADAPTER_MODE=memory` 增加从截止观测机械提取的原目标事件日志，没有 EC-JMF 更新器。它不是普通单次 LLM 提示冒充 MENTIS。
- **MENTIS_STRUCTURED**：同一官方引擎，以 `structured` 模式增加阅读字段提示。
- **B10**：仅有成员 A 的外部模型命令接口。A0–A7 登记的是配置文件引用和待交接状态，没有替 A 实现或假造模型。

命令协议是**我方集成契约**：stdin 仅为 cutoff observation JSON，stdout 仅为 canonical prediction JSON；模式和方法 ID 经环境变量传递。协议不是官方仓库原生功能。

适配器将同一观察转成文本 story、target_agent、问题和固定候选集合（每个 task_step 一个“窗口内首次恢复于该步骤”的候选，加一个“不恢复”候选）。未按实际答案过滤候选。官方 tie-break 必须用到 sample_id，故在适配器内部使用**仅由 observation 内容产生的哈希**；不传数据集 sample_id、家族、split、gold 或未来结果。

因此 B8 应在报告中称为“**官方公开 MENTIS 在本项目恢复预测任务上的适配**”，而非“复现原文全部实验”。原论文是 situated decision MCQ，本项目是指定目标、截止点及未来窗口的恢复 MCQ，问题分布、候选数与计费开销均可能变化。

官方只给出选项及分支评价，不直接提供本项目 T1/T2 概率或 V/F/A/B/C/Q 后验。当前适配输出硬标签；`p_resume=null`、`conditional_step_probs=null`、`state_probs={}`。不对价值分数做 softmax 后冒充校准概率，不捏造 T3 标签。原始过程和真实 token 统计保存到 metadata，供后续设计显式且公平的状态映射。

## 公平性与未完成项

1. 基座、temperature、每调用输出上限使用显式环境配置；本项目默认示例为 1024 tokens，属于我方预算，并非官方论文默认预算。
2. B8/B9/structured 保持相同候选集合、截止观测和官方引擎。memory 重复的是已有证据；structured 增加字段提示，不增加标签。
3. memory 当前按**字符上限**约束日志。字符相同不等于 token 相同；尚未完成严格等量 token 的 B9 对照，结果不能直接排除额外上下文收益。运行时须结合供应方 tokenizer/usage 做预算匹配与核对。
4. 官方多阶段、多分支调用成本通常高于 B2/B3 的一次调用；必须报告实际调用次数、tokens、latency、失败和存活分支，另行设计相同总预算对照，不能仅凭每次 token 上限声称计算预算公平。
5. 官方 README 表明公开发布的是最小参考系统和直接基线；分析消融脚手架及 oracle/gold 中间过程未公开。本项目不把未公开 oracle 当成已复现部分。[官方 README](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/README.md)。
6. 本地需另行提供 clean 固定版本 checkout、上述依赖和可用模型环境。`--check` 只检查，不请求模型；当前缺这些交付，正式 B2/B3/B8/B9/B10 实验均**没有运行**。

## 已验证范围

`tests/test_external_full.py` 使用真实本机 HTTP 服务与临时子进程验证协议、固定输入、token 账目传递、重试、错误捕获和密钥脱敏。对任务适配的测试注入 StubEngine，验证 `run_sample` 调用及选项映射；**StubEngine 不是官方模型**。

这证明 C 方接口可以运行，不证明真实端点可用、官方 MENTIS 完整环境运行成功、模型质量达标或项目算法有增益。

官方代码为 MIT 许可，代码作者为 The Mentis Authors。此处未复制官方算法源码或数据；日后分发官方代码仍应保留其许可。[固定版本 LICENSE](https://github.com/mental-world/Mentis/blob/7c6ea55e007a64233c3a0f987b6d229476f3fdf6/LICENSE)。
