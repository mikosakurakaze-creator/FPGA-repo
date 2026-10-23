# Reuse the exact physical_path04 simulation snapshot. Fixed 100 MHz stimulus.
# Sample 1 ns BEFORE each rising edge, avoiding post-NBA sampling ambiguity.
# if_din is the actual 168-bit FIFO input port. No removed sign bits are filled.
set trace_base /weather_rtl_test/dut/weather_frame_top_0/inst/grp_frame_fu_160
for {set trace_stage 0} {$trace_stage < 6} {incr trace_stage} {
    set trace_fd($trace_stage) [open physical_stage_${trace_stage}.txt w]
}
run 4 ns
for {set trace_sample 0} {$trace_sample < 4999} {incr trace_sample} {
    set trace_frame [get_value -radix hex /weather_rtl_test/active_case]
    if {[string trimleft $trace_frame 0] eq "1"} {break}
    if {[string trimleft $trace_frame 0] eq ""} {
        for {set trace_stage 0} {$trace_stage < 6} {incr trace_stage} {
            set trace_fifo [expr {$trace_stage + 1}]
            set trace_valid [get_value -radix bin $trace_base/spatial_${trace_stage}_U0_s${trace_fifo}_write]
            set trace_ready [get_value -radix bin $trace_base/s${trace_fifo}_full_n]
            if {$trace_valid eq "1" && $trace_ready eq "1"} {
                set trace_packet [get_value -radix hex $trace_base/s${trace_fifo}_U/if_din]
                puts $trace_fd($trace_stage) "$trace_frame $trace_sample $trace_packet"
                flush $trace_fd($trace_stage)
            }
        }
    }
    run 10 ns
}
for {set trace_stage 0} {$trace_stage < 6} {incr trace_stage} {
    close $trace_fd($trace_stage)
}
puts {PHYSICAL_FIRST_FRAME_TRACE_COMPLETED}
quit
