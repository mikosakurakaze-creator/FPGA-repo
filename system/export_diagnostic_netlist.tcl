if {$argc != 2} {error {Expected routed checkpoint and new diagnostic directory}}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to overwrite diagnostic output}}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set core [get_cells -hierarchical -filter {NAME == system_i/weather_frame_top_0}]
if {[llength $core] != 1} {error {Expected exactly one weather core}}
report_property -all $core -file [file join $output core_properties.txt]
write_verilog -force -mode funcsim -cell $core [file join $output weather_routed_funcsim.v]
set urams [get_cells -hierarchical -filter {REF_NAME == URAM288 && NAME =~ system_i/weather_frame_top_0/*}]
set fp [open [file join $output uram_properties.txt] w]
puts $fp "URAM_COUNT=[llength $urams]"
close $fp
foreach cell $urams {
    report_property -all $cell -append -file [file join $output uram_properties.txt]
}
report_timing_summary -delay_type min_max -file [file join $output routed_timing.rpt]
puts {WEATHER_DIAGNOSTIC_NETLIST_EXPORT_PASS}
close_design
exit
