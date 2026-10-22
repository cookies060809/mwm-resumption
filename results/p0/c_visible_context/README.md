# 完整可见上下文 EC-JMF：模型、训练与复现

本分支唯一部署模型为 C `Bill_method@291e94ad1951001748de32238192e2a06aff234c`
中的 `visible_context`。本次 fetch 成功，核实 origin/main=3765559、origin/Bill=87a660b、
origin/Bill_method=291e94a。开发在 `feat/a-c-context-integration`，原A分支和main未改变。

## 完整交付

- `models/ecr_mwm/context_residual.py`：完整模型，注意力池化人物proposal/末时刻记忆，
  对原hazard logit加 `2*tanh(MLP(state,context))`；hidden24、dropout0.1。
- `neural_model.py`、`models/ec_jmf/structured.py`及`neural_filter.py`：该模型必需的
  双GRU骨干、分离的状态语义与可微精确联合滤波；不作为旧模型独立部署。
- `models/ecr_mwm/neural_training.py`：P0读取、真实自动微分训练、dev选择、完整保存/重载、
  T1/T2/T3、指标和跨种子聚合；不需要C评测包或外部API。
- `configs/a_context_p0_v03.json`：完整架构、训练预算、数据/屏蔽/种子协议。
- 本目录 `model.pt`：所有20370个参数，含冻结骨干；其中1993个新参数可训练。
  加载/训练不再读取旧 `a0_seed0.pt`。

旧中央差分训练、独立float精确/SMC推理入口、旧A1–A6训练配置、开发起步配置、
三组旧A结果及checkpoint已从当前版本移除；历史仍在原A分支 `dec55fa`，未改写历史。
数据、schema、B脚本/标注、C评测模块和原A本地目录未改。共享输入契约测试保留。
B的历史Git-ref检查器 `scripts/check_p0_release_a.py` 保留，适用于旧A引用；
当前完整模型使用下面的新入口。

## 权重与来源

源文件：`experiments/bill_method/results/visible_context/seed_0/checkpoint.pt`。
源SHA256：`484fa2ebe837b6fe4f0ba847b97234b4774aca27017e74d064db77767e317658`。
新完整格式 `a-context-ec-jmf/v1` 增加architecture、config和provenance，
原全部tensor名称、形状、值逐项不变。新文件SHA256：
`705372a44fe2bfa234be09652f3c9cb5b6c1265cfb2e37c4d54ab71a7b6c573a`。
历史骨干SHA仅记录来源，不是加载依赖；模型文件本身含完整骨干及所有行为头。
只接受本格式，旧模型格式不再加载。C原始实现类在运行时不需要从Git读取。

## 使用与训练

```bash
python -m pip install -r requirements-dev.txt -r requirements-neural.txt
# 加载完整模型，输出T1/条件T2/T3及结构化证据轨迹到stdout。
python -m models.ecr_mwm.neural_training --predict results/p0/c_visible_context/model.pt --data data/p0/v0.3/p0_samples.json
# 重现seed0的40轮残差训练，默认只用train/dev，不执行test。
python -m models.ecr_mwm.neural_training --config configs/a_context_p0_v03.json
# 可选：固定20种子扩展；所有dev选择后才显式评价已暴露的P0 test。
python -m models.ecr_mwm.neural_training --config configs/a_context_p0_v03.json --all-seeds --evaluate-test
```

两种训练命令默认使用同一输出位置，重复运行前在配置副本中换一个新的 `output`。
入口拒绝覆盖已有目录。每次仅保留第一预定seed的最终 `model.pt` 和一份 `report.json`，
不写每轮日志、中间checkpoint或重复图表。默认输出 `results/runs/`，不自动加入Git。
配置中的architecture必须与完整模型相符，不会静默忽略结构改动。

训练重初始化attention/residual，冻结其他参数；从完整模型中取得相同已训练骨干，
复现的是C的warm-start残差训练，不是全网络从零训练。保持C的两次骨干构造RNG消耗顺序，
优化前重新设seed。40轮full-batch AdamW，lr=.01、weight_decay=.0001、grad_clip=5、CPU1线程。
保留原state NLL + T1 BCE + 条件T2 NLL + .05一致性项；冻结后state项等对新参数为常数。
dev使用未加权state+T1+T2，含epoch0，最低值选中，并列保留较早轮次。
`seed`用于单次训练；`--all-seeds`才展开固定 `evaluation_seeds=0..19`。
C原实验上下文种子仅0..4，不是20次独立骨干重训；本次未运行新20seed实验。

P0 v0.3：254条，train/dev/test=150/52/52，故事族75/26/26不跨划分。
数据SHA256：`93ca37e93442495039950c0f8c4c618fee4b8b178cfc52c3269b33cb9f0f7739`。
T1阈值.5、ECE10，indeterminate/null不转负例；T2只评分gold恢复且有效未完成原目标步骤，
是条件head top1/top3/NLL，不是C的实际发出步骤准确率；T3只取非UNKNOWN且有cutoff证据，
Q按图内位置；结构零支持保留计错。指标实现沿用neural_metrics，不根据test改屏蔽。
重复seed报告均值和样本SD，不作为人类总体置信区间。

## 本次实际验证

PyTorch 2.11.0+cpu（C记录2.14.0+cpu）：

- 旧checkpoint删除后完整模型独立加载；源C的全部tensor逐项相同。
- 52条dev的仅input输入，T1/T2/T3与源提交原C类最大差0；不可见/padding proposal扰动不改上下文。
- 实际40轮seed0完整训练入口，选epoch40；dev loss=0.09748930484056473，
  C历史记录0.09748923778533936，差约6.7e-8，不能说跨版本训练tensor逐位相同。
- 训练冻结参数和T3不变；保存重载的p/q/T3误差0；3条dev通过已有predict_file导出。
- 两项现有输入契约测试通过；未新增永久测试文件。
- 未重算test指标或20seed结果，所有本地验证临时输入/模型/汇总已自动删除。

## 结果解释与限制

C按mean dev loss选visible_context（.103746），而非balanced（.104209）或原头继续训练（.115050）；
seed0预先固定。C历史test T1准确率91.30%至97.83%（有效46条）、Brier .07456至.02592，
但简单原头继续训练也达97.83%，不能将硬判断变化独立归因于新增模块。
这是已多次暴露的脚本P0，不是新盲测，更不是P1真人效果/泛化/校准或创新性证据。
T2仅20条且gold均为首个未完成步骤，不能据100%历史诊断值推论复杂规划能力。
不迁入控制变体模型、CSV、图表、逐次日志或审计材料来充作模型组成。

上下文仅池化valid & visible人物proposal；可见包含接触/理解不确定的显式证据，
并不等于人物已经理解或采信。支路不读取world encoder或gold，不改写T3信念；
原行为头仍使用客观可行性等state特征。T2条件混合可能随hazard改变。
结构化证据轨迹不解释新增attention贡献。

关键事件焦点、消息目标关联和资源范围契约仍待B/C补齐，T3.A是代理，六因子均值
不是已确认的B全口径总成绩。公共update、MENTIS、无损理解/嵌套图输入及端到端T2评测
仍待C；授权真人行为、删失窗口、人物/任务族划分与独立校准仍依赖P1。
