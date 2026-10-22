# DeepSeek 实际调用评测

后续 B2/B3 v3 已澄清概率输出合同并完成完整重评，B3 无格式失败，最新结果见 [v3 协议与结果](deepseek_v3_format_protocol.md)。本文及 `deepseek_p0_results.json` 保留为 v2 历史实验记录。

本轮使用 B 的脚本构造 P0 v0.3，固定原有 52 条 test；T1 排除 6 条 UNKNOWN，分母为 46；T2 分母为 20。没有加入 HoloAssist/RFM-HRI 真人数据，也没有新盲测集或独立 calibration。测试集已参与此前诊断，不能将本轮结果解释为真人泛化效果。

调用官方 DeepSeek `deepseek-flash`，temperature=0、thinking=disabled，每次内部调用输出上限 4096 token。API 不提供本项目可控的可复现 seed；每个方法只有一次提供商推理结果，并非 20 次独立训练。匿名汇总、指标和输入哈希见 `deepseek_p0_results.json`；原始预测保存在本地忽略目录。

## 成绩与验收

| 方法 | T1 准确率（46条） | 恢复类 F1 | T2 步骤准确率（20条） | 输出失败（52条） |
|---|---:|---:|---:|---:|
| B2 | 71.74% | 0.7547 | 100% | 0 |
| B3 | 56.52% | 暂不发布 | 70% | 8 |
| B8 MENTIS | 76.09% | 0.7843 | 90% | 0 |
| B9 MENTIS + 机械记忆 | 78.26% | 0.8000 | 75% | 0 |

B9 的 31 条缺失结果全部补齐，复用原有 21 条，最终 52 条有效；充值后新增已知用量 1,122,960 token。全部历史尝试去除复用记录后，共 374 条样本执行记录、4,263,959 个已知 token；53 条失败记录没有可用 usage，故不是完整账单。174 项本地测试通过，包括余额不足立即停止、token 阈值阻止下一样本的假接口测试。实际调用已结束，不会自动继续重跑。

## 接口与计费记录

B2/B3 的旧接口未给出状态标签词表，初次 104 条请求仅 2 条通过输出校验。这些付费调用保留用于核算。统一补充合法标签、因子含义与任务步骤列表后，完整重跑全部 104 条，没有只挑错题重试，也没有将 gold 传给模型。最终 B3 仍有 8 条概率分布校验失败；准确率按失败计错，F1 按 C 协议暂不发布，不进行事后归一化修补。

B8 使用官方 MENTIS 仓库 `mental-world/Mentis`，固定提交 `7c6ea55e007a64233c3a0f987b6d229476f3fdf6`。上游代码未改；适配器将项目恢复步骤映射为 MCQ，通过 SDK 层转换 DeepSeek 参数并关闭 thinking。B9 在相同流程中附加最多 4000 字符的机械目标记忆。这是项目任务适配，不能声称复现论文原始数据集的成绩。

MENTIS 一个样本需要多次内部 LLM 调用。B9 原始执行出现 402/429，后续恢复只重试这类传输失败，21 条有效结果直接复用。充值前的一次恢复仍失败，日志和已有用量全部保留。充值后先试跑两条，再单样本并发继续；新增已知 token 达到 150 万后不再开启下一样本，遇 402 保存日志并立即停止。该阈值允许最后一条样本超出少量用量，且供应商失败请求可能不返回完整 usage，因此不是账单硬限额。

相同的单次输出上限不代表总 token 相等；B2/B3 的直接调用与 B8/B9 多阶段流程计算量不同。本轮不作等预算优越性结论。费用估计只根据返回的 usage，不能代替账户实际账单；汇总核算包括旧接口失败、充值前失败恢复，去除直接复用的重复成功记录。

## 复现与交接

配置分别为 `configs/deepseek_p0.json` 与 `configs/deepseek_mentis_p0.json`。密钥只通过 `MWM_LLM_API_KEY` 环境变量传入；MENTIS 还需要 `MWM_MENTIS_ROOT`、`MWM_LLM_MODEL`、`MWM_LLM_BASE_URL`、`MWM_LLM_THINKING_MODE`、`MWM_LLM_MAX_OUTPUT_TOKENS`，值与配置说明一致。配置中的 Python 路径需按机器调整。

```text
python scripts/run_external_resumable.py --config configs/deepseek_p0.json --output-dir results/c_neural_deepseek_b2b3_contract_v2 --methods B2,B3 --workers 1
python scripts/run_external_resumable.py --config configs/deepseek_mentis_p0.json --output-dir results/c_neural_deepseek_b9_resumed --methods B9 --workers 1 --reuse-successes-from results/c_neural_deepseek_mentis --max-new-tokens 1500000
python scripts/export_deepseek_results.py
```

恢复入口验证数据、配置、源码与测试 ID 指纹；已有失败不会默认重试。复现历史日志时需使用日志记录的源码版本。导出脚本重新验证完整测试 ID、实际输入哈希和 C 指标，再生成可提交的聚合结果。A 的 91.30% 来自其 v3 seed0 checkpoint 的独立推理核验，详见 `neural_aligned_integration.md`；不能把它当成本轮重新训练的均值。
