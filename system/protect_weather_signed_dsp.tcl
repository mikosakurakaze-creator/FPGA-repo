# Preserve signed truncation boundaries before opt_design. DONT_TOUCH on this
# receiver alone was tested and did NOT prevent the cascade rewrite in 2025.2.
# Use an explicitly checked process-local switch and then validate the netlist.
if {[catch {get_param logicopt.enableDSPCascadeFixing} weather_cascade_setting]} {
    error {Installed Vivado lacks the reviewed DSP cascade switch; no fallback}
}
set_param logicopt.enableDSPCascadeFixing false
if {[get_param logicopt.enableDSPCascadeFixing]} {error {DSP cascade fixing remains enabled}}
set ::weather_signed_base {system_i/weather_frame_top_0/inst/grp_frame_fu_160/spatial_5_U0/grp_spatial_5_Pipeline_VITIS_LOOP_133_2_fu_450}
set ::weather_signed_target $::weather_signed_base/mac_muladd_15ns_7s_22s_23_4_1_U1742/weather_frame_top_mac_muladd_15ns_7s_22s_23_4_1_DSP48_0_U/p_reg_reg
set ::weather_signed_source $::weather_signed_base/select_ln95_34_reg_11605_reg
proc weather_pin_drivers {pin_name} {
    set pin [get_pins -quiet $pin_name]
    if {[llength $pin] != 1} {error "Expected exactly one DSP pin: $pin_name"}
    set nets [get_nets -quiet -segments -of_objects $pin]
    set drivers [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == OUT}]
    if {[llength $drivers] != 1} {error "Expected one leaf driver: $pin_name"}
    return $drivers
}
proc weather_assert_signed_boundary {} {
    global weather_signed_target weather_signed_source
    foreach target [list $weather_signed_target $weather_signed_source] {
        set cell [get_cells -quiet $target]
        if {[llength $cell] != 1 || [get_property REF_NAME $cell] ne {DSP48E2}} {
            error "Expected reviewed DSP absent: $target; review changed synthesis"
        }
    }
    # Equality of C21/C22 alone also accepts the faulty all-VCC connection.
    # Check every C bit against the actual preceding DSP P bit instead.
    for {set bit 0} {$bit < 48} {incr bit} {
        set source_bit [expr {min($bit, 21)}]
        set actual [weather_pin_drivers "$weather_signed_target/C\[$bit\]"]
        set expected [weather_pin_drivers "$weather_signed_source/P\[$source_bit\]"]
        if {$actual ne $expected} {error "Weather signed C source differs at bit $bit"}
    }
    # Effective Z selection must remain C (011), rather than PCIN (001).
    foreach bit {4 5 6} expected {1 1 0} {
        set driver [weather_pin_drivers "$weather_signed_target/OPMODE\[$bit\]"]
        set kind [get_property REF_NAME [get_cells -of_objects $driver]]
        if {$kind ni {VCC GND}} {error {Unexpected dynamic weather DSP Z selector}}
        set value [expr {$kind eq {VCC}}]
        set cell [get_cells $weather_signed_target]
        if {{IS_OPMODE_INVERTED} in [list_property $cell]} {
            set inverted [get_property IS_OPMODE_INVERTED $cell]
            set inverted_text $inverted
            # Unset Vivado property uses the installed DSP48E2 primitive's 0 default.
            if {$inverted eq {}} {set inverted 0}
            if {[regexp {^[0-9]+'[hH]([0-9a-fA-F]+)$} $inverted -> hex]} {scan $hex %x inverted}
            if {[regexp {^[0-9]+'[bB]([01]+)$} $inverted -> binary]} {scan $binary %b inverted}
            if {![string is integer -strict $inverted]} {error "Unsupported OPMODE inversion encoding: <$inverted_text>"}
            set value [expr {$value ^ (($inverted >> $bit) & 1)}]
        }
        if {$value != $expected} {error {Weather DSP no longer selects signed C}}
    }
    puts {WEATHER_SIGNED_C_SOURCE_AND_OPMODE_PRESERVED}
}
weather_assert_signed_boundary
puts {WEATHER_DSP_CASCADE_FIXING_DISABLED process_local=true}
