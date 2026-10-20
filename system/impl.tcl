set root [file normalize [lindex $argv 0]]
open_project [file join $root project weather_system.xpr]
set_param general.maxThreads 2
launch_runs impl_1 -to_step route_design -jobs 1
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne {100%}} {error {Implementation failed}}
open_run impl_1
report_utilization -hierarchical -file [file join $root routed_utilization.rpt]
report_utilization -file [file join $root routed_utilization_summary.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $root routed_timing.rpt]
report_route_status -file [file join $root route_status.rpt]
report_drc -file [file join $root routed_drc.rpt]
write_checkpoint -force [file join $root system_routed.dcp]
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup] == 0 || [llength $hold] == 0} {error {Timing paths absent}}
if {[get_property SLACK $setup] < 0 || [get_property SLACK $hold] < 0} {error {Routed timing failed}}
puts {WEATHER_SYSTEM_IMPL_PASS}
close_project
exit
