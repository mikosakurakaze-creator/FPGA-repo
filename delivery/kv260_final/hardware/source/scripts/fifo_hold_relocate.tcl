# Physical-only relocation of existing RAM->FDRE FIFO output registers.
proc relocate_pin_signature {cell} {
    set signature {}
    foreach pin [lsort [get_pins -of_objects [get_cells $cell]]] {
        lappend signature [list [get_property REF_PIN_NAME $pin] [lsort [get_property NAME [get_nets -quiet -of_objects $pin]]]]
    }
    return $signature
}
proc relocate_leaf_snapshot {path} {
    set cells [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]
    set names [get_property NAME $cells]
    set refs [get_property REF_NAME $cells]
    set f [open $path w]
    foreach name $names ref $refs {puts $f "$name\t$ref"}
    close $f
}
proc verify_fifo_relocation {manifest report} {
    set f [open $manifest r]; set records [read $f]; close $f
    set f [open $report w]
    puts $f "cell\tendpoint\told_site\tnew_site\tconnections"
    foreach record $records {
        lassign $record cell endpoint loc bel signature hs ss target
        if {[get_property REF_NAME [get_cells $cell]] ne {FDRE} || [relocate_pin_signature $cell] ne $signature} {
            error "Relocated register type or connections changed: $cell"
        }
        set newloc [get_property LOC [get_cells $cell]]
        if {$newloc eq $loc || $newloc ne [lindex [split $target /] 0]} {error "Register placement changed: $cell"}
        puts $f "$cell\t$endpoint\t$loc\t$newloc\tPASS"
    }
    puts $f "VERIFIED_RELOCATED_REGISTERS=[llength $records]"
    close $f
    return [llength $records]
}
proc relocate_fifo_registers {out candidates} {
    if {![llength $candidates] || [llength $candidates] > 12000} {error {Unexpected relocation candidate count}}
    relocate_leaf_snapshot [file join $out relocation_before_cells.tsv]
    set occupied [dict create]
    # LUT logic in a SLICEL may stay; only sites with no existing FF/latch
    # are eligible, so no pre-existing clock/control set is disturbed.
    foreach loc [get_property LOC [get_cells -hierarchical -filter {IS_PRIMITIVE == 1 && (REF_NAME =~ FD* || REF_NAME =~ LD*)}]] {
        if {$loc ne {}} {dict set occupied $loc 1}
    }
    set free [dict create]
    set free_slots 0
    foreach site [get_sites -quiet -filter {SITE_TYPE == SLICEL}] {
        if {[dict exists $occupied $site]} {continue}
        if {![regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $site -> x y]} {continue}
        # Require an entirely unused LUT pair: a LUT6_2 may occupy its
        # shared input resources without marking the separate 5LUT used.
        set slots {}
        foreach letter {A B C D E F G H} {
            if {[get_property IS_USED [get_bels $site/${letter}5LUT]] ||
                [get_property IS_USED [get_bels $site/${letter}6LUT]]} {continue}
            lappend slots ${letter}FF ${letter}FF2
        }
        if {![llength $slots]} {continue}
        incr free_slots [llength $slots]
        dict set free "$x,$y" [list $site $slots]
    }
    puts "HOLD_RELOCATION_SLICEL_WITHOUT_FF=[dict size $free] AVAILABLE_FF_SLOTS=$free_slots"
    set pools [dict create]
    set relocated {}
    set f [open [file join $out relocation_selection.txt] w]
    puts $f "SELECTED=[llength $candidates]"
    close $f
    foreach record $candidates {
        lassign $record cell endpoint loc bel signature hs ss
        foreach property {IS_LOC_FIXED IS_BEL_FIXED DONT_TOUCH} {
            if {[get_property $property [get_cells $cell]] in {1 true TRUE}} {error "Refusing to move protected register: $cell $property"}
        }
        regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $loc -> x y
        set source_region [get_clock_regions -of_objects [get_sites $loc]]
        set key [list $source_region]
        foreach pin {C CE R} {lappend key [get_property NAME [get_nets -of_objects [get_pins $cell/$pin]]]}
        set target {}
        set pool [expr {[dict exists $pools $key] ? [dict get $pools $key] : {}}]
        for {set i 0} {$i < [llength $pool]} {incr i} {
            lassign [lindex $pool $i] site slots
            regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $site -> xx yy
            if {![llength $slots] || abs($xx-$x)+abs($yy-$y)>20} {continue}
            set target $site
            set slot [lindex $slots 0]
            lset pool $i [list $site [lrange $slots 1 end]]
            break
        }
        if {$target eq {}} {
            for {set radius 1} {$radius <= 40 && $target eq {}} {incr radius} {
                for {set dx -$radius} {$dx <= $radius && $target eq {}} {incr dx} {
                    set dy [expr {$radius-abs($dx)}]
                    foreach yy [lsort -unique [list [expr {$y-$dy}] [expr {$y+$dy}]]] {
                        set coord "[expr {$x+$dx}],$yy"
                        if {![dict exists $free $coord]} {continue}
                        lassign [dict get $free $coord] site slots
                        if {[get_clock_regions -of_objects [get_sites $site]] ne $source_region} {continue}
                        set target $site
                        set slot [lindex $slots 0]
                        dict unset free $coord
                        lappend pool [list $site [lrange $slots 1 end]]
                        break
                    }
                }
            }
        }
        if {$target eq {}} {error "No empty local SLICEL found for $cell"}
        dict set pools $key $pool
        set target_bel $target/$slot
        if {[get_property IS_USED [get_bels $target_bel]]} {error "Selected FF BEL is already used: $target_bel"}
        place_cell [list $cell $target_bel]
        if {[relocate_pin_signature $cell] ne $signature} {error {Register connectivity changed}}
        lappend relocated [concat $record [list $target_bel]]
        if {[llength $candidates] <= 8 || [llength $relocated]%250==0} {
            puts "HOLD_RELOCATED=[llength $relocated] $loc/$bel->$target_bel"
        }
    }
    set f [open [file join $out relocation_records.list] w]
    puts $f $relocated
    close $f
    verify_fifo_relocation [file join $out relocation_records.list] [file join $out relocation_before_route.tsv]
    relocate_leaf_snapshot [file join $out relocation_moved_cells.tsv]
    return [llength $relocated]
}
proc release_fifo_relocation {manifest} {
    set f [open $manifest r]; set records [read $f]; close $f
    foreach record $records {
        set cell [get_cells [lindex $record 0]]
        set_property IS_LOC_FIXED false $cell
        set_property IS_BEL_FIXED false $cell
    }
}
