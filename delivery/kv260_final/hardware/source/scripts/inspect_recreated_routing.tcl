# Read-only diagnosis of a retained failed experiment; no routing or export.
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set_param general.maxThreads 8
open_checkpoint $checkpoint
help route_design
help lock_design
report_route_status -file [file join $out route_before.rpt]
report_drc -file [file join $out drc_before.rpt]
source {D:/weather_builds/timing_margin_20261102/hold_recreate_control01/fifo_hold_relocate.tcl}
set f [open {D:/weather_builds/timing_margin_20261102/hold_recreate_control01/relocation_records.list} r]
set records [read $f]; close $f
set f [open [file join $out touched_nets.tsv] w]
puts $f "cell\tpin\tnet\trouting\tdriver\tfanout"
foreach record $records {
    set cell [lindex $record 0]
    foreach pin [get_pins -of_objects [get_cells $cell]] {
        set nets [get_nets -segments -of_objects $pin]
        set leaf [get_nets -top_net_of_hierarchical_group -of_objects $pin]
        puts $f "$cell\t[get_property REF_PIN_NAME $pin]\t$leaf\t[get_property ROUTE_STATUS $leaf]\t[get_pins -leaf -of_objects $nets -filter {DIRECTION == OUT}]\t[llength [get_pins -leaf -of_objects $nets -filter {DIRECTION == IN}]]"
    }
}
close $f
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
