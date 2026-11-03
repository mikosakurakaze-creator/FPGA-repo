# Scoped hold ECO: one identity LUT on a RAM output -> existing FDRE D pin.
# No flip-flop, clock, reset, enable or protocol stage is added.
proc hold_pin_nets {pin} {
    return [lsort [get_property NAME [get_nets -quiet -segments -of_objects $pin]]]
}

proc hold_leaf_snapshot {path} {
    set cells [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]
    set names [get_property NAME $cells]
    set refs [get_property REF_NAME $cells]
    set f [open $path w]
    foreach name $names ref $refs {puts $f "$name\t$ref"}
    close $f
}

proc verify_fifo_hold_eco {manifest report} {
    set f [open $manifest r]
    set records [read $f]
    close $f
    set f [open $report w]
    puts $f "buffer\tendpoint\tidentity_init\tconnections\tcontrols"
    foreach record $records {
        lassign $record buffer endpoint oldnet newnet olddrivers otherloads controls oldslack bel
        set cell [get_cells $buffer]
        if {[llength $cell] != 1 || [get_property REF_NAME $cell] ne {LUT1}} {error "Missing identity buffer $buffer"}
        set init [string tolower [get_property INIT $cell]]
        if {$init ni {2'h2 2'b10 2 10}} {error "Buffer truth table is not identity: $buffer $init"}
        set input [get_pins $buffer/I0]
        set output [get_pins $buffer/O]
        set end [get_pins $endpoint]
        if {[hold_pin_nets $input] ne [lsort [get_property NAME [get_nets -segments $oldnet]]]} {
            error "Input connection changed: $buffer"
        }
        if {[hold_pin_nets $output] ne [hold_pin_nets $end]} {error "Output does not feed original endpoint: $buffer"}
        set drivers [lsort [get_property NAME [get_pins -leaf -of_objects [get_nets -segments -of_objects $input] -filter {DIRECTION == OUT}]]]
        if {$drivers ne $olddrivers} {error "RAM driver changed: $buffer"}
        set loads [lsort [get_property NAME [get_pins -leaf -of_objects [get_nets -segments -of_objects $output] -filter {DIRECTION == IN}]]]
        if {$loads ne [list $endpoint]} {error "Unexpected buffer output loads: $buffer"}
        set upstream_loads [lsort [get_property NAME [get_pins -leaf -of_objects [get_nets -segments -of_objects $input] -filter {DIRECTION == IN}]]]
        if {$upstream_loads ne [lsort [concat $otherloads [list $buffer/I0]]]} {error "Unrelated loads changed: $buffer"}
        foreach control $controls {
            lassign $control name expected
            if {[hold_pin_nets [get_pins $name]] ne $expected} {error "Register control/output changed: $name"}
        }
        puts $f "$buffer\t$endpoint\t$init\tPASS\tPASS"
    }
    puts $f "VERIFIED_IDENTITY_BUFFERS=[llength $records]"
    close $f
    return [llength $records]
}

