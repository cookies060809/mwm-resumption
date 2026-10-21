# 给 C 的训练交接：CASAS 活动返回代理任务

这不是计划书第 3.4 节定义的完整 P1，不能将结果写成“预测人类目标承诺/真实任务恢复步骤”。

## 可以立即训练什么

输入是一个已标注活动从 A 切换到 B 的时刻及其之前最多 64 条传感器事件。输出是未来 60 秒内是否再次出现标注为 A 的事件。观察窗口不足且未见返回的记录删失；未来窗口包含多活动或未标注事件的候选排除。

训练文件共 151 条：train 84（正例 10）、dev 33（正例 8）、test 34（正例 7）。190 个候选中排除歧义 34 条、删失 5 条。来源压缩包实读有 20 个人物文件、7677 条事件；网页对交织部分人数的描述与归档实读不同，以 source_manifest.json 为本版本依据。

## C 的读取方法

```python
import json
from pathlib import Path
rows = [json.loads(line) for line in Path('train.jsonl').read_text(encoding='utf-8').splitlines()]
X = [r['input'] for r in rows]
y = [r['labels']['activity_return']['60']['y'] for r in rows]
```

只将 input 传给模型。labels、provenance、split 不作为模型特征。participant_id 和 source_line 仅供分组/溯源，不应作为数值特征。历史活动编号是原数据人工标注的 oracle 输入；若部署时只有传感器读数，必须另加活动识别模块并重新评测，不能混为端到端结果。

人物按固定 seed=42 分组，按人物是否存在正例分层；各集合人物互斥。不要再次按事件随机划分。使用 dev 调参；test 保留。样本非常小且不平衡，先做常量概率/多数类、最近活动/简单历史特征基线，报告 AUPRC、Balanced Accuracy、Brier 和 n，分人物置信区间应明确其不稳定性。

## 与原 P1 的差距

- cutoff 是活动切换开始，无法从该数据确定外部中断结束时刻。
- 同类活动重新出现不证明原目标之前未完成，不证明是在推进原目标尚未完成步骤。
- 不含任务完成标志、可靠步骤图、取消/通知/理解证据。
- p1_resume、p1_resume_step 均为 null；V/F/B/C/Q 为 UNKNOWN，A 为 UNCERTAIN。禁止将代理标签复制到这些字段。
- 60 秒是本转换新定义的固定时间窗口，不是计划书的 H=3 决策机会；180 秒结果保留供后续预先登记协议使用，不应据 test 表现选择窗口。
- 并发活动/未知事件采取保守排除，可能引入筛选偏差。不能声称全面覆盖真实中断类型。

## 来源与复现

数据：CASAS Smart Home dataset - scripted activities, separated and interweaved。
https://zenodo.org/records/15713190

引用：Singla, G., Cook, D. & Schmitter-Edgecombe, M. (2009). Tracking activities in complex settings using smart environment technologies. International Journal of BioSciences, Psychiatry and Technology, 1(1):25–35.

归档文件 adl_interweave.zip 的官方 MD5 为 033ee8304fd6c058b8dbcb489d70213c。每个输入文件 SHA-256 见 source_manifest.json。转换脚本在上级目录 build_casas_proxy.py，只需 Python 标准库。

本次读取的 Zenodo 页面未明确展示许可名称；公开可下载不代表可任意再分发。此包仅为本地研究转换交接，未确认原数据及衍生标注的再发布许可，正式提交/公开发布前需核对来源使用条款。

## InteRead 核验结果

另已下载 https://doi.org/10.18419/DARUS-4091 的 README、逐页恢复时延表、处理后注视事件等小文件。逐页表实读 290 行、50 个不同人物 ID；它适合真实中断后的阅读恢复时延辅助实验（需按原论文定义清洗并构建截断前特征），不是完整 P1 是否自主恢复/恢复步骤训练集。本包没有把这 290 行伪装成完整 P1 标签，也未完成其训练特征转换。

## 验证范围

已检查 sample_id 唯一性、输入事件时间不晚于 cutoff、人物划分互斥、训练文件只含可判定的 60 秒代理标签。没有训练模型，结果不能作为方法有效性证据。
