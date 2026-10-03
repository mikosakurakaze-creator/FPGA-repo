"""Read-only hash audit of original protected work and the isolated RTL overlay."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = Path("E:/HLS/kv260_three_module_v1_2_phase4")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    assert not args.output.exists(), args.output
    recovery = json.loads((EVIDENCE / "recovery_manifest.json").read_text())
    changed = [p for p, record in recovery["files"].items()
               if not Path(p).is_file() or sha(Path(p)) != record["sha256"]]
    assert not changed, changed
    spec = importlib.util.spec_from_file_location("candidate_builder", HERE / "build_writecredit_candidate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    candidate = module.CANDIDATE
    manifest = json.loads((candidate / "candidate_manifest.json").read_text())
    for p, expected in manifest["frozen_cpp"].items():
        assert sha(Path(p)) == expected, p
    for name in ("zero_dce_cnn_top.cpp", "zero_dce_cnn_top.h", "tb_zero_dce_cnn_dump.cpp"):
        assert (candidate / name).read_bytes() == (module.FROZEN / name).read_bytes(), name
    transforms = [lambda t: module.helper(t, "workspace"),
                  lambda t: module.helper(t, "output"), module.caller]
    for record, transform in zip(manifest["overlays"], transforms):
        frozen = Path(record["frozen"])
        overlay = candidate / "rtl" / record["name"]
        assert sha(frozen) == record["frozen_sha256"]
        assert sha(overlay) == record["candidate_sha256"]
        assert overlay.read_text() == transform(frozen.read_text())
    result = {"status": "PASS", "original_protected_files": len(recovery["files"]),
              "original_changed": changed, "frozen_cpp_files": len(manifest["frozen_cpp"]),
              "candidate_math_reference_byte_identical": True,
              "rtl_overlays_reproduced_exactly": len(manifest["overlays"]),
              "credit_limit": manifest["credit_limit"],
              "scope": "Three writer control overlays only; original recovery manifest unchanged."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
