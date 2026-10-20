"""C 独立工作的一键入口。正式数据与外部模型可以随后显式接入。"""

import argparse
import json
import sys
from pathlib import Path

from mwm_eval.engine import ROOT, run_experiment


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run C's independent baseline/evaluation pipeline")
    parser.add_argument("--inputs", type=Path, default=ROOT/"data/integration/inputs.jsonl")
    parser.add_argument("--labels", type=Path, default=ROOT/"data/integration/labels.jsonl")
    parser.add_argument("--config", type=Path, default=ROOT/"configs/external.example.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT/"results/full_run")
    parser.add_argument("--methods", default="B0,B1,B2,B3,B4,B5,B6,B7,B8,B9,B10,MENTIS_STRUCTURED")
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--suite", choices=("core", "all"), default="all")
    parser.add_argument("--enable-external", action="store_true")
    args = parser.parse_args()
    methods = args.methods.split(",")
    seeds = [int(seed) for seed in args.seeds.split(",")]
    if not seeds or len(set(seeds)) != len(seeds) or len(set(methods)) != len(methods):
        parser.error("methods and seeds must be nonempty and unique")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    print("开始运行 C 的独立基线与评测流程；没有配置的外部方法会明确标记 unavailable。", flush=True)
    summary, status = run_experiment(args.inputs, args.labels, args.output_dir, config, methods, seeds,
                                     suite=args.suite, enable_external=args.enable_external)
    print(f"运行完成：{args.output_dir.resolve() / 'report.md'}", flush=True)
    failed = [run for run in summary["runs"] if run["status"] == "error"]
    print(f"真实运行错误数：{len(failed)}；外部待接入：{','.join(status['external_methods_not_run'])}", flush=True)
    if failed:
        raise SystemExit(1)
    if status["overall"] == "no_methods_executed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
