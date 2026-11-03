# Select physical relocation candidates under temporarily tightened targets.
proc collect_and_relocate_fifo {out setup_margin hold_margin} {
    set risky [dict create]
    set setup_paths [get_timing_paths -delay_type max -slack_lesser_than 0.800 -max_paths 200000 -nworst 1]
    if {[llength $setup_paths]>=200000} {error {Setup-risk query reached its coverage cap}}
    foreach path $setup_paths {
        foreach property {STARTPOINT_PIN ENDPOINT_PIN} {
            set pin [get_pins [get_property $property $path]]
            dict set risky [get_property NAME [get_cells -of_objects $pin]] 1
        }
    }
    set hold_paths [get_timing_paths -delay_type min -slack_lesser_than 0.0 -max_paths 30000 -nworst 1]
    if {[llength $hold_paths]>=30000} {error {Hold query reached its coverage cap}}
    set candidates {}
    set skipped 0
    foreach path $hold_paths {
        set endpoint [get_property ENDPOINT_PIN $path]
        set pin [get_pins $endpoint]
        set cell [get_cells -of_objects $pin]
        set source [get_cells -of_objects [get_pins [get_property STARTPOINT_PIN $path]]]
        if {[get_property REF_NAME $source] ni {RAMD32 RAMD64E} || [get_property REF_NAME $cell] ne {FDRE} ||
            [get_property REF_PIN_NAME $pin] ne {D} || [get_property LOC $source] ne [get_property LOC $cell]} {continue}
        if {[dict exists $risky [get_property NAME $cell]]} {incr skipped; continue}
        lappend candidates [list $cell $endpoint [get_property LOC $cell] [get_property BEL $cell] \
            [relocate_pin_signature $cell] [expr {[get_property SLACK $path]+$hold_margin}] {}]
    }
    puts "HOLD_RELOCATION_CANDIDATES=[llength $candidates] SKIPPED_SETUP_RISK=$skipped"
    set f [open [file join $out relocation_coverage.txt] w]
    puts $f "HOLD_PATHS=[llength $hold_paths]\nCANDIDATES=[llength $candidates]\nSKIPPED_SETUP_RISK=$skipped\nSETUP_RISK_PATHS=[llength $setup_paths]"
    close $f
    return [relocate_fifo_registers $out $candidates]
}
