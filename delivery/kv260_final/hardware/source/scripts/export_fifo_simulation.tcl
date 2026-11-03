if {$argc != 7} {error {Use the isolated diagnostic runner}}
set out [file normalize [lindex $argv 1]]
open_project D:/weather_builds/timing_margin_20261102/fifo_configuration03/project/fifo_probe.xpr
export_simulation -of_objects [get_files */fifo_probe.bd] -simulator xsim -directory [file join $out export] -scripts_only -use_ip_compiled_libs
close_project
puts {TIMING_MARGIN_INSPECT_PASS}
exit
