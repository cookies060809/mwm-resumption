# Source manifest（ECR-MWM P1）

核验与下载日期：2026-10-22。环境：CPU-only Windows 主机，无 GPU。
逐文件 sha256 与上游对象 id 见 [raw_inventory.md](raw_inventory.md) 与 `raw/*/_manifest.json`。

## 0. 本机网络事实（决定「可下载性」判断，非推测）

| 主机 | 结果 |
|---|---|
| `huggingface.co` 直连 | 不可达（TLS 失败） |
| `hf-mirror.com` | 可用但**严重抖动**：同一 URL 常需 5–10 次重试；`resolve/` 端点有 5 分钟配额 |
| `github.com` / `api.github.com` / `codeload.github.com` | 可达；`api.github.com` 未认证限额 60 req/h（实测 403）；`codeload` 约 100 KB/s，需 `curl -C -` 续传 |
| `raw.githubusercontent.com` | 不可达（用 Contents API 或 tarball 代替） |
| `data.4tu.nl`（IndustReal 数据页） | **不可达**（连接失败，http=000） |
| `zenodo.org` | 不可达 |
| `nanayawoa.github.io`（REBOOT 项目页） | 可达（首次超时、重试成功） |
| `arxiv.org` / `export.arxiv.org` | 可达 |

## 1. 四项准入检查（任务书 §2）

| 检查项 | IHBench | REBOOT | IndustReal | InterruptBench |
|---|---|---|---|---|
| ① 许可证明确且允许再分发 | ✅ CC-BY-4.0（HF 卡 `license: cc-by-4.0`）+ 工具包 Apache-2.0 | ✅ Apache-2.0（38/38 仓 HF tag `license:apache-2.0`）；项目页另声明 CC-BY-4.0 | ⚠️ 代码仓 Apache-2.0（GitHub 识别）；**数据集**许可证在 4TU 页面，本机不可达，无法核验 | ❌ 根目录无 LICENSE（GitHub `license=null`），唯一 MIT 文本版权行属上游 VisualWebArena 作者 |
| ② gated:false 或 GitHub 免登录可取标注 | ✅ `gated:false, private:false` | ⚠️ 站点链接的 `REBOOT26/datasets` 未授权返回 **401 `Invalid username or password`**；但 org 内 38 个分仓全部 `gated:false, private:false`，免登录可取 | ❌ GitHub 免登录但**仓内没有标注 CSV**；标注在 4TU，需其页面许可 | ✅ 免登录可直接取 JSON |
| ③ 提供文本/CSV/JSON/Parquet 标注，而非必须整包视频/音频 | ✅ parquet 列级可选，音频列可完全跳过 | ✅ `meta/phase.json` 是纯 JSON episode 标注，与 `data/`、`videos/` 物理分离 | ⚠️ 标注是 per-recording `PSR_labels*.csv`，但打包在含 84 段视频 + 深度/立体流的整包内 | ✅ 纯 JSON |
| ④ 标注部分体积 < 500 MB | ✅ 文本列 2.1 MB | ✅ 68 KB | ❓ 无法测量（页面不可达）；已知整包含 84 段视频 | ✅ 2.17 MB |
| **结论** | **USED** | **USED（1/38 仓带标注，但已扩到 4 类截断点）** | **skipped: license unclear / gated + host unreachable** | **used_with_caveat（许可证）** |

## 2. 逐源记录

### 2.1 IHBench — USED（主源）

