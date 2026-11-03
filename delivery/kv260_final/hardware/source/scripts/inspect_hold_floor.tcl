# Read-only characterization of the currently routed minimum-delay paths.
if {$argc ni {5 6 7}} {error {Unexpected arguments}}
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[lindex $argv 2] ne {inspect}} {error {Read-only inspector requires inspect stage}}
set_param general.maxThreads 8
open_checkpoint $checkpoint
set f [open [file join $out hold_floor.tsv] w]
puts $f "slack\tstart\tend\tsource_ref\tdest_ref\tsource_loc\tdest_loc\tdest_bel\tlogic_levels\tdata_delay\tsetup_slack"
set paths [get_timing_paths -delay_type min -slack_lesser_than 0.150 -max_paths 50000 -nworst 1]
set groups [dict create]
set inspected 0
foreach path $paths {
    set start [get_pins [get_property STARTPOINT_PIN $path]]
    set end [get_pins [get_property ENDPOINT_PIN $path]]
    set sc [get_cells -of_objects $start]
    set dc [get_cells -of_objects $end]
    set sr [get_property REF_NAME $sc]
    set dr [get_property REF_NAME $dc]
    set sl [get_property LOC $sc]
    set dl [get_property LOC $dc]
    set key "$sr->$dr/[expr {$sl eq $dl ? {same_site} : {different_sites}}]"
    dict incr groups $key
    # Only query per-endpoint setup for the first representatives; thousands
    # of separate timing traversals are unnecessary for diagnosis.
    set setup {}
    if {$inspected < 12} {
        set sp [get_timing_paths -delay_type max -to $end -max_paths 1]
        if {[llength $sp]} {set setup [get_property SLACK $sp]}
    }
    puts $f [join [list [get_property SLACK $path] $start $end $sr $dr $sl $dl \
        [get_property BEL $dc] [get_property LOGIC_LEVELS $path] [get_property DATAPATH_DELAY $path] $setup] "\t"]
    incr inspected
}
close $f
set f [open [file join $out hold_floor_summary.txt] w]
puts $f "RETURNED_PATHS_BELOW_0_150=[llength $paths]\nQUERY_LIMIT=50000\nLIMIT_REACHED=[expr {[llength $paths] == 50000}]"
dict for {key value} $groups {puts $f "$key=$value"}
close $f
report_timing -delay_type min -max_paths 20 -nworst 1 -path_type full_clock_expanded -file [file join $out hold_paths.rpt]
report_timing_summary -delay_type min_max -file [file join $out timing.rpt]
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
