"""Draw a reproducible P0 spot-audit sample and print a worksheet for the auditor.

v0.2 reports 240/240 `reviewed`, but B wrote every one of those rows, so the
number measures self-consistency, not independent agreement. This packet picks a
fixed sample with a documented seed -- one pair per mechanism first, then a
hash-ordered fill -- and puts the machine preflight next to empty sign-off boxes.
It records no verdicts: filling them in is the audit.

Usage:
    python scripts/audit_packet.py --records 20 --seed 20261021
    python scripts/audit_packet.py --file data/p0/p0_samples_v0.3.json --out docs/annotation/x.md
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pair_diff_report as pdr  # noqa: E402
import validate_data as vd  # noqa: E402

FACTORS = ("V", "F", "A", "B", "C", "Q")
# Values that claim the person or the observer is not sure. Each one is what
# handbook 1.4 asks the auditor to defend: name the missing piece of evidence.
UNCERTAIN_STATE = ("UNKNOWN", "UNCERTAIN", "UNRESOLVED")
UNCERTAIN_EVENT_FIELDS = {
    "person_access": ("UNCERTAIN",),
    "person_comprehension": ("UNCERTAIN", "NOT_UNDERSTOOD", "MISUNDERSTOOD"),
    "certainty": ("PROBABLE", "UNCERTAIN"),
}

CHECKLIST = (
    "- [ ] 只改了一个设计变量，其余差异都是它的必然后果\n"
    "- [ ] 每个不确定档位都能指名 cutoff 前缺的是哪一条证据（手册 §1.4）\n"
    "- [ ] `p0_expected_action` 能由 `p0_scripted_policy` + 截断状态推出（Gate 5）\n"
    "- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿"
)
# A P07 pair must NOT differ in any input field, so the first item above is
# meaningless there; the audit question becomes "is the point label really absent".
P07_CHECKLIST = (
    "- [ ] 期望标签确实是 `indeterminate`，没有偷偷藏一个可判别的点标签\n"
    "- [ ] 截断后的设计结果只写在 `p0_design.future_outcome`，没有混进 `observed_events`\n"
    "- [ ] 结论：通过 / 需改（写样本号与字段）：＿＿＿＿＿＿"
)


def clean_pairs(records):
    by_story = defaultdict(list)
    for record in records:
        by_story[record["base_story_id"]].append(record)
    pairs = {}
    for story_id, group in by_story.items():
        if len(group) == 2:
            pairs[story_id] = sorted(group, key=lambda record: record["variant"])
    return pairs


def draw_key(seed: int, family: str) -> str:
    """Shuffle key that does not depend on the interpreter's RNG implementation.

    `random.Random(seed)` is only stable within a Python series, and the packets
    are committed as worksheets -- a 3.11 machine drawing a different 10 pairs
    than the 3.13 one would quietly invalidate whatever gets signed.
    """
    return hashlib.sha256(f"{seed}:{family}".encode("utf-8")).hexdigest()


def select(pairs, pair_count, seed):
    """One family per mechanism, then hash-ordered fill -- deterministic for a given seed."""
    by_mechanism = defaultdict(list)
    for story_id, (a, _) in sorted(pairs.items()):
        by_mechanism[a["mechanism"]].append(story_id)
    chosen = [
        min(by_mechanism[name], key=lambda family: draw_key(seed, family))
        for name in sorted(by_mechanism)
    ]
    rest = sorted(set(pairs) - set(chosen), key=lambda family: draw_key(seed, family))
    return (chosen + rest)[:pair_count]


def flag_lines(a, b):
    lines = []
    for side, record in (("A", a), ("B", b)):
        uncertain = [
            f"{factor}={record['state_at_cutoff'][factor]}"
            for factor in FACTORS
            if record["state_at_cutoff"][factor] in UNCERTAIN_STATE
        ]
        for event in record["observed_events"]:
            for field, values in UNCERTAIN_EVENT_FIELDS.items():
                if event[field] in values:
                    uncertain.append(f"{event['event_id']}.{field}={event[field]}")
        evidence = {
            factor: ids for factor, ids in record["state_evidence_by_factor"].items() if not ids
        }
        lines.append(
            f"  - {record['sample_id']}（{side} 臂）不确定档位：{'、'.join(uncertain) or '无'}；"
            f"零证据因子：{'、'.join(sorted(evidence)) or '无'}"
        )
    return lines


def block(pairs, story_id):
    a, b = pairs[story_id]
    changed = [factor for factor in FACTORS if a["state_at_cutoff"][factor] != b["state_at_cutoff"][factor]]
    diff_keys = sorted(
        {
            key
            for event_a, event_b in zip(a["observed_events"], b["observed_events"])
            for key in event_a
            if pdr.dump(event_a.get(key)) != pdr.dump(event_b.get(key))
        }
    )
    future_leak = a["mechanism"] == "future_leak"
    preflight = (
        f"- 机器预检：截断前输入一致性 "
        f"{'PASS' if pdr.is_future_leak(story_id, a, b) else 'FAIL'}\n"
        if future_leak
        else ""
    )
    return "\n".join(
        [
            f"### {story_id}  ·  {a['mechanism']}  ·  {a['split']}",
            "",
            f"- 事件条数：A {len(a['observed_events'])} / B {len(b['observed_events'])}"
            f"；逐字段差异 {pdr.count_event_diffs(a, b)} 处",
            f"- 状态变化因子：{'、'.join(changed) or '无（同输入对照）'}",
            f"- 差异字段：{'、'.join(diff_keys) or '无'}",
            f"- 期望动作：`{a['p0_expected_action']}` | `{b['p0_expected_action']}`"
            f"（政策 `{a['p0_scripted_policy']}`）",
            *flag_lines(a, b),
            "",
            preflight + (P07_CHECKLIST if future_leak else CHECKLIST),
            "",
        ]
    )


def render(path, records, pair_count, seed):
    pairs = clean_pairs(records)
    chosen = select(pairs, pair_count, seed)
    mechanisms = {pairs[story_id][0]["mechanism"] for story_id in chosen}
    return "\n".join(
        [
            f"# P0 抽查包 · {path.name}",
            "",
            f"> 生成：`python scripts/audit_packet.py --file {path.relative_to(ROOT).as_posix()} "
            f"--records {pair_count * 2} --seed {seed}`。换一个 seed 就是换一批样本，"
            "签核表不要复用。",
            "> **本文件不含任何结论。** 每个复选框都必须由人手工打勾；"
            "B 之外的第二双眼睛（A/C 盲审）是另一张表，不能靠这里代签。",
            "",
            f"- 数据 SHA256：`{hashlib.sha256(path.read_bytes()).hexdigest()}`",
            f"- 抽样：{len(chosen)} 对 / {len(chosen) * 2} 条，机制覆盖 {len(mechanisms)} 种"
            f"（仓库该批次共 {len(pairs)} 对 / {len(records)} 条）",
            f"- 抽样规则：先按机制各取 1 对（机制名排序），不足再按 `sha256(\"{seed}:家族名\")` 排序补齐；"
            "与机器、Python 版本、运行次数都无关",
            "",
            *[block(pairs, story_id) for story_id in chosen],
        ]
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=vd.DATA_FILES[1])
    parser.add_argument("--records", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261021)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the output even if it already carries human ticks",
    )
    args = parser.parse_args()

    path = args.file.resolve()
    text = render(path, vd.load_json(path), max(1, args.records // 2), args.seed)
    if args.out:
        out = args.out if args.out.is_absolute() else ROOT / args.out
        if out.exists() and not args.force:
            signed = out.read_text(encoding="utf-8").count("- [x]")
            if signed:
                print(
                    f"REFUSED: {out.relative_to(ROOT).as_posix()} holds {signed} human "
                    "ticks; a regenerated sheet would silently erase the sign-off. "
                    "Pass --force only if you mean to re-audit.",
                    file=sys.stderr,
                )
                return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
        print(f"wrote {out.relative_to(ROOT).as_posix()}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
