# Read-only positive/negative check of the reviewed DSP boundary.
if {$argc != 2} {error {Expected checkpoint and expected pass (0/1)}}
set checkpoint [file normalize [lindex $argv 0]]
set expected [lindex $argv 1]
if {$expected ni {0 1}} {error {Expected pass must be 0 or 1}}
set_param general.maxThreads 2
open_checkpoint $checkpoint
set failed [catch {source [file join [file dirname [info script]] protect_weather_signed_dsp.tcl]} detail]
puts "WEATHER_SIGNED_BOUNDARY_CHECK actual_pass=[expr {!$failed}] expected_pass=$expected detail=$detail"
if {[expr {!$failed}] != $expected} {error {Signed boundary positive/negative check failed}}
puts {WEATHER_SIGNED_BOUNDARY_VALIDATION_PASS}
close_design
exit
