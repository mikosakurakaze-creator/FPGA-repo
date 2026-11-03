# Read-only comparison of rebuilt parent boundaries and standalone OOC ports.
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set_param general.maxThreads 4
source D:/weather_builds/timing_margin_20261102/fifo_targeted03_nodes/node_specs.tcl
foreach command {read_checkpoint rename_port rename_cell} {
    if {[llength [info commands $command]]} {puts [help $command]}
}
open_checkpoint $checkpoint
set f [open [file join $out parent_pins.tsv] w]
puts $f "key\tname\tref_pin\tdirection\tnets"
foreach row $node_specs {
    lassign $row key module file method width
    lassign [split $key /] sc node
    set cell "system_i/$sc/inst/[lindex [split $node _] 0]_nodes/$node"
    report_property [get_cells $cell] -file [file join $out [string map {/ __} $key]_cell.txt]
    foreach pin [get_pins -of_objects [get_cells $cell]] {
        set nets [get_nets -quiet -of_objects $pin]
        set names {};if {[llength $nets]} {set names [get_property NAME $nets]}
        puts $f "$key\t[get_property NAME $pin]\t[get_property REF_PIN_NAME $pin]\t[get_property DIRECTION $pin]\t$names"
    }
}
close $f
close_design
open_checkpoint D:/weather_builds/timing_margin_20261102/fifo_targeted03_synth03/bilinear_ddr_sc__m00_r_node.dcp
set f [open [file join $out standalone_ports.tsv] w]
puts $f "name\tdirection"
foreach port [get_ports] {puts $f "[get_property NAME $port]\t[get_property DIRECTION $port]"}
close $f
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
