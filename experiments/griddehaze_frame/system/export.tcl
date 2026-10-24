set root [file normalize [lindex $argv 0]]
open_project [file join $root project weather_system.xpr]
set_param general.maxThreads 2
set signoff_marker [file join $root routed_signoff.pass]
if {![file isfile $signoff_marker]} {error {Validated routed timing signoff marker absent}}
set marker_file [open $signoff_marker r]
set marker_text [string trim [read $marker_file]]
close $marker_file
if {![string match {GRID_ROUTED_SIGNOFF_PASS *} $marker_text]} {error {Validated routed timing signoff marker invalid}}
open_run impl_1
foreach type {max min} {
    set path [get_timing_paths -delay_type $type -max_paths 1]
    if {[llength $path]==0 || [get_property SLACK $path]<0} {error {Routed timing gate failed}}
}
close_design
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne {100%}} {error {Bitstream generation failed}}
file copy [file join $root project weather_system.runs impl_1 system_wrapper.bit] [file join $root griddehaze_system.bit]
write_hw_platform -fixed -include_bit -force -file [file join $root griddehaze_system.xsa]
puts {GRID_SYSTEM_EXPORT_PASS}
close_project
exit
