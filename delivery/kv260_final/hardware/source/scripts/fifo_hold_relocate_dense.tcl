# Physical relocation with conservative reuse of homogeneous FDRE sites.
# No primitive, data/control net, or pipeline latency is changed.
proc relocate_pin_signature {cell} {
    set signature {}
    foreach pin [lsort [get_pins -of_objects [get_cells $cell]]] {
        lappend signature [list [get_property REF_PIN_NAME $pin] [lsort [get_property NAME [get_nets -quiet -of_objects $pin]]]]
    }
    return $signature
}
proc relocate_leaf_snapshot {path} {
    set cells [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]
    set f [open $path w]
    foreach name [get_property NAME $cells] ref [get_property REF_NAME $cells] {puts $f "$name\t$ref"}
    close $f
}
proc relocate_controls {cell} {
    set sig {}
    foreach pin {C CE R} {lappend sig [get_property NAME [get_nets -of_objects [get_pins $cell/$pin]]]}
    return $sig
}
proc verify_fifo_relocation {manifest report} {
    set f [open $manifest r]; set records [read $f]; close $f
    set f [open $report w]
    puts $f "cell\tendpoint\told_site\tnew_site\tconnections"
    foreach record $records {
        lassign $record cell endpoint loc bel signature hs ss target
        if {[get_property REF_NAME [get_cells $cell]] ne {FDRE} || [relocate_pin_signature $cell] ne $signature} {
            error "Relocated primitive or pin connections changed: $cell"
        }
        set newloc [get_property LOC [get_cells $cell]]
        # BEL is reported as SLICEL.AFF / SLICEM.AFF, whereas place_cell
        # accepts SLICE_XxYy/AFF. Compare both the site type and FF slot.
        set expected_bel "[get_property SITE_TYPE [get_sites $newloc]].[lindex [split $target /] 1]"
        if {$newloc eq $loc || $newloc ne [lindex [split $target /] 0] ||
            [get_property BEL [get_cells $cell]] ne $expected_bel} {
            error "Register placement differs from relocation manifest: $cell"
        }
        puts $f "$cell\t$endpoint\t$loc\t$newloc\tPASS"
    }
    puts $f "VERIFIED_RELOCATED_REGISTERS=[llength $records]"
    close $f
    return [llength $records]
}
proc relocate_fifo_registers {out candidates} {
    if {![llength $candidates] || [llength $candidates] > 12000} {error {Unexpected relocation count}}
    relocate_leaf_snapshot [file join $out relocation_before_cells.tsv]
    set occupied [dict create]
    foreach cell [get_cells -hierarchical -filter {IS_PRIMITIVE == 1 && (REF_NAME =~ FD* || REF_NAME =~ LD*)}] {
        set loc [get_property LOC $cell]
        if {$loc ne {}} {dict lappend occupied $loc $cell}
    }
    set free [dict create]
    set count 0
    foreach site [get_sites -filter {SITE_TYPE == SLICEL || SITE_TYPE == SLICEM}] {
        set slots {}
        foreach letter {A B C D E F G H} {
            if {[get_property IS_USED [get_bels $site/${letter}5LUT]] ||
                [get_property IS_USED [get_bels $site/${letter}6LUT]]} {continue}
            foreach suffix {FF FF2} {
                if {![get_property IS_USED [get_bels $site/${letter}${suffix}]]} {lappend slots ${letter}${suffix}}
            }
        }
        if {![llength $slots]} {continue}
        set controls {}
        set legal 1
        if {[dict exists $occupied $site]} {
            foreach cell [dict get $occupied $site] {
                if {[get_property REF_NAME [get_cells $cell]] ne {FDRE}} {set legal 0; break}
                set signature [relocate_controls $cell]
                if {$controls eq {}} {set controls $signature} elseif {$controls ne $signature} {set legal 0; break}
            }
        }
        if {!$legal} {continue}
        regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $site -> x y
        dict set free "$x,$y" [list $site $slots $controls [get_clock_regions -of_objects [get_sites $site]]]
        incr count [llength $slots]
        if {[dict size $free]%250==0} {puts "DENSE_RELOCATION_AVAILABLE_SITES=[dict size $free] FF_SLOTS=$count"}
    }
    puts "DENSE_RELOCATION_INITIAL_SITES=[dict size $free] FF_SLOTS=$count TARGETS=[llength $candidates]"
    set f [open [file join $out relocation_selection.txt] w]
    puts $f "SELECTED=[llength $candidates]\nINITIAL_SITES=[dict size $free]\nINITIAL_SLOTS=$count\nMODE=unused_lut_pair_same_controls_same_clock_region"
    close $f
    set relocated {}
    foreach record $candidates {
        lassign $record cell endpoint loc bel signature hs ss
        foreach property {IS_LOC_FIXED IS_BEL_FIXED DONT_TOUCH} {
            if {[get_property $property [get_cells $cell]] in {1 true TRUE}} {error "Protected FIFO register: $cell $property"}
        }
        regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $loc -> x y
        set region [get_clock_regions -of_objects [get_sites $loc]]
        set controls [relocate_controls $cell]
        set target {}
        for {set radius 1} {$radius <= 40 && $target eq {}} {incr radius} {
            for {set dx -$radius} {$dx <= $radius && $target eq {}} {incr dx} {
                set dy [expr {$radius-abs($dx)}]
                foreach yy [lsort -unique [list [expr {$y-$dy}] [expr {$y+$dy}]]] {
                    set key "[expr {$x+$dx}],$yy"
                    if {![dict exists $free $key]} {continue}
                    lassign [dict get $free $key] site slots existing site_region
                    if {$site_region ne $region || ($existing ne {} && $existing ne $controls)} {continue}
                    set target $site/[lindex $slots 0]
                    set slots [lrange $slots 1 end]
                    if {[llength $slots]} {dict set free $key [list $site $slots $controls $site_region]} else {dict unset free $key}
                    break
                }
            }
        }
        if {$target eq {}} {error "Insufficient local compatible FIFO placement capacity after [llength $relocated] moves: $cell"}
        if {[get_property IS_USED [get_bels $target]]} {error "Selected occupied FF: $target"}
        place_cell [list $cell $target]
        if {[relocate_pin_signature $cell] ne $signature} {error {Relocation changed logical connectivity}}
        lappend relocated [concat $record [list $target]]
        if {[llength $candidates]<=8 || [llength $relocated]%250==0} {
            puts "HOLD_RELOCATED=[llength $relocated] $loc/$bel->$target"
        }
    }
    set f [open [file join $out relocation_records.list] w]; puts $f $relocated; close $f
    write_checkpoint [file join $out relocation_moved_candidate.dcp]
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
