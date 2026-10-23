# Retry native platform export from a working directory without spaces.
# Vivado 2025.2's internal write_bitstream command failed with a spaced cwd.
if {$argc != 2} {error {Expected routed checkpoint and new XSA filename}}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error {Refuse to replace native XSA evidence}}
set_param general.maxThreads 2
open_checkpoint $checkpoint
source [file join [file dirname [info script]] protect_weather_signed_dsp.tcl]
write_hw_platform -fixed -include_bit -file $output
puts {WEATHER_CORRECTED_CHECKPOINT_PLATFORM_PASS}
close_design
exit
