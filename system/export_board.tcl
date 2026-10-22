if {$argc != 2} {error {Expected existing build directory and new output directory}}
set build [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to overwrite a board export}}
file mkdir $output
set_param general.maxThreads 2
open_project [file join $build project weather_system.xpr]
if {[get_property PART [current_project]] ne {xck26-sfvc784-2LV-c}} {
    error {Unexpected FPGA part}
}
set run [get_runs impl_1]
if {[get_property PROGRESS $run] ne {100%} ||
    ![string match {*write_bitstream Complete*} [get_property STATUS $run]]} {
    error {A completed routed bitstream run is required}
}
set bit [file join $build project weather_system.runs impl_1 system_wrapper.bit]
if {![file isfile $bit]} {error {Implemented bitstream absent}}
open_run impl_1
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup] == 0 || [llength $hold] == 0 ||
    [get_property SLACK $setup] < 0 || [get_property SLACK $hold] < 0} {
    error {Routed setup/hold timing gate failed}
}
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose \
    -file [file join $output routed_timing.rpt]
report_route_status -file [file join $output route_status.rpt]
report_utilization -file [file join $output routed_utilization_summary.rpt]
report_drc -file [file join $output routed_drc.rpt]
set blockers [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]
if {[llength $blockers] != 0} {error {Blocking DRC violations present}}
close_design
file copy $bit [file join $output weather_system.bit]
write_hw_platform -fixed -include_bit -force -file [file join $output weather_system.xsa]
puts {WEATHER_BOARD_EXPORT_PASS}
close_project
exit
