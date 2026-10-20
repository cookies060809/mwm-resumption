"""Run A-owned input diagnostics, leaving B's data/schema untouched."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.ecr_mwm.p0_diagnostics import run_diagnostics  # noqa: E402


def main():
    path = ROOT / "data/p0/p0_samples.json"
    report = run_diagnostics(json.loads(path.read_text(encoding="utf-8")))
    report["data_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    report["schema_sha256"] = hashlib.sha256((ROOT / "schema/p0_record.schema.json").read_bytes()).hexdigest()
    report["code_base_commit"] = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    report["code_sha256"] = {str(p.relative_to(ROOT)).replace("\\", "/"):
                              hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                                  ROOT / "models/ecr_mwm/p0_adapter.py",
                                  ROOT / "models/ecr_mwm/p0_diagnostics.py")}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
