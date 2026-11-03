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



# Preserve every pre-existing placed primitive while the native placer assigns
# only the recreated output FFs. All temporary locks/Pblock are removed before
# routing; original LOCK states, leaf set, connectivity and parameters are checked.
proc relocate_fifo_registers {out candidates} {
    if {![llength $candidates] || [llength $candidates]>12000} {error {Unexpected relocation count}}
    relocate_leaf_snapshot [file join $out relocation_before_cells.tsv]
    write_checkpoint [file join $out relocation_before_moves.dcp]
    set targets {}
    foreach record $candidates {dict set targets [lindex $record 0] 1}
    set originals {}
    # IS_PLACED is not a usable leaf-cell filter in this Vivado checkpoint.
    # Query actual LOC values, retaining every primitive with a placement.
    set placed [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]
    set names [get_property NAME $placed]
    set locs [get_property LOC $placed]
    set bels [get_property BEL $placed]
    set loc_fixed [get_property IS_LOC_FIXED $placed]
    set bel_fixed [get_property IS_BEL_FIXED $placed]
    set lock_names {}
    foreach name $names loc $locs bel $bels lf $loc_fixed bf $bel_fixed {
        if {$loc eq {}} {continue}
        if {[dict exists $targets $name]} {continue}
        lappend originals [list $name $loc $bel $lf $bf]
        lappend lock_names $name
    }
    if {![llength $originals]} {error {No original placed primitives were captured}}
    set f [open [file join $out batch_original_placement.list] w]; puts $f $originals; close $f
    set locked [get_cells $lock_names]
    set_property IS_LOC_FIXED true $locked
    set_property IS_BEL_FIXED true $locked
    puts "BATCH_RELOCATION_LOCKED=[llength $originals] TARGETS=[llength $candidates]"
    set frozen {}
    set f [open [file join $out reconstruction_before_parameters.tsv] w]
    puts $f "cell\tINIT\tIS_C_INVERTED\tIS_D_INVERTED\tIS_R_INVERTED"
    foreach record $candidates {
        lassign $record cell endpoint loc bel signature hs ss
        set cell [string range "cell:[get_property NAME [get_cells $cell]]" 5 end]
        set record [lreplace $record 0 1 $cell $cell/D]
        foreach property {IS_LOC_FIXED IS_BEL_FIXED DONT_TOUCH} {
            if {[get_property $property [get_cells $cell]] in {1 true TRUE}} {error "Protected target $cell"}
        }
        set props [relocate_register_properties $cell]
        set values {}
        foreach item $props {lappend values [lindex $item 1]}
        puts $f "$cell\t[join $values \t]"
        recreate_fifo_register $cell $signature $props
        lappend frozen [concat $record [list $props]]
        if {[llength $frozen]%250==0 || [llength $candidates]<=8} {puts "BATCH_RECREATED=[llength $frozen]"}
    }
    close $f
    set f [open [file join $out fifo_floorplan_targets.list] w]
    foreach record $frozen {puts $f [list [lindex $record 0]]}
    close $f
    prepare_fifo_floorplan $out
    puts {BATCH_RELOCATION_PHASE=native_eco_placement}
    place_design -eco -no_psip -no_bufg_opt
    verify_fifo_floorplan [file join $out fifo_floorplan_records.list] [file join $out fifo_floorplan_after_place.tsv]
    # Lock restoration is exact, and any unexpected location/BEL change is fatal.
    set restore [dict create]
    set f [open [file join $out batch_unchanged_placement.tsv] w]
    puts $f "cell\toriginal_loc\tcurrent_loc\toriginal_bel\tcurrent_bel"
    foreach record $originals {
        lassign $record name loc bel lf bf
        set cell [get_cells $name]
        set after_loc [get_property LOC $cell]
        set after_bel [get_property BEL $cell]
        if {$after_loc ne $loc || $after_bel ne $bel} {error "Native placer changed locked original $name"}
        puts $f "$name\t$loc\t$after_loc\t$bel\t$after_bel"
        dict lappend restore [list $lf $bf] $name
    }
    close $f
    dict for {flags names} $restore {
        lassign $flags lf bf
        set cells [get_cells $names]
        set_property IS_LOC_FIXED $lf $cells
        set_property IS_BEL_FIXED $bf $cells
        foreach a [get_property IS_LOC_FIXED $cells] b [get_property IS_BEL_FIXED $cells] {
            if {$a ne $lf || $b ne $bf} {error {Temporary original placement locks not restored}}
        }
    }
    release_fifo_floorplan
    set relocated {}
    foreach record $frozen {
        set cell [lindex $record 0]
        set props [lindex $record end]
        set loc [get_property LOC [get_cells $cell]]
        set bel [lindex [split [get_property BEL [get_cells $cell]] .] end]
        set_property IS_LOC_FIXED true [get_cells $cell]
        set_property IS_BEL_FIXED true [get_cells $cell]
        lappend relocated [concat [lrange $record 0 6] [list $loc/$bel $props]]
    }
    set f [open [file join $out relocation_records.list] w]; puts $f $relocated; close $f
    write_checkpoint [file join $out relocation_moved_candidate.dcp]
    verify_fifo_relocation [file join $out relocation_records.list] [file join $out relocation_before_route.tsv]
    relocate_leaf_snapshot [file join $out relocation_moved_cells.tsv]
    puts "DENSE_RELOCATION_ACCEPTED=[llength $relocated] MODE=NATIVE_BATCH_ECO"
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
