---
license: cc-by-4.0
task_categories:
- audio-text-to-text
language:
- en
tags:
- voice-agents
- interruption-handling
- spoken-dialogue
- benchmark
pretty_name: "IHBench: Interruption Handling Benchmark"
configs:
- config_name: conversations
  data_files:
  - split: test
    path: conversations.parquet
  default: true
- config_name: baseline
  data_files:
  - split: test
    path: baseline.parquet
---

# IHBench: Interruption Handling Benchmark

IHBench evaluates **post-interruption recovery** in voice agents executing
structured, multi-step workflows. Unlike benchmarks that measure the *timing* of
interruptions (barge-in detection, endpointing, turn-taking), IHBench measures
what the agent says **after** an interruption: does it resume the workflow at the
correct step, address the user's interjection, and avoid re-delivering content the
user already heard?

The benchmark contains **45 synthetically generated, verified conversations**
across **10 enterprise domains**, with **428 interruption points** spanning six
interruption types (normal, impatient, correction, topic switch, filler,
pushback). Each interruption carries a per-interruption evaluation rubric and is
scored on two axes: **task fulfillment** and **recovery quality**. Audio for every
user turn is embedded directly in the dataset.

**Links**
- Evaluation toolkit (code): <https://github.com/boson-ai/ihbench>
- Paper: [IHBench: Evaluating Post-Interruption Recovery in Voice Agents with Structured Workflows](https://arxiv.org/abs/2606.19595)

## Quick start

Evaluate a model with the official toolkit
(<https://github.com/boson-ai/ihbench>), which loads this dataset automatically
and runs the full infer → judge → summarize pipeline:

```bash
git clone https://github.com/boson-ai/ihbench && cd ihbench
pip install -e ".[api]"

# set API keys (the judge + OpenAI models use OPENAI_API_KEY; Gemini uses GEMINI_API_KEY)
cp .env.example .env   # then edit .env and fill in your key(s)

# 1. generate responses (auto-loads bosonai/ihbench)
python scripts/run_inference_api.py --config configs/gpt-realtime-2.yaml \
    --output responses/model.jsonl --epochs 3
# 2. judge them (TF vs. the baseline config + RQ rubrics)
python scripts/run_evaluate.py --responses responses/model.jsonl \
    --output results/model.jsonl --judge-config configs/judge.yaml
# 3. print task-fulfillment win rate + recovery-quality pass rate
python scripts/summarize_results.py results/
```

To score your own model, add a client + config (see the toolkit README) or
produce responses in the same JSONL format and run steps 2-3. The schema below
documents the raw fields for anyone consuming the data directly.

## Configs

### `conversations` (45 rows, default)

One row per conversation, trimmed to end at its final interruption turn. The
conversation always starts with an assistant message, so messages pair strictly:
assistant at even message indices, user at odd. Per-turn columns run `t = 1..20`
and are `None`/empty past a conversation's `num_turns`.

| Column | Type | Description |
|---|---|---|
| `conversation_id` | string | Unique id |
| `domain` | struct | `{id, name, description}` (one of 10 domains) |
| `goal` | string | The assistant's workflow goal |
| `system_message` | string | The assistant's full operating instructions (system prompt) |
| `knowledge_base` | struct | `{rationale, detailed_guidelines, known_user_information, stages[]}` |
| `user_intent` | struct | `{reaction_profile, description, emotion, user_hidden_information}` |
| `num_turns` | int | Number of populated turns |
| `assistant_turn_{t}_transcript` | string | Assistant utterance (delivered text) |
| `assistant_turn_{t}_original` | string | Full pre-truncation text if the turn was interrupted, else `None` |
| `user_turn_{t}_transcript` | string | User utterance |
| `user_turn_{t}_audio` | Audio (16 kHz) | The user turn's audio, embedded |
| `user_turn_{t}_interruption_type` | string | One of the six types, or `None` if not an interruption |
| `turn_{t}_tf_rubric` | string | Task Fulfillment criterion, or `None` |
| `turn_{t}_rq_rubrics` | list[string] | Recovery Quality criteria, or `[]` |

**Rubric semantics.** `turn_{t}_*_rubric` evaluates the assistant response that
**follows** the turn-`t` user interruption (i.e. the turn-`(t+1)` assistant
message the model under test must generate). `assistant_turn_{t}_original` exposes
the full utterance an interrupted assistant turn was cut off from (its `content`
is only the delivered prefix).

### `baseline` (428 rows)

The GPT-4o Audio responses used as the task-fulfillment comparison anchor (the TF
metric is a win rate against this baseline).

| Column | Type | Description |
|---|---|---|
| `conversation_id` | string | Conversation id |
| `interrupting_user_message_index` | int | Message index of the interrupting user turn |
| `turn` | int | Turn number (= `(index + 1) / 2`) |
| `response` | string | The baseline assistant response to that interruption |

## Evaluation

Each interruption is one evaluation sample. Give the model under test the system
prompt and the conversation history truncated at the interrupting user turn (the
interrupted assistant turn keeps only its delivered text; the user turn is the
embedded audio, or its transcript for text-only evaluation), have it generate the
next assistant response, and score it:

- **Task fulfillment**: a comparative judge picks the model's response vs. the
  GPT-4o Audio baseline (`baseline` config). The metric is the win rate.
- **Recovery quality**: a judge checks the response against the per-interruption
  `turn_{t}_rq_rubrics`; pass = all criteria met.

The official toolkit (see [Quick start](#quick-start)) implements this pipeline.

## Notes

- The dataset is built from synthetic conversations (English, 10 enterprise
  domains); rubrics inherit the biases of the generator and judge models.
- The 45 conversations / 428 interruption points are the evaluable set reported in
  the paper. One synthesized conversation and a few trailing interruption points
  that produced no usable evaluation item are excluded.

## Citation

```bibtex
@misc{ihbench2026,
  title         = {IHBench: Evaluating Post-Interruption Recovery in Voice Agents with Structured Workflows},
  author        = {Salimi, Ahmad and Ma, Wentao and Tang, Yuzhi and Shen, Dongming and Li, Mu and Smola, Alex},
  year          = {2026},
  eprint        = {2606.19595},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
}
```
