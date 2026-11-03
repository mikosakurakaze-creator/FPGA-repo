# Eight representative RAM->FDRE paths, one per top-level hierarchy where possible.
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set setup_target [lindex $argv 3]
set hold_target [lindex $argv 4]
set_param general.maxThreads 8
open_checkpoint $checkpoint
# This input retains the temporary tighter targets; measure probe deltas at
# the original clock contract. Full implementation restoration is independent.
set_clock_uncertainty -setup 0.0 [get_clocks]
set_clock_uncertainty -hold 0.0 [get_clocks]
source [file join $out fifo_hold_relocate.tcl]
set relocation_net_alias_cache {}
set alias_report [open [file join $out control_net_aliases.tsv] w]
puts $alias_report "cell\tlocal_clock_net\tcanonical_clock_net\tconnected_segments"
set canonical_clock_nets {}
foreach clock {clk_pl_0 clk_pl_1} {
    set source [get_property SOURCE_PINS [get_clocks $clock]]
    if {[llength $source]!=1} {error "Unexpected source pin count for $clock"}
    lappend canonical_clock_nets [relocate_canonical_net [get_pins $source]]
}
if {[llength [lsort -unique $canonical_clock_nets]]!=2} {error {Clock canonicalization must preserve two distinct clocks}}
set candidates [get_cells -hierarchical -filter {REF_NAME == FDRE && NAME =~ *doutb_reg_reg*}]
set checked 0
set aliases {}
foreach cell $candidates {
    set cpin [get_pins $cell/C]
    set local [get_property NAME [get_nets -of_objects $cpin]]
    if {[dict exists $aliases $local]} {continue}
    dict set aliases $local 1
    set canonical [relocate_canonical_net $cpin]
    if {$canonical ni $canonical_clock_nets} {error {Canonical clock not connected to a known clock buffer}}
    puts $alias_report "$cell\t$local\t$canonical\t[llength [get_nets -segments -of_objects $cpin]]"
    incr checked
    if {$checked>=16} {break}
}
close $alias_report
if {$checked<2} {error {Insufficient distinct aliases for clock-equivalence coverage}}
puts "CONTROL_NET_ALIAS_COVERAGE=$checked DISTINCT_CLOCKS=[llength [lsort -unique $canonical_clock_nets]]"
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
# Include the exact endpoint that exhausted both full-design relocation runs.
set stubborn {system_i/curve_ddr_sc/inst/s05_nodes/s05_aw_node/inst/inst_mi_handler/gen_normal_area.inst_fifo_node_payld/gen_xpm_memory_fifo.inst_fifo/gen_mem_rep[0].inst_xpm_memory/xpm_memory_base_inst/gen_rd_b.gen_rd_b_synth_template.gen_rf_narrow_reg.doutb_reg_reg[172]}
set pin [get_pins $stubborn/D]
set hp [get_timing_paths -delay_type min -to $pin -max_paths 1]
if {[llength $pin]!=1 || [llength $hp]!=1 || [get_property SLACK $hp]>=$hold_target} {error {Missing exact stubborn short path}}
set selected [lreplace $selected 7 7 [list $stubborn $stubborn/D [get_property SLACK $hp]]]
# Include the next full-design endpoint and explicitly exercise an empty query.
set next_cell {system_i/cnn_model_sc/inst/s00_nodes/s00_ar_node/inst/inst_mi_handler/gen_normal_area.inst_fifo_node_payld/gen_xpm_memory_fifo.inst_fifo/gen_mem_rep[0].inst_xpm_memory/xpm_memory_base_inst/gen_rd_b.gen_rd_b_synth_template.gen_rf_narrow_reg.doutb_reg_reg[124]}
set hp [get_timing_paths -delay_type min -to [get_pins $next_cell/D] -max_paths 1]
if {[llength $hp]!=1 || [get_property SLACK $hp]>=$hold_target} {error {Missing next full-design endpoint}}
set selected [lreplace $selected 6 6 [list $next_cell $next_cell/D [get_property SLACK $hp]]]
set crowded {system_i/cnn_data_sc/inst/s02_nodes/s02_r_node/inst/inst_mi_handler/gen_normal_area.inst_fifo_node_payld/gen_xpm_memory_fifo.inst_fifo/gen_mem_rep[0].inst_xpm_memory/xpm_memory_base_inst/gen_rd_b.gen_rd_b_synth_template.gen_rf_narrow_reg.doutb_reg_reg[50]}
set hp [get_timing_paths -delay_type min -to [get_pins $crowded/D] -max_paths 1]
if {[llength $hp]!=1 || [get_property SLACK $hp]>=$hold_target} {error {Missing crowded-control endpoint}}
set selected [lreplace $selected 5 5 [list $crowded $crowded/D [get_property SLACK $hp]]]
# Check the prefilter rejects a deliberately incompatible reset signature.
set relocation_control_cache {}
set signature [relocate_control_signature $crowded]
set native_site [get_property LOC [get_cells $crowded]]
set native_slot [lindex [split [get_property BEL [get_cells $crowded]] .] end]
if {![relocate_control_allowed $native_site $native_slot $signature]} {error {Native self control signature must be compatible}}
set invalid [lreplace $signature 2 2 __negative_reset_signature__]
if {[relocate_control_allowed $native_site $native_slot $invalid]} {error {Control filter accepts incompatible reset}}
puts {CONTROL_FILTER_NEGATIVE=PASS}
set free {}
set regions {}
set fullsite {}
foreach region [get_clock_regions] {
    foreach site [get_sites -of_objects $region -filter {SITE_TYPE == SLICEL || SITE_TYPE == SLICEM}] {
        if {![llength [get_bels -quiet $site/*FF* -filter {IS_USED == 0 && IS_RESERVED == 0 && PROHIBIT == 0}]]} {
            set fullsite $site
            break
        }
    }
    if {$fullsite ne {}} {break}
}
if {$fullsite eq {} || ![regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $fullsite -> x y]} {error {Missing fully occupied site for empty-query coverage}}
relocate_query_site "$x,$y" free regions
if {[dict exists $free "$x,$y"] || ![dict exists $regions "$x,$y"]} {error {Empty FF site must be cached without slots}}
puts "EMPTY_FF_QUERY=PASS SITE=$fullsite"
set records {}
foreach selected_path $selected {
    lassign $selected_path cell endpoint hs
    set cell [get_cells $cell]
    set ss [get_property SLACK [get_timing_paths -delay_type max -to [get_pins $endpoint] -max_paths 1]]
    if {$ss<$setup_target} {error {Probe FIFO endpoint lacks requested setup budget}}
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
route_design -preserve
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
