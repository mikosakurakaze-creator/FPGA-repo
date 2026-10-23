# Inspect the exact routed stage5 c2 residual-add/saturation cone, before edge.
set sat_base /weather_rtl_test/dut/weather_frame_top_0/inst/grp_frame_fu_160/spatial_5_U0/grp_spatial_5_Pipeline_VITIS_LOOP_133_2_fu_450
set sat_names {retval_0_i_i_2_reg_11860 v_assign_2_reg_11299_pp0_iter12_reg add_ln188_4_fu_7651_p2 add_ln188_5_fu_7655_p2 icmp_ln61_31_fu_7661_p2}
set sat_fd [open physical_saturation.txt w]
puts $sat_fd "sample [join $sat_names { }]"
run 4 ns
for {set sat_sample 0} {$sat_sample < 4999} {incr sat_sample} {
    set sat_frame [get_value -radix hex /weather_rtl_test/active_case]
    if {[string trimleft $sat_frame 0] eq "1"} {break}
    if {[string trimleft $sat_frame 0] eq "" && [get_value -radix bin $sat_base/p_8_in] eq "1"} {
        set sat_row [list $sat_sample]
        foreach sat_name $sat_names {
            lappend sat_row [get_value -radix bin $sat_base/$sat_name]
        }
        puts $sat_fd [join $sat_row { }]
        flush $sat_fd
    }
    run 10 ns
}
close $sat_fd
puts {PHYSICAL_SATURATION_TRACE_COMPLETED}
quit
