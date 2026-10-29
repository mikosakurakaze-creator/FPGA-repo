if {$argc != 2} {error {Expected source file and new build directory}}
set source [file normalize [lindex $argv 0]]
set root [file normalize [lindex $argv 1]]
file mkdir $root
set_param general.maxThreads 2
create_project fusion_ooc [file join $root project] -part xck26-sfvc784-2LV-c
read_verilog [list $source]
set_property top joint_fusion [current_fileset]
set xdc [file join $root fusion_ooc.xdc]
set stream [open $xdc w]
puts $stream {create_clock -name ap_clk -period 10.000 [get_ports ap_clk]}
puts $stream {set_input_delay 1.0 -clock ap_clk [get_ports -filter {DIRECTION == IN && NAME != ap_clk}]}
puts $stream {set_output_delay 1.0 -clock ap_clk [all_outputs]}
close $stream
add_files -fileset constrs_1 [list $xdc]
synth_design -top joint_fusion -mode out_of_context -part xck26-sfvc784-2LV-c
if {[llength [get_clocks ap_clk -quiet]] != 1} {read_xdc $xdc}
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} {error {Unresolved blackbox}}
report_utilization -file [file join $root utilization.rpt]
report_timing_summary -delay_type min_max -file [file join $root timing.rpt]
report_drc -file [file join $root drc.rpt]
write_checkpoint [file join $root fusion_ooc.dcp]
puts {FUSION_OOC_SYNTHESIS_PASS}
close_design
close_project
exit
