# Recreate each FDRE with identical pins and functional parameters before
# relocation, removing inherited native packing membership if supported.
# No register, data/control connection, or pipeline latency is added.
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

proc relocate_register_properties {cell} {
    set result {}
    foreach property {INIT IS_C_INVERTED IS_D_INVERTED IS_R_INVERTED} {
        set value [get_property $property [get_cells $cell]]
        if {$value in {{} 0 false FALSE 1'b0 1'h0}} {set value 0
        } elseif {$value in {1 true TRUE 1'b1 1'h1}} {set value 1
        } else {error "Unsupported FDRE functional property $cell $property=$value"}
        lappend result [list $property $value]
    }
    return $result
}
proc recreate_fifo_register {name signature properties} {
    set old [get_cells $name]
    set name [string range "name:[get_property NAME $old]" 5 end]
    puts "RECREATE_STEP=old_properties NAME=$name"
    if {[get_property REF_NAME $old] ne {FDRE}} {error {Only FDRE reconstruction is allowed}}
    if {[llength $signature]!=5} {error {Unexpected FDRE pin set}}
    foreach item $signature {
        lassign $item pin nets
        if {$pin ni {C CE D R Q} || [llength $nets]!=1} {error {Ambiguous FDRE connectivity}}
    }
    puts {RECREATE_STEP=remove}
    remove_cell $old
    puts {RECREATE_STEP=create}
    create_cell -reference FDRE $name
    puts "RECREATE_STEP=created MATCHED=[llength [get_cells $name]]"
    foreach item $properties {
        lassign $item property value
        puts "RECREATE_STEP=parameter $property=$value"
        # Empty inversion values denote the documented FDRE default zero.
        if {$property eq {INIT} || $value} {set_property $property "1'b$value" [get_cells $name]}
    }
    foreach item $signature {
        lassign $item pin nets
        puts "RECREATE_STEP=connect PIN=$pin NETS=$nets MATCHED_NETS=[llength [get_nets [lindex $nets 0]]] MATCHED_PIN=[llength [get_pins $name/$pin]]"
        connect_net -hierarchical -net [get_nets [lindex $nets 0]] -objects [get_pins $name/$pin]
    }
    puts {RECREATE_STEP=verify}
    if {[relocate_pin_signature $name] ne $signature ||
        [relocate_register_properties $name] ne $properties} {
        error "FDRE reconstruction changed function: $name"
    }
}

proc verify_fifo_relocation {manifest report} {
    set f [open $manifest r]; set records [read $f]; close $f
    set f [open $report w]
    puts $f "cell\tendpoint\told_site\tnew_site\tconnections"
    foreach record $records {
        lassign $record cell endpoint loc bel signature hs ss target properties
        if {[get_property REF_NAME [get_cells $cell]] ne {FDRE} || [relocate_pin_signature $cell] ne $signature} {
            error "Relocated primitive or pin connections changed: $cell"
        }
        if {[relocate_register_properties $cell] ne $properties} {error "Recreated FDRE parameters changed: $cell"}
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
    foreach region [get_clock_regions] {
        foreach site [get_sites -of_objects $region -filter {SITE_TYPE == SLICEL || SITE_TYPE == SLICEM}] {
            if {[dict exists $regions $site]} {error {Ambiguous site clock region}}
            dict set regions $site $region
        }
    }
    if {[dict size $regions]!=[llength $sites]} {error {Incomplete bulk site-region map}}
    foreach record $candidates {
        set loc [lindex $record 2]
        if {[dict get $regions $loc] ne [get_clock_regions -of_objects [get_sites $loc]]} {
            error {Bulk clock-region map disagrees with native point query}
        }
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
    puts $f "SELECTED=[llength $candidates]\nINITIAL_SITES=[dict size $free]\nINITIAL_SLOTS=$count\nMODE=reconstructed_fdre_bulk_clock_region_native_legality"
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
        set region [dict get $regions $loc]
        set properties [relocate_register_properties $cell]
        recreate_fifo_register $cell $signature $properties
        set target {}
        set rejected_for_cell [dict create]
        set cell_rejections 0
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
                            incr cell_rejections
                            dict set rejected_for_cell $attempt 1
                            set original_bel [lindex [split $bel .] end]
                            if {[get_property LOC [get_cells $cell]] ne $loc ||
                                [get_property BEL [get_cells $cell]] ne $bel} {
                                place_cell [list $cell $loc/$original_bel]
                            }
                            if {[relocate_pin_signature $cell] ne $signature} {error {Rejected placement changed logical connectivity}}
                            if {[string match -nocase *shape* $reason] || $cell_rejections>=512} {
                                close $trials
                                write_checkpoint [file join $out relocation_partial_failed.dcp]
                                error "Reconstructed FDRE has persistent packing restriction or excessive placement rejections: $cell"
                            }
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
        lappend relocated [concat $record [list $target $properties]]
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
