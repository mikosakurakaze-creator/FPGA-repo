# Eight-endpoint physical-only probe, sharing the production relocation helper.
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set selection {D:/weather_builds/timing_margin_20261102/hold_probe03/hold_eco_before_route.tsv}
set setup_target [lindex $argv 3]
set hold_target [lindex $argv 4]
set_param general.maxThreads 8
open_checkpoint $checkpoint
source [file join $out fifo_hold_relocate.tcl]
set f [open $selection r]; set lines [split [read $f] \n]; close $f
set records {}
foreach line [lrange $lines 1 8] {
    set endpoint [lindex [split $line \t] 1]
    set pin [get_pins $endpoint]
    set cell [get_cells -of_objects $pin]
    if {[llength $cell] != 1 || [get_property REF_NAME $cell] ne {FDRE}} {error {Unexpected probe endpoint}}
    set hp [get_timing_paths -delay_type min -to $pin -max_paths 1]
    set sp [get_timing_paths -delay_type max -to $pin -max_paths 1]
    set hs [get_property SLACK $hp]
    set ss [get_property SLACK $sp]
    if {$hs >= $hold_target || $ss < 1.000} {error "Unsuitable probe endpoint: $hs $ss"}
    lappend records [list $cell $endpoint [get_property LOC $cell] [get_property BEL $cell] [relocate_pin_signature $cell] $hs $ss]
}
relocate_fifo_registers $out $records
puts {HOLD_RELOCATE_PHASE=eco_route}
route_design -eco
verify_fifo_relocation [file join $out relocation_records.list] [file join $out relocation_after_route.tsv]
report_route_status -file [file join $out route_status.rpt]
report_drc -file [file join $out drc.rpt]
report_timing_summary -delay_type min_max -file [file join $out timing.rpt]
set f [open [file join $out changed_path_checks.tsv] w]
puts $f "endpoint\tbefore_hold_ns\tafter_hold_ns\tafter_setup_ns"
set target_miss 0
foreach record $records {
    lassign $record cell endpoint loc bel signature hs ss
    set hp [get_timing_paths -delay_type min -to [get_pins $endpoint] -max_paths 1]
    set sp [get_timing_paths -delay_type max -to [get_pins $endpoint] -max_paths 1]
    set after [get_property SLACK $hp]
    set setup [get_property SLACK $sp]
    puts $f "$endpoint\t$hs\t$after\t$setup"
    if {$after < $hold_target || $after <= $hs || $setup < $setup_target} {set target_miss 1}
}
close $f
release_fifo_relocation [file join $out relocation_records.list]
relocate_leaf_snapshot [file join $out relocation_final_cells.tsv]
write_xdc [file join $out probe_constraints.xdc]
write_checkpoint [file join $out probe_routed.dcp]
if {$target_miss} {error {Relocation probe misses requested endpoint timing margins}}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]]} {error {Probe DRC failure}}
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
