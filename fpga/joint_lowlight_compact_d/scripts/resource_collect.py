"""Collect actual Vivado joint synthesis evidence, refusing unfinished runs."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def parse_resources(util):
    rows = {}
    for label in ("CLB LUTs", "CLB Registers", "Block RAM Tile", "URAM", "DSPs"):
        m = re.search(r"^\|\s*" + re.escape(label) + r"\*?\s*\|([^\n]+)", util, re.M)
        assert m, f"Missing actual report row: {label}"
        cols = [x.strip() for x in m[1].strip().strip("|").split("|")]
        used, available = float(cols[0]), float(cols[-2])
        rows[label] = {"used": used, "available": available,
                       "remaining": available - used, "percent": float(cols[-1])}
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    args = ap.parse_args()
    log = (args.build / "synth.log").read_text(errors="replace")
    assert re.search(r"^JOINT_FOUR_CORE_SYNTHESIS_PASS\s*$", log, re.M), "No completed joint synthesis"
    manifest = json.loads((args.build / "frozen_inputs.json").read_text())
    input_count = 0
    for relative, expected in manifest["frozen_input_files"].items():
        assert hashlib.sha256((args.build / relative).read_bytes()).hexdigest() == expected, relative
        input_count += 1
    seed = Path(manifest["lowlight_seed"])
    assert hashlib.sha256(seed.read_bytes()).hexdigest() == manifest["lowlight_seed_sha256"]
    original_roots = manifest.get("lowlight_package_roots", {
        "cnn": str(seed.parents[6] / "ip_primary_05"),
        "bilinear": str(seed.parents[5] / "stable_ip_repo/bilinear"),
        "curve": str(seed.parents[5] / "stable_ip_repo/curve"),
    })
    original_count = 0
    for relative, expected in manifest["frozen_input_files"].items():
        parts = Path(relative).parts
        if parts[1] in original_roots:
            original = Path(original_roots[parts[1]]).joinpath(*parts[2:])
            assert hashlib.sha256(original.read_bytes()).hexdigest() == expected, str(original)
            original_count += 1
    repo = Path(__file__).resolve().parents[3]
    original_d = subprocess.check_output(["git", "show", manifest["compact_d_commit"] +
        ":compact_d_fpga/board/k26_compact_d_20261025/compact_d_ip.zip"], cwd=repo)
    assert hashlib.sha256(original_d).hexdigest() == manifest["compact_d_ip_zip_sha256"]
    util = (args.build / "reports/joint_utilization.rpt").read_text()
    rows = parse_resources(util)
    cores = {}
    for name in ("zero_dce_cnn_top_0", "bilinear_fixed16_buffered_0",
                 "curve_image_fixed16_0", "compact_d_top_0"):
        src = args.build / "reports" / f"core_{name}_utilization.rpt"
        cores[name] = parse_resources(src.read_text())
        assert cores[name]["CLB LUTs"]["used"] > 0, f"Core optimized away: {name}"
    args.dest.mkdir(parents=True, exist_ok=True)
    evidence = {}
    for name in ("joint_utilization.rpt", "joint_utilization_hierarchical.rpt",
                 "joint_synthesis_timing.rpt", "joint_clocks.rpt", "joint_synthesis_drc.rpt",
                 "joint_system_recreate.tcl", "ip_status.rpt"):
        src = args.build / "reports" / name
        dst = args.dest / ("resource_" + name)
        shutil.copy2(src, dst)
        evidence[dst.name] = hashlib.sha256(dst.read_bytes()).hexdigest()
    for name in ("synth.log", "frozen_inputs.json"):
        dst = args.dest / ("resource_" + name)
        shutil.copy2(args.build / name, dst)
        evidence[dst.name] = hashlib.sha256(dst.read_bytes()).hexdigest()
    for src in sorted((args.build / "reports").glob("core_*_utilization.rpt")):
        dst = args.dest / ("resource_" + src.name)
        shutil.copy2(src, dst)
        evidence[dst.name] = hashlib.sha256(dst.read_bytes()).hexdigest()
    checkpoint = args.build / "joint_synth.dcp"
    result = {
        "status": "synthesis_completed", "device": "xck26-sfvc784-2LV-c",
        "scope": "Frozen lowlight three cores plus frozen Compact D and shared AXI/DDR CDC fabric",
        "excluded": ["encoding adapters", "three-way fusion", "implementation", "board run"],
        "build_directory": str(args.build.resolve()), "resources": rows,
        "retained_core_resources": cores,
        "post_synthesis_validation": {"fully_linked_open_run": True,
            "four_unique_retained_core_hierarchies": True,
            "each_retained_core_has_nonzero_luts": True, "unresolved_blackbox_count": 0,
            "basis": "Actual per-core reports and terminal PASS after Tcl hierarchy/blackbox gates"},
        "input_reverification": {"copied_files_unchanged": input_count,
            "original_lowlight_files_unchanged": original_count,
            "original_lowlight_seed_unchanged": True, "original_compact_d_zip_unchanged": True},
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "evidence_sha256": evidence,
    }
    (args.dest / "resource_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
