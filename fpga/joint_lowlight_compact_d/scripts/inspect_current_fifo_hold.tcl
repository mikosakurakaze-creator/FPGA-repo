# Read-only selection from the CURRENT routed candidate, never the old baseline.
if {$argc != 7} {error {Use the isolated diagnostic runner}}
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set_param general.maxThreads 4
open_checkpoint $checkpoint
if {[get_property PERIOD [get_clocks clk_pl_0]] != 10.0 ||
    [get_property PERIOD [get_clocks clk_pl_1]] != 5.0} {error {Unexpected clocks}}
set cutoff 0.100
set paths [get_timing_paths -delay_type min -from [get_clocks clk_pl_0] -to [get_clocks clk_pl_0] \
    -slack_lesser_than $cutoff -max_paths 20000 -nworst 1]
if {[llength $paths] >= 20000} {error {Selection was truncated}}
set groups [dict create]
set f [open [file join $out current_hold_targets.tsv] w]
puts $f "slack\tstart\tend\tnode\tsource_ref\tdest_ref\tsource_loc\tdest_loc\tdata_delay"
foreach path $paths {
    set start [get_property STARTPOINT_PIN $path]
    set end [get_property ENDPOINT_PIN $path]
    set a [get_cells -of_objects [get_pins $start]]
    set b [get_cells -of_objects [get_pins $end]]
    set node OTHER
    if {[regexp {^system_i/([^/]+)/inst/[sm][0-9]+_nodes/([^/]+)/} $start -> sc channel]} {
        set node "$sc/$channel"
    }
    dict incr groups $node
    puts $f "[get_property SLACK $path]\t$start\t$end\t$node\t[get_property REF_NAME $a]\t[get_property REF_NAME $b]\t[get_property LOC $a]\t[get_property LOC $b]\t[get_property DATAPATH_DELAY $path]"
}
close $f
set f [open [file join $out current_hold_groups.tsv] w]
puts $f "node\tendpoints"
foreach node [lsort [dict keys $groups]] {puts $f "$node\t[dict get $groups $node]"}
close $f
report_timing_summary -delay_type min_max -file [file join $out current_timing.rpt]
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
