# First validate the protected opt checkpoint numerically before implementation.
if {$argc != 2} {error {Expected linked synthesis checkpoint and new output directory}}
set source [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to replace diagnostic evidence}}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source
source [file join [file dirname [info script]] protect_weather_signed_dsp.tcl]
opt_design
weather_assert_signed_boundary
write_checkpoint [file join $output system_protected_opt.dcp]
write_verilog -mode funcsim [file join $output system_protected_opt_funcsim.v]
puts {WEATHER_PROTECTED_OPTIMIZATION_COMPLETED}
close_design
exit