| 字段 | 值 |
|---|---|
| 数据集名 | `bosonai/IHBench`（arXiv:2606.19595） |
| 许可证 | CC-BY-4.0（HF 卡 frontmatter 原文 `license: cc-by-4.0`）；`gated:false`；代码仓 `boson-ai/ihbench` = Apache-2.0 |
| 下载 URL | `https://hf-mirror.com/datasets/bosonai/ihbench/resolve/main/{conversations,baseline}.parquet`（回退 `huggingface.co`），commit `cbd8280ab59bc4a50c48cbe0511a307fba9945cf` |
| 本地路径 | `raw/IHBench/conversations_text.json`、`raw/IHBench/baseline_text.json`、`raw/IHBench/dataset_card.md` |
| 文件体积 | 2,576,308 B + 215,726 B（远端 conversations.parquet 为 216,471,312 B） |
| 实际传输 | **2,255,700 B**（65 次 HTTP Range 请求）；`user_turn_{1..20}_audio` 的 **214,161,509 B 未请求** |
| SHA256 | `612b6d0961429c4e5bb2ce87eed45488ffee93bb8f1b6a386adfbbd3af4de55a`（conversations_text.json）、`53bd10e58c5119fbf5276dd9ea1592a59d88a865b5f9264da26f8ceb5e482c86`（baseline_text.json） |
| 状态 | 成功，**856 条 P1**（428 episode 行为者 + 428 baseline 行为者，规则 R10）|
| 覆盖的 P1 字段 | `base_story_id`、`goal_id`、`task_steps`(218 个阶段)、`observed_events`(start_goal/progress/interruption/background_fact)、`cutoff_event_id`、`V`(规则)、`F`、`A`、`B`、`C`、`Q`(132 值)、`p1_observed_resume`(episode 行为者 true 346 / false 23 / null 59；baseline 行为者 true 313 / false 115)、`p1_resume_step`、`evidence_trace`、`original_annotation_ref` |
| 未覆盖 | `V=CANCELLED/FULFILLED`、`B=BELIEVES_INVALID`、`C=ACTIVE/ABANDONED/COMPLETED`、`F=BLOCKED`、`event_type=completion` |

### 2.2 REBOOT — USED（部分可用）

| 字段 | 值 |
|---|---|
| 数据集名 | `REBOOT26/sample_recovery-demonstration`（org `REBOOT26`；论文 *REBOOT: From Failure to Recovery — A Dataset and Benchmark for Precision Assembly*，arXiv preprint 2026，作者 Ofori-Ampofo, Ebrahimi Kahou, Thekinen） |
| 许可证 | **Apache-2.0**（HF API tag `license:apache-2.0`，38/38 仓一致）；项目页文字另称 "REBOOT is released under CC-BY-4.0 on Hugging Face" —— 两处声明不一致，本交付按**逐仓 API tag**（Apache-2.0）为准并保留项目页出处 |
| 下载 URL | `https://hf-mirror.com/datasets/REBOOT26/sample_recovery-demonstration/resolve/main/meta/{phase.json,info.json,tasks.parquet}` |
| 本地路径 | `raw/REBOOT/sample_recovery-demonstration/{phase.json,info.json,tasks.parquet}` |
| 文件体积 | 60,992 + 5,194 + 2,351 B（合计 68.5 KB）。**未下载** `data/*.parquet` 轨迹与 `videos/` |
| SHA256 | `1d61ff591ff9f52628c4…`（phase.json，全值见 `raw/REBOOT/_manifest.json`）、`b0890cbbccd2b4db1e6b…`（info.json） |
| 状态 | 成功，**192 条 P1**（4 类截断点：pre 60 / fail 60 / rec 57 / done 15；129 observed_resume / 63 censored） |
| 覆盖的 P1 字段 | `task_steps`=标注的五 phase（Align pick / Engage pick / Transport / Align place / Engage place）、`Q`=失败帧所处 phase、`p1_resume_step`=恢复帧所处 phase、`failure_mode`、`p1_observed_resume` 来自**人工标注的 `recovery_started_at_frame`**（真实观测，非推断）；
  并独家补齐 `V=FULFILLED`(15)、`C=COMPLETED`(15)、`F=BLOCKED`(57)、`A=NOT_ACCESSED`(60)、`event_type=resume/completion`(70/15)、`Q=NOT_APPLICABLE`(15) |
