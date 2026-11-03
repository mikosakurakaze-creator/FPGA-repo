# Recreate each FDRE with identical pins and functional parameters before
# relocation, removing inherited native packing membership if supported.
# No register, data/control connection, or pipeline latency is added.
# Target only logic slices: avoid stealing a live LUTRAM address/site pin.
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
# A hierarchical net alias is not a distinct electrical control signal.
# Cache the complete connected-segment equivalence class before comparing.
proc relocate_canonical_net {pin} {
    global relocation_net_alias_cache
    set local [get_nets -of_objects $pin]
    if {[llength $local]!=1} {error "Ambiguous control net: $pin"}
    set alias [get_property NAME $local]
    if {[dict exists $relocation_net_alias_cache $alias]} {
        return [dict get $relocation_net_alias_cache $alias]
    }
    set names [lsort [get_property NAME [get_nets -segments -of_objects $pin]]]
    if {![llength $names]} {error "Empty connected control-net class: $pin"}
    set canonical [lindex $names 0]
    foreach name $names {dict set relocation_net_alias_cache $name $canonical}
    return $canonical
}
proc relocate_controls {cell} {
    set sig {}
    foreach pin {C CE R} {lappend sig [relocate_canonical_net [get_pins $cell/$pin]]}
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
    if {[get_property REF_NAME $old] ne {FDRE}} {error {Only FDRE reconstruction is allowed}}
    if {[llength $signature]!=5} {error {Unexpected FDRE pin set}}
    foreach item $signature {
        lassign $item pin nets
        if {$pin ni {C CE D R Q} || [llength $nets]!=1} {error {Ambiguous FDRE connectivity}}
    }
    remove_cell $old
    create_cell -reference FDRE $name
    foreach item $properties {
        lassign $item property value
        # Empty inversion values denote the documented FDRE default zero.
        if {$property eq {INIT} || $value} {set_property $property "1'b$value" [get_cells $name]}
    }
    foreach item $signature {
        lassign $item pin nets
        connect_net -hierarchical -net [get_nets [lindex $nets 0]] -objects [get_pins $name/$pin]
    }
    if {[relocate_pin_signature $name] ne $signature ||
        [relocate_register_properties $name] ne $properties} {
        error "FDRE reconstruction changed function: $name"
    }
}

proc verify_fifo_relocation {manifest report} {
    set f [open $manifest r]; set records [read $f]; close $f
    set f [open $report w]
    puts $f "cell\tendpoint\told_site\tnew_site\tconnections"
    set pf [open $report.parameters.tsv w]
    puts $pf "cell\tINIT\tIS_C_INVERTED\tIS_D_INVERTED\tIS_R_INVERTED"
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
        set values {}
        foreach item [relocate_register_properties $cell] {lappend values [lindex $item 1]}
        puts $pf "$cell\t[join $values \t]"
    }
    puts $f "VERIFIED_RELOCATED_REGISTERS=[llength $records]"
    close $f
    close $pf
    return [llength $records]
}


