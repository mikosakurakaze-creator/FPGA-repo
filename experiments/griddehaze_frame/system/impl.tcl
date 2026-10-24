set root [file normalize [lindex $argv 0]]
open_project [file join $root project weather_system.xpr]
set_param general.maxThreads 2
foreach name {protect_weather_signed_dsp.tcl check_weather_signed_dsp.tcl} {
    if {![file isfile [file join $root $name]]} {error "Signed DSP protection absent: $name"}
}
set_property STEPS.OPT_DESIGN.TCL.PRE [file join $root protect_weather_signed_dsp.tcl] [get_runs impl_1]
set_property STEPS.OPT_DESIGN.TCL.POST [file join $root check_weather_signed_dsp.tcl] [get_runs impl_1]
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
write_verilog -force -mode funcsim [file join $root system_routed_funcsim.v]
foreach type {max min} {
    set path [get_timing_paths -delay_type $type -max_paths 1]
    if {[llength $path]==0 || [get_property SLACK $path]<0} {error "Routed timing failed: $type"}
}
puts {GRID_SYSTEM_IMPL_PASS}
close_project
exit
