"""Score the A/C blind-review returns against P0 v0.4 and list disagreements.

This only reports agreement and candidates for adjudication. It never writes a
verdict and never changes `annotation.status`; adjudication stays human.

Usage:
    python scripts/compare_blind_review.py
    python scripts/compare_blind_review.py --returns-dir /tmp/returns --out /tmp/report.md
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY = ROOT / "docs" / "annotation" / "blind_review_v0.4_key.json"
DEFAULT_RETURNS = ROOT / "docs" / "annotation"
DEFAULT_OUT = ROOT / "docs" / "annotation" / "blind_review_v0.4_report.md"

FACTORS = ("V", "F", "A", "B", "C", "Q")
LEGAL = {
    "V": {"VALID", "CANCELLED", "FULFILLED", "UNKNOWN"},
    "F": {"READY", "BLOCKED", "UNKNOWN"},
    "A": {"ACCESSED", "NOT_ACCESSED", "UNCERTAIN", "UNKNOWN"},
    "B": {"BELIEVES_VALID", "BELIEVES_INVALID", "UNRESOLVED", "UNKNOWN"},
    "C": {"ACTIVE", "SUSPENDED", "ABANDONED", "COMPLETED", "UNKNOWN"},
}
RESUME = {"resume", "not_resume", "unknown"}


def read_csv(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["blind_id"].strip(): {key: (value or "").strip() for key, value in row.items()} for row in rows}


def gold(record: dict) -> dict:
    expected = record["p0_expected"]
    action = record["p0_expected_action"]
    if action == "indeterminate":
        resume_label, resume_step = "unknown", ""
    elif expected.get("resume_within_horizon") is True:
        resume_label = "resume"
        step = expected.get("first_step")
        resume_step = step if step in record["task_steps"] else ""
    else:
        resume_label, resume_step = "not_resume", ""
    return {
        **{factor: record["state_at_cutoff"][factor] for factor in FACTORS},
        "resume_label": resume_label,
        "resume_step": resume_step,
    }


def legal_value(column: str, value: str, steps: list[str]) -> bool:
    if column in LEGAL:
        return value in LEGAL[column]
    if column == "resume_label":
        return value in RESUME
    if column == "resume_step":
        return value == "" or value in steps
    return True


def score(reviewer: str, returns: dict, key: dict, records: dict) -> tuple[dict, dict, list[str]]:
    counts = {column: {"filled": 0, "agree": 0} for column in (*FACTORS, "resume_label", "resume_step")}
    values = {}
    problems = []
    for item in key["items"]:
        blind_id = item["blind_id"]
        row = returns.get(blind_id)
        if row is None:
            problems.append(f"{reviewer}: missing {blind_id}")
            continue
        if row.get("reviewer") != reviewer:
            problems.append(f"{reviewer}: {blind_id} reviewer column is {row.get('reviewer')!r}")
        reference = gold(records[item["sample_id"]])
        values[blind_id] = {}
        for column in counts:
            value = row.get(column, "")
            if value and not legal_value(column, value, records[item["sample_id"]]["task_steps"]):
                problems.append(f"{reviewer}: {blind_id} {column}={value!r} is not a legal value")
            if value or column == "resume_step":
                counts[column]["filled"] += 1
                counts[column]["agree"] += int(value == reference[column])
            values[blind_id][column] = value
        label, step = row.get("resume_label", ""), row.get("resume_step", "")
        steps = records[item["sample_id"]]["task_steps"]
        if label == "resume" and (not step or step not in steps):
            problems.append(f"{reviewer}: {blind_id} resume without a valid resume_step")
        if label and label != "resume" and step:
            problems.append(f"{reviewer}: {blind_id} resume_step set while resume_label={label}")
    return counts, values, problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--returns-dir", type=Path, default=DEFAULT_RETURNS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    key = json.loads(args.key.read_text(encoding="utf-8"))
    records = {
        record["sample_id"]: record
        for record in json.loads((ROOT / "data" / "p0" / "v0.4" / "p0_samples.json").read_text(encoding="utf-8"))
    }
    paths = {name: args.returns_dir / f"blind_review_v0.4_returns_{name}.csv" for name in ("A", "C")}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        print("missing return files:\n" + "\n".join(missing))
        return 2

    results, problems, values, all_filled = {}, [], {}, True
    for name, path in paths.items():
        returns = read_csv(path)
        counts, vals, errs = score(name, returns, key, records)
        results[name] = counts
        values[name] = vals
        problems += errs
        all_filled &= all(counts[column]["filled"] == len(key["items"]) for column in (*FACTORS, "resume_label"))

    if problems:
        print("PROBLEMS:\n" + "\n".join(problems))
    if not all_filled:
        print("NOT READY: at least one return file is incomplete; no adjudication report written.")
        return 2

    lines = [
        "# P0 v0.4 盲审一致性报告",
        "",
        f"- 盲审包版本：`{key['packet_version']}`；选择规则：`{key['selection']}`",
        f"- 数据：`{key['source']}`，SHA256 `{key['source_sha256']}`",
        f"- 包 SHA256：`{key['packet_sha256']}`",
        "",
        "> 本报告只列一致性与分歧，不写仲裁结论，也不改 `annotation.status`。",
        "",
        "## 覆盖率与一致率",
        "",
        "| 列 | A 已填 | A 与金标一致 | C 已填 | C 与金标一致 | A/C 一致 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for column in (*FACTORS, "resume_label", "resume_step"):
        a_filled, a_agree = results["A"][column]["filled"], results["A"][column]["agree"]
        c_filled, c_agree = results["C"][column]["filled"], results["C"][column]["agree"]
        ac = sum(1 for item in key["items"] if values["A"][item["blind_id"]][column] == values["C"][item["blind_id"]][column])
        lines.append(f"| {column} | {a_filled}/8 | {a_agree}/{a_filled or 0} | {c_filled}/8 | {c_agree}/{c_filled or 0} | {ac}/8 |")

    lines += [
        "",
        "## 分歧清单（仲裁用）",
        "",
        "“金标”列仅供仲裁者查看；A/C 在返回前不应看到本报告。",
        "",
        "| 盲审 | 列 | 金标 | A | C | 仲裁结论（人工填） |",
        "|---|---|---|---|---|---|",
    ]
    disagreements = 0
    for item in key["items"]:
        blind_id = item["blind_id"]
        reference = gold(records[item["sample_id"]])
        for column in (*FACTORS, "resume_label", "resume_step"):
            a_value, c_value = values["A"][blind_id][column], values["C"][blind_id][column]
            if a_value == c_value == reference[column]:
                continue
            disagreements += 1
            lines.append(
                f"| {blind_id} | {column} | {reference[column]} | {a_value or '—'} | {c_value or '—'} |  |"
            )
    if not disagreements:
        lines.append("| — | — | 全部一致 | — | — | — |")

    lines += [
        "",
        "## 下一步",
        "",
        "1. 仲裁者逐行填“仲裁结论”，并在独立记录里写明依据（手册条款 + 事件 ID）。",
        "2. 只有仲裁记录落盘后，才把 `annotation.status` 升 `adjudicated`；本脚本不自动改状态。",
        "3. 若分歧源于定义，改手册而不是改数据去迁就。",
        "",
    ]
    args.out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({disagreements} disagreements)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
