"""Check the standalone release against an A Git revision without checking out it.

Only model Python sources are read from Git into a temporary directory. Inference
uses default, untrained parameters; this is a compatibility check, not evaluation
or training. No Git fetch, branch switch, data modification or prediction export.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_p0_release import OUT, main as check_release  # noqa: E402

WORKER = """
from collections import Counter
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from models.ecr_mwm.training import p0_example
from models.ecr_mwm.structured import infer
records = json.loads(Path(sys.argv[2]).read_bytes())
examples = [p0_example(record) for record in records]
failures = []
for record, example in zip(records, examples):
    try:
        pred = infer(example.inputs)['prediction']
        p = pred['t1_resume_probability']
        if not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError('invalid resume probability')
        distributions = list(pred['t3_state_distributions'].values())
        if pred['t2_conditional_step_distribution'] is not None:
            distributions.append(pred['t2_conditional_step_distribution'])
        for dist in distributions:
            if (any(not math.isfinite(p) or p < 0 for p in dist.values()) or
                    abs(sum(dist.values()) - 1) > 1e-9):
                raise ValueError('invalid distribution')
    except Exception as error:
        failures.append({'sample_id': record['sample_id'], 'error': repr(error)})
print(json.dumps({'training_example_records': len(examples),
                  'splits': dict(Counter(e.split for e in examples)),
                  'inference_records': len(records), 'failures': failures}))
sys.exit(bool(failures))
"""


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-ref", required=True, help="locally available A branch or commit (no fetch)")
    args = parser.parse_args()
    if check_release(["--check"]):
        return 1
    try:
        commit = git("rev-parse", "--verify", "--end-of-options", args.a_ref + "^{commit}").decode().strip()
        paths = git("ls-tree", "-r", "--name-only", commit).decode().splitlines()
        cache = (ROOT / ".workbuddy" / "release_checks").resolve()
        if not cache.is_relative_to(ROOT.resolve()):
            raise ValueError("TEMP_ROOT_OUTSIDE_WORKSPACE")
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="p0-v03-a-", dir=cache) as folder:
            for name in paths:
                if name.startswith("models/") and name.endswith(".py"):
                    # Git paths are data; reject traversal before writing files.
                    target = (Path(folder) / name).resolve()
                    if not target.is_relative_to(Path(folder).resolve()):
                        raise ValueError("MODEL_PATH_OUTSIDE_TEMP")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(git("show", f"{commit}:{name}"))
            completed = subprocess.run(
                [sys.executable, "-c", WORKER, folder, str(OUT / "p0_samples.json")],
                text=True, encoding="utf-8", capture_output=True)
            if completed.returncode and not completed.stdout.strip():
                print(completed.stderr, file=sys.stderr)
                return 1
            report = json.loads(completed.stdout)
            report.update({"kind": "untrained_exact_inference_compatibility_only",
                           "a_commit": commit,
                           "release_sha256": hashlib.sha256((OUT / "p0_samples.json").read_bytes()).hexdigest()})
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return completed.returncode
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"A_COMPATIBILITY_CHECK_FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
