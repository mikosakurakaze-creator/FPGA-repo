"""Evidence validators required before exporting the GridDehaze system."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_cross_tile(result_dir: Path, build_dir: Path, golden_dir: Path,
                        package_dir: Path, source_root: Path) -> dict:
    """Require same-image 33x47 cold/warm RTL evidence for all 320 nodes."""
    result_dir, build_dir = Path(result_dir), Path(build_dir)
    golden_dir, package_dir, source_root = Path(golden_dir), Path(package_dir), Path(source_root)
    result_path = result_dir / "result.json"
    result = _load(result_path)
    if result.get("pass_result") is not True or result.get("kind") != "independent_full_graph_axi_rtl":
        raise ValueError("Cross-tile evidence is not a passing full-graph RTL run")
    if result.get("scope") != "exported RTL plus simulated AXI RAM; not PS, routed circuit or board":
        raise ValueError("Cross-tile run scope is not the exported full-graph RTL harness")
    if result.get("case_shape") != [33, 47] or result.get("nodes_exact") != 320:
        raise ValueError("Cross-tile evidence must be 33x47 and compare all 320 nodes")
    if result.get("cold_warm_exact") is not True or result.get("negative_control") is not True:
        raise ValueError("Cold/warm comparison or negative control is missing")
    if result.get("source_snapshot_stable") is not True:
        raise ValueError("Cross-tile run has no stable source snapshot")

    steps = result.get("steps", {})
    for name in ("simulation", "negative_control"):
        if steps.get(name, {}).get("exit_code") != 0:
            raise ValueError("Cross-tile step did not exit successfully: " + name)
        log = result_dir / (name + ".log")
        if not log.is_file() or sha(log) != steps[name].get("log_sha256"):
            raise ValueError("Cross-tile step log missing or changed: " + name)
    frames = result.get("frames", [])
    if len(frames) != 2 or any(f"pass={i} " not in frames[i] or "completed_csr=320" not in frames[i]
                               for i in range(2)):
        raise ValueError("Cross-tile cold/warm frame records are incomplete")
    sim_log = (result_dir / "simulation.log").read_text(encoding="utf-8", errors="replace")
    if "GDN_RTL_SEQUENCE_PASS frames=2 scope=all_320_nodes bad_model=1" not in sim_log:
        raise ValueError("Cross-tile simulation completion marker is missing")
    if "Fatal:" in sim_log:
        raise ValueError("Cross-tile simulation contains a fatal diagnostic")

    report_path = golden_dir / "report.json"
    golden = _load(report_path)
    if sha(report_path) != result.get("golden_report_sha256"):
        raise ValueError("Cross-tile result points to another Golden report")
    shape = golden.get("input_shape", [])
    if len(shape) < 2 or shape[-2:] != [33, 47]:
        raise ValueError("Frozen Golden case is not 33x47")
    if golden.get("manifest_sha256") != sha(package_dir / "manifest.json"):
        raise ValueError("Cross-tile Golden belongs to a different frozen package")
    golden_nodes = golden.get("nodes", [])
    expected = result.get("expected_nodes", [])
    if len(golden_nodes) != 320 or len(expected) != 320:
        raise ValueError("Golden or result does not enumerate all 320 nodes")
    for index, (golden_node, actual_record) in enumerate(zip(golden_nodes, expected)):
        for key in ("id", "bytes", "sha256"):
            if golden_node.get(key) != actual_record.get(key):
                raise ValueError(f"Cross-tile Golden identity mismatch at node {index}: {key}")
        raw_path = golden_dir / ("" if index == 0 else "nodes") / golden_node["file"]
        if not raw_path.is_file() or raw_path.stat().st_size != golden_node["bytes"] or sha(raw_path) != golden_node["sha256"]:
            raise ValueError(f"Frozen Golden raw node missing or changed: {index}")
        captured = result_dir / f"node_{index}.raw"
        if not captured.is_file() or captured.stat().st_size != golden_node["bytes"] or sha(captured) != golden_node["sha256"]:
            raise ValueError(f"Captured RTL node missing or differs from Golden: {index}")

    rtl_hashes = result.get("rtl_sha256", {})
    if not rtl_hashes or "griddehaze_frame_top.v" not in rtl_hashes:
        raise ValueError("Cross-tile result does not identify the tested RTL")
    rtl_dir = build_dir / "ip/griddehaze/hdl/verilog"
    for name, digest in rtl_hashes.items():
        candidate = rtl_dir / name
        if not candidate.is_file() or sha(candidate) != digest:
            raise ValueError("Cross-tile RTL differs from the implementation input: " + name)

    source_hashes = result.get("test_source_sha256", {})
    required_sources = {
        "frame_axi_test.sv": source_root / "system/frame_axi_test.sv",
        "axi_bounded_memory.sv": source_root / "system/axi_bounded_memory.sv",
        "frame_rtl_trial.py": source_root / "tools/frame_rtl_trial.py",
        "ddr_fixture.py": source_root / "tools/ddr_fixture.py",
    }
    for name, source in required_sources.items():
        if source_hashes.get(name) != sha(source):
            raise ValueError("Cross-tile test source is stale or not identified: " + name)
    for name, output_name in (("frame_axi_test.sv", "frame_axi_test.sv"),
                              ("axi_bounded_memory.sv", "axi_bounded_memory.sv"),
                              ("frame_rtl_trial.py", "frame_rtl_trial.py"),
                              ("ddr_fixture.py", "ddr_fixture.py")):
        expected_hash = result.get("compiled_source_sha256", {}).get(name)
        copied = result_dir / output_name
        if not expected_hash or not copied.is_file() or sha(copied) != expected_hash:
            raise ValueError("Executed cross-tile source copy is missing or changed: " + name)

    fixture_path = result_dir / "ddr_fixture.json"
    if not fixture_path.is_file() or sha(fixture_path) != result.get("ddr_fixture_sha256"):
        raise ValueError("Cross-tile simulated DDR fixture is missing or changed")
    fixture = _load(fixture_path)
    if fixture.get("kind") != "simulated_disjoint_low_ddr_not_board_allocation":
        raise ValueError("DDR fixture is not explicitly labelled as simulation-only")
    regions = sorted(fixture.get("regions", []), key=lambda r: r["base"])
    if len(regions) != 5 or not fixture.get("cross_master_overlap_check"):
        raise ValueError("DDR fixture does not enumerate all five shared-address regions")
    for i, region in enumerate(regions):
        base, size = region["base"], region["allocation_bytes"]
        if base % 64 or size <= 0 or size % 64 or base + size > 0x80000000:
            raise ValueError("DDR fixture contains an invalid low-DDR slot")
        if i and regions[i - 1]["base"] + regions[i - 1]["allocation_bytes"] > base:
            raise ValueError("DDR fixture contains overlapping HP0/HP3 slots")

    return {"pass_result": True, "shape": [33, 47], "nodes_exact": 320,
            "frames": 2, "rtl_files": len(rtl_hashes),
            "result_sha256": sha(result_path), "golden_report_sha256": sha(report_path),
            "ddr_fixture_sha256": sha(fixture_path)}


def parse_routed_timing(timing_text: str, route_text: str, drc_text: str | None = None) -> dict:
    """Parse and enforce the final Vivado routed timing and route reports."""
    headers = [i for i, line in enumerate(timing_text.splitlines())
               if "WNS(ns)" in line and "WPWS(ns)" in line]
    if not headers:
        raise ValueError("Timing summary table is missing")
    lines = timing_text.splitlines()
    metrics = None
    for header in headers:
        for line in lines[header + 1:header + 5]:
            values = line.split()
            if len(values) == 12:
                try:
                    metrics = [float(values[0]), float(values[1]), int(values[2]), int(values[3]),
                               float(values[4]), float(values[5]), int(values[6]), int(values[7]),
                               float(values[8]), float(values[9]), int(values[10]), int(values[11])]
                    break
                except ValueError:
                    continue
        if metrics is not None:
            break
    if metrics is None:
        raise ValueError("Could not parse routed WNS/WHS/WPWS summary")
    wns, tns, setup_fail, setup_total, whs, ths, hold_fail, hold_total, wpws, tpws, pulse_fail, pulse_total = metrics
    if min(wns, whs, wpws) < 0 or any((tns != 0, ths != 0, tpws != 0,
                                      setup_fail != 0, hold_fail != 0, pulse_fail != 0)):
        raise ValueError("Routed setup, hold, or pulse-width timing has a violation")

    check_names = ("no_clock", "constant_clock", "pulse_width_clock", "unconstrained_internal_endpoints",
                   "no_input_delay", "no_output_delay", "multiple_clock", "generated_clocks",
                   "loops", "partial_input_delay", "partial_output_delay", "latch_loops")
    for check in check_names:
        matches = re.findall(r"checking\s+" + re.escape(check) + r"\s*\((\d+)\)", timing_text)
        if not matches or any(int(value) != 0 for value in matches):
            raise ValueError("Routed check_timing is missing or nonzero: " + check)
    for phrase in ("There are 0 register/latch pins with no clock.",
                   "There are 0 register/latch pins with constant_clock.",
                   "There are 0 register/latch pins with multiple clocks.",
                   "There are 0 generated clocks that are not connected to a clock source."):
        if phrase not in timing_text:
            raise ValueError("Detailed routed timing check missing: " + phrase)
    clocks = re.findall(r"^\s*(\S+)\s+\{[^\r\n]*?\}\s+([0-9.]+)\s+([0-9.]+)\s*$", timing_text, re.M)
    if not clocks or any(abs(float(period) - 10.0) > 1e-6 or abs(float(freq) - 100.0) > 1e-6
                         for _, period, freq in clocks[:2]) or len(clocks) < 2:
        raise ValueError("Routed clock summary does not show the expected 100 MHz clocks")
    if "All user specified timing constraints are met." not in timing_text:
        raise ValueError("Vivado did not report all user timing constraints met")

    def route_count(label: str) -> int:
        match = re.search(r"# of " + re.escape(label) + r"\s*\.*\s*:\s*(\d+)", route_text)
        if not match:
            raise ValueError("Route status is missing: " + label)
        return int(match.group(1))
    routable = route_count("routable nets")
    fully_routed = route_count("fully routed nets")
    route_errors = route_count("nets with routing errors")
    if routable <= 0 or fully_routed != routable or route_errors != 0:
        raise ValueError("Routed design has incomplete or erroneous nets")
    result = {"pass_result": True, "wns_ns": wns, "whs_ns": whs, "wpws_ns": wpws,
            "setup_fail_endpoints": setup_fail, "hold_fail_endpoints": hold_fail,
            "pulse_fail_endpoints": pulse_fail, "clock_summary": clocks[:2],
            "routable_nets": routable, "fully_routed_nets": fully_routed,
            "route_errors": route_errors}
    if drc_text is not None:
        result["drc"] = parse_routed_drc(drc_text)
    return result


def parse_routed_drc(drc_text: str) -> dict:
    if "Design State : Fully Routed" not in drc_text:
        raise ValueError("Routed DRC report does not describe a fully routed design")
    found_match = re.search(r"Checks found:\s*(\d+)", drc_text)
    if not found_match:
        raise ValueError("Routed DRC report has no Checks found total")
    found = int(found_match.group(1))
    rows = re.findall(r"^\|\s*([A-Z0-9-]+)\s*\|\s*(Error|Critical Warning|Warning|Advisory)\s*\|[^\r\n]*?\|\s*(\d+)\s*\|\s*$",
                      drc_text, re.M)
    if not rows:
        raise ValueError("Routed DRC severity summary is missing")
    counted = sum(int(count) for _, _, count in rows)
    if counted != found:
        raise ValueError("Routed DRC summary count does not match checks found")
    severe = [{"rule": rule, "severity": severity, "checks": int(count)}
              for rule, severity, count in rows if severity in ("Error", "Critical Warning")]
    if severe:
        raise ValueError("Routed DRC contains errors or critical warnings: " + repr(severe))
    warnings = [{"rule": rule, "severity": severity, "checks": int(count)}
                for rule, severity, count in rows if severity == "Warning"]
    return {"pass_result": True, "checks_found": found, "warnings": warnings,
            "warning_checks": sum(row["checks"] for row in warnings), "severe_checks": 0}
