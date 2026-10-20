set root [file normalize [lindex $argv 0]]
open_project [file join $root project weather_system.xpr]
set_param general.maxThreads 2
open_run impl_1
foreach type {max min} {
    set path [get_timing_paths -delay_type $type -max_paths 1]
    if {[llength $path] == 0 || [get_property SLACK $path] < 0} {error {Timing gate failed}}
}
close_design
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne {100%}} {error {Bitstream failed}}
set bit [file join $root project weather_system.runs impl_1 system_wrapper.bit]
if {![file isfile $bit]} {error {Bitstream absent}}
file copy -force $bit [file join $root weather_system.bit]
write_hw_platform -fixed -include_bit -force -file [file join $root weather_system.xsa]
puts {WEATHER_SYSTEM_PACKAGE_PASS}
close_project
exit
