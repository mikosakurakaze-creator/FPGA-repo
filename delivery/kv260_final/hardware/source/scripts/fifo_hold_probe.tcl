if {$argc ni {5 6 7}} {error {Unexpected arguments}}
set out [file normalize [lindex $argv 1]]
set_param general.maxThreads 8
open_checkpoint [file normalize [lindex $argv 0]]
source [file join $out fifo_hold_eco.tcl]
set setup_target [lindex $argv 3]
set hold_target [lindex $argv 4]
set_clock_uncertainty -setup $setup_target [get_clocks]
set_clock_uncertainty -hold $hold_target [get_clocks]
insert_fifo_hold_eco $out 12000 8
set_clock_uncertainty -setup 0 [get_clocks]
set_clock_uncertainty -hold 0 [get_clocks]
route_design -eco
verify_fifo_hold_eco [file join $out hold_eco_records.list] [file join $out hold_eco_final.tsv]
hold_leaf_snapshot [file join $out hold_eco_final_cells.tsv]
set f [open [file join $out hold_eco_records.list] r]
set records [read $f]
close $f
set pins {}
foreach record $records {lappend pins [lindex $record 1]}
report_timing -delay_type min -to [get_pins $pins] -max_paths 8 -nworst 1 -file [file join $out changed_hold_paths.rpt]
report_timing -delay_type max -to [get_pins $pins] -max_paths 8 -nworst 1 -file [file join $out changed_setup_paths.rpt]
report_route_status -file [file join $out route_status.rpt]
report_drc -file [file join $out drc.rpt]
set f [open [file join $out changed_path_checks.tsv] w]
puts $f "endpoint\tbefore_hold_ns\tafter_hold_ns\tafter_setup_ns"
foreach record $records {
    set endpoint [lindex $record 1]
    set before [expr {[lindex $record 7]+$hold_target}]
    set hp [get_timing_paths -delay_type min -to [get_pins $endpoint] -max_paths 1]
    set sp [get_timing_paths -delay_type max -to [get_pins $endpoint] -max_paths 1]
    if {[llength $hp] != 1 || [llength $sp] != 1} {error "Missing changed endpoint timing: $endpoint"}
    set hs [get_property SLACK $hp]
    set ss [get_property SLACK $sp]
    puts $f "$endpoint\t$before\t$hs\t$ss"
    if {$hs < $hold_target || $hs <= $before || $ss < $setup_target} {
        error "Small hold probe misses margin gate at $endpoint: hold=$hs setup=$ss before=$before"
    }
}
close $f
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]]} {
    error {Small hold probe has blocking DRC violations}
}
release_hold_eco_placement [file join $out hold_eco_records.list]
write_xdc [file join $out probe_constraints.xdc]
write_checkpoint [file join $out probe_routed.dcp]
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
