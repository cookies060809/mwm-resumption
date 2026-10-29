"""Build the P0 v0.4 blind-review packet for A/C.

One record per mechanism (8 total), deterministic selection, labels stripped.
The packet is safe to send to reviewers; the key file is B-only. Reviewers fill
the CSV templates, and compare_blind_review.py scores agreement and lists
disagreements. This script never writes a verdict or changes annotation.status.

Usage:
    python scripts/build_blind_packet.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "p0" / "v0.4" / "p0_samples.json"
OUT = ROOT / "docs" / "annotation"
SEED = "blind-v0.4:2026-10-24"
FACTORS = ("V", "F", "A", "B", "C", "Q")
LEGAL = {
    "V": "VALID / CANCELLED / FULFILLED / UNKNOWN",
    "F": "READY / BLOCKED / UNKNOWN",
    "A": "ACCESSED / NOT_ACCESSED / UNCERTAIN / UNKNOWN",
    "B": "BELIEVES_VALID / BELIEVES_INVALID / UNRESOLVED / UNKNOWN",
    "C": "ACTIVE / SUSPENDED / ABANDONED / COMPLETED / UNKNOWN",
    "Q": "task_steps 中的步骤 ID / UNKNOWN / NOT_APPLICABLE",
    "resume_label": "resume / not_resume / unknown",
    "resume_step": "task_steps 中的步骤 ID，或留空",
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def select(records: list[dict]) -> list[dict]:
    pairs = defaultdict(list)
    for record in records:
        pairs[record["base_story_id"]].append(record)
    by_mechanism = defaultdict(list)
    for story, group in pairs.items():
        if len(group) == 2:
            by_mechanism[group[0]["mechanism"]].append(story)
    assert len(by_mechanism) == 8, f"expected 8 mechanisms, got {sorted(by_mechanism)}"

    chosen = []
    for mechanism in sorted(by_mechanism):
        stories = sorted(by_mechanism[mechanism], key=lambda story: digest(f"{SEED}:{story}"))
        story = stories[0]
        group = sorted(pairs[story], key=lambda record: record["variant"])
        index = int(digest(f"{SEED}:variant:{story}")[:2], 16) % 2
        chosen.append(group[index])
    return chosen


def event_rows(record: dict) -> str:
    header = "| id | time | actor | type | step | access | comprehension | certainty | text | semantics |\n"
    header += "|---|---|---|---|---|---|---|---|---|---|\n"
    rows = []
    for event in record["observed_events"]:
        semantics = event.get("person_available_semantics") or {}
        semantic_text = json.dumps(semantics, ensure_ascii=False) if semantics.get("kind", "none") != "none" else ""
        rows.append(
            "| {event_id} | {time} | {actor} | {event_type} | {step_id} | {person_access} | "
            "{person_comprehension} | {certainty} | {description} | {semantics} |".format(
                semantics=semantic_text.replace("|", "/"),
                **{key: ("" if value is None else str(value).replace("|", "/")) for key, value in event.items()},
            )
        )
    return header + "\n".join(rows)


def packet(selected: list[dict]) -> str:
    lines = [
        "# P0 v0.4 盲审包（A/C 用）",
        "",
        "> 这是 8 条**去掉标签**的样本，每机制 1 条。请不要查看 `blind_review_v0.4_key.json`，",
        "> 也不要与 B 讨论答案。按 `blind_review_v0.4_protocol.md` 填写你名下的 CSV。",
        "",
        "每条只给：目标、任务步骤与依赖、决策窗口、截断事件、截断前事件。",
        "没有 `state_at_cutoff`、`p0_expected`、`p0_scripted_policy`、机制名、家族 ID 或 B 的备注。",
        "",
    ]
    for index, record in enumerate(selected, 1):
        blind_id = f"B{index:02d}"
        lines += [
            f"## {blind_id}",
            "",
            f"**目标**：{record['goal_description']}",
            "",
            f"**决策窗口**：{record['horizon']['type']} = {record['horizon']['value']}",
            "",
            f"**任务步骤**：{', '.join(record['task_steps'])}",
            "",
            "**依赖**：" + ("；".join(f"{d['before']} → {d['after']}" for d in record["task_dependencies"]) or "无"),
            "",
            f"**截断事件**：{record['cutoff_event_id']}（其后事件不在输入中）",
            "",
            event_rows(record),
            "",
            "**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，",
            "以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def csv_template(reviewer: str) -> str:
    rows = [["blind_id", "reviewer", *FACTORS, "resume_label", "resume_step", "evidence_event_ids", "notes"]]
    for index in range(1, 9):
        rows.append([f"B{index:02d}", reviewer, *[""] * 6, "", "", "", ""])
    path = OUT / f"blind_review_v0.4_returns_{reviewer}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator=chr(10)).writerows(rows)
    return path.name


def protocol() -> str:
    legal = "\n".join(f"- `{factor}`：{values}" for factor, values in LEGAL.items())
    return f"""# P0 v0.4 盲审协议（A/C）

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
{legal}

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
"""


def main() -> int:
    records = json.loads(DATA.read_text(encoding="utf-8"))
    selected = select(records)
    assert len({record["base_story_id"] for record in selected}) == 8
    assert len({record["mechanism"] for record in selected}) == 8

    OUT.mkdir(parents=True, exist_ok=True)
    packet_text = packet(selected)
    (OUT / "blind_review_v0.4_packet.md").write_text(packet_text, encoding="utf-8", newline="\n")
    (OUT / "blind_review_v0.4_protocol.md").write_text(protocol(), encoding="utf-8", newline="\n")
    csv_template("A")
    csv_template("C")

    key = {
        "warning": "B only. Do not open before returning the CSV; it maps blind ids to sample ids.",
        "packet_version": "p0-v0.4-blind/1",
        "source": DATA.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest(),
        "selection": SEED,
        "packet_sha256": hashlib.sha256(packet_text.encode("utf-8")).hexdigest(),
        "items": [
            {
                "blind_id": f"B{index:02d}",
                "sample_id": record["sample_id"],
                "base_story_id": record["base_story_id"],
                "mechanism": record["mechanism"],
                "variant": record["variant"],
            }
            for index, record in enumerate(selected, 1)
        ],
    }
    (OUT / "blind_review_v0.4_key.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote packet/key/templates to {OUT.relative_to(ROOT)}")
    print("blind ids:", ", ".join(item["blind_id"] for item in key["items"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
