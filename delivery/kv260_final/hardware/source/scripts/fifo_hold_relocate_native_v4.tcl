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
    # Each native place_cell trial checks the complete site's shared routing
    # and control resources. An unused FF is a candidate, not proof of legality.
    set free [dict create]
    set sites [get_sites -filter {SITE_TYPE == SLICEL || SITE_TYPE == SLICEM}]
    set regions [dict create]
    foreach site $sites {
        dict set regions $site [get_clock_regions -of_objects [get_sites $site]]
    }
    set bels [get_bels -quiet SLICE*/*FF*]
    set used [get_property IS_USED $bels]
    set count 0
    foreach bel $bels occupied $used {
        if {$occupied || ![regexp {^(SLICE_X([0-9]+)Y([0-9]+))/([A-H]FF2?)$} $bel -> site x y slot]} {continue}
        if {![dict exists $regions $site]} {continue}
        set key "$x,$y"
        if {![dict exists $free $key]} {dict set free $key [list $site {} {} [dict get $regions $site]]}
        lassign [dict get $free $key] site slots controls region
        lappend slots $slot
        dict set free $key [list $site $slots {} $region]
        incr count
    }
    puts "DENSE_RELOCATION_INITIAL_SITES=[dict size $free] FF_SLOTS=$count TARGETS=[llength $candidates]"
    set f [open [file join $out relocation_selection.txt] w]
    puts $f "SELECTED=[llength $candidates]\nINITIAL_SITES=[dict size $free]\nINITIAL_SLOTS=$count\nMODE=native_legality_all_free_ff_same_clock_region"
    close $f
    set relocated {}
    write_checkpoint [file join $out relocation_before_moves.dcp]
    set trials [open [file join $out relocation_placement_trials.tsv] w]
    puts $trials "cell\ttarget\tstatus\tdiagnostics"
    set rejected 0
    foreach record $candidates {
        lassign $record cell endpoint loc bel signature hs ss
        foreach property {IS_LOC_FIXED IS_BEL_FIXED DONT_TOUCH} {
            if {[get_property $property [get_cells $cell]] in {1 true TRUE}} {error "Protected FIFO register: $cell $property"}
        }
        regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $loc -> x y
        set region [get_clock_regions -of_objects [get_sites $loc]]
        set controls [relocate_controls $cell]
        set target {}
        set rejected_for_cell [dict create]
        for {set radius 1} {$radius <= 80 && $target eq {}} {incr radius} {
            for {set dx -$radius} {$dx <= $radius && $target eq {}} {incr dx} {
                set dy [expr {$radius-abs($dx)}]
                foreach yy [lsort -unique [list [expr {$y-$dy}] [expr {$y+$dy}]]] {
                    set key "[expr {$x+$dx}],$yy"
                    if {![dict exists $free $key]} {continue}
                    lassign [dict get $free $key] site slots existing site_region
                    if {$site_region ne $region} {continue}
                    foreach slot $slots {
                        set attempt $site/$slot
                        if {[dict exists $rejected_for_cell $attempt]} {continue}
                        puts "PLACEMENT_TRIAL_BEGIN\t$cell\t$attempt"
                        set code [catch {place_cell [list $cell $attempt]} reason]
                        if {$code} {puts $reason}
                        puts "PLACEMENT_TRIAL_END\t$code"
                        set diagnostics $reason
                        if {$code} {
                            # A speculative BEL can fail due to site routing resources.
                            # Keep its complete tool message; only this specific
                            # placement rejection is eligible for another attempt.
                            puts $trials "$cell\t$attempt\tREJECTED\t[string map [list \n {\\n} \t {\\t} \r {}] [list $reason $diagnostics]]"
                            flush $trials
                            # Raw tool messages remain in the console between
                            # the trial markers. The runner accepts only the
                            # exact reviewed 12-1409 rejection in a failed trial.
                            incr rejected
                            dict set rejected_for_cell $attempt 1
                            set original_bel [lindex [split $bel .] end]
                            if {[get_property LOC [get_cells $cell]] ne $loc ||
                                [get_property BEL [get_cells $cell]] ne $bel} {
                                place_cell [list $cell $loc/$original_bel]
                            }
                            if {[relocate_pin_signature $cell] ne $signature} {error {Rejected placement changed logical connectivity}}
                            continue
                        }
                        set target $attempt
                        puts $trials "$cell\t$attempt\tACCEPTED\t[string map [list \n {\\n} \t {\\t} \r {}] $diagnostics]"
                        set remaining [lsearch -all -inline -not -exact $slots $slot]
                        if {[llength $remaining]} {dict set free $key [list $site $remaining {} $site_region]} else {dict unset free $key}
                        break
                    }
                    if {$target ne {}} {break}
                }
            }
        }
        if {$target eq {}} {
            close $trials
            write_checkpoint [file join $out relocation_partial_failed.dcp]
            error "Insufficient compatible local placement after [llength $relocated] moves: $cell"
        }
        if {[relocate_pin_signature $cell] ne $signature} {error {Relocation changed logical connectivity}}
        lappend relocated [concat $record [list $target]]
        if {[llength $candidates]<=8 || [llength $relocated]%250==0} {
            puts "HOLD_RELOCATED=[llength $relocated] $loc/$bel->$target"
        }
    }
    close $trials
    puts "DENSE_RELOCATION_ACCEPTED=[llength $relocated] REJECTED_BEL_ATTEMPTS=$rejected"
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
