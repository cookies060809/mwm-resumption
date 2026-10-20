"""Run the offline C delivery acceptance workflow using only the standard library."""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from mwm_eval.schema import canonical_hash, load_jsonl

ROOT = Path(__file__).resolve().parent
LOCAL = "B0,B1,B4,B5,B6,B7"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    verification_dir = ROOT / "results/verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    record = {"created_utc": datetime.now(timezone.utc).isoformat(), "overall": "running", "steps": []}

    def save():
        (verification_dir / "verification.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def step(name, arguments):
        print(f"执行：{name}", flush=True)
        result = subprocess.run([sys.executable, "-u", *arguments], cwd=ROOT,
                                env={**os.environ, "PYTHONUTF8": "1"}, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        log = result.stdout.decode("utf-8", errors="replace")
        (verification_dir / f"{name}.log").write_text(log, encoding="utf-8")
        record["steps"].append({"name": name, "exit_code": result.returncode,
                                "log": f"results/verification/{name}.log"})
        save()
        if result.returncode:
            print(log, flush=True)
            raise RuntimeError(f"{name} failed with exit code {result.returncode}")
        print("\n".join(log.strip().splitlines()[-3:]), flush=True)
        return log

    save()
    try:
        log = step("unit_tests", ["-m", "unittest", "discover", "-s", "tests", "-v"])
        import re
        match = re.search(r"Ran (\d+) tests", log)
        record["tests_passed"] = int(match.group(1)) if match else None
        step("experiment", ["run_evaluation.py"])
        step("dashboard_self_test", ["tools/build_dashboard.py", "--self-test"])
        step("dashboard", ["tools/build_dashboard.py"])
        original = load_jsonl(ROOT / "results/full_run/predictions.jsonl")

        def snapshot(rows):
            return {f"{row['method_id']}:{row['seed']}:{row['sample_id']}": {
                key: row[key] for key in ("status", "prediction", "input_hash", "source_input_hash")}
                    for row in rows if row["method_id"] in LOCAL.split(",")}

        with tempfile.TemporaryDirectory(prefix="mwm_c_repro_") as directory:
            step("reproducibility", ["run_evaluation.py", "--methods", LOCAL, "--suite", "core", "--output-dir", directory])
            rerun = load_jsonl(Path(directory) / "predictions.jsonl")
            before, after = snapshot(original), snapshot(rerun)
            if not before or before != after:
                raise RuntimeError("repeated local predictions differ")
            record["reproducibility"] = {"matched": True, "n_test_predictions": len(before),
                                         "prediction_sha256": canonical_hash(before), "seeds": [0, 1, 2],
                                         "excluded_from_comparison": "runtime timings and creation timestamp",
                                         "scope": "same inputs, same source, same local environment"}
        record["overall"] = "passed"
        save()
        step("package", ["tools/build_delivery.py"])
        print("C 独立工程验收通过。结果：results/full_run/demo.html；交付包：delivery/C_independent_bundle.zip", flush=True)
    except Exception as exc:
        record["overall"], record["error"] = "failed", f"{type(exc).__name__}: {exc}"
        save()
        raise


if __name__ == "__main__":
    main()
