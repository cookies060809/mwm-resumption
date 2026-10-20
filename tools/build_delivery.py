"""Build and verify the internal, offline engineering delivery (not a contest submission)."""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mwm_eval.schema import file_hash


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    summary = json.loads((ROOT / "results/full_run/summary.json").read_text(encoding="utf-8"))
    verified = json.loads((ROOT / "results/verification/verification.json").read_text(encoding="utf-8"))
    if summary["dataset_layer"] != "integration_fixture" or verified["overall"] != "passed":
        raise ValueError("This engineering bundle requires verified integration fixtures")
    # Explicit engineering allowlist. Personal/internal docs and third-party
    # source data never enter this bundle through a recursive docs/data glob.
    files = [ROOT / name for name in ("README.md", "CONTRIBUTING.md", "pyproject.toml",
             "requirements-dev.txt", "run_evaluation.py", "run_full_check.py", "开始完整自检.cmd")]
    for folder in ("mwm_eval", "integration", "tools", "tests", "schema", "scripts", "models",
                   "baselines", "evaluation", "data/p0", "data/integration",
                   "results/full_run", "results/verification"):
        files.extend(path for path in (ROOT / folder).rglob("*") if path.is_file()
                     and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"})
    files += [ROOT / "configs" / name for name in
              ("external.example.json", "ablation_matrix.json", "a_ec_jmf_reference.json", "base.yaml")]
    files.append(ROOT / ".gitignore")
    # Upstream regression tests require these two unsigned technical audit packets.
    files += [ROOT / "docs/annotation" / name for name in
              ("p0_spot_audit_v0.2_seed20261021.md", "p0_spot_audit_v0.3_all7.md")]
    # package.log is still being written by the parent wrapper; verification.json
    # records all pre-package checks and the outer checksum file proves packaging.
    files = sorted({path for path in files if path.exists() and path.name != "package.log"})
    manifest = {"purpose": "internal C engineering delivery; not final competition submission",
                "excluded": ["docs/internal", "docs/personal", "third-party raw data", "local configs", "credentials"],
                "dataset_layer": summary["dataset_layer"], "files_sha256": {
                    path.relative_to(ROOT).as_posix(): file_hash(path) for path in files}}
    delivery = ROOT / "delivery"
    delivery.mkdir(exist_ok=True)
    archive = delivery / "C_independent_bundle.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, "mwm-resumption/" + path.relative_to(ROOT).as_posix())
        bundle.writestr("mwm-resumption/BUNDLE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("archive CRC verification failed")
        for name, expected in manifest["files_sha256"].items():
            actual = hashlib.sha256(bundle.read("mwm-resumption/" + name)).hexdigest()
            if actual != expected:
                raise ValueError(f"archive file hash mismatch: {name}")
    result = {"archive": archive.name, "sha256": file_hash(archive), "n_source_files": len(files),
              "n_entries": len(files)+1, "size_bytes": archive.stat().st_size, "crc_and_file_hashes_verified": True,
              "scope": manifest["purpose"]}
    (delivery / "bundle_verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"工程包已生成并逐文件验证：{archive.name} ({len(files)} files)")
    print(f"SHA256: {result['sha256']}")


if __name__ == "__main__":
    main()
