# Replace only six frozen modules in the CURRENT routed design, then re-use it.
if {$argc != 7} {error {Use isolated runner}}
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set stage [lindex $argv 2]
set setup_margin [lindex $argv 3]
set hold_margin [lindex $argv 4]
set_param general.maxThreads 8
set_param logicopt.enableDSPCascadeFixing false
if {$stage eq {help}} {
    foreach command {update_design read_checkpoint place_design route_design} {puts [help $command]}
    puts {TIMING_MARGIN_HELP_PASS}
    exit
}
if {$stage ne {optimize}} {error {Expected targeted optimize stage}}
set prepared D:/weather_builds/timing_margin_20261102/fifo_targeted03_nodes
set synthesized D:/weather_builds/timing_margin_20261102/fifo_targeted03_synth03
file copy [file join $prepared physical_inputs01.json] [file join $out physical_inputs.json]
file copy [file join $prepared verify_targeted_node_inputs.py] [file join $out verify_targeted_node_inputs.py]
puts [exec {C:/Users/wzh16/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe} -E -B \
    [file join $out verify_targeted_node_inputs.py] verify --manifest [file join $out physical_inputs.json]]
file copy [file join $prepared node_specs.tcl] [file join $out node_specs.tcl]
source [file join $out node_specs.tcl]
proc selected_cell {name specs} {
    foreach row $specs {
        set key [lindex $row 0]
        lassign [split $key /] sc node
        set prefix "system_i/$sc/inst/[lindex [split $node _] 0]_nodes/$node/"
        if {[string first $prefix $name]==0} {return 1}
    }
    return 0
}
proc outside_signature {specs} {
    set cells [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]
    set result {}
    foreach name [get_property NAME $cells] ref [get_property REF_NAME $cells] \
            loc [get_property LOC $cells] bel [get_property BEL $cells] {
        if {![selected_cell $name $specs]} {lappend result [list $name $ref $loc $bel]}
    }
    return [lsort $result]
}
proc boundary {cell} {
    set rows {}
    foreach pin [get_pins -of_objects [get_cells $cell]] {
        # Generated wrappers retain unused pins. Preserve their disconnected
        # state in the contract instead of querying a property on an empty set.
        set nets [get_nets -quiet -of_objects $pin]
        set names {}
        if {[llength $nets]} {set names [lsort [get_property NAME $nets]]}
        lappend rows [list [get_property REF_PIN_NAME $pin] [get_property DIRECTION $pin] \
            $names]
    }
    return [lsort $rows]
}
open_checkpoint $checkpoint
if {[lsort [get_clocks]] ne {clk_pl_0 clk_pl_1} ||
    [get_property PERIOD [get_clocks clk_pl_0]] != 10.0 ||
    [get_property PERIOD [get_clocks clk_pl_1]] != 5.0} {error {Unexpected original clocks}}
write_xdc [file join $out baseline_constraints.xdc]
report_clocks -file [file join $out baseline_clocks.rpt]
set outside [outside_signature $node_specs]
set f [open [file join $out original_outside_placement.txt] w];puts $f $outside;close $f
set f [open [file join $out replacement_boundary.txt] w]
foreach row $node_specs {
    lassign $row key module source method width
    lassign [split $key /] sc node
    set cell "system_i/$sc/inst/[lindex [split $node _] 0]_nodes/$node"
    # Joint synthesis prefixes generated wrapper references with the owning BD
    # IP instance; standalone source/DCP top names retain their original name.
    set expected "system_${sc}_0_${module}"
    if {[llength [get_cells -quiet $cell]]!=1 || [get_property REF_NAME [get_cells $cell]] ne $expected} {error "Wrong parent instance: $key"}
    set before [boundary $cell]
    set dcp [file join $synthesized [string map {/ __} $key].dcp]
    file copy $dcp [file join $out [file tail $dcp]]
    puts "TARGETED_NODE_REPLACE_START=$key"
    update_design -cell $cell -black_box
    read_checkpoint -cell $cell [file join $out [file tail $dcp]]
    set after [boundary $cell]
    puts $f "NODE=$key\nBEFORE=$before\nAFTER=$after";flush $f
    if {$before ne $after} {error "Replacement changed boundary nets/pins: $key"}
    puts "TARGETED_NODE_REPLACE_PASS=$key"
}
close $f
if {$outside ne [outside_signature $node_specs]} {error {Untargeted primitives or placement changed during replacement}}
set f [open [file join $out outside_replacement_proof.txt] w]
puts $f "UNCHANGED_OUTSIDE_PRIMITIVES=[llength $outside]";close $f
if {[lsort [get_clocks]] ne {clk_pl_0 clk_pl_1}} {error {Replacement introduced clock constraints}}
write_checkpoint [file join $out replaced_candidate.dcp]
read_checkpoint -incremental $checkpoint
set_clock_uncertainty -setup $setup_margin [get_clocks]
set_clock_uncertainty -hold $hold_margin [get_clocks]
puts {TARGETED_PHASE=place_only_new_logic}
place_design -directive Explore
write_checkpoint [file join $out placed_candidate.dcp]
puts {TARGETED_PHASE=route_preserve}
route_design -preserve
report_timing_summary -delay_type min_max -file [file join $out tightened_final.rpt]
write_checkpoint [file join $out tightened_final.dcp]
set_clock_uncertainty -setup 0.0 [get_clocks]
set_clock_uncertainty -hold 0.0 [get_clocks]
write_xdc [file join $out restored_constraints.xdc]
report_clocks -file [file join $out restored_clocks.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $out routed_timing.rpt]
report_timing -delay_type max -max_paths 40 -nworst 1 -path_type full_clock_expanded -file [file join $out final_setup_paths.rpt]
report_timing -delay_type min -max_paths 40 -nworst 1 -path_type full_clock_expanded -file [file join $out final_hold_paths.rpt]
report_utilization -file [file join $out routed_utilization.rpt]
report_utilization -hierarchical -file [file join $out routed_hierarchical.rpt]
report_route_status -file [file join $out route_status.rpt]
report_drc -file [file join $out routed_drc.rpt]
report_cdc -details -file [file join $out routed_cdc.rpt]
report_bus_skew -file [file join $out routed_bus_skew.rpt]
check_timing -verbose -file [file join $out routed_clock_check.rpt]
set f [open [file join $out final_path_summary.txt] w]
foreach type {max min} {
    foreach path [get_timing_paths -delay_type $type -max_paths 40 -nworst 1] {
        puts $f "$type SLACK=[get_property SLACK $path] START=[get_property STARTPOINT_PIN $path] END=[get_property ENDPOINT_PIN $path]"
    }
}
close $f
write_checkpoint [file join $out optimized_routed.dcp]
if {[llength [get_timing_paths -delay_type max -slack_lesser_than 0 -max_paths 1]] ||
    [llength [get_timing_paths -delay_type min -slack_lesser_than 0 -max_paths 1]]} {error {Original timing constraints not met}}
close_design
puts {TIMING_MARGIN_OPTIMIZE_PASS}
exit
