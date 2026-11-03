"""Freeze and check the exact tested sources without rewriting prior results."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    args = parser.parse_args()
    suite = args.suite.resolve()
    target = suite / "source_evidence_audit01.json"
    if target.exists():
        raise ValueError("Preserve the previous audit")
    result = {"pass": False, "board_operations": 0, "bound_files": {},
              "verified_tests": [], "preserved_failures": []}

    def bind(path, expected=None):
        digest = sha(path)
        if expected is not None and digest != expected:
            raise ValueError("Evidence identity mismatch: " + str(path))
        result["bound_files"][path.resolve().as_posix()] = digest

    try:
        for name in ("rtl03", "tail01", "full01", "bandwidth03", "same_image01", "package01", "verify02"):
            folder = suite / name
            record_path = folder / "result.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            bind(record_path)
            if not record["pass"]:
                raise ValueError("Required evidence failed: " + name)
            for relative, expected in record.get("source_sha256", record.get("sources", {})).items():
                bind(folder / Path(relative).name, expected)
            for relative, expected in record.get("reports", {}).items():
                bind(folder / relative, expected)
            for step in record["steps"]:
                if step.get("return_code", step.get("exit_code")) != 0:
                    raise ValueError("Failed process: " + name)
                candidates = [p for p in folder.glob("*.log") if sha(p) == step["log_sha256"]]
                if len(candidates) != 1:
                    raise ValueError("Missing or ambiguous log: " + name)
                bind(candidates[0], step["log_sha256"])
            for file in folder.glob("*.tcl"):
                bind(file)
            result["verified_tests"].append(name)
        checkpoint = suite / "ooc01/ooc/fusion_ooc.dcp"
        record = json.loads((suite / "verify02/result.json").read_text())
        bind(checkpoint, record["checkpoint_sha256"])

        folder = suite / "controller_tests01"
        record = json.loads((folder / "result.json").read_text())
        bind(folder / "result.json")
        if not record["pass"] or record["exit_code"] != 0:
            raise ValueError("Controller regression failed")
        bind(folder / "tests.log", record["log_sha256"])
        for relative, expected in record["source_sha256"].items():
            source = ROOT / relative
            bind(source, expected)
            frozen = folder / "source" / relative
            frozen.parent.mkdir(parents=True, exist_ok=True)
            if frozen.exists():
                bind(frozen, expected)
            else:
                shutil.copy2(source, frozen)
                bind(frozen, expected)
        result["verified_tests"].append("controller_tests01 (host mock only)")
        for name in ("rtl01", "ooc01", "verify01", "bandwidth02"):
            folder = suite / name
            record = json.loads((folder / "result.json").read_text())
            if record["pass"]:
                raise ValueError("Expected preserved failure changed: " + name)
            bind(folder / "result.json")
            for log in folder.glob("*.log"):
                bind(log)
            result["preserved_failures"].append(name)
        result["pass"] = True
    except Exception as exc:
        result["error"] = str(exc)
        raise
    finally:
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"pass": result["pass"], "output": str(target),
                          "files": len(result["bound_files"]),
                          "error": result.get("error")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
