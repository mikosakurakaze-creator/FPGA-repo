if {$argc != 2} {error {Expected checkpoint and new diagnostic directory}}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to overwrite diagnostic output}}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
write_verilog -force -mode funcsim [file join $output system_routed_funcsim.v]
puts {WEATHER_DIAGNOSTIC_SYSTEM_EXPORT_COMPLETED}
close_design
exit
