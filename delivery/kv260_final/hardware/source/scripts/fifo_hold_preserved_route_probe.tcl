# Independently repair the retained eight-cell moved checkpoint, preserving
# completed routing. A failed source experiment remains failed.
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set setup_target [lindex $argv 3]
set hold_target [lindex $argv 4]
set source_dir {D:/weather_builds/timing_margin_20261102/hold_recreate_control01}
set_param general.maxThreads 8
open_checkpoint $checkpoint
source [file join $source_dir fifo_hold_relocate.tcl]
set f [open [file join $source_dir relocation_records.list] r]
set records [read $f]; close $f
file copy [file join $source_dir relocation_records.list] [file join $out relocation_records.list]
verify_fifo_relocation [file join $out relocation_records.list] [file join $out before_route.tsv]
puts {HOLD_RELOCATE_PHASE=preserve_completed_routes}
route_design -preserve
verify_fifo_relocation [file join $out relocation_records.list] [file join $out after_route.tsv]
report_route_status -file [file join $out route_status.rpt]
report_drc -file [file join $out drc.rpt]
report_timing_summary -delay_type min_max -file [file join $out timing.rpt]
set f [open [file join $out changed_path_checks.tsv] w]
puts $f "endpoint\tbefore_hold_ns\tafter_hold_ns\tafter_setup_ns"
set target_miss 0
foreach record $records {
    lassign $record cell endpoint loc bel signature hs ss
    set after [get_property SLACK [get_timing_paths -delay_type min -to [get_pins $endpoint] -max_paths 1]]
    set setup [get_property SLACK [get_timing_paths -delay_type max -to [get_pins $endpoint] -max_paths 1]]
    puts $f "$endpoint\t$hs\t$after\t$setup"
    if {$after<$hold_target || $after<=$hs || $setup<$setup_target} {set target_miss 1}
}
close $f
write_checkpoint [file join $out repaired_routed.dcp]
if {$target_miss} {error {Representative preserved-route repair misses margins}}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]]} {error {Probe DRC failure}}
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
