# Read actual parent wires named by the primitive port connections. XSim
# optimizes primitive scopes away, so refer to exported nets, not missing ports.
# Source PCOUT[22]=lopt_53, PCOUT[21]=..._n_84; sink P[22:21]=..._n_0/n_1.
# No force/deposit or guessed sign restoration.
set cascade_base /weather_rtl_test/dut/weather_frame_top_0/inst/grp_frame_fu_160/spatial_5_U0/grp_spatial_5_Pipeline_VITIS_LOOP_133_2_fu_450
set cascade_names {select_ln95_34_reg_11605_reg_n_84 lopt_53 mac_muladd_15ns_7s_22s_23_4_1_U1742_n_0 mac_muladd_15ns_7s_22s_23_4_1_U1742_n_1 q_51_reg_11786 tmp_134_reg_11781 p_8_in}
set cascade_fd [open physical_dsp_cascade.txt w]
puts $cascade_fd "sample source_PCOUT21 source_PCOUT22 sink_P22 sink_P21 magnitude sign enable"
run 4 ns
for {set cascade_sample 0} {$cascade_sample < 4999} {incr cascade_sample} {
    set cascade_frame [get_value -radix hex /weather_rtl_test/active_case]
    if {[string trimleft $cascade_frame 0] eq "1"} {break}
    if {[string trimleft $cascade_frame 0] eq ""} {
        set cascade_row [list $cascade_sample]
        foreach cascade_name $cascade_names {
            lappend cascade_row [get_value -radix bin $cascade_base/$cascade_name]
        }
        puts $cascade_fd [join $cascade_row { }]
    }
    run 10 ns
}
close $cascade_fd
puts {PHYSICAL_DSP_CASCADE_TRACE_COMPLETED}
quit
