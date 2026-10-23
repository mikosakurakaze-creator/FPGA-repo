# Observe existing routed signals, with no force/deposit or reconstructed bits.
# The exported RTL uses q_51 (unsigned magnitude) and tmp_134 (sign) before
# the task=0 channel2 pointwise saturation. Sample 1 ns before rising edge.
set quant_base /weather_rtl_test/dut/weather_frame_top_0/inst/grp_frame_fu_160/spatial_5_U0/grp_spatial_5_Pipeline_VITIS_LOOP_133_2_fu_450
set quant_names {q_51_reg_11786 tmp_134_reg_11781 icmp_ln61_29_fu_6856_p2 retval_0_i_i_2_reg_11860 p_8_in}
set quant_fd [open physical_quantization.txt w]
puts $quant_fd "sample [join $quant_names { }]"
run 4 ns
for {set quant_sample 0} {$quant_sample < 4999} {incr quant_sample} {
    set quant_frame [get_value -radix hex /weather_rtl_test/active_case]
    if {[string trimleft $quant_frame 0] eq "1"} {break}
    if {[string trimleft $quant_frame 0] eq ""} {
        set quant_row [list $quant_sample]
        foreach quant_name $quant_names {
            lappend quant_row [get_value -radix bin $quant_base/$quant_name]
        }
        puts $quant_fd [join $quant_row { }]
    }
    run 10 ns
}
close $quant_fd
puts {PHYSICAL_QUANTIZATION_TRACE_COMPLETED}
quit
