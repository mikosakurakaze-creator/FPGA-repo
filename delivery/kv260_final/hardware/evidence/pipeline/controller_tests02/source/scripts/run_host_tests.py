"""Run host regressions against frozen sources in a new evidence directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = list((ROOT / "runtime").glob("*.py")) + list((ROOT / "tests").glob("test_*.py"))
    sources += [ROOT / "scripts/accept_system.py", Path(__file__).resolve()]
    source_hashes = {}
    for source in sources:
        relative = source.relative_to(ROOT)
        target = out / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hashes[relative.as_posix()] = sha(target)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(out / "source/runtime")
    command = [sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover",
               "-s", str(out / "source/tests"), "-p", "test_*.py", "-v"]
    log = out / "tests.log"
    with log.open("xb") as stream:
        process = subprocess.run(command, cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT)
    passed = process.returncode == 0 and "\nOK\n" in log.read_text().replace("\r\n", "\n")
    result = {"pass": passed, "exit_code": process.returncode, "command": command,
              "source_sha256": source_hashes, "log_sha256": sha(log), "board_operations": 0,
              "scope": "frozen-source host regressions; ring DMA ownership, scheduling, metrics and report parsers; no FPGA FPS claim"}
    (out / "result.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
