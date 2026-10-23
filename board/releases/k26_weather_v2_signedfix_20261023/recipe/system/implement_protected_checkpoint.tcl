# Reimplement in isolation; numerical validation must pass before release.
if {$argc != 2} {error {Expected protected opt checkpoint and new output directory}}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to replace implementation evidence}}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
source [file join [file dirname [info script]] protect_weather_signed_dsp.tcl]
place_design
phys_opt_design
route_design
weather_assert_signed_boundary
report_utilization -hierarchical -file [file join $output routed_utilization.rpt]
report_utilization -file [file join $output routed_utilization_summary.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $output routed_timing.rpt]
report_route_status -file [file join $output route_status.rpt]
report_drc -file [file join $output routed_drc.rpt]
write_checkpoint [file join $output system_routed.dcp]
write_verilog -mode funcsim [file join $output system_routed_funcsim.v]
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup] == 0 || [llength $hold] == 0} {error {Timing paths absent}}
if {[get_property SLACK $setup] < 0 || [get_property SLACK $hold] < 0} {error {Routed timing failed}}
puts {WEATHER_SIGNED_FIX_IMPLEMENTATION_COMPLETED}
close_design
exit
