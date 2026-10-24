"""Retain raw-dump comparator positive and negative tests for a chosen bundle.

All candidate files are synthetic copies or intentional corruptions of Golden
files. None are represented as FPGA or board captures.
"""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

from .io import sha256


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--golden", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="new directory; existing evidence is preserved")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    package, golden, out = args.package.resolve(), args.golden.resolve(), args.out.resolve()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    input_meta = json.loads((golden / "input.json").read_text(encoding="utf-8"))
    bundle = manifest["identity"]["bundle_id"]
    original = (golden / "output.raw").read_bytes()
    out.mkdir(parents=True, exist_ok=False)
    same = out / "candidate_exact.raw"; same.write_bytes(original)
    one_lsb = np.frombuffer(original, dtype="<i2").copy()
    one_lsb[0] += 1 if one_lsb[0] < 32767 else -1
    changed = out / "candidate_one_lsb.raw"; changed.write_bytes(one_lsb.tobytes())
    short = out / "candidate_truncated.raw"; short.write_bytes(original[:-1])
    records = []
    provenance = dict(python=sys.version, platform=platform.platform(), package=str(package), golden=str(golden),
                      bundle_id=bundle, manifest_sha256=sha256(package / "manifest.json"),
                      input_sha256=input_meta["sha256"], golden_output_sha256=sha256(golden / "output.raw"),
                      source_module_sha256=sha256(Path(__file__)), command=sys.argv,
                      candidates={p.name: sha256(p) for p in (same, changed, short)}, hardware_test=False,
                      candidate_origin="synthetic_copies_and_corruptions_for_comparator_testing")

    def execute(name, arguments, expected_exit):
        command = [sys.executable] + arguments
        start = time.time()
        completed = subprocess.run(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        log = out / (name + ".log")
        log.write_text(completed.stdout, encoding="utf-8")
        record = dict(name=name, command=command, cwd=str(root), started_unix=start, elapsed_seconds=time.time() - start,
                      actual_exit=completed.returncode, expected_exit=expected_exit,
                      expectation_met=completed.returncode == expected_exit, log=str(log))
        records.append(record)
        (out / "status.json").write_text(json.dumps(dict(**provenance, records=records,
            all_expectations_met=all(r["expectation_met"] for r in records)), indent=2) + "\n", encoding="utf-8")
        print(name, completed.returncode, "expected", expected_exit, flush=True)

    execute("unit_tests", ["-m", "unittest", "griddehaze_fixed.test_compare_fpga", "-v"], 0)
    base = ["-m", "griddehaze_fixed.compare_fpga", "--golden-dir", str(golden), "--package", str(package),
            "--bundle-id", bundle, "--input-sha256", input_meta["sha256"]]
    execute("exact_final", base + ["--actual-output", str(same), "--report", str(out / "exact_final.json")], 0)
    execute("exact_all_nodes", base + ["--actual-output", str(same), "--actual-nodes", str(golden / "nodes"),
                                     "--report", str(out / "exact_all_nodes.json")], 0)
    execute("reject_one_lsb", base + ["--actual-output", str(changed), "--report", str(out / "reject_one_lsb.json")], 1)
    execute("reject_truncated", base + ["--actual-output", str(short), "--report", str(out / "reject_truncated.json")], 1)
    wrong = base.copy(); wrong[wrong.index("--bundle-id") + 1] = "0" * 64
    execute("reject_wrong_bundle", wrong + ["--actual-output", str(same), "--report", str(out / "reject_wrong_bundle.json")], 1)
    raise SystemExit(0 if all(r["expectation_met"] for r in records) else 1)


if __name__ == "__main__":
    main()
