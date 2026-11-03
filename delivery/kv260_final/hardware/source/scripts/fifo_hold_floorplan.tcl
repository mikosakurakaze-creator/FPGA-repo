# Keep selected FIFO output FFs out of SLICEM RAM bypass connections.
# The native placer chooses legal FF/control-set packing within SLICEL sites.
proc floorplan_pin_signature {cell} {
    set result {}
    foreach pin [lsort [get_pins -of_objects [get_cells $cell]]] {
        lappend result [list [get_property REF_PIN_NAME $pin] [lsort [get_property NAME [get_nets -quiet -of_objects $pin]]]]
    }
    return $result
}
proc prepare_fifo_floorplan {out} {
    set f [open [file join $out fifo_floorplan_targets.list] r]; set names [read $f]; close $f
    if {![llength $names] || [llength $names]>12000} {error {Unexpected FIFO floorplan target count}}
    set cells [get_cells $names]
    if {[llength $cells] != [llength $names]} {error {FIFO target names do not match the new optimized netlist}}
    set records {}
    foreach cell $cells {
        if {[get_property REF_NAME $cell] ne {FDRE}} {error {Unexpected FIFO target primitive}}
        foreach property {DONT_TOUCH IS_LOC_FIXED IS_BEL_FIXED} {
            if {[get_property $property $cell] in {1 true TRUE}} {error "Refusing protected FIFO cell: $cell $property"}
        }
        if {[llength [get_pblocks -quiet -of_objects $cell]]} {error {FIFO cell already belongs to a floorplan}}
        lappend records [list $cell [floorplan_pin_signature $cell]]
    }
    set f [open [file join $out fifo_floorplan_records.list] w]; puts $f $records; close $f
    set columns [dict create]
    foreach site [get_sites -filter {SITE_TYPE == SLICEL}] {
        if {![regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $site -> x y]} {error {Unexpected SLICEL coordinate}}
        dict lappend columns $x $y
    }
    set ranges {}
    foreach x [lsort -integer [dict keys $columns]] {
        set begin -1
        set previous -1
        foreach y [lsort -integer -unique [dict get $columns $x]] {
            if {$begin < 0} {set begin $y; set previous $y; continue}
            if {$y != $previous+1} {
                lappend ranges SLICE_X${x}Y${begin}:SLICE_X${x}Y${previous}
                set begin $y
            }
            set previous $y
        }
        lappend ranges SLICE_X${x}Y${begin}:SLICE_X${x}Y${previous}
    }
    set name hold_fifo_logic_only
    if {[llength [get_pblocks -quiet $name]]} {error {Refusing to overwrite existing Pblock}}
    set pb [create_pblock $name]
    resize_pblock $pb -add $ranges
    set_property IS_SOFT false $pb
    add_cells_to_pblock $pb $cells -clear_locs
    set actual [get_sites -of_objects $pb]
    foreach site $actual {
        if {[get_property SITE_TYPE $site] ne {SLICEL}} {error {FIFO floorplan accidentally includes RAM-capable slices}}
    }
    set f [open [file join $out fifo_floorplan_scope.txt] w]
    puts $f "TARGETS=[llength $cells]\nALLOWED_SLICEL=[llength $actual]\nRANGES=[llength $ranges]\nIS_SOFT=[get_property IS_SOFT $pb]\nNEW_PIPELINE_CYCLES=0"
    close $f
    puts "FIFO_FLOORPLAN_TARGETS=[llength $cells] ALLOWED_SLICEL=[llength $actual]"
}
proc verify_fifo_floorplan {manifest report} {
    set f [open $manifest r]; set records [read $f]; close $f
    set f [open $report w]
    puts $f "cell\tsite\ttype\tconnections"
    foreach record $records {
        lassign $record name signature
        set cell [get_cells $name]
        if {[llength $cell]!=1 || [get_property REF_NAME $cell] ne {FDRE} || [floorplan_pin_signature $name] ne $signature} {
            error "FIFO primitive or connection changed: $name"
        }
        set site [get_property LOC $cell]
        if {$site eq {} || [get_property SITE_TYPE [get_sites $site]] ne {SLICEL}} {error "FIFO FF is not in a SLICEL: $name $site"}
        puts $f "$name\t$site\tFDRE\tPASS"
    }
    puts $f "VERIFIED_FLOORPLAN_REGISTERS=[llength $records]"
    close $f
}
proc release_fifo_floorplan {} {
    delete_pblocks [get_pblocks hold_fifo_logic_only]
    if {[llength [get_pblocks -quiet hold_fifo_logic_only]]} {error {Temporary FIFO Pblock remains}}
}
