# Eight representative RAM->FDRE paths, one per top-level hierarchy where possible.
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set setup_target [lindex $argv 3]
set hold_target [lindex $argv 4]
set_param general.maxThreads 8
open_checkpoint $checkpoint
source [file join $out fifo_hold_relocate.tcl]
set paths [get_timing_paths -delay_type min -slack_lesser_than $hold_target -max_paths 30000 -nworst 1]
if {[llength $paths]>=30000} {error {Probe path query coverage cap reached}}
set groups [dict create]
foreach path $paths {
    set endpoint [get_property ENDPOINT_PIN $path]
    set pin [get_pins $endpoint]
    set cell [get_cells -of_objects $pin]
    set source [get_cells -of_objects [get_pins [get_property STARTPOINT_PIN $path]]]
    if {[get_property REF_NAME $cell] ne {FDRE} || [get_property REF_NAME $source] ni {RAMD32 RAMD64E} ||
        [get_property REF_PIN_NAME $pin] ne {D} || [get_property LOC $cell] ne [get_property LOC $source]} {continue}
    set group [lindex [split $cell /] 1]
    dict lappend groups $group [list $cell $endpoint [get_property SLACK $path]]
}
set selected {}
for {set round 0} {[llength $selected]<8 && $round<8} {incr round} {
    foreach group [lsort [dict keys $groups]] {
        set pool [dict get $groups $group]
        if {$round<[llength $pool] && [llength $selected]<8} {lappend selected [lindex $pool $round]}
    }
}
if {[llength $selected]!=8} {error {Insufficient representative probe paths}}
set records {}
foreach selected_path $selected {
    lassign $selected_path cell endpoint hs
    set cell [get_cells $cell]
    set ss [get_property SLACK [get_timing_paths -delay_type max -to [get_pins $endpoint] -max_paths 1]]
    if {$ss<1.000} {error {Probe FIFO endpoint lacks setup budget}}
    lappend records [list $cell $endpoint [get_property LOC $cell] [get_property BEL $cell] [relocate_pin_signature $cell] $hs $ss]
}
# Explicit negative control: an occupied FF BEL must be rejected and logged.
lassign [lindex $records 0] first_cell first_endpoint old_loc old_bel first_signature
set occupied [lindex [get_cells -hierarchical -filter {REF_NAME == FDRE && IS_LOC_FIXED == 0}] end]
if {$occupied eq $first_cell} {error {Negative control requires a different occupied FF}}
set target "[get_property LOC $occupied]/[lindex [split [get_property BEL $occupied] .] end]"
puts "PLACEMENT_TRIAL_BEGIN\t$first_cell\t$target"
set rejected [catch {place_cell [list $first_cell $target]} reason]
if {$rejected} {puts $reason}
puts "PLACEMENT_TRIAL_END\t$rejected"
set diagnostics $reason
set f [open [file join $out occupied_bel_negative_control.txt] w]
puts $f "RETURN_CODE=$rejected\nREASON=$reason\nTOOL_MESSAGES=$diagnostics"
close $f
if {!$rejected} {error {Negative control did not reject the occupied BEL as expected}}
if {[get_property LOC [get_cells $first_cell]] ne $old_loc || [get_property BEL [get_cells $first_cell]] ne $old_bel} {
    place_cell [list $first_cell $old_loc/[lindex [split $old_bel .] end]]
}
if {[relocate_pin_signature $first_cell] ne $first_signature} {error {Negative control changed logical connectivity}}
puts {OCCUPIED_BEL_NEGATIVE_CONTROL=PASS_FULL_MESSAGE_RETAINED}
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
    set after [get_property SLACK [get_timing_paths -delay_type min -to [get_pins $endpoint] -max_paths 1]]
    set setup [get_property SLACK [get_timing_paths -delay_type max -to [get_pins $endpoint] -max_paths 1]]
    puts $f "$endpoint\t$hs\t$after\t$setup"
    if {$after<$hold_target || $after<=$hs || $setup<$setup_target} {set target_miss 1}
}
close $f
release_fifo_relocation [file join $out relocation_records.list]
relocate_leaf_snapshot [file join $out relocation_final_cells.tsv]
write_xdc [file join $out probe_constraints.xdc]
write_checkpoint [file join $out probe_routed.dcp]
if {$target_miss} {error {Representative relocation probe misses margins}}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]]} {error {Probe DRC failure}}
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
