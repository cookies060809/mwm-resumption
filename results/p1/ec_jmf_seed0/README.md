# P1-only EC-JMF training and mechanism ablations

All state parameters start randomly; no P0 data, weights or Git objects are read.
IH is heuristic weak supervision. REBOOT recovery labels are positive-only; AUROC is undefined.
InterruptBench supplies V only. Other latent-state distributions are not validated state truth.
The test splits were previously exposed and are repeated evaluations, not new blind tests.

Reproduce from the repository root:

```powershell
python -m models.ecr_mwm.p1_training --config configs/a_ec_jmf_p1.json
python -m models.ecr_mwm.p1_training --predict "results\p1\ec_jmf_seed0\model.pt" --split test --source IHBench --limit 3
```

If the configured results directory already exists, reproduce into a new empty path with `--output results/p1/ec_jmf_reproduction`; existing outputs are never overwritten.
The final representative model is saved immediately after its complete 40-epoch run and dev selection. Full comparison/report completion still requires all declared runs; model.pt alone does not mean the experiment finished.
The seed field controls development checks; evaluation_seeds=0..19 controls the formal experiment.
Fixed seed0 tie-shuffled event-length minibatch grouping is shared across variants and seeds; seed-specific shuffled minibatch order is paired across variants.
All train/dev selections finish before test scoring. Retained checkpoint: A0, first declared seed, never chosen by test.
Full 20-seed protocol completed: False.

| Variant | Source/window | T1 Brier mean ± SD | T2 top1 mean ± SD | V accuracy mean ± SD |
|---|---|---:|---:|---:|
| A0 | IHBench/assistant_turn | 0.0531 (single seed) | 0.4286 (single seed) | 1.0000 (single seed) |
| A0 | IHBench/single_response | 0.3477 (single seed) | 0.6383 (single seed) | 1.0000 (single seed) |
| A0 | InterruptBench/unobserved | undefined | undefined | 0.9418 (single seed) |
| A0 | REBOOT/episode_tail | 0.0000 (single seed) | 0.4545 (single seed) | 1.0000 (single seed) |
| A1 | IHBench/assistant_turn | 0.0483 (single seed) | 0.4286 (single seed) | 1.0000 (single seed) |
| A1 | IHBench/single_response | 0.2295 (single seed) | 0.6383 (single seed) | 1.0000 (single seed) |
| A1 | InterruptBench/unobserved | undefined | undefined | 0.9564 (single seed) |
| A1 | REBOOT/episode_tail | 0.0000 (single seed) | 0.4545 (single seed) | 1.0000 (single seed) |
| A2 | IHBench/assistant_turn | 0.0511 (single seed) | 0.4286 (single seed) | 1.0000 (single seed) |
| A2 | IHBench/single_response | 0.4197 (single seed) | 0.5957 (single seed) | 1.0000 (single seed) |
| A2 | InterruptBench/unobserved | undefined | undefined | 0.9418 (single seed) |
| A2 | REBOOT/episode_tail | 0.0000 (single seed) | 0.4545 (single seed) | 1.0000 (single seed) |
| A3 | IHBench/assistant_turn | 0.0533 (single seed) | 0.4107 (single seed) | 1.0000 (single seed) |
| A3 | IHBench/single_response | 0.3909 (single seed) | 0.6383 (single seed) | 1.0000 (single seed) |
| A3 | InterruptBench/unobserved | undefined | undefined | 0.9418 (single seed) |
| A3 | REBOOT/episode_tail | 0.0000 (single seed) | 0.4545 (single seed) | 1.0000 (single seed) |
| A4 | IHBench/assistant_turn | 0.0513 (single seed) | 0.4286 (single seed) | 1.0000 (single seed) |
| A4 | IHBench/single_response | 0.3694 (single seed) | 0.6383 (single seed) | 1.0000 (single seed) |
| A4 | InterruptBench/unobserved | undefined | undefined | 0.9418 (single seed) |
| A4 | REBOOT/episode_tail | 0.0000 (single seed) | 0.4545 (single seed) | 1.0000 (single seed) |
| A5 | IHBench/assistant_turn | 0.0491 (single seed) | 0.1607 (single seed) | 1.0000 (single seed) |
| A5 | IHBench/single_response | 0.2228 (single seed) | 0.0213 (single seed) | 1.0000 (single seed) |
| A5 | InterruptBench/unobserved | undefined | undefined | 0.9636 (single seed) |
| A5 | REBOOT/episode_tail | 0.0001 (single seed) | 0.1818 (single seed) | 1.0000 (single seed) |
| A6 | IHBench/assistant_turn | 0.0496 (single seed) | 0.4286 (single seed) | 1.0000 (single seed) |
| A6 | IHBench/single_response | 0.2149 (single seed) | 0.6383 (single seed) | 1.0000 (single seed) |
| A6 | InterruptBench/unobserved | undefined | undefined | 0.6655 (single seed) |
| A6 | REBOOT/episode_tail | 0.0000 (single seed) | 0.7273 (single seed) | 1.0000 (single seed) |

Complete per-seed metrics, denominators, zero-support counts, label origins and development selections are in report.json.
T1 metrics measure source-window recovery labels; T2 is conditional step identification; V is labeled objective validity.
Do not interpret these as real-person prediction, belief calibration, or unrestricted text understanding.
