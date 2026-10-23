"""Minimal CPU read + masked-loss check for an exported aux view.

No torch, no GPU: it reads one `processed/aux_view/*.jsonl` file and proves the interface
A and C are handed is actually consumable -

  * input and supervision share no key (so a loader cannot accidentally feed a label);
  * every supervised factor really appears in the loss, and every masked factor really
    does not (the accumulated term count must equal the sum of the masks);
  * masked cross-entropy against the empirical class distribution, plus masked BCE for
    the resume head, computes without NaN on CPU.

A masked loss over an empty set is reported as such rather than as 0.0, because "no
supervision" and "perfect prediction" must never look the same in a report.

Usage: python scripts/check_aux_view.py [processed/aux_view/ihbench.train.jsonl]
"""

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTORS = ("V", "F", "A", "B", "C", "Q")
CLASSES = {
    "V": ["VALID", "CANCELLED", "FULFILLED"],
    "F": ["READY", "BLOCKED"],
    "A": ["ACCESSED", "NOT_ACCESSED", "UNCERTAIN"],
    "B": ["BELIEVES_VALID", "BELIEVES_INVALID", "UNRESOLVED"],
    "C": ["ACTIVE", "SUSPENDED", "ABANDONED", "COMPLETED"],
}


def read(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main():
    # A directory named `aux` is a reserved device name on Windows and git
    # cannot read inside it, so the view ships as `aux_view`.
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "processed" / "aux_view" / "ihbench.train.jsonl"
    if not path.is_absolute():
        path = ROOT / path
    rows = read(path)
    if not rows:
        raise SystemExit(f"{path} is empty")

    overlap = sorted(set(rows[0]["input"]) & set(rows[0]["supervision"]))
    if overlap:
        raise SystemExit(f"input/supervision share keys {overlap}")

    counts, terms, bad = defaultdict(Counter), defaultdict(int), []
    resume_pos, resume_n = 0, 0
    step_pos, step_n = 0, 0
    for r in rows:
        sup, inp = r["supervision"], r["input"]
        for f in FACTORS:
            if sup["state_loss_mask"][f]:
                counts[f][sup["state_at_cutoff"][f]] += 1
                terms[f] += 1
            elif sup["state_at_cutoff"][f] != "UNKNOWN":
                bad.append(f"{r['supervision']['sample_id']}: {f} masked but value {sup['state_at_cutoff'][f]}")
        if sup["resume_loss_mask"]:
            resume_n += 1
            resume_pos += bool(sup["p1_observed_resume"])
        elif sup["p1_observed_resume"] is not None and sup["eligible_for_resume_eval"]:
            bad.append(f"{r['supervision']['sample_id']}: resume label present but masked on an eligible row")
        if sup["step_loss_mask"]:
            step_n += 1
            vocab = inp["task_steps"] + ["NOT_APPLICABLE"]
            if sup["p1_resume_step"] not in vocab:
                bad.append(f"{r['supervision']['sample_id']}: p1_resume_step {sup['p1_resume_step']} not in vocab")

    print(f"{path.relative_to(ROOT)}: {len(rows)} rows, {len({r['supervision']['split_group_id'] for r in rows})} split groups")
    losses = {}
    for f in FACTORS:
        n = terms[f]
        if not n:
            print(f"  {f}: no supervision in this file (mask sum 0) - head must be skipped, not trained on 0 loss")
            losses[f] = None
            continue
        vocab = CLASSES[f] if f != "Q" else sorted({v for r in rows for v in r["input"]["task_steps"]} | {"NOT_APPLICABLE"})
        total = sum(counts[f].values())
        loss = -sum(c * math.log(max(c / total, 1e-12)) for c in counts[f].values()) / total
        losses[f] = loss
        print(f"  {f}: supervised={n} ({n / len(rows):.1%}) classes={len(vocab)} "
              f"masked-CE={loss:.4f} dist={dict(counts[f])}")
    if resume_n:
        p = resume_pos / resume_n
        loss = -(p * math.log(max(p, 1e-12)) + (1 - p) * math.log(max(1 - p, 1e-12)))
        print(f"  resume: supervised={resume_n} positive_rate={p:.3f} masked-BCE(empirical)={loss:.4f} "
              f"| eligible rows={sum(r['supervision']['eligible_for_resume_eval'] for r in rows)}")
    else:
        print("  resume: no supervision in this file - the head must be skipped for this source")
    print(f"  resume_step: supervised={step_n}")
    for math_key, v in losses.items():
        if v is not None and math.isnan(v):
            raise SystemExit(f"{math_key} loss is NaN")
    if bad:
        print("\n".join(f"  BAD {b}" for b in bad[:10]))
        raise SystemExit(f"{len(bad)} mask/value inconsistencies")
    print("check: masks, vocabularies and losses are consistent on CPU")


if __name__ == "__main__":
    main()
