"""Exploratory pass over the IHBench text annotations.

Answers, before any P1 mapping is written:
  - how many interruption points exist, per type, and how many are the final
    (trimmed) turn of their conversation, i.e. have no recorded continuation;
  - whether truncation of the assistant utterance is a usable signal;
  - whether rubric text contains explicit no-resume / termination directives
    (which would license an `observed_not_resume` label by rule);
  - how well assistant turns can be attributed to a workflow stage by a
    deterministic lexical rule, and how ambiguous that rule is.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROWS = Path("raw/IHBench/conversations_text.json")

STOP = set("""the a an and or of to in for on with that this it is are was be as at by from
you your we our i my me then than so such not no into over after before while when which who
if but also just please their them us its do does did done will would can could have has had""".split())


def toks(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 2} - STOP


TERM_HINTS = [
    "end the call", "end the conversation", "terminate", "stops the call", "close the call",
    "does not resume", "no further", "declines to proceed", "wrap up", "say goodbye",
    "correctly ends", "not continue the workflow", "stop the workflow", "abandon",
]


def main():
    rows = json.loads(ROWS.read_text(encoding="utf-8"))
    print(f"conversations={len(rows)}")
    stats = Counter()
    per_type = Counter()
    term_hits = Counter()
    stage_margin = Counter()
    examples = []
    for r in rows:
        n = r["num_turns"]
        stages = r["knowledge_base"]["stages"]
        stage_tok = [toks(s["name"] + " " + s["description"]) for s in stages]
        stats["conversations"] += 1
        stats["turns"] += n
        # per-turn interruption + truncation stats
        for t in range(1, n + 1):
            it = r.get(f"user_turn_{t}_interruption_type")
            if not it:
                continue
            stats["interruption_points"] += 1
            per_type[it] += 1
            tf = r.get(f"turn_{t}_tf_rubric") or ""
            rq = r.get(f"turn_{t}_rq_rubrics") or []
            stats["with_tf_rubric"] += 1 if tf else 0
            stats["rq_criteria"] += len(rq)
            if t == n:
                stats["final_turn_interruption_censored"] += 1
            else:
                stats["has_recorded_continuation"] += 1
            orig = r.get(f"assistant_turn_{t}_original")
            deliv = r.get(f"assistant_turn_{t}_transcript") or ""
            if orig:
                stats["assistant_turn_truncated"] += 1
                if len(deliv) >= len(orig):
                    stats["truncation_anomaly_delivered_ge_original"] += 1
            else:
                stats["assistant_turn_not_truncated"] += 1
            low = tf.lower()
            hit = [h for h in TERM_HINTS if h in low]
            if hit:
                term_hits[tuple(hit)] += 1
                if len(examples) < 6:
                    examples.append((r["conversation_id"], t, it, hit, tf[:300]))
            # stage attribution of the *interrupted* assistant turn
            if stage_tok:
                scores = sorted(
                    ((len(tok_toks := toks(deliv) & st), i) for i, st in enumerate(stage_tok)),
                    reverse=True,
                )
                best, second = scores[0], scores[1]
                stats["stage_attributed"] += 1 if best[0] > 0 else 0
                stage_margin[min(3, best[0] - second[0])] += 1

    print("\n== turn / interruption stats ==")
    for k, v in stats.most_common():
        print(f"  {k:48s} {v}")
    print("\n== interruption types ==")
    for k, v in per_type.most_common():
        print(f"  {k:16s} {v}")
    print("\n== rubrics with explicit termination / no-resume directives ==")
    print(f"  total hits: {sum(term_hits.values())}")
    for k, v in term_hits.most_common(10):
        print(f"  {v:4d} {k}")
    print("\n== stage-attribution margin (best minus second, bucketed) ==")
    for k in sorted(stage_margin):
        print(f"  margin<={k}: {stage_margin[k]}")
    print("\n== termination-hint examples ==")
    for e in examples:
        print(" ", e[0], "turn", e[1], e[2], e[3])
        print("    ", e[4].replace("\n", " "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
