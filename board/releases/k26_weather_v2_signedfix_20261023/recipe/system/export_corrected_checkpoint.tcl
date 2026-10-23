# Export only this corrected routed design, never the old project's impl run.
if {$argc != 2} {error {Expected routed checkpoint and new export directory}}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to overwrite board export}}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
if {[get_property PART [current_project]] ne {xck26-sfvc784-2LV-c}} {error {Wrong FPGA part}}
source [file join [file dirname [info script]] protect_weather_signed_dsp.tcl]
foreach type {max min} {
    set path [get_timing_paths -delay_type $type -max_paths 1]
    if {[llength $path] == 0 || [get_property SLACK $path] < 0} {error {Routed timing failed}}
}
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $output routed_timing.rpt]
report_route_status -file [file join $output route_status.rpt]
report_utilization -file [file join $output routed_utilization_summary.rpt]
report_drc -file [file join $output routed_drc.rpt]
if {[llength [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]]} {
    error {Blocking DRC violations present}
}
write_bitstream [file join $output weather_system.bit]
puts {WEATHER_CORRECTED_CHECKPOINT_BIT_PASS}
# A standalone DCP might lack BD/PFM metadata. Preserve the actual result;
# never silently export the old project's bit to fill this gap.
set native_failed [catch {
    write_hw_platform -fixed -include_bit -file [file join $output weather_system.xsa]
} native_detail]
set status [open [file join $output native_xsa_status.txt] w]
puts $status "native_export_pass=[expr {!$native_failed}]"
puts $status $native_detail
close $status
puts "WEATHER_CORRECTED_NATIVE_XSA_PASS=[expr {!$native_failed}]"
close_design
exit
