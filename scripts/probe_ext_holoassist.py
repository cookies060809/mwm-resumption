"""Probe the HoloAssist annotation file before committing to any derivation.

HoloAssist (ICCV 2023) is the only public dataset that carries a behavioural
proxy for the project's A factor: whether an error was corrected by an outside
verbal prompt ("corrected by instructor verbally") or discovered by the person
themselves ("corrected by student"). Before building an adapter on top of it we
need to know whether the pairing is actually usable, and in particular whether
T1 has any negative class at all.

This script answers four questions and nothing else:

1. How much of the corpus is there, and what are the tasks?
2. What is the distribution of `Action Correctness`?
3. For "corrected by instructor verbally", is there readable transcript nearby?
   (the A factor needs the person to have been able to receive the message)
4. After an error, does the same action reappear and succeed? (T2 coverage)

It deliberately does NOT derive T1: the measured positive:negative ratio makes a
binary T1 target useless, and saying so is the point of running the probe.

Usage:
    python scripts/probe_ext_holoassist.py --anno /path/to/anno.json
    python scripts/probe_ext_holoassist.py --anno anno.json --export out.jsonl \
        --per-group 400

Download the annotation file (117 MB, CDLA-Permissive-2.0, no application):
    https://hl2data.z5.web.core.windows.net/holoassist-data-release/\
data-annotation-trainval-v1_1.json
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

# Measured values, not the strings printed in the official README.
# The README says "Wrong action, corrected by performer"; the file says
# "Wrong Action, corrected by student". Matching the README yields zero rows.
CORRECT = "Correct Action"
BY_INSTRUCTOR = "Wrong Action, corrected by instructor verbally"
BY_SELF = "Wrong Action, corrected by student"
NOT_CORRECTED = "Wrong Action, not corrected"

WRONG_PREFIX = "Wrong Action"


def load_sessions(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise SystemExit(f"{path}: expected a list of sessions, got {type(data).__name__}")
    return data


def action_key(attrs: dict[str, Any]) -> str:
    return f"{attrs.get('Verb')}|{attrs.get('Noun')}"


def iter_fine(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fine = [event for event in events if event.get("label") == "Fine grained action"]
    fine.sort(key=lambda event: event.get("start", 0.0))
    return fine


def readable(attrs: dict[str, Any]) -> bool:
    text = (attrs.get("Transcription") or "").strip()
    return text not in ("", "*unintelligible*")


def probe(sessions: list[dict[str, Any]], window_before: float = 15.0, window_after: float = 25.0) -> dict[str, Any]:
    labels: collections.Counter[str] = collections.Counter()
    correctness: collections.Counter[str] = collections.Counter()
    tasks: collections.Counter[str] = collections.Counter()
    purposes: collections.Counter[str] = collections.Counter()

    instructor_total = 0
    instructor_with_conv = 0
    instructor_with_text = 0
    access_strict = 0
    clean_self = 0

    wrong_total = 0
    reappeared = 0

    for session in sessions:
        tasks[session.get("taskType")] += 1
        events = session.get("events", []) or []
        for event in events:
            label = event.get("label")
            labels[label] += 1
            attrs = event.get("attributes") or {}
            if label == "Conversation":
                purposes[attrs.get("Conversation Purpose")] += 1
            elif label == "Fine grained action":
                correctness[attrs.get("Action Correctness")] += 1

        conversations = [e for e in events if e.get("label") == "Conversation"]
        fine = iter_fine(events)

        def instructor_purposes(start: float, end: float) -> list[str]:
            found = []
            for conv in conversations:
                if not start - window_before <= conv.get("start", 0.0) <= end + window_after:
                    continue
                purpose = (conv.get("attributes") or {}).get("Conversation Purpose") or ""
                if purpose.startswith("instructor"):
                    found.append(purpose)
            return found

        for index, event in enumerate(fine):
            attrs = event.get("attributes") or {}
            verdict = attrs.get("Action Correctness")
            start, end = event.get("start", 0.0), event.get("end", 0.0)

            if verdict == BY_INSTRUCTOR:
                instructor_total += 1
                nearby = [
                    c
                    for c in conversations
                    if start - window_before <= c.get("start", 0.0) <= end + window_after
                ]
                if nearby:
                    instructor_with_conv += 1
                    if any(readable(c.get("attributes") or {}) for c in nearby):
                        instructor_with_text += 1
                if any("correct the wrong action" in p for p in instructor_purposes(start, end)):
                    access_strict += 1
            elif verdict == BY_SELF:
                # A clean "self-discovered" case must not sit inside an
                # instructor utterance, otherwise the person may have been
                # guided anyway and the A contrast is confounded.
                if not instructor_purposes(start, end):
                    clean_self += 1

            if isinstance(verdict, str) and verdict.startswith(WRONG_PREFIX):
                wrong_total += 1
                key = action_key(attrs)
                if any(
                    action_key(later.get("attributes") or {}) == key
                    and (later.get("attributes") or {}).get("Action Correctness") == CORRECT
                    for later in fine[index + 1 :]
                ):
                    reappeared += 1

    positives = correctness[BY_INSTRUCTOR] + correctness[BY_SELF]
    negatives = correctness[NOT_CORRECTED]
    return {
        "sessions": len(sessions),
        "tasks": dict(tasks.most_common()),
        "labels": dict(labels),
        "correctness": dict(correctness.most_common()),
        "conversation_purposes": dict(purposes.most_common(8)),
        "instructor_corrected": {
            "total": instructor_total,
            "with_conversation_nearby": instructor_with_conv,
            "with_readable_transcript": instructor_with_text,
        },
        "a_factor": {
            "raw_instructor": instructor_total,
            "raw_self": correctness[BY_SELF],
            "access_strict": access_strict,
            "clean_self": clean_self,
            "raw_self_is_contaminated": 1 - clean_self / max(correctness[BY_SELF], 1),
            "balanced_per_side": min(access_strict, clean_self),
        },
        "t1_signal": {
            "positives": positives,
            "negatives": negatives,
            "ratio": (round(positives / negatives, 1) if negatives else None),
            "majority_baseline": (
                round(positives / (positives + negatives), 4) if positives + negatives else None
            ),
        },
        "t2_signal": {
            "wrong_total": wrong_total,
            "reappeared_and_correct": reappeared,
            "coverage": (round(reappeared / wrong_total, 4) if wrong_total else None),
        },
    }


def export_pairs(
    sessions: list[dict[str, Any]], per_group: int, window_before: float, window_after: float
) -> list[dict[str, Any]]:
    """Emit the A-factor contrast, cleaned.

    The raw `corrected by student` group is contaminated: most of those errors
    happen while the instructor is still talking, so "the person discovered it
    themselves" is not warranted. Keep only self-corrected cases with no
    instructor utterance in the window, and only instructor-corrected cases
    whose nearby purpose is actually "correct the wrong action".
    """
    rows: list[dict[str, Any]] = []
    for session in sessions:
        events = session.get("events", []) or []
        conversations = [e for e in events if e.get("label") == "Conversation"]
        fine = iter_fine(events)
        for index, event in enumerate(fine):
            attrs = event.get("attributes") or {}
            verdict = attrs.get("Action Correctness")
            if verdict not in (BY_INSTRUCTOR, BY_SELF):
                continue
            start, end = event.get("start", 0.0), event.get("end", 0.0)
            nearby = [
                c
                for c in conversations
                if start - window_before <= c.get("start", 0.0) <= end + window_after
            ]
            instructor_purposes = [
                (c.get("attributes") or {}).get("Conversation Purpose") or ""
                for c in nearby
                if ((c.get("attributes") or {}).get("Conversation Purpose") or "").startswith(
                    "instructor"
                )
            ]

            if verdict == BY_SELF and instructor_purposes:
                continue  # contaminated: instructor was talking
            if verdict == BY_INSTRUCTOR and not any(
                "correct the wrong action" in purpose for purpose in instructor_purposes
            ):
                continue  # not a correction utterance

            transcript = " ".join(
                (c.get("attributes") or {}).get("Transcription") or "" for c in nearby
            ).strip()
            key = action_key(attrs)
            recovery = next(
                (
                    later
                    for later in fine[index + 1 :]
                    if action_key(later.get("attributes") or {}) == key
                    and (later.get("attributes") or {}).get("Action Correctness") == CORRECT
                ),
                None,
            )
            rows.append(
                {
                    "session": session.get("video_name"),
                    "task_type": session.get("taskType"),
                    "error_start": start,
                    "error_end": end,
                    "verb": attrs.get("Verb"),
                    "noun": attrs.get("Noun"),
                    "correctness": verdict,
                    "a_factor_proxy": "access" if verdict == BY_INSTRUCTOR else "self",
                    "instructor_utterances_in_window": len(instructor_purposes),
                    "nearby_transcript": transcript[:600],
                    "recovery_start": (recovery or {}).get("start"),
                    "explanation": attrs.get("Incorrect Action Explanation"),
                }
            )

    by_group: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        by_group[row["a_factor_proxy"]].append(row)
    balanced: list[dict[str, Any]] = []
    for group in ("access", "self"):
        balanced.extend(by_group[group][:per_group])
    return balanced


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--anno", required=True, type=Path, help="path to data-annotation-trainval-v1_1.json")
    parser.add_argument("--export", type=Path, default=None, help="optional JSONL of A-factor contrast pairs")
    parser.add_argument("--per-group", type=int, default=400, help="rows to keep per A-factor group")
    parser.add_argument("--window-before", type=float, default=15.0)
    parser.add_argument("--window-after", type=float, default=25.0)
    args = parser.parse_args()

    sessions = load_sessions(args.anno)
    stats = probe(sessions, args.window_before, args.window_after)

    print(json.dumps(stats, ensure_ascii=False, indent=2))

    signal = stats["t1_signal"]
    print("\n判定：")
    if signal["negatives"] and signal["ratio"] and signal["ratio"] >= 10:
        print(
            f"- T1 不可用：正负比 {signal['ratio']}:1，朴素基线 {signal['majority_baseline']:.1%}，"
            "负例太少，做不出可用的测试集。"
        )
    else:
        print(f"- T1 正负比 {signal['ratio']}:1，可以人工检查后使用。")
    print(f"- T2 覆盖率 {stats['t2_signal']['coverage']:.1%}（错误后同动作重做且正确）")
    inst = stats["instructor_corrected"]
    print(
        f"- A 证据：{inst['total']} 个被言语纠正案例中，"
        f"{inst['with_conversation_nearby']} 个有相邻对话，"
        f"{inst['with_readable_transcript']} 个转写可读。"
    )
    a = stats["a_factor"]
    print(
        f"- A 对照（清洗后）：access {a['access_strict']} vs self {a['clean_self']}，"
        f"可配平每侧 {a['balanced_per_side']} 例。"
    )
    print(
        f"  未清洗的 self 组有 {a['raw_self_is_contaminated']:.1%} 处在指导者发言窗口内，"
        "直接用会把「被提示」误记成「自主发现」。"
    )

    if args.export:
        rows = export_pairs(sessions, args.per_group, args.window_before, args.window_after)
        args.export.parent.mkdir(parents=True, exist_ok=True)
        with args.export.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"\n导出 {len(rows)} 条到 {args.export}")


if __name__ == "__main__":
    main()
