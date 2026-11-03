# Record setup sensitivity, but do not silently leave tight hold paths untreated.
# Final global setup >= requested margin remains mandatory after real routing.
proc collect_and_relocate_fifo {out setup_margin hold_margin} {
    set risky [dict create]
    set setup_paths [get_timing_paths -delay_type max -slack_lesser_than 0.800 -max_paths 200000 -nworst 1]
    if {[llength $setup_paths]>=200000} {error {Setup query coverage cap reached}}
    foreach path $setup_paths {
        foreach property {STARTPOINT_PIN ENDPOINT_PIN} {
            dict set risky [get_property NAME [get_cells -of_objects [get_pins [get_property $property $path]]]] 1
        }
    }
    set hold_paths [get_timing_paths -delay_type min -slack_lesser_than 0.0 -max_paths 30000 -nworst 1]
    if {[llength $hold_paths]>=30000} {error {Hold query coverage cap reached}}
    set candidates {}
    set sensitive {}
    set other 0
    set f [open [file join $out relocation_setup_sensitive.tsv] w]
    puts $f "cell\thold_ns\tsetup_sensitive"
    foreach path $hold_paths {
        set endpoint [get_property ENDPOINT_PIN $path]
        set pin [get_pins $endpoint]
        set cell [get_cells -of_objects $pin]
        set source [get_cells -of_objects [get_pins [get_property STARTPOINT_PIN $path]]]
        if {[get_property REF_NAME $source] ni {RAMD32 RAMD64E} || [get_property REF_NAME $cell] ne {FDRE} ||
            [get_property REF_PIN_NAME $pin] ne {D} || [get_property LOC $source] ne [get_property LOC $cell]} {incr other; continue}
        set record [list $cell $endpoint [get_property LOC $cell] [get_property BEL $cell] \
            [relocate_pin_signature $cell] [expr {[get_property SLACK $path]+$hold_margin}] {}]
        set is_sensitive [dict exists $risky [get_property NAME $cell]]
        puts $f "$cell\t[get_property SLACK $path]\t$is_sensitive"
        if {$is_sensitive} {lappend sensitive $record} else {lappend candidates $record}
    }
    close $f
    # Reserve nearby compatible resources for setup-sensitive cells first.
    set candidates [concat $sensitive $candidates]
    set f [open [file join $out relocation_coverage.txt] w]
    puts $f "HOLD_PATHS=[llength $hold_paths]\nCANDIDATES=[llength $candidates]\nSETUP_SENSITIVE=[llength $sensitive]\nSKIPPED_SETUP_RISK=0\nOTHER_SHORT_PATHS=$other\nSETUP_RISK_PATHS=[llength $setup_paths]"
    close $f
    puts "HOLD_RELOCATION_CANDIDATES=[llength $candidates] SETUP_SENSITIVE=[llength $sensitive] OTHER=$other"
    return [relocate_fifo_registers $out $candidates]
}