| 可用性上限 | org 内 38 个仓**只有这 1 个**带 `meta/phase.json`（全量扫描：with=1、without=37、unreachable=0）。站点主链接 `REBOOT26/datasets`（应为 2,160 段演示 / 18 任务的完整标注）**未授权返回 401**，需 HF 登录或作者放行才能取全 |
| 源数据质量（未修复，仅记录） | `failure.originating_phase` 与「失败帧落在哪个 phase 区间」在 **46/60** 条上不一致（偏移 +1 ×22、+2 ×22、−1 ×1、值 21 越界 ×1）；另有 1 条 `phase_boundaries` 非单调（τ 不减/首末不闭合）。转换器因此**不使用 `originating_phase` 作 step_id**，改由 `induced_at_frame` + `phase_boundaries` 推导（规则 B4/B13/B14），受影响行记入构建日志；3 条帧号不可解释的降为 `censored` |
| 模态声明 | 主体是**双指机器人 + 人类操作员示教**，不是语音 agent；聚合指标必须分源报告（见 dataset_card） |

### 2.3 IndustReal — skipped: license unclear / gated（且主机不可达）

| 字段 | 值 |
|---|---|
| 数据集名 | IndustReal（arXiv:2310.17323，*A Dataset for Procedure Step Recognition Handling Execution Errors in Egocentric Videos in an Industrial-Like Setting*）；84 段第一人称视频、27 名参与者 |
| 代码 | `https://github.com/TimSchoonbeek/IndustReal` — GitHub API `license.spdx_id = Apache-2.0`，仓库仅 20 个文件 / 138 KB（AR/ASD/PSR 代码 + readme），**不含任何 CSV 标注** |
| 数据 | `https://data.4tu.nl/datasets/b008dd74-020d-4ea4-a8ba-7bb60769d224`（readme 原文指向）。目录结构显示标注为 per-recording `PSR_labels.csv` / `PSR_labels_with_errors.csv` / `PSR_labels_raw.csv`，与 rgb/stereo/depth 流同包 |
| 跳过原因 | ① `data.4tu.nl` 在本机**连接失败**（http=000，多次重试），无法核验数据集许可证、无法列出可单独下载的 CSV、无法测量标注体积；② 即使可达，其分发形式是含视频的整包，需要仅标注子集的确认可再分发许可证 |
| 为何值得后续跟进 | 它是四源中唯一能同时提供 **omission/error 步骤级标注** 与 **真人操作** 的源：`PSR_labels_raw.csv` 的组件状态 `-1` 语义可派生真实的「出错/漏做后是否补做」，即当前只有 23 条的 `observed_not_resume` 类别 |
| 同名混淆提醒 | NVIDIA 的 **IndustReal**（sim-to-real 机器人装配算法与工具）与此无关，检索时须区分 |

### 2.4 InterruptBench — used_with_caveat（许可证）

| 字段 | 值 |
|---|---|
| 数据集名 | `HenryPengZou/InterruptBench`（arXiv:2604.00892） |
| 许可证 | **不明确**：GitHub `license=null`，根目录无 LICENSE；`Eval/LICENSE` 为 MIT，版权行是 VisualWebArena 作者（Koh, Lo, Jang, Duvvur, Lim, Huang）。按任务书 §2 检查①应为 FAIL；本交付保留它是因为「≥2 源」需要第二源，且 `Eval/` 目录树内确有 MIT 文本可作初步依据。**结论：仅限内部评测，对外再分发前必须向作者书面确认** |
| 下载 URL | `https://api.github.com/repos/HenryPengZou/InterruptBench/contents/Eval/...`（34 个文件）+ `https://codeload.github.com/HenryPengZou/InterruptBench/tar.gz/refs/heads/main`（补齐 process 变体） |
| 本地路径 | `raw/InterruptBench/Eval/**`（与上游同构，46 个文本/JSON 文件，2,165,518 B）；每条都有上游 git blob sha（`_upstream_blobs.json` / `_upstream_tree_subset.json`） |
| 交叉验证 | 两条下载通道重叠的 **31 个文件 sha256 完全一致** |
| SHA256 | `3325283ea39734ab8207…`（`Eval/interrupt_config/raw/3mixed.json`）、`f05ad64b8bdcfcac21ac…`（`Eval/config_files/wa/test_webarena_lite.json`） |
| 媒体排除 | 解包时 `--exclude` 掉 `coco_images/`、`*.png`、`*.jpg`；仓库 42.9 MB 中只保留 2.17 MB 文本 |
| 状态 | 成功，1,815 条 P1（全部 `censored`） |
| 覆盖的 P1 字段 | `V`(VALID/CANCELLED)、`B=BELIEVES_VALID`、`C`(ACTIVE/SUSPENDED/ABANDONED 三值)、`F`(READY/UNKNOWN)、`A=ACCESSED`（按任务书 §2.4 规定的注入即暴露）、多轮中断事件序列 |
| 未覆盖 | `task_steps`=[]（无步骤级标注：`interrupt_at_pct` 是运行时动作序列的百分比，仓库不含该序列）、`Q=UNKNOWN`、`p1_observed_resume=null`（无 run 记录） |
| 同名项目排查 | `PrabhavD/interruptbench`（Apache-2.0，合成环境生成器，无标注文件）、`Arcadi4/interruptbench`（MIT，只有 README + `.gitmodules`） |

