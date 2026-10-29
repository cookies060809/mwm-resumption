"""Build P0 v0.4: v0.3 plus B's adjudication of 14 `B=UNKNOWN` records.

Handbook §2.5 rule 2: an explicit "still valid / continue" statement is
BELIEVES_VALID evidence. Each arbitrated record contains exactly one such
statement (e06, "人物说：还剩三步，回来接着弄。"), so B is set to
BELIEVES_VALID with e06 as evidence. v0.3 stays frozen; nothing else changes.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_eval_format import MAPPING_NOTES, to_input, to_label  # noqa: E402
from scripts.validate_data import validate_records  # noqa: E402

V03 = ROOT / "data" / "p0" / "v0.3"
OUT = ROOT / "data" / "p0" / "v0.4"
SPLITS = ("train", "dev", "test", "calibration")
STATEMENT = "人物说：还剩三步，回来接着弄。"
ARBITRATED = [
    "P01-D1-B", "P01-D2-B", "P01-D3-B", "P01-D4-B", "P01-D5-B",
    "P01-S1-B", "P01-S2-B", "P01-S3-B", "P01-S4-B", "P01-S5-B",
    "P01-W2-B", "P01-W3-B", "P01-W4-B", "P01-W5-B",
]
UNCHANGED = {
    "P01-B": "only return_to_task after the unseen cancellation; a return action alone is not belief evidence",
    "P01-W6-A": "no event after the cancellation",
    "P01-W6-B": "no event after the cancellation",
    "P08-S7-B": "no event after the cancellation",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def jsonl_bytes(rows) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def arbitrate(records: list[dict]) -> list[dict]:
    by_id = {record["sample_id"]: record for record in records}
    changes = []
    for sample_id in ARBITRATED:
        record = by_id[sample_id]
        assert record["state_at_cutoff"]["B"] == "UNKNOWN", sample_id
        assert record["state_at_cutoff"]["V"] == "CANCELLED", sample_id
        assert record["state_at_cutoff"]["A"] == "NOT_ACCESSED", sample_id
        statements = [
            event for event in record["observed_events"]
            if event["event_type"] == "person_statement" and event["description"] == STATEMENT
        ]
        assert len(statements) == 1 and statements[0]["event_id"] == "e06", sample_id
        record["state_at_cutoff"]["B"] = "BELIEVES_VALID"
        record["state_evidence_by_factor"]["B"] = ["e06"]
        ordered = [event["event_id"] for event in record["observed_events"]]
        record["state_evidence_event_ids"] = [
            event_id for event_id in ordered
            if any(event_id in ids for ids in record["state_evidence_by_factor"].values())
        ]
        changes.append({"sample_id": sample_id, "factor": "B", "from": "UNKNOWN", "to": "BELIEVES_VALID", "evidence": ["e06"]})
    return changes


def main() -> int:
    parent = load(V03 / "p0_samples.json")
    records = json.loads(json.dumps(parent))
    changes = arbitrate(records)

    for sample_id, record in {record["sample_id"]: record for record in records}.items():
        if sample_id in ARBITRATED:
            continue
        original = next(item for item in parent if item["sample_id"] == sample_id)
        assert record == original, f"unexpected change in {sample_id}"

    errors = validate_records(records)
    if errors:
        raise SystemExit("validation failed:\n" + "\n".join(errors[:20]))

    OUT.mkdir(parents=True, exist_ok=True)
    split_files = {}
    for split in SPLITS:
        rows = [record for record in records if record["split"] == split]
        payload = json_bytes(rows)
        (OUT / "splits").mkdir(exist_ok=True)
        (OUT / "splits" / f"{split}.json").write_bytes(payload)
        split_files[f"splits/{split}.json"] = {"records": len(rows), "sha256": sha(payload)}

    payload = json_bytes(records)
    (OUT / "p0_samples.json").write_bytes(payload)

    inputs = [to_input(record) for record in records]
    labels = [to_label(record) for record in records]
    (OUT / "eval").mkdir(exist_ok=True)
    (OUT / "eval" / "inputs.jsonl").write_bytes(jsonl_bytes(inputs))
    (OUT / "eval" / "labels.jsonl").write_bytes(jsonl_bytes(labels))
    mapping = (V03 / "eval" / "MAPPING.md").read_text(encoding="utf-8").rstrip()
    mapping += (
        "\n\n## v0.4 arbitration patch\n\n"
        "Only the `B` label of 14 contact-cancellation B arms changed:\n"
        "`UNKNOWN` -> `BELIEVES_VALID`, with `e06` (an explicit \"回来接着弄\" statement)\n"
        "as evidence, per handbook §2.5 rule 2. No event, split, expected behavior or\n"
        "other factor changed. `gold.state_labels.B` therefore becomes `BELIEVES_VALID`\n"
        "for those 14 rows; everything else in this mapping is unchanged from v0.3.\n"
    )
    (OUT / "eval" / "MAPPING.md").write_text(mapping, encoding="utf-8", newline="\n")

    manifest = {
        "release_version": "p0-release/v0.4.0",
        "record_schema_version": "p0-record/v0.2.0",
        "dataset_layer": "P0",
        "standalone": True,
        "parent_release": {
            "path": V03.relative_to(ROOT).as_posix(),
            "release_version": "p0-release/v0.3.0",
            "sha256": sha((V03 / "p0_samples.json").read_bytes()),
        },
        "records": len(records),
        "families": len({record["base_story_id"] for record in records}),
        "events": sum(len(record["observed_events"]) for record in records),
        "arbitration": {
            "rule": "annotation handbook §2.5 rule 2 (explicit continue statement -> BELIEVES_VALID)",
            "factor": "B",
            "records": len(ARBITRATED),
            "changes": changes,
            "unchanged": UNCHANGED,
        },
        "splits": {
            split: {
                "records": sum(1 for record in records if record["split"] == split),
                "families": len({record["base_story_id"] for record in records if record["split"] == split}),
            }
            for split in SPLITS
        },
        "annotation_status": dict(Counter(record["annotation"]["status"] for record in records)),
        "second_reviewer_records": 0,
        "checks": {
            "schema_and_cross_fields": "pass",
            "paired_family_split": "pass",
            "blueprint_split_isolation": "pass",
            "only_arbitrated_labels_changed": "pass",
        },
        "limitations": [
            "Scripted P0 expectations, not observed human behavior.",
            "v0.4 is a B label-arbitration release on top of v0.3; A/C blind review and independent adjudication remain pending.",
            "14 contact-cancellation B arms now carry B=BELIEVES_VALID; results computed on v0.3 are stale and must be rerun.",
            "P0 datasets must not be appended to one another; read v0.4 only.",
        ],
        "artifacts": {
            "p0_samples.json": {"sha256": sha(payload), "bytes": len(payload)},
            **split_files,
            "eval/inputs.jsonl": {"sha256": sha((OUT / "eval" / "inputs.jsonl").read_bytes())},
            "eval/labels.jsonl": {"sha256": sha((OUT / "eval" / "labels.jsonl").read_bytes())},
            "eval/MAPPING.md": {"sha256": sha((OUT / "eval" / "MAPPING.md").read_bytes())},
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    readme = f"""# P0 v0.4 仲裁发布版

