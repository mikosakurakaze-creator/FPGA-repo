# Preserve signed truncation boundaries before opt_design. DONT_TOUCH on this
# receiver alone was tested and did NOT prevent the cascade rewrite in 2025.2.
# Use an explicitly checked process-local switch and then validate the netlist.
if {[catch {get_param logicopt.enableDSPCascadeFixing} weather_cascade_setting]} {
    error {Installed Vivado lacks the reviewed DSP cascade switch; no fallback}
}
set_param logicopt.enableDSPCascadeFixing false
if {[get_param logicopt.enableDSPCascadeFixing]} {error {DSP cascade fixing remains enabled}}
set weather_signed_target {system_i/weather_frame_top_0/inst/grp_frame_fu_160/spatial_5_U0/grp_spatial_5_Pipeline_VITIS_LOOP_133_2_fu_450/mac_muladd_15ns_7s_22s_23_4_1_U1742/weather_frame_top_mac_muladd_15ns_7s_22s_23_4_1_DSP48_0_U/p_reg_reg}
set weather_signed_cell [get_cells -quiet $weather_signed_target]
if {[llength $weather_signed_cell] != 1 || [get_property REF_NAME $weather_signed_cell] ne {DSP48E2}} {
    error {Expected weather signed DSP receiver absent; review changed synthesis}
}
set weather_signed_pin [get_pins -quiet "$weather_signed_target/C\[21\]"]
set weather_signed_net [get_nets -quiet -of_objects $weather_signed_pin]
if {[llength $weather_signed_net] != 1} {error {Cannot resolve synthesized C sign net}}
for {set weather_signed_bit 22} {$weather_signed_bit < 48} {incr weather_signed_bit} {
    set weather_signed_upper [get_nets -quiet -of_objects [get_pins -quiet "$weather_signed_target/C\[$weather_signed_bit\]"]]
    if {$weather_signed_upper ne $weather_signed_net} {
        error "Signed C boundary already changed at bit $weather_signed_bit; refusing late protection"
    }
}
proc weather_assert_signed_boundary {} {
    global weather_signed_target
    set c21 [get_nets -quiet -of_objects [get_pins -quiet "$weather_signed_target/C\[21\]"]]
    set c22 [get_nets -quiet -of_objects [get_pins -quiet "$weather_signed_target/C\[22\]"]]
    if {[llength $c21] != 1 || $c21 ne $c22} {
        error {Weather signed truncation boundary was rewritten; candidate rejected}
    }
    puts {WEATHER_SIGNED_C21_C22_BOUNDARY_PRESERVED}
}
weather_assert_signed_boundary
puts {WEATHER_DSP_CASCADE_FIXING_DISABLED process_local=true}