proc relocate_control_signature {cell} {
    if {[get_property REF_NAME [get_cells $cell]] ne {FDRE}} {return {UNSUPPORTED}}
    set nets [relocate_controls $cell]
    set params [relocate_register_properties $cell]
    return [list [lindex $nets 0] [lindex $nets 1] [lindex $nets 2] [lindex [lindex $params 1] 1] [lindex [lindex $params 3] 1]]
}
proc relocate_bank {slot} {
    if {![regexp {^([A-H])FF(2?)$} $slot -> letter second]} {error {Invalid FF slot}}
    return [list [expr {$letter in {A B C D} ? 0 : 1}] [expr {$second eq {2} ? 1 : 0}]]
}
proc relocate_control_allowed {site slot signature} {
    global relocation_control_cache
    if {![dict exists $relocation_control_cache $site]} {
        set present [get_bels -quiet $site/*FF* -filter {IS_USED == 1}]
        set controls {}
        if {[llength $present]} {
            set cells [get_cells -quiet -of_objects $present]
            foreach cell $cells {
                set bel [lindex [split [get_property BEL $cell] .] end]
                lassign [relocate_bank $bel] half bank
                lappend controls [list $half $bank [relocate_control_signature $cell]]
            }
        }
        dict set relocation_control_cache $site $controls
    }
    lassign [relocate_bank $slot] half bank
    lassign $signature clock enable reset invert_clock invert_reset
    foreach item [dict get $relocation_control_cache $site] {
        lassign $item oldhalf oldbank other
        if {$half!=$oldhalf} {continue}
        if {$other eq {UNSUPPORTED}} {return 0}
        lassign $other oc oe orst oic oir
        if {$clock ne $oc || $reset ne $orst || $invert_clock ne $oic || $invert_reset ne $oir} {return 0}
        if {$bank==$oldbank && $enable ne $oe} {return 0}
    }
    return 1
}

proc relocate_query_site {key free_var region_var} {
    upvar 1 $free_var free $region_var regions
    if {[dict exists $regions $key]} {return}
    lassign [split $key ,] x y
    set name SLICE_X${x}Y${y}
    set site [get_sites -quiet $name]
    if {![llength $site]} {dict set regions $key {}; return}
    set region [get_clock_regions -of_objects $site]
    dict set regions $key $region
    if {[get_property SITE_TYPE $site] ne {SLICEL}} {return}
    set bels [get_bels -quiet $name/*FF* -filter {IS_USED == 0 && IS_RESERVED == 0 && PROHIBIT == 0}]
    if {![llength $bels]} {return}
    set slots {}
    foreach bel [get_property NAME $bels] {
        if {[regexp {/([A-H]FF2?)$} $bel -> slot]} {lappend slots $slot}
    }
    if {[llength $slots]} {dict set free $key [list $name $slots {} $region]}
}

proc relocate_fifo_registers {out candidates} {
    if {![llength $candidates] || [llength $candidates] > 12000} {error {Unexpected relocation count}}
    relocate_leaf_snapshot [file join $out relocation_before_cells.tsv]
    # Query and cache only sites actually encountered by the local search.
    set free [dict create]
    set regions [dict create]
    global relocation_control_cache relocation_net_alias_cache
    set relocation_control_cache [dict create]
    set relocation_net_alias_cache [dict create]
    set control_filtered 0
    puts "RELOCATION_SITE_QUERY_MODE=lazy_neighbors TARGETS=[llength $candidates]"
    set f [open [file join $out relocation_selection.txt] w]
    puts $f "SELECTED=[llength $candidates]\nMODE=reconstructed_fdre_slicel_only_half_slice_control_filter"
    close $f
    set relocated {}
    write_checkpoint [file join $out relocation_before_moves.dcp]
    set trials [open [file join $out relocation_placement_trials.tsv] w]
    puts $trials "cell\ttarget\tstatus\tdiagnostics"
    set parameters [open [file join $out reconstruction_before_parameters.tsv] w]
    puts $parameters "cell\tINIT\tIS_C_INVERTED\tIS_D_INVERTED\tIS_R_INVERTED"
    set rejected 0
    foreach record $candidates {
        lassign $record cell endpoint loc bel signature hs ss
        # Serialized strings must not retain a deleted cell/pin object handle.
        set cell [string range "cell:[get_property NAME [get_cells $cell]]" 5 end]
        set endpoint $cell/D
        set record [lreplace $record 0 1 $cell $endpoint]
        foreach property {IS_LOC_FIXED IS_BEL_FIXED DONT_TOUCH} {
            if {[get_property $property [get_cells $cell]] in {1 true TRUE}} {error "Protected FIFO register: $cell $property"}
        }
        regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $loc -> x y
        set source_key "$x,$y"
        relocate_query_site $source_key free regions
        set region [dict get $regions $source_key]
        set control_signature [relocate_control_signature $cell]
        set properties [relocate_register_properties $cell]
        set values {}
        foreach item $properties {lappend values [lindex $item 1]}
        puts $parameters "$cell\t[join $values \t]"
        flush $parameters
        recreate_fifo_register $cell $signature $properties
        set target {}
        set rejected_for_cell [dict create]
        set cell_rejections 0
        for {set radius 1} {$radius <= 80 && $target eq {}} {incr radius} {
            for {set dx -$radius} {$dx <= $radius && $target eq {}} {incr dx} {
                set dy [expr {$radius-abs($dx)}]
                foreach yy [lsort -unique [list [expr {$y-$dy}] [expr {$y+$dy}]]] {
                    set key "[expr {$x+$dx}],$yy"
                    relocate_query_site $key free regions
                    if {![dict exists $free $key]} {continue}
                    lassign [dict get $free $key] site slots existing site_region
                    if {$site_region ne $region} {continue}
                    foreach slot $slots {
                        if {![relocate_control_allowed $site $slot $control_signature]} {incr control_filtered; continue}
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
                            # This is a newly recreated, originally unplaced cell.
                            # Keep rejected trials unplaced, avoiding reattachment
                            # to the old RAM packing through its original slot.
                            if {[get_property LOC [get_cells $cell]] ne {}} {
                                unplace_cell [get_cells $cell]
                            }
                            if {[relocate_pin_signature $cell] ne $signature} {error {Rejected placement changed logical connectivity}}
                            if {[string match -nocase *shape* $reason] || $cell_rejections>=4096} {
                                close $trials
                                write_checkpoint [file join $out relocation_partial_failed.dcp]
                                error "Reconstructed FDRE has persistent packing restriction or excessive placement rejections: $cell"
                            }
                            continue
                        }
                        set target $attempt
                        lassign [relocate_bank $slot] half bank
                        dict lappend relocation_control_cache $site [list $half $bank $control_signature]
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
    close $parameters
    puts "DENSE_RELOCATION_ACCEPTED=[llength $relocated] REJECTED_BEL_ATTEMPTS=$rejected CONTROL_FILTERED=$control_filtered"
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
