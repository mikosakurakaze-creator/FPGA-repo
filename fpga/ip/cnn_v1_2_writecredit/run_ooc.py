"""Run actual 100 MHz out-of-context synthesis of the packaged IP sources."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from build_ip import NS, SYN, audit, inputs, run_vivado, save, sha, HERE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ip, output = args.ip.resolve(), args.output.resolve()
    assert not output.exists(), "Refuse to overwrite OOC evidence"
    lock = json.loads((HERE / "input_lock.json").read_text())
    assert inputs() == lock
    result, sources = audit(ip, lock)
    output.mkdir(parents=True)
    compile_sources = sources["filesets"][SYN]
    for entry in compile_sources:
        assert sha(ip / entry["path"]) == entry["sha256"]
    save(output / "synthesis_input_manifest.json", {"packaged_ip": ip.as_posix(), "fileset": SYN,
                                                   "sources": compile_sources,
                                                   "build_manifest_sha256": sha(ip / "build_manifest.json")})
    files = " ".join("{" + (ip / x["path"]).as_posix() + "}" for x in compile_sources if x["path"].startswith("hdl/"))
    script = output / "run_ooc.tcl"
    script.write_text(f'''set out {{{output.as_posix()}}}
create_project cnn_writecredit_ooc [file join $out project] -part xck26-sfvc784-2LV-c
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property include_dirs {{{(ip / 'hdl/verilog').as_posix()}}} [current_fileset]
set_param general.maxThreads 4
add_files -norecurse [list {files}]
set_property top zero_dce_cnn_top [current_fileset]
read_xdc {{{(ip / 'constraints/zero_dce_cnn_top_ooc.xdc').as_posix()}}}
update_compile_order -fileset sources_1
set f [open [file join $out actual_compile_order.txt] w]
foreach source [get_files -compile_order sources -used_in synthesis] {{puts $f $source}}
close $f
synth_design -top zero_dce_cnn_top -part xck26-sfvc784-2LV-c -mode out_of_context -flatten_hierarchy none
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -hierarchical_depth 5 -file [file join $out hierarchy_utilization.rpt]
report_timing_summary -delay_type min_max -max_paths 10 -file [file join $out timing_summary.rpt]
write_checkpoint [file join $out cnn_writecredit_ooc.dcp]
set f [open [file join $out hierarchy.tsv] w]
foreach cell [get_cells -hier -filter {{REF_NAME =~ *row_axi_writer* || REF_NAME =~ *output_writer*}}] {{
    puts $f "$cell\\t[get_property REF_NAME $cell]"
}}
close $f
set f [open [file join $out credit_nets.txt] w]
foreach net [get_nets -hier -filter {{NAME =~ *credit_count* || NAME =~ *write_credit_empty*}}] {{puts $f $net}}
close $f
set f [open [file join $out metrics.tsv] w]
puts $f "clock_period_ns\\t[get_property PERIOD [get_clocks ap_clk]]"
puts $f "LUT\\t[llength [get_cells -hier -filter {{REF_NAME =~ LUT*}}]]"
puts $f "FF\\t[llength [get_cells -hier -filter {{REF_NAME =~ FD*}}]]"
puts $f "BRAM36\\t[llength [get_cells -hier -filter {{REF_NAME =~ RAMB36*}}]]"
puts $f "BRAM18\\t[llength [get_cells -hier -filter {{REF_NAME =~ RAMB18*}}]]"
puts $f "URAM\\t[llength [get_cells -hier -filter {{REF_NAME =~ URAM*}}]]"
puts $f "DSP\\t[llength [get_cells -hier -filter {{REF_NAME =~ DSP*}}]]"
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {{[llength $setup]}} {{puts $f "setup_estimate_slack_ns\\t[get_property SLACK $setup]"}}
if {{[llength $hold]}} {{puts $f "pre_route_hold_slack_ns\\t[get_property SLACK $hold]"}}
close $f
puts {{PHASE4G_OOC_SYNTHESIS_PASS}}
close_project
exit
''', encoding="utf-8")
    try:
        run_vivado(script, output, "ooc")
    except Exception:
        save(output / "ooc_summary.json", {"status": "FAIL", "actual_exit": "Vivado nonzero", "logs": (output / "ooc_console.log").as_posix()})
        raise
    log = (output / "ooc_console.log").read_text(encoding="utf-8", errors="replace")
    assert "PHASE4G_OOC_SYNTHESIS_PASS" in log
    metrics = dict(line.split("\t", 1) for line in (output / "metrics.tsv").read_text().splitlines())
    metrics = {k: float(v) if "." in v else int(v) for k, v in metrics.items()}
    utilization = (output / "utilization.rpt").read_text()
    for metric, label in (("LUT", "CLB LUTs*"), ("FF", "CLB Registers"),
                          ("BRAM_tiles", "Block RAM Tile"), ("URAM", "URAM"), ("DSP", "DSPs")):
        match = re.search(r"^\|\s*" + re.escape(label) + r"\s*\|\s*([0-9.]+)\s*\|", utilization, re.MULTILINE)
        assert match, label
        value = float(match.group(1))
        metrics[metric] = int(value) if value.is_integer() else value
    assert metrics["clock_period_ns"] == 10
    hierarchy = [dict(zip(("path", "ref_name"), line.split("\t", 1))) for line in (output / "hierarchy.tsv").read_text().splitlines()]
    for stem in ("row_axi_writer", "row_axi_writer_2", "p_anonymous_namespace_output_writer"):
        assert any(stem in cell["ref_name"] for cell in hierarchy), stem
    credit_nets = (output / "credit_nets.txt").read_text().splitlines()
    assert any("credit_count" in name for name in credit_nets), "Credit state absent from synthesized hierarchy"
    # All declared Verilog sources must be the exact packaged files in the
    # Vivado compile order; headers/ROM data are held by the input manifest.
    actual = [Path(p).resolve() for p in (output / "actual_compile_order.txt").read_text().splitlines()]
    wanted = [ip / entry["path"] for entry in compile_sources if entry["path"].endswith(".v")]
    assert set(wanted).issubset(set(actual)), "Packaged RTL missing from compile order"
    assert inputs() == lock
    after, _ = audit(ip, lock)
    assert after == result
    save(output / "ooc_summary.json", {"status": "PASS", "actual_exit": 0, "top": "zero_dce_cnn_top",
                                       "part": "xck26-sfvc784-2LV-c", "clock_mhz": 100, "metrics": metrics,
                                       "resource_metrics_source": "Vivado report_utilization named rows: CLB LUTs, CLB Registers, Block RAM Tile, URAM, DSPs",
                                       "raw_counter_scope": "metrics.tsv REF_NAME-pattern diagnostic counts do not filter IS_PRIMITIVE; LUT/DSP can include hierarchy or macro cells and are not reported resource totals",
                                       "source_inputs": compile_sources, "hierarchy": hierarchy,
                                       "credit_nets": credit_nets,
                                       "patched_rtl": result["patched_rtl"], "compile_order_audit": "PASS",
                                       "checkpoint_sha256": sha(output / "cnn_writecredit_ooc.dcp"),
                                       "timing_scope": "Synthesis estimate only; pre-route hold is not final signoff",
                                       "implementation_run": False})
    print(json.dumps({"ooc_synthesis": "PASS", "metrics": metrics}))


if __name__ == "__main__":
    main()