给 A/C 的正式入口是 **`data/p0/v0.4/p0_samples.json`**：254 条 / 127 家族 / 1,908 事件，
划分仍为 **150/52/52**，记录 schema 仍为 `p0-record/v0.2.0`。**v0.3 冻结保留**，
本版是它之上的 B 侧标签仲裁，不重写历史。

## 改了什么

只有 **14 条** `contact_cancellation` 的 B 臂标签：

| 项 | v0.3 | v0.4 |
|---|---|---|
| `state_at_cutoff.B` | `UNKNOWN` | `BELIEVES_VALID` |
| `state_evidence_by_factor.B` | `[]` | `["e06"]` |
| 事件、划分、预期动作、其他因子 | — | 不变 |

依据：手册 §2.5 判定顺序第 2 条——人物在未接触取消通知后明确说
"还剩三步，回来接着弄"，这是明确的继续表达，应判 `BELIEVES_VALID`；
此前把它留作 `UNKNOWN` 与同一批数据里 215 条 `BELIEVES_VALID` 的取值规则不一致。
这 14 条的 A 臂仍是 `B=BELIEVES_INVALID`，接触—信念的对照因此更干净。

**未改动：** `P01-B`（只有 `return_to_task`，返回动作本身不构成信念证据）、
`P01-W6-A/B`、`P08-S7-B`（取消后无任何事件，`UNKNOWN` 合法）。

## P02 "放弃后开始步骤"的仲裁

14 条 P02 B 臂在显式放弃（"先不做了，别再安排"）之后仍有 `step_started`。
B 的裁决是**维持 `C=ABANDONED` 与 `not_resume`**：手册 §2.6 的判定顺序里，
明确的放弃陈述优先于其后的一般性步骤动作；只有新的承诺表达
（`commitment_expressed` 或明确的继续陈述）才重新打开目标。该规则已写入手册 §2.6。
A 按"终止 + 重新承诺两假设"处理这两条路径，与本次裁决一致。

## 使用

- A：`p0_samples.json` 或 `splits/`；`B` 掩码现在对上述 14 条为 1。**v0.3 上的训练/评测结果作废，需重跑。**
- C：`eval/{{inputs,labels}}.jsonl`，254/254；标签的 `B` 值随之更新。
- `data/training_ready/v1` 已按 v0.4 重建（`sources/p0.json` 已替换），A/C 直接读训练包即可。
- 不要把 v0.4 与 v0.3 或其他批次拼接。

## 校验

```bash
python scripts/validate_data.py --file data/p0/v0.4/p0_samples.json
python scripts/build_p0_v04.py --check
python scripts/release_manifest.py
```

A/C 独立盲审与仲裁仍未完成，`annotation.status` 仍为 `reviewed`，不得写成 `adjudicated`。
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(records)} records, {len(changes)} B labels arbitrated")
    return 0


def check() -> int:
    current = load(OUT / "p0_samples.json")
    rebuild = json.loads(json.dumps(load(V03 / "p0_samples.json")))
    arbitrate(rebuild)
    assert current == rebuild, "v0.4 is not v0.3 + the documented arbitration patch"
    assert len(current) == 254
    assert sum(1 for record in current if record["state_at_cutoff"]["B"] == "BELIEVES_VALID") == 216
    assert sum(1 for record in current if record["state_at_cutoff"]["B"] == "UNKNOWN") == 4
    manifest = load(OUT / "manifest.json")
    for name, meta in manifest["artifacts"].items():
        assert sha((OUT / name).read_bytes()) == meta["sha256"], name
    print("OK: v0.4 equals v0.3 + 14 documented B changes; artifacts match the manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(check() if "--check" in sys.argv else main())
