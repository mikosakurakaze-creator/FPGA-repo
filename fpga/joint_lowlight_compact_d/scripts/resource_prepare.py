"""Copy frozen inputs to an isolated joint resource-check project (no Git writes)."""
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

D_COMMIT = "8c202508d267151c4ae034975b17947818be7865"
D_ZIP = "compact_d_fpga/board/k26_compact_d_20261025/compact_d_ip.zip"
D_SHA = "7d276942544f3785bde9267484da6d08bbae819cd46b8bb8e7214ea8a5603bc4"
CNN_SHA = "7e046bd557997e8a8b55b466ee9a76b8c3c321f1435df2879a8bf92a45f54ecd"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lowlight", type=Path,
                    default=Path("E:/HLS/kv260_three_module_v1_2_phase4/phase4g"))
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[3]
    out = args.out.resolve()
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing isolated build: {out}")
    sources = {
        "cnn": args.lowlight / "ip_primary_05",
        "bilinear": args.lowlight / "integration_01/stable_ip_repo/bilinear",
        "curve": args.lowlight / "integration_01/stable_ip_repo/curve",
    }
    seed = args.lowlight / "integration_01/project/v12_wc.srcs/sources_1/bd/system/system.bd"
    assert sha(sources["cnn"] / "component.xml") == CNN_SHA, "Frozen CNN mismatch"
    assert seed.is_file()
    blob = subprocess.check_output(["git", "show", f"{D_COMMIT}:{D_ZIP}"], cwd=repo)
    assert hashlib.sha256(blob).hexdigest() == D_SHA, "Frozen D IP ZIP mismatch"
    out.mkdir(parents=True)
    (out / "compact_d_ip.zip").write_bytes(blob)
    with zipfile.ZipFile(out / "compact_d_ip.zip") as z:
        z.extractall(out / "ip/compact_d")
    assert (out / "ip/compact_d/component.xml").is_file()
    for name, source in sources.items():
        shutil.copytree(source, out / "ip" / name)
    shutil.copy2(seed, out / "lowlight_seed.bd")
    (out / "reports").mkdir()
    manifest = {
        "purpose": "Synthesis-only four-core joint resource check; no fusion or board claim",
        "lowlight_seed": str(seed), "lowlight_seed_sha256": sha(seed),
        "lowlight_package_roots": {name: str(path.resolve()) for name, path in sources.items()},
        "compact_d_commit": D_COMMIT, "compact_d_ip_zip_sha256": D_SHA,
        "frozen_input_files": {
            str(p.relative_to(out)): sha(p)
            for p in sorted((out / "ip").rglob("*")) if p.is_file()
        },
    }
    (out / "frozen_inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"prepared": str(out), "frozen_input_files": len(manifest["frozen_input_files"])}))


if __name__ == "__main__":
    main()