## 3. 硬约束对照

| 约束 | 结果 |
|---|---|
| 只下载文本/CSV/JSON/Parquet 标注 | ✅ 三源合计 `raw/` **5.04 MB**，全部为 JSON/parquet 文本列/MD/PY；IHBench 音频列 214 MB 未请求；REBOOT 的 `data/`、`videos/` 未请求；IndustReal 因需视频整包而跳过 |
| 标注部分 < 500 MB | ✅ 5.04 MB |
| 许可证明确 | ⚠️ IHBench（CC-BY-4.0）与 REBOOT（Apache-2.0）明确；InterruptBench 标注为 `used_with_caveat`；IndustReal 无法核验 → 未使用 |
| 不伪造标签 | ✅ `llm_inferred` = 0；无标注处一律 `UNKNOWN`/`null`；`observed_not_resume` 只来自 IHBench 的内容级判定（23 条），REBOOT 的正例来自人工标注帧号 |
| 非 UNKNOWN 标签可溯源 | ✅ 规则编号 R1–R9 / T1–T10 / B1–B14 写在转换脚本 docstring；`evidence_trace` + `fields_used` 逐样本记录；`merge_and_validate.py` 强制引用完整性与 censoring↔标签一致性 |
| IHBench 或 REBOOT 至少一个成功 | ✅ **两者都成功**（IHBench 428 条；REBOOT 60 条，受限于只有 1 个仓带标注） |
| ≥2 个 source_dataset | ✅ 3 个：IHBench、InterruptBench、REBOOT |
| 单源失败不中止 | ✅ 全程未中止；GitHub 403 → codeload 续传；hf-mirror 抖动 → 重试脚本；4TU 不可达 → 记录跳过原因继续 |

## 4. 署名（再分发前必须保留）

- **IHBench** — CC-BY-4.0：`bosonai/IHBench` + arXiv:2606.19595（Salimi, Ma, Tang, Shen, Li, Smola, 2026）；工具包 `boson-ai/ihbench`（Apache-2.0）。
- **REBOOT** — Apache-2.0（逐仓 HF tag）：`REBOOT26/sample_recovery-demonstration`；论文与项目页 https://nanayawoa.github.io/REBOOT （Ofori-Ampofo, Ebrahimi Kahou, Thekinen, 2026）；代码基于 LeRobot（Apache-2.0，`anon-robo-account/REBOOT`）。注意许可证声明存在两处表述（HF tag Apache-2.0 / 项目页 CC-BY-4.0），引用时两者都列出。
- **InterruptBench** — arXiv:2604.00892（Zou 等，芝加哥大学）；底层任务 WebArena / WebArena-Lite（Zhou 等；Koh 等，`Eval/LICENSE` MIT）。**仅限内部使用**，见 §2.4。
- **IndustReal** — 未使用；若后续纳入需同时署名 arXiv:2310.17323（Schoonbeek 等）与 4TU 页面的数据集许可证。