proc insert_fifo_hold_eco {out {limit 12000} {sample 0}} {
    # Called only after an initial route, under the stricter hold target.
    set candidates {}
    set risky [dict create]
    foreach path [get_timing_paths -delay_type max -slack_lesser_than 0.8 -max_paths 50000 -nworst 1] {
        dict set risky [get_property ENDPOINT_PIN $path] 1
    }
    set skipped 0
    foreach path [get_timing_paths -delay_type min -slack_lesser_than 0.0 -max_paths 30000 -nworst 1] {
        set start [get_pins [get_property STARTPOINT_PIN $path]]
        set endpoint [get_property ENDPOINT_PIN $path]
        set end [get_pins $endpoint]
        set sc [get_cells -of_objects $start]
        set dc [get_cells -of_objects $end]
        if {[get_property REF_NAME $sc] ni {RAMD32 RAMD64E} ||
            [get_property REF_NAME $dc] ne {FDRE} ||
            [get_property LOC $sc] ne [get_property LOC $dc] ||
            [get_property REF_PIN_NAME $end] ne {D}} {continue}
        if {[dict exists $risky $endpoint]} {incr skipped; continue}
        lappend candidates [list $endpoint [get_property LOC $dc] [get_property SLACK $path]]
    }
    if {$sample > 0} {set candidates [lrange $candidates 0 [expr {$sample-1}]]}
    if {![llength $candidates] || [llength $candidates] > $limit} {
        error "Unexpected scoped hold candidate count: [llength $candidates]"
    }
    set f [open [file join $out hold_eco_selection.txt] w]
    puts $f "SELECTED=[llength $candidates]\nSKIPPED_SETUP_HEADROOM=$skipped\nMIN_TIGHTENED_SETUP_HEADROOM_NS=0.800"
    close $f
    puts "HOLD_ECO_SELECTED=[llength $candidates]"
    hold_leaf_snapshot [file join $out hold_eco_before_cells.tsv]

    # Index unused LUT pairs. A LUT1 has no clock/control-set requirement.
    # Requiring both 5LUT and 6LUT free avoids disturbing an existing LUT pair.
    set free [dict create]
    # Vivado 2025.2 BEL objects expose IS_USED, not IS_OCCUPIED.
    # The latter silently yields an empty filter result on this device.
    set free_bels [get_bels -quiet SLICE*/*6LUT -filter {IS_USED == 0 && IS_RESERVED == 0 && PROHIBIT == 0}]
    puts "HOLD_ECO_FREE_BEL_QUERY=[llength $free_bels] SAMPLE=[lrange $free_bels 0 3]"
    foreach bel $free_bels {
        if {![regexp {^(SLICE_X([0-9]+)Y([0-9]+))/([A-H])6LUT$} [get_property NAME $bel] -> site x y letter]} {continue}
        set pair [get_bels $site/${letter}5LUT]
        if {[llength $pair] != 1 || [get_property IS_USED $pair] ||
            [get_property IS_RESERVED $pair] || [get_property PROHIBIT $pair]} {continue}
        dict lappend free "$x,$y" $bel
    }
    puts "HOLD_ECO_FREE_PAIR_SITES=[dict size $free] SAMPLE=[lrange [dict keys $free] 0 4]"
    if {![dict size $free]} {error {No unoccupied LUT pairs found; inspect BEL query evidence}}
    set records {}
    set index 0
    foreach candidate $candidates {
        lassign $candidate endpoint loc slack
        if {![regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $loc -> x y]} {error "Unexpected sink location $loc"}
        set chosen {}
        for {set radius 0} {$radius <= 40 && $chosen eq {}} {incr radius} {
            for {set dx -$radius} {$dx <= $radius && $chosen eq {}} {incr dx} {
                set dy [expr {$radius-abs($dx)}]
                foreach yy [lsort -unique [list [expr {$y+$dy}] [expr {$y-$dy}]]] {
                    set key "[expr {$x+$dx}],$yy"
                    if {[dict exists $free $key] && [llength [dict get $free $key]]} {
                        set chosen [lindex [dict get $free $key] 0]
                        dict set free $key [lrange [dict get $free $key] 1 end]
                        break
                    }
                }
            }
        }
        if {$chosen eq {}} {
            set best_distance 1000000
            set best_key {}
            dict for {key bels} $free {
                if {![llength $bels]} {continue}
                lassign [split $key ,] xx yy
                set distance [expr {abs($xx-$x)+abs($yy-$y)}]
                if {$distance < $best_distance} {set best_distance $distance; set best_key $key}
            }
            if {$best_key eq {}} {error "No free LUT remains for $endpoint"}
            set chosen [lindex [dict get $free $best_key] 0]
            dict set free $best_key [lrange [dict get $free $best_key] 1 end]
            puts "HOLD_ECO_DISTANT_PLACEMENT=$best_distance END=$endpoint"
        }
        set end [get_pins $endpoint]
        set dest [get_cells -of_objects $end]
        set net [get_nets -of_objects $end]
        if {[llength $net] != 1} {error "Ambiguous endpoint net $endpoint"}
        set segments [get_nets -segments -of_objects $end]
        if {[llength [get_clocks -quiet -of_objects $segments]]} {error {Refusing to modify clock net}}
        if {[llength [filter $segments {DONT_TOUCH == 1}]]} {error {Refusing to modify protected net}}
        set drivers [lsort [get_property NAME [get_pins -leaf -of_objects $segments -filter {DIRECTION == OUT}]]]
        if {[llength $drivers] != 1} {error {Expected a single RAM output driver}}
        set loads [lsort [get_property NAME [get_pins -leaf -of_objects $segments -filter {DIRECTION == IN}]]]
        set pos [lsearch -exact $loads $endpoint]
        if {$pos < 0} {error {Original endpoint missing from net}}
        set otherloads [lreplace $loads $pos $pos]
        set controls {}
        foreach pin {C CE R Q} {
            set name $dest/$pin
            lappend controls [list $name [hold_pin_nets [get_pins $name]]]
        }
        set parent [get_property PARENT_CELL $net]
        set buffer $parent/hold_margin_buf_[format %05d $index]
        set newnet $parent/hold_margin_data_[format %05d $index]
        create_cell -reference LUT1 $buffer
        set_property INIT 2'h2 [get_cells $buffer]
        set_property DONT_TOUCH true [get_cells $buffer]
        create_net $newnet
        connect_net -hierarchical -net $net -objects [get_pins $buffer/I0]
        disconnect_net -net $net -pinlist $end
        connect_net -hierarchical -net [get_nets $newnet] -objects [list $buffer/O $endpoint]
        place_cell [list $buffer $chosen]
        lappend records [list $buffer $endpoint $net $newnet $drivers $otherloads $controls $slack $chosen]
        incr index
        if {$index % 250 == 0} {puts "HOLD_ECO_INSERTED=$index"}
    }
    set manifest [file join $out hold_eco_records.list]
    set f [open $manifest w]
    puts $f $records
    close $f
    verify_fifo_hold_eco $manifest [file join $out hold_eco_before_route.tsv]
    hold_leaf_snapshot [file join $out hold_eco_inserted_cells.tsv]
    puts "HOLD_ECO_INSERT_PASS=$index"
    return $index
}

proc release_hold_eco_placement {manifest} {
    set f [open $manifest r]
    set records [read $f]
    close $f
    foreach record $records {
        set cell [get_cells [lindex $record 0]]
        set_property IS_LOC_FIXED false $cell
        set_property IS_BEL_FIXED false $cell
    }
}
