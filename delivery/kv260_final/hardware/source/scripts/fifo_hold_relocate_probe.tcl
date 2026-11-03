# Small physical-only probe: move eight existing FIFO output registers.
# Netlist, arithmetic, reset/enable connections and cycle behavior are unchanged.
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set selection {D:/weather_builds/timing_margin_20261102/hold_probe03/hold_eco_before_route.tsv}
set_param general.maxThreads 8
open_checkpoint $checkpoint
proc pin_signature {cell} {
    set signature {}
    foreach pin [lsort [get_pins -of_objects $cell]] {
        lappend signature [list [get_property REF_PIN_NAME $pin] [lsort [get_property NAME [get_nets -quiet -of_objects $pin]]]]
    }
    return $signature
}
proc leaf_snapshot {path} {
    set cells [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]
    set names [get_property NAME $cells]
    set refs [get_property REF_NAME $cells]
    set f [open $path w]
    foreach name $names ref $refs {puts $f "$name\t$ref"}
    close $f
}
set f [open $selection r]
set lines [split [read $f] \n]
close $f
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
    if {$hs >= 0.100 || $ss < 1.000} {error "Unsuitable probe endpoint: $hs $ss"}
    lappend records [list $cell $endpoint [get_property LOC $cell] [get_property BEL $cell] [pin_signature $cell] $hs $ss]
}
leaf_snapshot [file join $out before_cells.tsv]
puts {HOLD_RELOCATE_PHASE=move_eight_registers}
set relocated {}
foreach record $records {
    lassign $record cell endpoint loc bel signature hs ss
    if {[get_property IS_LOC_FIXED $cell] || [get_property IS_BEL_FIXED $cell] || [get_property DONT_TOUCH $cell]} {
        error "Refusing to move protected register: $cell"
    }
    regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $loc -> x y
    set target {}
    for {set radius 1} {$radius <= 30 && $target eq {}} {incr radius} {
        for {set dx -$radius} {$dx <= $radius && $target eq {}} {incr dx} {
            set dy [expr {$radius-abs($dx)}]
            foreach yy [lsort -unique [list [expr {$y-$dy}] [expr {$y+$dy}]]] {
                if {$yy < 0 || $yy/60 != $y/60} {continue}
                set site [get_sites -quiet SLICE_X[expr {$x+$dx}]Y$yy]
                if {[llength $site] != 1 || [get_property SITE_TYPE $site] ne {SLICEL}} {continue}
                if {[llength [get_cells -quiet -of_objects $site]]} {continue}
                set target $site
                break
            }
        }
    }
    if {$target eq {}} {error "No empty local SLICEL found for $cell"}
    # Move the whole register to an ordinary logic slice, so the RAM->D
    # connection no longer uses its dedicated same-site bypass.
    place_cell [list $cell $target/AFF]
    if {[pin_signature $cell] ne $signature} {error {Register connectivity changed}}
    lappend relocated [concat $record [list $target/AFF]]
    puts "HOLD_RELOCATED=$loc/$bel->$target/AFF"
}
set f [open [file join $out relocation_records.list] w]
puts $f $relocated
close $f
puts {HOLD_RELOCATE_PHASE=eco_route}
route_design -eco
report_route_status -file [file join $out route_status.rpt]
report_drc -file [file join $out drc.rpt]
report_timing_summary -delay_type min_max -file [file join $out timing.rpt]
set f [open [file join $out changed_path_checks.tsv] w]
puts $f "endpoint\tbefore_hold_ns\tafter_hold_ns\tafter_setup_ns"
set target_miss 0
foreach record $relocated {
    lassign $record cell endpoint loc bel signature hs ss target
    if {[pin_signature $cell] ne $signature} {error {Register connectivity changed after route}}
    set hp [get_timing_paths -delay_type min -to [get_pins $endpoint] -max_paths 1]
    set sp [get_timing_paths -delay_type max -to [get_pins $endpoint] -max_paths 1]
    set after [get_property SLACK $hp]
    set setup [get_property SLACK $sp]
    puts $f "$endpoint\t$hs\t$after\t$setup"
    if {$after < 0.100 || $after <= $hs || $setup < 0.300} {set target_miss 1}
    set_property IS_LOC_FIXED false [get_cells $cell]
    set_property IS_BEL_FIXED false [get_cells $cell]
}
close $f
leaf_snapshot [file join $out after_cells.tsv]
write_checkpoint [file join $out probe_routed.dcp]
if {$target_miss} {error {Relocation probe misses requested endpoint timing margins}}
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == {Critical Warning}}]]} {error {Probe DRC failure}}
close_design
puts {TIMING_MARGIN_INSPECT_PASS}
exit
